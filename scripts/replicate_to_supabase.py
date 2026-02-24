"""
Replicate local DB schema and data to Supabase.

Usage:
    python scripts/replicate_to_supabase.py [--schema-only] [--data-only]

Default: runs schema first, then data.
"""

import os
import sys
import argparse
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

LOCAL_URL = os.environ.get(
    "LOCAL_DATABASE_URL",
    "postgresql://solara_user:solara123@localhost:5432/solara_dashboard",
)
SUPABASE_URL = os.environ.get(
    "DATABASE_URL",
    "",
)

# ─────────────────────────────────────────────
# DDL — correct 12-table schema
# (mirrors the live local DB; replaces the old init_db.sql)
# ─────────────────────────────────────────────
SCHEMA_SQL = """
-- Drop old tables from init_db.sql schema (if they exist)
DROP TABLE IF EXISTS scraping_logs      CASCADE;
DROP TABLE IF EXISTS inventory_data     CASCADE;
DROP TABLE IF EXISTS sales_data         CASCADE;

-- Drop new tables in reverse-dependency order
DROP TABLE IF EXISTS import_logs            CASCADE;
DROP TABLE IF EXISTS monthly_ad_spend       CASCADE;
DROP TABLE IF EXISTS monthly_targets        CASCADE;
DROP TABLE IF EXISTS city_daily_sales       CASCADE;
DROP TABLE IF EXISTS daily_sales            CASCADE;
DROP TABLE IF EXISTS inventory_snapshots    CASCADE;
DROP TABLE IF EXISTS product_portal_mapping CASCADE;
DROP TABLE IF EXISTS warehouses             CASCADE;
DROP TABLE IF EXISTS products               CASCADE;
DROP TABLE IF EXISTS product_categories     CASCADE;
DROP TABLE IF EXISTS cities                 CASCADE;
DROP TABLE IF EXISTS portals                CASCADE;

-- ── Master ──────────────────────────────────────────────────────────────────

CREATE TABLE portals (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(50)  NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP
);

CREATE TABLE cities (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    state      VARCHAR(100),
    region     VARCHAR(50),
    is_active  BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP    NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX uq_cities_name_state ON cities (name, COALESCE(state, ''));

CREATE TABLE product_categories (
    id      SERIAL PRIMARY KEY,
    l1_name VARCHAR(100) NOT NULL,
    l2_name VARCHAR(100)
);
CREATE UNIQUE INDEX uq_product_categories_l1_l2 ON product_categories (l1_name, COALESCE(l2_name, ''));

-- ── Product ──────────────────────────────────────────────────────────────────

CREATE TABLE products (
    id           SERIAL PRIMARY KEY,
    sku_code     VARCHAR(100) NOT NULL UNIQUE,
    product_name VARCHAR(500) NOT NULL,
    category_id  INTEGER REFERENCES product_categories(id),
    default_asp  NUMERIC,
    unit_type    VARCHAR(50)  NOT NULL DEFAULT 'pieces',
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP
);

CREATE TABLE warehouses (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(200) NOT NULL,
    code       VARCHAR(100),
    portal_id  INTEGER REFERENCES portals(id),
    city_id    INTEGER REFERENCES cities(id),
    is_active  BOOLEAN   NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE product_portal_mapping (
    id                  SERIAL PRIMARY KEY,
    product_id          INTEGER      NOT NULL REFERENCES products(id),
    portal_id           INTEGER      NOT NULL REFERENCES portals(id),
    portal_sku          VARCHAR(500) NOT NULL,
    portal_product_name VARCHAR(500),
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP,
    CONSTRAINT product_portal_mapping_portal_id_portal_sku_key
        UNIQUE (portal_id, portal_sku)
);

-- ── Transactional ────────────────────────────────────────────────────────────

CREATE TABLE daily_sales (
    id          SERIAL PRIMARY KEY,
    portal_id   INTEGER      NOT NULL REFERENCES portals(id),
    product_id  INTEGER      NOT NULL REFERENCES products(id),
    sale_date   DATE         NOT NULL,
    units_sold  NUMERIC      NOT NULL DEFAULT 0,
    asp         NUMERIC,
    revenue     NUMERIC,
    data_source VARCHAR(30)  NOT NULL DEFAULT 'excel',
    imported_at TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT daily_sales_portal_id_product_id_sale_date_key
        UNIQUE (portal_id, product_id, sale_date)
);

CREATE INDEX idx_daily_sales_date         ON daily_sales (sale_date DESC);
CREATE INDEX idx_daily_sales_portal_date  ON daily_sales (portal_id, sale_date DESC);
CREATE INDEX idx_daily_sales_product_date ON daily_sales (product_id, sale_date DESC);

CREATE TABLE city_daily_sales (
    id              SERIAL PRIMARY KEY,
    portal_id       INTEGER      NOT NULL REFERENCES portals(id),
    product_id      INTEGER      NOT NULL REFERENCES products(id),
    city_id         INTEGER      NOT NULL REFERENCES cities(id),
    sale_date       DATE         NOT NULL,
    units_sold      NUMERIC      NOT NULL DEFAULT 0,
    mrp             NUMERIC,
    selling_price   NUMERIC,
    revenue         NUMERIC,
    discount_amount NUMERIC      DEFAULT 0,
    net_revenue     NUMERIC,
    order_count     INTEGER      DEFAULT 0,
    data_source     VARCHAR(30)  NOT NULL DEFAULT 'portal_csv',
    imported_at     TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT city_daily_sales_portal_id_product_id_city_id_sale_date_key
        UNIQUE (portal_id, product_id, city_id, sale_date)
);

CREATE INDEX idx_city_sales_date         ON city_daily_sales (sale_date DESC);
CREATE INDEX idx_city_sales_portal_city  ON city_daily_sales (portal_id, city_id, sale_date DESC);
CREATE INDEX idx_city_sales_product_date ON city_daily_sales (product_id, sale_date DESC);

CREATE TABLE inventory_snapshots (
    id             SERIAL PRIMARY KEY,
    portal_id      INTEGER   NOT NULL REFERENCES portals(id),
    product_id     INTEGER   NOT NULL REFERENCES products(id),
    snapshot_date  DATE      NOT NULL,
    portal_stock   NUMERIC,
    backend_stock  NUMERIC,
    frontend_stock NUMERIC,
    solara_stock   NUMERIC,
    amazon_fc_stock NUMERIC,
    open_po        NUMERIC,
    doc            NUMERIC,
    imported_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT inventory_snapshots_portal_id_product_id_snapshot_date_key
        UNIQUE (portal_id, product_id, snapshot_date)
);

CREATE INDEX idx_inv_portal_date  ON inventory_snapshots (portal_id, snapshot_date DESC);
CREATE INDEX idx_inv_product_date ON inventory_snapshots (product_id, snapshot_date DESC);

CREATE TABLE monthly_targets (
    id             SERIAL PRIMARY KEY,
    portal_id      INTEGER  NOT NULL REFERENCES portals(id),
    product_id     INTEGER  NOT NULL REFERENCES products(id),
    year           SMALLINT NOT NULL,
    month          SMALLINT NOT NULL,
    target_units   NUMERIC,
    target_revenue NUMERIC,
    target_drr     NUMERIC,
    achievement_pct NUMERIC,
    CONSTRAINT monthly_targets_portal_id_product_id_year_month_key
        UNIQUE (portal_id, product_id, year, month)
);

CREATE INDEX idx_targets_portal_period ON monthly_targets (portal_id, year, month);

CREATE TABLE monthly_ad_spend (
    id            SERIAL PRIMARY KEY,
    portal_id     INTEGER  NOT NULL REFERENCES portals(id),
    year          SMALLINT NOT NULL,
    month         SMALLINT NOT NULL,
    total_revenue NUMERIC,
    ad_spend      NUMERIC,
    tacos_pct     NUMERIC,
    CONSTRAINT monthly_ad_spend_portal_id_year_month_key
        UNIQUE (portal_id, year, month)
);

-- ── Audit ────────────────────────────────────────────────────────────────────

CREATE TABLE import_logs (
    id               SERIAL PRIMARY KEY,
    source_type      VARCHAR(30)  NOT NULL,
    portal_id        INTEGER REFERENCES portals(id),
    sheet_name       VARCHAR(200),
    file_name        VARCHAR(500),
    import_date      DATE         NOT NULL,
    start_time       TIMESTAMP    NOT NULL DEFAULT NOW(),
    end_time         TIMESTAMP,
    status           VARCHAR(20)  NOT NULL DEFAULT 'running',
    records_imported INTEGER      DEFAULT 0,
    error_message    TEXT,
    created_at       TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_import_logs_date   ON import_logs (import_date DESC);
CREATE INDEX idx_import_logs_portal ON import_logs (portal_id, import_date DESC);
"""

