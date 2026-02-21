"""Schema v2: Replace 9-table scaffold with 12-table production schema

Revision ID: 001_schema_v2
Revises:
Create Date: 2026-02-20

Changes from v1:
  - Drops: sales_data, inventory_data, scraping_logs
  - Adds: daily_sales, city_daily_sales, inventory_snapshots,
          monthly_targets, monthly_ad_spend, import_logs
  - Modifies: products (adds default_asp, expands product_name to 500 chars)
  - Modifies: product_categories (removes l3_name; adds COALESCE unique index)
  - Modifies: cities (removes updated_at; adds COALESCE unique index)
  - Modifies: product_portal_mapping (renames portal_product_id → portal_sku)
"""
from alembic import op
import sqlalchemy as sa

revision = "001_schema_v2"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Drop old tables (order respects FK dependencies) ──────────────────
    op.drop_table("sales_data",      checkfirst=True)
    op.drop_table("inventory_data",  checkfirst=True)
    op.drop_table("scraping_logs",   checkfirst=True)

    # ── product_categories: drop l3_name, fix unique constraint ───────────
    with op.batch_alter_table("product_categories") as batch_op:
        try:
            batch_op.drop_column("l3_name")
        except Exception:
            pass  # might not exist
        try:
            batch_op.drop_constraint("product_categories_l1_name_l2_name_l3_name_key")
        except Exception:
            pass

    op.execute("""
        ALTER TABLE product_categories
        DROP CONSTRAINT IF EXISTS product_categories_l1_name_l2_name_l3_name_key;
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_product_categories_l1_l2
        ON product_categories (l1_name, COALESCE(l2_name, ''));
    """)

    # ── products: add default_asp, expand product_name ────────────────────
    op.execute("ALTER TABLE products ALTER COLUMN product_name TYPE VARCHAR(500);")
    op.execute("""
        ALTER TABLE products ADD COLUMN IF NOT EXISTS default_asp NUMERIC(10, 2);
    """)

    # ── cities: fix unique constraint ─────────────────────────────────────
    op.execute("""
        ALTER TABLE cities DROP CONSTRAINT IF EXISTS cities_name_state_key;
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_cities_name_state
        ON cities (name, COALESCE(state, ''));
    """)

    # ── product_portal_mapping: rename portal_product_id → portal_sku ─────
    op.execute("""
        ALTER TABLE product_portal_mapping
        RENAME COLUMN portal_product_id TO portal_sku;
    """)
    op.execute("""
        ALTER TABLE product_portal_mapping
        ALTER COLUMN portal_sku TYPE VARCHAR(500);
    """)

    # ── daily_sales ───────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS daily_sales (
            id          SERIAL         PRIMARY KEY,
            portal_id   INTEGER        NOT NULL REFERENCES portals(id),
            product_id  INTEGER        NOT NULL REFERENCES products(id),
            sale_date   DATE           NOT NULL,
            units_sold  NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (units_sold >= 0),
            asp         NUMERIC(10, 2),
            revenue     NUMERIC(14, 2),
            data_source VARCHAR(30)    NOT NULL DEFAULT 'excel',
            imported_at TIMESTAMP      NOT NULL DEFAULT NOW(),
            UNIQUE (portal_id, product_id, sale_date)
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_daily_sales_date         ON daily_sales (sale_date DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_daily_sales_portal_date  ON daily_sales (portal_id, sale_date DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_daily_sales_product_date ON daily_sales (product_id, sale_date DESC);")

    # ── city_daily_sales ──────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS city_daily_sales (
            id              SERIAL         PRIMARY KEY,
            portal_id       INTEGER        NOT NULL REFERENCES portals(id),
            product_id      INTEGER        NOT NULL REFERENCES products(id),
            city_id         INTEGER        NOT NULL REFERENCES cities(id),
            sale_date       DATE           NOT NULL,
            units_sold      NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (units_sold >= 0),
            mrp             NUMERIC(10, 2),
            selling_price   NUMERIC(10, 2),
            revenue         NUMERIC(14, 2),
            discount_amount NUMERIC(12, 2) DEFAULT 0,
            net_revenue     NUMERIC(14, 2),
            order_count     INTEGER        DEFAULT 0,
            data_source     VARCHAR(30)    NOT NULL DEFAULT 'portal_csv',
            imported_at     TIMESTAMP      NOT NULL DEFAULT NOW(),
            UNIQUE (portal_id, product_id, city_id, sale_date)
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_city_sales_date         ON city_daily_sales (sale_date DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_city_sales_portal_city  ON city_daily_sales (portal_id, city_id, sale_date DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_city_sales_product_date ON city_daily_sales (product_id, sale_date DESC);")

    # ── inventory_snapshots ───────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_snapshots (
            id              SERIAL         PRIMARY KEY,
            portal_id       INTEGER        NOT NULL REFERENCES portals(id),
            product_id      INTEGER        NOT NULL REFERENCES products(id),
            snapshot_date   DATE           NOT NULL,
            portal_stock    NUMERIC(12, 2),
            backend_stock   NUMERIC(12, 2),
            frontend_stock  NUMERIC(12, 2),
            solara_stock    NUMERIC(12, 2),
            amazon_fc_stock NUMERIC(12, 2),
            open_po         NUMERIC(12, 2),
            doc             NUMERIC(8, 2),
            imported_at     TIMESTAMP      NOT NULL DEFAULT NOW(),
            UNIQUE (portal_id, product_id, snapshot_date)
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_inv_portal_date  ON inventory_snapshots (portal_id, snapshot_date DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_inv_product_date ON inventory_snapshots (product_id, snapshot_date DESC);")

    # ── monthly_targets ───────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS monthly_targets (
            id              SERIAL         PRIMARY KEY,
            portal_id       INTEGER        NOT NULL REFERENCES portals(id),
            product_id      INTEGER        NOT NULL REFERENCES products(id),
            year            SMALLINT       NOT NULL,
            month           SMALLINT       NOT NULL CHECK (month BETWEEN 1 AND 12),
            target_units    NUMERIC(12, 2),
            target_revenue  NUMERIC(14, 2),
            target_drr      NUMERIC(10, 2),
            achievement_pct NUMERIC(8, 4),
            UNIQUE (portal_id, product_id, year, month)
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_targets_portal_period ON monthly_targets (portal_id, year, month);")

    # ── monthly_ad_spend ──────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS monthly_ad_spend (
            id            SERIAL         PRIMARY KEY,
            portal_id     INTEGER        NOT NULL REFERENCES portals(id),
            year          SMALLINT       NOT NULL,
            month         SMALLINT       NOT NULL CHECK (month BETWEEN 1 AND 12),
            total_revenue NUMERIC(14, 2),
            ad_spend      NUMERIC(14, 2),
            tacos_pct     NUMERIC(8, 4),
            UNIQUE (portal_id, year, month)
        );
    """)

    # ── import_logs ───────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS import_logs (
            id               SERIAL       PRIMARY KEY,
            source_type      VARCHAR(30)  NOT NULL,
            portal_id        INTEGER      REFERENCES portals(id),
            sheet_name       VARCHAR(200),
            file_name        VARCHAR(500),
            import_date      DATE         NOT NULL,
            start_time       TIMESTAMP    NOT NULL DEFAULT NOW(),
            end_time         TIMESTAMP,
            status           VARCHAR(20)  NOT NULL DEFAULT 'running'
                                 CHECK (status IN ('running', 'success', 'failed', 'partial')),
            records_imported INTEGER      DEFAULT 0,
            error_message    TEXT,
            created_at       TIMESTAMP    NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_import_logs_date   ON import_logs (import_date DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_import_logs_portal ON import_logs (portal_id, import_date DESC);")


def downgrade() -> None:
    # Drop new tables
    op.drop_table("import_logs",        checkfirst=True)
    op.drop_table("monthly_ad_spend",   checkfirst=True)
    op.drop_table("monthly_targets",    checkfirst=True)
    op.drop_table("inventory_snapshots", checkfirst=True)
    op.drop_table("city_daily_sales",   checkfirst=True)
    op.drop_table("daily_sales",        checkfirst=True)
    # Note: downgrade does not restore old tables — run init_db.sql from v1 if needed
