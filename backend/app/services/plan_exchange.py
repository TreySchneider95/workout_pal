"""Plan documents: hand a profile's plan to an AI and take its edited version back.

The flow:

1. ``build_prompt`` writes a prompt with the person's request, their current plan
   (already in the plan-document format), recent performance, their equipment and
   the whole exercise library, plus the rules for the document to send back.
2. The person pastes the AI's reply. ``read_document`` finds the JSON in it,
   ``validate_document`` checks it against the library, and ``diff_plans`` shows
   what would change.
3. ``apply_plan`` replaces the profile's plan with the document and records a
   ``PlanRevision`` so the change can be undone (undo applies the previous plan).

A plan document is the complete plan: workouts left out of it are removed.
Recorded sessions are never touched; they hold their own snapshots.
"""

import difflib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Equipment,
    Exercise,
    LoadType,
    PlanRevision,
    Profile,
    SessionStatus,
    TrackingType,
    WorkoutSession,
    WorkoutTemplate,
    WorkoutTemplateExercise,
    utcnow,
)
from app.services import progression
from app.services.plan import WEEKDAYS, get_app_settings, program_week
from app.services.prescription import Prescription, format_prescription, parse_prescription
from app.serializers import summarize_sets
from app.services.sessions import default_targets

FORMAT = "workout-pal-plan/v1"

LOAD_TYPE_TEXT = {
    LoadType.per_dumbbell: "lb per dumbbell (two dumbbells)",
    LoadType.single_dumbbell: "lb, one dumbbell",
    LoadType.plates_loaded: "lb of plates on the cable stack",
    LoadType.added_plates: "lb of plates added to the Smith bar (bar not included)",
    LoadType.bodyweight: "bodyweight (weight = optional added lb, usually 0)",
    LoadType.none: "no weight (use null)",
}


# --------------------------------------------------------------------------- document schema


class DocExercise(BaseModel):
    model_config = ConfigDict(extra="ignore")

    exercise_id: str = Field(min_length=1, max_length=20)
    exercise_name: str | None = Field(None, max_length=200)
    sets: int = Field(ge=1, le=20)
    sets_first_weeks: int | None = Field(None, ge=1, le=20)
    reps_or_duration: str = Field(min_length=1, max_length=50)
    weight: float | None = Field(None, ge=0, le=1000)
    rest_seconds: int | None = Field(None, ge=0, le=900)
    notes: str | None = Field(None, max_length=1000)
    skipped: bool = False


class DocWorkout(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=100)
    day: str | None = Field(None, max_length=20)
    notes: str | None = Field(None, max_length=2000)
    exercises: list[DocExercise] = Field(default_factory=list, max_length=40)


class PlanDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    format: str | None = None
    summary: str | None = Field(None, max_length=4000)
    workouts: list[DocWorkout] = Field(max_length=14)


# --------------------------------------------------------------------------- export


def _load_templates(db: Session, profile_id: int) -> list[WorkoutTemplate]:
    templates = db.scalars(
        select(WorkoutTemplate)
        .where(WorkoutTemplate.profile_id == profile_id)
        .options(selectinload(WorkoutTemplate.exercises).selectinload(WorkoutTemplateExercise.exercise)
                 .selectinload(Exercise.equipment))
    ).all()
    return sorted(templates, key=lambda t: (t.weekday is None, t.weekday or 0, t.name))


def _te_reps(te: WorkoutTemplateExercise) -> str:
    return (
        format_prescription(te.target_rep_min, te.target_rep_max, te.target_duration_min,
                            te.target_duration_max, te.per_side)
        or te.target_text
        or "10"
    )


