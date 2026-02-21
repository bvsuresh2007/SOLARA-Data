-- =============================================================================
-- SolaraDashboard — Schema v2
-- 12-table schema redesigned from real portal data (Apr 2025 – Feb 2026)
-- Future-proof: add any new monthly Excel → upsert handles it automatically
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- DIMENSION TABLES
-- =============================================================================

CREATE TABLE IF NOT EXISTS portals (
    id           SERIAL      PRIMARY KEY,
    name         VARCHAR(50) UNIQUE NOT NULL,   -- slug: 'zepto', 'swiggy', etc.
    display_name VARCHAR(100) NOT NULL,
    is_active    BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cities (
    id         SERIAL       PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    state      VARCHAR(100),
    region     VARCHAR(50),    -- 'North' | 'South' | 'East' | 'West'
    is_active  BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP    NOT NULL DEFAULT NOW()
);
-- Expression-based unique index (COALESCE not allowed inside UNIQUE constraint)
CREATE UNIQUE INDEX IF NOT EXISTS uq_cities_name_state
    ON cities (name, COALESCE(state, ''));

CREATE TABLE IF NOT EXISTS product_categories (
    id      SERIAL       PRIMARY KEY,
    l1_name VARCHAR(100) NOT NULL,   -- e.g. 'Kitchen & Dining'
    l2_name VARCHAR(100)             -- e.g. 'Air Fryer', 'Water Bottles'
);
-- Expression-based unique index (COALESCE not allowed inside UNIQUE constraint)
CREATE UNIQUE INDEX IF NOT EXISTS uq_product_categories_l1_l2
    ON product_categories (l1_name, COALESCE(l2_name, ''));

CREATE TABLE IF NOT EXISTS warehouses (
    id         SERIAL       PRIMARY KEY,
    name       VARCHAR(200) NOT NULL,
    code       VARCHAR(100),
    portal_id  INTEGER REFERENCES portals(id)  ON DELETE SET NULL,
    city_id    INTEGER REFERENCES cities(id)   ON DELETE SET NULL,
    is_active  BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- PRODUCT TABLES
-- =============================================================================

CREATE TABLE IF NOT EXISTS products (
    id           SERIAL       PRIMARY KEY,
    sku_code     VARCHAR(100) UNIQUE NOT NULL,   -- e.g. 'SOL-AF-124'
    product_name VARCHAR(500) NOT NULL,
    category_id  INTEGER REFERENCES product_categories(id) ON DELETE SET NULL,
    default_asp  NUMERIC(10, 2),                 -- BAU ASP (fallback for revenue calc)
    unit_type    VARCHAR(50)  NOT NULL DEFAULT 'pieces',
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_portal_mapping (
    id                  SERIAL       PRIMARY KEY,
    product_id          INTEGER      NOT NULL REFERENCES products(id)  ON DELETE CASCADE,
    portal_id           INTEGER      NOT NULL REFERENCES portals(id)   ON DELETE CASCADE,
    -- Portal-specific identifier (ASIN / Swiggy Code / Style ID / FSN / EAN / SKU)
    portal_sku          VARCHAR(500) NOT NULL,
    portal_product_name VARCHAR(500),
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP,
    UNIQUE (portal_id, portal_sku)
);

-- =============================================================================
-- SALES FACT TABLES (two grains)
-- =============================================================================

-- Grain: (portal, product, date) — from master Excel daily columns
-- This is the PRIMARY daily sales table. No city — portal-level aggregate.
CREATE TABLE IF NOT EXISTS daily_sales (
    id          SERIAL         PRIMARY KEY,
    portal_id   INTEGER        NOT NULL REFERENCES portals(id),
    product_id  INTEGER        NOT NULL REFERENCES products(id),
    sale_date   DATE           NOT NULL,
    units_sold  NUMERIC(12, 2) NOT NULL DEFAULT 0,  -- can be negative (returns/refunds)
    asp         NUMERIC(10, 2),                    -- avg selling price for this day
    revenue     NUMERIC(14, 2),                    -- units_sold × asp (stored explicitly)
    data_source VARCHAR(30)    NOT NULL DEFAULT 'excel',  -- 'excel' | 'scraper'
    imported_at TIMESTAMP      NOT NULL DEFAULT NOW(),
    UNIQUE (portal_id, product_id, sale_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_sales_date         ON daily_sales (sale_date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_sales_portal_date  ON daily_sales (portal_id, sale_date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_sales_product_date ON daily_sales (product_id, sale_date DESC);

-- Grain: (portal, product, city, date) — from portal CSV exports
-- Supplementary city-level detail. Used for geo-breakdown in dashboard.
CREATE TABLE IF NOT EXISTS city_daily_sales (
    id              SERIAL         PRIMARY KEY,
    portal_id       INTEGER        NOT NULL REFERENCES portals(id),
    product_id      INTEGER        NOT NULL REFERENCES products(id),
    city_id         INTEGER        NOT NULL REFERENCES cities(id),
    sale_date       DATE           NOT NULL,
    units_sold      NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (units_sold >= 0),
    mrp             NUMERIC(10, 2),             -- max retail price
    selling_price   NUMERIC(10, 2),             -- actual price charged
    revenue         NUMERIC(14, 2),             -- GMV (units × mrp)
    discount_amount NUMERIC(12, 2) DEFAULT 0,
    net_revenue     NUMERIC(14, 2),             -- units × selling_price
    order_count     INTEGER        DEFAULT 0,
    data_source     VARCHAR(30)    NOT NULL DEFAULT 'portal_csv',
    imported_at     TIMESTAMP      NOT NULL DEFAULT NOW(),
    UNIQUE (portal_id, product_id, city_id, sale_date)
);

CREATE INDEX IF NOT EXISTS idx_city_sales_date          ON city_daily_sales (sale_date DESC);
CREATE INDEX IF NOT EXISTS idx_city_sales_portal_city   ON city_daily_sales (portal_id, city_id, sale_date DESC);
CREATE INDEX IF NOT EXISTS idx_city_sales_product_date  ON city_daily_sales (product_id, sale_date DESC);

-- =============================================================================
-- INVENTORY TABLE
-- =============================================================================

-- Grain: (portal, product, snapshot_date) — one snapshot per portal per SKU per month-end
-- Covers: portal WH, Solara WH, Amazon FC, Blinkit backend/frontend, planning metrics
CREATE TABLE IF NOT EXISTS inventory_snapshots (
    id              SERIAL         PRIMARY KEY,
    portal_id       INTEGER        NOT NULL REFERENCES portals(id),
    product_id      INTEGER        NOT NULL REFERENCES products(id),
    snapshot_date   DATE           NOT NULL,    -- last day of reporting month (or last data date)
    -- Portal warehouse stock
    portal_stock    NUMERIC(12, 2),             -- Zepto WH / Swiggy / Myntra / Flipkart stock
    backend_stock   NUMERIC(12, 2),             -- Blinkit: backend inventory
    frontend_stock  NUMERIC(12, 2),             -- Blinkit: frontend inventory
    -- Solara's own warehouse
    solara_stock    NUMERIC(12, 2),             -- Inventory in Solara WH (Amazon + Summary)
    amazon_fc_stock NUMERIC(12, 2),             -- Amazon fulfillment center stock
    -- Planning metrics
    open_po         NUMERIC(12, 2),             -- open purchase orders (units)
    doc             NUMERIC(8, 2),              -- days of coverage
    imported_at     TIMESTAMP      NOT NULL DEFAULT NOW(),
    UNIQUE (portal_id, product_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_inv_portal_date   ON inventory_snapshots (portal_id, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_inv_product_date  ON inventory_snapshots (product_id, snapshot_date DESC);

-- =============================================================================
-- TARGETS TABLE (Amazon primarily; extensible to other portals)
-- =============================================================================

CREATE TABLE IF NOT EXISTS monthly_targets (
    id              SERIAL         PRIMARY KEY,
    portal_id       INTEGER        NOT NULL REFERENCES portals(id),
    product_id      INTEGER        NOT NULL REFERENCES products(id),
    year            SMALLINT       NOT NULL,
    month           SMALLINT       NOT NULL CHECK (month BETWEEN 1 AND 12),
    target_units    NUMERIC(12, 2),
    target_revenue  NUMERIC(14, 2),
    target_drr      NUMERIC(10, 2),    -- target daily run rate
    achievement_pct NUMERIC(8, 4),     -- % achieved vs target (decimal, e.g. 1.048 = 104.8%)
    UNIQUE (portal_id, product_id, year, month)
);

CREATE INDEX IF NOT EXISTS idx_targets_portal_period ON monthly_targets (portal_id, year, month);

-- =============================================================================
-- AD SPEND TABLE
-- =============================================================================

-- TACOS and ad spend at (portal, month) grain
-- Source: 'Total Revenue' and 'Total Ad Spend' rows at the bottom of each portal sheet
CREATE TABLE IF NOT EXISTS monthly_ad_spend (
    id            SERIAL         PRIMARY KEY,
    portal_id     INTEGER        NOT NULL REFERENCES portals(id),
    year          SMALLINT       NOT NULL,
    month         SMALLINT       NOT NULL CHECK (month BETWEEN 1 AND 12),
    total_revenue NUMERIC(14, 2),
    ad_spend      NUMERIC(14, 2),
    tacos_pct     NUMERIC(8, 4),    -- TACOS % (ad_spend / total_revenue × 100)
    UNIQUE (portal_id, year, month)
);

-- =============================================================================
-- IMPORT LOG (replaces scraping_logs — covers both Excel imports & scrapers)
-- =============================================================================

CREATE TABLE IF NOT EXISTS import_logs (
    id               SERIAL       PRIMARY KEY,
    source_type      VARCHAR(30)  NOT NULL,   -- 'excel_import' | 'portal_scraper' | 'portal_csv'
    portal_id        INTEGER      REFERENCES portals(id),
    sheet_name       VARCHAR(200),            -- which Excel sheet was imported
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

CREATE INDEX IF NOT EXISTS idx_import_logs_date   ON import_logs (import_date DESC);
CREATE INDEX IF NOT EXISTS idx_import_logs_portal ON import_logs (portal_id, import_date DESC);

-- =============================================================================
-- SEED DATA
-- =============================================================================

INSERT INTO portals (name, display_name) VALUES
    ('zepto',    'Zepto'),
    ('swiggy',   'Swiggy'),
    ('blinkit',  'Blinkit'),
    ('myntra',   'Myntra'),
    ('flipkart', 'Flipkart'),
    ('amazon',   'Amazon'),
    ('shopify',  'Shopify')
ON CONFLICT (name) DO NOTHING;
