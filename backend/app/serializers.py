"""Builders that turn ORM objects into response schemas."""

from pathlib import Path

from sqlalchemy.orm import Session

from app import schemas
from app.config import get_settings
from app.models import (
    Exercise,
    ExerciseSet,
    LoadType,
    TrackingType,
    WorkoutSession,
    WorkoutSessionExercise,
    WorkoutTemplate,
)
from app.services import progression
from app.services.plan import WEEKDAYS, estimate_minutes, planned_sets

MEDIA_PREFIX = "/media"


# --------------------------------------------------------------------------- media


def media_urls(image_path: str | None) -> tuple[str | None, str | None]:
    if not image_path:
        return None, None
    media_dir = get_settings().media_dir
    if not (media_dir / image_path).is_file():
        return None, None
    image_url = f"{MEDIA_PREFIX}/{image_path}"
    p = Path(image_path)
    thumb_rel = f"{p.parent}/thumbs/{p.stem}.webp"
    thumb_url = f"{MEDIA_PREFIX}/{thumb_rel}" if (media_dir / thumb_rel).is_file() else image_url
    return image_url, thumb_url


# --------------------------------------------------------------------------- exercises


def exercise_out(ex: Exercise, scheduled_in: list[str] | None = None) -> schemas.ExerciseOut:
    image_url, thumb_url = media_urls(ex.image_path)
    return schemas.ExerciseOut(
        id=ex.id,
        name=ex.name,
        primary_muscle_group=ex.primary_muscle_group,
        secondary_muscles=ex.secondary_muscles or [],
        equipment_id=ex.equipment_id,
        equipment_name=ex.equipment.name if ex.equipment else None,
        equipment_detail=ex.equipment_detail,
        attachment=ex.attachment,
        tracking_type=ex.tracking_type,
        load_type=ex.load_type,
        pulley_ratio=ex.pulley_ratio,
        unilateral=ex.unilateral,
        starting_weight=ex.starting_weight,
        image_url=image_url,
        thumb_url=thumb_url,
        notes=ex.notes,
        enabled=ex.enabled,
        is_custom=ex.is_custom,
        weight_options=progression.weight_options(ex.equipment),
        weight_increment=ex.equipment.weight_increment if ex.equipment else None,
        scheduled_in=scheduled_in or [],
    )


def exercise_brief(ex: Exercise) -> schemas.ExerciseBrief:
    image_url, thumb_url = media_urls(ex.image_path)
    return schemas.ExerciseBrief(
        id=ex.id,
        name=ex.name,
        primary_muscle_group=ex.primary_muscle_group,
        tracking_type=ex.tracking_type,
        load_type=ex.load_type,
        pulley_ratio=ex.pulley_ratio,
        unilateral=ex.unilateral,
        thumb_url=thumb_url,
        image_url=image_url,
        enabled=ex.enabled,
        equipment_name=ex.equipment.name if ex.equipment else None,
    )


# --------------------------------------------------------------------------- templates


def template_out(t: WorkoutTemplate, week: int | None, ramp_weeks: int) -> schemas.TemplateOut:
    exercises = [
        schemas.TemplateExerciseOut(
            id=te.id,
            exercise=exercise_brief(te.exercise),
            exercise_order=te.exercise_order,
            ramp_sets=te.ramp_sets,
            target_sets=te.target_sets,
            planned_sets=planned_sets(te, week, ramp_weeks),
            target_text=te.target_text,
            target_rep_min=te.target_rep_min,
            target_rep_max=te.target_rep_max,
            target_duration_min=te.target_duration_min,
            target_duration_max=te.target_duration_max,
            per_side=te.per_side,
            suggested_weight=te.suggested_weight,
            default_rest_seconds=te.default_rest_seconds,
            notes=te.notes,
            skipped=te.skipped,
        )
        for te in t.exercises
    ]
    return schemas.TemplateOut(
        id=t.id,
        name=t.name,
        weekday=t.weekday,
        weekday_name=WEEKDAYS[t.weekday] if t.weekday is not None else None,
        estimated_duration_minutes=estimate_minutes(t, week, ramp_weeks),
        estimated_duration_override=t.estimated_duration_minutes,
        notes=t.notes,
        exercise_count=sum(1 for te in t.exercises if not te.skipped),
        exercises=exercises,
    )


