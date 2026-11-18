"""Plan documents: hand a profile's plan to an AI and take its edited version back.

The flow:

1. ``build_prompt`` writes a prompt with the person's request, their current plan
   (already in the plan-document format), recent performance, their equipment and
   the whole exercise library, plus the rules for the document to send back.
2. The person pastes the AI's reply. ``read_document`` finds the JSON in it,
   ``validate_document`` checks it against the library, and ``diff_plans`` shows
   what would change.
3. ``apply_plan`` replaces the profile's plan with the document and records a
   ``PlanRevision`` so the change can be undone (undo applies the previous plan).

A plan document is the complete plan: workouts left out of it are removed.
Recorded sessions are never touched; they hold their own snapshots.

A plan is either weekly (``plan_weeks`` 1: the same workouts every week) or a multi-week
program (e.g. 6 weeks) in which each workout lists the plan ``weeks`` it runs in. After the
last week it starts again at week 1.
"""

import difflib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Equipment,
    Exercise,
    LoadType,
    PlanRevision,
    Profile,
    SessionStatus,
    TrackingType,
    WorkoutSession,
    WorkoutTemplate,
    WorkoutTemplateExercise,
    utcnow,
)
from app.services import progression
from app.services.plan import (
    MAX_PLAN_WEEKS,
    WEEKDAYS,
    get_app_settings,
    normalize_weeks,
    plan_start_for,
    plan_week,
    program_week,
    weeks_overlap,
    weeks_text,
)
from app.services.prescription import Prescription, format_prescription, parse_prescription
from app.serializers import summarize_sets
from app.services.sessions import default_targets

FORMAT = "workout-pal-plan/v2"
# v1 documents (no plan_weeks / weeks) are weekly plans and still read fine.
_KNOWN_FORMATS = {FORMAT, "workout-pal-plan/v1"}

LOAD_TYPE_TEXT = {
    LoadType.per_dumbbell: "lb per dumbbell (two dumbbells)",
    LoadType.single_dumbbell: "lb, one dumbbell",
    LoadType.plates_loaded: "lb of plates on the cable stack",
    LoadType.added_plates: "lb of plates added to the Smith bar (bar not included)",
    LoadType.bodyweight: "bodyweight (weight = optional added lb, usually 0)",
    LoadType.none: "no weight (use null)",
}


# --------------------------------------------------------------------------- document schema


class DocExercise(BaseModel):
    model_config = ConfigDict(extra="ignore")

    exercise_id: str = Field(min_length=1, max_length=20)
    exercise_name: str | None = Field(None, max_length=200)
    sets: int = Field(ge=1, le=20)
    sets_first_weeks: int | None = Field(None, ge=1, le=20)
    reps_or_duration: str = Field(min_length=1, max_length=50)
    weight: float | None = Field(None, ge=0, le=1000)
    rest_seconds: int | None = Field(None, ge=0, le=900)
    notes: str | None = Field(None, max_length=1000)
    skipped: bool = False


_WEEK_RANGE = re.compile(r"^(\d+)\s*(?:-|–|to)\s*(\d+)$")
_EVERY_WEEK = {"", "all", "every", "every week", "all weeks", "each week", "null", "none"}


def _parse_weeks(value: object) -> object:
    """Accept [1, 2, 3], 2, "1-3", "weeks 1, 3, 5" or "every week" (= null)."""
    if isinstance(value, int) and not isinstance(value, bool):
        return [value]
    if not isinstance(value, str):
        return value
    text = value.strip().lower()
    if text in _EVERY_WEEK:
        return None
    text = re.sub(r"^weeks?\s*", "", text)
    weeks: list[int] = []
    for part in re.split(r"\s*(?:,|\band\b|&)\s*", text):
        if not part:
            continue
        if part.isdigit():
            weeks.append(int(part))
        elif m := _WEEK_RANGE.match(part):
            lo, hi = sorted((int(m.group(1)), int(m.group(2))))
            if hi > 99:
                raise ValueError(f"weeks '{value}' go past week {MAX_PLAN_WEEKS}, the longest a plan can be")
            weeks.extend(range(lo, hi + 1))  # weeks past the plan's end are reported by validation
        else:
            raise ValueError(f"can't read weeks '{value}' (use a list of week numbers like [1, 2, 3], or null)")
    if not weeks:
        raise ValueError(f"can't read weeks '{value}' (use a list of week numbers like [1, 2, 3], or null)")
    return weeks


class DocWorkout(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=100)
    day: str | None = Field(None, max_length=20)
    weeks: list[Annotated[int, Field(ge=1, le=MAX_PLAN_WEEKS)]] | None = Field(None, max_length=100)
    notes: str | None = Field(None, max_length=2000)
    exercises: list[DocExercise] = Field(default_factory=list, max_length=40)

    @field_validator("weeks", mode="before")
    @classmethod
    def _read_weeks(cls, value: object) -> object:
        return _parse_weeks(value)


class PlanDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    format: str | None = None
    summary: str | None = Field(None, max_length=4000)
    plan_weeks: int | None = Field(None, ge=1, le=MAX_PLAN_WEEKS)
    workouts: list[DocWorkout] = Field(max_length=7 * MAX_PLAN_WEEKS)


# --------------------------------------------------------------------------- export


def _load_templates(db: Session, profile_id: int) -> list[WorkoutTemplate]:
    templates = db.scalars(
        select(WorkoutTemplate)
        .where(WorkoutTemplate.profile_id == profile_id)
        .options(selectinload(WorkoutTemplate.exercises).selectinload(WorkoutTemplateExercise.exercise)
                 .selectinload(Exercise.equipment))
    ).all()
    # Grouped by first week, then by day, so multi-week plans read week by week.
    return sorted(templates, key=lambda t: (min(t.weeks or [0]), t.weekday is None, t.weekday or 0, t.name))


def _te_reps(te: WorkoutTemplateExercise) -> str:
    return (
        format_prescription(te.target_rep_min, te.target_rep_max, te.target_duration_min,
                            te.target_duration_max, te.per_side)
        or te.target_text
        or "10"
    )


def export_plan(db: Session, profile_id: int) -> dict:
    """The profile's current plan as a plan document."""
    workouts = []
    for t in _load_templates(db, profile_id):
        workouts.append({
            "name": t.name,
            "day": WEEKDAYS[t.weekday] if t.weekday is not None else None,
            "weeks": t.weeks or None,
            "notes": t.notes,
            "exercises": [
                {
                    "exercise_id": te.exercise_id,
                    "exercise_name": te.exercise.name,
                    "sets": te.target_sets,
                    "sets_first_weeks": te.ramp_sets,
                    "reps_or_duration": _te_reps(te),
                    "weight": te.suggested_weight if te.exercise.load_type != LoadType.none else None,
                    "rest_seconds": te.default_rest_seconds,
                    "notes": te.notes,
                    "skipped": te.skipped,
                }
                for te in t.exercises
            ],
        })
    plan_weeks = get_app_settings(db, profile_id).plan_weeks
    return {"format": FORMAT, "summary": None, "plan_weeks": plan_weeks, "workouts": workouts}


# --------------------------------------------------------------------------- prompt


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:g}"


def _equipment_lines(db: Session) -> list[str]:
    lines = []
    for eq in db.scalars(select(Equipment).order_by(Equipment.name)):
        if eq.equipment_type == "dumbbell":
            weights = ", ".join(_fmt(w) for w in progression.weight_options(eq) or [])
            lines.append(f"- {eq.name}: pairs of {weights} lb (only these weights exist)")
        elif eq.equipment_type in ("cable", "smith_machine"):
            lines.append(f"- {eq.name}: plates in {_fmt(eq.weight_increment or 5)} lb steps")
        else:
            lines.append(f"- {eq.name}")
    return lines


def _library_lines(db: Session) -> list[str]:
    exercises = db.scalars(
        select(Exercise).where(Exercise.enabled.is_(True))
        .options(selectinload(Exercise.equipment))
        .order_by(Exercise.primary_muscle_group, Exercise.name)
    ).all()
    lines: list[str] = []
    group = object()
    for ex in exercises:
        if ex.primary_muscle_group != group:
            group = ex.primary_muscle_group
            lines.append(f"\n## {group or 'Other'}")
        flags = []
        if ex.tracking_type == TrackingType.cardio:
            flags.append("cardio: minutes")
        elif ex.tracking_type == TrackingType.timed:
            flags.append("timed: seconds")
        if ex.unilateral:
            flags.append("each side")
        if ex.pulley_ratio:
            flags.append(f"{ex.pulley_ratio} pulley")
        equipment = ex.equipment_detail or (ex.equipment.name if ex.equipment else "")
        weight = LOAD_TYPE_TEXT.get(ex.load_type, ex.load_type)
        tail = f" [{', '.join(flags)}]" if flags else ""
        lines.append(f"{ex.id} | {ex.name} | {equipment} | {weight}{tail}")
    return lines


def _recent_lines(db: Session, profile_id: int, exercise_ids: list[str]) -> list[str]:
    lines = []
    for ex_id in dict.fromkeys(exercise_ids):
        last = progression.previous_performance(db, ex_id, profile_id)
        if last is None:
            continue
        done = [s for s in last.sets if s.completed]
        lines.append(
            f"- {ex_id} {last.exercise_name}: {last.session.performed_on.isoformat()} "
            f"{summarize_sets(done, last.tracking_type, last.load_type)} (target {last.target_text or '-'})"
        )
    return lines


