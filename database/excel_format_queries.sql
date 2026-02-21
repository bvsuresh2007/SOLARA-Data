-- =============================================================================
-- SOLARA — Excel Format Queries
-- Replicates the layout of "SOLARA - Daily Sales Tracking FY 25-26"
-- directly inside pgAdmin.
--
-- CONTENTS
--   PART 1  Install the generator function (run once, entire block)
--   PART 2  How to use it — one portal, one month, daily columns
--   PART 3  Full-year monthly summary pivot (static, no function needed)
--   PART 4  All-portals combined view (current month, static)
-- =============================================================================


-- =============================================================================
-- PART 1 — Install generator function
-- =============================================================================
-- Select ALL lines from here to the closing semicolon (line ~80) and run once.
-- After that the function lives in your DB permanently.

CREATE OR REPLACE FUNCTION portal_daily_grid_sql(
    p_portal  TEXT,
    p_start   DATE DEFAULT DATE_TRUNC('month', CURRENT_DATE)::DATE,
    p_end     DATE DEFAULT CURRENT_DATE
)
RETURNS TEXT
LANGUAGE plpgsql
AS $BODY$
DECLARE
    v_date      DATE;
    v_date_cols TEXT := '';
    v_inv_col   TEXT;
    v_inv_label TEXT;
    v_sql       TEXT;
BEGIN
    -- Pick the right inventory column for this portal
    v_inv_col := CASE LOWER(p_portal)
        WHEN 'blinkit' THEN 'MAX(inv.backend_stock)'
        WHEN 'amazon'  THEN 'MAX(inv.solara_stock)'
        WHEN 'shopify' THEN 'NULL::numeric'
        ELSE                'MAX(inv.portal_stock)'
    END;

    v_inv_label := CASE LOWER(p_portal)
        WHEN 'zepto'    THEN 'Zepto WH Stock'
        WHEN 'swiggy'   THEN 'Swiggy Inventory'
        WHEN 'flipkart' THEN 'VC+FBF Inventory'
        WHEN 'myntra'   THEN 'Myntra Inventory'
        WHEN 'blinkit'  THEN 'Backend Stock'
        WHEN 'amazon'   THEN 'Solara WH'
        WHEN 'shopify'  THEN 'Inventory'
        ELSE                 'Stock'
    END;

    -- Build one column per date that has data in the DB for this portal
    FOR v_date IN
        SELECT DISTINCT ds.sale_date
        FROM   daily_sales ds
        JOIN   portals por ON por.id = ds.portal_id
        WHERE  LOWER(por.name) = LOWER(p_portal)
          AND  ds.sale_date BETWEEN p_start AND p_end
        ORDER  BY ds.sale_date
    LOOP
        v_date_cols := v_date_cols
            || E'\n    ,MAX(CASE WHEN ds.sale_date = '
            || quote_literal(v_date)
            || ' THEN ds.units_sold END) AS "'
            || TO_CHAR(v_date, 'DD-Mon-YY')
            || '"';
    END LOOP;

    -- Assemble the final SELECT using plain string concatenation (no nesting)
    v_sql :=
        'SELECT'
        || E'\n     p.sku_code                                                     AS "SKU Code"'
        || E'\n    ,p.product_name                                                 AS "Product Name"'
        || E'\n    ,COALESCE(pc.l2_name, ''-'')                                   AS "Category"'
        || E'\n    ,pm.portal_sku                                                  AS "Portal SKU"'
        || E'\n    ,ROUND(AVG(ds.asp) FILTER (WHERE ds.asp IS NOT NULL), 2)        AS "BAU ASP"'
        || E'\n    ,' || v_inv_col || ' AS "' || v_inv_label || '"'
        || v_date_cols
        || E'\n    ,COALESCE(SUM(ds.units_sold) FILTER (WHERE ds.units_sold > 0), 0)::INT   AS "MTD Units"'
        || E'\n    ,COALESCE(ROUND(SUM(ds.revenue) FILTER (WHERE ds.units_sold > 0), 0), 0) AS "MTD Value (Rs)"'
        || E'\nFROM products p'
        || E'\nJOIN product_portal_mapping pm  ON pm.product_id = p.id'
        || E'\nJOIN portals por               ON por.id = pm.portal_id'
        || E'\n                               AND LOWER(por.name) = ' || quote_literal(LOWER(p_portal))
        || E'\nLEFT JOIN product_categories pc ON pc.id = p.category_id'
        || E'\nLEFT JOIN daily_sales ds        ON  ds.product_id = p.id'
        || E'\n                               AND ds.portal_id   = por.id'
        || E'\n                               AND ds.sale_date BETWEEN '
            || quote_literal(p_start) || ' AND ' || quote_literal(p_end)
        || E'\nLEFT JOIN inventory_snapshots inv'
        || E'\n                                ON  inv.product_id = p.id'
        || E'\n                               AND inv.portal_id   = por.id'
        || E'\n                               AND inv.snapshot_date = ('
        || E'\n                                   SELECT MAX(snapshot_date)'
        || E'\n                                   FROM   inventory_snapshots'
        || E'\n                                   WHERE  portal_id  = por.id'
        || E'\n                                     AND  product_id = p.id'
        || E'\n                               )'
        || E'\nGROUP BY p.id, p.sku_code, p.product_name, pc.l2_name, pm.portal_sku'
        || E'\nHAVING COUNT(ds.id) > 0'
        || E'\nORDER BY "MTD Units" DESC NULLS LAST;';

    RETURN v_sql;