def export_plan(db: Session, profile_id: int) -> dict:
    """The profile's current plan as a plan document."""
    workouts = []
    for t in _load_templates(db, profile_id):
        workouts.append({
            "name": t.name,
            "day": WEEKDAYS[t.weekday] if t.weekday is not None else None,
            "notes": t.notes,
            "exercises": [
                {
                    "exercise_id": te.exercise_id,
                    "exercise_name": te.exercise.name,
                    "sets": te.target_sets,
                    "sets_first_weeks": te.ramp_sets,
                    "reps_or_duration": _te_reps(te),
                    "weight": te.suggested_weight if te.exercise.load_type != LoadType.none else None,
                    "rest_seconds": te.default_rest_seconds,
                    "notes": te.notes,
                    "skipped": te.skipped,
                }
                for te in t.exercises
            ],
        })
    return {"format": FORMAT, "summary": None, "workouts": workouts}


# --------------------------------------------------------------------------- prompt


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:g}"


def _equipment_lines(db: Session) -> list[str]:
    lines = []
    for eq in db.scalars(select(Equipment).order_by(Equipment.name)):
        if eq.equipment_type == "dumbbell":
            weights = ", ".join(_fmt(w) for w in progression.weight_options(eq) or [])
            lines.append(f"- {eq.name}: pairs of {weights} lb (only these weights exist)")
        elif eq.equipment_type in ("cable", "smith_machine"):
            lines.append(f"- {eq.name}: plates in {_fmt(eq.weight_increment or 5)} lb steps")
        else:
            lines.append(f"- {eq.name}")
    return lines


def _library_lines(db: Session) -> list[str]:
    exercises = db.scalars(
        select(Exercise).where(Exercise.enabled.is_(True))
        .options(selectinload(Exercise.equipment))
        .order_by(Exercise.primary_muscle_group, Exercise.name)
    ).all()
    lines: list[str] = []
    group = object()
    for ex in exercises:
        if ex.primary_muscle_group != group:
            group = ex.primary_muscle_group
            lines.append(f"\n## {group or 'Other'}")
        flags = []
        if ex.tracking_type == TrackingType.cardio:
            flags.append("cardio: minutes")
        elif ex.tracking_type == TrackingType.timed:
            flags.append("timed: seconds")
        if ex.unilateral:
            flags.append("each side")
        if ex.pulley_ratio:
            flags.append(f"{ex.pulley_ratio} pulley")
        equipment = ex.equipment_detail or (ex.equipment.name if ex.equipment else "")
        weight = LOAD_TYPE_TEXT.get(ex.load_type, ex.load_type)
        tail = f" [{', '.join(flags)}]" if flags else ""
        lines.append(f"{ex.id} | {ex.name} | {equipment} | {weight}{tail}")
    return lines


def _recent_lines(db: Session, profile_id: int, exercise_ids: list[str]) -> list[str]:
    lines = []
    for ex_id in dict.fromkeys(exercise_ids):
        last = progression.previous_performance(db, ex_id, profile_id)
        if last is None:
            continue
        done = [s for s in last.sets if s.completed]
        lines.append(
            f"- {ex_id} {last.exercise_name}: {last.session.performed_on.isoformat()} "
            f"{summarize_sets(done, last.tracking_type, last.load_type)} (target {last.target_text or '-'})"
        )
    return lines


