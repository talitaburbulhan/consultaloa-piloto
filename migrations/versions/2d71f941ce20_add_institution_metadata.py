"""add institution metadata to budget records

Revision ID: 2d71f941ce20
Revises: f76fcaa4b556
Create Date: 2026-07-30 11:25:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2d71f941ce20"
down_revision: Union[str, Sequence[str], None] = "f76fcaa4b556"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("budget_records") as batch_op:
        batch_op.add_column(sa.Column("organization_name", sa.String(length=500)))
        batch_op.add_column(sa.Column("institution_category", sa.String(length=80)))
        batch_op.add_column(sa.Column("parent_organization_code", sa.String(length=30)))
        batch_op.create_index("ix_budget_records_organization_name", ["organization_name"])
        batch_op.create_index(
            "ix_budget_records_institution_category", ["institution_category"]
        )
        batch_op.create_index(
            "ix_budget_records_parent_organization_code", ["parent_organization_code"]
        )


def downgrade() -> None:
    with op.batch_alter_table("budget_records") as batch_op:
        batch_op.drop_index("ix_budget_records_parent_organization_code")
        batch_op.drop_index("ix_budget_records_institution_category")
        batch_op.drop_index("ix_budget_records_organization_name")
        batch_op.drop_column("parent_organization_code")
        batch_op.drop_column("institution_category")
        batch_op.drop_column("organization_name")
