from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Equipment,
    Exercise,
    ExerciseSet,
    WorkoutSession,
    WorkoutTemplate,
    WorkoutTemplateExercise,
)
from app.services.importer import ImportAborted, run_import
from app.services.prescription import parse_prescription
from app.services.sessions import start_session
from tests.conftest import PLAN_CSV, PROJECT_DIR, TREY, make_plan_zip


def _count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("8-10", (8, 10, None, None, False)),
        ("10", (10, 10, None, None, False)),
        ("10/side", (10, 10, None, None, True)),
        ("8/leg", (8, 8, None, None, True)),
        ("20-40 sec", (None, None, 20, 40, False)),
        ("35 min", (None, None, 2100, 2100, False)),
        ("30-40 min", (None, None, 1800, 2400, False)),
    ],
)
def test_parse_prescription(text: str, expected: tuple) -> None:
    p = parse_prescription(text)
    assert p is not None
    assert (p.rep_min, p.rep_max, p.duration_min, p.duration_max, p.per_side) == expected


def test_parse_prescription_rejects_garbage() -> None:
    assert parse_prescription("as many as possible") is None
    assert parse_prescription("") is None


def test_imports_exercises(seeded: Session) -> None:
    db = seeded
    assert _count(db, Exercise) == 7

    bench = db.get(Exercise, "EX0001")
    assert bench.name == "Flat dumbbell bench press"
    assert bench.primary_muscle_group == "Chest"
    assert bench.equipment.slug == "dumbbells"
    assert bench.equipment_detail == "Dumbbells + adjustable bench"
    assert bench.load_type == "per_dumbbell"
    assert bench.starting_weight == 20
    assert bench.image_path == "exercise-images/ex0001.png"

    fly = db.get(Exercise, "EX0021")
    assert fly.unilateral is True
    assert fly.load_type == "plates_loaded"
    assert fly.pulley_ratio == "2:1"
    assert fly.attachment == "Single-grip cable handle"

    smith = db.get(Exercise, "EX0139")
    assert smith.load_type == "added_plates"

    plank = db.get(Exercise, "EX0213")
    assert plank.tracking_type == "timed"

    tread = db.get(Exercise, "EX0263")
    assert tread.tracking_type == "cardio"
    assert tread.load_type == "none"

    dip = db.get(Exercise, "EX0300")  # library-only exercise
    assert dip.primary_muscle_group == "Chest"
    assert dip.secondary_muscles == ["Triceps"]
    assert dip.image_path is None
    assert dip.tracking_type == "bodyweight"


def test_imports_templates(seeded: Session) -> None:
    db = seeded
    templates = {t.name: t for t in db.scalars(select(WorkoutTemplate))}
    assert set(templates) == {"Upper A", "Lower A", "Upper B", "Cardio Mobility"}
    upper = templates["Upper A"]
    assert upper.weekday == 0
    assert [te.exercise_id for te in upper.exercises] == ["EX0001", "EX0021"]
    bench = upper.exercises[0]
    assert (bench.ramp_sets, bench.target_sets) == (2, 3)
    assert (bench.target_rep_min, bench.target_rep_max) == (8, 10)
    assert bench.suggested_weight == 20
    assert bench.default_rest_seconds == 120
    fly = upper.exercises[1]
    assert fly.per_side is True
    assert fly.notes == "Handle note."
    plank = templates["Lower A"].exercises[1]
    assert (plank.target_duration_min, plank.target_duration_max) == (20, 40)
    walk = templates["Cardio Mobility"].exercises[0]
    assert (walk.target_duration_min, walk.target_duration_max) == (1800, 2400)


def test_images_copied_and_thumbnailed(seeded: Session, data_dir: Path) -> None:
    images = data_dir / "media" / "exercise-images"
    assert (images / "ex0001.png").is_file()
    assert (images / "thumbs" / "ex0001.webp").is_file()


def test_import_is_idempotent(seeded: Session, library_csv: Path, plan_zip: Path, data_dir: Path) -> None:
    db = seeded
    before = (_count(db, Exercise), _count(db, WorkoutTemplate), _count(db, WorkoutTemplateExercise),
              _count(db, Equipment))
    report = run_import(db, library_path=library_csv, plan_path=plan_zip, media_dir=data_dir / "media")
    after = (_count(db, Exercise), _count(db, WorkoutTemplate), _count(db, WorkoutTemplateExercise),
             _count(db, Equipment))
    assert before == after
    assert report.exercises_created == 0
    assert report.exercises_updated == 0
    assert report.templates_created == 0
    assert report.images_copied == 0


