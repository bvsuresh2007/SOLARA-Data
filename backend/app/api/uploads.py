"""
File upload API — partial duplicate handling.

GET  /api/uploads/types       — list supported file types
POST /api/uploads/file        — upload and ingest a portal CSV or master Excel
POST /api/uploads/sku-mapping — upload SKU mapping file to sync product names & new SKUs

Duplicate behaviour:
  - Flipkart Kitchen / Appliances: latest file always wins — existing rows for
    the same (portal_id, product_id, sale_date) are deleted and replaced.
  - All other types: rows whose composite key already exists are silently skipped.
  - Rows with unmapped SKUs or bad dates go into errors[].
  - HTTP 200 is always returned with counts; never 409.
"""

import io
import logging
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.inventory import ImportLog, InventorySnapshot
from ..models.sales import CityDailySales, DailySales, Product
from ..schemas.uploads import (
    FILE_TYPE_META,
    FileTypeInfo,
    UploadError,
    UploadFileType,
    UploadResult,
)
from ..utils.excel_parsers import ColumnMismatchError, _parse_date_ymd, parse_file
from ..utils.portal_resolver import PortalResolver


class SkuMappingResult(BaseModel):
    file_name: str
    rows_parsed: int
    updated: int
    added: int
    skipped: int
    errors: list[str]
    time_taken_s: Optional[float] = None

router = APIRouter()
logger = logging.getLogger(__name__)

# ─── File types that overwrite (upsert) existing daily_sales rows ─────────────
# For these portals the latest uploaded file is always authoritative — existing
# rows for the same (portal_id, product_id, sale_date) are deleted and replaced.
_UPSERT_SALES_TYPES = {
    UploadFileType.FLIPKART_KITCHEN,
    UploadFileType.FLIPKART_APPLIANCES,
}

# ─── File types that produce city_daily_sales rows ────────────────────────────
_CITY_SALES_TYPES = {
    UploadFileType.BLINKIT_SALES,
    UploadFileType.SWIGGY_SALES,
    UploadFileType.ZEPTO_SALES,
    UploadFileType.EASYECOM_SALES,   # has Shipping City column
}

# ─── File types that produce inventory_snapshot rows ──────────────────────────
_INVENTORY_TYPES = {
    UploadFileType.BLINKIT_INVENTORY,
    UploadFileType.SWIGGY_INVENTORY,
    UploadFileType.ZEPTO_INVENTORY,
}


# =============================================================================
# GET /types
# =============================================================================

@router.get(
    "/types",
    response_model=list[FileTypeInfo],
    summary="List supported upload file types",
)
def list_file_types():
    return [
        FileTypeInfo(
            value=ft.value,
            label=meta["label"],
            description=meta["description"],
            target_tables=meta["target_tables"],
        )
        for ft, meta in FILE_TYPE_META.items()
    ]


# =============================================================================
# POST /file
# =============================================================================

@router.post(
    "/file",
    response_model=UploadResult,
    summary="Upload a portal CSV or master Excel file",
    description=(
        "Parse the uploaded file using the correct column mapping for the given file_type. "
        "Rows that already exist in the DB are skipped; new rows are inserted. "
        "Returns a summary of inserted, skipped, and error counts. Always returns HTTP 200."
    ),
)
async def upload_file(
    file_type: UploadFileType = Query(..., description="Type of file being uploaded"),
    file: UploadFile = File(..., description="The CSV or Excel file to ingest"),
    db: Session = Depends(get_db),
):
    filename = file.filename or "upload"
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit")

    _t_start = time.monotonic()

    # ── 1. Parse file ─────────────────────────────────────────────────────────
    try:
        raw_rows = parse_file(file_type.value, content, filename)
    except ColumnMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": (
                    f"The uploaded file does not match the expected format for '{file_type.value}'. "
                    "It may be a different version of the export. Please check the column names."
                ),
                "missing_columns": exc.missing,
                "columns_found_in_file": exc.found,
            },
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc)},
        )
    except Exception as exc:
        logger.exception("Unexpected error parsing file %s (%s)", filename, file_type)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": f"Could not parse file: {exc}"},
        )

    rows_parsed = len(raw_rows)

    # ── 2. Route to correct pipeline ──────────────────────────────────────────
    if file_type in _INVENTORY_TYPES:
        result = _process_inventory(db, raw_rows, file_type, filename)
    elif file_type == UploadFileType.MASTER_EXCEL:
        result = _process_master_excel(db, raw_rows, filename)
    else:
        result = _process_sales(db, raw_rows, file_type, filename)

    result.rows_parsed = rows_parsed
    result.file_name = filename
    result.file_type = file_type.value
    result.time_taken_s = round(time.monotonic() - _t_start, 1)
    return result


