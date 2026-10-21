"""Starting sessions: snapshot the plan, compute suggestions and prefill sets."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.models import (
    Exercise,
    ExerciseSet,
    Side,
    TrackingType,
    WorkoutSession,
    WorkoutSessionExercise,
    WorkoutTemplate,
    WorkoutTemplateExercise,
)
from app.services import progression
from app.services.plan import get_app_settings, planned_sets, program_week
from app.services.prescription import format_prescription


@dataclass
class Targets:
    sets: int
    rep_min: int | None
    rep_max: int | None
    duration_min: int | None
    duration_max: int | None
    rest_seconds: int


def default_targets(exercise: Exercise) -> Targets:
    """Prescription used when an exercise is added without one."""
    match exercise.tracking_type:
        case TrackingType.cardio:
            return Targets(1, None, None, 20 * 60, 30 * 60, 0)
        case TrackingType.timed:
            return Targets(3, None, None, 30, 45, 60)
        case TrackingType.bodyweight:
            return Targets(3, 10, 15, None, None, 60)
        case _:
            return Targets(3, 8, 12, None, None, 90)


def _sides(unilateral: bool) -> list[str | None]:
    return [Side.left.value, Side.right.value] if unilateral else [None]


def build_session_exercise(
    db: Session,
    exercise: Exercise,
    order: int,
    *,
    profile_id: int,
    te: WorkoutTemplateExercise | None,
    week: int | None,
    ramp_weeks: int,
    drop_threshold: int,
) -> WorkoutSessionExercise:
    if te is not None:
        t = Targets(
            planned_sets(te, week, ramp_weeks),
            te.target_rep_min, te.target_rep_max,
            te.target_duration_min, te.target_duration_max,
            te.default_rest_seconds,
        )
        target_text = te.target_text
        plan_weight = te.suggested_weight
        plan_weight_updated_at = te.suggested_weight_updated_at
        plan_notes = te.notes
    else:
        t = default_targets(exercise)
        target_text = format_prescription(t.rep_min, t.rep_max, t.duration_min, t.duration_max,
                                          exercise.unilateral)
        plan_weight = exercise.starting_weight
        plan_weight_updated_at = None
        plan_notes = None

    # A duration prescription on a non-cardio exercise is a timed hold.
    tracking = exercise.tracking_type
    if t.duration_min is not None and tracking != TrackingType.cardio:
        tracking = TrackingType.timed.value

    last = progression.previous_performance(db, exercise.id, profile_id)
    suggestion = progression.suggest(
        tracking_type=tracking,
        load_type=exercise.load_type,
        equipment=exercise.equipment,
        target=progression.Target(t.rep_min, t.rep_max, t.duration_max, plan_weight, plan_weight_updated_at),
        last=last,
        drop_threshold=drop_threshold,
    )

    se = WorkoutSessionExercise(
        exercise=exercise,
        exercise_order=order,
        exercise_name=exercise.name,
        tracking_type=tracking,
        load_type=exercise.load_type,
        pulley_ratio=exercise.pulley_ratio,
        unilateral=exercise.unilateral,
        target_sets=t.sets,
        target_text=target_text,
        target_rep_min=t.rep_min,
        target_rep_max=t.rep_max,
        target_duration_min=t.duration_min,
        target_duration_max=t.duration_max,
        suggested_weight=suggestion.prefill_weight,
        recommended_weight=suggestion.recommended_weight,
        suggestion_action=suggestion.action.value,
        suggestion_reason=suggestion.reason or None,
        rest_seconds=t.rest_seconds,
        plan_notes=plan_notes,
    )
    se.sets = _prefill_sets(se, last, suggestion)
    return se


def _prefill_sets(
    se: WorkoutSessionExercise,
    last: WorkoutSessionExercise | None,
    suggestion: progression.Suggestion,
) -> list[ExerciseSet]:
    """Planned sets prefilled from last time (same weight) or the targets."""
    previous: dict[tuple[int, str | None], ExerciseSet] = {}
    if last is not None:
        for s in last.sets:
            if s.completed:
                previous[(s.set_number, s.side)] = s

    weighted = se.load_type in progression.WEIGHTED
    sets: list[ExerciseSet] = []
    for number in range(1, se.target_sets + 1):
        for side in _sides(se.unilateral):
            prev = previous.get((number, side))
            if se.tracking_type == TrackingType.cardio:
                sets.append(ExerciseSet(
                    set_number=number, side=side,
                    duration_seconds=(prev.duration_seconds if prev else None) or se.target_duration_min,
                    distance=prev.distance if prev else None,
                    speed=prev.speed if prev else None,
                ))
                continue
            if weighted:
                weight = suggestion.prefill_weight
            else:  # bodyweight: keep any added weight from last time
                weight = prev.weight if prev else None
            same_weight = prev is not None and prev.weight == weight
            reps = None
            duration = None
            if se.tracking_type == TrackingType.timed:
                duration = (prev.duration_seconds if same_weight and prev else None) or se.target_duration_min
            else:
                reps = (prev.repetitions if same_weight and prev else None) or se.target_rep_min
            sets.append(ExerciseSet(set_number=number, side=side, weight=weight,
                                    repetitions=reps, duration_seconds=duration))
    return sets


def add_set(se: WorkoutSessionExercise) -> list[ExerciseSet]:
    """Append one set (a left/right pair for unilateral exercises), copying the last values."""
    number = max((s.set_number for s in se.sets), default=0) + 1
    created = []
    for side in _sides(se.unilateral):
        template = next((s for s in reversed(se.sets) if s.side == side), None)
        new = ExerciseSet(set_number=number, side=side)
        if template is not None:
            new.weight = template.weight
            new.repetitions = template.repetitions
            new.duration_seconds = template.duration_seconds
            new.distance = template.distance
            new.speed = template.speed
        else:
            new.weight = se.suggested_weight if se.load_type in progression.WEIGHTED else None
            new.repetitions = se.target_rep_min
            new.duration_seconds = se.target_duration_min
        se.sets.append(new)
        created.append(new)
    return created


def renumber_sets(se: WorkoutSessionExercise) -> None:
    numbers = sorted({s.set_number for s in se.sets})
    mapping = {old: new for new, old in enumerate(numbers, start=1)}
    for s in se.sets:
        s.set_number = mapping[s.set_number]


def start_session(
    db: Session,
    profile_id: int,
    template: WorkoutTemplate | None,
    performed_on: date,
    name: str | None = None,
) -> WorkoutSession:
    settings = get_app_settings(db, profile_id)
    if settings.program_start_date is None:
        settings.program_start_date = performed_on
    week = program_week(settings, performed_on)

    session = WorkoutSession(
        profile_id=profile_id,
        workout_template_id=template.id if template else None,
        name=name or (template.name if template else "Custom workout"),
        performed_on=performed_on,
        program_week=week,
    )
    if template is not None:
        order = 0
        for te in template.exercises:
            if te.skipped or not te.exercise.enabled:
                continue
            order += 1
            session.exercises.append(build_session_exercise(
                db, te.exercise, order, profile_id=profile_id, te=te, week=week,
                ramp_weeks=settings.ramp_weeks, drop_threshold=settings.progression_drop_threshold,
            ))
    db.add(session)
    db.flush()
    return session


def append_exercise(db: Session, session: WorkoutSession, exercise: Exercise) -> WorkoutSessionExercise:
    settings = get_app_settings(db, session.profile_id)
    order = max((e.exercise_order for e in session.exercises), default=0) + 1
    se = build_session_exercise(
        db, exercise, order, profile_id=session.profile_id, te=None, week=session.program_week,
        ramp_weeks=settings.ramp_weeks, drop_threshold=settings.progression_drop_threshold,
    )
    session.exercises.append(se)
    db.flush()
    return se

