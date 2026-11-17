"""Prompts for an image AI to draw a missing exercise picture, in the style of the existing ones.

The library's pictures are portrait infographics: a title, two photo panels of a real-looking
person ("1 Start position" / "2 End position") with bullet captions, then a bottom row with the
muscles worked, key form tips and common mistakes. Image generators cap how many pictures you
can make, so each prompt asks for exactly one exercise and one image.
"""

from dataclasses import dataclass
from typing import Literal

from app.models import Exercise, TrackingType, WorkoutTemplateExercise

Person = Literal["man", "woman"]

# What the equipment looks like; brand and model names mean nothing to an image model.
_EQUIPMENT_LOOK = {
    "dumbbell": "black hexagonal rubber dumbbells",
    "cable": "a black cable pulley station (the cable runs over a pulley to a weight-plate-loaded carriage)",
    "smith_machine": "a black Smith machine (a barbell that slides on fixed vertical rails) built into a power rack",
    "cardio": "a modern treadmill",
}


@dataclass(frozen=True)
class _Phases:
    first: str
    second: str
    motion: str


def _phases(tracking: str) -> _Phases:
    if tracking == TrackingType.timed:
        return _Phases("SETUP POSITION", "HOLD POSITION",
                       "a dashed alignment line in the hold panel showing the straight body position")
    if tracking == TrackingType.cardio:
        return _Phases("GETTING STARTED", "IN MOTION", "subtle motion lines showing a steady, natural pace")
    return _Phases("START POSITION", "END POSITION",
                   "a bold curved arrow in the end panel showing the direction of the movement")


def _target(te: WorkoutTemplateExercise | None) -> str | None:
    if te is None:
        return None
    if te.exercise.tracking_type == TrackingType.cardio:
        return te.target_text
    if te.target_duration_min is not None:
        return f"{te.target_sets} sets of {te.target_text}"
    if te.target_rep_min is not None:
        lo, hi = te.target_rep_min, te.target_rep_max or te.target_rep_min
        reps = f"{lo}" if lo == hi else f"{lo}-{hi}"
        return f"{te.target_sets} sets of {reps} reps{' per side' if te.per_side else ''}"
    return f"{te.target_sets} sets of {te.target_text}" if te.target_text else None


def build_image_prompt(exercise: Exercise, te: WorkoutTemplateExercise | None = None, person: Person = "man") -> str:
    """One image prompt for `exercise`; `te` (its place in the plan) adds the target and coaching notes."""
    phases = _phases(exercise.tracking_type)
    who = "man" if person == "man" else "woman"
    equipment = exercise.equipment_detail or (exercise.equipment.name if exercise.equipment else "None (bodyweight)")
    look = _EQUIPMENT_LOOK.get(exercise.equipment.equipment_type) if exercise.equipment else None

    facts = [f"- Exercise: {exercise.name}"]
    facts.append(f"- Equipment: {equipment}" + (f", with a {exercise.attachment.lower()}" if exercise.attachment else ""))
    if look:
        facts.append(f"- What the equipment looks like: {look}. Draw no brand names or logos on it.")
    muscles = exercise.primary_muscle_group or "the main muscles this exercise trains"
    facts.append(f"- Main muscle group: {muscles}"
                 + (f"; also works {', '.join(exercise.secondary_muscles)}" if exercise.secondary_muscles else ""))
    if exercise.unilateral:
        facts.append("- Done one side at a time: show the working side clearly, and say in the tips to finish all "
                     "reps on one side, then switch.")
    target = _target(te)
    if target:
        facts.append(f"- Their plan: {target}")
    notes = (("Library notes", exercise.notes),
             ("Notes from their plan (use only what describes the movement)", te.notes if te else None))
    for label, note in notes:
        if note and note.strip():
            facts.append(f"- {label}: {note.strip()}")

    tips_extra = f', including "{target}"' if target else ""
    focus = (exercise.primary_muscle_group or "this exercise").lower()
    return f"""Create ONE image: an exercise instruction infographic for "{exercise.name}". Make exactly one
picture for this exercise and nothing else. If you can't create images, say so instead of describing one.

# The exercise

{chr(10).join(facts)}

Depict exactly this exercise with exactly this equipment. Follow the name literally (grip, bench
angle, stance, cable height, one arm or two); don't swap in a similar exercise or a different machine.

# Style (match it closely; it has to fit with the other pictures in the app)

- Portrait, 4:5 (about 1120 x 1400 px). Clean, bright, modern fitness-app infographic on a white
  background, with dark navy headings and blue and green accents.
- Large, bold, easy-to-read sans-serif text. Spell every word correctly and keep text short.
- No watermarks, logos, signatures or website names.

# Layout, top to bottom

1. Title: "{exercise.name.upper()}" in big, bold, dark-navy letters across the top, with a short
   motivating tagline about what it does for the {focus} in small, widely spaced capitals.
2. Two equal photo panels side by side:
   - Left: a blue circle with "1" and the heading "{phases.first}".
   - Right: a green circle with "2" and the heading "{phases.second}" (or a more specific name for
     this exercise's position, if one reads better).
   Both panels are realistic, photo-quality pictures of the same fit adult {who} (athletic t-shirt or
   tank top, dark shorts, sneakers) in a bright, modern home gym with dumbbell racks, a power rack,
   rubber flooring and a few plants. Same person, same camera angle and lighting in both panels, whole
   body and equipment in view, correct anatomy and hands gripping the equipment naturally. Add
   {phases.motion}.
   Under each photo, a lightly tinted box (blue on the left, green on the right) with 3-4 short bullet
   points describing how to get into, and what to do in, that position.
3. A bottom row of three equal columns, each with a dark-navy heading bar:
   - "MUSCLES WORKED": grey front and back anatomy figures with the worked muscles highlighted in
     red, orange and blue, and a color-coded legend (common name with the anatomical name in brackets).
   - "KEY FORM TIPS": 5 short tips, each with a green check-mark icon.
   - "COMMON MISTAKES": 3 mistakes, each with a small photo of the same person making the mistake,
     a red X icon, a bold short title and a one-line fix.
4. A slim light-blue "PRO TIPS" strip along the bottom with 3-4 short tips and simple icons{tips_extra}.

Make the instructions accurate and safe; they're for someone who isn't an expert.
"""