def template_choice(t: WorkoutTemplate, week: int | None, ramp_weeks: int) -> schemas.TemplateChoice:
    return schemas.TemplateChoice(
        id=t.id,
        name=t.name,
        weekday=t.weekday,
        weekday_name=WEEKDAYS[t.weekday] if t.weekday is not None else None,
        exercise_count=sum(1 for te in t.exercises if not te.skipped),
        estimated_duration_minutes=estimate_minutes(t, week, ramp_weeks),
    )


# --------------------------------------------------------------------------- set math


def set_volume(s: ExerciseSet) -> float:
    if not s.completed or s.weight is None or s.repetitions is None:
        return 0.0
    return s.weight * s.repetitions


def exercise_volume(se: WorkoutSessionExercise) -> float:
    return sum(set_volume(s) for s in se.sets)


def _fmt_num(value: float) -> str:
    return f"{value:g}"


def _fmt_duration(seconds: int) -> str:
    if seconds >= 120 and seconds % 60 == 0:
        return f"{seconds // 60} min"
    if seconds >= 60:
        return f"{seconds // 60}:{seconds % 60:02d}"
    return f"{seconds}s"


def summarize_sets(sets: list[ExerciseSet], tracking_type: str, load_type: str) -> str:
    """Compact human summary, e.g. '20 lb × 10, 9, 8' or 'L 10, 9 · R 10, 10'."""
    done = [s for s in sets if s.completed]
    if not done:
        return "No completed sets"
    if tracking_type == TrackingType.cardio:
        parts = []
        for s in done:
            bits = []
            if s.duration_seconds:
                bits.append(_fmt_duration(s.duration_seconds))
            if s.distance:
                bits.append(f"{_fmt_num(s.distance)} mi")
            if s.speed:
                bits.append(f"{_fmt_num(s.speed)} mph")
            parts.append(" · ".join(bits) or "done")
        return "; ".join(parts)

    def value(s: ExerciseSet) -> str:
        if tracking_type == TrackingType.timed:
            return _fmt_duration(s.duration_seconds or 0)
        return str(s.repetitions if s.repetitions is not None else "-")

    weights = {s.weight for s in done}
    weighted = load_type not in (LoadType.bodyweight, LoadType.none)
    if len(weights) == 1:
        (w,) = weights
        if w is None or (not weighted and not w):
            prefix = ""
        else:
            prefix = f"{'+' if not weighted else ''}{_fmt_num(w)} lb × "
        sides = {s.side for s in done}
        if sides == {"left", "right"} or (sides and None not in sides):
            left = ", ".join(value(s) for s in done if s.side == "left")
            right = ", ".join(value(s) for s in done if s.side == "right")
            return f"{prefix}L {left} · R {right}".strip()
        return prefix + ", ".join(value(s) for s in done)
    side_tag = {"left": "L ", "right": "R ", None: ""}
    return ", ".join(
        f"{side_tag[s.side]}{_fmt_num(s.weight) + ' lb × ' if s.weight is not None else ''}{value(s)}"
        for s in done
    )


def best_set_text(se: WorkoutSessionExercise) -> str | None:
    done = [s for s in se.sets if s.completed]
    if not done:
        return None
    if se.tracking_type in (TrackingType.cardio, TrackingType.timed):
        return summarize_sets(se.sets, se.tracking_type, se.load_type)
    best = max(done, key=lambda s: ((s.weight or 0), (s.repetitions or 0)))
    if best.weight and se.load_type not in (LoadType.bodyweight, LoadType.none):
        return f"{_fmt_num(best.weight)} lb × {best.repetitions or 0}"
    if best.weight:
        return f"+{_fmt_num(best.weight)} lb × {best.repetitions or 0}"
    return f"{best.repetitions or 0} reps"


# --------------------------------------------------------------------------- sessions


