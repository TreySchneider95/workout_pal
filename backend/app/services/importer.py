"""Idempotent import of the exercise library and weekly plan.

Sources
-------
* Library CSV (``home_gym_exercises_verified.csv``): every exercise the gym supports.
* Plan (``home_gym_workout_with_images.zip`` or the CSV inside it plus an ``images/``
  folder next to it): the weekly schedule, starting weights, weight conventions and
  demonstration images.

Rules
-----
* Exercises are upserted by their stable IDs (EX0001...). Running twice changes nothing.
* Templates belong to one profile (the owner by default), are matched by session name
  within it and synced to the plan. Custom templates
  (not in the plan) are left alone. A template exercise's "skipped" flag is preserved.
* Workout history (sessions and sets) is never read or modified.
* The whole import runs in one transaction: validation errors abort without changes.
"""

import csv
import hashlib
import io
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Equipment,
    Exercise,
    LoadType,
    Profile,
    TrackingType,
    WorkoutTemplate,
    WorkoutTemplateExercise,
)
from app.services.plan import WEEKDAYS
from app.services.prescription import parse_prescription

IMAGE_DIR = "exercise-images"
THUMB_DIR = f"{IMAGE_DIR}/thumbs"
THUMB_WIDTH = 640

EXERCISE_ID_RE = re.compile(r"^EX\d{4}$")
PULLEY_RE = re.compile(r"^\d+:\d+$")

LIBRARY_COLUMNS = {"exercise_id", "exercise_name", "primary_muscle_group", "equipment",
                   "attachment", "tracking_type", "track_per_side"}
PLAN_COLUMNS = {"week_day", "session", "order", "exercise_id", "exercise_name",
                "sets_week_1_2", "sets_week_3_plus", "reps_or_duration", "starting_weight",
                "weight_unit", "pulley_ratio", "rest_seconds", "notes", "image_key", "image_path"}

PLAN_LOAD_TYPES = {
    "lb_per_dumbbell": LoadType.per_dumbbell,
    "lb_single_dumbbell": LoadType.single_dumbbell,
    "lb_plates_loaded": LoadType.plates_loaded,
    "lb_added_plates": LoadType.added_plates,
    "bodyweight": LoadType.bodyweight,
}

LIBRARY_TRACKING = {
    "weight_reps": TrackingType.strength,
    "weight_reps_or_distance": TrackingType.strength,
    "weight_reps_or_seconds": TrackingType.strength,
    "reps": TrackingType.bodyweight,
    "reps_or_seconds": TrackingType.bodyweight,
    "time_distance_speed": TrackingType.cardio,
}
# Exercises whose "_or_seconds" tracking is naturally a timed hold.
_HOLD_RE = re.compile(r"\b(hold|hang|wall sit)\b|^(forearm|high|side) plank$", re.IGNORECASE)

# Default equipment. Increments are only set when the row is first created, so
# values edited in Settings survive re-imports.
DEFAULT_EQUIPMENT = {
    "dumbbells": dict(name="Dumbbells", equipment_type="dumbbell",
                      available_weights=[float(w) for w in range(5, 55, 5)], weight_increment=5.0,
                      notes="Weights are per dumbbell. Edit the list to match your set."),
    "goimu-wm1": dict(name="Goimu WM1", equipment_type="cable", weight_increment=5.0,
                      notes="Plate-loaded cable. Record loaded plate weight; pulley ratio is stored per exercise."),
    "ritfit-pulley": dict(name="RitFit PSR05 2.0 pulleys", equipment_type="cable", weight_increment=5.0,
                          notes="High and low pulleys. Record loaded plate weight."),
    "ritfit-smith": dict(name="RitFit PSR05 2.0 Smith machine", equipment_type="smith_machine",
                         weight_increment=5.0,
                         notes="Record plates added to the bar only. Bar weight is not included."),
    "ritfit-pullup": dict(name="RitFit PSR05 2.0 pull-up bar", equipment_type="bodyweight",
                          weight_increment=5.0, notes=None),
    "bodyweight": dict(name="Bodyweight", equipment_type="bodyweight", weight_increment=5.0,
                       notes="Optional added weight."),
    "treadmill": dict(name="Treadmill", equipment_type="cardio", weight_increment=None, notes=None),
}


