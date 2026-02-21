-- =============================================================================
-- SOLARA DASHBOARD — pgAdmin Query Bank
-- Copy any query below into pgAdmin's Query Tool and run.
-- All queries are read-only (no data modification).
-- =============================================================================
-- SECTIONS:
--   A. Data Understanding   (A1–A8)
--   B. Sales Analysis       (B1–B10)
--   C. Discrepancy Checks   (C1–C8)
--   D. Sales Dashboard      (D1–D10)
-- =============================================================================


-- =============================================================================
-- A. DATA UNDERSTANDING
-- =============================================================================

-- A1. Overview: row counts for every table
-- Quick snapshot of how much data you have across the whole schema.
SELECT 'portals'                AS table_name, COUNT(*) AS row_count FROM portals
UNION ALL SELECT 'products',               COUNT(*) FROM products
UNION ALL SELECT 'product_categories',     COUNT(*) FROM product_categories
UNION ALL SELECT 'product_portal_mapping', COUNT(*) FROM product_portal_mapping
UNION ALL SELECT 'daily_sales',            COUNT(*) FROM daily_sales
UNION ALL SELECT 'inventory_snapshots',    COUNT(*) FROM inventory_snapshots
UNION ALL SELECT 'monthly_targets',        COUNT(*) FROM monthly_targets
UNION ALL SELECT 'monthly_ad_spend',       COUNT(*) FROM monthly_ad_spend
UNION ALL SELECT 'import_logs',            COUNT(*) FROM import_logs
ORDER BY row_count DESC;


-- A2. All products with their category and default ASP
-- Use this to browse the product catalogue and spot missing categories / ASPs.
SELECT
    p.sku_code,
    p.product_name,
    pc.l2_name            AS category,
    p.default_asp         AS bau_asp,
    p.created_at::date    AS added_on
FROM products p
LEFT JOIN product_categories pc ON pc.id = p.category_id
ORDER BY pc.l2_name, p.sku_code;


-- A3. Portal coverage per SKU
-- How many portals is each SKU listed on?
-- SKUs on only 1 portal may represent distribution gaps.
SELECT
    p.sku_code,
    LEFT(p.product_name, 50)     AS product_name,
    COUNT(DISTINCT pm.portal_id) AS portal_count,
    STRING_AGG(por.name, ', ' ORDER BY por.name) AS portals
FROM products p
LEFT JOIN product_portal_mapping pm ON pm.product_id = p.id
LEFT JOIN portals por ON por.id = pm.portal_id
GROUP BY p.id, p.sku_code, p.product_name
ORDER BY portal_count DESC, p.sku_code;


-- A4. Date range and data density per portal
-- Shows how many days of data exist per portal and the coverage period.
SELECT
    por.display_name         AS portal,
    MIN(ds.sale_date)        AS earliest_date,
    MAX(ds.sale_date)        AS latest_date,
    COUNT(DISTINCT ds.sale_date) AS days_with_data,
    COUNT(DISTINCT ds.product_id) AS distinct_skus,
    COUNT(*)                 AS total_rows
FROM daily_sales ds
JOIN portals por ON por.id = ds.portal_id
GROUP BY por.display_name
ORDER BY por.display_name;


-- A5. Sales data completeness by portal + month
-- Shows how many SKU-days exist in each portal/month.
-- Months with unusually low counts may have import issues.
SELECT
    por.display_name           AS portal,
    TO_CHAR(ds.sale_date, 'YYYY-MM') AS month,
    COUNT(DISTINCT ds.product_id)    AS active_skus,
    COUNT(DISTINCT ds.sale_date)     AS days_in_data,
    COUNT(*)                         AS sku_day_rows,
    SUM(ds.units_sold)::int          AS total_units
FROM daily_sales ds
JOIN portals por ON por.id = ds.portal_id
GROUP BY por.display_name, TO_CHAR(ds.sale_date, 'YYYY-MM')
ORDER BY month DESC, por.display_name;


-- A6. Import log — most recent imports
-- See what was imported, when, and whether it succeeded or failed.
SELECT
    il.import_date,
    por.display_name   AS portal,
    il.sheet_name,
    il.status,
    il.records_imported,
    il.start_time::time AS started,
    il.end_time::time   AS ended,
    il.error_message
FROM import_logs il
LEFT JOIN portals por ON por.id = il.portal_id
ORDER BY il.import_date DESC, il.start_time DESC
LIMIT 50;


-- A7. Products that have never sold on a given portal
-- Change the portal name in the WHERE clause to check any portal.
-- Lists SKUs that are mapped to a portal but have zero sales there.
SELECT
    p.sku_code,
    LEFT(p.product_name, 60) AS product_name