# =============================================================================
# Sales pipeline (portal CSV + Amazon PI + Shopify)
# =============================================================================

def _process_sales(
    db: Session,
    raw_rows: list[dict],
    file_type: UploadFileType,
    filename: str,
) -> UploadResult:
    resolver = PortalResolver(db)
    errors: list[UploadError] = []
    resolved: list[dict] = []

    for idx, row in enumerate(raw_rows, start=1):
        portal_name: str = row.get("portal", "")
        portal_id = resolver.portal_id(portal_name)
        if portal_id is None:
            errors.append(UploadError(row=idx, reason=f"Portal '{portal_name}' not found in DB"))
            continue

        sku = str(row.get("portal_product_id", "")).strip()
        if not sku:
            errors.append(UploadError(row=idx, reason="Empty portal_product_id (SKU)"))
            continue

        # EasyEcom rows use SOL-XXXX internal SKU codes — resolve directly from
        # products table (no product_portal_mapping entries needed for these portals).
        if file_type == UploadFileType.EASYECOM_SALES:
            product_id = resolver.product_id_by_sku(sku)
            if product_id is None:
                errors.append(UploadError(row=idx, reason=f"SKU '{sku}' not found in products table"))
                continue
        else:
            product_id = resolver.product_id(portal_id, sku)
            if product_id is None:
                errors.append(UploadError(row=idx, reason=f"SKU '{sku}' not mapped for portal '{portal_name}'"))
                continue

        sale_date: Optional[date] = row.get("sale_date")
        if sale_date is None:
            errors.append(UploadError(row=idx, reason=f"Invalid or missing date (value: {row.get('sale_date')!r})"))
            continue

        resolved.append({
            **row,
            "_portal_id": portal_id,
            "_product_id": product_id,
            "_sale_date": sale_date,
        })

    if not resolved:
        return UploadResult(
            file_type="",
            file_name="",
            rows_parsed=0,
            inserted=0,
            skipped=0,
            errors=errors,
            import_log_id=None,
        )

    # ── Deduplicate / overwrite against daily_sales ───────────────────────────
    keys = [(r["_portal_id"], r["_product_id"], r["_sale_date"]) for r in resolved]

    if file_type in _UPSERT_SALES_TYPES:
        # Delete existing rows so the latest uploaded file always wins
        existing_daily = _fetch_existing_daily_keys(db, keys)
        rows_to_delete = [k for k in keys if k in existing_daily]
        if rows_to_delete:
            db.query(DailySales).filter(
                tuple_(DailySales.portal_id, DailySales.product_id, DailySales.sale_date)
                .in_(rows_to_delete)
            ).delete(synchronize_session=False)
        to_insert = resolved
        skipped = 0
    else:
        existing_daily = _fetch_existing_daily_keys(db, keys)
        to_insert = [r for r in resolved if (r["_portal_id"], r["_product_id"], r["_sale_date"]) not in existing_daily]
        skipped = len(resolved) - len(to_insert)

    inserted = 0
    import_log_id = None

    if to_insert:
        # ── Insert into city_daily_sales (if applicable) ──────────────────────
        if file_type in _CITY_SALES_TYPES:
            _insert_city_sales(db, to_insert, resolver)

        # ── Aggregate by (portal_id, product_id, date) → daily_sales ─────────
        aggregated = _aggregate_to_daily(to_insert)
        # Re-check daily_sales for the aggregated keys (some may already exist from other city rows)
        agg_keys = [(r["portal_id"], r["product_id"], r["sale_date"]) for r in aggregated]
        existing_agg = _fetch_existing_daily_keys(db, agg_keys)
        agg_to_insert = [r for r in aggregated if (r["portal_id"], r["product_id"], r["sale_date"]) not in existing_agg]

        try:
            daily_rows = [
                DailySales(
                    portal_id=r["portal_id"],
                    product_id=r["product_id"],
                    sale_date=r["sale_date"],
                    units_sold=r["units_sold"],
                    revenue=r["revenue"],
                    asp=r["asp"],
                    data_source="portal_csv",
                )
                for r in agg_to_insert
            ]
            db.bulk_save_objects(daily_rows)
            inserted = len(agg_to_insert)

            # Create one import log per portal so pipeline health tracks each
            portal_ids = {r["portal_id"] for r in agg_to_insert}
            now = datetime.now(timezone.utc)
            for pid in portal_ids:
                pid_rows = [r for r in agg_to_insert if r["portal_id"] == pid]
                log = ImportLog(
                    source_type="portal_csv",
                    portal_id=pid,
                    file_name=filename,
                    import_date=min(r["sale_date"] for r in pid_rows),
                    end_time=now,
                    status="success",
                    records_imported=len(pid_rows),
                )
                db.add(log)
            db.flush()
            import_log_id = log.id
            db.commit()
        except IntegrityError:
            db.rollback()
            inserted = 0
            errors.append(UploadError(row=0, reason="Database conflict — no rows were inserted. Try re-uploading."))
            logger.warning("IntegrityError during sales insert — all rows rolled back")

    return UploadResult(
        file_type="",
        file_name="",
        rows_parsed=0,
        inserted=inserted,
        skipped=skipped,
        errors=errors,
        import_log_id=import_log_id,
    )


