"""
Import SKU mapping from Sku_mapping.xlsx into:
  1. product_portal_mapping — portal-specific codes (ASIN, FSN, Myntra, Blinkit, Swiggy)
  2. products.default_asp   — BAU ASP from the Excel file

Portal mapping:
  ASIN              → amazon   (portal_id=6)
  FSN               → flipkart (portal_id=5)
  STYLE ID(Myntra)  → myntra   (portal_id=4)
  STYLE ID(Blinkit) → blinkit  (portal_id=3)
  SWIGGY CODE       → swiggy   (portal_id=2)
"""

import pandas as pd
import psycopg2
from datetime import datetime, timezone

DB_URL = "postgresql://postgres.fyoegnmfdlfhfcnvocly:6LkqSuEXJ0zNLOCP@aws-1-ap-southeast-2.pooler.supabase.com:5432/postgres"
EXCEL_PATH = r"C:\Users\accou\Downloads\Sku_mapping.xlsx"

PORTAL_MAP = {
    "ASIN":              6,   # amazon
    "FSN":               5,   # flipkart
    "STYLE ID(Myntra)":  4,   # myntra
    "STYLE ID(Blinkit)": 3,   # blinkit
    "SWIGGY CODE":       2,   # swiggy
}


def main():
    df = pd.read_excel(EXCEL_PATH).iloc[:, :8].dropna(subset=["SKU CODE"])
    print(f"Read {len(df)} SKUs from Excel")

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    now = datetime.now(timezone.utc)

    # ── Load lookups ────────────────────────────────────────────
    cur.execute("SELECT id, sku_code FROM products")
    sku_to_pid = {row[1]: row[0] for row in cur.fetchall()}
    pid_to_sku = {v: k for k, v in sku_to_pid.items()}

    inserted = 0
    updated = 0
    skipped = 0
    asp_updated = 0

    for _, row in df.iterrows():
        sku = str(row["SKU CODE"]).strip()
        bau_asp = row.get("BAU ASP")
        product_id = sku_to_pid.get(sku)

        if not product_id:
            print(f"  SKIP: SKU {sku} not in products table")
            continue

        # ── Update BAU ASP ──────────────────────────────────────
        if pd.notna(bau_asp) and float(bau_asp) > 0:
            cur.execute(
                "UPDATE products SET default_asp = %s, updated_at = %s WHERE id = %s",
                (float(bau_asp), now, product_id),
            )
            asp_updated += 1

        # ── Upsert portal mappings ──────────────────────────────
        for col, portal_id in PORTAL_MAP.items():
            raw_val = row.get(col)
            if pd.isna(raw_val):
                continue

            portal_sku = str(raw_val).strip()
            if portal_sku in ("0", "0.0", ""):
                continue
            if portal_sku.endswith(".0"):
                portal_sku = portal_sku[:-2]

            # First delete any existing mapping for this product+portal
            # (since the unique constraint is on (portal_id, portal_sku), not (product_id, portal_id))
            cur.execute(
                """DELETE FROM product_portal_mapping
                   WHERE product_id = %s AND portal_id = %s""",
                (product_id, portal_id),
            )
            had_existing = cur.rowcount > 0

            # Now upsert using the actual unique constraint (portal_id, portal_sku)
            cur.execute(
                """INSERT INTO product_portal_mapping
                       (product_id, portal_id, portal_sku, portal_product_name, is_active, created_at)
                   VALUES (%s, %s, %s, NULL, true, %s)
                   ON CONFLICT (portal_id, portal_sku) DO UPDATE
                       SET product_id = EXCLUDED.product_id,
                           updated_at = %s""",
                (product_id, portal_id, portal_sku, now, now),
            )

            if had_existing:
                updated += 1
            else:
                inserted += 1

    conn.commit()

    print(f"\n{'='*50}")
    print(f"SUMMARY:")
    print(f"  Portal mappings inserted/upserted: {inserted}")
    print(f"  Portal mappings reassigned:        {updated}")
    print(f"  BAU ASP updated:                   {asp_updated}")
    print(f"{'='*50}")

    # ── Verify ──────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM product_portal_mapping")
    print(f"\nTotal mappings in DB now: {cur.fetchone()[0]}")

    # Show sample
    cur.execute("""
        SELECT p.sku_code, po.name, ppm.portal_sku, p.default_asp
        FROM product_portal_mapping ppm
        JOIN products p ON p.id = ppm.product_id
        JOIN portals po ON po.id = ppm.portal_id
        WHERE ppm.portal_id IN (2,3,4,5,6)
        ORDER BY p.sku_code, po.name
        LIMIT 30
    """)

    print("\nSAMPLE PORTAL MAPPINGS:")
    for r in cur.fetchall():
        print(f"  {r[0]:40s} | {r[1]:10s} | portal_sku={r[2]:20s} | BAU_ASP={r[3]}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