def _example_document() -> str:
    """A small multi-week example: weekly plans are the same thing with plan_weeks 1 and weeks null."""
    def bench(sets: int, reps: str, weight: float, notes: str | None) -> dict:
        return {
            "exercise_id": "EX0001",
            "exercise_name": "Flat dumbbell bench press",
            "sets": sets,
            "sets_first_weeks": None,
            "reps_or_duration": reps,
            "weight": weight,
            "rest_seconds": 120,
            "notes": notes,
        }

    return json.dumps({
        "format": FORMAT,
        "summary": "A 4-week plan: Upper A builds over weeks 1-3, then week 4 is an easier deload week.",
        "plan_weeks": 4,
        "workouts": [
            {"name": "Upper A · Weeks 1-3", "day": "Monday", "weeks": [1, 2, 3], "notes": None,
             "exercises": [bench(3, "8-10", 25, "Pause 1 second at the bottom.")]},
            {"name": "Upper A · Deload", "day": "Monday", "weeks": [4], "notes": "Easy week to recover.",
             "exercises": [bench(2, "8-10", 25, "Stop 2-3 reps short of failure.")]},
        ],
    }, indent=2, ensure_ascii=False)


def build_prompt(db: Session, profile: Profile, request: str, today: date | None = None) -> str:
    today = today or date.today()
    settings = get_app_settings(db, profile.id)
    week = program_week(settings, today)
    plan = export_plan(db, profile.id)
    plan_ids = [e["exercise_id"] for w in plan["workouts"] for e in w["exercises"]]
    recent_count = db.scalar(
        select(func.count()).select_from(WorkoutSession).where(
            WorkoutSession.profile_id == profile.id,
            WorkoutSession.status == SessionStatus.completed,
            WorkoutSession.performed_on >= today - timedelta(weeks=4),
        )
    ) or 0
    recent = _recent_lines(db, profile.id, plan_ids)

    if plan["workouts"]:
        plan_intro = "Their current plan, in the exact format you will send back:"
    else:
        plan_intro = ("They have no plan yet, so build one from scratch. "
                      "This is the (empty) document you will fill in:")
    if not plan["workouts"]:
        plan_kind = "none yet"
    elif settings.plan_weeks == 1:
        plan_kind = "a weekly plan (the same workouts every week)"
    else:
        plan_kind = (f"a {settings.plan_weeks}-week plan; this is week {plan_week(settings, today)} of "
                     f"{settings.plan_weeks} (after week {settings.plan_weeks} it starts again at week 1)")
    ramp = settings.ramp_weeks
    ramp_note = f" (the first {ramp} weeks use the lighter \"sets_first_weeks\" count)" if ramp else ""
    first_weeks_rule = (
        f'"sets_first_weeks": sets for their first {ramp} program weeks (counted from when they\n'
        '  started training, not from the start of the plan), or null to use "sets". In a multi-week\n'
        '  plan, write lighter early weeks directly into those weeks instead and use null.'
        if ramp else '"sets_first_weeks": not used right now (their ramp-in is off). Keep the value\n'
        '  an exercise already has, and use null for new exercises.'
    )

    sections = [
        f"""You are a knowledgeable, safety-minded strength coach helping {profile.name} change their
home-gym workout plan. They are not an expert, so explain your choices in plain language.
Their app (Workout Pal) will import the plan document you produce.

# What {profile.name} wants changed

\"\"\"
{request.strip()}
\"\"\"

# What the app can do

The app runs two kinds of plan, and you can switch between them:

- A weekly plan: the same workouts every week ("plan_weeks": 1).
- A multi-week program of 2 to {MAX_PLAN_WEEKS} weeks (for example a 6-week plan) in which the workouts,
  exercises, sets and reps change from week to week: building volume, then intensity, a lighter
  deload week, a different focus each week, and so on. After the last week it starts again at
  week 1, so it can also be a repeating cycle (e.g. alternating an A week and a B week).

Build a multi-week program when they ask for one (e.g. "a 6-week plan"), or when what they ask
for only works across weeks (progression over several weeks, periodization, a deload, "something
different each week"). Otherwise keep their current structure. If a multi-week program would
clearly serve them better, you may suggest it, but ask before switching.

# How to work

1. If the request is unclear, or mentions pain or injury, ask your questions first and wait for
   the answers. (Pain that is sharp or lasting is a reason to see a professional; say so.)
2. When you are ready, briefly explain what you changed and why (for a multi-week program, give
   a short week-by-week overview), then give the complete new plan as ONE ```json code block in
   the format described at the end.
3. Keep everything they didn't ask to change exactly as it is.

# About {profile.name}

- Current plan: {plan_kind}
- Program week: {week if week is not None else "not started yet"}{ramp_note}
- Workouts completed in the last 4 weeks: {recent_count}
- All weights are in pounds (lb).

# Equipment in the gym

""" + "\n".join(_equipment_lines(db)),
        f"""# Current plan

{plan_intro}

```json
{json.dumps(plan, indent=2, ensure_ascii=False)}
```""",
    ]
    if recent:
        sections.append("# Most recent performance of the exercises in the plan\n\n"
                        "Use this to choose realistic weights.\n\n" + "\n".join(recent))
    sections.append(
        "# Exercise library\n\n"
        "These are the ONLY exercises available. Use their exact IDs.\n"
        "Columns: ID | name | equipment | how the weight is measured [notes]"
        + "\n".join(_library_lines(db))
    )
    sections.append(f"""# The plan document to send back

Reply with one ```json code block containing the COMPLETE plan: every workout in every week,
including the ones you didn't change. Any workout left out is deleted from the app. This example
is a 4-week plan; a weekly plan looks the same with "plan_weeks": 1 and "weeks": null.

```json
{_example_document()}
```

Rules:
- "format": always "{FORMAT}".
- "summary": one or two plain sentences describing the change (shown in the app's history).
- "plan_weeks": 1 for the same workouts every week, or 2-{MAX_PLAN_WEEKS} for a multi-week program.
  After the last week the plan starts again at week 1.
- "workouts": "name" must be unique, so a workout that changes between weeks needs one entry per
  version, each with its own name (e.g. "Upper A · Weeks 1-3" and "Upper A · Deload"). "day" is
  Monday to Sunday, or null for a workout that isn't scheduled.
- "weeks": the plan weeks the workout runs in, e.g. [1, 2, 3] or [4]; null means every week (always
  use null in a weekly plan). A workout that is identical in several weeks is listed once with all
  of those weeks. A day can hold different workouts in different weeks, but never two workouts in
  the same week. Make sure every week has the workouts it should have.
- "exercise_id" must come from the exercise library above. Also give "exercise_name" so
  mistakes can be caught. Exercises are done in the order listed.
- "sets": working sets (1-20){f" from program week {ramp + 1} on" if ramp else ""}.
- {first_weeks_rule}
- "reps_or_duration": reps like "8-10" or "12", per side like "10/side", holds like "30-45 sec",
  cardio like "20-30 min". Exercises marked "cardio: minutes" need minutes and those marked
  "timed: seconds" need seconds.
- "weight": the starting weight in the exercise's convention from the library (for example lb
  PER dumbbell, or lb of plates on a cable stack). Dumbbell weights must be ones that exist.
  Use null for cardio. Bodyweight exercises use 0 unless extra weight is added.
  The app uses this weight the next time they do the exercise. After that it prefills what they
  actually lifted and suggests the next weight up once they reach the top of the rep range (or a
  lighter one if they fall well short), so weights you give for later weeks won't override what
  they lift. Drive week-to-week progression with sets and rep ranges (e.g. 3 x 10-12, then
  4 x 8-10, then 4 x 6-8) and make deload weeks easier with fewer sets, not a lower weight
  (the app would prefill their usual weight anyway). Give each version of an exercise the same weight.
- "rest_seconds": rest between sets (0-900).
- "notes": optional short coaching cue, or null.
- "skipped": true keeps an exercise in the plan but leaves it out of workouts for now
  (keep existing values; use false for anything new).""")
    return "\n\n".join(sections) + "\n"


