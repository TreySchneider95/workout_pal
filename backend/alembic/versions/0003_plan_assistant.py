"""plan assistant: profile email and plan revisions

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19 14:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('profiles') as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(length=254), nullable=True))

    op.create_table('plan_revisions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('profile_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('previous_plan', sa.JSON(), nullable=False),
    sa.Column('new_plan', sa.JSON(), nullable=False),
    sa.Column('undone_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['profile_id'], ['profiles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('plan_revisions') as batch_op:
        batch_op.create_index('ix_plan_revisions_profile_id', ['profile_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('plan_revisions') as batch_op:
        batch_op.drop_index('ix_plan_revisions_profile_id')
    op.drop_table('plan_revisions')
    with op.batch_alter_table('profiles') as batch_op:
        batch_op.drop_column('email')