def test_missing_image_is_reported_not_fatal(db: Session, library_csv: Path, tmp_path: Path, data_dir: Path) -> None:
    plan = make_plan_zip(tmp_path / "missing.zip", skip_images={"ex0005.png"})
    report = run_import(db, library_path=library_csv, plan_path=plan, media_dir=data_dir / "media")
    assert any("ex0005.png" in w for w in report.warnings)
    assert db.get(Exercise, "EX0005").image_path is None


def test_invalid_plan_aborts_without_changes(db: Session, library_csv: Path, tmp_path: Path, data_dir: Path) -> None:
    bad = PLAN_CSV.replace("Monday,Upper A,1,EX0001", "Moonday,Upper A,1,EX0001").replace(",8-10,20,", ",8-10,-5,", 1)
    plan = make_plan_zip(tmp_path / "bad.zip", plan_csv=bad)
    with pytest.raises(ImportAborted) as exc:
        run_import(db, library_path=library_csv, plan_path=plan, media_dir=data_dir / "media")
    errors = "\n".join(exc.value.report.errors)
    assert "Moonday" in errors
    assert "negative" in errors
    assert _count(db, Exercise) == 0
    assert _count(db, WorkoutTemplate) == 0


def test_reimport_keeps_history_and_skip_flags(seeded: Session, library_csv: Path, plan_zip: Path, data_dir: Path) -> None:
    db = seeded
    from datetime import date

    template = db.scalar(select(WorkoutTemplate).where(WorkoutTemplate.name == "Upper A"))
    template.exercises[1].skipped = True
    session = start_session(db, TREY, template, date(2026, 10, 19))
    session.exercises[0].sets[0].completed = True
    session.exercises[0].sets[0].repetitions = 9
    db.commit()
    sets_before = _count(db, ExerciseSet)

    run_import(db, library_path=library_csv, plan_path=plan_zip, media_dir=data_dir / "media")

    assert _count(db, WorkoutSession) == 1
    assert _count(db, ExerciseSet) == sets_before
    db.expire_all()
    template = db.scalar(select(WorkoutTemplate).where(WorkoutTemplate.name == "Upper A"))
    assert template.exercises[1].skipped is True


def test_custom_templates_survive_reimport(seeded: Session, library_csv: Path, plan_zip: Path, data_dir: Path) -> None:
    db = seeded
    db.add(WorkoutTemplate(profile_id=TREY, name="My Arms Day", weekday=6))
    db.commit()
    run_import(db, library_path=library_csv, plan_path=plan_zip, media_dir=data_dir / "media")
    custom = db.scalar(select(WorkoutTemplate).where(WorkoutTemplate.name == "My Arms Day"))
    assert custom is not None and custom.weekday == 6


def test_equipment_settings_survive_reimport(seeded: Session, library_csv: Path, plan_zip: Path, data_dir: Path) -> None:
    db = seeded
    dumbbells = db.scalar(select(Equipment).where(Equipment.slug == "dumbbells"))
    dumbbells.available_weights = [5, 12.5, 20]
    db.commit()
    run_import(db, library_path=library_csv, plan_path=plan_zip, media_dir=data_dir / "media")
    db.expire_all()
    assert db.scalar(select(Equipment).where(Equipment.slug == "dumbbells")).available_weights == [5, 12.5, 20]


SEED_LIBRARY = PROJECT_DIR / "seed" / "home_gym_exercises_verified.csv"
SEED_PLAN = PROJECT_DIR / "seed" / "home_gym_workout_with_images.zip"


@pytest.mark.skipif(not (SEED_LIBRARY.exists() and SEED_PLAN.exists()), reason="seed files not present")
def test_real_seed_imports_cleanly(db: Session, data_dir: Path) -> None:
    report = run_import(db, library_path=SEED_LIBRARY, plan_path=SEED_PLAN, media_dir=data_dir / "media")
    assert report.warnings == []
    assert _count(db, Exercise) == 271
    assert report.images_verified == 31
    templates = {t.weekday: t for t in db.scalars(select(WorkoutTemplate))}
    assert sorted(templates) == [0, 1, 2, 3, 4, 5]  # Sunday is a rest day
    assert _count(db, WorkoutTemplateExercise) == 31
    for ex in db.scalars(select(Exercise).where(Exercise.image_path.is_not(None))):
        assert (data_dir / "media" / ex.image_path).is_file()
