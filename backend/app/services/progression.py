"""Previous-performance lookup and simple, transparent weight suggestions.

Rules (per profile and exact exercise ID - variations never share history):

* Never performed      -> plan's starting weight.
* Plan weight edited after the last performance -> use the edited plan weight.
* Every planned set reached the top of the rep range at the working weight
                       -> suggest the next weight the equipment supports (needs approval).
* Average reps fell `progression_drop_threshold` or more below the range minimum
                       -> suggest the next lower weight (needs approval).
* Otherwise            -> keep the weight.

Sets are always prefilled with the weight actually used last time; a suggested
increase or decrease is only applied when the user accepts it.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Equipment,
    ExerciseSet,
    LoadType,
    SessionStatus,
    TrackingType,
    WorkoutSession,
    WorkoutSessionExercise,
)


class SuggestionAction(StrEnum):
    start = "start"
    plan = "plan"
    increase = "increase"
    maintain = "maintain"
    decrease = "decrease"
    none = "none"


@dataclass
class Suggestion:
    action: SuggestionAction
    recommended_weight: float | None  # what the rules recommend
    prefill_weight: float | None  # what sets start with (never an unapproved change)
    reason: str


@dataclass
class Target:
    rep_min: int | None
    rep_max: int | None
    duration_max: int | None
    plan_weight: float | None
    plan_weight_updated_at: datetime | None


WEIGHTED = {LoadType.per_dumbbell, LoadType.single_dumbbell, LoadType.plates_loaded, LoadType.added_plates}


def fmt_weight(weight: float | None) -> str:
    if weight is None:
        return "-"
    return f"{weight:g} lb"


# --------------------------------------------------------------------------- equipment


def weight_options(equipment: Equipment | None) -> list[float] | None:
    if equipment is None or not equipment.available_weights:
        return None
    return sorted({float(w) for w in equipment.available_weights})


def step_weight(equipment: Equipment | None, weight: float, direction: int) -> float:
    """Next supported weight above (direction=1) or below (-1). Returns `weight` at the ends."""
    options = weight_options(equipment)
    if options:
        if direction > 0:
            higher = [w for w in options if w > weight]
            return higher[0] if higher else weight
        lower = [w for w in options if w < weight]
        return lower[-1] if lower else weight
    increment = (equipment.weight_increment if equipment else None) or 5.0
    return max(0.0, weight + direction * increment)


# --------------------------------------------------------------------------- history


def previous_performance(
    db: Session, exercise_id: str, profile_id: int, *, before: WorkoutSession | None = None
) -> WorkoutSessionExercise | None:
    """The profile's most recent completed session exercise with at least one completed set."""
    stmt = (
        select(WorkoutSessionExercise)
        .join(WorkoutSession)
        .where(
            WorkoutSessionExercise.exercise_id == exercise_id,
            WorkoutSession.profile_id == profile_id,
            WorkoutSession.status == SessionStatus.completed,
            WorkoutSessionExercise.sets.any(ExerciseSet.completed.is_(True)),
        )
        .options(selectinload(WorkoutSessionExercise.sets), selectinload(WorkoutSessionExercise.session))
        .order_by(WorkoutSession.performed_on.desc(), WorkoutSession.started_at.desc())
        .limit(1)
    )
    if before is not None:
        stmt = stmt.where(
            WorkoutSession.id != before.id,
            WorkoutSession.started_at < before.started_at,
        )
    return db.scalars(stmt).first()


def completed_sets(se: WorkoutSessionExercise) -> list[ExerciseSet]:
    return [s for s in se.sets if s.completed]


def _reps_by_set(sets: list[ExerciseSet]) -> dict[int, int]:
    """Reps per set number; for left/right sets the weaker side counts."""
    reps: dict[int, int] = {}
    for s in sets:
        if s.repetitions is None:
            continue
        reps[s.set_number] = min(reps.get(s.set_number, s.repetitions), s.repetitions)
    return reps


def suggest(
    *,
    tracking_type: str,
    load_type: str,
    equipment: Equipment | None,
    target: Target,
    last: WorkoutSessionExercise | None,
    drop_threshold: int,
) -> Suggestion:
    weighted = load_type in WEIGHTED

    if tracking_type == TrackingType.cardio or load_type == LoadType.none:
        return Suggestion(SuggestionAction.none, None, None, "")

    if last is None:
        if weighted:
            reason = (
                f"First time: starting weight from your plan ({fmt_weight(target.plan_weight)})"
                if target.plan_weight is not None
                else "First time: no starting weight in the plan; pick a comfortable weight"
            )
            return Suggestion(SuggestionAction.start, target.plan_weight, target.plan_weight, reason)
        return Suggestion(SuggestionAction.none, None, None, "First time doing this exercise")

    sets = completed_sets(last)
    weights = [s.weight for s in sets if s.weight is not None]
    top = max(weights) if weights else None
    last_completed = last.session.completed_at

    if (
        weighted
        and target.plan_weight is not None
        and target.plan_weight_updated_at is not None
        and last_completed is not None
        and _aware(target.plan_weight_updated_at) > _aware(last_completed)
    ):
        return Suggestion(
            SuggestionAction.plan, target.plan_weight, target.plan_weight,
            f"Using the plan weight you set ({fmt_weight(target.plan_weight)})",
        )

    if tracking_type == TrackingType.timed:
        durations = [s.duration_seconds for s in sets if s.duration_seconds]
        if target.duration_max and durations and min(durations) >= target.duration_max:
            reason = f"You held {target.duration_max}s on every set - try a longer hold or harder variation"
        else:
            reason = "Match or beat last time's holds"
        return Suggestion(SuggestionAction.maintain, top, top, reason)

    working = [s for s in sets if (s.weight == top)] if weighted else sets
    reps = _reps_by_set(working)
    planned = last.target_sets or len(reps)

    if target.rep_max is None or not reps:
        return Suggestion(SuggestionAction.maintain, top, top, "Repeat last time's weight")

    rep_list = ", ".join(str(reps[k]) for k in sorted(reps))
    all_top = len(reps) >= planned and all(r >= target.rep_max for r in reps.values())
    average = sum(reps.values()) / len(reps)

    if not weighted:
        if all_top:
            return Suggestion(
                SuggestionAction.maintain, top, top,
                f"Hit {target.rep_max} reps on every set ({rep_list}) - add reps, slow the tempo or add weight",
            )
        return Suggestion(SuggestionAction.maintain, top, top, f"Last time: {rep_list} reps")

    assert top is not None
    if all_top:
        nxt = step_weight(equipment, top, 1)
        if nxt > top:
            return Suggestion(
                SuggestionAction.increase, nxt, top,
                f"Hit {target.rep_max}+ reps on all {len(reps)} sets at {fmt_weight(top)} ({rep_list}). "
                f"Ready for {fmt_weight(nxt)}",
            )
        return Suggestion(
            SuggestionAction.maintain, top, top,
            f"Top of the range at {fmt_weight(top)}, the heaviest available - add reps or slow the tempo",
        )

    if target.rep_min is not None and average <= target.rep_min - drop_threshold:
        lower = step_weight(equipment, top, -1)
        if lower < top:
            return Suggestion(
                SuggestionAction.decrease, lower, top,
                f"Reps dropped to {rep_list} at {fmt_weight(top)} (target {target.rep_min}-{target.rep_max}). "
                f"Consider {fmt_weight(lower)}",
            )

    return Suggestion(
        SuggestionAction.maintain, top, top,
        f"Last time {fmt_weight(top)} × {rep_list}. Stay here until every set reaches {target.rep_max}",
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
