"""
Master import orchestrator — runs Phase 1 (seed) and/or Phase 2 (sales).

Usage:
    # Run both phases (recommended for first-time setup)
    python scripts/run_import.py --file "data/source/SOLARA - Daily Sales Tracking FY 25-26.xlsx"

    # Run only master data seed (products + mappings)
    python scripts/run_import.py --file "..." --phase seed

    # Run only sales/inventory import (requires products already seeded)
    python scripts/run_import.py --file "..." --phase sales

    # Import a new month's Excel file (re-running is always safe)
    python scripts/run_import.py --file "data/source/SOLARA - Daily Sales Tracking FY 26-27.xlsx"
"""
import argparse
import logging
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("run_import")


def main():
    parser = argparse.ArgumentParser(
        description="SOLARA — Import master Excel data into PostgreSQL database."
    )
    parser.add_argument(
        "--file",
        required=True,
        help='Path to the master Excel file (e.g., "data/source/SOLARA - Daily Sales Tracking FY 25-26.xlsx")',
    )
    parser.add_argument(
        "--phase",
        choices=["seed", "sales", "both"],
        default="both",
        help="Which phase to run: seed (products/mappings), sales (daily_sales/inventory), or both (default)",
    )
    args = parser.parse_args()

    file_path = args.file
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path!r}")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("SOLARA Data Import Pipeline")
    logger.info(f"File  : {file_path}")
    logger.info(f"Phase : {args.phase}")
    logger.info("=" * 60)

    overall_start = time.time()

    if args.phase in ("seed", "both"):
        logger.info("\n── PHASE 1: Seeding master data (products + portal mappings) ──")
        t0 = time.time()
        from scripts.seed_master_data import seed_from_excel
        seed_from_excel(file_path)
        logger.info(f"Phase 1 done in {time.time() - t0:.1f}s")

    if args.phase in ("sales", "both"):
        logger.info("\n── PHASE 2: Importing sales, inventory, targets, ad spend ──")
        t0 = time.time()
        from scripts.import_excel_sales import import_from_excel
        import_from_excel(file_path)
        logger.info(f"Phase 2 done in {time.time() - t0:.1f}s")

    logger.info(f"\nAll done in {time.time() - overall_start:.1f}s")
    logger.info("\nVerification queries:")
    logger.info("  SELECT COUNT(*) FROM products;")
    logger.info("  SELECT COUNT(*) FROM product_portal_mapping;")
    logger.info("  SELECT portal_id, COUNT(*), SUM(units_sold) FROM daily_sales GROUP BY portal_id;")
    logger.info("  SELECT MIN(sale_date), MAX(sale_date) FROM daily_sales;")
    logger.info("  SELECT COUNT(*) FROM inventory_snapshots;")
    logger.info("  SELECT COUNT(*) FROM monthly_targets;")


if __name__ == "__main__":
    main()
