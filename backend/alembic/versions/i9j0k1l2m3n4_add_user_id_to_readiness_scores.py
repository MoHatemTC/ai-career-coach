"""add user_id to readiness_scores

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-07-05 02:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i9j0k1l2m3n4'
down_revision: Union[str, None] = 'h8i9j0k1l2m3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('readiness_scores', sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False))
    op.create_index(op.f('ix_readiness_scores_user_id'), 'readiness_scores', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_readiness_scores_user_id'), table_name='readiness_scores')
    op.drop_column('readiness_scores', 'user_id')
