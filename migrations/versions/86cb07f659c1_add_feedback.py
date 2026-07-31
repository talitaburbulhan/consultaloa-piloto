"""add human feedback records

Revision ID: 86cb07f659c1
Revises: 2d71f941ce20
Create Date: 2026-07-30 18:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "86cb07f659c1"
down_revision: Union[str, Sequence[str], None] = "2d71f941ce20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("user_email", sa.String(length=320), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("years_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("verdict", sa.String(length=30), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "review_status",
            sa.String(length=30),
            nullable=False,
            server_default="pending",
        ),
    )
    op.create_index("ix_feedback_public_id", "feedback", ["public_id"], unique=True)
    op.create_index("ix_feedback_created_at", "feedback", ["created_at"])
    op.create_index("ix_feedback_user_email", "feedback", ["user_email"])
    op.create_index("ix_feedback_verdict", "feedback", ["verdict"])
    op.create_index("ix_feedback_review_status", "feedback", ["review_status"])


def downgrade() -> None:
    op.drop_table("feedback")