# =============================================================================
# Inventory pipeline
# =============================================================================

def _process_inventory(
    db: Session,
    raw_rows: list[dict],
    file_type: UploadFileType,
    filename: str,
) -> UploadResult:
    resolver = PortalResolver(db)
    errors: list[UploadError] = []
    resolved: list[dict] = []

    for idx, row in enumerate(raw_rows, start=1):
        portal_name = row.get("portal", "")
        portal_id = resolver.portal_id(portal_name)
        if portal_id is None:
            errors.append(UploadError(row=idx, reason=f"Portal '{portal_name}' not found in DB"))
            continue

        sku = str(row.get("portal_product_id", "")).strip()
        if not sku:
            errors.append(UploadError(row=idx, reason="Empty portal_product_id (SKU)"))
            continue

        product_id = resolver.product_id(portal_id, sku)
        if product_id is None:
            errors.append(UploadError(row=idx, reason=f"SKU '{sku}' not mapped for portal '{portal_name}'"))
            continue

        snap_date: Optional[date] = row.get("snapshot_date")
        if snap_date is None:
            errors.append(UploadError(row=idx, reason=f"Invalid or missing snapshot_date (value: {row.get('snapshot_date')!r})"))
            continue

        resolved.append({
            **row,
            "_portal_id": portal_id,
            "_product_id": product_id,
            "_snap_date": snap_date,
        })

    if not resolved:
        return UploadResult(
            file_type="", file_name="", rows_parsed=0,
            inserted=0, skipped=0, errors=errors, import_log_id=None,
        )

    keys = [(r["_portal_id"], r["_product_id"], r["_snap_date"]) for r in resolved]
    existing = _fetch_existing_inventory_keys(db, keys)
    to_insert = [r for r in resolved if (r["_portal_id"], r["_product_id"], r["_snap_date"]) not in existing]
    skipped = len(resolved) - len(to_insert)

    inserted = 0
    import_log_id = None

    if to_insert:
        try:
            snap_rows = [
                InventorySnapshot(
                    portal_id=r["_portal_id"],
                    product_id=r["_product_id"],
                    snapshot_date=r["_snap_date"],
                    backend_stock=r.get("backend_stock"),
                    frontend_stock=r.get("frontend_stock"),
                )
                for r in to_insert
            ]
            db.bulk_save_objects(snap_rows)
            inserted = len(snap_rows)

            # Create one import log per portal so pipeline health tracks each
            portal_ids = {r["_portal_id"] for r in to_insert}
            now = datetime.now(timezone.utc)
            for pid in portal_ids:
                pid_rows = [r for r in to_insert if r["_portal_id"] == pid]
                log = ImportLog(
                    source_type="portal_csv",
                    portal_id=pid,
                    file_name=filename,
                    import_date=min(r["_snap_date"] for r in pid_rows),
                    end_time=now,
                    status="success",
                    records_imported=len(pid_rows),
                )
                db.add(log)
            db.flush()
            import_log_id = log.id
            db.commit()
        except IntegrityError:
            db.rollback()
            inserted = 0
            errors.append(UploadError(row=0, reason="Database conflict — no rows were inserted. Try re-uploading."))
            logger.warning("IntegrityError during inventory insert — all rows rolled back")

    return UploadResult(
        file_type="", file_name="", rows_parsed=0,
        inserted=inserted, skipped=skipped, errors=errors, import_log_id=import_log_id,
    )


