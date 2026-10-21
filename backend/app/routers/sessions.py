"""Workout sessions and set tracking.

Every set change is saved individually (PATCH), so progress is persisted
continuously and an interrupted session can always be resumed.
"""

from datetime import date

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import schemas
from app.deps import DB, CurrentProfile
from app.models import (
    Exercise,
    ExerciseSet,
    Profile,
    SessionStatus,
    WorkoutSession,
    WorkoutSessionExercise,
    WorkoutTemplate,
    WorkoutTemplateExercise,
    utcnow,
)
from app.serializers import session_exercise_out, session_out, session_summary
from app.services.sessions import add_set, append_exercise, renumber_sets, start_session

router = APIRouter(prefix="/api/workout-sessions", tags=["workout sessions"])

def _load(db: Session, profile: Profile, session_id: int) -> WorkoutSession:
    session = db.scalar(
        select(WorkoutSession)
        .where(WorkoutSession.id == session_id, WorkoutSession.profile_id == profile.id)
        .options(
            selectinload(WorkoutSession.exercises).selectinload(WorkoutSessionExercise.sets),
            selectinload(WorkoutSession.exercises).selectinload(WorkoutSessionExercise.exercise)
            .selectinload(Exercise.equipment),
        )
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workout session not found")
    return session


def _get_se(session: WorkoutSession, se_id: int) -> WorkoutSessionExercise:
    for se in session.exercises:
        if se.id == se_id:
            return se
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Exercise is not part of this session")


def _get_set(session: WorkoutSession, set_id: int) -> tuple[WorkoutSessionExercise, ExerciseSet]:
    for se in session.exercises:
        for s in se.sets:
            if s.id == set_id:
                return se, s
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Set is not part of this session")


def _active(db: Session, profile: Profile) -> WorkoutSession | None:
    return db.scalar(
        select(WorkoutSession)
        .where(WorkoutSession.profile_id == profile.id, WorkoutSession.status == SessionStatus.in_progress)
        .order_by(WorkoutSession.started_at.desc())
    )


def _touch(session: WorkoutSession) -> None:
    session.updated_at = utcnow()


@router.get("/active", response_model=schemas.SessionSummary | None)
def active_session(db: DB, profile: CurrentProfile) -> schemas.SessionSummary | None:
    session = _active(db, profile)
    return session_summary(_load(db, profile, session.id)) if session else None


@router.post("", response_model=schemas.SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(body: schemas.SessionCreate, db: DB, profile: CurrentProfile) -> schemas.SessionOut:
    active = _active(db, profile)
    if active is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"message": f"'{active.name}' is still in progress. Finish or discard it first.",
                    "active_session_id": active.id},
        )
    template = None
    if body.workout_template_id is not None:
        template = db.scalar(
            select(WorkoutTemplate)
            .where(WorkoutTemplate.id == body.workout_template_id, WorkoutTemplate.profile_id == profile.id)
            .options(selectinload(WorkoutTemplate.exercises).selectinload(WorkoutTemplateExercise.exercise))
        )
        if template is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Workout template not found")
    session = start_session(db, profile.id, template, body.performed_on or date.today(), body.name)
    db.commit()
    return session_out(db, _load(db, profile, session.id))


@router.get("/{session_id}", response_model=schemas.SessionOut)
def get_session(session_id: int, db: DB, profile: CurrentProfile) -> schemas.SessionOut:
    return session_out(db, _load(db, profile, session_id))


@router.patch("/{session_id}", response_model=schemas.SessionOut)
def update_session(session_id: int, body: schemas.SessionUpdate, db: DB, profile: CurrentProfile) -> schemas.SessionOut:
    session = _load(db, profile, session_id)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if key in {"name", "performed_on", "started_at"} and value is None:
            continue
        setattr(session, key, value)
    if session.completed_at is not None and session.completed_at < session.started_at:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Finish time cannot be before start time")
    _touch(session)
    db.commit()
    return session_out(db, _load(db, profile, session_id))


@router.post("/{session_id}/complete", response_model=schemas.SessionOut)
def complete_session(session_id: int, body: schemas.SessionComplete, db: DB, profile: CurrentProfile) -> schemas.SessionOut:
    session = _load(db, profile, session_id)
    if session.status == SessionStatus.completed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Workout is already completed")
    session.status = SessionStatus.completed
    session.completed_at = utcnow()
    if body.notes is not None:
        session.notes = body.notes
    db.commit()
    return session_out(db, _load(db, profile, session_id))


