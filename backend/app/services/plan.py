"""Helpers for the plan: program weeks, plan weeks, planned set counts and duration estimates.

A plan repeats every ``plan_weeks`` weeks (1 = the same workouts every week). Each workout
runs in the plan weeks listed in ``WorkoutTemplate.weeks`` (``None`` = every week), so a
6-week program can do different workouts, sets or reps from one week to the next.
Two dates drive the weeks, and they're kept apart on purpose:

- ``program_start_date``: when the person started training. Program weeks count 7-day blocks
  from it and decide the lighter ramp-in sets (``ramp_weeks``). Restarting a plan never moves it.
- ``plan_start_date``: the Monday that plan week 1 starts on. Plan weeks run Monday to Sunday;
  restarting a plan or picking "make week N this week" moves only this date.
"""

import threading
from collections.abc import Iterable
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSettings, TrackingType, WorkoutTemplate, WorkoutTemplateExercise

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MAX_PLAN_WEEKS = 12

# Changes to the schedule (which workout runs on which day in which weeks) read the plan, then
# write it. The database can't enforce "one workout per day per week", so those changes are
# serialized here (the server runs as a single process).
schedule_lock = threading.Lock()

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
    """Training week (7-day blocks from the program start date); drives the ramp-in sets."""
    if settings.program_start_date is None:
        return None
    return max(1, (on_date - settings.program_start_date).days // 7 + 1)


def plan_start_for(day: date) -> date:
    """The Monday plan week 1 starts on when a plan (re)starts on `day`: that week's Monday,
    or the next Monday at the weekend, so a weekend restart doesn't use up week 1."""
    monday = week_start(day)
    return monday + timedelta(weeks=1) if day.weekday() >= 5 else monday


def plan_start_for_week(on_date: date, week: int) -> date:
    """Plan start date that makes `on_date`'s week plan week `week`."""
    return week_start(on_date) - timedelta(weeks=week - 1)


def plan_week(settings: AppSettings, on_date: date) -> int:
    """Week of the repeating plan (1..plan_weeks). Before the plan starts it's week 1."""
    start = settings.plan_start_date
    if start is None or on_date < start:
        return 1
    return (on_date - week_start(start)).days // 7 % max(1, settings.plan_weeks or 1) + 1


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


def set_plan_weeks(db: Session, settings: AppSettings, plan_weeks: int, today: date) -> None:
    """Change the plan length. Weeks past the end are dropped from workouts; a workout left
    with no weeks is unscheduled (it can still be started by hand).

    `today` keeps its plan week (or goes back to week 1 when that week is dropped); otherwise the
    new length would silently move today into a different week."""
    if settings.plan_start_date is not None and today >= settings.plan_start_date:
        current = plan_week(settings, today)
        settings.plan_start_date = plan_start_for_week(today, current if current <= plan_weeks else 1)
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
