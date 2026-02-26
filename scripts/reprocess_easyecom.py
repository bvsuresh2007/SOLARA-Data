"""
Re-process all EasyEcom CSVs in data/raw/easyecom/ with the updated MP Name
split parser.

Deletes existing daily_sales / city_daily_sales rows where portal_id equals the
(now-inactive) easyecom portal, then re-inserts everything correctly split into
Shopify, Meesho, Nykaa Fashion, CRED, Vaaree, and Offline portals.

Usage:
  python scripts/reprocess_easyecom.py
  python scripts/reprocess_easyecom.py --data-dir ./data/raw
  python scripts/reprocess_easyecom.py --dry-run   # parse only, no DB changes
"""
import argparse
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    ap = argparse.ArgumentParser(description="Re-process EasyEcom CSVs with MP Name split")
    ap.add_argument("--data-dir", default="./data/raw", help="Root data directory (default: ./data/raw)")
    ap.add_argument("--dry-run", action="store_true", help="Parse only; do not modify the DB")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    easyecom_dir = data_dir / "easyecom"

    if not easyecom_dir.exists():
        logger.error("EasyEcom data directory not found: %s", easyecom_dir)
        sys.exit(1)

    files = sorted(
        (f for f in easyecom_dir.glob("*")
         if f.is_file() and f.suffix.lower() in (".csv", ".xlsx", ".xls")),
        key=lambda p: p.name,
    )

    if not files:
        logger.info("No files found in %s — nothing to reprocess", easyecom_dir)
        return

    logger.info("Found %d EasyEcom file(s) to reprocess", len(files))

    from scrapers.excel_parser import EasyEcomParser
    parser = EasyEcomParser()

    all_rows: list[dict] = []
    for file in files:
        if file.stat().st_size == 0:
            logger.warning("Skipping empty file: %s", file.name)
            continue
        logger.info("Parsing %s ...", file.name)
        try:
            rows = parser.parse_sales(file)
            portal_counts: dict[str, int] = defaultdict(int)
            for r in rows:
                portal_counts[r["portal"]] += 1
            logger.info("  %d rows — %s", len(rows), dict(portal_counts))
            all_rows.extend(rows)
        except Exception as exc:
            logger.warning("  Failed to parse %s: %s", file.name, exc)

    logger.info("Total rows parsed across all files: %d", len(all_rows))
    portal_totals: dict[str, int] = defaultdict(int)
    for r in all_rows:
        portal_totals[r["portal"]] += 1
    for portal, cnt in sorted(portal_totals.items()):
        logger.info("  %-20s %d rows", portal, cnt)

    if args.dry_run:
        logger.info("Dry run — no DB changes made.")
        return

    from scripts.db_utils import get_session
    from scrapers.data_transformer import DataTransformer
    from scrapers.orchestrator import _upsert_sales, _upsert_daily_sales
    from sqlalchemy import text

    with get_session() as session:
        # 1. Find the easyecom portal_id
        row = session.execute(
            text("SELECT id FROM portals WHERE name = 'easyecom'")
        ).fetchone()
        if not row:
            logger.error(
                "Portal 'easyecom' not found in DB. "
                "Run: alembic upgrade 003_add_easyecom_portals"
            )
            sys.exit(1)
        easyecom_portal_id = row[0]
        logger.info("easyecom portal_id = %d", easyecom_portal_id)

        # 2. Delete existing easyecom-tagged rows
        res = session.execute(
            text("DELETE FROM city_daily_sales WHERE portal_id = :pid"),
            {"pid": easyecom_portal_id},
        )
        logger.info("Deleted %d city_daily_sales rows for easyecom", res.rowcount)

        res = session.execute(
            text("DELETE FROM daily_sales WHERE portal_id = :pid"),
            {"pid": easyecom_portal_id},
        )
        logger.info("Deleted %d daily_sales rows for easyecom", res.rowcount)
        session.commit()

        if not all_rows:
            logger.info("No rows to insert.")
            return

        # 3. Transform: portal slug + sku_code → IDs, city normalisation
        transformer = DataTransformer(session)
        transformed = transformer.transform_sales_rows_by_sku(all_rows)
        logger.info(
            "Transformed %d rows (%d skipped: unknown SKU / city / portal)",
            len(transformed),
            len(all_rows) - len(transformed),
        )

        if not transformed:
            logger.warning(
                "No rows survived transformation. "
                "Check that products table contains the SOL-XXXX SKU codes."
            )
            return

        # 4. Upsert into DB
        n_city = _upsert_sales(session, transformed)
        n_daily = _upsert_daily_sales(session, transformed)
        logger.info("Inserted %d city_daily_sales, %d daily_sales rows", n_city, n_daily)

        # 5. Summary by portal
        by_portal: dict[int, int] = defaultdict(int)
        for r in transformed:
            by_portal[r["portal_id"]] += 1
        logger.info("Breakdown by portal:")
        for pid, cnt in sorted(by_portal.items()):
            name_row = session.execute(
                text("SELECT name FROM portals WHERE id = :id"), {"id": pid}
            ).fetchone()
            pname = name_row[0] if name_row else str(pid)
            logger.info("  %-20s %d rows", pname, cnt)


if __name__ == "__main__":
    main()
