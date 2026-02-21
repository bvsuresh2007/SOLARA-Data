"""
Installs portal_daily_grid_sql() function into the database.
Run: python scripts/install_excel_function.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.db_utils import engine

FUNC_SQL = """
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

    FOR v_date IN
        SELECT DISTINCT ds.sale_date
        FROM   daily_sales ds
        JOIN   portals por ON por.id = ds.portal_id
        WHERE  LOWER(por.name) = LOWER(p_portal)
          AND  ds.sale_date BETWEEN p_start AND p_end
        ORDER  BY ds.sale_date
    LOOP
        v_date_cols := v_date_cols
            || E'\\n    ,MAX(CASE WHEN ds.sale_date = '
            || quote_literal(v_date)
            || ' THEN ds.units_sold END) AS "'
            || TO_CHAR(v_date, 'DD-Mon-YY')
            || '"';
    END LOOP;

    v_sql :=
        'SELECT'
        || E'\\n     p.sku_code                                                     AS "SKU Code"'
        || E'\\n    ,p.product_name                                                 AS "Product Name"'
        || E'\\n    ,COALESCE(pc.l2_name, ''-'')                                   AS "Category"'
        || E'\\n    ,pm.portal_sku                                                  AS "Portal SKU"'
        || E'\\n    ,ROUND(AVG(ds.asp) FILTER (WHERE ds.asp IS NOT NULL), 2)        AS "BAU ASP"'
        || E'\\n    ,' || v_inv_col || ' AS "' || v_inv_label || '"'
        || v_date_cols
        || E'\\n    ,COALESCE(SUM(ds.units_sold) FILTER (WHERE ds.units_sold > 0), 0)::INT   AS "MTD Units"'
        || E'\\n    ,COALESCE(ROUND(SUM(ds.revenue) FILTER (WHERE ds.units_sold > 0), 0), 0) AS "MTD Value (Rs)"'
        || E'\\nFROM products p'
        || E'\\nJOIN product_portal_mapping pm  ON pm.product_id = p.id'
        || E'\\nJOIN portals por               ON por.id = pm.portal_id'
        || E'\\n                               AND LOWER(por.name) = ' || quote_literal(LOWER(p_portal))
        || E'\\nLEFT JOIN product_categories pc ON pc.id = p.category_id'
        || E'\\nLEFT JOIN daily_sales ds        ON  ds.product_id = p.id'
        || E'\\n                               AND ds.portal_id   = por.id'
        || E'\\n                               AND ds.sale_date BETWEEN '
            || quote_literal(p_start) || ' AND ' || quote_literal(p_end)
        || E'\\nLEFT JOIN inventory_snapshots inv'
        || E'\\n                                ON  inv.product_id = p.id'
        || E'\\n                               AND inv.portal_id   = por.id'
        || E'\\n                               AND inv.snapshot_date = ('
        || E'\\n                                   SELECT MAX(snapshot_date)'
        || E'\\n                                   FROM   inventory_snapshots'
        || E'\\n                                   WHERE  portal_id  = por.id'
        || E'\\n                                     AND  product_id = p.id'
        || E'\\n                               )'
        || E'\\nGROUP BY p.id, p.sku_code, p.product_name, pc.l2_name, pm.portal_sku'
        || E'\\nHAVING COUNT(ds.id) > 0'
        || E'\\nORDER BY "MTD Units" DESC NULLS LAST;';

    RETURN v_sql;
END;
$BODY$;
"""


def install():
    # Use AUTOCOMMIT isolation so DDL commits immediately
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        from sqlalchemy import text as _text
        conn.execute(_text(FUNC_SQL))
        print("Function portal_daily_grid_sql() installed successfully.")
        print("\nUsage in pgAdmin:")
        print("  -- Get current month SQL for any portal:")
        print("  SELECT portal_daily_grid_sql('zepto');")
        print("  SELECT portal_daily_grid_sql('amazon');")
        print("  SELECT portal_daily_grid_sql('blinkit');")
        print("  -- Get a specific month:")
        print("  SELECT portal_daily_grid_sql('zepto', '2026-01-01', '2026-01-31');")
        print("  -- Then copy the result and run it as a new query.")

if __name__ == "__main__":
    install()
