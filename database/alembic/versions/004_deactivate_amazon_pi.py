"""Set amazon_pi portal as inactive

amazon_pi is a scraper-only portal used for import logging. Actual sales
data is stored under the 'amazon' portal (AmazonPIParser emits portal="amazon").
Marking amazon_pi as inactive prevents it from appearing in dashboard charts
and portal dropdowns, replacing the hardcoded exclusion in sales.py.

Revision ID: 004_deactivate_amazon_pi
Revises: 003_add_easyecom_portals, 003_add_portal_exclusions
Create Date: 2026-03-01
"""
from alembic import op

revision = "004_deactivate_amazon_pi"
down_revision = ("003_add_easyecom_portals", "003_add_portal_exclusions")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE portals SET is_active = false WHERE name = 'amazon_pi'")


def downgrade() -> None:
    op.execute("UPDATE portals SET is_active = true WHERE name = 'amazon_pi'")