# --------------------------------------------------------------------------- reading the AI's answer


class DocumentError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _loads(text: str) -> object:
    # Chat apps sometimes "smarten" quotes; JSON needs straight ones.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(text.replace("“", '"').replace("”", '"'))


def read_document(text: str) -> PlanDocument:
    """Find and parse the plan JSON in a pasted reply (code fences and chatter allowed)."""
    # Last fenced block first (a reply may quote the old plan before the new one),
    # then everything between the first "{" and the last "}".
    candidates = [m.group(1) for m in _FENCE.finditer(text)][::-1]
    if "{" in text and "}" in text:
        candidates.append(text[text.index("{"): text.rindex("}") + 1])
    data = None
    syntax_error = None
    for candidate in candidates:
        try:
            data = _loads(candidate)
            break
        except json.JSONDecodeError as exc:
            syntax_error = exc
    if data is None:
        if "{" in text and syntax_error is None:
            raise DocumentError(["The JSON looks cut off (it never closes). "
                                 "Ask the AI to resend the complete JSON block."])
        if syntax_error is not None:
            raise DocumentError([f"The JSON is malformed (line {syntax_error.lineno}: {syntax_error.msg}). "
                                 "Ask the AI to resend the complete JSON block."])
        raise DocumentError(["Couldn't find a JSON plan in what you pasted. "
                             "Paste the AI's whole reply, including the ```json block."])
    if not isinstance(data, dict):
        raise DocumentError(["The JSON should be an object with a \"workouts\" list."])
    try:
        return PlanDocument.model_validate(data)
    except ValidationError as exc:
        raise DocumentError([_describe_error(err, data) for err in exc.errors()]) from exc


