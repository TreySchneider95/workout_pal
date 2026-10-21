"""Database models.

Three layers are kept separate on purpose:

* Library   - Equipment, Exercise (shared by every profile)
* Plan      - WorkoutTemplate, WorkoutTemplateExercise (freely editable, per profile)
* History   - WorkoutSession, WorkoutSessionExercise, ExerciseSet (per profile)

History rows snapshot everything they need from the plan when a session is
started, so editing or deleting templates never changes recorded workouts.
"""

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Stores naive UTC in SQLite and always returns timezone-aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


class TrackingType(StrEnum):
    strength = "strength"
    bodyweight = "bodyweight"
    timed = "timed"
    cardio = "cardio"


class LoadType(StrEnum):
    """How a recorded weight should be read. Stored with every set's exercise snapshot."""

    per_dumbbell = "per_dumbbell"  # weight of ONE dumbbell, two are used
    single_dumbbell = "single_dumbbell"  # one dumbbell held for the movement
    plates_loaded = "plates_loaded"  # plates on a cable stack; pulley ratio stored separately
    added_plates = "added_plates"  # plates added to a Smith bar; bar weight NOT included
    bodyweight = "bodyweight"  # bodyweight, optional added load
    none = "none"


class SessionStatus(StrEnum):
    in_progress = "in_progress"
    completed = "completed"


class SessionExerciseStatus(StrEnum):
    active = "active"
    skipped = "skipped"


class Side(StrEnum):
    left = "left"
    right = "right"


