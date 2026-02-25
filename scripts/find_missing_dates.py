"""
find_missing_dates.py
---------------------
Scans the database for dates where sales data is missing per portal,
from 2026-01-01 to today. Prints a summary table and saves a CSV report.

Usage:
    python scripts/find_missing_dates.py
    python scripts/find_missing_dates.py --start 2025-11-01
    python scripts/find_missing_dates.py --csv missing_dates.csv
"""

import sys
import csv
import argparse
from pathlib import Path
from datetime import date, timedelta

# Allow running from project root or scripts/
sys.path.insert(0, str(Path(__file__).parent.parent))

import os

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import DictCursor

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ["DATABASE_URL"]

# Only portals with active scrapers — skip Shopify/Flipkart/Myntra for now
# Maps portal DB name → friendly label
SCRAPER_PORTALS = {
    "swiggy":   "Swiggy",
    "blinkit":  "Blinkit",
    "zepto":    "Zepto",
    "amazon":   "Amazon PI",
    "easyecom": "EasyEcom",
}

# EasyEcom covers Myntra/Nykaa/CRED/Shopify — check by portal name in DB
# If easyecom isn't a portal in the DB, fall back to checking by import_logs source
EASYECOM_FALLBACK_PORTALS = ["myntra", "shopify"]


def date_range(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def get_connection():
    return psycopg2.connect(DATABASE_URL, connect_timeout=15, sslmode="require")


def fetch_portals(cur):
    cur.execute("SELECT id, name, display_name, is_active FROM portals ORDER BY id")
    return {row["name"]: dict(row) for row in cur.fetchall()}


def fetch_existing_dates(cur, portal_id: int, start: date, end: date) -> set:
    """Return set of dates that have ANY sales record for this portal."""
    cur.execute(
        """
        SELECT DISTINCT sale_date
        FROM daily_sales
        WHERE portal_id = %s
          AND sale_date BETWEEN %s AND %s
        """,
        (portal_id, start, end),
    )
    dates = {row[0] for row in cur.fetchall()}

    # Also check city_daily_sales for portals that go through the scraper pipeline
    cur.execute(
        """
        SELECT DISTINCT sale_date
        FROM city_daily_sales
        WHERE portal_id = %s
          AND sale_date BETWEEN %s AND %s
        """,
        (portal_id, start, end),
    )
    dates |= {row[0] for row in cur.fetchall()}
    return dates


def fetch_successful_imports(cur, portal_id: int, start: date, end: date) -> set:
    """Return dates with successful import_logs entries for this portal."""
    cur.execute(
        """
        SELECT DISTINCT import_date
        FROM import_logs
        WHERE portal_id = %s
          AND import_date BETWEEN %s AND %s
          AND status = 'success'
        """,
        (portal_id, start, end),
    )
    return {row[0] for row in cur.fetchall()}


def find_missing(all_dates: list, existing: set) -> list:
    return sorted(d for d in all_dates if d not in existing)


def render_table(results: dict, all_dates: list):
    """Print a compact summary table."""
    col_w = 16
    header = f"{'Portal':<{col_w}} {'Has Data':>10} {'Missing':>10} {'Coverage':>10}"
    print("\n" + "=" * len(header))
    print(header)
    print("=" * len(header))
    for portal_name, info in results.items():
        has = len(info["existing"])
        missing = len(info["missing"])
        total = len(all_dates)
        pct = f"{has/total*100:.1f}%" if total else "N/A"
        print(f"{info['label']:<{col_w}} {has:>10} {missing:>10} {pct:>10}")
    print("=" * len(header))


def render_detail(results: dict):
    """Print missing date lists per portal."""
    for portal_name, info in results.items():
        missing = info["missing"]
        if not missing:
            print(f"\n[OK] {info['label']}: No missing dates - full coverage!")
            continue
        print(f"\n[!!] {info['label']}: {len(missing)} missing date(s)")
        # Group consecutive ranges for readability
        ranges = []
        start = end = missing[0]
        for d in missing[1:]:
            if (d - end).days == 1:
                end = d
            else:
                ranges.append((start, end))
                start = end = d
        ranges.append((start, end))
        for s, e in ranges:
            if s == e:
                print(f"     {s}")
            else:
                print(f"     {s} to {e}  ({(e-s).days+1} days)")


def save_csv(results: dict, out_path: str):
    rows = []
    for portal_name, info in results.items():
        for d in info["missing"]:
            rows.append({
                "portal":       portal_name,
                "portal_label": info["label"],
                "missing_date": d.isoformat(),
                "weekday":      d.strftime("%A"),
            })
    if not rows:
        print("\nNo missing dates — nothing to save.")
        return
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["portal", "portal_label", "missing_date", "weekday"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV saved -> {out_path}  ({len(rows)} rows)")


def main():
    parser = argparse.ArgumentParser(description="Find missing sales dates per portal")
    parser.add_argument("--start", default="2026-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end",   default=date.today().isoformat(), help="End date YYYY-MM-DD")
    parser.add_argument("--csv",   default="", help="Optional output CSV path")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end   = date.fromisoformat(args.end)
    all_dates = list(date_range(start, end))

    print(f"\nScanning sales data from {start} to {end}  ({len(all_dates)} calendar days)")
    print(f"Portals: {', '.join(SCRAPER_PORTALS.values())}")

    try:
        conn = get_connection()
    except Exception as e:
        print(f"\nERROR: Could not connect to database.\n{e}")
        sys.exit(1)

    results = {}
    with conn, conn.cursor(cursor_factory=DictCursor) as cur:
        portals_in_db = fetch_portals(cur)

        for db_name, label in SCRAPER_PORTALS.items():
            # EasyEcom is stored as "easyecom" OR falls back to myntra/shopify
            portal_ids_to_check = []

            if db_name == "easyecom":
                if db_name in portals_in_db:
                    portal_ids_to_check = [portals_in_db[db_name]["id"]]
                else:
                    # Fallback: check myntra + shopify portals combined
                    for fb in EASYECOM_FALLBACK_PORTALS:
                        if fb in portals_in_db:
                            portal_ids_to_check.append(portals_in_db[fb]["id"])
                    if not portal_ids_to_check:
                        print(f"  SKIP {label}: no matching portal in DB")
                        continue
            else:
                if db_name not in portals_in_db:
                    print(f"  SKIP {label}: portal '{db_name}' not found in DB")
                    continue
                portal_ids_to_check = [portals_in_db[db_name]["id"]]

            # Collect existing dates across all relevant portal_ids
            existing: set = set()
            for pid in portal_ids_to_check:
                existing |= fetch_existing_dates(cur, pid, start, end)
                existing |= fetch_successful_imports(cur, pid, start, end)

            missing = find_missing(all_dates, existing)
            results[db_name] = {"label": label, "existing": existing, "missing": missing}
            status = "OK" if not missing else f"MISSING {len(missing)} days"
            print(f"  {label:<14} - {status}")

    render_table(results, all_dates)
    render_detail(results)

    if args.csv:
        save_csv(results, args.csv)
    else:
        # Auto-save to data/source/
        out_dir = Path(__file__).parent.parent / "data" / "source"
        out_dir.mkdir(parents=True, exist_ok=True)
        save_csv(results, str(out_dir / "missing_dates.csv"))


if __name__ == "__main__":
    main()