@router.post("/{session_id}/resume", response_model=schemas.SessionOut)
def resume_session(session_id: int, db: DB, profile: CurrentProfile) -> schemas.SessionOut:
    """Reopen a completed workout (e.g. finished by mistake)."""
    session = _load(db, profile, session_id)
    if session.status != SessionStatus.completed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Workout is not completed")
    active = _active(db, profile)
    if active is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"'{active.name}' is already in progress")
    session.status = SessionStatus.in_progress
    session.completed_at = None
    db.commit()
    return session_out(db, _load(db, profile, session_id))


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: int, db: DB, profile: CurrentProfile) -> Response:
    db.delete(_load(db, profile, session_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- exercises within a session


@router.post("/{session_id}/exercises", response_model=schemas.SessionExerciseOut, status_code=status.HTTP_201_CREATED)
def add_session_exercise(session_id: int, body: schemas.SessionExerciseAdd, db: DB, profile: CurrentProfile) -> schemas.SessionExerciseOut:
    session = _load(db, profile, session_id)
    exercise = db.get(Exercise, body.exercise_id.upper())
    if exercise is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Exercise {body.exercise_id} not found")
    se = append_exercise(db, session, exercise)
    _touch(session)
    db.commit()
    return session_exercise_out(db, se, session)


@router.patch("/{session_id}/exercises/{se_id}", response_model=schemas.SessionExerciseOut)
def update_session_exercise(
    session_id: int, se_id: int, body: schemas.SessionExerciseUpdate, db: DB, profile: CurrentProfile
) -> schemas.SessionExerciseOut:
    session = _load(db, profile, session_id)
    se = _get_se(session, se_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        if key == "status" and value is None:
            continue
        setattr(se, key, value)
    _touch(session)
    db.commit()
    return session_exercise_out(db, se, session)


@router.delete("/{session_id}/exercises/{se_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_session_exercise(session_id: int, se_id: int, db: DB, profile: CurrentProfile) -> Response:
    session = _load(db, profile, session_id)
    se = _get_se(session, se_id)
    if any(s.completed for s in se.sets):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "This exercise has completed sets. Delete those sets first or mark it skipped.")
    session.exercises.remove(se)
    _touch(session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{session_id}/exercises/{se_id}/apply-weight", response_model=schemas.SessionExerciseOut)
def apply_weight(session_id: int, se_id: int, body: schemas.ApplyWeight, db: DB, profile: CurrentProfile) -> schemas.SessionExerciseOut:
    """Accept a suggested weight: update every not-yet-completed set of the exercise."""
    session = _load(db, profile, session_id)
    se = _get_se(session, se_id)
    for s in se.sets:
        if not s.completed:
            s.weight = body.weight
    _touch(session)
    db.commit()
    return session_exercise_out(db, se, session)


# --------------------------------------------------------------------------- sets


@router.post("/{session_id}/exercises/{se_id}/sets", response_model=list[schemas.SetOut], status_code=status.HTTP_201_CREATED)
def create_set(session_id: int, se_id: int, db: DB, profile: CurrentProfile) -> list[ExerciseSet]:
    session = _load(db, profile, session_id)
    se = _get_se(session, se_id)
    if len(se.sets) >= 60:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Too many sets")
    created = add_set(se)
    _touch(session)
    db.commit()
    return created


@router.patch("/{session_id}/sets/{set_id}", response_model=schemas.SetOut)
def update_set(session_id: int, set_id: int, body: schemas.SetUpdate, db: DB, profile: CurrentProfile) -> ExerciseSet:
    session = _load(db, profile, session_id)
    _, exercise_set = _get_set(session, set_id)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if key == "completed":
            if value is None:
                continue
            if value and not exercise_set.completed:
                exercise_set.completed_at = utcnow()
            elif not value:
                exercise_set.completed_at = None
        setattr(exercise_set, key, value)
    _touch(session)
    db.commit()
    return exercise_set


@router.delete("/{session_id}/sets/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_set(session_id: int, set_id: int, db: DB, profile: CurrentProfile) -> Response:
    """Delete a set. For unilateral exercises the matching other side is removed too."""
    session = _load(db, profile, session_id)
    se, exercise_set = _get_set(session, set_id)
    for s in [s for s in se.sets if s.set_number == exercise_set.set_number]:
        se.sets.remove(s)
    renumber_sets(se)
    _touch(session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