def _describe_error(err: dict, data: dict) -> str:
    """Turn a pydantic error location into words, using workout and exercise names."""
    parts: list[str] = []
    node: object = data
    loc = list(err["loc"])
    i = 0
    while i < len(loc):
        key = loc[i]
        if key == "workouts" and i + 1 < len(loc) and isinstance(loc[i + 1], int):
            idx = loc[i + 1]
            workout = node["workouts"][idx] if isinstance(node, dict) else {}
            name = workout.get("name") if isinstance(workout, dict) else None
            parts.append(f"workout '{name}'" if name else f"workout #{idx + 1}")
            node, i = workout, i + 2
        elif key == "exercises" and i + 1 < len(loc) and isinstance(loc[i + 1], int):
            idx = loc[i + 1]
            ex = node["exercises"][idx] if isinstance(node, dict) else {}
            label = (ex.get("exercise_name") or ex.get("exercise_id")) if isinstance(ex, dict) else None
            parts.append(f"exercise #{idx + 1}" + (f" ({label})" if label else ""))
            node, i = ex, i + 2
        else:
            parts.append(str(key))
            node = node.get(key) if isinstance(node, dict) else None
            i += 1
    where = " › ".join(parts) or "document"
    return f"{where}: {err['msg']}"


# --------------------------------------------------------------------------- validation


@dataclass
class PlanItem:
    exercise: Exercise
    sets: int
    sets_first_weeks: int | None
    prescription: Prescription
    weight: float | None
    rest_seconds: int
    notes: str | None
    skipped: bool = False


@dataclass
class PlanWorkout:
    name: str
    weekday: int | None
    notes: str | None
    items: list[PlanItem]
    weeks: list[int] | None = None  # None = every week


@dataclass
class ValidatedPlan:
    summary: str | None
    plan_weeks: int = 1
    workouts: list[PlanWorkout] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


_DAY_ALIASES = {d.lower(): i for i, d in enumerate(WEEKDAYS)} | {d[:3].lower(): i for i, d in enumerate(WEEKDAYS)}
_UNSCHEDULED = {"", "none", "null", "unscheduled", "any", "flexible"}
_SAME_NAME = 0.6


def _clean(text: str | None) -> str | None:
    text = (text or "").strip()
    return text or None