FROM products p
JOIN product_portal_mapping pm ON pm.product_id = p.id
JOIN portals por ON por.id = pm.portal_id
WHERE por.name = 'amazon'   -- ← change portal here
  AND NOT EXISTS (
        SELECT 1 FROM daily_sales ds
        WHERE ds.product_id = p.id
          AND ds.portal_id  = por.id
  )
ORDER BY p.sku_code;


-- A8. Sample raw rows — browse what was imported for one portal
-- Useful sanity check. Change portal and date to inspect any window.
SELECT
    p.sku_code,
    LEFT(p.product_name, 45) AS product_name,
    ds.sale_date,
    ds.units_sold,
    ds.asp,
    ds.revenue
FROM daily_sales ds
JOIN products p ON p.id = ds.product_id
JOIN portals por ON por.id = ds.portal_id
WHERE por.name    = 'zepto'           -- ← change portal
  AND ds.sale_date BETWEEN '2026-01-01' AND '2026-01-31'  -- ← change dates
ORDER BY ds.sale_date, p.sku_code
LIMIT 200;


-- =============================================================================
-- B. SALES ANALYSIS
-- =============================================================================

-- B1. Monthly totals by portal — units and revenue
-- The core summary view. Shows how each portal performed each month.
SELECT
    TO_CHAR(ds.sale_date, 'YYYY-MM')  AS month,
    por.display_name                  AS portal,
    SUM(ds.units_sold)::int           AS total_units,
    ROUND(SUM(ds.revenue), 0)         AS total_revenue,
    ROUND(AVG(ds.asp), 2)             AS avg_asp,
    COUNT(DISTINCT ds.product_id)     AS active_skus
FROM daily_sales ds
JOIN portals por ON por.id = ds.portal_id
WHERE ds.units_sold > 0
GROUP BY TO_CHAR(ds.sale_date, 'YYYY-MM'), por.display_name
ORDER BY month DESC, total_units DESC;


-- B2. Daily sales trend — last 30 days across all portals
-- Good for spotting spikes, drops, or missing days in recent data.
SELECT
    ds.sale_date,
    por.display_name                AS portal,
    SUM(ds.units_sold)::int         AS units,
    ROUND(SUM(ds.revenue), 0)       AS revenue
FROM daily_sales ds
JOIN portals por ON por.id = ds.portal_id
WHERE ds.sale_date >= CURRENT_DATE - INTERVAL '30 days'
  AND ds.units_sold > 0
GROUP BY ds.sale_date, por.display_name
ORDER BY ds.sale_date DESC, por.display_name;


-- B3. Top 20 SKUs by total units sold (all time, all portals)
-- Identifies your best-performing products.
SELECT
    p.sku_code,
    LEFT(p.product_name, 55)         AS product_name,
    pc.l2_name                       AS category,
    SUM(ds.units_sold)::int          AS total_units,
    ROUND(SUM(ds.revenue), 0)        AS total_revenue,
    ROUND(AVG(ds.asp), 2)            AS avg_asp,
    COUNT(DISTINCT ds.portal_id)     AS portal_count
FROM daily_sales ds
JOIN products p ON p.id = ds.product_id
LEFT JOIN product_categories pc ON pc.id = p.category_id
WHERE ds.units_sold > 0
GROUP BY p.id, p.sku_code, p.product_name, pc.l2_name
ORDER BY total_units DESC
LIMIT 20;


-- B4. Portal revenue share — current month (MTD)
-- Pie/donut chart data. Shows which portals are driving revenue right now.
WITH mtd AS (
    SELECT
        por.display_name                 AS portal,
        SUM(ds.units_sold)::int          AS units,
        ROUND(SUM(ds.revenue), 0)        AS revenue
    FROM daily_sales ds
    JOIN portals por ON por.id = ds.portal_id
    WHERE ds.sale_date >= DATE_TRUNC('month', CURRENT_DATE)
      AND ds.units_sold > 0
    GROUP BY por.display_name
)
SELECT
    portal,
    units,
    revenue,
    ROUND(100.0 * revenue / NULLIF(SUM(revenue) OVER (), 0), 1) AS revenue_share_pct,
    ROUND(100.0 * units  / NULLIF(SUM(units)    OVER (), 0), 1) AS units_share_pct
FROM mtd
ORDER BY revenue DESC;


