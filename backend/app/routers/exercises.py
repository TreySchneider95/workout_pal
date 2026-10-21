import hashlib
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import schemas
from app.config import get_settings
from app.deps import DB, CurrentProfile
from app.models import (
    Equipment,
    Exercise,
    Profile,
    SessionStatus,
    WorkoutSession,
    WorkoutSessionExercise,
    WorkoutTemplate,
    WorkoutTemplateExercise,
)
from app.serializers import exercise_out, exercise_volume
from app.services.importer import IMAGE_DIR, ImportReport, store_image

router = APIRouter(prefix="/api/exercises", tags=["exercises"])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def _get_exercise(db: Session, exercise_id: str) -> Exercise:
    exercise = db.get(Exercise, exercise_id.upper())
    if exercise is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Exercise {exercise_id} not found")
    return exercise


def _schedule_map(db: Session, profile: Profile) -> dict[str, list[str]]:
    """Exercise id -> the profile's workouts that include it."""
    rows = db.execute(
        select(WorkoutTemplateExercise.exercise_id, WorkoutTemplate.name)
        .join(WorkoutTemplate)
        .where(WorkoutTemplate.profile_id == profile.id)
        .order_by(WorkoutTemplate.weekday)
    ).all()
    result: dict[str, list[str]] = defaultdict(list)
    for exercise_id, name in rows:
        if name not in result[exercise_id]:
            result[exercise_id].append(name)
    return result


@router.get("", response_model=list[schemas.ExerciseOut])
def list_exercises(
    db: DB,
    profile: CurrentProfile,
    search: str | None = None,
    muscle: str | None = None,
    equipment_id: int | None = None,
    include_disabled: bool = False,
) -> list[schemas.ExerciseOut]:
    stmt = select(Exercise).options(selectinload(Exercise.equipment)).order_by(Exercise.name)
    if search:
        stmt = stmt.where(Exercise.name.ilike(f"%{search.strip()}%"))
    if equipment_id is not None:
        stmt = stmt.where(Exercise.equipment_id == equipment_id)
    if not include_disabled:
        stmt = stmt.where(Exercise.enabled.is_(True))
    exercises = list(db.scalars(stmt))
    if muscle:
        wanted = muscle.lower()
        exercises = [
            e for e in exercises
            if (e.primary_muscle_group or "").lower() == wanted
            or wanted in [m.lower() for m in e.secondary_muscles or []]
        ]
    schedule = _schedule_map(db, profile)
    return [exercise_out(e, schedule.get(e.id)) for e in exercises]


@router.get("/muscle-groups", response_model=list[str])
def muscle_groups(db: DB) -> list[str]:
    groups: set[str] = set()
    for primary, secondary in db.execute(select(Exercise.primary_muscle_group, Exercise.secondary_muscles)):
        if primary:
            groups.add(primary)
        groups.update(secondary or [])
    return sorted(groups)


@router.get("/{exercise_id}", response_model=schemas.ExerciseOut)
def get_exercise(exercise_id: str, db: DB, profile: CurrentProfile) -> schemas.ExerciseOut:
    exercise = _get_exercise(db, exercise_id)
    return exercise_out(exercise, _schedule_map(db, profile).get(exercise.id))


def _next_custom_id(db: Session) -> str:
    ids = db.scalars(select(Exercise.id).where(Exercise.id.like("CX%"))).all()
    numbers = [int(i[2:]) for i in ids if i[2:].isdigit()]
    return f"CX{(max(numbers, default=0) + 1):04d}"


def _check_equipment(db: Session, equipment_id: int | None) -> None:
    if equipment_id is not None and db.get(Equipment, equipment_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Equipment {equipment_id} not found")


@router.post("", response_model=schemas.ExerciseOut, status_code=status.HTTP_201_CREATED)
def create_exercise(body: schemas.ExerciseCreate, db: DB) -> schemas.ExerciseOut:
    _check_equipment(db, body.equipment_id)
    duplicate = db.scalar(select(Exercise).where(func.lower(Exercise.name) == body.name.strip().lower()))
    if duplicate is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"An exercise named '{duplicate.name}' already exists ({duplicate.id})")
    exercise = Exercise(id=_next_custom_id(db), is_custom=True, **body.model_dump())
    exercise.name = exercise.name.strip()
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return exercise_out(exercise)