END;
$BODY$;


-- =============================================================================
-- PART 2 — How to use the generator
-- =============================================================================
-- Step 1: Run one SELECT below — it returns a single text cell containing SQL.
-- Step 2: Double-click the result cell in pgAdmin to see the full text.
-- Step 3: Copy all of it, open a NEW Query Tool tab, paste, and run.
--         The result table matches the corresponding Excel sheet exactly.
-- -----------------------------------------------------------------------------

-- Current month for each portal (defaults to today's month):
SELECT portal_daily_grid_sql('zepto');
SELECT portal_daily_grid_sql('swiggy');
SELECT portal_daily_grid_sql('blinkit');
SELECT portal_daily_grid_sql('myntra');
SELECT portal_daily_grid_sql('flipkart');
SELECT portal_daily_grid_sql('amazon');
SELECT portal_daily_grid_sql('shopify');

-- Specific month (pass start + end date):
SELECT portal_daily_grid_sql('zepto',    '2026-01-01', '2026-01-31');
SELECT portal_daily_grid_sql('amazon',   '2025-12-01', '2025-12-31');
SELECT portal_daily_grid_sql('blinkit',  '2025-11-01', '2025-11-30');
SELECT portal_daily_grid_sql('flipkart', '2025-10-01', '2025-10-31');
SELECT portal_daily_grid_sql('swiggy',   '2025-09-01', '2025-09-30');
SELECT portal_daily_grid_sql('myntra',   '2025-08-01', '2025-08-31');

-- Full history Apr-25 to latest date:
SELECT portal_daily_grid_sql('zepto',    '2025-04-01', CURRENT_DATE);
SELECT portal_daily_grid_sql('amazon',   '2025-04-01', CURRENT_DATE);
SELECT portal_daily_grid_sql('blinkit',  '2025-04-01', CURRENT_DATE);
SELECT portal_daily_grid_sql('flipkart', '2025-04-01', CURRENT_DATE);


-- =============================================================================
-- PART 3 — Full-year monthly summary pivot  (run directly, no function needed)
-- =============================================================================
-- One row per SKU x portal.
-- Columns: Portal | SKU | Product | Category | Portal SKU | BAU ASP |
--          Apr-25 | May-25 | Jun-25 | Jul-25 | Aug-25 | Sep-25 |
--          Oct-25 | Nov-25 | Dec-25 | Jan-26 | Feb-26 MTD |
--          FY Total Units | FY Total Revenue
--
-- This is the complete bird's-eye view of FY 25-26.
-- When a new month is added, copy one of the month blocks and update the dates.

SELECT
     por.display_name  AS "Portal"
    ,p.sku_code        AS "SKU Code"
    ,p.product_name    AS "Product Name"
    ,COALESCE(pc.l2_name, '-') AS "Category"
    ,pm.portal_sku     AS "Portal SKU"
    ,p.default_asp     AS "BAU ASP"
    ,COALESCE(SUM(ds.units_sold) FILTER (
        WHERE ds.sale_date BETWEEN '2025-04-01' AND '2025-04-30'
          AND ds.units_sold > 0), 0)::INT  AS "Apr-25"
    ,COALESCE(SUM(ds.units_sold) FILTER (
        WHERE ds.sale_date BETWEEN '2025-05-01' AND '2025-05-31'
          AND ds.units_sold > 0), 0)::INT  AS "May-25"
    ,COALESCE(SUM(ds.units_sold) FILTER (
        WHERE ds.sale_date BETWEEN '2025-06-01' AND '2025-06-30'
          AND ds.units_sold > 0), 0)::INT  AS "Jun-25"
    ,COALESCE(SUM(ds.units_sold) FILTER (
        WHERE ds.sale_date BETWEEN '2025-07-01' AND '2025-07-31'
          AND ds.units_sold > 0), 0)::INT  AS "Jul-25"
    ,COALESCE(SUM(ds.units_sold) FILTER (
        WHERE ds.sale_date BETWEEN '2025-08-01' AND '2025-08-31'
          AND ds.units_sold > 0), 0)::INT  AS "Aug-25"
    ,COALESCE(SUM(ds.units_sold) FILTER (
        WHERE ds.sale_date BETWEEN '2025-09-01' AND '2025-09-30'
          AND ds.units_sold > 0), 0)::INT  AS "Sep-25"
    ,COALESCE(SUM(ds.units_sold) FILTER (
        WHERE ds.sale_date BETWEEN '2025-10-01' AND '2025-10-31'
          AND ds.units_sold > 0), 0)::INT  AS "Oct-25"
    ,COALESCE(SUM(ds.units_sold) FILTER (
        WHERE ds.sale_date BETWEEN '2025-11-01' AND '2025-11-30'
          AND ds.units_sold > 0), 0)::INT  AS "Nov-25"
    ,COALESCE(SUM(ds.units_sold) FILTER (
        WHERE ds.sale_date BETWEEN '2025-12-01' AND '2025-12-31'
          AND ds.units_sold > 0), 0)::INT  AS "Dec-25"
    ,COALESCE(SUM(ds.units_sold) FILTER (
        WHERE ds.sale_date BETWEEN '2026-01-01' AND '2026-01-31'
          AND ds.units_sold > 0), 0)::INT  AS "Jan-26"
    ,COALESCE(SUM(ds.units_sold) FILTER (
        WHERE ds.sale_date BETWEEN '2026-02-01' AND '2026-02-28'
          AND ds.units_sold > 0), 0)::INT  AS "Feb-26 (MTD)"
    ,COALESCE(SUM(ds.units_sold) FILTER (
        WHERE ds.units_sold > 0), 0)::INT   AS "FY Total Units"
    ,COALESCE(ROUND(SUM(ds.revenue) FILTER (
        WHERE ds.units_sold > 0), 0), 0)    AS "FY Total Revenue (Rs)"
FROM products p
JOIN product_portal_mapping pm  ON pm.product_id = p.id
JOIN portals por                ON por.id = pm.portal_id
LEFT JOIN product_categories pc ON pc.id = p.category_id
LEFT JOIN daily_sales ds        ON  ds.product_id = p.id
                               AND ds.portal_id   = por.id
GROUP BY por.display_name, por.id, p.id, p.sku_code,
         p.product_name, pc.l2_name, pm.portal_sku, p.default_asp
HAVING COALESCE(SUM(ds.units_sold) FILTER (WHERE ds.units_sold > 0), 0) > 0
ORDER BY por.display_name, "FY Total Units" DESC;


-- =============================================================================
-- PART 4 — All portals, current month, daily columns  (run directly)
-- =============================================================================
-- Shows every active SKU x portal for Feb-26 with one column per day.
-- To use for a different month: change every date literal in this query.
-- Columns: Portal | SKU | Product Name | Category | Portal SKU | BAU ASP |
--          Stock | 01-Feb | 02-Feb | ... | 08-Feb | MTD Units | MTD Value

SELECT
     por.display_name  AS "Portal"
    ,p.sku_code        AS "SKU Code"
    ,p.product_name    AS "Product Name"
    ,COALESCE(pc.l2_name, '-') AS "Category"
    ,pm.portal_sku     AS "Portal SKU"
    ,ROUND(AVG(ds.asp) FILTER (WHERE ds.asp IS NOT NULL), 2) AS "BAU ASP"
    ,MAX(CASE
        WHEN LOWER(por.name) IN ('zepto','swiggy','flipkart','myntra')
             THEN inv.portal_stock
        WHEN LOWER(por.name) = 'blinkit' THEN inv.backend_stock
        WHEN LOWER(por.name) = 'amazon'  THEN inv.solara_stock
        ELSE NULL
     END)  AS "Stock"
    -- ── daily columns for Feb 2026 ──────────────────────────────────────────
    -- To change month: update all 8 dates below to the new month's dates
    ,MAX(CASE WHEN ds.sale_date = '2026-02-01' THEN ds.units_sold END) AS "01-Feb"
    ,MAX(CASE WHEN ds.sale_date = '2026-02-02' THEN ds.units_sold END) AS "02-Feb"
    ,MAX(CASE WHEN ds.sale_date = '2026-02-03' THEN ds.units_sold END) AS "03-Feb"
    ,MAX(CASE WHEN ds.sale_date = '2026-02-04' THEN ds.units_sold END) AS "04-Feb"
    ,MAX(CASE WHEN ds.sale_date = '2026-02-05' THEN ds.units_sold END) AS "05-Feb"
    ,MAX(CASE WHEN ds.sale_date = '2026-02-06' THEN ds.units_sold END) AS "06-Feb"
    ,MAX(CASE WHEN ds.sale_date = '2026-02-07' THEN ds.units_sold END) AS "07-Feb"
    ,MAX(CASE WHEN ds.sale_date = '2026-02-08' THEN ds.units_sold END) AS "08-Feb"
    -- ────────────────────────────────────────────────────────────────────────
    ,COALESCE(SUM(ds.units_sold) FILTER (WHERE ds.units_sold > 0), 0)::INT   AS "MTD Units"
    ,COALESCE(ROUND(SUM(ds.revenue) FILTER (WHERE ds.units_sold > 0), 0), 0) AS "MTD Value (Rs)"
FROM products p
JOIN product_portal_mapping pm  ON pm.product_id = p.id
JOIN portals por                ON por.id = pm.portal_id
LEFT JOIN product_categories pc ON pc.id = p.category_id
LEFT JOIN daily_sales ds        ON  ds.product_id = p.id
                               AND ds.portal_id   = por.id
                               -- change this range to match the month above:
                               AND ds.sale_date BETWEEN '2026-02-01' AND '2026-02-08'
LEFT JOIN inventory_snapshots inv
                                ON  inv.product_id = p.id
                               AND inv.portal_id   = por.id
                               AND inv.snapshot_date = (
                                   SELECT MAX(snapshot_date)
                                   FROM   inventory_snapshots
                                   WHERE  portal_id  = por.id
                                     AND  product_id = p.id
                               )
GROUP BY por.display_name, p.id, p.sku_code, p.product_name,
         pc.l2_name, pm.portal_sku
HAVING COUNT(ds.id) > 0
ORDER BY por.display_name, "MTD Units" DESC;
