"""profiles: plans, sessions and settings belong to a person

Existing data is assigned to Trey (profile 1); Abby (profile 2) starts empty.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-19 10:00:00

"""
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op


revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Lets batch mode name (and so drop) the unnamed unique constraints from 0001.
NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
OWNER_ID = 1  # Trey


def upgrade() -> None:
    profiles = op.create_table('profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    op.bulk_insert(profiles, [
        {"id": 1, "name": "Trey", "created_at": now},
        {"id": 2, "name": "Abby", "created_at": now},
    ])

    for table in ('workout_templates', 'workout_sessions', 'app_settings'):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column('profile_id', sa.Integer(), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET profile_id = {OWNER_ID}"))

    with op.batch_alter_table('workout_templates', naming_convention=NAMING) as batch_op:
        batch_op.alter_column('profile_id', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_constraint('uq_workout_templates_name', type_='unique')
        batch_op.drop_constraint('uq_workout_templates_weekday', type_='unique')
        batch_op.create_unique_constraint('uq_workout_templates_profile_name', ['profile_id', 'name'])
        batch_op.create_unique_constraint('uq_workout_templates_profile_weekday', ['profile_id', 'weekday'])
        batch_op.create_foreign_key('fk_workout_templates_profile_id', 'profiles', ['profile_id'], ['id'],
                                    ondelete='CASCADE')
        batch_op.create_index('ix_workout_templates_profile_id', ['profile_id'], unique=False)

    with op.batch_alter_table('workout_sessions') as batch_op:
        batch_op.alter_column('profile_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_workout_sessions_profile_id', 'profiles', ['profile_id'], ['id'],
                                    ondelete='CASCADE')
        batch_op.create_index('ix_workout_sessions_profile_id', ['profile_id'], unique=False)

    with op.batch_alter_table('app_settings') as batch_op:
        batch_op.alter_column('profile_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_unique_constraint('uq_app_settings_profile_id', ['profile_id'])
        batch_op.create_foreign_key('fk_app_settings_profile_id', 'profiles', ['profile_id'], ['id'],
                                    ondelete='CASCADE')


def downgrade() -> None:
    # Only the owner's data fits the single-user schema; everyone else's is removed.
    for table in ('workout_sessions', 'workout_templates', 'app_settings'):
        op.execute(sa.text(f"DELETE FROM {table} WHERE profile_id != {OWNER_ID}"))

    with op.batch_alter_table('app_settings') as batch_op:
        batch_op.drop_constraint('fk_app_settings_profile_id', type_='foreignkey')
        batch_op.drop_constraint('uq_app_settings_profile_id', type_='unique')
        batch_op.drop_column('profile_id')

    with op.batch_alter_table('workout_sessions') as batch_op:
        batch_op.drop_index('ix_workout_sessions_profile_id')
        batch_op.drop_constraint('fk_workout_sessions_profile_id', type_='foreignkey')
        batch_op.drop_column('profile_id')

    with op.batch_alter_table('workout_templates') as batch_op:
        batch_op.drop_index('ix_workout_templates_profile_id')
        batch_op.drop_constraint('fk_workout_templates_profile_id', type_='foreignkey')
        batch_op.drop_constraint('uq_workout_templates_profile_weekday', type_='unique')
        batch_op.drop_constraint('uq_workout_templates_profile_name', type_='unique')
        batch_op.drop_column('profile_id')
        batch_op.create_unique_constraint('uq_workout_templates_name', ['name'])
        batch_op.create_unique_constraint('uq_workout_templates_weekday', ['weekday'])

    op.drop_table('profiles')
