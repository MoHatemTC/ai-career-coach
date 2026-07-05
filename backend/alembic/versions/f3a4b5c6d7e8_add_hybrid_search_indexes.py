"""add hybrid-search indexes (HNSW on embedding, GIN on required_skills)

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-07-01

- HNSW on jobs.embedding for approximate nearest-neighbour vector search.
  m=16, ef_construction=64 (pgvector defaults) give near-exact recall at this
  table size (hundreds → low thousands of jobs).
- GIN (jsonb_path_ops) on jobs.required_skills for fast @> containment, the
  keyword pre-filter fast path (e.g. required_skills @> '["python"]').

Must run after the embedding column is VECTOR(768) (revision e2f3a4b5c6d7).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3a4b5c6d7e8'
down_revision: Union[str, Sequence[str], None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_embedding_hnsw "
        "ON jobs USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_required_skills_gin "
        "ON jobs USING gin (required_skills jsonb_path_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_jobs_required_skills_gin")
    op.execute("DROP INDEX IF EXISTS idx_jobs_embedding_hnsw")