# =============================================================================
# Master Excel pipeline
# =============================================================================

def _process_master_excel(
    db: Session,
    raw_rows: list[dict],
    filename: str,
) -> UploadResult:
    """
    raw_rows from parse_master_excel() — each dict has:
      portal, sku_code, sale_date, units_sold, asp, revenue

    Master Excel uses sku_code (SOL-XXXX) resolved directly from products table,
    not via product_portal_mapping (unlike portal CSV files).
    """
    resolver = PortalResolver(db)
    errors: list[UploadError] = []
    resolved: list[dict] = []

    for idx, row in enumerate(raw_rows, start=1):
        portal_name = str(row.get("portal", "")).strip()
        portal_id = resolver.portal_id(portal_name)
        if portal_id is None:
            errors.append(UploadError(row=idx, reason=f"Portal '{portal_name}' not found in DB"))
            continue

        sku = str(row.get("sku_code", "")).strip()
        if not sku:
            errors.append(UploadError(row=idx, reason="Empty sku_code"))
            continue

        # Master Excel resolution: sku_code → product_id (direct, not via portal mapping)
        product_id = resolver.product_id_by_sku(sku)
        if product_id is None:
            errors.append(UploadError(row=idx, reason=f"SKU '{sku}' not found in products table"))
            continue

        sale_date: Optional[date] = row.get("sale_date")
        if isinstance(sale_date, str):
            sale_date = _parse_date_ymd(sale_date)
        if sale_date is None:
            errors.append(UploadError(row=idx, reason=f"Invalid date (value: {row.get('sale_date')!r})"))
            continue

        resolved.append({
            "_portal_id": portal_id,
            "_product_id": product_id,
            "_sale_date": sale_date,
            "units_sold": float(row.get("units_sold", 0) or 0),
            "revenue": float(row.get("revenue", 0) or 0),
            "asp": row.get("asp") or None,
        })

    if not resolved:
        return UploadResult(
            file_type="", file_name="", rows_parsed=0,
            inserted=0, skipped=0, errors=errors, import_log_id=None,
        )

    # Single-pass upsert: INSERT ... ON CONFLICT (portal_id, product_id, sale_date) DO NOTHING
    # This eliminates the separate fetch-existing-keys phase (was 667 round trips for 333K rows).
    _INSERT_BATCH = 5000
    inserted = 0
    import_log_id = None

    try:
        for i in range(0, len(resolved), _INSERT_BATCH):
            batch = resolved[i : i + _INSERT_BATCH]
            stmt = pg_insert(DailySales).values([
                {
                    "portal_id": r["_portal_id"],
                    "product_id": r["_product_id"],
                    "sale_date": r["_sale_date"],
                    "units_sold": r["units_sold"],
                    "revenue": r["revenue"],
                    "asp": r["asp"],
                    "data_source": "master_excel",
                }
                for r in batch
            ]).on_conflict_do_nothing(
                index_elements=["portal_id", "product_id", "sale_date"]
            )
            result_proxy = db.execute(stmt)
            inserted += result_proxy.rowcount

        skipped = len(resolved) - inserted

        if inserted > 0:
            # Create one import log per portal so pipeline health tracks each
            portal_ids = {r["_portal_id"] for r in resolved}
            now = datetime.now(timezone.utc)
            for pid in portal_ids:
                pid_rows = [r for r in resolved if r["_portal_id"] == pid]
                log = ImportLog(
                    source_type="excel_import",
                    portal_id=pid,
                    file_name=filename,
                    import_date=min(r["_sale_date"] for r in pid_rows),
                    end_time=now,
                    status="success",
                    records_imported=len(pid_rows),
                )
                db.add(log)
            db.flush()
            import_log_id = log.id

        db.commit()
    except IntegrityError:
        db.rollback()
        inserted = 0
        skipped = 0
        errors.append(UploadError(row=0, reason="Database conflict — no rows were inserted. Try re-uploading."))
        logger.warning("IntegrityError during master Excel insert — all rows rolled back")

    return UploadResult(
        file_type="", file_name="", rows_parsed=0,
        inserted=inserted, skipped=skipped, errors=errors, import_log_id=import_log_id,
    )


