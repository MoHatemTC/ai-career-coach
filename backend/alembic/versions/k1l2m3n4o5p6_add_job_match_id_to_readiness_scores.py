"""add job_match_id to readiness_scores

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-07-05 11:11:35.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k1l2m3n4o5p6'
down_revision: Union[str, None] = 'j0k1l2m3n4o5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('readiness_scores', sa.Column('job_match_id', sa.Integer(), sa.ForeignKey('job_matches.id'), nullable=True))
    op.create_index(op.f('ix_readiness_scores_job_match_id'), 'readiness_scores', ['job_match_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_readiness_scores_job_match_id'), table_name='readiness_scores')
    op.drop_column('readiness_scores', 'job_match_id')