-- B5. Month-over-month growth by portal
-- Compares current month MTD vs same number of days last month.
-- Controls for partial month bias.
WITH day_of_month AS (SELECT EXTRACT(DAY FROM CURRENT_DATE)::int AS d),
current_month AS (
    SELECT por.display_name AS portal,
           SUM(ds.units_sold)::int AS units,
           ROUND(SUM(ds.revenue), 0) AS revenue
    FROM daily_sales ds
    JOIN portals por ON por.id = ds.portal_id
    CROSS JOIN day_of_month dom
    WHERE ds.sale_date >= DATE_TRUNC('month', CURRENT_DATE)
      AND EXTRACT(DAY FROM ds.sale_date) <= dom.d
    GROUP BY por.display_name
),
last_month AS (
    SELECT por.display_name AS portal,
           SUM(ds.units_sold)::int AS units,
           ROUND(SUM(ds.revenue), 0) AS revenue
    FROM daily_sales ds
    JOIN portals por ON por.id = ds.portal_id
    CROSS JOIN day_of_month dom
    WHERE ds.sale_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'
      AND ds.sale_date <  DATE_TRUNC('month', CURRENT_DATE)
      AND EXTRACT(DAY FROM ds.sale_date) <= dom.d
    GROUP BY por.display_name
)
SELECT
    COALESCE(c.portal, l.portal)    AS portal,
    COALESCE(l.units, 0)            AS last_month_units,
    COALESCE(c.units, 0)            AS this_month_units,
    COALESCE(c.units, 0) - COALESCE(l.units, 0) AS unit_delta,
    CASE WHEN COALESCE(l.units, 0) > 0
         THEN ROUND(100.0 * (COALESCE(c.units,0) - COALESCE(l.units,0))
                          / l.units, 1)
    END                             AS units_growth_pct,
    COALESCE(l.revenue, 0)          AS last_month_revenue,
    COALESCE(c.revenue, 0)          AS this_month_revenue
FROM current_month c
FULL JOIN last_month l USING (portal)
ORDER BY this_month_units DESC;


-- B6. Daily run rate (DRR) — actual vs target (Amazon)
-- Shows how Amazon is pacing against monthly targets.
WITH days_elapsed AS (
    SELECT EXTRACT(DAY FROM CURRENT_DATE)::numeric AS d
),
actuals AS (
    SELECT
        ds.product_id,
        SUM(ds.units_sold)    AS mtd_units,
        ROUND(SUM(ds.revenue), 0) AS mtd_revenue
    FROM daily_sales ds
    JOIN portals por ON por.id = ds.portal_id
    WHERE por.name = 'amazon'
      AND ds.sale_date >= DATE_TRUNC('month', CURRENT_DATE)
    GROUP BY ds.product_id
),
targets AS (
    SELECT
        mt.product_id,
        mt.target_units,
        mt.target_revenue,
        mt.target_drr
    FROM monthly_targets mt
    JOIN portals por ON por.id = mt.portal_id
    WHERE por.name = 'amazon'
      AND mt.year  = EXTRACT(YEAR  FROM CURRENT_DATE)
      AND mt.month = EXTRACT(MONTH FROM CURRENT_DATE)
)
SELECT
    p.sku_code,
    LEFT(p.product_name, 45)                       AS product_name,
    t.target_units,
    a.mtd_units,
    ROUND(a.mtd_units / NULLIF(de.d, 0), 1)        AS actual_drr,
    t.target_drr,
    ROUND(100.0 * a.mtd_units / NULLIF(t.target_units, 0), 1) AS achievement_pct
FROM targets t
JOIN products p ON p.id = t.product_id
CROSS JOIN days_elapsed de
LEFT JOIN actuals a ON a.product_id = t.product_id
WHERE t.target_units > 0
ORDER BY achievement_pct ASC NULLS LAST;


-- B7. Per-SKU performance across portals — current month
-- Heatmap source: shows units sold per SKU for each portal side by side.
SELECT
    p.sku_code,
    LEFT(p.product_name, 45)                                    AS product_name,
    COALESCE(SUM(CASE WHEN por.name='zepto'    THEN ds.units_sold END), 0)::int AS zepto,
    COALESCE(SUM(CASE WHEN por.name='swiggy'   THEN ds.units_sold END), 0)::int AS swiggy,
    COALESCE(SUM(CASE WHEN por.name='blinkit'  THEN ds.units_sold END), 0)::int AS blinkit,
    COALESCE(SUM(CASE WHEN por.name='myntra'   THEN ds.units_sold END), 0)::int AS myntra,
    COALESCE(SUM(CASE WHEN por.name='flipkart' THEN ds.units_sold END), 0)::int AS flipkart,
    COALESCE(SUM(CASE WHEN por.name='amazon'   THEN ds.units_sold END), 0)::int AS amazon,
    COALESCE(SUM(CASE WHEN por.name='shopify'  THEN ds.units_sold END), 0)::int AS shopify,
    SUM(ds.units_sold)::int                                     AS all_portals
