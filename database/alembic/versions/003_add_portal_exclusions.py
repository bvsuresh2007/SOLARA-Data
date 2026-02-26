"""Add product_portal_exclusions table

Records products that are intentionally NOT listed on a specific portal.
This lets the Actions Dashboard distinguish "mapping missing" from
"product does not sell on this portal at all".

Revision ID: 003_add_portal_exclusions
Revises: 002_rename_amazon_display
Create Date: 2026-02-26
"""
from alembic import op

revision = "003_add_portal_exclusions"
down_revision = "002_rename_amazon_display"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS product_portal_exclusions (
            product_id INTEGER NOT NULL REFERENCES products(id)  ON DELETE CASCADE,
            portal_id  INTEGER NOT NULL REFERENCES portals(id)   ON DELETE CASCADE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (product_id, portal_id)
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ppe_portal
        ON product_portal_exclusions (portal_id);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS product_portal_exclusions;")
