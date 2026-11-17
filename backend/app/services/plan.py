"""Helpers for the plan: program weeks, plan weeks, planned set counts and duration estimates.

A plan repeats every ``plan_weeks`` weeks (1 = the same workouts every week). Each workout
runs in the plan weeks listed in ``WorkoutTemplate.weeks`` (``None`` = every week), so a
6-week program can do different workouts, sets or reps from one week to the next.
Program weeks run Monday to Sunday; week 1 is the week containing the program start date.
"""

from collections.abc import Iterable
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSettings, TrackingType, WorkoutTemplate, WorkoutTemplateExercise

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MAX_PLAN_WEEKS = 12

# Rough time per working set (seconds) used for the duration estimate.
_WORK_SECONDS = 45
_TRANSITION_SECONDS = 60


def get_app_settings(db: Session, profile_id: int) -> AppSettings:
    settings = db.scalar(select(AppSettings).where(AppSettings.profile_id == profile_id))
    if settings is None:
        settings = AppSettings(profile_id=profile_id, plan_weeks=1)
        db.add(settings)
        db.flush()
    return settings


def week_start(day: date) -> date:
    """The Monday of `day`'s week."""
    return day - timedelta(days=day.weekday())


def program_week(settings: AppSettings, on_date: date) -> int | None:
    if settings.program_start_date is None:
        return None
    days = (week_start(on_date) - week_start(settings.program_start_date)).days
    return max(1, days // 7 + 1)


def plan_week(settings: AppSettings, on_date: date) -> int:
    """Week of the repeating plan (1..plan_weeks). Before the program starts it's week 1."""
    week = program_week(settings, on_date) or 1
    return (week - 1) % max(1, settings.plan_weeks or 1) + 1


def start_date_for_plan_week(today: date, week: int) -> date:
    """Program start date that makes `today` fall in program week `week`."""
    return week_start(today) - timedelta(weeks=week - 1)


def runs_in_week(template: WorkoutTemplate, week: int) -> bool:
    return not template.weeks or week in template.weeks


def weeks_overlap(a: Iterable[int] | None, b: Iterable[int] | None) -> bool:
    """Whether two workouts' weeks share a week (None = every week)."""
    if not a or not b:
        return True
    return bool(set(a) & set(b))


def normalize_weeks(weeks: Iterable[int] | None, plan_weeks: int) -> list[int] | None:
    """Sorted, de-duplicated weeks; None when the workout runs every week."""
    if not weeks:
        return None
    result = sorted(set(weeks))
    if plan_weeks <= 1 or result == list(range(1, plan_weeks + 1)):
        return None
    return result


def weeks_text(weeks: Iterable[int] | None) -> str:
    """'Every week', 'Week 2', 'Weeks 1–3' or 'Weeks 1, 3, 5'."""
    if not weeks:
        return "Every week"
    ws = sorted(set(weeks))
    if len(ws) == 1:
        return f"Week {ws[0]}"
    if ws == list(range(ws[0], ws[-1] + 1)):
        return f"Weeks {ws[0]}–{ws[-1]}"
    return "Weeks " + ", ".join(str(w) for w in ws)


def schedule_conflicts(
    templates: Iterable[WorkoutTemplate], weekday: int | None, weeks: list[int] | None,
    exclude: WorkoutTemplate | None = None,
) -> list[WorkoutTemplate]:
    """Workouts already on `weekday` in any of `weeks` (a day holds one workout per week)."""
    if weekday is None:
        return []
    return [t for t in templates
            if t is not exclude and t.weekday == weekday and weeks_overlap(t.weeks, weeks)]


def set_plan_weeks(db: Session, settings: AppSettings, plan_weeks: int) -> None:
    """Change the plan length. Weeks past the end are dropped from workouts; a workout left
    with no weeks is unscheduled (it can still be started by hand)."""
    settings.plan_weeks = plan_weeks
    for t in db.scalars(select(WorkoutTemplate).where(WorkoutTemplate.profile_id == settings.profile_id)):
        if not t.weeks:
            continue
        kept = [w for w in t.weeks if w <= plan_weeks]
        if not kept:
            t.weekday = None
        t.weeks = normalize_weeks(kept, plan_weeks)


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