FROM daily_sales ds
JOIN products p ON p.id = ds.product_id
JOIN portals por ON por.id = ds.portal_id
WHERE ds.sale_date >= DATE_TRUNC('month', CURRENT_DATE)
  AND ds.units_sold > 0
GROUP BY p.id, p.sku_code, p.product_name
ORDER BY all_portals DESC;


-- B8. Weekly sales trend — last 12 weeks
-- Smooths out day-of-week effects. Good for spotting real growth/decline.
SELECT
    DATE_TRUNC('week', ds.sale_date)::date    AS week_start,
    por.display_name                          AS portal,
    SUM(ds.units_sold)::int                   AS weekly_units,
    ROUND(SUM(ds.revenue), 0)                 AS weekly_revenue
FROM daily_sales ds
JOIN portals por ON por.id = ds.portal_id
WHERE ds.sale_date >= CURRENT_DATE - INTERVAL '12 weeks'
  AND ds.units_sold > 0
GROUP BY DATE_TRUNC('week', ds.sale_date), por.display_name
ORDER BY week_start DESC, weekly_units DESC;


-- B9. Category-level monthly performance
-- Roll-up view: how is each product category trending?
SELECT
    TO_CHAR(ds.sale_date, 'YYYY-MM') AS month,
    COALESCE(pc.l2_name, 'Uncategorised') AS category,
    SUM(ds.units_sold)::int          AS total_units,
    ROUND(SUM(ds.revenue), 0)        AS total_revenue,
    COUNT(DISTINCT ds.product_id)    AS active_skus
FROM daily_sales ds
JOIN products p ON p.id = ds.product_id
LEFT JOIN product_categories pc ON pc.id = p.category_id
WHERE ds.units_sold > 0
GROUP BY TO_CHAR(ds.sale_date, 'YYYY-MM'), pc.l2_name
ORDER BY month DESC, total_units DESC;


-- B10. Returns / negative sales — which SKUs & portals have them
-- Negative units_sold = return or reversal recorded in the Excel.
SELECT
    por.display_name                         AS portal,
    p.sku_code,
    LEFT(p.product_name, 50)                 AS product_name,
    ds.sale_date,
    ds.units_sold                            AS return_units,
    ds.asp,
    ds.revenue
FROM daily_sales ds
JOIN portals por ON por.id = ds.portal_id
JOIN products p   ON p.id  = ds.product_id
WHERE ds.units_sold < 0
ORDER BY ds.sale_date DESC, ds.units_sold ASC;


-- =============================================================================
-- C. DISCREPANCY CHECKS
-- =============================================================================

-- C1. Products with no sales at all (ever)
-- These SKUs exist in the catalogue but have never sold on any portal.
-- Could be newly listed, discontinued, or a mapping problem.
SELECT
    p.sku_code,
    LEFT(p.product_name, 60)     AS product_name,
    p.default_asp,
    STRING_AGG(por.name, ', ' ORDER BY por.name) AS mapped_portals
FROM products p
LEFT JOIN product_portal_mapping pm ON pm.product_id = p.id
LEFT JOIN portals por ON por.id = pm.portal_id
WHERE NOT EXISTS (
    SELECT 1 FROM daily_sales ds WHERE ds.product_id = p.id
)
GROUP BY p.id, p.sku_code, p.product_name, p.default_asp
ORDER BY p.sku_code;


-- C2. SKUs missing ASP (revenue cannot be calculated)
-- These rows have units but no avg selling price → revenue = NULL.
SELECT
    por.display_name         AS portal,
    p.sku_code,
    LEFT(p.product_name, 50) AS product_name,
    COUNT(*)                 AS rows_missing_asp,
    SUM(ds.units_sold)::int  AS units_affected
FROM daily_sales ds
JOIN portals por ON por.id = ds.portal_id
JOIN products p   ON p.id  = ds.product_id
WHERE ds.asp IS NULL AND ds.units_sold > 0
GROUP BY por.display_name, p.sku_code, p.product_name
ORDER BY units_affected DESC;