def build_prompt(db: Session, profile: Profile, request: str, today: date | None = None) -> str:
    today = today or date.today()
    settings = get_app_settings(db, profile.id)
    week = program_week(settings, today)
    plan = export_plan(db, profile.id)
    plan_ids = [e["exercise_id"] for w in plan["workouts"] for e in w["exercises"]]
    recent_count = db.scalar(
        select(func.count()).select_from(WorkoutSession).where(
            WorkoutSession.profile_id == profile.id,
            WorkoutSession.status == SessionStatus.completed,
            WorkoutSession.performed_on >= today - timedelta(weeks=4),
        )
    ) or 0
    recent = _recent_lines(db, profile.id, plan_ids)

    if plan["workouts"]:
        plan_intro = "Their current plan, in the exact format you will send back:"
    else:
        plan_intro = ("They have no plan yet, so build one from scratch. "
                      "This is the (empty) document you will fill in:")
    example = json.dumps({
        "format": FORMAT,
        "summary": "Added a core finisher to Upper A and moved Lower B to Saturday.",
        "workouts": [{
            "name": "Upper A",
            "day": "Monday",
            "notes": None,
            "exercises": [{
                "exercise_id": "EX0001",
                "exercise_name": "Flat dumbbell bench press",
                "sets": 3,
                "sets_first_weeks": 2,
                "reps_or_duration": "8-10",
                "weight": 25,
                "rest_seconds": 120,
                "notes": "Pause 1 second at the bottom.",
            }],
        }],
    }, indent=2)

    sections = [
        f"""You are a knowledgeable, safety-minded strength coach helping {profile.name} change their
home-gym workout plan. They are not an expert, so explain your choices in plain language.
Their app (Workout Pal) will import the plan document you produce.

# What {profile.name} wants changed

\"\"\"
{request.strip()}
\"\"\"

# How to work

1. If the request is unclear, or mentions pain or injury, ask your questions first and wait for
   the answers. (Pain that is sharp or lasting is a reason to see a professional; say so.)
2. When you are ready, briefly explain what you changed and why, then give the complete new
   plan as ONE ```json code block in the format described at the end.
3. Keep everything they didn't ask to change exactly as it is.

# About {profile.name}

- Program week: {week if week is not None else "not started yet"} (the first {settings.ramp_weeks} weeks use the lighter "sets_first_weeks" count)
- Workouts completed in the last 4 weeks: {recent_count}
- All weights are in pounds (lb).

# Equipment in the gym

""" + "\n".join(_equipment_lines(db)),
        f"""# Current plan

{plan_intro}

```json
{json.dumps(plan, indent=2)}
```""",
    ]
    if recent:
        sections.append("# Most recent performance of the exercises in the plan\n\n"
                        "Use this to choose realistic weights.\n\n" + "\n".join(recent))
    sections.append(
        "# Exercise library\n\n"
        "These are the ONLY exercises available. Use their exact IDs.\n"
        "Columns: ID | name | equipment | how the weight is measured [notes]"
        + "\n".join(_library_lines(db))
    )
    sections.append(f"""# The plan document to send back

Reply with one ```json code block containing the COMPLETE plan: every workout, including the
ones you didn't change. Any workout left out is deleted from the app. Example:

```json
{example}
```

Rules:
- "format": always "{FORMAT}".
- "summary": one or two plain sentences describing the change (shown in the app's history).
- "workouts": at most 7 scheduled workouts. "name" must be unique. "day" is Monday to Sunday,
  or null for a workout that isn't scheduled. Only one workout per day.
- "exercise_id" must come from the exercise library above. Also give "exercise_name" so
  mistakes can be caught. Exercises are done in the order listed.
- "sets": working sets from week {settings.ramp_weeks + 1} on (1-20). "sets_first_weeks": sets for the first
  {settings.ramp_weeks} program weeks, or null to use "sets".
- "reps_or_duration": reps like "8-10" or "12", per side like "10/side", holds like "30-45 sec",
  cardio like "20-30 min". Exercises marked "cardio: minutes" need minutes and those marked
  "timed: seconds" need seconds.
- "weight": the starting weight in the exercise's convention from the library (for example lb
  PER dumbbell, or lb of plates on a cable stack). Dumbbell weights must be ones that exist.
  Use null for cardio. Bodyweight exercises use 0 unless extra weight is added.
- "rest_seconds": rest between sets (0-900).
- "notes": optional short coaching cue, or null.
- "skipped": true keeps an exercise in the plan but leaves it out of workouts for now
  (keep existing values; use false for anything new).""")
    return "\n\n".join(sections) + "\n"


# --------------------------------------------------------------------------- reading the AI's answer


class DocumentError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _loads(text: str) -> object:
    # Chat apps sometimes "smarten" quotes; JSON needs straight ones.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(text.replace("“", '"').replace("”", '"'))


