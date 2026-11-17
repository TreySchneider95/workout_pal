"""multi-week plans: workouts run in chosen plan weeks; plans repeat every N weeks

A day may now hold different workouts in different weeks, so the one-workout-per-day
unique constraint goes (the app checks for overlapping weeks instead).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17 12:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('workout_templates') as batch_op:
        batch_op.drop_constraint('uq_workout_templates_profile_weekday', type_='unique')
        batch_op.add_column(sa.Column('weeks', sa.JSON(), nullable=True))

    with op.batch_alter_table('app_settings') as batch_op:
        batch_op.add_column(sa.Column('plan_weeks', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    with op.batch_alter_table('app_settings') as batch_op:
        batch_op.drop_column('plan_weeks')

    # Back to one workout per day: keep each day's every-week (or lowest-week) workout.
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, profile_id, weekday, weeks FROM workout_templates WHERE weekday IS NOT NULL ORDER BY id"
    )).all()
    import json

    def first_week(weeks: object) -> int:
        values = json.loads(weeks) if isinstance(weeks, str) else weeks
        return min(values) if values else 0

    keep: dict[tuple[int, int], tuple[int, int]] = {}
    for row in rows:
        key = (row.profile_id, row.weekday)
        rank = (first_week(row.weeks), row.id)
        if key not in keep or rank < keep[key]:
            keep[key] = rank
    kept_ids = {rank[1] for rank in keep.values()}
    for row in rows:
        if row.id not in kept_ids:
            conn.execute(sa.text("UPDATE workout_templates SET weekday = NULL WHERE id = :id"), {"id": row.id})

    with op.batch_alter_table('workout_templates') as batch_op:
        batch_op.drop_column('weeks')
        batch_op.create_unique_constraint('uq_workout_templates_profile_weekday', ['profile_id', 'weekday'])
