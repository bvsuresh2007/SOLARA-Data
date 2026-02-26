"""Rename Amazon display_name to Amazon PI

Revision ID: 002_rename_amazon_display
Revises: 001_schema_v2
Create Date: 2026-02-26
"""
from alembic import op

revision = "002_rename_amazon_display"
down_revision = "001_schema_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE portals SET display_name = 'Amazon PI' WHERE name = 'amazon'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE portals SET display_name = 'Amazon' WHERE name = 'amazon'"
    )
