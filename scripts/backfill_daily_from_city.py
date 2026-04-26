"""Backfill daily_sales from city_daily_sales for a given date.

Sums city_daily_sales across all cities per (portal, product) and upserts into
daily_sales. Excludes the `amazon` portal — SP-API (hourly_amazon_sync) is the
authoritative source for amazon daily_sales, and AmazonPI city-level data must
not pollute it.

Usage:
    python -m scripts.backfill_daily_from_city                  # yesterday
    python -m scripts.backfill_daily_from_city 2026-04-25       # specific date
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from backend.app.database import SessionLocal

EXCLUDED_PORTALS = ("amazon",)  # SP-API is authoritative for amazon


def backfill(report_date: date) -> dict[str, int]:
    db = SessionLocal()
    try:
        sql = text(
            """
            INSERT INTO daily_sales (
                portal_id, product_id, sale_date, units_sold, revenue,
                data_source, imported_at
            )
            SELECT cds.portal_id, cds.product_id, cds.sale_date,
                   SUM(cds.units_sold), SUM(cds.revenue),
                   'city_daily_sales_backfill', NOW()
            FROM city_daily_sales cds
            JOIN portals p ON p.id = cds.portal_id
            WHERE cds.sale_date = :d
              AND p.name <> ALL(:excluded)
            GROUP BY cds.portal_id, cds.product_id, cds.sale_date
            ON CONFLICT (portal_id, product_id, sale_date) DO UPDATE SET
                units_sold  = EXCLUDED.units_sold,
                revenue     = EXCLUDED.revenue,
                data_source = EXCLUDED.data_source,
                imported_at = EXCLUDED.imported_at
            """
        )
        result = db.execute(sql, {"d": report_date, "excluded": list(EXCLUDED_PORTALS)})
        db.commit()
        touched = result.rowcount

        summary_sql = text(
            """
            SELECT p.name, COUNT(*) AS products, SUM(ds.units_sold) AS units,
                   ROUND(SUM(ds.revenue)::numeric, 0) AS revenue
            FROM daily_sales ds
            JOIN portals p ON p.id = ds.portal_id
            WHERE ds.sale_date = :d
            GROUP BY p.name ORDER BY p.name
            """
        )
        print(f"[backfill_daily_from_city] {report_date}: touched {touched} daily_sales rows "
              f"(excluded portals: {', '.join(EXCLUDED_PORTALS)})")
        for row in db.execute(summary_sql, {"d": report_date}):
            print(f"  {row[0]:<15} products={row[1]:>4}  units={row[2]:>6}  "
                  f"revenue=Rs {row[3]:>12}")
        return {"rows_touched": touched}
    finally:
        db.close()


def _parse_date(arg: str | None) -> date:
    if not arg:
        return date.today() - timedelta(days=1)
    return date.fromisoformat(arg)


if __name__ == "__main__":
    target = _parse_date(sys.argv[1] if len(sys.argv) > 1 else None)
    backfill(target)
