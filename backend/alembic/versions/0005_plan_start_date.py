"""plan start date apart from the training start date; plan week recorded on sessions

Restarting a plan used to move the training start date, which also restarted the lighter
ramp-in weeks and re-counted past weeks in the stats. Plan weeks now count from their own
Monday-aligned plan_start_date, and each session records the plan week it was done in.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-18 12:00:00

"""
from collections.abc import Sequence
from datetime import date, timedelta

import sqlalchemy as sa
from alembic import op


revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _plan_start_for(day: date) -> date:
    monday = day - timedelta(days=day.weekday())
    return monday + timedelta(weeks=1) if day.weekday() >= 5 else monday


def upgrade() -> None:
    with op.batch_alter_table('app_settings') as batch_op:
        batch_op.add_column(sa.Column('plan_start_date', sa.Date(), nullable=True))
    with op.batch_alter_table('workout_sessions') as batch_op:
        batch_op.add_column(sa.Column('plan_week', sa.Integer(), nullable=True))

    conn = op.get_bind()
    for row in conn.execute(sa.text(
        "SELECT id, program_start_date FROM app_settings WHERE program_start_date IS NOT NULL"
    )).all():
        start = row.program_start_date
        start = date.fromisoformat(start) if isinstance(start, str) else start
        conn.execute(sa.text("UPDATE app_settings SET plan_start_date = :d WHERE id = :id"),
                     {"d": _plan_start_for(start).isoformat(), "id": row.id})
    # "Every week" was sometimes stored as the JSON text 'null' rather than SQL NULL.
    conn.execute(sa.text("UPDATE workout_templates SET weeks = NULL WHERE weeks = 'null'"))


def downgrade() -> None:
    with op.batch_alter_table('workout_sessions') as batch_op:
        batch_op.drop_column('plan_week')
    with op.batch_alter_table('app_settings') as batch_op:
        batch_op.drop_column('plan_start_date')