-- C3. Days with abnormally high or zero sales — outlier detector
-- For each portal, flags dates where units are > 3× the portal's daily average
-- OR zero (full-day dropout). Useful to catch data entry errors.
WITH portal_avg AS (
    SELECT portal_id,
           AVG(daily_total)   AS avg_daily,
           STDDEV(daily_total) AS sd_daily
    FROM (
        SELECT portal_id, sale_date, SUM(units_sold) AS daily_total
        FROM daily_sales
        GROUP BY portal_id, sale_date
    ) d
    GROUP BY portal_id
),
daily_totals AS (
    SELECT portal_id, sale_date, SUM(units_sold) AS daily_total
    FROM daily_sales
    GROUP BY portal_id, sale_date
)
SELECT
    por.display_name      AS portal,
    dt.sale_date,
    dt.daily_total        AS units,
    ROUND(pa.avg_daily, 0) AS avg_daily_units,
    CASE
        WHEN dt.daily_total = 0          THEN 'ZERO DAY'
        WHEN dt.daily_total > pa.avg_daily + 3 * pa.sd_daily THEN 'SPIKE'
        WHEN dt.daily_total < pa.avg_daily - 2 * pa.sd_daily THEN 'DROP'
    END                   AS flag
FROM daily_totals dt
JOIN portal_avg pa    ON pa.portal_id = dt.portal_id
JOIN portals por      ON por.id = dt.portal_id
WHERE dt.daily_total = 0
   OR dt.daily_total > pa.avg_daily + 3 * COALESCE(pa.sd_daily, 0)
   OR dt.daily_total < pa.avg_daily - 2 * COALESCE(pa.sd_daily, 0)
ORDER BY dt.sale_date DESC, flag;