# =============================================================================
# POST /sku-mapping
# =============================================================================

@router.post(
    "/sku-mapping",
    response_model=SkuMappingResult,
    summary="Upload SKU mapping file to sync product names and add new SKUs",
)
async def upload_sku_mapping(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Accepts an .xlsx or .csv with at minimum a SKU column and a Product name column.
    Expected columns (case-insensitive, flexible naming):
      - SKU / sku_code / sku code / SKU CODE
      - Product / product_name / product name / Product Name / PRODUCT
      - Category / category_name / l2_name  (optional)

    For each row:
      - If the SKU already exists in products → UPDATE product_name (and category if provided)
      - If the SKU does not exist → INSERT new product
    Returns counts of updated / added / skipped rows.
    """
    import pandas as pd

    t_start = time.monotonic()
    filename = file.filename or "sku_mapping"
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 20 MB limit")

    # ── Parse file ────────────────────────────────────────────────────────────
    try:
        ext = (filename.rsplit(".", 1)[-1]).lower()
        if ext in ("xlsx", "xls"):
            df = pd.read_excel(io.BytesIO(content))
        else:
            df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"message": f"Could not parse file: {exc}"})

    # Normalise column names
    df.columns = [str(c).strip() for c in df.columns]

    def find_col(keywords: list[str]) -> Optional[str]:
        for kw in keywords:
            for col in df.columns:
                if col.lower() == kw.lower():
                    return col
        for kw in keywords:
            for col in df.columns:
                if kw.lower() in col.lower():
                    return col
        return None

    sku_col      = find_col(["SKU", "sku_code", "sku code", "SKU CODE"])
    sub_cat_col  = find_col(["Product Sub-category", "sub_category", "sub-category", "subcategory", "Sub Category", "Sub-Category"])
    product_col  = find_col(["Product Name", "product_name", "product name", "PRODUCT NAME", "Product", "PRODUCT"])
    category_col = find_col(["Category", "category_name", "l2_name", "CATEGORY"])

    if not sku_col:
        raise HTTPException(status_code=422, detail={"message": f"Could not find SKU column. Columns found: {list(df.columns)}"})
    if not product_col:
        raise HTTPException(status_code=422, detail={"message": f"Could not find Product name column. Columns found: {list(df.columns)}"})

    rows_parsed = len(df)
    updated = added = skipped = 0
    errors: list[str] = []

    # Build category name → id lookup if category column present
    cat_name_to_id: dict[str, int] = {}
    if category_col:
        from ..models.metadata import ProductCategory  # type: ignore
        cats = db.query(ProductCategory).all()
        for c in cats:
            if c.l2_name:
                cat_name_to_id[c.l2_name.lower().strip()] = c.id
            if c.l1_name:
                cat_name_to_id[c.l1_name.lower().strip()] = c.id  # fallback

    try:
        for _, row in df.iterrows():
            sku = str(row.get(sku_col, "")).strip()
            product_name = str(row.get(product_col, "")).strip()

            if not sku or sku.lower() == "nan":
                skipped += 1
                continue
            if not product_name or product_name.lower() == "nan":
                skipped += 1
                continue

            # Sub-category (optional)
            sub_category: Optional[str] = None
            if sub_cat_col:
                raw = str(row.get(sub_cat_col, "")).strip()
                if raw and raw.lower() != "nan":
                    sub_category = raw

            # Resolve category_id if provided
            category_id: Optional[int] = None
            if category_col:
                cat_raw = str(row.get(category_col, "")).strip().lower()
                category_id = cat_name_to_id.get(cat_raw)

            existing = db.query(Product).filter(Product.sku_code == sku).first()
            if existing:
                existing.product_name = product_name
                if sub_category is not None:
                    existing.sub_category = sub_category
                if category_id is not None:
                    existing.category_id = category_id
                updated += 1
            else:
                new_product = Product(
                    sku_code=sku,
                    product_name=product_name,
                    sub_category=sub_category,
                    category_id=category_id,
                    unit_type="pieces",
                )
                db.add(new_product)
                added += 1

        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Error processing SKU mapping file %s", filename)
        raise HTTPException(status_code=500, detail={"message": f"Database error: {exc}"})

    return SkuMappingResult(
        file_name=filename,
        rows_parsed=rows_parsed,
        updated=updated,
        added=added,
        skipped=skipped,
        errors=errors,
        time_taken_s=round(time.monotonic() - t_start, 1),
    )


# =============================================================================
# Helpers
# =============================================================================

_FETCH_BATCH = 500  # PostgreSQL stack depth limit with tuple IN() — stay well under


def _fetch_existing_daily_keys(db: Session, keys: list[tuple]) -> set[tuple]:
    if not keys:
        return set()
    existing: set[tuple] = set()
    for i in range(0, len(keys), _FETCH_BATCH):
        batch = keys[i : i + _FETCH_BATCH]
        rows = db.execute(
            select(DailySales.portal_id, DailySales.product_id, DailySales.sale_date).where(
                tuple_(DailySales.portal_id, DailySales.product_id, DailySales.sale_date).in_(batch)
            )
        ).fetchall()
        existing.update((r[0], r[1], r[2]) for r in rows)
    return existing


def _fetch_existing_inventory_keys(db: Session, keys: list[tuple]) -> set[tuple]:
    if not keys:
        return set()
    existing: set[tuple] = set()
    for i in range(0, len(keys), _FETCH_BATCH):
        batch = keys[i : i + _FETCH_BATCH]
        rows = db.execute(
            select(
                InventorySnapshot.portal_id,
                InventorySnapshot.product_id,
                InventorySnapshot.snapshot_date,
            ).where(
                tuple_(
                    InventorySnapshot.portal_id,
                    InventorySnapshot.product_id,
                    InventorySnapshot.snapshot_date,
                ).in_(batch)
            )
        ).fetchall()
        existing.update((r[0], r[1], r[2]) for r in rows)
    return existing


def _insert_city_sales(db: Session, rows: list[dict], resolver: PortalResolver) -> None:
    """Insert city_daily_sales rows for portal CSV files. Skips unknown cities."""
    # Deduplicate by composite key first
    keys = set()
    city_rows = []
    for row in rows:
        city_name = str(row.get("city", "")).strip()
        if not city_name:
            continue
        city_id = resolver.city_id(city_name)
        if city_id is None:
            continue
        key = (row["_portal_id"], row["_product_id"], city_id, row["_sale_date"])
        if key in keys:
            continue
        keys.add(key)
        city_rows.append(
            CityDailySales(
                portal_id=row["_portal_id"],
                product_id=row["_product_id"],
                city_id=city_id,
                sale_date=row["_sale_date"],
                units_sold=row.get("quantity_sold", 0),
                revenue=row.get("revenue", 0),
                discount_amount=row.get("discount_amount", 0),
                net_revenue=row.get("net_revenue", row.get("revenue", 0)),
                order_count=row.get("order_count", 0),
                data_source="portal_csv",
            )
        )
    if city_rows:
        sp = db.begin_nested()
        try:
            db.bulk_save_objects(city_rows)
            sp.commit()
        except IntegrityError:
            sp.rollback()
            logger.warning("IntegrityError inserting city_daily_sales — some rows skipped")


def _aggregate_to_daily(rows: list[dict]) -> list[dict]:
    """Aggregate city-level rows to (portal_id, product_id, sale_date) grain."""
    agg: dict[tuple, dict] = defaultdict(lambda: {"units_sold": 0.0, "revenue": 0.0})
    for row in rows:
        key = (row["_portal_id"], row["_product_id"], row["_sale_date"])
        agg[key]["units_sold"] += float(row.get("quantity_sold", 0) or 0)
        agg[key]["revenue"] += float(row.get("revenue", 0) or 0)

    result = []
    for (portal_id, product_id, sale_date), totals in agg.items():
        units = totals["units_sold"]
        revenue = totals["revenue"]
        asp = round(revenue / units, 2) if units > 0 else None
        result.append({
            "portal_id": portal_id,
            "product_id": product_id,
            "sale_date": sale_date,
            "units_sold": units,
            "revenue": revenue,
            "asp": asp,
        })
    return result
