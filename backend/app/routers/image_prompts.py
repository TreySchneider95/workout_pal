"""Prompts for drawing the pictures that exercises in the current plan are missing."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import schemas
from app.deps import DB, CurrentProfile
from app.models import Exercise, WorkoutTemplate, WorkoutTemplateExercise
from app.serializers import exercise_brief
from app.services.image_prompts import Person, build_image_prompt
from app.services.plan import WEEKDAYS

router = APIRouter(prefix="/api/image-prompts", tags=["exercise pictures"])


@router.get("", response_model=list[schemas.ImagePromptItem])
def plan_image_prompts(
    db: DB,
    profile: CurrentProfile,
    person: Annotated[Person, Query(description="Who the picture shows")] = "man",
) -> list[schemas.ImagePromptItem]:
    """Every exercise in the profile's plan, in plan order, with a one-picture prompt for each."""
    templates = db.scalars(
        select(WorkoutTemplate).where(WorkoutTemplate.profile_id == profile.id)
        .options(selectinload(WorkoutTemplate.exercises).selectinload(WorkoutTemplateExercise.exercise)
                 .selectinload(Exercise.equipment))
    ).all()
    templates = sorted(templates, key=lambda t: (t.weekday is None, t.weekday or 0, min(t.weeks or [0]), t.name))

    first_use: dict[str, WorkoutTemplateExercise] = {}
    workouts: dict[str, list[str]] = {}
    for t in templates:
        label = f"{t.name} ({WEEKDAYS[t.weekday][:3]})" if t.weekday is not None else t.name
        for te in t.exercises:
            first_use.setdefault(te.exercise_id, te)
            names = workouts.setdefault(te.exercise_id, [])
            if label not in names:
                names.append(label)

    items = []
    for ex_id, te in first_use.items():
        brief = exercise_brief(te.exercise)
        items.append(schemas.ImagePromptItem(
            exercise=brief,
            has_image=brief.image_url is not None,
            workouts=workouts[ex_id],
            prompt=build_image_prompt(te.exercise, te, person),
        ))
    return items
