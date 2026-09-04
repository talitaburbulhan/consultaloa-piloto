"""add executable editorial map

Revision ID: b41c9d8e7a10
Revises: 86cb07f659c1
Create Date: 2026-08-31 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b41c9d8e7a10"
down_revision: Union[str, Sequence[str], None] = "86cb07f659c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("budget_records") as batch_op:
        batch_op.add_column(sa.Column("area_slug", sa.String(length=100)))
        batch_op.add_column(sa.Column("record_level", sa.String(length=50)))
        batch_op.add_column(sa.Column("evidence_status", sa.String(length=50)))
        batch_op.add_column(sa.Column("aggregation_policy", sa.String(length=50)))
        batch_op.create_index("ix_budget_records_area_slug", ["area_slug"])
        batch_op.create_index("ix_budget_records_record_level", ["record_level"])
        batch_op.create_index("ix_budget_records_evidence_status", ["evidence_status"])
        batch_op.create_index("ix_budget_records_aggregation_policy", ["aggregation_policy"])

    op.create_table(
        "editorial_areas",
        sa.Column("slug", sa.String(length=100), primary_key=True),
        sa.Column("label", sa.String(length=300), nullable=False, unique=True),
        sa.Column("aliases_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("protected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "human_validation_complete",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "editorial_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rule_key", sa.String(length=200), nullable=False, unique=True),
        sa.Column("subject_slug", sa.String(length=150), nullable=False),
        sa.Column("rule_type", sa.String(length=80), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("source_checkpoint", sa.String(length=500)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_editorial_rules_rule_key", "editorial_rules", ["rule_key"])
    op.create_index("ix_editorial_rules_subject_slug", "editorial_rules", ["subject_slug"])
    op.create_index("ix_editorial_rules_rule_type", "editorial_rules", ["rule_type"])
    op.create_table(
        "historical_segments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_slug", sa.String(length=150), nullable=False),
        sa.Column("area_slug", sa.String(length=100), nullable=False),
        sa.Column("organization_code", sa.String(length=30), nullable=False),
        sa.Column("start_year", sa.Integer(), nullable=False),
        sa.Column("end_year", sa.Integer(), nullable=False),
        sa.Column("comparison_group", sa.String(length=150)),
        sa.Column("aggregation_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text()),
        sa.UniqueConstraint(
            "entity_slug",
            "organization_code",
            "start_year",
            "end_year",
            name="uq_historical_segment",
        ),
    )
    op.create_index("ix_historical_segments_entity_slug", "historical_segments", ["entity_slug"])
    op.create_index("ix_historical_segments_area_slug", "historical_segments", ["area_slug"])
    op.create_index("ix_historical_segments_organization_code", "historical_segments", ["organization_code"])
    op.create_index("ix_historical_segments_start_year", "historical_segments", ["start_year"])
    op.create_index("ix_historical_segments_end_year", "historical_segments", ["end_year"])
    op.create_index("ix_historical_segments_comparison_group", "historical_segments", ["comparison_group"])


def downgrade() -> None:
    op.drop_table("historical_segments")
    op.drop_table("editorial_rules")
    op.drop_table("editorial_areas")
    with op.batch_alter_table("budget_records") as batch_op:
        batch_op.drop_index("ix_budget_records_aggregation_policy")
        batch_op.drop_index("ix_budget_records_evidence_status")
        batch_op.drop_index("ix_budget_records_record_level")
        batch_op.drop_index("ix_budget_records_area_slug")
        batch_op.drop_column("aggregation_policy")
        batch_op.drop_column("evidence_status")
        batch_op.drop_column("record_level")
        batch_op.drop_column("area_slug")
