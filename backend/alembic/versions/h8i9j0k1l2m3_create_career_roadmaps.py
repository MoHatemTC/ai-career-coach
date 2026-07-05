"""create_career_roadmaps

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-07-05 04:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'h8i9j0k1l2m3'
down_revision = 'g7h8i9j0k1l2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'career_roadmaps',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('readiness_score_id', sa.Integer(), sa.ForeignKey('readiness_scores.id'), nullable=False),
        sa.Column('weeks', sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column('executive_summary', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('key_focus_areas', sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column('responsible_ai_disclaimer', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column('reviewed_at', sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index(op.f('ix_career_roadmaps_readiness_score_id'), 'career_roadmaps', ['readiness_score_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_career_roadmaps_readiness_score_id'), table_name='career_roadmaps')
    op.drop_table('career_roadmaps')