-- C4. Missing days — gaps in daily sales data per portal
-- Finds calendar days within the data range that have NO rows at all.
-- (Expected gaps: portals that don't sell on specific days)
WITH calendar AS (
    SELECT generate_series(
        (SELECT MIN(sale_date) FROM daily_sales),
        (SELECT MAX(sale_date) FROM daily_sales),
        '1 day'::interval
    )::date AS cal_date
),
portal_dates AS (
    SELECT DISTINCT portal_id, sale_date FROM daily_sales
)
SELECT
    por.display_name   AS portal,
    c.cal_date         AS missing_date
FROM calendar c
CROSS JOIN portals por
LEFT JOIN portal_dates pd ON pd.portal_id = por.id AND pd.sale_date = c.cal_date
WHERE pd.sale_date IS NULL
  AND por.is_active = TRUE
  AND c.cal_date <= CURRENT_DATE
ORDER BY por.display_name, c.cal_date;


-- C5. ASP anomalies — same SKU with wildly different ASP across months
-- A big ASP swing usually means a price change, a data entry error,
-- or a different variant being reported under the same SKU.
SELECT
    p.sku_code,
    LEFT(p.product_name, 50) AS product_name,
    por.display_name         AS portal,
    ROUND(MIN(ds.asp), 2)    AS min_asp,
    ROUND(MAX(ds.asp), 2)    AS max_asp,
    ROUND(MAX(ds.asp) - MIN(ds.asp), 2) AS asp_range,
    ROUND(100.0 * (MAX(ds.asp) - MIN(ds.asp)) / NULLIF(MIN(ds.asp), 0), 1) AS pct_variation
FROM daily_sales ds
JOIN products p   ON p.id  = ds.product_id
JOIN portals por  ON por.id = ds.portal_id
WHERE ds.asp IS NOT NULL AND ds.asp > 0
GROUP BY p.sku_code, p.product_name, por.display_name
HAVING MAX(ds.asp) > MIN(ds.asp) * 1.25   -- flag >25% variation
ORDER BY pct_variation DESC
LIMIT 30;


-- C6. Inventory health check — DOC (days of coverage) per SKU
-- SKUs with low DOC are at risk of going out of stock.
-- Red: DOC < 15. Amber: 15–30. Green: > 30.
SELECT
    p.sku_code,
    LEFT(p.product_name, 50) AS product_name,
    por.display_name         AS portal,
    i.snapshot_date,
    COALESCE(i.portal_stock, i.backend_stock + COALESCE(i.frontend_stock,0)) AS portal_wh_stock,
    i.solara_stock,
    i.amazon_fc_stock,
    i.open_po,
    ROUND(i.doc, 1)          AS doc_days,
    CASE
        WHEN i.doc < 15  THEN 'RED — Reorder Now'
        WHEN i.doc < 30  THEN 'AMBER — Reorder Soon'
        ELSE                  'GREEN — OK'
    END                      AS stock_status
FROM inventory_snapshots i
JOIN products p   ON p.id  = i.product_id
JOIN portals por  ON por.id = i.portal_id
WHERE (i.portal_id, i.snapshot_date) IN (
    SELECT portal_id, MAX(snapshot_date)
    FROM inventory_snapshots GROUP BY portal_id
)
  AND i.doc IS NOT NULL
ORDER BY i.doc ASC;


-- C7. Revenue vs units cross-check — rows where revenue seems inconsistent
-- Flags rows where stored revenue differs from units × asp by more than ₹5.
-- Helps identify data entry errors or import bugs.
SELECT
    por.display_name    AS portal,
    p.sku_code,
    ds.sale_date,
    ds.units_sold,
    ds.asp,
    ds.revenue          AS stored_revenue,
    ROUND(ds.units_sold * ds.asp, 2) AS calculated_revenue,
    ABS(ds.revenue - ROUND(ds.units_sold * ds.asp, 2)) AS discrepancy
FROM daily_sales ds
JOIN portals por ON por.id = ds.portal_id
JOIN products p  ON p.id  = ds.product_id
WHERE ds.asp IS NOT NULL
  AND ds.revenue IS NOT NULL
  AND ABS(ds.revenue - ROUND(ds.units_sold * ds.asp, 2)) > 5
ORDER BY discrepancy DESC
LIMIT 50;


-- C8. Portal mapping coverage — which SKUs are NOT mapped to each portal
-- A quick table showing which products have no mapping on each portal.
-- If a product should be on Amazon but has no mapping → it won't be tracked.
SELECT
    p.sku_code,
    LEFT(p.product_name, 50) AS product_name,
    MAX(CASE WHEN por.name='zepto'    THEN '✓' ELSE '—' END) AS zepto,
    MAX(CASE WHEN por.name='swiggy'   THEN '✓' ELSE '—' END) AS swiggy,
    MAX(CASE WHEN por.name='blinkit'  THEN '✓' ELSE '—' END) AS blinkit,
    MAX(CASE WHEN por.name='myntra'   THEN '✓' ELSE '—' END) AS myntra,
    MAX(CASE WHEN por.name='flipkart' THEN '✓' ELSE '—' END) AS flipkart,
    MAX(CASE WHEN por.name='amazon'   THEN '✓' ELSE '—' END) AS amazon,
    MAX(CASE WHEN por.name='shopify'  THEN '✓' ELSE '—' END) AS shopify
FROM products p
CROSS JOIN portals por
LEFT JOIN product_portal_mapping pm
       ON pm.product_id = p.id AND pm.portal_id = por.id
GROUP BY p.id, p.sku_code, p.product_name
ORDER BY p.sku_code;


-- =============================================================================
-- D. SALES DASHBOARD
-- =============================================================================

-- D1. KPI Summary Card — MTD snapshot
-- Single row: total units, revenue, active SKUs, best portal.
-- Use this as the top-of-dashboard numbers.
SELECT
    SUM(ds.units_sold)::int                         AS mtd_units,
    ROUND(SUM(ds.revenue), 0)                       AS mtd_revenue,
    COUNT(DISTINCT ds.product_id)                   AS active_skus,
    COUNT(DISTINCT ds.portal_id)                    AS active_portals,
    (
        SELECT por2.display_name FROM daily_sales ds2
        JOIN portals por2 ON por2.id = ds2.portal_id
        WHERE ds2.sale_date >= DATE_TRUNC('month', CURRENT_DATE)
        GROUP BY por2.display_name ORDER BY SUM(ds2.units_sold) DESC LIMIT 1
    )                                               AS top_portal_by_units,
    ROUND(SUM(ds.units_sold)::numeric / NULLIF(
        EXTRACT(DAY FROM CURRENT_DATE), 0), 1)      AS avg_daily_run_rate
FROM daily_sales ds
WHERE ds.sale_date >= DATE_TRUNC('month', CURRENT_DATE)
  AND ds.units_sold > 0;


-- D2. MTD units & revenue per portal — dashboard portal cards
-- One row per portal with MTD actuals + rank.
SELECT
    RANK() OVER (ORDER BY SUM(ds.units_sold) DESC) AS rank,
    por.display_name                               AS portal,
    SUM(ds.units_sold)::int                        AS mtd_units,
    ROUND(SUM(ds.revenue), 0)                      AS mtd_revenue,
    ROUND(AVG(ds.asp), 2)                          AS avg_asp,
    COUNT(DISTINCT ds.product_id)                  AS active_skus,
    COUNT(DISTINCT ds.sale_date)                   AS selling_days
FROM daily_sales ds
JOIN portals por ON por.id = ds.portal_id
WHERE ds.sale_date >= DATE_TRUNC('month', CURRENT_DATE)
  AND ds.units_sold > 0
GROUP BY por.display_name
ORDER BY mtd_units DESC;


-- D3. Daily units trend — last 30 days, all portals combined
-- Line chart source. One row per day = total across all portals.
SELECT
    ds.sale_date,
    SUM(ds.units_sold)::int   AS total_units,
    ROUND(SUM(ds.revenue), 0) AS total_revenue,
    COUNT(DISTINCT ds.portal_id) AS portals_with_sales
FROM daily_sales ds
WHERE ds.sale_date >= CURRENT_DATE - INTERVAL '30 days'
  AND ds.units_sold > 0
GROUP BY ds.sale_date
ORDER BY ds.sale_date;


-- D4. Daily units trend — last 30 days, split by portal
-- Multi-line/stacked bar source. One row per day × portal.
SELECT
    ds.sale_date,
    por.display_name          AS portal,
    SUM(ds.units_sold)::int   AS units,
    ROUND(SUM(ds.revenue), 0) AS revenue
FROM daily_sales ds
JOIN portals por ON por.id = ds.portal_id
WHERE ds.sale_date >= CURRENT_DATE - INTERVAL '30 days'
  AND ds.units_sold > 0
GROUP BY ds.sale_date, por.display_name
ORDER BY ds.sale_date, por.display_name;


-- D5. Top 10 SKUs — current month, with MoM comparison
-- Product performance table for dashboard.
WITH this_month AS (
    SELECT product_id,
           SUM(units_sold)::int     AS units_tm,
           ROUND(SUM(revenue), 0)   AS rev_tm
    FROM daily_sales
    WHERE sale_date >= DATE_TRUNC('month', CURRENT_DATE)
    GROUP BY product_id
),
last_month AS (
    SELECT product_id,
           SUM(units_sold)::int     AS units_lm,
           ROUND(SUM(revenue), 0)   AS rev_lm
    FROM daily_sales
    WHERE sale_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'
      AND sale_date <  DATE_TRUNC('month', CURRENT_DATE)
      AND EXTRACT(DAY FROM sale_date) <= EXTRACT(DAY FROM CURRENT_DATE)
    GROUP BY product_id
)
SELECT
    p.sku_code,
    LEFT(p.product_name, 45)         AS product_name,
    COALESCE(tm.units_tm, 0)         AS this_month_units,
    COALESCE(lm.units_lm, 0)         AS last_month_units,
    COALESCE(tm.units_tm,0) - COALESCE(lm.units_lm,0) AS delta_units,
    CASE WHEN COALESCE(lm.units_lm,0) > 0
         THEN ROUND(100.0*(COALESCE(tm.units_tm,0)-lm.units_lm)/lm.units_lm,1)
    END                              AS growth_pct,
    COALESCE(tm.rev_tm, 0)           AS this_month_revenue
FROM this_month tm
JOIN products p ON p.id = tm.product_id
LEFT JOIN last_month lm ON lm.product_id = tm.product_id
ORDER BY this_month_units DESC
LIMIT 10;


-- D6. Inventory alert table — low stock SKUs (DOC < 30 days)
-- Dashboard widget: "Reorder List". Shows critical items first.
SELECT
    por.display_name    AS portal,
    p.sku_code,
    LEFT(p.product_name, 50) AS product_name,
    i.snapshot_date,
    ROUND(i.doc, 0)     AS days_of_coverage,
    COALESCE(i.portal_stock,
             i.backend_stock + COALESCE(i.frontend_stock, 0)) AS portal_stock,
    i.solara_stock,
    i.open_po,
    CASE
        WHEN i.doc < 15 THEN '🔴 Critical'
        ELSE                 '🟡 Low'
    END AS alert_level
FROM inventory_snapshots i
JOIN products p   ON p.id   = i.product_id
JOIN portals por  ON por.id = i.portal_id
WHERE (i.portal_id, i.snapshot_date) IN (
    SELECT portal_id, MAX(snapshot_date)
    FROM inventory_snapshots GROUP BY portal_id
)
  AND i.doc < 30
ORDER BY i.doc ASC;


-- D7. Amazon target achievement — current month
-- Achievement gauge data: target vs actual vs DRR for each SKU.
WITH actuals AS (
    SELECT ds.product_id,
           SUM(ds.units_sold)    AS mtd_units,
           ROUND(SUM(ds.revenue),0) AS mtd_revenue
    FROM daily_sales ds
    JOIN portals por ON por.id = ds.portal_id
    WHERE por.name = 'amazon'
      AND ds.sale_date >= DATE_TRUNC('month', CURRENT_DATE)
    GROUP BY ds.product_id
)
SELECT
    p.sku_code,
    LEFT(p.product_name, 45)                         AS product_name,
    mt.target_units,
    mt.target_revenue,
    COALESCE(a.mtd_units, 0)                         AS actual_units,
    COALESCE(a.mtd_revenue, 0)                       AS actual_revenue,
    ROUND(100.0 * COALESCE(a.mtd_units,0)
                / NULLIF(mt.target_units, 0), 1)     AS units_achievement_pct,
    mt.target_drr,
    ROUND(COALESCE(a.mtd_units,0)
          / NULLIF(EXTRACT(DAY FROM CURRENT_DATE), 0), 1) AS actual_drr,
    CASE
        WHEN COALESCE(a.mtd_units,0) >= mt.target_units        THEN 'ON TRACK ✓'
        WHEN COALESCE(a.mtd_units,0) >= mt.target_units * 0.75 THEN 'CLOSE'
        ELSE 'BEHIND'
    END AS status
FROM monthly_targets mt
JOIN portals por ON por.id = mt.portal_id
JOIN products p  ON p.id  = mt.product_id
LEFT JOIN actuals a ON a.product_id = mt.product_id
WHERE por.name = 'amazon'
  AND mt.year  = EXTRACT(YEAR  FROM CURRENT_DATE)
  AND mt.month = EXTRACT(MONTH FROM CURRENT_DATE)
  AND mt.target_units > 0
ORDER BY units_achievement_pct ASC NULLS LAST;


-- D8. 12-month trend — monthly totals for the full year
-- Bar/line chart covering Apr 2025 → latest month.
SELECT
    TO_CHAR(ds.sale_date, 'YYYY-MM')  AS month,
    SUM(ds.units_sold)::int           AS total_units,
    ROUND(SUM(ds.revenue), 0)         AS total_revenue,
    COUNT(DISTINCT ds.product_id)     AS active_skus,
    COUNT(DISTINCT ds.portal_id)      AS active_portals,
    ROUND(SUM(ds.units_sold)::numeric
          / NULLIF(COUNT(DISTINCT ds.sale_date), 0), 1) AS avg_daily_units
FROM daily_sales ds
WHERE ds.units_sold > 0
GROUP BY TO_CHAR(ds.sale_date, 'YYYY-MM')
ORDER BY month;


-- D9. Category contribution — current month
-- Donut / bar chart source for product category breakdown.
SELECT
    COALESCE(pc.l2_name, 'Uncategorised') AS category,
    SUM(ds.units_sold)::int               AS units,
    ROUND(SUM(ds.revenue), 0)             AS revenue,
    ROUND(100.0 * SUM(ds.units_sold)
          / NULLIF(SUM(SUM(ds.units_sold)) OVER (), 0), 1) AS units_pct,
    ROUND(100.0 * SUM(ds.revenue)
          / NULLIF(SUM(SUM(ds.revenue)) OVER (), 0), 1)    AS revenue_pct
FROM daily_sales ds
JOIN products p   ON p.id  = ds.product_id
LEFT JOIN product_categories pc ON pc.id = p.category_id
WHERE ds.sale_date >= DATE_TRUNC('month', CURRENT_DATE)
  AND ds.units_sold > 0
GROUP BY pc.l2_name
ORDER BY units DESC;


-- D10. Full SKU detail drill-down — single product across all time
-- ---------------------------------------------------------------
-- Change the sku_code value to drill into any product.
-- Shows daily sales per portal, plus inventory snapshot history.
--
-- Part A: Daily sales for this SKU across all portals
SELECT
    ds.sale_date,
    por.display_name          AS portal,
    ds.units_sold,
    ds.asp,
    ds.revenue
FROM daily_sales ds
JOIN portals por ON por.id = ds.portal_id
JOIN products p  ON p.id  = ds.product_id
WHERE p.sku_code = 'SOL-CI-DT-101'   -- ← change SKU here
ORDER BY ds.sale_date DESC, por.display_name;

-- Part B: Inventory snapshot history for this SKU
SELECT
    por.display_name    AS portal,
    i.snapshot_date,
    i.portal_stock,
    i.backend_stock,
    i.frontend_stock,
    i.solara_stock,
    i.amazon_fc_stock,
    i.open_po,
    ROUND(i.doc, 1)     AS doc_days
FROM inventory_snapshots i
JOIN portals por ON por.id = i.portal_id
JOIN products p  ON p.id  = i.product_id
WHERE p.sku_code = 'SOL-CI-DT-101'   -- ← same SKU
ORDER BY i.snapshot_date DESC, por.display_name;