def previous_out(db: Session, se: WorkoutSessionExercise, session: WorkoutSession) -> schemas.PreviousPerformance | None:
    prev = progression.previous_performance(db, se.exercise_id, session.profile_id, before=session)
    if prev is None:
        return None
    done = [s for s in prev.sets if s.completed]
    return schemas.PreviousPerformance(
        session_id=prev.session.id,
        session_name=prev.session.name,
        performed_on=prev.session.performed_on,
        load_type=prev.load_type,
        pulley_ratio=prev.pulley_ratio,
        sets=[schemas.SetOut.model_validate(s) for s in done],
        summary=summarize_sets(done, prev.tracking_type, prev.load_type),
    )


def session_exercise_out(db: Session, se: WorkoutSessionExercise, session: WorkoutSession) -> schemas.SessionExerciseOut:
    ex = se.exercise
    image_url, thumb_url = media_urls(ex.image_path)
    return schemas.SessionExerciseOut(
        id=se.id,
        exercise_id=se.exercise_id,
        exercise_order=se.exercise_order,
        status=se.status,
        notes=se.notes,
        exercise_name=se.exercise_name,
        tracking_type=se.tracking_type,
        load_type=se.load_type,
        pulley_ratio=se.pulley_ratio,
        unilateral=se.unilateral,
        target_sets=se.target_sets,
        target_text=se.target_text,
        target_rep_min=se.target_rep_min,
        target_rep_max=se.target_rep_max,
        target_duration_min=se.target_duration_min,
        target_duration_max=se.target_duration_max,
        suggested_weight=se.suggested_weight,
        recommended_weight=se.recommended_weight,
        suggestion_action=se.suggestion_action,
        suggestion_reason=se.suggestion_reason,
        rest_seconds=se.rest_seconds,
        plan_notes=se.plan_notes,
        primary_muscle_group=ex.primary_muscle_group,
        equipment_name=ex.equipment.name if ex.equipment else None,
        equipment_detail=ex.equipment_detail,
        attachment=ex.attachment,
        image_url=image_url,
        thumb_url=thumb_url,
        weight_options=progression.weight_options(ex.equipment),
        weight_increment=ex.equipment.weight_increment if ex.equipment else None,
        previous=previous_out(db, se, session),
        sets=[schemas.SetOut.model_validate(s) for s in se.sets],
    )


def session_out(db: Session, session: WorkoutSession) -> schemas.SessionOut:
    all_sets = [s for se in session.exercises for s in se.sets]
    return schemas.SessionOut(
        id=session.id,
        workout_template_id=session.workout_template_id,
        name=session.name,
        performed_on=session.performed_on,
        program_week=session.program_week,
        started_at=session.started_at,
        completed_at=session.completed_at,
        status=session.status,
        notes=session.notes,
        completed_sets=sum(1 for s in all_sets if s.completed),
        total_sets=len(all_sets),
        exercises=[session_exercise_out(db, se, session) for se in session.exercises],
    )


def session_duration_minutes(session: WorkoutSession) -> int | None:
    if session.completed_at is None:
        return None
    return max(0, round((session.completed_at - session.started_at).total_seconds() / 60))


def session_summary(session: WorkoutSession) -> schemas.SessionSummary:
    all_sets = [s for se in session.exercises for s in se.sets]
    exercises = [
        schemas.SessionExerciseSummary(
            exercise_id=se.exercise_id,
            exercise_name=se.exercise_name,
            status=se.status,
            load_type=se.load_type,
            completed_sets=sum(1 for s in se.sets if s.completed),
            best=best_set_text(se),
        )
        for se in session.exercises
    ]
    return schemas.SessionSummary(
        id=session.id,
        workout_template_id=session.workout_template_id,
        name=session.name,
        performed_on=session.performed_on,
        started_at=session.started_at,
        completed_at=session.completed_at,
        duration_minutes=session_duration_minutes(session),
        status=session.status,
        notes=session.notes,
        exercise_count=len(session.exercises),
        exercises_completed=sum(1 for e in exercises if e.completed_sets > 0),
        completed_sets=sum(1 for s in all_sets if s.completed),
        total_sets=len(all_sets),
        volume=sum(exercise_volume(se) for se in session.exercises),
        exercises=exercises,
    )