@router.patch("/{exercise_id}", response_model=schemas.ExerciseOut)
def update_exercise(exercise_id: str, body: schemas.ExerciseUpdate, db: DB, profile: CurrentProfile) -> schemas.ExerciseOut:
    exercise = _get_exercise(db, exercise_id)
    changes = body.model_dump(exclude_unset=True)
    if "equipment_id" in changes:
        _check_equipment(db, changes["equipment_id"])
    for key, value in changes.items():
        setattr(exercise, key, value)
    db.commit()
    db.refresh(exercise)
    return exercise_out(exercise, _schedule_map(db, profile).get(exercise.id))


@router.post("/{exercise_id}/image", response_model=schemas.ExerciseOut)
async def upload_image(exercise_id: str, file: UploadFile, db: DB, profile: CurrentProfile) -> schemas.ExerciseOut:
    exercise = _get_exercise(db, exercise_id)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Image is larger than 15 MB")
    suffix = (file.filename or "").rsplit(".", 1)[-1].lower()
    if suffix not in {"png", "jpg", "jpeg", "webp", "gif"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Upload a PNG, JPEG, WebP or GIF image")
    filename = f"{exercise.id.lower()}-{hashlib.sha256(data).hexdigest()[:8]}.{suffix}"
    report = ImportReport()
    if not store_image(data, filename, get_settings().media_dir, report):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "File is not a valid image")
    exercise.image_key = filename
    exercise.image_path = f"{IMAGE_DIR}/{filename}"
    db.commit()
    return exercise_out(exercise, _schedule_map(db, profile).get(exercise.id))


@router.get("/{exercise_id}/progress", response_model=schemas.ExerciseProgress)
def exercise_progress(exercise_id: str, db: DB, profile: CurrentProfile) -> schemas.ExerciseProgress:
    exercise = _get_exercise(db, exercise_id)
    rows = db.scalars(
        select(WorkoutSessionExercise)
        .join(WorkoutSession)
        .where(
            WorkoutSessionExercise.exercise_id == exercise.id,
            WorkoutSession.profile_id == profile.id,
            WorkoutSession.status == SessionStatus.completed,
        )
        .options(selectinload(WorkoutSessionExercise.sets), selectinload(WorkoutSessionExercise.session))
        .order_by(WorkoutSession.performed_on, WorkoutSession.started_at)
    ).all()

    points: list[schemas.ExerciseProgressPoint] = []
    history: list[schemas.ExerciseHistoryEntry] = []
    best_weight: float | None = None
    best_reps: int | None = None
    best_date = None
    total_volume = 0.0
    total_reps = 0
    for se in rows:
        done = [s for s in se.sets if s.completed]
        if not done:
            continue
        weights = [s.weight for s in done if s.weight is not None]
        top = max(weights) if weights else None
        reps = [s.repetitions for s in done if s.repetitions is not None]
        reps_at_top = [s.repetitions or 0 for s in done if top is not None and s.weight == top]
        volume = exercise_volume(se)
        durations = [s.duration_seconds for s in done if s.duration_seconds]
        distances = [s.distance for s in done if s.distance]
        points.append(schemas.ExerciseProgressPoint(
            performed_on=se.session.performed_on,
            session_id=se.session.id,
            top_weight=top,
            best_reps=max(reps) if reps else None,
            total_reps=sum(reps),
            volume=volume,
            total_duration=sum(durations) if durations else None,
            total_distance=round(sum(distances), 2) if distances else None,
        ))
        history.append(schemas.ExerciseHistoryEntry(
            session_id=se.session.id,
            session_name=se.session.name,
            performed_on=se.session.performed_on,
            load_type=se.load_type,
            pulley_ratio=se.pulley_ratio,
            sets=[schemas.SetOut.model_validate(s) for s in se.sets if s.completed],
            top_weight=top,
            total_reps=sum(reps),
            volume=volume,
        ))
        total_volume += volume
        total_reps += sum(reps)
        if top is not None and (best_weight is None or top > best_weight):
            best_weight, best_reps, best_date = top, max(reps_at_top) if reps_at_top else None, se.session.performed_on

    history.reverse()
    return schemas.ExerciseProgress(
        exercise_id=exercise.id,
        sessions=len(points),
        best_weight=best_weight,
        best_weight_reps=best_reps,
        best_weight_date=best_date,
        total_volume=total_volume,
        total_reps=total_reps,
        points=points,
        history=history,
    )
