"""add role_benchmarks and readiness_scores tables

Revision ID: e5f6g7h8i9j0
Revises: c1d2e3f4g5h6
Create Date: 2026-07-03 22:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector.sqlalchemy.vector

# revision identifiers, used by Alembic.
revision: str = 'e5f6g7h8i9j0'
down_revision: Union[str, None] = 'c1d2e3f4g5h6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector is already enabled in init_schema migration
    
    op.create_table(
        'role_benchmarks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('must_have_skills', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('nice_to_have_skills', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('required_tools', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('common_responsibilities', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('minimum_years', sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column('seniority_level', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
    )
    
    op.execute("CREATE INDEX ix_role_benchmarks_embedding_hnsw ON role_benchmarks USING hnsw (embedding vector_cosine_ops)")

    op.create_table(
        'readiness_scores',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('benchmark_id', sa.Integer(), sa.ForeignKey('role_benchmarks.id'), nullable=False),
        sa.Column('overall_score', sa.Integer(), nullable=False),
        sa.Column('must_have_skills_score', sa.Integer(), nullable=False),
        sa.Column('tools_score', sa.Integer(), nullable=False),
        sa.Column('experience_score', sa.Integer(), nullable=False),
        sa.Column('soft_skills_score', sa.Integer(), nullable=False),
        sa.Column('critical_gaps', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('nice_to_have_gaps', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('strengths', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('explanation', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('candidate_skills', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('candidate_tools', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('candidate_experience_years', sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column('reviewed_at', sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index(op.f('ix_readiness_scores_benchmark_id'), 'readiness_scores', ['benchmark_id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_readiness_scores_benchmark_id'), table_name='readiness_scores')
    op.drop_table('readiness_scores')
    op.drop_table('role_benchmarks')
