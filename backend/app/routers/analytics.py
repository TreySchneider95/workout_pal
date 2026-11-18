from collections import defaultdict
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import schemas
from app.deps import DB, CurrentProfile
from app.models import SessionStatus, WorkoutSession, WorkoutSessionExercise, WorkoutTemplate
from app.serializers import exercise_volume, session_duration_minutes
from app.services.plan import get_app_settings, plan_week, runs_in_week, week_start
from app.services.progression import WEIGHTED

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

WEEKS = 12
CONSISTENCY_WEEKS = 8


@router.get("/summary", response_model=schemas.AnalyticsSummary)
def summary(
    db: DB,
    profile: CurrentProfile,
    on_date: Annotated[date | None, Query(alias="date", description="The device's local date")] = None,
) -> schemas.AnalyticsSummary:
    today = on_date or date.today()
    sessions = db.scalars(
        select(WorkoutSession)
        .where(WorkoutSession.profile_id == profile.id, WorkoutSession.status == SessionStatus.completed)
        .options(selectinload(WorkoutSession.exercises).selectinload(WorkoutSessionExercise.sets))
        .order_by(WorkoutSession.performed_on, WorkoutSession.started_at)
    ).all()
    settings = get_app_settings(db, profile.id)
    scheduled = db.scalars(select(WorkoutTemplate).where(
        WorkoutTemplate.profile_id == profile.id, WorkoutTemplate.weekday.is_not(None)
    )).all()

    this_week = week_start(today)
    # Past weeks use the plan week their sessions recorded, so restarting the plan or changing its
    # length doesn't rewrite history. Weeks with no sessions fall back to today's plan calendar.
    recorded: dict[date, int] = {}
    for s in sessions:
        if s.plan_week is not None:
            recorded[week_start(s.performed_on)] = s.plan_week

    def plan_week_on(day: date) -> int:
        start = week_start(day)
        if start < this_week and start in recorded:
            return recorded[start]
        return plan_week(settings, day)

    def planned_on(day: date) -> bool:
        week = plan_week_on(day)
        return any(t.weekday == day.weekday() and runs_in_week(t, week) for t in scheduled)

    def planned_in_week(start: date) -> int:
        return sum(planned_on(start + timedelta(days=i)) for i in range(7))

    first_week = this_week - timedelta(weeks=WEEKS - 1)
    by_week: dict[date, list[WorkoutSession]] = defaultdict(list)
    by_day: dict[date, list[int]] = defaultdict(list)
    for s in sessions:
        by_week[week_start(s.performed_on)].append(s)
        by_day[s.performed_on].append(s.id)

    weeks = []
    for i in range(WEEKS):
        start = first_week + timedelta(weeks=i)
        items = by_week.get(start, [])
        weeks.append(schemas.WeekBucket(
            week_start=start,
            workouts=len(items),
            planned=planned_in_week(start),
            minutes=sum(session_duration_minutes(s) or 0 for s in items),
            volume=round(sum(exercise_volume(se) for s in items for se in s.exercises), 1),
        ))

    # Consistency: scheduled days (up to today) on which a workout was completed.
    window_start = this_week - timedelta(weeks=CONSISTENCY_WEEKS - 1)
    first_session_day = sessions[0].performed_on if sessions else None
    planned_days = done_days = 0
    if first_session_day is not None:
        day = max(window_start, first_session_day)
        while day <= today:
            if planned_on(day):
                planned_days += 1
                if day in by_day:
                    done_days += 1
            day += timedelta(days=1)
    consistency = round(100 * done_days / planned_days) if planned_days else None

    # Streak: consecutive weeks (before this one, plus this one if already complete) that hit the plan.
    # Weeks with nothing planned (e.g. a rest week in a multi-week plan) don't break it.
    streak = 0
    planned_this_week = planned_in_week(this_week)
    if sessions and scheduled:
        def trained_days(week: date) -> int:
            return len({s.performed_on for s in by_week.get(week, [])})

        earliest = week_start(sessions[0].performed_on)
        week = this_week if planned_this_week and trained_days(this_week) >= planned_this_week \
            else this_week - timedelta(weeks=1)
        while week >= earliest:
            planned = planned_in_week(week)
            if planned and trained_days(week) < planned:
                break
            if planned:
                streak += 1
            week -= timedelta(weeks=1)

    # Personal bests: a session whose top working weight beats every earlier session.
    best_so_far: dict[str, float] = {}
    personal_bests: list[schemas.PersonalBest] = []
    for s in sessions:
        for se in s.exercises:
            if se.load_type not in WEIGHTED:
                continue
            done = [x for x in se.sets if x.completed and x.weight is not None and (x.repetitions or 0) > 0]
            if not done:
                continue
            top = max(done, key=lambda x: (x.weight, x.repetitions or 0))
            previous = best_so_far.get(se.exercise_id)
            if previous is not None and top.weight > previous:
                personal_bests.append(schemas.PersonalBest(
                    exercise_id=se.exercise_id, exercise_name=se.exercise_name, performed_on=s.performed_on,
                    weight=top.weight, repetitions=top.repetitions, previous_best=previous, load_type=se.load_type,
                ))
            if previous is None or top.weight > previous:
                best_so_far[se.exercise_id] = top.weight
    personal_bests.reverse()

    calendar_start = first_week
    calendar_end = this_week + timedelta(days=6)
    calendar = []
    day = calendar_start
    while day <= calendar_end:
        calendar.append(schemas.CalendarDay(date=day, session_ids=by_day.get(day, []),
                                            planned=planned_on(day)))
        day += timedelta(days=1)

    durations = [m for m in (session_duration_minutes(s) for s in sessions) if m is not None]
    return schemas.AnalyticsSummary(
        workouts_this_week=len(by_week.get(this_week, [])),
        planned_this_week=planned_this_week,
        total_workouts=len(sessions),
        total_minutes=sum(durations),
        average_minutes=round(sum(durations) / len(durations)) if durations else None,
        consistency_percent=consistency,
        current_streak_weeks=streak,
        weeks=weeks,
        personal_bests=personal_bests[:8],
        calendar=calendar,
    )
