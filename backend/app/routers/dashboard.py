from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import schemas
from app.deps import DB, CurrentProfile
from app.models import (
    Exercise,
    SessionStatus,
    WorkoutSession,
    WorkoutSessionExercise,
    WorkoutTemplate,
    WorkoutTemplateExercise,
)
from app.serializers import session_summary, template_choice, template_out
from app.services.plan import WEEKDAYS, get_app_settings, program_week

router = APIRouter(prefix="/api", tags=["dashboard & settings"])

_SESSION_LOAD = selectinload(WorkoutSession.exercises).selectinload(WorkoutSessionExercise.sets)


@router.get("/dashboard", response_model=schemas.Dashboard)
def dashboard(
    db: DB,
    profile: CurrentProfile,
    on_date: Annotated[date | None, Query(alias="date", description="The device's local date")] = None,
) -> schemas.Dashboard:
    today = on_date or date.today()
    settings = get_app_settings(db, profile.id)
    db.commit()
    week = program_week(settings, today)

    templates = db.scalars(
        select(WorkoutTemplate).where(WorkoutTemplate.profile_id == profile.id).options(
            selectinload(WorkoutTemplate.exercises).selectinload(WorkoutTemplateExercise.exercise)
            .selectinload(Exercise.equipment)
        )
    ).all()
    templates = sorted(templates, key=lambda t: (t.weekday is None, t.weekday or 0, t.name))
    todays = next((t for t in templates if t.weekday == today.weekday()), None)

    active = db.scalar(
        select(WorkoutSession).where(
            WorkoutSession.profile_id == profile.id, WorkoutSession.status == SessionStatus.in_progress
        )
        .options(_SESSION_LOAD).order_by(WorkoutSession.started_at.desc())
    )
    last = db.scalar(
        select(WorkoutSession).where(
            WorkoutSession.profile_id == profile.id, WorkoutSession.status == SessionStatus.completed
        )
        .options(_SESSION_LOAD)
        .order_by(WorkoutSession.performed_on.desc(), WorkoutSession.completed_at.desc())
    )
    completed_today = db.scalar(
        select(WorkoutSession).where(
            WorkoutSession.profile_id == profile.id,
            WorkoutSession.status == SessionStatus.completed,
            WorkoutSession.performed_on == today,
        ).options(_SESSION_LOAD).order_by(WorkoutSession.completed_at.desc())
    )

    return schemas.Dashboard(
        date=today,
        weekday=today.weekday(),
        weekday_name=WEEKDAYS[today.weekday()],
        program_week=week,
        today=template_out(todays, week, settings.ramp_weeks) if todays else None,
        active_session=session_summary(active) if active else None,
        last_session=session_summary(last) if last else None,
        completed_today=session_summary(completed_today) if completed_today else None,
        templates=[template_choice(t, week, settings.ramp_weeks) for t in templates],
    )


@router.get("/settings", response_model=schemas.AppSettingsOut)
def get_settings_route(db: DB, profile: CurrentProfile) -> schemas.AppSettingsOut:
    settings = get_app_settings(db, profile.id)
    db.commit()
    return schemas.AppSettingsOut.model_validate(settings)


@router.patch("/settings", response_model=schemas.AppSettingsOut)
def update_settings(body: schemas.AppSettingsUpdate, db: DB, profile: CurrentProfile) -> schemas.AppSettingsOut:
    settings = get_app_settings(db, profile.id)
    changes = body.model_dump(exclude_unset=True)
    clear = changes.pop("clear_program_start_date", False)
    for key, value in changes.items():
        if value is not None:
            setattr(settings, key, value)
    if clear:
        settings.program_start_date = None
    db.commit()
    return schemas.AppSettingsOut.model_validate(settings)