def read_document(text: str) -> PlanDocument:
    """Find and parse the plan JSON in a pasted reply (code fences and chatter allowed)."""
    # Last fenced block first (a reply may quote the old plan before the new one),
    # then everything between the first "{" and the last "}".
    candidates = [m.group(1) for m in _FENCE.finditer(text)][::-1]
    if "{" in text and "}" in text:
        candidates.append(text[text.index("{"): text.rindex("}") + 1])
    data = None
    syntax_error = None
    for candidate in candidates:
        try:
            data = _loads(candidate)
            break
        except json.JSONDecodeError as exc:
            syntax_error = exc
    if data is None:
        if "{" in text and syntax_error is None:
            raise DocumentError(["The JSON looks cut off (it never closes). "
                                 "Ask the AI to resend the complete JSON block."])
        if syntax_error is not None:
            raise DocumentError([f"The JSON is malformed (line {syntax_error.lineno}: {syntax_error.msg}). "
                                 "Ask the AI to resend the complete JSON block."])
        raise DocumentError(["Couldn't find a JSON plan in what you pasted. "
                             "Paste the AI's whole reply, including the ```json block."])
    if not isinstance(data, dict):
        raise DocumentError(["The JSON should be an object with a \"workouts\" list."])
    try:
        return PlanDocument.model_validate(data)
    except ValidationError as exc:
        raise DocumentError([_describe_error(err, data) for err in exc.errors()]) from exc


def _describe_error(err: dict, data: dict) -> str:
    """Turn a pydantic error location into words, using workout and exercise names."""
    parts: list[str] = []
    node: object = data
    loc = list(err["loc"])
    i = 0
    while i < len(loc):
        key = loc[i]
        if key == "workouts" and i + 1 < len(loc) and isinstance(loc[i + 1], int):
            idx = loc[i + 1]
            workout = node["workouts"][idx] if isinstance(node, dict) else {}
            name = workout.get("name") if isinstance(workout, dict) else None
            parts.append(f"workout '{name}'" if name else f"workout #{idx + 1}")
            node, i = workout, i + 2
        elif key == "exercises" and i + 1 < len(loc) and isinstance(loc[i + 1], int):
            idx = loc[i + 1]
            ex = node["exercises"][idx] if isinstance(node, dict) else {}
            label = (ex.get("exercise_name") or ex.get("exercise_id")) if isinstance(ex, dict) else None
            parts.append(f"exercise #{idx + 1}" + (f" ({label})" if label else ""))
            node, i = ex, i + 2
        else:
            parts.append(str(key))
            node = node.get(key) if isinstance(node, dict) else None
            i += 1
    where = " › ".join(parts) or "document"
    return f"{where}: {err['msg']}"


# --------------------------------------------------------------------------- validation


@dataclass
class PlanItem:
    exercise: Exercise
    sets: int
    sets_first_weeks: int | None
    prescription: Prescription
    weight: float | None
    rest_seconds: int
    notes: str | None
    skipped: bool = False


@dataclass
class PlanWorkout:
    name: str
    weekday: int | None
    notes: str | None
    items: list[PlanItem]


@dataclass
class ValidatedPlan:
    summary: str | None
    workouts: list[PlanWorkout] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


_DAY_ALIASES = {d.lower(): i for i, d in enumerate(WEEKDAYS)} | {d[:3].lower(): i for i, d in enumerate(WEEKDAYS)}
_UNSCHEDULED = {"", "none", "null", "unscheduled", "any", "flexible"}
_SAME_NAME = 0.6


def _clean(text: str | None) -> str | None:
    text = (text or "").strip()
    return text or None


