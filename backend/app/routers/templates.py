"""Weekly plan editing. Nothing here touches recorded sessions: they hold their own snapshots."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import schemas
from app.deps import DB, CurrentProfile
from app.models import Exercise, Profile, WorkoutTemplate, WorkoutTemplateExercise, utcnow
from app.serializers import template_out
from app.services.plan import get_app_settings, program_week
from app.services.prescription import format_prescription
from app.services.sessions import default_targets

router = APIRouter(prefix="/api/workout-templates", tags=["workout templates"])

OnDate = Annotated[date | None, Query(alias="date", description="Local date used for the program week")]


def _week(db: Session, profile: Profile, on_date: date | None) -> tuple[int | None, int]:
    settings = get_app_settings(db, profile.id)
    return program_week(settings, on_date or date.today()), settings.ramp_weeks


def _load(db: Session, profile: Profile, template_id: int) -> WorkoutTemplate:
    template = db.scalar(
        select(WorkoutTemplate)
        .where(WorkoutTemplate.id == template_id, WorkoutTemplate.profile_id == profile.id)
        .options(selectinload(WorkoutTemplate.exercises).selectinload(WorkoutTemplateExercise.exercise)
                 .selectinload(Exercise.equipment))
    )
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workout template not found")
    return template


def _out(db: Session, profile: Profile, template: WorkoutTemplate, on_date: date | None = None) -> schemas.TemplateOut:
    db.refresh(template)
    week, ramp = _week(db, profile, on_date)
    return template_out(template, week, ramp)


def _check_name(db: Session, profile: Profile, name: str, exclude_id: int | None = None) -> None:
    stmt = select(WorkoutTemplate).where(
        WorkoutTemplate.profile_id == profile.id, func.lower(WorkoutTemplate.name) == name.strip().lower()
    )
    existing = db.scalar(stmt)
    if existing is not None and existing.id != exclude_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A workout named '{existing.name}' already exists")


@router.get("", response_model=list[schemas.TemplateOut])
def list_templates(db: DB, profile: CurrentProfile, on_date: OnDate = None) -> list[schemas.TemplateOut]:
    week, ramp = _week(db, profile, on_date)
    templates = db.scalars(
        select(WorkoutTemplate)
        .where(WorkoutTemplate.profile_id == profile.id)
        .options(selectinload(WorkoutTemplate.exercises).selectinload(WorkoutTemplateExercise.exercise)
                 .selectinload(Exercise.equipment))
    ).all()
    templates = sorted(templates, key=lambda t: (t.weekday is None, t.weekday or 0, t.name))
    return [template_out(t, week, ramp) for t in templates]


@router.get("/{template_id}", response_model=schemas.TemplateOut)
def get_template(template_id: int, db: DB, profile: CurrentProfile, on_date: OnDate = None) -> schemas.TemplateOut:
    week, ramp = _week(db, profile, on_date)
    return template_out(_load(db, profile, template_id), week, ramp)


def _assign_weekday(db: Session, template: WorkoutTemplate, weekday: int | None) -> None:
    """Move a template to a weekday; a template already on that day swaps into the old slot."""
    if template.weekday == weekday:
        return
    old = template.weekday
    occupant = None
    if weekday is not None:
        occupant = db.scalar(select(WorkoutTemplate).where(
            WorkoutTemplate.profile_id == template.profile_id, WorkoutTemplate.weekday == weekday
        ))
    template.weekday = None
    db.flush()
    if occupant is not None:
        occupant.weekday = old
        db.flush()
    template.weekday = weekday
    db.flush()


@router.post("", response_model=schemas.TemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(body: schemas.TemplateCreate, db: DB, profile: CurrentProfile) -> schemas.TemplateOut:
    _check_name(db, profile, body.name)
    template = WorkoutTemplate(profile_id=profile.id, name=body.name.strip(), notes=body.notes)
    db.add(template)
    db.flush()
    if body.copy_from_template_id is not None:
        source = _load(db, profile, body.copy_from_template_id)
        for te in source.exercises:
            template.exercises.append(WorkoutTemplateExercise(
                exercise_id=te.exercise_id, exercise_order=te.exercise_order,
                ramp_sets=te.ramp_sets, target_sets=te.target_sets, target_text=te.target_text,
                target_rep_min=te.target_rep_min, target_rep_max=te.target_rep_max,
                target_duration_min=te.target_duration_min, target_duration_max=te.target_duration_max,
                per_side=te.per_side, suggested_weight=te.suggested_weight,
                default_rest_seconds=te.default_rest_seconds, notes=te.notes, skipped=te.skipped,
            ))
    _assign_weekday(db, template, body.weekday)
    db.commit()
    return _out(db, profile, template)


@router.patch("/{template_id}", response_model=schemas.TemplateOut)
def update_template(template_id: int, body: schemas.TemplateUpdate, db: DB, profile: CurrentProfile) -> schemas.TemplateOut:
    template = _load(db, profile, template_id)
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"]:
        _check_name(db, profile, changes["name"], exclude_id=template.id)
        template.name = changes["name"].strip()
    if "notes" in changes:
        template.notes = changes["notes"]
    if "estimated_duration_minutes" in changes:
        template.estimated_duration_minutes = changes["estimated_duration_minutes"] or None
    if body.unschedule:
        _assign_weekday(db, template, None)
    elif "weekday" in changes and changes["weekday"] is not None:
        _assign_weekday(db, template, changes["weekday"])
    db.commit()
    return _out(db, profile, template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: int, db: DB, profile: CurrentProfile) -> Response:
    """Delete a plan. Past sessions keep their recorded data (template link becomes empty)."""
    db.delete(_load(db, profile, template_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- template exercises


def _get_te(template: WorkoutTemplate, te_id: int) -> WorkoutTemplateExercise:
    for te in template.exercises:
        if te.id == te_id:
            return te
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Exercise is not part of this workout")


def _refresh_text(te: WorkoutTemplateExercise) -> None:
    te.target_text = format_prescription(
        te.target_rep_min, te.target_rep_max, te.target_duration_min, te.target_duration_max, te.per_side
    )


@router.post("/{template_id}/exercises", response_model=schemas.TemplateOut, status_code=status.HTTP_201_CREATED)
def add_template_exercise(
    template_id: int, body: schemas.TemplateExerciseCreate, db: DB, profile: CurrentProfile
) -> schemas.TemplateOut:
    template = _load(db, profile, template_id)
    exercise = db.get(Exercise, body.exercise_id.upper())
    if exercise is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Exercise {body.exercise_id} not found")
    defaults = default_targets(exercise)
    has_targets = any(v is not None for v in (body.target_rep_min, body.target_rep_max,
                                              body.target_duration_min, body.target_duration_max))
    te = WorkoutTemplateExercise(
        exercise=exercise,
        exercise_order=max((t.exercise_order for t in template.exercises), default=0) + 1,
        target_sets=body.target_sets,
        ramp_sets=body.ramp_sets,
        target_rep_min=body.target_rep_min if has_targets else defaults.rep_min,
        target_rep_max=body.target_rep_max if has_targets else defaults.rep_max,
        target_duration_min=body.target_duration_min if has_targets else defaults.duration_min,
        target_duration_max=body.target_duration_max if has_targets else defaults.duration_max,
        per_side=exercise.unilateral if body.per_side is None else body.per_side,
        suggested_weight=body.suggested_weight if body.suggested_weight is not None else exercise.starting_weight,
        default_rest_seconds=body.default_rest_seconds if body.default_rest_seconds is not None else defaults.rest_seconds,
        notes=body.notes,
        skipped=False,
    )
    if has_targets and te.target_rep_max is None and te.target_rep_min is not None:
        te.target_rep_max = te.target_rep_min
    if has_targets and te.target_duration_max is None and te.target_duration_min is not None:
        te.target_duration_max = te.target_duration_min
    _refresh_text(te)
    template.exercises.append(te)
    db.commit()
    return _out(db, profile, template)


@router.patch("/{template_id}/exercises/{te_id}", response_model=schemas.TemplateOut)
def update_template_exercise(
    template_id: int, te_id: int, body: schemas.TemplateExerciseUpdate, db: DB, profile: CurrentProfile
) -> schemas.TemplateOut:
    template = _load(db, profile, template_id)
    te = _get_te(template, te_id)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(te, key, value)
    if "suggested_weight" in changes:
        te.suggested_weight_updated_at = utcnow()
    if {"target_rep_min", "target_rep_max", "target_duration_min", "target_duration_max", "per_side"} & changes.keys():
        if te.target_rep_min is not None and te.target_rep_max is not None and te.target_rep_min > te.target_rep_max:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Minimum reps cannot exceed maximum reps")
        _refresh_text(te)
    db.commit()
    return _out(db, profile, template)


@router.delete("/{template_id}/exercises/{te_id}", response_model=schemas.TemplateOut)
def remove_template_exercise(template_id: int, te_id: int, db: DB, profile: CurrentProfile) -> schemas.TemplateOut:
    template = _load(db, profile, template_id)
    template.exercises.remove(_get_te(template, te_id))
    for order, te in enumerate(template.exercises, start=1):
        te.exercise_order = order
    db.commit()
    return _out(db, profile, template)


@router.post("/{template_id}/reorder", response_model=schemas.TemplateOut)
def reorder_template(template_id: int, body: schemas.ReorderRequest, db: DB, profile: CurrentProfile) -> schemas.TemplateOut:
    template = _load(db, profile, template_id)
    current = {te.id for te in template.exercises}
    if set(body.template_exercise_ids) != current or len(body.template_exercise_ids) != len(current):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Reorder must list every exercise in the workout exactly once")
    by_id = {te.id: te for te in template.exercises}
    for order, te_id in enumerate(body.template_exercise_ids, start=1):
        by_id[te_id].exercise_order = order
    db.commit()
    db.expire(template, ["exercises"])
    return _out(db, profile, template)