@dataclass
class ImportReport:
    exercises_created: int = 0
    exercises_updated: int = 0
    exercises_unchanged: int = 0
    templates_created: int = 0
    templates_updated: int = 0
    template_exercises: int = 0
    images_copied: int = 0
    images_verified: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    created_ids: set[str] = field(default_factory=set)
    updated_ids: set[str] = field(default_factory=set)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        lines = [
            f"Exercises: {self.exercises_created} created, {self.exercises_updated} updated, "
            f"{self.exercises_unchanged} unchanged",
            f"Templates: {self.templates_created} created, {self.templates_updated} synced "
            f"({self.template_exercises} exercise slots)",
            f"Images: {self.images_verified} verified, {self.images_copied} copied",
        ]
        lines += [f"WARNING: {w}" for w in self.warnings]
        lines += [f"ERROR: {e}" for e in self.errors]
        return "\n".join(lines)


class ImportAborted(Exception):
    def __init__(self, report: ImportReport):
        super().__init__("Import aborted:\n" + "\n".join(report.errors))
        self.report = report


# --------------------------------------------------------------------------- sources


def _read_csv(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    return [{k.strip(): (v or "").strip() for k, v in row.items() if k} for row in reader]


@dataclass
class PlanSource:
    rows: list[dict[str, str]]
    read_file: Callable[[str], bytes | None]  # relative path inside the source -> bytes
    description: str


def open_plan(path: Path) -> PlanSource:
    """Open a plan ZIP, or a plan CSV with images in a sibling directory."""
    if zipfile.is_zipfile(path):
        archive = zipfile.ZipFile(path)
        names = [n for n in archive.namelist() if not n.startswith("__MACOSX")]
        csvs = [n for n in names if n.lower().endswith(".csv")]
        if len(csvs) != 1:
            raise ValueError(f"{path.name}: expected exactly one CSV in the archive, found {csvs}")
        csv_name = csvs[0]
        base = csv_name.rsplit("/", 1)[0] + "/" if "/" in csv_name else ""
        members = set(names)

        def read_zip(rel: str) -> bytes | None:
            name = base + rel
            return archive.read(name) if name in members else None

        rows = _read_csv(archive.read(csv_name).decode("utf-8-sig"))
        return PlanSource(rows, read_zip, f"{path.name}:{csv_name}")

    base_dir = path.parent

    def read_dir(rel: str) -> bytes | None:
        target = (base_dir / rel).resolve()
        if base_dir.resolve() not in target.parents or not target.is_file():
            return None
        return target.read_bytes()

    return PlanSource(_read_csv(path.read_text(encoding="utf-8-sig")), read_dir, path.name)


# --------------------------------------------------------------------------- helpers


def _equipment_slug(text: str) -> str | None:
    t = text.lower()
    if t.startswith("dumbbell"):
        return "dumbbells"
    if "goimu" in t:
        return "goimu-wm1"
    if "smith" in t:
        return "ritfit-smith"
    if "pulley" in t:
        return "ritfit-pulley"
    if "pull-up" in t:
        return "ritfit-pullup"
    if "treadmill" in t:
        return "treadmill"
    if "bodyweight" in t:
        return "bodyweight"
    return None


_SLUG_LOAD = {
    "dumbbells": LoadType.per_dumbbell,
    "goimu-wm1": LoadType.plates_loaded,
    "ritfit-pulley": LoadType.plates_loaded,
    "ritfit-smith": LoadType.added_plates,
    "ritfit-pullup": LoadType.bodyweight,
    "bodyweight": LoadType.bodyweight,
    "treadmill": LoadType.none,
}


def _split_muscles(text: str) -> tuple[str | None, list[str]]:
    parts = [p.strip() for p in text.split(";") if p.strip()]
    return (parts[0] if parts else None), parts[1:]


def _int(value: str, label: str, errors: list[str], *, minimum: int = 0) -> int | None:
    try:
        number = int(float(value))
    except ValueError:
        errors.append(f"{label}: '{value}' is not a number")
        return None
    if number < minimum:
        errors.append(f"{label}: {number} is below {minimum}")
        return None
    return number


def _float(value: str, label: str, errors: list[str]) -> float | None:
    if value == "":
        return None
    try:
        number = float(value)
    except ValueError:
        errors.append(f"{label}: '{value}' is not a number")
        return None
    if number < 0:
        errors.append(f"{label}: weight cannot be negative")
        return None
    return number


def _set_if_changed(obj: object, values: dict[str, object]) -> bool:
    changed = False
    for key, value in values.items():
        if getattr(obj, key) != value:
            setattr(obj, key, value)
            changed = True
    return changed


def ensure_equipment(db: Session) -> dict[str, Equipment]:
    existing = {e.slug: e for e in db.scalars(select(Equipment))}
    for slug, values in DEFAULT_EQUIPMENT.items():
        if slug not in existing:
            equipment = Equipment(slug=slug, **values)
            db.add(equipment)
            existing[slug] = equipment
    db.flush()
    return existing


# --------------------------------------------------------------------------- images


def store_image(
    data: bytes, filename: str, media_dir: Path, report: ImportReport
) -> bool:
    """Verify an image and copy it (plus a phone-sized thumbnail) into the media dir."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
    except (UnidentifiedImageError, OSError) as exc:
        report.warnings.append(f"Image {filename} is not a valid image ({exc}); placeholder will be used")
        return False
    report.images_verified += 1

    target = media_dir / IMAGE_DIR / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()
    if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        target.write_bytes(data)
        report.images_copied += 1

    thumb = media_dir / THUMB_DIR / (Path(filename).stem + ".webp")
    if not thumb.exists() or thumb.stat().st_mtime < target.stat().st_mtime:
        thumb.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(target) as img:
            img = img.convert("RGB")
            if img.width > THUMB_WIDTH:
                img = img.resize((THUMB_WIDTH, round(img.height * THUMB_WIDTH / img.width)))
            img.save(thumb, "WEBP", quality=80)
    return True


# --------------------------------------------------------------------------- library


def _import_library(
    db: Session, rows: list[dict[str, str]], equipment: dict[str, Equipment], report: ImportReport
) -> dict[str, Exercise]:
    if rows and not LIBRARY_COLUMNS <= rows[0].keys():
        report.errors.append(f"Library CSV missing columns: {sorted(LIBRARY_COLUMNS - rows[0].keys())}")
        return {}

    exercises = {e.id: e for e in db.scalars(select(Exercise))}
    seen: set[str] = set()
    for line, row in enumerate(rows, start=2):
        ex_id = row["exercise_id"].upper()
        label = f"Library line {line} ({ex_id or '?'})"
        if not EXERCISE_ID_RE.match(ex_id):
            report.errors.append(f"{label}: invalid exercise_id '{row['exercise_id']}'")
            continue
        if ex_id in seen:
            report.warnings.append(f"{label}: duplicate exercise_id, later row ignored")
            continue
        seen.add(ex_id)
        if not row["exercise_name"]:
            report.errors.append(f"{label}: missing exercise_name")
            continue
        tracking = LIBRARY_TRACKING.get(row["tracking_type"])
        if tracking is None:
            report.errors.append(f"{label}: unknown tracking_type '{row['tracking_type']}'")
            continue
        if row["tracking_type"].endswith("_or_seconds") and _HOLD_RE.search(row["exercise_name"]):
            tracking = TrackingType.timed

        slug = _equipment_slug(row["equipment"])
        if slug is None and row["equipment"]:
            report.warnings.append(f"{label}: unrecognised equipment '{row['equipment']}'")
        primary, secondary = _split_muscles(row["primary_muscle_group"])
        values: dict[str, object] = dict(
            name=row["exercise_name"],
            primary_muscle_group=primary,
            secondary_muscles=secondary,
            equipment_id=equipment[slug].id if slug else None,
            equipment_detail=row["equipment"] or None,
            attachment=row["attachment"] or None,
            tracking_type=tracking.value,
            unilateral=row["track_per_side"].lower() in {"yes", "y", "true", "1"},
        )
        exercise = exercises.get(ex_id)
        if exercise is None:
            exercise = Exercise(id=ex_id, load_type=_SLUG_LOAD.get(slug or "", LoadType.none).value,
                                **values)
            db.add(exercise)
            exercises[ex_id] = exercise
            report.exercises_created += 1
            report.created_ids.add(ex_id)
        elif _set_if_changed(exercise, values):
            report.exercises_updated += 1
            report.updated_ids.add(ex_id)
        else:
            report.exercises_unchanged += 1
    return exercises


# --------------------------------------------------------------------------- plan


def _import_plan(
    db: Session,
    plan: PlanSource,
    exercises: dict[str, Exercise],
    equipment: dict[str, Equipment],
    media_dir: Path,
    report: ImportReport,
    *,
    sync_templates: bool,
    library_loaded: bool,
    profile_id: int | None,
) -> None:
    rows = plan.rows
    if not rows:
        report.errors.append(f"{plan.description}: plan CSV has no rows")
        return
    if not PLAN_COLUMNS <= rows[0].keys():
        report.errors.append(f"Plan CSV missing columns: {sorted(PLAN_COLUMNS - rows[0].keys())}")
        return

    # ---- validate every row first
    parsed: list[dict[str, object]] = []
    for line, row in enumerate(rows, start=2):
        errors: list[str] = []
        ex_id = row["exercise_id"].upper()
        label = f"Plan line {line} ({ex_id or '?'})"
        if not EXERCISE_ID_RE.match(ex_id):
            report.errors.append(f"{label}: invalid exercise_id '{row['exercise_id']}'")
            continue
        weekday = WEEKDAYS.index(row["week_day"].title()) if row["week_day"].title() in WEEKDAYS else None
        if weekday is None:
            errors.append(f"unknown week_day '{row['week_day']}'")
        if not row["session"]:
            errors.append("missing session name")
        order = _int(row["order"], "order", errors, minimum=1)
        ramp_sets = _int(row["sets_week_1_2"], "sets_week_1_2", errors, minimum=1)
        target_sets = _int(row["sets_week_3_plus"], "sets_week_3_plus", errors, minimum=1)
        rest = _int(row["rest_seconds"] or "0", "rest_seconds", errors)
        weight = _float(row["starting_weight"], "starting_weight", errors)
        prescription = parse_prescription(row["reps_or_duration"])
        if prescription is None:
            errors.append(f"cannot parse reps_or_duration '{row['reps_or_duration']}'")
        load_type = PLAN_LOAD_TYPES.get(row["weight_unit"])
        if load_type is None:
            errors.append(f"unknown weight_unit '{row['weight_unit']}'")
        if row["pulley_ratio"] and not PULLEY_RE.match(row["pulley_ratio"]):
            errors.append(f"invalid pulley_ratio '{row['pulley_ratio']}'")
        if errors:
            report.errors.extend(f"{label}: {e}" for e in errors)
            continue
        parsed.append(dict(row=row, ex_id=ex_id, label=label, weekday=weekday, order=order,
                           ramp_sets=ramp_sets, target_sets=target_sets, rest=rest, weight=weight,
                           prescription=prescription, load_type=load_type))

    if report.errors:
        return

    # ---- exercises referenced by the plan (+ images)
    handled: set[str] = set()
    for item in parsed:
        row, ex_id, label = item["row"], item["ex_id"], item["label"]
        exercise = exercises.get(ex_id)
        if exercise is None:
            if library_loaded:
                report.warnings.append(f"{label}: '{row['exercise_name']}' is not in the library; created from the plan")
            exercise = Exercise(id=ex_id, name=row["exercise_name"], secondary_muscles=[],
                                tracking_type=TrackingType.strength.value,
                                load_type=LoadType.none.value)
            db.add(exercise)
            exercises[ex_id] = exercise
            report.exercises_created += 1
            report.created_ids.add(ex_id)
        elif exercise.name != row["exercise_name"]:
            report.warnings.append(
                f"{label}: plan name '{row['exercise_name']}' differs from library name '{exercise.name}'"
            )
        if ex_id in handled:
            # Same exercise scheduled twice: one record, already updated.
            continue
        handled.add(ex_id)

        load_type: LoadType = item["load_type"]
        if exercise.tracking_type == TrackingType.cardio:
            load_type = LoadType.none
        values: dict[str, object] = dict(
            load_type=load_type.value,
            pulley_ratio=row["pulley_ratio"] or None,
            starting_weight=item["weight"],
        )
        prescription = item["prescription"]
        if prescription.is_duration and exercise.tracking_type == TrackingType.bodyweight:
            values["tracking_type"] = TrackingType.timed.value

        image_rel = row["image_path"] or (f"images/{row['image_key']}" if row["image_key"] else "")
        if image_rel:
            filename = row["image_key"] or Path(image_rel).name
            data = plan.read_file(image_rel)
            if data is None:
                report.warnings.append(f"{label}: image '{image_rel}' not found; placeholder will be used")
            elif store_image(data, filename, media_dir, report):
                values["image_key"] = filename
                values["image_path"] = f"{IMAGE_DIR}/{filename}"
        else:
            report.warnings.append(f"{label}: no image reference")

        changed = _set_if_changed(exercise, values)
        if changed and ex_id not in report.created_ids and ex_id not in report.updated_ids:
            report.updated_ids.add(ex_id)
            report.exercises_updated += 1
            if report.exercises_unchanged and library_loaded:
                report.exercises_unchanged -= 1

    db.flush()
    if not sync_templates:
        return

    # ---- templates, matched by session name within the profile
    if profile_id is None:
        profile_id = db.scalar(select(Profile.id).order_by(Profile.id))
    if profile_id is None or db.get(Profile, profile_id) is None:
        report.errors.append("No profile to import the plan into")
        return
    templates = {t.name: t for t in db.scalars(select(WorkoutTemplate).where(WorkoutTemplate.profile_id == profile_id))}
    by_session: dict[str, list[dict[str, object]]] = {}
    for item in parsed:
        by_session.setdefault(item["row"]["session"], []).append(item)

    for name, items in by_session.items():
        weekdays = {i["weekday"] for i in items}
        if len(weekdays) > 1:
            report.warnings.append(f"Session '{name}' appears on several days; using {WEEKDAYS[items[0]['weekday']]}")
        weekday = items[0]["weekday"]
        template = templates.get(name)
        if template is None:
            template = WorkoutTemplate(name=name, profile_id=profile_id)
            db.add(template)
            templates[name] = template
            report.templates_created += 1
        else:
            report.templates_updated += 1

        # Free the weekday if another template currently occupies it.
        for other in templates.values():
            if other is not template and other.weekday == weekday:
                report.warnings.append(
                    f"'{other.name}' was scheduled on {WEEKDAYS[weekday]}; unscheduled to make room for '{name}'"
                )
                other.weekday = None
        db.flush()
        template.weekday = weekday

        existing = {te.exercise_id: te for te in template.exercises}
        keep: list[WorkoutTemplateExercise] = []
        for item in sorted(items, key=lambda i: i["order"]):
            p = item["prescription"]
            te = existing.pop(item["ex_id"], None)
            if te is None:
                te = WorkoutTemplateExercise(exercise_id=item["ex_id"], skipped=False)
            elif te in keep:
                report.warnings.append(f"{item['label']}: exercise listed twice in '{name}'; keeping both")
                te = WorkoutTemplateExercise(exercise_id=item["ex_id"], skipped=False)
            te.exercise = exercises[item["ex_id"]]
            _set_if_changed(te, dict(
                exercise_order=item["order"],
                ramp_sets=item["ramp_sets"],
                target_sets=item["target_sets"],
                target_text=p.text,
                target_rep_min=p.rep_min,
                target_rep_max=p.rep_max,
                target_duration_min=p.duration_min,
                target_duration_max=p.duration_max,
                per_side=p.per_side,
                suggested_weight=item["weight"],
                default_rest_seconds=item["rest"],
                notes=item["row"]["notes"] or None,
            ))
            keep.append(te)
        for removed in existing.values():
            template.exercises.remove(removed)
        template.exercises[:] = keep
        report.template_exercises += len(keep)


# --------------------------------------------------------------------------- entry point


def run_import(
    db: Session,
    *,
    library_path: Path | None,
    plan_path: Path | None,
    media_dir: Path,
    sync_templates: bool = True,
    profile_id: int | None = None,
) -> ImportReport:
    """Import library and/or plan. Commits on success; raises ImportAborted on errors.

    The plan's workouts go to `profile_id` (default: the first profile, the app's owner).
    """
    report = ImportReport()
    equipment = ensure_equipment(db)

    exercises: dict[str, Exercise] = {e.id: e for e in db.scalars(select(Exercise))}
    if library_path is not None:
        if not library_path.exists():
            report.errors.append(f"Library file not found: {library_path}")
        else:
            rows = _read_csv(library_path.read_text(encoding="utf-8-sig"))
            exercises = _import_library(db, rows, equipment, report)
            db.flush()

    if plan_path is not None and not report.errors:
        if not plan_path.exists():
            report.errors.append(f"Plan file not found: {plan_path}")
        else:
            try:
                plan = open_plan(plan_path)
            except (ValueError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
                report.errors.append(str(exc))
            else:
                _import_plan(db, plan, exercises, equipment, media_dir, report,
                             sync_templates=sync_templates,
                             library_loaded=library_path is not None,
                             profile_id=profile_id)

    if report.errors:
        db.rollback()
        raise ImportAborted(report)
    db.commit()
    return report