def validate_document(db: Session, doc: PlanDocument) -> ValidatedPlan:
    plan = ValidatedPlan(summary=_clean(doc.summary))
    if doc.format and doc.format != FORMAT:
        plan.warnings.append(f"Unexpected format '{doc.format}'; reading it as {FORMAT}")
    if not doc.workouts:
        plan.errors.append("The plan has no workouts; applying it would delete the whole plan.")
        return plan

    library = {e.id: e for e in db.scalars(select(Exercise).options(selectinload(Exercise.equipment)))}
    names: dict[str, str] = {}
    days: dict[int, str] = {}
    for w in doc.workouts:
        name = w.name.strip()
        label = f"'{name}'"
        if name.lower() in names:
            plan.errors.append(f"Two workouts are named {label}; names must be unique.")
        names[name.lower()] = name

        weekday = None
        day = (w.day or "").strip().lower()
        if day not in _UNSCHEDULED:
            weekday = _DAY_ALIASES.get(day)
            if weekday is None:
                plan.errors.append(f"{label}: unknown day '{w.day}' (use Monday to Sunday, or null).")
            elif weekday in days:
                plan.errors.append(f"{WEEKDAYS[weekday]} has two workouts: '{days[weekday]}' and {label}.")
            else:
                days[weekday] = name

        if not w.exercises:
            plan.warnings.append(f"{label} has no exercises.")
        seen: set[str] = set()
        items: list[PlanItem] = []
        for n, e in enumerate(w.exercises, start=1):
            ex_id = e.exercise_id.strip().upper()
            where = f"{label} exercise #{n} ({e.exercise_name or ex_id})"
            exercise = library.get(ex_id)
            if exercise is None:
                plan.errors.append(f"{where}: {ex_id} isn't in the exercise library.")
                continue
            if not exercise.enabled:
                plan.errors.append(f"{where}: {exercise.name} is marked unavailable in the library.")
                continue
            if e.exercise_name and difflib.SequenceMatcher(
                None, e.exercise_name.lower(), exercise.name.lower()
            ).ratio() < _SAME_NAME:
                plan.warnings.append(
                    f"{where}: {ex_id} is '{exercise.name}' in the library, not '{e.exercise_name}'. "
                    "Check the AI picked the exercise it meant."
                )
            if ex_id in seen:
                plan.warnings.append(f"{label}: {exercise.name} is listed more than once.")
            seen.add(ex_id)

            p = parse_prescription(e.reps_or_duration)
            if p is None:
                plan.errors.append(f"{where}: can't read reps_or_duration '{e.reps_or_duration}' "
                                   "(use e.g. \"8-10\", \"10/side\", \"30-45 sec\", \"20-30 min\").")
                continue
            if exercise.tracking_type == TrackingType.cardio and not p.is_duration:
                plan.errors.append(f"{where}: cardio needs a duration like \"20-30 min\", not '{p.text}'.")
                continue
            if exercise.tracking_type == TrackingType.timed and not p.is_duration:
                plan.warnings.append(f"{where}: {exercise.name} is usually timed; '{p.text}' will be tracked as reps.")

            weight = _check_weight(exercise, e.weight, where, plan.warnings)
            rest = e.rest_seconds if e.rest_seconds is not None else default_targets(exercise).rest_seconds
            items.append(PlanItem(exercise, e.sets, e.sets_first_weeks, p, weight, rest, _clean(e.notes), e.skipped))
        plan.workouts.append(PlanWorkout(name, weekday, _clean(w.notes), items))
    return plan


def _check_weight(exercise: Exercise, weight: float | None, where: str, warnings: list[str]) -> float | None:
    if exercise.load_type == LoadType.none:
        return None
    if exercise.load_type not in progression.WEIGHTED:
        return weight
    if weight is None:
        warnings.append(f"{where}: no starting weight; you'll pick one during the first workout.")
        return None
    options = progression.weight_options(exercise.equipment)
    if options and weight not in options:
        nearest = min(options, key=lambda w: (abs(w - weight), w))
        warnings.append(f"{where}: there are no {weight:g} lb dumbbells; using {nearest:g} lb.")
        return nearest
    return weight


# --------------------------------------------------------------------------- preview


def plan_to_document(plan: ValidatedPlan) -> dict:
    return {
        "format": FORMAT,
        "summary": plan.summary,
        "workouts": [
            {
                "name": w.name,
                "day": WEEKDAYS[w.weekday] if w.weekday is not None else None,
                "notes": w.notes,
                "exercises": [
                    {
                        "exercise_id": i.exercise.id,
                        "exercise_name": i.exercise.name,
                        "sets": i.sets,
                        "sets_first_weeks": i.sets_first_weeks,
                        "reps_or_duration": i.prescription.text,
                        "weight": i.weight,
                        "rest_seconds": i.rest_seconds,
                        "notes": i.notes,
                        "skipped": i.skipped,
                    }
                    for i in w.items
                ],
            }
            for w in plan.workouts
        ],
    }