def validate_document(db: Session, doc: PlanDocument) -> ValidatedPlan:
    used_weeks = sorted({n for w in doc.workouts for n in (w.weeks or [])})
    plan_weeks = doc.plan_weeks or max(used_weeks, default=1)
    plan = ValidatedPlan(summary=_clean(doc.summary), plan_weeks=plan_weeks)
    if doc.format and doc.format not in _KNOWN_FORMATS:
        plan.warnings.append(f"Unexpected format '{doc.format}'; reading it as {FORMAT}")
    if not doc.workouts:
        plan.errors.append("The plan has no workouts; applying it would delete the whole plan.")
        return plan
    beyond = [n for n in used_weeks if n > plan_weeks]
    if beyond:
        plan.errors.append(
            f"plan_weeks is {plan_weeks}, but some workouts are in week {', '.join(map(str, beyond))}. "
            "Raise plan_weeks or fix those workouts' weeks."
        )

    library = {e.id: e for e in db.scalars(select(Exercise).options(selectinload(Exercise.equipment)))}
    names: dict[str, str] = {}
    scheduled: list[tuple[int, list[int] | None, str]] = []  # (weekday, weeks, name)
    for w in doc.workouts:
        name = w.name.strip()
        label = f"'{name}'"
        if name.lower() in names:
            plan.errors.append(f"Two workouts are named {label}; names must be unique.")
        names[name.lower()] = name
        if w.weeks is not None and not w.weeks:
            plan.errors.append(f'{label} has "weeks": [] (no weeks). List the weeks it runs in, '
                               'or use null for every week.')
        weeks = normalize_weeks([n for n in (w.weeks or []) if n <= plan_weeks] or None, plan_weeks)

        weekday = None
        day = (w.day or "").strip().lower()
        if day not in _UNSCHEDULED:
            weekday = _DAY_ALIASES.get(day)
            if weekday is None:
                plan.errors.append(f"{label}: unknown day '{w.day}' (use Monday to Sunday, or null).")
            else:
                for other_day, other_weeks, other_name in scheduled:
                    if other_day == weekday and weeks_overlap(other_weeks, weeks):
                        shared = _shared_weeks(other_weeks, weeks, plan_weeks)
                        when = f" in {weeks_text(shared).lower()}" if plan_weeks > 1 else ""
                        plan.errors.append(
                            f"{WEEKDAYS[weekday]} has two workouts{when}: '{other_name}' and {label}."
                        )
                        break
                else:
                    scheduled.append((weekday, weeks, name))

        if not w.exercises:
            plan.warnings.append(f"{label} has no exercises.")
        seen: set[str] = set()
        items: list[PlanItem] = []
        for n, e in enumerate(w.exercises, start=1):
            ex_id = e.exercise_id.strip().upper()
            where = f"{label} exercise #{n} ({e.exercise_name or ex_id})"
            exercise = library.get(ex_id)
            if exercise is None:
                plan.errors.append(f"{where}: {ex_id} isn't in the exercise library.")
                continue
            if not exercise.enabled:
                plan.errors.append(f"{where}: {exercise.name} is marked unavailable in the library.")
                continue
            if e.exercise_name and difflib.SequenceMatcher(
                None, e.exercise_name.lower(), exercise.name.lower()
            ).ratio() < _SAME_NAME:
                plan.warnings.append(
                    f"{where}: {ex_id} is '{exercise.name}' in the library, not '{e.exercise_name}'. "
                    "Check the AI picked the exercise it meant."
                )
            if ex_id in seen:
                plan.warnings.append(f"{label}: {exercise.name} is listed more than once.")
            seen.add(ex_id)

            p = parse_prescription(e.reps_or_duration)
            if p is None:
                plan.errors.append(f"{where}: can't read reps_or_duration '{e.reps_or_duration}' "
                                   "(use e.g. \"8-10\", \"10/side\", \"30-45 sec\", \"20-30 min\").")
                continue
            if exercise.tracking_type == TrackingType.cardio and not p.is_duration:
                plan.errors.append(f"{where}: cardio needs a duration like \"20-30 min\", not '{p.text}'.")
                continue
            if exercise.tracking_type == TrackingType.timed and not p.is_duration:
                plan.warnings.append(f"{where}: {exercise.name} is usually timed; '{p.text}' will be tracked as reps.")

            weight = _check_weight(exercise, e.weight, where, plan.warnings)
            rest = e.rest_seconds if e.rest_seconds is not None else default_targets(exercise).rest_seconds
            items.append(PlanItem(exercise, e.sets, e.sets_first_weeks, p, weight, rest, _clean(e.notes), e.skipped))
        plan.workouts.append(PlanWorkout(name, weekday, _clean(w.notes), items, weeks))

    if plan_weeks > 1 and scheduled:
        if all(weeks is None for _, weeks, _ in scheduled):
            plan.warnings.append(f"This is a {plan_weeks}-week plan, but every workout runs every week, "
                                 "so all the weeks are the same.")
        for n in range(1, plan_weeks + 1):
            if not any(weeks is None or n in weeks for _, weeks, _ in scheduled):
                plan.warnings.append(f"Week {n} has no scheduled workouts (a rest week).")
    return plan


def _shared_weeks(a: list[int] | None, b: list[int] | None, plan_weeks: int) -> list[int] | None:
    every = set(range(1, plan_weeks + 1))
    return normalize_weeks(sorted(set(a or every) & set(b or every)), plan_weeks)


def _check_weight(exercise: Exercise, weight: float | None, where: str, warnings: list[str]) -> float | None:
    if exercise.load_type == LoadType.none:
        return None
    if exercise.load_type not in progression.WEIGHTED:
        return weight
    if weight is None:
        warnings.append(f"{where}: no starting weight; you'll pick one during the first workout.")
        return None
    options = progression.weight_options(exercise.equipment)
    if options and weight not in options:
        nearest = min(options, key=lambda w: (abs(w - weight), w))
        warnings.append(f"{where}: there are no {weight:g} lb dumbbells; using {nearest:g} lb.")
        return nearest
    return weight


# --------------------------------------------------------------------------- preview


def plan_to_document(plan: ValidatedPlan) -> dict:
    return {
        "format": FORMAT,
        "summary": plan.summary,
        "plan_weeks": plan.plan_weeks,
        "workouts": [
            {
                "name": w.name,
                "day": WEEKDAYS[w.weekday] if w.weekday is not None else None,
                "weeks": w.weeks,
                "notes": w.notes,
                "exercises": [
                    {
                        "exercise_id": i.exercise.id,
                        "exercise_name": i.exercise.name,
                        "sets": i.sets,
                        "sets_first_weeks": i.sets_first_weeks,
                        "reps_or_duration": i.prescription.text,
                        "weight": i.weight,
                        "rest_seconds": i.rest_seconds,
                        "notes": i.notes,
                        "skipped": i.skipped,
                    }
                    for i in w.items
                ],
            }
            for w in plan.workouts
        ],
    }


