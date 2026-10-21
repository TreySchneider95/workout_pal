from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import LoadType, Side, TrackingType

Weight = Annotated[float, Field(ge=0, le=1000)]
Reps = Annotated[int, Field(ge=0, le=500)]
Seconds = Annotated[int, Field(ge=0, le=6 * 3600)]
Distance = Annotated[float, Field(ge=0, le=100)]
Speed = Annotated[float, Field(ge=0, le=25)]
SetCount = Annotated[int, Field(ge=1, le=20)]
RestSeconds = Annotated[int, Field(ge=0, le=900)]
PulleyRatio = Annotated[str, Field(pattern=r"^\d+:\d+$")]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- profiles


class ProfileOut(ORM):
    id: int
    name: str
    email: str | None


class ProfileUpdate(BaseModel):
    email: Annotated[str, Field(max_length=254, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$")] | None = None

    @field_validator("email", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


# --------------------------------------------------------------------------- equipment


class EquipmentOut(ORM):
    id: int
    slug: str
    name: str
    equipment_type: str
    weight_increment: float | None
    available_weights: list[float] | None
    notes: str | None


class EquipmentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    weight_increment: Annotated[float, Field(gt=0, le=100)] | None = None
    available_weights: list[Weight] | None = None
    notes: str | None = None

    @field_validator("available_weights")
    @classmethod
    def _sorted_unique(cls, v: list[float] | None) -> list[float] | None:
        return sorted(set(v)) if v else v


# --------------------------------------------------------------------------- exercises


class ExerciseOut(BaseModel):
    id: str
    name: str
    primary_muscle_group: str | None
    secondary_muscles: list[str]
    equipment_id: int | None
    equipment_name: str | None
    equipment_detail: str | None
    attachment: str | None
    tracking_type: TrackingType
    load_type: LoadType
    pulley_ratio: str | None
    unilateral: bool
    starting_weight: float | None
    image_url: str | None
    thumb_url: str | None
    notes: str | None
    enabled: bool
    is_custom: bool
    weight_options: list[float] | None
    weight_increment: float | None
    scheduled_in: list[str] = []


class ExerciseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    primary_muscle_group: str | None = Field(None, max_length=50)
    secondary_muscles: list[str] = []
    equipment_id: int | None = None
    equipment_detail: str | None = Field(None, max_length=200)
    attachment: str | None = Field(None, max_length=200)
    tracking_type: TrackingType = TrackingType.strength
    load_type: LoadType = LoadType.per_dumbbell
    pulley_ratio: PulleyRatio | None = None
    unilateral: bool = False
    starting_weight: Weight | None = None
    notes: str | None = None


class ExerciseUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    primary_muscle_group: str | None = Field(None, max_length=50)
    secondary_muscles: list[str] | None = None
    equipment_id: int | None = None
    equipment_detail: str | None = Field(None, max_length=200)
    attachment: str | None = Field(None, max_length=200)
    tracking_type: TrackingType | None = None
    load_type: LoadType | None = None
    pulley_ratio: PulleyRatio | None = None
    unilateral: bool | None = None
    starting_weight: Weight | None = None
    notes: str | None = None
    enabled: bool | None = None


class ExerciseHistoryEntry(BaseModel):
    session_id: int
    session_name: str
    performed_on: date
    load_type: LoadType
    pulley_ratio: str | None
    sets: list["SetOut"]
    top_weight: float | None
    total_reps: int
    volume: float


class ExerciseProgressPoint(BaseModel):
    performed_on: date
    session_id: int
    top_weight: float | None
    best_reps: int | None
    total_reps: int
    volume: float
    total_duration: int | None
    total_distance: float | None


class ExerciseProgress(BaseModel):
    exercise_id: str
    sessions: int
    best_weight: float | None
    best_weight_reps: int | None
    best_weight_date: date | None
    total_volume: float
    total_reps: int
    points: list[ExerciseProgressPoint]
    history: list[ExerciseHistoryEntry]


# --------------------------------------------------------------------------- templates


class ExerciseBrief(BaseModel):
    id: str
    name: str
    primary_muscle_group: str | None
    tracking_type: TrackingType
    load_type: LoadType
    pulley_ratio: str | None
    unilateral: bool
    thumb_url: str | None
    image_url: str | None
    enabled: bool
    equipment_name: str | None


class TemplateExerciseOut(BaseModel):
    id: int
    exercise: ExerciseBrief
    exercise_order: int
    ramp_sets: int | None
    target_sets: int
    planned_sets: int
    target_text: str | None
    target_rep_min: int | None
    target_rep_max: int | None
    target_duration_min: int | None
    target_duration_max: int | None
    per_side: bool
    suggested_weight: float | None
    default_rest_seconds: int
    notes: str | None
    skipped: bool


class TemplateOut(BaseModel):
    id: int
    name: str
    weekday: int | None
    weekday_name: str | None
    estimated_duration_minutes: int
    estimated_duration_override: int | None
    notes: str | None
    exercise_count: int
    exercises: list[TemplateExerciseOut]


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    weekday: Annotated[int, Field(ge=0, le=6)] | None = None
    notes: str | None = None
    copy_from_template_id: int | None = None


class TemplateUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    weekday: Annotated[int, Field(ge=0, le=6)] | None = None
    unschedule: bool = False  # set True to remove the template from the week
    estimated_duration_minutes: Annotated[int, Field(ge=0, le=600)] | None = None
    notes: str | None = None


class TargetFields(BaseModel):
    target_rep_min: Reps | None = None
    target_rep_max: Reps | None = None
    target_duration_min: Seconds | None = None
    target_duration_max: Seconds | None = None

    @model_validator(mode="after")
    def _ranges(self):  # noqa: ANN202
        if (
            self.target_rep_min is not None
            and self.target_rep_max is not None
            and self.target_rep_min > self.target_rep_max
        ):
            raise ValueError("target_rep_min cannot exceed target_rep_max")
        if (
            self.target_duration_min is not None
            and self.target_duration_max is not None
            and self.target_duration_min > self.target_duration_max
        ):
            raise ValueError("target_duration_min cannot exceed target_duration_max")
        return self


class TemplateExerciseCreate(TargetFields):
    exercise_id: str
    target_sets: SetCount = 3
    ramp_sets: SetCount | None = None
    per_side: bool | None = None
    suggested_weight: Weight | None = None
    default_rest_seconds: RestSeconds | None = None
    notes: str | None = None


class TemplateExerciseUpdate(TargetFields):
    target_sets: SetCount | None = None
    ramp_sets: SetCount | None = None
    per_side: bool | None = None
    suggested_weight: Weight | None = None
    default_rest_seconds: RestSeconds | None = None
    notes: str | None = None
    skipped: bool | None = None


class ReorderRequest(BaseModel):
    template_exercise_ids: list[int] = Field(min_length=1)


# --------------------------------------------------------------------------- sessions


class SetOut(ORM):
    id: int
    set_number: int
    side: Side | None
    weight: float | None
    repetitions: int | None
    duration_seconds: int | None
    distance: float | None
    speed: float | None
    completed: bool
    completed_at: datetime | None


class SetUpdate(BaseModel):
    weight: Weight | None = None
    repetitions: Reps | None = None
    duration_seconds: Seconds | None = None
    distance: Distance | None = None
    speed: Speed | None = None
    completed: bool | None = None


class SetCreate(BaseModel):
    """Add a set (or a left/right pair for unilateral exercises) copying the last set's values."""


class PreviousPerformance(BaseModel):
    session_id: int
    session_name: str
    performed_on: date
    load_type: LoadType
    pulley_ratio: str | None
    sets: list[SetOut]
    summary: str


class SessionExerciseOut(BaseModel):
    id: int
    exercise_id: str
    exercise_order: int
    status: str
    notes: str | None
    exercise_name: str
    tracking_type: TrackingType
    load_type: LoadType
    pulley_ratio: str | None
    unilateral: bool
    target_sets: int
    target_text: str | None
    target_rep_min: int | None
    target_rep_max: int | None
    target_duration_min: int | None
    target_duration_max: int | None
    suggested_weight: float | None
    recommended_weight: float | None
    suggestion_action: str | None
    suggestion_reason: str | None
    rest_seconds: int
    plan_notes: str | None
    # Current library data (display only)
    primary_muscle_group: str | None
    equipment_name: str | None
    equipment_detail: str | None
    attachment: str | None
    image_url: str | None
    thumb_url: str | None
    weight_options: list[float] | None
    weight_increment: float | None
    previous: PreviousPerformance | None
    sets: list[SetOut]


class SessionOut(BaseModel):
    id: int
    workout_template_id: int | None
    name: str
    performed_on: date
    program_week: int | None
    started_at: datetime
    completed_at: datetime | None
    status: str
    notes: str | None
    completed_sets: int
    total_sets: int
    exercises: list[SessionExerciseOut]


class SessionCreate(BaseModel):
    workout_template_id: int | None = None
    name: str | None = Field(None, max_length=100)
    performed_on: date | None = None


class SessionUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    notes: str | None = None
    performed_on: date | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class SessionComplete(BaseModel):
    notes: str | None = None


class SessionExerciseUpdate(BaseModel):
    status: str | None = Field(None, pattern="^(active|skipped)$")
    notes: str | None = None


class SessionExerciseAdd(BaseModel):
    exercise_id: str


class ApplyWeight(BaseModel):
    weight: Weight


class SessionExerciseSummary(BaseModel):
    exercise_id: str
    exercise_name: str
    status: str
    load_type: LoadType
    completed_sets: int
    best: str | None


class SessionSummary(BaseModel):
    id: int
    workout_template_id: int | None
    name: str
    performed_on: date
    started_at: datetime
    completed_at: datetime | None
    duration_minutes: int | None
    status: str
    notes: str | None
    exercise_count: int
    exercises_completed: int
    completed_sets: int
    total_sets: int
    volume: float
    exercises: list[SessionExerciseSummary]


class HistoryPage(BaseModel):
    total: int
    items: list[SessionSummary]


# --------------------------------------------------------------------------- dashboard & settings


class TemplateChoice(BaseModel):
    id: int
    name: str
    weekday: int | None
    weekday_name: str | None
    exercise_count: int
    estimated_duration_minutes: int


class Dashboard(BaseModel):
    date: date
    weekday: int
    weekday_name: str
    program_week: int | None
    today: TemplateOut | None
    active_session: SessionSummary | None
    last_session: SessionSummary | None
    completed_today: SessionSummary | None
    templates: list[TemplateChoice]


class AppSettingsOut(ORM):
    program_start_date: date | None
    ramp_weeks: int
    rest_timer_auto_start: bool
    rest_timer_sound: bool
    progression_drop_threshold: int


class AppSettingsUpdate(BaseModel):
    program_start_date: date | None = None
    clear_program_start_date: bool = False
    ramp_weeks: Annotated[int, Field(ge=0, le=12)] | None = None
    rest_timer_auto_start: bool | None = None
    rest_timer_sound: bool | None = None
    progression_drop_threshold: Annotated[int, Field(ge=1, le=10)] | None = None


# --------------------------------------------------------------------------- analytics


class WeekBucket(BaseModel):
    week_start: date
    workouts: int
    planned: int
    minutes: int
    volume: float


class PersonalBest(BaseModel):
    exercise_id: str
    exercise_name: str
    performed_on: date
    weight: float
    repetitions: int | None
    previous_best: float | None
    load_type: LoadType


class CalendarDay(BaseModel):
    date: date
    session_ids: list[int]
    planned: bool


class AnalyticsSummary(BaseModel):
    workouts_this_week: int
    planned_this_week: int
    total_workouts: int
    total_minutes: int
    average_minutes: int | None
    consistency_percent: int | None  # last 8 weeks, completed / planned workout days
    current_streak_weeks: int
    weeks: list[WeekBucket]
    personal_bests: list[PersonalBest]
    calendar: list[CalendarDay]


# --------------------------------------------------------------------------- plan assistant


class AssistantStatus(BaseModel):
    email_enabled: bool
    email: str | None


class PromptRequest(BaseModel):
    request: str = Field(min_length=3, max_length=4000)


class PromptOut(BaseModel):
    prompt: str


class EmailSent(BaseModel):
    sent_to: str


class PlanDocumentIn(BaseModel):
    document: str = Field(min_length=1, max_length=500_000)


class PlanDiffExercise(BaseModel):
    exercise_id: str
    exercise_name: str
    status: str  # added | removed | changed | unchanged
    changes: list[str]
    sets: int
    reps_or_duration: str
    weight: float | None


class PlanDiffWorkout(BaseModel):
    name: str
    day: str | None
    previous_day: str | None
    status: str  # added | removed | changed | unchanged
    notes: list[str]
    exercises: list[PlanDiffExercise]


class PlanPreview(BaseModel):
    ok: bool
    summary: str | None
    errors: list[str]
    warnings: list[str]
    workouts: list[PlanDiffWorkout]


class PlanRevisionOut(ORM):
    id: int
    created_at: datetime
    source: str
    summary: str | None
    undone_at: datetime | None
    can_undo: bool = False