class Profile(Base):
    """A person using the app. Plans, history and settings belong to a profile."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    # Where plan-assistant prompts are emailed.
    email: Mapped[str | None] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    equipment_type: Mapped[str] = mapped_column(String(30))
    # Weight steps the equipment supports. An explicit list wins over the increment.
    weight_increment: Mapped[float | None] = mapped_column(Float)
    available_weights: Mapped[list[float] | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)

    exercises: Mapped[list["Exercise"]] = relationship(back_populates="equipment")


class Exercise(Base):
    __tablename__ = "exercises"

    # Stable IDs from the CSV (e.g. EX0001); custom exercises use CX0001...
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    primary_muscle_group: Mapped[str | None] = mapped_column(String(50), index=True)
    secondary_muscles: Mapped[list[str]] = mapped_column(JSON, default=list)
    equipment_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipment.id", ondelete="SET NULL"), index=True
    )
    # Full equipment requirement as written in the library, e.g. "Dumbbells + adjustable bench".
    equipment_detail: Mapped[str | None] = mapped_column(String(200))
    attachment: Mapped[str | None] = mapped_column(String(200))
    tracking_type: Mapped[str] = mapped_column(String(20), default=TrackingType.strength)
    load_type: Mapped[str] = mapped_column(String(30), default=LoadType.none)
    pulley_ratio: Mapped[str | None] = mapped_column(String(10))
    # Unilateral exercises record left and right sides as separate sets.
    unilateral: Mapped[bool] = mapped_column(Boolean, default=False)
    starting_weight: Mapped[float | None] = mapped_column(Float)
    image_key: Mapped[str | None] = mapped_column(String(200))
    image_path: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow
    )

    equipment: Mapped[Equipment | None] = relationship(back_populates="exercises")


class WorkoutTemplate(Base):
    __tablename__ = "workout_templates"
    __table_args__ = (
        UniqueConstraint("profile_id", "name", name="uq_workout_templates_profile_name"),
        UniqueConstraint("profile_id", "weekday", name="uq_workout_templates_profile_weekday"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    # 0 = Monday ... 6 = Sunday. NULL = not scheduled (can still be performed manually).
    weekday: Mapped[int | None] = mapped_column(Integer)
    # Manual override; otherwise estimated from the exercises.
    estimated_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow
    )

    exercises: Mapped[list["WorkoutTemplateExercise"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="WorkoutTemplateExercise.exercise_order",
    )


class WorkoutTemplateExercise(Base):
    __tablename__ = "workout_template_exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    workout_template_id: Mapped[int] = mapped_column(
        ForeignKey("workout_templates.id", ondelete="CASCADE"), index=True
    )
    exercise_id: Mapped[str] = mapped_column(
        ForeignKey("exercises.id", ondelete="RESTRICT"), index=True
    )
    exercise_order: Mapped[int] = mapped_column(Integer)
    # Sets for the first program weeks (ramp-in) and afterwards.
    ramp_sets: Mapped[int | None] = mapped_column(Integer)
    target_sets: Mapped[int] = mapped_column(Integer)
    # Original prescription text, e.g. "8-10", "10/side", "20-40 sec", "35 min".
    target_text: Mapped[str | None] = mapped_column(String(50))
    target_rep_min: Mapped[int | None] = mapped_column(Integer)
    target_rep_max: Mapped[int | None] = mapped_column(Integer)
    target_duration_min: Mapped[int | None] = mapped_column(Integer)  # seconds
    target_duration_max: Mapped[int | None] = mapped_column(Integer)  # seconds
    per_side: Mapped[bool] = mapped_column(Boolean, default=False)
    suggested_weight: Mapped[float | None] = mapped_column(Float)
    # When the default weight was last changed by hand; newer than history => it wins.
    suggested_weight_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    default_rest_seconds: Mapped[int] = mapped_column(Integer, default=90)
    notes: Mapped[str | None] = mapped_column(Text)
    # Temporarily excluded from new sessions.
    skipped: Mapped[bool] = mapped_column(Boolean, default=False)

    template: Mapped[WorkoutTemplate] = relationship(back_populates="exercises")
    exercise: Mapped[Exercise] = relationship()


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"
    __table_args__ = (Index("ix_workout_sessions_status_completed", "status", "completed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    workout_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("workout_templates.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))  # snapshot of template name
    performed_on: Mapped[date] = mapped_column(Date, index=True)  # local calendar date
    program_week: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(20), default=SessionStatus.in_progress)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow
    )

    exercises: Mapped[list["WorkoutSessionExercise"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="WorkoutSessionExercise.exercise_order",
    )


class WorkoutSessionExercise(Base):
    __tablename__ = "workout_session_exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    workout_session_id: Mapped[int] = mapped_column(
        ForeignKey("workout_sessions.id", ondelete="CASCADE"), index=True
    )
    exercise_id: Mapped[str] = mapped_column(
        ForeignKey("exercises.id", ondelete="RESTRICT"), index=True
    )
    exercise_order: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default=SessionExerciseStatus.active)
    notes: Mapped[str | None] = mapped_column(Text)

    # --- Snapshot of the exercise and prescription at the time of the session ---
    exercise_name: Mapped[str] = mapped_column(String(200))
    tracking_type: Mapped[str] = mapped_column(String(20))
    load_type: Mapped[str] = mapped_column(String(30))
    pulley_ratio: Mapped[str | None] = mapped_column(String(10))
    unilateral: Mapped[bool] = mapped_column(Boolean, default=False)
    target_sets: Mapped[int] = mapped_column(Integer)
    target_text: Mapped[str | None] = mapped_column(String(50))
    target_rep_min: Mapped[int | None] = mapped_column(Integer)
    target_rep_max: Mapped[int | None] = mapped_column(Integer)
    target_duration_min: Mapped[int | None] = mapped_column(Integer)
    target_duration_max: Mapped[int | None] = mapped_column(Integer)
    # Weight the sets were prefilled with, and what the progression rules recommended.
    suggested_weight: Mapped[float | None] = mapped_column(Float)
    recommended_weight: Mapped[float | None] = mapped_column(Float)
    suggestion_action: Mapped[str | None] = mapped_column(String(20))
    suggestion_reason: Mapped[str | None] = mapped_column(Text)
    rest_seconds: Mapped[int] = mapped_column(Integer, default=90)
    plan_notes: Mapped[str | None] = mapped_column(Text)

    session: Mapped[WorkoutSession] = relationship(back_populates="exercises")
    exercise: Mapped[Exercise] = relationship()
    sets: Mapped[list["ExerciseSet"]] = relationship(
        back_populates="session_exercise",
        cascade="all, delete-orphan",
        order_by="(ExerciseSet.set_number, ExerciseSet.side)",
    )


class ExerciseSet(Base):
    __tablename__ = "exercise_sets"
    __table_args__ = (
        Index("ix_exercise_sets_session_exercise_set", "workout_session_exercise_id", "set_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workout_session_exercise_id: Mapped[int] = mapped_column(
        ForeignKey("workout_session_exercises.id", ondelete="CASCADE")
    )
    set_number: Mapped[int] = mapped_column(Integer)
    side: Mapped[str | None] = mapped_column(String(10))  # NULL, "left", "right"
    weight: Mapped[float | None] = mapped_column(Float)  # lb, per the snapshot's load_type
    repetitions: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    distance: Mapped[float | None] = mapped_column(Float)  # miles
    speed: Mapped[float | None] = mapped_column(Float)  # mph
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow
    )

    session_exercise: Mapped[WorkoutSessionExercise] = relationship(back_populates="sets")


class AppSettings(Base):
    """One row per profile holding that person's preferences."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), unique=True)
    # Week 1 starts here; weeks before `ramp_weeks` use each exercise's ramp_sets.
    program_start_date: Mapped[date | None] = mapped_column(Date)
    ramp_weeks: Mapped[int] = mapped_column(Integer, default=2)
    rest_timer_auto_start: Mapped[bool] = mapped_column(Boolean, default=True)
    rest_timer_sound: Mapped[bool] = mapped_column(Boolean, default=True)
    # Progression: suggest a lower weight when average reps fall this far below the minimum.
    progression_drop_threshold: Mapped[int] = mapped_column(Integer, default=2)


class PlanRevision(Base):
    """A whole-plan change applied from a plan document (e.g. an AI's answer), kept for undo."""

    __tablename__ = "plan_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    source: Mapped[str] = mapped_column(String(20))  # "document" or "undo"
    summary: Mapped[str | None] = mapped_column(Text)
    # Both plans in the plan-document format, so undo is just applying `previous_plan`.
    previous_plan: Mapped[dict] = mapped_column(JSON)
    new_plan: Mapped[dict] = mapped_column(JSON)
    undone_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