def _targets(text: str) -> tuple | None:
    p = parse_prescription(text)
    return (p.rep_min, p.rep_max, p.duration_min, p.duration_max, p.per_side) if p else None


def _exercise_changes(old: dict, new: dict) -> list[str]:
    changes = []
    if old.get("skipped", False) != new.get("skipped", False):
        changes.append("now skipped" if new.get("skipped") else "no longer skipped")
    if old["sets"] != new["sets"]:
        changes.append(f"sets {old['sets']} → {new['sets']}")
    if (old["sets_first_weeks"] or old["sets"]) != (new["sets_first_weeks"] or new["sets"]):
        changes.append(f"first-weeks sets {old['sets_first_weeks'] or old['sets']} → "
                       f"{new['sets_first_weeks'] or new['sets']}")
    if _targets(old["reps_or_duration"]) != _targets(new["reps_or_duration"]):
        changes.append(f"{old['reps_or_duration']} → {new['reps_or_duration']}")
    if old["weight"] != new["weight"]:
        changes.append(f"weight {_fmt(old['weight'])} → {_fmt(new['weight'])} lb")
    if old["rest_seconds"] != new["rest_seconds"]:
        changes.append(f"rest {old['rest_seconds']}s → {new['rest_seconds']}s")
    if (old["notes"] or None) != (new["notes"] or None):
        changes.append("notes changed")
    return changes


def diff_plans(current: dict, proposed: dict) -> list[dict]:
    """Workout-by-workout changes from `current` to `proposed` (both plan documents)."""
    before = {w["name"].lower(): w for w in current["workouts"]}
    result = []
    for w in proposed["workouts"]:
        old = before.pop(w["name"].lower(), None)
        weeks = w.get("weeks") or None
        entry = {"name": w["name"], "day": w["day"], "previous_day": old["day"] if old else None,
                 "weeks": weeks, "weeks_text": weeks_text(weeks),
                 "status": "added" if old is None else "unchanged", "notes": [], "exercises": []}
        old_items: dict[str, list[dict]] = defaultdict(list)
        for e in (old["exercises"] if old else []):
            old_items[e["exercise_id"]].append(e)
        matched_order = []
        for e in w["exercises"]:
            prev = old_items[e["exercise_id"]].pop(0) if old_items[e["exercise_id"]] else None
            if prev is None:
                status, changes = "added", []
            else:
                matched_order.append(e["exercise_id"])
                changes = _exercise_changes(prev, e)
                status = "changed" if changes else "unchanged"
            entry["exercises"].append({"exercise_id": e["exercise_id"], "exercise_name": e["exercise_name"],
                                       "status": status, "changes": changes,
                                       "sets": e["sets"], "reps_or_duration": e["reps_or_duration"],
                                       "weight": e["weight"]})
        for leftovers in old_items.values():
            for e in leftovers:
                entry["exercises"].append({"exercise_id": e["exercise_id"], "exercise_name": e["exercise_name"],
                                           "status": "removed", "changes": [], "sets": e["sets"],
                                           "reps_or_duration": e["reps_or_duration"], "weight": e["weight"]})
        if old is not None:
            if old["day"] != w["day"]:
                entry["notes"].append(f"Moved from {old['day'] or 'unscheduled'} to {w['day'] or 'unscheduled'}")
            old_weeks = old.get("weeks") or None
            if old_weeks != weeks:
                entry["notes"].append(f"Now {weeks_text(weeks).lower()} (was {weeks_text(old_weeks).lower()})")
            old_order = [e["exercise_id"] for e in old["exercises"] if e["exercise_id"] in matched_order]
            if old_order != matched_order:
                entry["notes"].append("Exercises reordered")
            if (old["notes"] or None) != (w["notes"] or None):
                entry["notes"].append("Workout notes changed")
            if entry["notes"] or any(e["status"] != "unchanged" for e in entry["exercises"]):
                entry["status"] = "changed"
        result.append(entry)
    for old in before.values():
        result.append({"name": old["name"], "day": None, "previous_day": old["day"],
                       "weeks": old.get("weeks") or None, "weeks_text": weeks_text(old.get("weeks")),
                       "status": "removed",
                       "notes": [], "exercises": [
                           {"exercise_id": e["exercise_id"], "exercise_name": e["exercise_name"],
                            "status": "removed", "changes": [], "sets": e["sets"],
                            "reps_or_duration": e["reps_or_duration"], "weight": e["weight"]}
                           for e in old["exercises"]]})
    return result


# --------------------------------------------------------------------------- applying


