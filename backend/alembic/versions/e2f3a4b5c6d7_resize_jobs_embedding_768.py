"""resize jobs.embedding VECTOR(1536) -> VECTOR(768)

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-07-01

Switches to the local BAAI/bge-base-en-v1.5 model (768-dim). Every existing
``jobs.embedding`` is NULL, so no data migration is needed — the column is simply
recreated at the new dimension. Backfill with scripts/backfill_embeddings.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy.vector

# revision identifiers, used by Alembic.
revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('jobs', 'embedding')
    op.add_column(
        'jobs',
        sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('jobs', 'embedding')
    op.add_column(
        'jobs',
        sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=True),
    )
