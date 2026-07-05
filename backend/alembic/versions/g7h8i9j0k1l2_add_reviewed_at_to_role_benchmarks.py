"""add_reviewed_at_to_role_benchmarks

Revision ID: g7h8i9j0k1l2
Revises: f6g7h8i9j0k1
Create Date: 2026-07-05 03:28:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g7h8i9j0k1l2'
down_revision = 'f6g7h8i9j0k1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('role_benchmarks', sa.Column('reviewed_at', sa.DateTime(timezone=False), nullable=True))


def downgrade() -> None:
    op.drop_column('role_benchmarks', 'reviewed_at')
