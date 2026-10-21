from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app import schemas
from app.deps import DB, CurrentProfile
from app.models import SessionStatus, WorkoutSession, WorkoutSessionExercise
from app.serializers import session_summary

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=schemas.HistoryPage)
def list_history(
    db: DB,
    profile: CurrentProfile,
    limit: Annotated[int, Query(ge=1, le=200)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
    template_id: int | None = None,
    exercise_id: str | None = None,
) -> schemas.HistoryPage:
    """Completed workouts, newest first."""
    stmt = select(WorkoutSession).where(
        WorkoutSession.profile_id == profile.id, WorkoutSession.status == SessionStatus.completed
    )
    if template_id is not None:
        stmt = stmt.where(WorkoutSession.workout_template_id == template_id)
    if exercise_id:
        stmt = stmt.where(WorkoutSession.exercises.any(WorkoutSessionExercise.exercise_id == exercise_id.upper()))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    sessions = db.scalars(
        stmt.options(selectinload(WorkoutSession.exercises).selectinload(WorkoutSessionExercise.sets))
        .order_by(WorkoutSession.performed_on.desc(), WorkoutSession.started_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return schemas.HistoryPage(total=total, items=[session_summary(s) for s in sessions])
