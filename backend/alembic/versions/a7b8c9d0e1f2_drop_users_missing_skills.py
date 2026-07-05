"""drop users.missing_skills

Revision ID: a7b8c9d0e1f2
Revises: f3a4b5c6d7e8
Create Date: 2026-07-01

"missing skills" is a per-(user, job) result and already lives on
job_matches.missing_skills. The users.missing_skills column was never read and
never meaningfully populated (the CV parser hard-coded it to []), so it is
removed here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('users', 'missing_skills')


def downgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'missing_skills',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
