"""Add EasyEcom marketplace portals; revert amazon display_name to 'Amazon'

Adds the 5 new portal rows that EasyEcom data is split into (Meesho, Nykaa
Fashion, CRED, Vaaree, Offline), marks the easyecom aggregator portal as
inactive, and reverts the amazon display_name from 'Amazon PI' back to 'Amazon'
(the 'Amazon PI' rename was superseded by this cleaner naming).

Revision ID: 003_add_easyecom_portals
Revises: 002_rename_amazon_display
Create Date: 2026-02-26
"""
from alembic import op

revision = "003_add_easyecom_portals"
down_revision = "002_rename_amazon_display"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new marketplace portals sourced from EasyEcom split
    op.execute("""
        INSERT INTO portals (name, display_name) VALUES
            ('meesho',        'Meesho'),
            ('nykaa_fashion', 'Nykaa Fashion'),
            ('cred',          'CRED'),
            ('vaaree',        'Vaaree'),
            ('offline',       'Offline')
        ON CONFLICT (name) DO NOTHING
    """)

    # Add easyecom as an inactive aggregator (data lives in the split portals now)
    op.execute("""
        INSERT INTO portals (name, display_name, is_active) VALUES
            ('easyecom', 'EasyEcom (Aggregator)', false)
        ON CONFLICT (name) DO UPDATE SET is_active = false
    """)

    # Revert amazon display_name from 'Amazon PI' back to 'Amazon'
    op.execute("UPDATE portals SET display_name = 'Amazon' WHERE name = 'amazon'")


def downgrade() -> None:
    op.execute("UPDATE portals SET display_name = 'Amazon PI' WHERE name = 'amazon'")
    op.execute(
        "DELETE FROM portals WHERE name IN "
        "('meesho', 'nykaa_fashion', 'cred', 'vaaree', 'offline', 'easyecom')"
    )
