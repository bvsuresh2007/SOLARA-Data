"""
Seeds the cities table from Zepto city data in the master Excel.

Usage:
    python scripts/seed_cities.py
    python scripts/seed_cities.py --file "data/source/SOLARA - Daily Sales Tracking FY 25-26.xlsx"
"""
import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from sqlalchemy import text
from scripts.db_utils import engine
from shared.constants import normalise_city, CITY_REGION_MAP

DEFAULT_FILE = "data/source/SOLARA - Daily Sales Tracking FY 25-26.xlsx"


def extract_zepto_cities(xl: pd.ExcelFile) -> set[str]:
    """Read all Zepto sheets and return a set of normalised canonical city names."""
    zepto_sheets = [s for s in xl.sheet_names if s.strip().lower().startswith("zepto")]
    cities: set[str] = set()

    for sheet in zepto_sheets:
        df = pd.read_excel(xl, sheet_name=sheet, header=None)

        # Find the city pivot header row (contains 'Row Labels' in col 8)
        pivot_start = None
        for i, row in df.iterrows():
            vals = [str(v).strip() for v in row if pd.notna(v)]
            if "Row Labels" in vals:
                pivot_start = i + 1
                break

        if pivot_start is None:
            continue

        # Collect city names until 'Grand Total'
        for i in range(pivot_start, len(df)):
            raw = df.iloc[i, 8]
            if pd.isna(raw):
                continue
            canonical = normalise_city(str(raw))
            if canonical.lower() == "grand total":
                break
            if canonical:
                cities.add(canonical)

    return cities


def seed(file_path: str):
    xl = pd.ExcelFile(file_path)
    cities = extract_zepto_cities(xl)
    print(f"Extracted {len(cities)} unique cities after normalisation.")

    inserted = 0
    skipped = 0

    with engine.connect() as conn:
        # Fetch already-existing city names
        existing = {
            row[0] for row in conn.execute(text("SELECT name FROM cities")).fetchall()
        }

        for city in sorted(cities):
            if city in existing:
                skipped += 1
                continue

            region = CITY_REGION_MAP.get(city)
            if region is None:
                print(f"  [WARN] No region mapping for '{city}' — inserting with region=NULL")

            conn.execute(
                text(
                    "INSERT INTO cities (name, region) VALUES (:name, :region)"
                ),
                {"name": city, "region": region},
            )
            inserted += 1

        conn.commit()

    print(f"\nDone. Inserted: {inserted}  |  Already existed: {skipped}")
    print(f"Total cities in DB: {inserted + skipped}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=DEFAULT_FILE)
    args = parser.parse_args()
    seed(args.file)
