"""
Test all pgadmin_queries.sql queries to confirm they execute without error.
Run: python scripts/test_queries.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.db_utils import engine
from sqlalchemy import text

QUERIES = {
    # --- Section A: Data Understanding ---
    "A1 Table counts": """
        SELECT 'portals' AS t, COUNT(*) FROM portals
        UNION ALL SELECT 'products', COUNT(*) FROM products
        UNION ALL SELECT 'daily_sales', COUNT(*) FROM daily_sales
        UNION ALL SELECT 'inventory_snapshots', COUNT(*) FROM inventory_snapshots
        UNION ALL SELECT 'monthly_targets', COUNT(*) FROM monthly_targets
    """,
    "A2 Products + category": """
        SELECT p.sku_code, pc.l2_name, p.default_asp
        FROM products p LEFT JOIN product_categories pc ON pc.id = p.category_id
        ORDER BY pc.l2_name, p.sku_code LIMIT 3
    """,
    "A3 Portal coverage per SKU": """
        SELECT p.sku_code, COUNT(DISTINCT pm.portal_id) AS n,
               STRING_AGG(por.name, ', ' ORDER BY por.name) AS portals
        FROM products p
        LEFT JOIN product_portal_mapping pm ON pm.product_id = p.id
        LEFT JOIN portals por ON por.id = pm.portal_id
        GROUP BY p.id, p.sku_code, p.product_name
        ORDER BY n DESC LIMIT 3
    """,
    "A4 Date range per portal": """
        SELECT por.display_name, MIN(ds.sale_date), MAX(ds.sale_date),
               COUNT(DISTINCT ds.sale_date) AS days
        FROM daily_sales ds JOIN portals por ON por.id = ds.portal_id
        GROUP BY por.display_name ORDER BY por.display_name
    """,
    "A5 Data completeness by portal+month": """
        SELECT por.display_name, TO_CHAR(ds.sale_date, 'YYYY-MM'),
               COUNT(DISTINCT ds.product_id), SUM(ds.units_sold)::int
        FROM daily_sales ds JOIN portals por ON por.id = ds.portal_id
        GROUP BY por.display_name, TO_CHAR(ds.sale_date, 'YYYY-MM')
        ORDER BY 2 DESC, 1 LIMIT 5
    """,
    "A6 Import log": """
        SELECT il.import_date, por.display_name, il.sheet_name, il.status, il.records_imported
        FROM import_logs il LEFT JOIN portals por ON por.id = il.portal_id
        ORDER BY il.import_date DESC LIMIT 5
    """,
    "A7 Products not sold on amazon": """
        SELECT p.sku_code FROM products p
        JOIN product_portal_mapping pm ON pm.product_id = p.id
        JOIN portals por ON por.id = pm.portal_id
        WHERE por.name = 'amazon'
          AND NOT EXISTS (SELECT 1 FROM daily_sales ds
                          WHERE ds.product_id = p.id AND ds.portal_id = por.id)
        ORDER BY p.sku_code LIMIT 5
    """,
    "A8 Raw rows zepto jan 2026": """
        SELECT p.sku_code, ds.sale_date, ds.units_sold, ds.asp, ds.revenue
        FROM daily_sales ds
        JOIN products p  ON p.id  = ds.product_id
        JOIN portals por ON por.id = ds.portal_id
        WHERE por.name = 'zepto'
          AND ds.sale_date BETWEEN '2026-01-01' AND '2026-01-05'
        ORDER BY ds.sale_date, p.sku_code LIMIT 5
    """,
    # --- Section B: Sales Analysis ---
    "B1 Monthly totals by portal": """
        SELECT TO_CHAR(ds.sale_date, 'YYYY-MM'), por.display_name,
               SUM(ds.units_sold)::int, ROUND(SUM(ds.revenue), 0)
        FROM daily_sales ds JOIN portals por ON por.id = ds.portal_id
        WHERE ds.units_sold > 0
        GROUP BY TO_CHAR(ds.sale_date, 'YYYY-MM'), por.display_name
        ORDER BY 1 DESC, 3 DESC LIMIT 5
    """,
    "B2 Daily last 30 days": """
        SELECT ds.sale_date, por.display_name, SUM(ds.units_sold)::int
        FROM daily_sales ds JOIN portals por ON por.id = ds.portal_id
        WHERE ds.sale_date >= CURRENT_DATE - INTERVAL '30 days' AND ds.units_sold > 0
        GROUP BY ds.sale_date, por.display_name
        ORDER BY ds.sale_date DESC LIMIT 5
    """,
    "B3 Top 20 SKUs all time": """
        SELECT p.sku_code, LEFT(p.product_name, 50), SUM(ds.units_sold)::int
        FROM daily_sales ds JOIN products p ON p.id = ds.product_id
        WHERE ds.units_sold > 0
        GROUP BY p.sku_code, p.product_name
        ORDER BY 3 DESC LIMIT 5
    """,
    "B4 Portal share MTD": """
        WITH mtd AS (
            SELECT por.display_name AS portal,
                   SUM(ds.units_sold)::int AS units,
                   ROUND(SUM(ds.revenue), 0) AS revenue
            FROM daily_sales ds JOIN portals por ON por.id = ds.portal_id
            WHERE ds.sale_date >= DATE_TRUNC('month', CURRENT_DATE) AND ds.units_sold > 0
            GROUP BY por.display_name
        )
        SELECT portal, units, revenue,
               ROUND(100.0 * revenue / NULLIF(SUM(revenue) OVER (), 0), 1) AS pct
        FROM mtd ORDER BY revenue DESC
    """,
    "B5 MoM growth": """
        WITH this_m AS (
            SELECT por.display_name AS portal, SUM(ds.units_sold)::int AS units
            FROM daily_sales ds JOIN portals por ON por.id = ds.portal_id
            WHERE ds.sale_date >= DATE_TRUNC('month', CURRENT_DATE)
              AND EXTRACT(DAY FROM ds.sale_date) <= EXTRACT(DAY FROM CURRENT_DATE)
            GROUP BY por.display_name
        ), last_m AS (
            SELECT por.display_name AS portal, SUM(ds.units_sold)::int AS units
            FROM daily_sales ds JOIN portals por ON por.id = ds.portal_id
            WHERE ds.sale_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'
              AND ds.sale_date < DATE_TRUNC('month', CURRENT_DATE)
              AND EXTRACT(DAY FROM ds.sale_date) <= EXTRACT(DAY FROM CURRENT_DATE)
            GROUP BY por.display_name
        )
        SELECT COALESCE(c.portal, l.portal), COALESCE(l.units,0), COALESCE(c.units,0)
        FROM this_m c FULL JOIN last_m l USING (portal)
        ORDER BY 3 DESC
    """,
    "B6 DRR vs target amazon": """
        SELECT p.sku_code, mt.target_units, mt.target_drr
        FROM monthly_targets mt
        JOIN portals por ON por.id = mt.portal_id
        JOIN products p   ON p.id  = mt.product_id
        WHERE por.name = 'amazon' AND mt.year = 2026 AND mt.month = 2
          AND mt.target_units > 0
        LIMIT 5
    """,
    "B7 SKU heatmap current month": """
        SELECT p.sku_code,
               COALESCE(SUM(CASE WHEN por.name='amazon'   THEN ds.units_sold END),0)::int AS amazon,
               COALESCE(SUM(CASE WHEN por.name='shopify'  THEN ds.units_sold END),0)::int AS shopify,
               COALESCE(SUM(CASE WHEN por.name='flipkart' THEN ds.units_sold END),0)::int AS flipkart
        FROM daily_sales ds
        JOIN products p  ON p.id  = ds.product_id
        JOIN portals por ON por.id = ds.portal_id
        WHERE ds.sale_date >= DATE_TRUNC('month', CURRENT_DATE) AND ds.units_sold > 0
        GROUP BY p.sku_code ORDER BY amazon DESC LIMIT 5
    """,
    "B8 Weekly trend 12 weeks": """
        SELECT DATE_TRUNC('week', ds.sale_date)::date, por.display_name,
               SUM(ds.units_sold)::int
        FROM daily_sales ds JOIN portals por ON por.id = ds.portal_id
        WHERE ds.sale_date >= CURRENT_DATE - INTERVAL '12 weeks' AND ds.units_sold > 0
        GROUP BY DATE_TRUNC('week', ds.sale_date), por.display_name
        ORDER BY 1 DESC LIMIT 5
    """,
    "B9 Category monthly": """
        SELECT TO_CHAR(ds.sale_date, 'YYYY-MM'), COALESCE(pc.l2_name,'Uncategorised'),
               SUM(ds.units_sold)::int
        FROM daily_sales ds
        JOIN products p ON p.id = ds.product_id
        LEFT JOIN product_categories pc ON pc.id = p.category_id
        WHERE ds.units_sold > 0
        GROUP BY TO_CHAR(ds.sale_date, 'YYYY-MM'), pc.l2_name
        ORDER BY 1 DESC LIMIT 5
    """,
    "B10 Returns / negatives": """
        SELECT por.display_name, p.sku_code, ds.sale_date, ds.units_sold
        FROM daily_sales ds
        JOIN portals por ON por.id = ds.portal_id
        JOIN products p   ON p.id  = ds.product_id
        WHERE ds.units_sold < 0
        ORDER BY ds.sale_date DESC LIMIT 10
    """,
    # --- Section C: Discrepancy Checks ---
    "C1 Products never sold": """
        SELECT p.sku_code, LEFT(p.product_name, 50)
        FROM products p
        WHERE NOT EXISTS (SELECT 1 FROM daily_sales ds WHERE ds.product_id = p.id)
        ORDER BY p.sku_code LIMIT 5
    """,
    "C2 Missing ASP rows": """
        SELECT por.display_name, p.sku_code, COUNT(*), SUM(ds.units_sold)::int
        FROM daily_sales ds
        JOIN portals por ON por.id = ds.portal_id
        JOIN products p   ON p.id  = ds.product_id
        WHERE ds.asp IS NULL AND ds.units_sold > 0
        GROUP BY por.display_name, p.sku_code
        ORDER BY 4 DESC LIMIT 5
    """,
    "C3 Outlier days (spikes/zeros)": """
        WITH pa AS (
            SELECT portal_id, AVG(daily_total) AS avg_d, STDDEV(daily_total) AS sd
            FROM (SELECT portal_id, sale_date, SUM(units_sold) AS daily_total
                  FROM daily_sales GROUP BY portal_id, sale_date) d
            GROUP BY portal_id
        ), dt AS (
            SELECT portal_id, sale_date, SUM(units_sold) AS daily_total
            FROM daily_sales GROUP BY portal_id, sale_date
        )
        SELECT por.display_name, dt.sale_date, dt.daily_total, ROUND(pa.avg_d, 0)
        FROM dt
        JOIN pa  ON pa.portal_id = dt.portal_id
        JOIN portals por ON por.id = dt.portal_id
        WHERE dt.daily_total = 0
           OR dt.daily_total > pa.avg_d + 3 * COALESCE(pa.sd, 0)
        ORDER BY dt.sale_date DESC LIMIT 5
    """,
    "C4 Missing days (gaps)": """
        WITH cal AS (
            SELECT generate_series(
                (SELECT MIN(sale_date) FROM daily_sales),
                (SELECT MAX(sale_date) FROM daily_sales),
                '1 day'::interval
            )::date AS cal_date
        ), pd AS (SELECT DISTINCT portal_id, sale_date FROM daily_sales)
        SELECT por.display_name, c.cal_date AS missing_date
        FROM cal c
        CROSS JOIN portals por
        LEFT JOIN pd ON pd.portal_id = por.id AND pd.sale_date = c.cal_date
        WHERE pd.sale_date IS NULL AND por.is_active = TRUE AND c.cal_date <= CURRENT_DATE
        ORDER BY por.display_name, c.cal_date LIMIT 10
    """,
    "C5 ASP anomalies >25%": """
        SELECT p.sku_code, por.display_name,
               ROUND(MIN(ds.asp),2), ROUND(MAX(ds.asp),2),
               ROUND(100.0*(MAX(ds.asp)-MIN(ds.asp))/NULLIF(MIN(ds.asp),0),1) AS pct
        FROM daily_sales ds
        JOIN products p  ON p.id  = ds.product_id
        JOIN portals por ON por.id = ds.portal_id
        WHERE ds.asp IS NOT NULL AND ds.asp > 0
        GROUP BY p.sku_code, p.product_name, por.display_name
        HAVING MAX(ds.asp) > MIN(ds.asp) * 1.25
        ORDER BY 5 DESC LIMIT 5
    """,
    "C6 Inventory DOC health": """
        SELECT por.display_name, p.sku_code, ROUND(i.doc,1),
               COALESCE(i.portal_stock, i.backend_stock + COALESCE(i.frontend_stock,0)) AS stk
        FROM inventory_snapshots i
        JOIN products p  ON p.id  = i.product_id
        JOIN portals por ON por.id = i.portal_id
        WHERE (i.portal_id, i.snapshot_date) IN (
            SELECT portal_id, MAX(snapshot_date) FROM inventory_snapshots GROUP BY portal_id
        )
          AND i.doc IS NOT NULL
        ORDER BY i.doc ASC LIMIT 5
    """,
    "C7 Revenue vs units cross-check": """
        SELECT por.display_name, p.sku_code, ds.units_sold, ds.asp,
               ds.revenue, ROUND(ds.units_sold * ds.asp, 2) AS calc,
               ABS(ds.revenue - ROUND(ds.units_sold * ds.asp, 2)) AS diff
        FROM daily_sales ds
        JOIN portals por ON por.id = ds.portal_id
        JOIN products p  ON p.id  = ds.product_id
        WHERE ds.asp IS NOT NULL AND ds.revenue IS NOT NULL
          AND ABS(ds.revenue - ROUND(ds.units_sold * ds.asp, 2)) > 5
        ORDER BY 7 DESC LIMIT 5
    """,
    "C8 Mapping coverage matrix": """
        SELECT p.sku_code,
               MAX(CASE WHEN por.name='zepto'    THEN 'Y' ELSE '-' END) AS zepto,
               MAX(CASE WHEN por.name='swiggy'   THEN 'Y' ELSE '-' END) AS swiggy,
               MAX(CASE WHEN por.name='blinkit'  THEN 'Y' ELSE '-' END) AS blinkit,
               MAX(CASE WHEN por.name='flipkart' THEN 'Y' ELSE '-' END) AS flipkart,
               MAX(CASE WHEN por.name='amazon'   THEN 'Y' ELSE '-' END) AS amazon,
               MAX(CASE WHEN por.name='shopify'  THEN 'Y' ELSE '-' END) AS shopify
        FROM products p
        CROSS JOIN portals por
        LEFT JOIN product_portal_mapping pm ON pm.product_id = p.id AND pm.portal_id = por.id
        GROUP BY p.sku_code ORDER BY p.sku_code LIMIT 5
    """,
    # --- Section D: Dashboard ---
    "D1 KPI summary card MTD": """
        SELECT SUM(ds.units_sold)::int AS mtd_units,
               ROUND(SUM(ds.revenue), 0) AS mtd_revenue,
               COUNT(DISTINCT ds.product_id) AS active_skus,
               COUNT(DISTINCT ds.portal_id) AS active_portals,
               ROUND(SUM(ds.units_sold)::numeric / NULLIF(EXTRACT(DAY FROM CURRENT_DATE), 0), 1) AS avg_drr
        FROM daily_sales ds
        WHERE ds.sale_date >= DATE_TRUNC('month', CURRENT_DATE) AND ds.units_sold > 0
    """,
    "D2 Portal cards MTD": """
        SELECT RANK() OVER (ORDER BY SUM(ds.units_sold) DESC) AS rank,
               por.display_name, SUM(ds.units_sold)::int, ROUND(SUM(ds.revenue),0),
               COUNT(DISTINCT ds.product_id) AS skus
        FROM daily_sales ds JOIN portals por ON por.id = ds.portal_id
        WHERE ds.sale_date >= DATE_TRUNC('month', CURRENT_DATE) AND ds.units_sold > 0
        GROUP BY por.display_name ORDER BY 3 DESC
    """,
    "D3 Daily trend combined 30d": """
        SELECT ds.sale_date, SUM(ds.units_sold)::int, ROUND(SUM(ds.revenue),0)
        FROM daily_sales ds
        WHERE ds.sale_date >= CURRENT_DATE - INTERVAL '30 days' AND ds.units_sold > 0
        GROUP BY ds.sale_date ORDER BY ds.sale_date
    """,
    "D4 Daily trend by portal 30d": """
        SELECT ds.sale_date, por.display_name, SUM(ds.units_sold)::int
        FROM daily_sales ds JOIN portals por ON por.id = ds.portal_id
        WHERE ds.sale_date >= CURRENT_DATE - INTERVAL '30 days' AND ds.units_sold > 0
        GROUP BY ds.sale_date, por.display_name ORDER BY ds.sale_date LIMIT 10
    """,
    "D5 Top 10 SKUs MoM": """
        WITH tm AS (
            SELECT product_id, SUM(units_sold)::int AS u, ROUND(SUM(revenue),0) AS r
            FROM daily_sales WHERE sale_date >= DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY product_id
        ), lm AS (
            SELECT product_id, SUM(units_sold)::int AS u
            FROM daily_sales
            WHERE sale_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'
              AND sale_date < DATE_TRUNC('month', CURRENT_DATE)
              AND EXTRACT(DAY FROM sale_date) <= EXTRACT(DAY FROM CURRENT_DATE)
            GROUP BY product_id
        )
        SELECT p.sku_code, LEFT(p.product_name, 45),
               COALESCE(tm.u,0) AS this_m, COALESCE(lm.u,0) AS last_m,
               COALESCE(tm.u,0) - COALESCE(lm.u,0) AS delta, tm.r
        FROM tm JOIN products p ON p.id = tm.product_id
        LEFT JOIN lm ON lm.product_id = tm.product_id
        ORDER BY this_m DESC LIMIT 10
    """,
    "D6 Inventory alerts <30 DOC": """
        SELECT por.display_name, p.sku_code, ROUND(i.doc,0) AS doc,
               COALESCE(i.portal_stock, i.backend_stock + COALESCE(i.frontend_stock,0)) AS stock,
               i.open_po
        FROM inventory_snapshots i
        JOIN products p  ON p.id  = i.product_id
        JOIN portals por ON por.id = i.portal_id
        WHERE (i.portal_id, i.snapshot_date) IN (
            SELECT portal_id, MAX(snapshot_date) FROM inventory_snapshots GROUP BY portal_id
        )
          AND i.doc < 30
        ORDER BY i.doc ASC LIMIT 10
    """,
    "D7 Amazon target achievement": """
        WITH actuals AS (
            SELECT ds.product_id,
                   SUM(ds.units_sold)::int AS mtd_units,
                   ROUND(SUM(ds.revenue),0) AS mtd_revenue
            FROM daily_sales ds JOIN portals por ON por.id = ds.portal_id
            WHERE por.name = 'amazon' AND ds.sale_date >= DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY ds.product_id
        )
        SELECT p.sku_code, mt.target_units, COALESCE(a.mtd_units,0) AS actual_units,
               ROUND(100.0*COALESCE(a.mtd_units,0)/NULLIF(mt.target_units,0),1) AS pct,
               mt.target_drr
        FROM monthly_targets mt
        JOIN portals por ON por.id = mt.portal_id
        JOIN products p  ON p.id  = mt.product_id
        LEFT JOIN actuals a ON a.product_id = mt.product_id
        WHERE por.name = 'amazon' AND mt.year = 2026 AND mt.month = 2
          AND mt.target_units > 0
        ORDER BY pct ASC NULLS LAST LIMIT 5
    """,
    "D8 12 month trend full year": """
        SELECT TO_CHAR(ds.sale_date, 'YYYY-MM') AS month,
               SUM(ds.units_sold)::int AS units, ROUND(SUM(ds.revenue),0) AS revenue,
               COUNT(DISTINCT ds.product_id) AS skus
        FROM daily_sales ds WHERE ds.units_sold > 0
        GROUP BY TO_CHAR(ds.sale_date, 'YYYY-MM') ORDER BY 1
    """,
    "D9 Category contribution MTD": """
        SELECT COALESCE(pc.l2_name, 'Uncategorised') AS category,
               SUM(ds.units_sold)::int AS units, ROUND(SUM(ds.revenue),0) AS revenue,
               ROUND(100.0*SUM(ds.units_sold)/NULLIF(SUM(SUM(ds.units_sold)) OVER (),0),1) AS units_pct
        FROM daily_sales ds
        JOIN products p ON p.id = ds.product_id
        LEFT JOIN product_categories pc ON pc.id = p.category_id
        WHERE ds.sale_date >= DATE_TRUNC('month', CURRENT_DATE) AND ds.units_sold > 0
        GROUP BY pc.l2_name ORDER BY units DESC
    """,
    "D10 SKU drilldown (SOL-CI-DT-101)": """
        SELECT ds.sale_date, por.display_name, ds.units_sold, ds.asp, ds.revenue
        FROM daily_sales ds
        JOIN portals por ON por.id = ds.portal_id
        JOIN products p  ON p.id  = ds.product_id
        WHERE p.sku_code = 'SOL-CI-DT-101'
        ORDER BY ds.sale_date DESC LIMIT 5
    """,
}


def run_tests():
    passed, failed = 0, 0
    with engine.connect() as conn:
        for name, sql in QUERIES.items():
            try:
                rows = conn.execute(text(sql)).fetchall()
                print(f"  PASS  {name} ({len(rows)} rows)")
                passed += 1
            except Exception as e:
                print(f"  FAIL  {name}")
                print(f"        {str(e)[:120]}")
                failed += 1

    print(f"\n{'='*50}")
    print(f"Result: {passed} passed, {failed} failed out of {passed+failed} queries")
    return failed == 0


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