_KEEP = object()


def apply_plan(
    db: Session, profile_id: int, plan: ValidatedPlan, *, source: str = "document",
    restart_on: date | None = None, plan_start: date | None | object = _KEEP,
) -> PlanRevision:
    """Replace the profile's plan with `plan` (already validated) and record a revision. Commits.

    `restart_on` starts plan week 1 in that date's week (next week at the weekend); `plan_start`
    sets the plan start date directly (used by undo). The training start date, and with it the
    ramp-in, never changes here."""
    assert plan.ok
    settings = get_app_settings(db, profile_id)
    previous = export_plan(db, profile_id)
    if restart_on is not None:
        plan_start = plan_start_for(restart_on)
    if plan_start is not _KEEP:
        # Kept with the revision so undo can put the old plan week back.
        start = settings.plan_start_date
        previous["plan_start_date"] = start.isoformat() if start else None
        settings.plan_start_date = plan_start
    settings.plan_weeks = plan.plan_weeks
    templates = _load_templates(db, profile_id)
    existing = {t.name.lower(): t for t in templates}

    wanted = {w.name.lower() for w in plan.workouts}
    for t in templates:
        if t.name.lower() not in wanted:
            db.delete(t)  # recorded sessions keep their data; their template link becomes empty
    db.flush()

    now = utcnow()
    for w in plan.workouts:
        template = existing.get(w.name.lower())
        if template is None:
            template = WorkoutTemplate(profile_id=profile_id, name=w.name)
            db.add(template)
        template.name = w.name
        template.notes = w.notes
        template.weekday = w.weekday
        template.weeks = w.weeks

        reusable: dict[str, list[WorkoutTemplateExercise]] = defaultdict(list)
        for te in template.exercises:
            reusable[te.exercise_id].append(te)
        rows = []
        for order, item in enumerate(w.items, start=1):
            te = reusable[item.exercise.id].pop(0) if reusable[item.exercise.id] else None
            if te is None:
                te = WorkoutTemplateExercise(exercise=item.exercise)
                # A weight chosen for the plan beats older history, like a hand edit.
                te.suggested_weight_updated_at = now if item.weight is not None else None
            elif te.suggested_weight != item.weight:
                te.suggested_weight_updated_at = now
            p = item.prescription
            te.exercise_order = order
            te.target_sets = item.sets
            te.ramp_sets = item.sets_first_weeks
            te.target_text = p.text
            te.target_rep_min, te.target_rep_max = p.rep_min, p.rep_max
            te.target_duration_min, te.target_duration_max = p.duration_min, p.duration_max
            te.per_side = p.per_side or item.exercise.unilateral
            te.suggested_weight = item.weight
            te.default_rest_seconds = item.rest_seconds
            te.notes = item.notes
            te.skipped = item.skipped
            rows.append(te)
        template.exercises[:] = rows
        if template.id is not None and template.estimated_duration_minutes:
            template.estimated_duration_minutes = None  # a stale manual estimate would mislead
    db.flush()

    revision = PlanRevision(profile_id=profile_id, source=source, summary=plan.summary,
                            previous_plan=previous, new_plan=plan_to_document(plan))
    db.add(revision)
    db.commit()
    return revision


def latest_revision(db: Session, profile_id: int) -> PlanRevision | None:
    return db.scalar(
        select(PlanRevision).where(PlanRevision.profile_id == profile_id)
        .order_by(PlanRevision.created_at.desc(), PlanRevision.id.desc())
    )


def undo_revision(db: Session, revision: PlanRevision) -> PlanRevision:
    """Put back the plan from before `revision` (which must be the latest). Raises DocumentError."""
    plan = validate_document(db, PlanDocument.model_validate(revision.previous_plan))
    if not revision.previous_plan["workouts"]:
        # Undoing the very first plan: an empty plan is legitimate here.
        plan.errors = [e for e in plan.errors if "no workouts" not in e]
    if not plan.ok:
        raise DocumentError(plan.errors)
    plan.summary = f"Undid: {revision.summary}" if revision.summary else "Undid the previous change"
    revision.undone_at = utcnow()
    plan_start: date | None | object = _KEEP
    if "plan_start_date" in revision.previous_plan:  # the change restarted the plan at week 1
        start = revision.previous_plan["plan_start_date"]
        plan_start = date.fromisoformat(start) if start else None
    elif "program_start_date" in revision.previous_plan:  # older revisions moved the training start
        start = revision.previous_plan["program_start_date"]
        restored = date.fromisoformat(start) if start else None
        get_app_settings(db, revision.profile_id).program_start_date = restored
        plan_start = plan_start_for(restored) if restored else None
    return apply_plan(db, revision.profile_id, plan, source="undo", plan_start=plan_start)