def _targets(text: str) -> tuple | None:
    p = parse_prescription(text)
    return (p.rep_min, p.rep_max, p.duration_min, p.duration_max, p.per_side) if p else None


def _exercise_changes(old: dict, new: dict) -> list[str]:
    changes = []
    if old.get("skipped", False) != new.get("skipped", False):
        changes.append("now skipped" if new.get("skipped") else "no longer skipped")
    if old["sets"] != new["sets"]:
        changes.append(f"sets {old['sets']} → {new['sets']}")
    if (old["sets_first_weeks"] or old["sets"]) != (new["sets_first_weeks"] or new["sets"]):
        changes.append(f"first-weeks sets {old['sets_first_weeks'] or old['sets']} → "
                       f"{new['sets_first_weeks'] or new['sets']}")
    if _targets(old["reps_or_duration"]) != _targets(new["reps_or_duration"]):
        changes.append(f"{old['reps_or_duration']} → {new['reps_or_duration']}")
    if old["weight"] != new["weight"]:
        changes.append(f"weight {_fmt(old['weight'])} → {_fmt(new['weight'])} lb")
    if old["rest_seconds"] != new["rest_seconds"]:
        changes.append(f"rest {old['rest_seconds']}s → {new['rest_seconds']}s")
    if (old["notes"] or None) != (new["notes"] or None):
        changes.append("notes changed")
    return changes


def diff_plans(current: dict, proposed: dict) -> list[dict]:
    """Workout-by-workout changes from `current` to `proposed` (both plan documents)."""
    before = {w["name"].lower(): w for w in current["workouts"]}
    result = []
    for w in proposed["workouts"]:
        old = before.pop(w["name"].lower(), None)
        entry = {"name": w["name"], "day": w["day"], "previous_day": old["day"] if old else None,
                 "status": "added" if old is None else "unchanged", "notes": [], "exercises": []}
        old_items: dict[str, list[dict]] = defaultdict(list)
        for e in (old["exercises"] if old else []):
            old_items[e["exercise_id"]].append(e)
        matched_order = []
        for e in w["exercises"]:
            prev = old_items[e["exercise_id"]].pop(0) if old_items[e["exercise_id"]] else None
            if prev is None:
                status, changes = "added", []
            else:
                matched_order.append(e["exercise_id"])
                changes = _exercise_changes(prev, e)
                status = "changed" if changes else "unchanged"
            entry["exercises"].append({"exercise_id": e["exercise_id"], "exercise_name": e["exercise_name"],
                                       "status": status, "changes": changes,
                                       "sets": e["sets"], "reps_or_duration": e["reps_or_duration"],
                                       "weight": e["weight"]})
        for leftovers in old_items.values():
            for e in leftovers:
                entry["exercises"].append({"exercise_id": e["exercise_id"], "exercise_name": e["exercise_name"],
                                           "status": "removed", "changes": [], "sets": e["sets"],
                                           "reps_or_duration": e["reps_or_duration"], "weight": e["weight"]})
        if old is not None:
            if old["day"] != w["day"]:
                entry["notes"].append(f"Moved from {old['day'] or 'unscheduled'} to {w['day'] or 'unscheduled'}")
            old_order = [e["exercise_id"] for e in old["exercises"] if e["exercise_id"] in matched_order]
            if old_order != matched_order:
                entry["notes"].append("Exercises reordered")
            if (old["notes"] or None) != (w["notes"] or None):
                entry["notes"].append("Workout notes changed")
            if entry["notes"] or any(e["status"] != "unchanged" for e in entry["exercises"]):
                entry["status"] = "changed"
        result.append(entry)
    for old in before.values():
        result.append({"name": old["name"], "day": None, "previous_day": old["day"], "status": "removed",
                       "notes": [], "exercises": [
                           {"exercise_id": e["exercise_id"], "exercise_name": e["exercise_name"],
                            "status": "removed", "changes": [], "sets": e["sets"],
                            "reps_or_duration": e["reps_or_duration"], "weight": e["weight"]}
                           for e in old["exercises"]]})
    return result


