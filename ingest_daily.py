"""One-shot ingestion script for daily sales files."""
import os, sys
from datetime import date
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.WARNING)

from scrapers.excel_parser import get_parser
from scrapers.data_transformer import DataTransformer
from backend.app.database import SessionLocal
from sqlalchemy.dialects.postgresql import insert
from backend.app.models.sales import CityDailySales, DailySales
from backend.app.models.inventory import InventorySnapshot
from backend.app.models.sales import Product
from backend.app.models.metadata import Portal

BATCH = 500
REPORT_DATE = date(2026, 3, 12)


def ingest(portal_name, file_path):
    parser = get_parser(portal_name)
    db = SessionLocal()
    transformer = DataTransformer(db)
    try:
        rows = parser.parse_sales(Path(file_path))
        if portal_name == "easyecom":
            transformed = transformer.transform_sales_rows_by_sku(rows)
        else:
            transformed = transformer.transform_sales_rows(rows)
        if not transformed:
            print(f"  [{portal_name}] 0 rows transformed, skip")
            return

        city_agg = defaultdict(lambda: {"units_sold": 0, "revenue": 0.0, "discount_amount": 0.0, "net_revenue": 0.0, "order_count": 0})
        for r in transformed:
            k = (r["portal_id"], r["product_id"], r.get("city_id"), r["sale_date"])
            city_agg[k]["units_sold"]      += r.get("units_sold", 0) or 0
            city_agg[k]["revenue"]         += r.get("revenue", 0) or 0
            city_agg[k]["discount_amount"] += r.get("discount_amount", 0) or 0
            city_agg[k]["net_revenue"]     += r.get("net_revenue", 0) or 0
            city_agg[k]["order_count"]     += r.get("order_count", 0) or 0

        city_rows = [
            {"portal_id": pid, "product_id": prod, "city_id": city, "sale_date": dt,
             "units_sold": v["units_sold"], "revenue": v["revenue"],
             "discount_amount": v["discount_amount"], "net_revenue": v["net_revenue"],
             "order_count": v["order_count"], "data_source": "portal_csv"}
            for (pid, prod, city, dt), v in city_agg.items()
        ]

        for i in range(0, len(city_rows), BATCH):
            db.execute(insert(CityDailySales).values(city_rows[i:i+BATCH]).on_conflict_do_update(
                index_elements=["portal_id", "product_id", "sale_date", "city_id"],
                set_={"units_sold": insert(CityDailySales).excluded.units_sold,
                      "revenue": insert(CityDailySales).excluded.revenue}))
        db.commit()

        daily_agg = defaultdict(lambda: {"units_sold": 0, "revenue": 0.0})
        for r in city_rows:
            k = (r["portal_id"], r["product_id"], r["sale_date"])
            daily_agg[k]["units_sold"] += r["units_sold"]
            daily_agg[k]["revenue"]    += r["revenue"]

        daily_rows = [
            {"portal_id": pid, "product_id": prod, "sale_date": dt,
             "units_sold": v["units_sold"], "revenue": v["revenue"],
             "asp": round(v["revenue"] / v["units_sold"], 2) if v["units_sold"] > 0 else None,
             "data_source": "portal_csv"}
            for (pid, prod, dt), v in daily_agg.items()
        ]

        for i in range(0, len(daily_rows), BATCH):
            db.execute(insert(DailySales).values(daily_rows[i:i+BATCH]).on_conflict_do_update(
                index_elements=["portal_id", "product_id", "sale_date"],
                set_={"units_sold": insert(DailySales).excluded.units_sold,
                      "revenue": insert(DailySales).excluded.revenue,
                      "asp": insert(DailySales).excluded.asp}))
        db.commit()
        print(f"  [{portal_name}] city={len(city_rows)}, daily={len(daily_rows)}")
    except Exception as e:
        import traceback; traceback.print_exc(); db.rollback()
    finally:
        db.close()