# Tables to copy in dependency order
TABLES = [
    "portals",
    "cities",
    "product_categories",
    "products",
    "warehouses",
    "product_portal_mapping",
    "daily_sales",
    "city_daily_sales",
    "inventory_snapshots",
    "monthly_targets",
    "monthly_ad_spend",
    "import_logs",
]

BATCH_SIZE = 5000


def get_columns(cur, table: str) -> list[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return [row[0] for row in cur.fetchall()]


def copy_table(src_cur, dst_cur, table: str) -> int:
    columns = get_columns(src_cur, table)
    col_list = ", ".join(f'"{c}"' for c in columns)

    src_cur.execute(f'SELECT COUNT(*) FROM "{table}"')
    total = src_cur.fetchone()[0]
    if total == 0:
        print(f"  {table}: 0 rows — skipped")
        return 0

    copied = 0
    src_cur.execute(f'SELECT {col_list} FROM "{table}" ORDER BY id')

    while True:
        rows = src_cur.fetchmany(BATCH_SIZE)
        if not rows:
            break
        execute_values(
            dst_cur,
            f'INSERT INTO "{table}" ({col_list}) VALUES %s ON CONFLICT DO NOTHING',
            rows,
        )
        copied += len(rows)
        print(f"  {table}: {copied}/{total} rows", end="\r")

    print(f"  {table}: {copied} rows copied" + " " * 20)
    return copied


def reset_sequences(dst_cur):
    """Reset all sequences to max(id)+1 so future inserts don't collide."""
    for table in TABLES:
        dst_cur.execute(
            f"""
            SELECT setval(
                pg_get_serial_sequence('{table}', 'id'),
                COALESCE(MAX(id), 0) + 1,
                false
            )
            FROM "{table}"
            """
        )


def main():
    parser = argparse.ArgumentParser(description="Replicate local DB to Supabase")
    parser.add_argument("--schema-only", action="store_true")
    parser.add_argument("--data-only", action="store_true")
    args = parser.parse_args()

    if not SUPABASE_URL:
        print("ERROR: DATABASE_URL env var is not set.")
        sys.exit(1)

    print("Connecting to local DB …")
    local_conn = psycopg2.connect(LOCAL_URL)
    local_conn.autocommit = True

    print("Connecting to Supabase …")
    supa_conn = psycopg2.connect(SUPABASE_URL)
    supa_conn.autocommit = False

    src_cur = local_conn.cursor()
    dst_cur = supa_conn.cursor()

    try:
        if not args.data_only:
            print("\n== Applying schema to Supabase ==")
            dst_cur.execute(SCHEMA_SQL)
            supa_conn.commit()
            print("Schema applied.")

        if not args.schema_only:
            print("\n== Copying data ==")
            total_rows = 0
            for table in TABLES:
                total_rows += copy_table(src_cur, dst_cur, table)

            print("\nResetting sequences …")
            reset_sequences(dst_cur)
            supa_conn.commit()
            print(f"\nDone. {total_rows:,} rows copied to Supabase.")

    except Exception as exc:
        supa_conn.rollback()
        print(f"\nERROR: {exc}")
        raise
    finally:
        src_cur.close()
        dst_cur.close()
        local_conn.close()
        supa_conn.close()


if __name__ == "__main__":
    main()
