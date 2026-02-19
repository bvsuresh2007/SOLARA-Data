-- =============================================================================
-- SolaraDashboard - Initial Database Schema
-- 9-table optimised schema for multi-portal sales & inventory tracking
-- =============================================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- MASTER DATA TABLES
-- =============================================================================

CREATE TABLE IF NOT EXISTS portals (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(50)  UNIQUE NOT NULL,  -- 'swiggy', 'blinkit', 'amazon', etc.
    display_name VARCHAR(100) NOT NULL,
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cities (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    state       VARCHAR(100),
    region      VARCHAR(50),                   -- 'North', 'South', 'East', 'West'
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP,
    UNIQUE (name, state)
);

CREATE TABLE IF NOT EXISTS warehouses (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    code        VARCHAR(100),
    portal_id   INTEGER REFERENCES portals(id) ON DELETE SET NULL,
    city_id     INTEGER REFERENCES cities(id)  ON DELETE SET NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_categories (
    id          SERIAL PRIMARY KEY,
    l1_name     VARCHAR(100) NOT NULL,          -- Top-level  (e.g. "Kitchen and dining")
    l2_name     VARCHAR(100),                   -- Mid-level  (e.g. "Flasks jugs tiffins")
    l3_name     VARCHAR(100),                   -- Leaf-level (e.g. "Thermos flasks")
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (l1_name, l2_name, l3_name)
);

-- =============================================================================
-- PRODUCT TABLES
-- =============================================================================

CREATE TABLE IF NOT EXISTS products (
    id              SERIAL PRIMARY KEY,
    sku_code        VARCHAR(100) UNIQUE NOT NULL,  -- Internal Solara SKU
    product_name    VARCHAR(255) NOT NULL,
    category_id     INTEGER REFERENCES product_categories(id) ON DELETE SET NULL,
    unit_type       VARCHAR(50),                    -- 'kg', 'liters', 'pieces'
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_portal_mapping (
    id              SERIAL PRIMARY KEY,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    portal_id       INTEGER NOT NULL REFERENCES portals(id)  ON DELETE CASCADE,
    portal_product_id VARCHAR(200) NOT NULL,         -- ASIN / item_id / SKU_Number / ITEM_CODE
    portal_product_name VARCHAR(255),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP,
    UNIQUE (portal_id, portal_product_id)
);

-- =============================================================================
-- TRANSACTION TABLES
-- =============================================================================

CREATE TABLE IF NOT EXISTS sales_data (
    id              SERIAL PRIMARY KEY,
    portal_id       INTEGER NOT NULL REFERENCES portals(id),
    city_id         INTEGER REFERENCES cities(id),
    product_id      INTEGER NOT NULL REFERENCES products(id),
    sale_date       DATE    NOT NULL,
    quantity_sold   DECIMAL(12, 2) NOT NULL DEFAULT 0 CHECK (quantity_sold >= 0),
    revenue         DECIMAL(12, 2) NOT NULL DEFAULT 0 CHECK (revenue >= 0),
    discount_amount DECIMAL(12, 2) NOT NULL DEFAULT 0,
    net_revenue     DECIMAL(12, 2) NOT NULL DEFAULT 0,
    order_count     INTEGER DEFAULT 0,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP,
    UNIQUE (portal_id, city_id, product_id, sale_date)
);

CREATE INDEX IF NOT EXISTS idx_sales_date_portal_city  ON sales_data (sale_date, portal_id, city_id);
CREATE INDEX IF NOT EXISTS idx_sales_product_date      ON sales_data (product_id, sale_date);

CREATE TABLE IF NOT EXISTS inventory_data (
    id                  SERIAL PRIMARY KEY,
    portal_id           INTEGER NOT NULL REFERENCES portals(id),
    city_id             INTEGER REFERENCES cities(id),
    warehouse_id        INTEGER REFERENCES warehouses(id),
    product_id          INTEGER NOT NULL REFERENCES products(id),
    snapshot_date       DATE    NOT NULL,
    stock_quantity      DECIMAL(12, 2) NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    reserved_quantity   DECIMAL(12, 2) NOT NULL DEFAULT 0,
    available_quantity  DECIMAL(12, 2) NOT NULL DEFAULT 0 CHECK (available_quantity >= 0),
    -- Amazon-specific vendor metrics
    unsellable_units    DECIMAL(12, 2),
    aged_90_plus_units  DECIMAL(12, 2),
    oos_percentage      DECIMAL(5, 2),
    lead_time_days      INTEGER,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP,
    UNIQUE (portal_id, warehouse_id, product_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_inv_date_portal_city ON inventory_data (snapshot_date, portal_id, city_id);
CREATE INDEX IF NOT EXISTS idx_inv_product_date     ON inventory_data (product_id, snapshot_date);

-- =============================================================================
-- AUDIT TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS scraping_logs (
    id                  SERIAL PRIMARY KEY,
    portal_id           INTEGER REFERENCES portals(id),
    scrape_date         DATE    NOT NULL,
    start_time          TIMESTAMP NOT NULL DEFAULT NOW(),
    end_time            TIMESTAMP,
    status              VARCHAR(20) NOT NULL DEFAULT 'running'  -- 'running', 'success', 'failed', 'partial'
                            CHECK (status IN ('running', 'success', 'failed', 'partial')),
    records_processed   INTEGER DEFAULT 0,
    error_message       TEXT,
    file_path           VARCHAR(500),
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_logs_date_portal_status ON scraping_logs (scrape_date, portal_id, status);

-- =============================================================================
-- SEED DATA
-- =============================================================================

INSERT INTO portals (name, display_name) VALUES
    ('swiggy',   'Swiggy'),
    ('blinkit',  'Blinkit'),
    ('amazon',   'Amazon'),
    ('zepto',    'Zepto'),
    ('shopify',  'Shopify'),
    ('myntra',   'Myntra'),
    ('flipkart', 'Flipkart')
ON CONFLICT (name) DO NOTHING;