def ingest_amazon_pi(report_date):
    parser = get_parser("amazon_pi")
    db = SessionLocal()
    transformer = DataTransformer(db)
    city_agg = defaultdict(lambda: {"units_sold": 0, "revenue": 0.0, "discount_amount": 0.0, "net_revenue": 0.0, "order_count": 0})

    pi_dir = Path(f"data/raw/amazon_pi/{report_date.strftime('%Y-%m-%d')}")
    for f in sorted(pi_dir.glob("*.xlsx")):
        try:
            rows = parser.parse_sales(f)
            transformed = transformer.transform_sales_rows(rows)
            for r in transformed:
                k = (r["portal_id"], r["product_id"], r.get("city_id"), r["sale_date"])
                city_agg[k]["units_sold"]      += r.get("units_sold", 0) or 0
                city_agg[k]["revenue"]         += r.get("revenue", 0) or 0
                city_agg[k]["discount_amount"] += r.get("discount_amount", 0) or 0
                city_agg[k]["net_revenue"]     += r.get("net_revenue", 0) or 0
                city_agg[k]["order_count"]     += r.get("order_count", 0) or 0
            print(f"    {f.name}: {len(transformed)} rows")
        except Exception as e:
            print(f"    SKIP {f.name}: {e}")

    city_rows = [
        {"portal_id": pid, "product_id": prod, "city_id": city, "sale_date": dt,
         "units_sold": v["units_sold"], "revenue": v["revenue"],
         "discount_amount": v["discount_amount"], "net_revenue": v["net_revenue"],
         "order_count": v["order_count"], "data_source": "portal_csv"}
        for (pid, prod, city, dt), v in city_agg.items()
    ]

    for i in range(0, len(city_rows), BATCH):
        db.execute(insert(CityDailySales).values(city_rows[i:i+BATCH]).on_conflict_do_update(
            index_elements=["portal_id", "product_id", "sale_date", "city_id"],
            set_={"units_sold": insert(CityDailySales).excluded.units_sold,
                  "revenue": insert(CityDailySales).excluded.revenue}))
    db.commit()

    daily_agg = defaultdict(lambda: {"units_sold": 0, "revenue": 0.0})
    for r in city_rows:
        k = (r["portal_id"], r["product_id"], r["sale_date"])
        daily_agg[k]["units_sold"] += r["units_sold"]
        daily_agg[k]["revenue"]    += r["revenue"]

    daily_rows = [
        {"portal_id": pid, "product_id": prod, "sale_date": dt,
         "units_sold": v["units_sold"], "revenue": v["revenue"],
         "asp": round(v["revenue"] / v["units_sold"], 2) if v["units_sold"] > 0 else None,
         "data_source": "portal_csv"}
        for (pid, prod, dt), v in daily_agg.items()
    ]

    for i in range(0, len(daily_rows), BATCH):
        db.execute(insert(DailySales).values(daily_rows[i:i+BATCH]).on_conflict_do_update(
            index_elements=["portal_id", "product_id", "sale_date"],
            set_={"units_sold": insert(DailySales).excluded.units_sold,
                  "revenue": insert(DailySales).excluded.revenue,
                  "asp": insert(DailySales).excluded.asp}))
    db.commit()
    print(f"  [amazon_pi] city={len(city_rows)}, daily={len(daily_rows)}")
    db.close()


