"""drop shadow schema (role_benchmarks, readiness_scores)

Revision ID: d1e2f3a4b5c6
Revises: 84e36046a174
Create Date: 2026-07-01

The shadow schema was disconnected from the real tables and is replaced by the
match service writing into ``job_matches``. The real ``users`` columns added by
``84e36046a174`` are kept — only the two shadow tables are dropped here.
``IF EXISTS`` keeps this safe on fresh databases (which create then drop them).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = '84e36046a174'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_readiness_scores_benchmark_id")
    op.execute("DROP TABLE IF EXISTS readiness_scores")  # child first (FK)
    op.execute("DROP TABLE IF EXISTS role_benchmarks")


def downgrade() -> None:
    # Recreate the shadow tables (best-effort; the shadow feature is gone).
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS role_benchmarks (
            id SERIAL PRIMARY KEY,
            must_have_skills JSON,
            nice_to_have_skills JSON,
            required_tools JSON,
            common_responsibilities JSON,
            minimum_years INTEGER NOT NULL,
            seniority_level VARCHAR NOT NULL,
            embedding VECTOR(1536),
            created_at TIMESTAMP NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS readiness_scores (
            id SERIAL PRIMARY KEY,
            benchmark_id INTEGER NOT NULL REFERENCES role_benchmarks(id),
            overall_score INTEGER NOT NULL,
            must_have_skills_score INTEGER NOT NULL,
            tools_score INTEGER NOT NULL,
            experience_score INTEGER NOT NULL,
            soft_skills_score INTEGER NOT NULL,
            critical_gaps JSON,
            nice_to_have_gaps JSON,
            strengths JSON,
            explanation VARCHAR NOT NULL,
            candidate_skills JSON,
            candidate_tools JSON,
            candidate_experience_years INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL,
            reviewed_at TIMESTAMP
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_readiness_scores_benchmark_id "
        "ON readiness_scores (benchmark_id)"
    )