# --------------------------------------------------------------------------- applying


def apply_plan(db: Session, profile_id: int, plan: ValidatedPlan, *, source: str = "document") -> PlanRevision:
    """Replace the profile's plan with `plan` (already validated) and record a revision. Commits."""
    assert plan.ok
    previous = export_plan(db, profile_id)
    templates = _load_templates(db, profile_id)
    existing = {t.name.lower(): t for t in templates}

    # Clear the schedule first so workouts can trade days without tripping the unique constraint.
    for t in templates:
        t.weekday = None
    db.flush()

    wanted = {w.name.lower() for w in plan.workouts}
    for t in templates:
        if t.name.lower() not in wanted:
            db.delete(t)  # recorded sessions keep their data; their template link becomes empty
    db.flush()

    now = utcnow()
    for w in plan.workouts:
        template = existing.get(w.name.lower())
        if template is None:
            template = WorkoutTemplate(profile_id=profile_id, name=w.name)
            db.add(template)
        template.name = w.name
        template.notes = w.notes
        template.weekday = w.weekday

        reusable: dict[str, list[WorkoutTemplateExercise]] = defaultdict(list)
        for te in template.exercises:
            reusable[te.exercise_id].append(te)
        rows = []
        for order, item in enumerate(w.items, start=1):
            te = reusable[item.exercise.id].pop(0) if reusable[item.exercise.id] else None
            if te is None:
                te = WorkoutTemplateExercise(exercise=item.exercise)
                # A weight chosen for the plan beats older history, like a hand edit.
                te.suggested_weight_updated_at = now if item.weight is not None else None
            elif te.suggested_weight != item.weight:
                te.suggested_weight_updated_at = now
            p = item.prescription
            te.exercise_order = order
            te.target_sets = item.sets
            te.ramp_sets = item.sets_first_weeks
            te.target_text = p.text
            te.target_rep_min, te.target_rep_max = p.rep_min, p.rep_max
            te.target_duration_min, te.target_duration_max = p.duration_min, p.duration_max
            te.per_side = p.per_side or item.exercise.unilateral
            te.suggested_weight = item.weight
            te.default_rest_seconds = item.rest_seconds
            te.notes = item.notes
            te.skipped = item.skipped
            rows.append(te)
        template.exercises[:] = rows
        if template.id is not None and template.estimated_duration_minutes:
            template.estimated_duration_minutes = None  # a stale manual estimate would mislead
    db.flush()

    revision = PlanRevision(profile_id=profile_id, source=source, summary=plan.summary,
                            previous_plan=previous, new_plan=plan_to_document(plan))
    db.add(revision)
    db.commit()
    return revision


def latest_revision(db: Session, profile_id: int) -> PlanRevision | None:
    return db.scalar(
        select(PlanRevision).where(PlanRevision.profile_id == profile_id)
        .order_by(PlanRevision.created_at.desc(), PlanRevision.id.desc())
    )


def undo_revision(db: Session, revision: PlanRevision) -> PlanRevision:
    """Put back the plan from before `revision` (which must be the latest). Raises DocumentError."""
    plan = validate_document(db, PlanDocument.model_validate(revision.previous_plan))
    if not revision.previous_plan["workouts"]:
        # Undoing the very first plan: an empty plan is legitimate here.
        plan.errors = [e for e in plan.errors if "no workouts" not in e]
    if not plan.ok:
        raise DocumentError(plan.errors)
    plan.summary = f"Undid: {revision.summary}" if revision.summary else "Undid the previous change"
    revision.undone_at = utcnow()
    return apply_plan(db, revision.profile_id, plan, source="undo")
