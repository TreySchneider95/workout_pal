"""Helpers for the weekly plan: program weeks, planned set counts and duration estimates."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSettings, TrackingType, WorkoutTemplate, WorkoutTemplateExercise

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Rough time per working set (seconds) used for the duration estimate.
_WORK_SECONDS = 45
_TRANSITION_SECONDS = 60


def get_app_settings(db: Session, profile_id: int) -> AppSettings:
    settings = db.scalar(select(AppSettings).where(AppSettings.profile_id == profile_id))
    if settings is None:
        settings = AppSettings(profile_id=profile_id)
        db.add(settings)
        db.flush()
    return settings


def program_week(settings: AppSettings, on_date: date) -> int | None:
    if settings.program_start_date is None:
        return None
    days = (on_date - settings.program_start_date).days
    return max(1, days // 7 + 1)


def planned_sets(te: WorkoutTemplateExercise, week: int | None, ramp_weeks: int) -> int:
    """Set count for a given program week; weeks 1..ramp_weeks use the ramp-in count."""
    in_ramp = week is None or week <= ramp_weeks
    if in_ramp and te.ramp_sets:
        return te.ramp_sets
    return te.target_sets


def estimate_minutes(template: WorkoutTemplate, week: int | None, ramp_weeks: int) -> int:
    if template.estimated_duration_minutes:
        return template.estimated_duration_minutes
    total = 0.0
    for te in template.exercises:
        if te.skipped:
            continue
        sets = planned_sets(te, week, ramp_weeks)
        tracking = te.exercise.tracking_type
        if te.target_duration_min is not None:
            work = (te.target_duration_min + (te.target_duration_max or te.target_duration_min)) / 2
        else:
            work = _WORK_SECONDS
        if tracking == TrackingType.cardio:
            total += work * sets + _TRANSITION_SECONDS
            continue
        sides = 2 if (te.per_side or te.exercise.unilateral) else 1
        total += sets * (work * sides + te.default_rest_seconds) + _TRANSITION_SECONDS
    return max(5, int(round(total / 60 / 5.0)) * 5)