def ingest_blinkit_soh(file_path: str, snapshot_date: date) -> None:
    """
    Parse the Blinkit SOH Excel and upsert backend_stock + frontend_stock
    into inventory_snapshots.

    Matches by Item Id → product_portal_mapping.portal_sku (Blinkit numeric IDs).
    Aggregates across all warehouse rows per item before upserting.
    """
    import pandas as pd
    import math
    from backend.app.models.sales import ProductPortalMapping

    p = Path(file_path)
    if not p.exists():
        print(f"  [blinkit_soh] File not found, skipping: {file_path}")
        return

    df = pd.read_csv(p) if p.suffix.lower() == ".csv" else pd.read_excel(p)
    df.columns = [str(c).strip().lower() for c in df.columns]

    def find_col(keywords):
        for kw in keywords:
            for col in df.columns:
                if kw in col:
                    return col
        return None

    item_id_col  = find_col(["item id", "item_id", "itemid"])
    backend_col  = find_col(["backend quantity", "backend qty", "backend"])
    frontend_col = find_col(["frontend quantity", "frontend qty", "frontend"])

    if not item_id_col:
        print(f"  [blinkit_soh] Could not find item id column. Columns: {list(df.columns)}")
        return
    if not backend_col and not frontend_col:
        print(f"  [blinkit_soh] Could not find backend/frontend columns. Columns: {list(df.columns)}")
        return

    print(f"  [blinkit_soh] Columns — item_id={item_id_col!r} backend={backend_col!r} frontend={frontend_col!r}")

    def safe_float(v):
        try:
            f = float(v)
            return 0.0 if math.isnan(f) else f
        except (ValueError, TypeError):
            return 0.0

    # Aggregate backend + frontend across all warehouse rows per item_id
    item_agg: dict[str, dict] = {}
    for _, row in df.iterrows():
        item_id = str(row.get(item_id_col, "")).strip().rstrip(".0")
        if not item_id or item_id.lower() in ("nan", ""):
            continue
        if item_id not in item_agg:
            item_agg[item_id] = {"backend": 0.0, "frontend": 0.0}
        item_agg[item_id]["backend"]  += safe_float(row[backend_col])  if backend_col  else 0.0
        item_agg[item_id]["frontend"] += safe_float(row[frontend_col]) if frontend_col else 0.0

    db = SessionLocal()
    try:
        blinkit_portal = db.query(Portal).filter(Portal.name.ilike("%blinkit%")).first()
        if not blinkit_portal:
            print("  [blinkit_soh] Blinkit portal not found in DB")
            return

        # portal_sku (item_id string) → product_id
        mappings = db.query(ProductPortalMapping).filter(
            ProductPortalMapping.portal_id == blinkit_portal.id
        ).all()
        portal_sku_to_product = {str(m.portal_sku).strip(): m.product_id for m in mappings if m.portal_sku}

        rows_upserted = 0
        rows_skipped = 0
        for item_id, agg in item_agg.items():
            product_id = portal_sku_to_product.get(item_id)
            if not product_id:
                rows_skipped += 1
                continue

            stmt = insert(InventorySnapshot).values(
                portal_id=blinkit_portal.id,
                product_id=product_id,
                snapshot_date=snapshot_date,
                backend_stock=agg["backend"],
                frontend_stock=agg["frontend"],
            ).on_conflict_do_update(
                index_elements=["portal_id", "product_id", "snapshot_date"],
                set_={
                    "backend_stock":  insert(InventorySnapshot).excluded.backend_stock,
                    "frontend_stock": insert(InventorySnapshot).excluded.frontend_stock,
                }
            )
            db.execute(stmt)
            rows_upserted += 1

        db.commit()
        print(f"  [blinkit_soh] upserted={rows_upserted} skipped={rows_skipped} (no portal_sku match)")
    except Exception as e:
        db.rollback()
        print(f"  [blinkit_soh] ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        db.close()


def ingest_swiggy_soh(file_path: str, snapshot_date) -> None:
    """
    Parse the Swiggy SOH CSV/Excel and upsert portal_stock into inventory_snapshots.

    Matches by SkuCode → product_portal_mapping.portal_sku (Swiggy numeric IDs).
    Aggregates WarehouseQtyAvailable across all facility rows per SKU.
    """
    import pandas as pd
    import math
    from backend.app.models.sales import ProductPortalMapping

    p = Path(file_path)
    if not p.exists():
        print(f"  [swiggy_soh] File not found, skipping: {file_path}")
        return

    df = pd.read_csv(p) if p.suffix.lower() == ".csv" else pd.read_excel(p)
    df.columns = [str(c).strip().lower() for c in df.columns]

    def find_col(keywords):
        for kw in keywords:
            for col in df.columns:
                if kw in col:
                    return col
        return None

    sku_col   = find_col(["skucode", "sku_code", "sku code", "sku"])
    stock_col = find_col(["warehouseqtyavailable", "warehouse qty available", "warehouse_qty", "qty available", "stock"])

    if not sku_col:
        print(f"  [swiggy_soh] Could not find SkuCode column. Columns: {list(df.columns)}")
        return
    if not stock_col:
        print(f"  [swiggy_soh] Could not find stock column. Columns: {list(df.columns)}")
        return

    print(f"  [swiggy_soh] Columns — sku={sku_col!r} stock={stock_col!r}")

    def safe_float(v):
        try:
            f = float(v)
            return 0.0 if math.isnan(f) else f
        except (ValueError, TypeError):
            return 0.0

    # Aggregate WarehouseQtyAvailable across all facility rows per SKU
    sku_agg: dict[str, float] = {}
    for _, row in df.iterrows():
        sku = str(row.get(sku_col, "")).strip().rstrip(".0")
        if not sku or sku.lower() in ("nan", ""):
            continue
        sku_agg[sku] = sku_agg.get(sku, 0.0) + safe_float(row[stock_col])

    db = SessionLocal()
    try:
        swiggy_portal = db.query(Portal).filter(Portal.name.ilike("%swiggy%")).first()
        if not swiggy_portal:
            print("  [swiggy_soh] Swiggy portal not found in DB")
            return

        mappings = db.query(ProductPortalMapping).filter(
            ProductPortalMapping.portal_id == swiggy_portal.id
        ).all()
        portal_sku_to_product = {str(m.portal_sku).strip(): m.product_id for m in mappings if m.portal_sku}

        rows_upserted = 0
        rows_skipped  = 0
        for sku, total_stock in sku_agg.items():
            product_id = portal_sku_to_product.get(sku)
            if not product_id:
                rows_skipped += 1
                continue

            stmt = insert(InventorySnapshot).values(
                portal_id=swiggy_portal.id,
                product_id=product_id,
                snapshot_date=snapshot_date,
                portal_stock=total_stock,
            ).on_conflict_do_update(
                index_elements=["portal_id", "product_id", "snapshot_date"],
                set_={"portal_stock": insert(InventorySnapshot).excluded.portal_stock}
            )
            db.execute(stmt)
            rows_upserted += 1

        db.commit()
        print(f"  [swiggy_soh] upserted={rows_upserted} skipped={rows_skipped} (no portal_sku match)")
    except Exception as e:
        db.rollback()
        print(f"  [swiggy_soh] ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        db.close()


def ingest_zepto_soh(file_path: str, snapshot_date: date) -> None:
    """
    Parse the Zepto Vendor Inventory_F report and upsert portal_stock
    into inventory_snapshots.

    Matches by Item Id / SKU → product_portal_mapping.portal_sku (Zepto codes).
    Aggregates available/closing stock across any duplicate rows per SKU.
    """
    import pandas as pd
    import math
    from backend.app.models.sales import ProductPortalMapping

    p = Path(file_path)
    if not p.exists():
        print(f"  [zepto_soh] File not found, skipping: {file_path}")
        return

    df = pd.read_csv(p) if p.suffix.lower() == ".csv" else pd.read_excel(p)
    df.columns = [str(c).strip().lower() for c in df.columns]

    def find_col(keywords):
        for kw in keywords:
            for col in df.columns:
                if kw in col:
                    return col
        return None

    # Zepto inventory report columns (may vary slightly):
    # "item_id", "item id", "sku", "sku_id" for the product identifier
    # "closing_stock", "closing stock", "available_stock", "quantity" for stock
    sku_col   = find_col(["item_id", "item id", "itemid", "sku_id", "sku id", "skuid", "sku"])
    stock_col = find_col(["closing_stock", "closing stock", "available_stock", "available stock",
                           "quantity_available", "quantity available", "quantity", "stock"])

    if not sku_col:
        print(f"  [zepto_soh] Could not find SKU/item_id column. Columns: {list(df.columns)}")
        return
    if not stock_col:
        print(f"  [zepto_soh] Could not find stock column. Columns: {list(df.columns)}")
        return

    print(f"  [zepto_soh] Columns — sku={sku_col!r} stock={stock_col!r}")

    def safe_float(v):
        try:
            f = float(v)
            return 0.0 if math.isnan(f) else f
        except (ValueError, TypeError):
            return 0.0

    # Aggregate stock per SKU (sum across any multi-row per SKU)
    sku_agg: dict[str, float] = {}
    for _, row in df.iterrows():
        sku = str(row.get(sku_col, "")).strip().rstrip(".0")
        if not sku or sku.lower() in ("nan", ""):
            continue
        sku_agg[sku] = sku_agg.get(sku, 0.0) + safe_float(row[stock_col])

    db = SessionLocal()
    try:
        zepto_portal = db.query(Portal).filter(Portal.name.ilike("%zepto%")).first()
        if not zepto_portal:
            print("  [zepto_soh] Zepto portal not found in DB")
            return

        mappings = db.query(ProductPortalMapping).filter(
            ProductPortalMapping.portal_id == zepto_portal.id
        ).all()
        portal_sku_to_product = {str(m.portal_sku).strip(): m.product_id for m in mappings if m.portal_sku}

        rows_upserted = 0
        rows_skipped  = 0
        for sku, total_stock in sku_agg.items():
            product_id = portal_sku_to_product.get(sku)
            if not product_id:
                rows_skipped += 1
                continue

            stmt = insert(InventorySnapshot).values(
                portal_id=zepto_portal.id,
                product_id=product_id,
                snapshot_date=snapshot_date,
                portal_stock=total_stock,
            ).on_conflict_do_update(
                index_elements=["portal_id", "product_id", "snapshot_date"],
                set_={"portal_stock": insert(InventorySnapshot).excluded.portal_stock}
            )
            db.execute(stmt)
            rows_upserted += 1

        db.commit()
        print(f"  [zepto_soh] upserted={rows_upserted} skipped={rows_skipped} (no portal_sku match)")
    except Exception as e:
        db.rollback()
        print(f"  [zepto_soh] ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    d = REPORT_DATE
    print(f"Ingesting sales data for {d}")
    ingest("swiggy",   f"data/raw/swiggy/swiggy_sales_{d}.xlsx")
    ingest("blinkit",  f"data/raw/blinkit/blinkit_sales_{d}.xlsx")
    ingest("zepto",    f"data/raw/zepto/zepto_sales_{d}.xlsx")
    ingest("easyecom", f"data/raw/easyecom/easyecom_sales_{d}.csv")
    print("  [amazon_pi] parsing all category files...")
    ingest_amazon_pi(d)
    print("  [blinkit_soh] ingesting SOH inventory...")
    # scraper saves as .csv; fall back to .xlsx if csv not found
    soh_csv  = f"data/raw/blinkit/blinkit_soh_{d}.csv"
    soh_xlsx = f"data/raw/blinkit/blinkit_soh_{d}.xlsx"
    ingest_blinkit_soh(soh_csv if Path(soh_csv).exists() else soh_xlsx, d)
    print("  [swiggy_soh] ingesting SOH inventory...")
    swiggy_soh_csv  = f"data/raw/swiggy/swiggy_soh_{d}.csv"
    swiggy_soh_xlsx = f"data/raw/swiggy/swiggy_soh_{d}.xlsx"
    ingest_swiggy_soh(swiggy_soh_csv if Path(swiggy_soh_csv).exists() else swiggy_soh_xlsx, d)
    print("  [zepto_soh] ingesting SOH inventory...")
    zepto_soh_csv  = f"data/raw/zepto/zepto_soh_{d}.csv"
    zepto_soh_xlsx = f"data/raw/zepto/zepto_soh_{d}.xlsx"
    ingest_zepto_soh(zepto_soh_csv if Path(zepto_soh_csv).exists() else zepto_soh_xlsx, d)
    print("Done.")
