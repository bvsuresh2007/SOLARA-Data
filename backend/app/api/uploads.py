"""
File upload API — partial duplicate handling.

GET  /api/uploads/types       — list supported file types
POST /api/uploads/file        — upload and ingest a portal CSV or master Excel

Duplicate behaviour:
  - Rows whose composite key already exists in the DB are silently skipped.
  - Rows with unmapped SKUs or bad dates go into errors[].
  - HTTP 200 is always returned with counts; never 409.
"""

import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.inventory import ImportLog, InventorySnapshot
from ..models.sales import CityDailySales, DailySales
from ..schemas.uploads import (
    FILE_TYPE_META,
    FileTypeInfo,
    UploadError,
    UploadFileType,
    UploadResult,
)
from ..utils.excel_parsers import ColumnMismatchError, _parse_date_ymd, parse_file
from ..utils.portal_resolver import PortalResolver

router = APIRouter()
logger = logging.getLogger(__name__)

# ─── File types that produce city_daily_sales rows ────────────────────────────
_CITY_SALES_TYPES = {
    UploadFileType.BLINKIT_SALES,
    UploadFileType.SWIGGY_SALES,
    UploadFileType.ZEPTO_SALES,
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

    # ── Deduplicate against daily_sales ───────────────────────────────────────
    keys = [(r["_portal_id"], r["_product_id"], r["_sale_date"]) for r in resolved]
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

            earliest = min(r["sale_date"] for r in agg_to_insert) if agg_to_insert else date.today()
            portal_ids = {r["portal_id"] for r in agg_to_insert}
            portal_id_for_log = next(iter(portal_ids)) if len(portal_ids) == 1 else None

            log = ImportLog(
                source_type="portal_csv",
                portal_id=portal_id_for_log,
                file_name=filename,
                import_date=earliest,
                end_time=datetime.now(timezone.utc),
                status="success",
                records_imported=inserted,
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

            earliest = min(r["_snap_date"] for r in to_insert)
            portal_ids = {r["_portal_id"] for r in to_insert}
            portal_id_for_log = next(iter(portal_ids)) if len(portal_ids) == 1 else None

            log = ImportLog(
                source_type="portal_csv",
                portal_id=portal_id_for_log,
                file_name=filename,
                import_date=earliest,
                end_time=datetime.now(timezone.utc),
                status="success",
                records_imported=inserted,
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

    keys = [(r["_portal_id"], r["_product_id"], r["_sale_date"]) for r in resolved]
    existing = _fetch_existing_daily_keys(db, keys)
    to_insert = [r for r in resolved if (r["_portal_id"], r["_product_id"], r["_sale_date"]) not in existing]
    skipped = len(resolved) - len(to_insert)

    inserted = 0
    import_log_id = None

    if to_insert:
        try:
            daily_rows = [
                DailySales(
                    portal_id=r["_portal_id"],
                    product_id=r["_product_id"],
                    sale_date=r["_sale_date"],
                    units_sold=r["units_sold"],
                    revenue=r["revenue"],
                    asp=r["asp"],
                    data_source="master_excel",
                )
                for r in to_insert
            ]
            db.bulk_save_objects(daily_rows)
            inserted = len(daily_rows)

            earliest = min(r["_sale_date"] for r in to_insert)
            log = ImportLog(
                source_type="excel_import",
                file_name=filename,
                import_date=earliest,
                end_time=datetime.now(timezone.utc),
                status="success",
                records_imported=inserted,
            )
            db.add(log)
            db.flush()
            import_log_id = log.id
            db.commit()
        except IntegrityError:
            db.rollback()
            inserted = 0
            errors.append(UploadError(row=0, reason="Database conflict — no rows were inserted. Try re-uploading."))
            logger.warning("IntegrityError during master Excel insert — all rows rolled back")

    return UploadResult(
        file_type="", file_name="", rows_parsed=0,
        inserted=inserted, skipped=skipped, errors=errors, import_log_id=import_log_id,
    )


# =============================================================================
# Helpers
# =============================================================================

def _fetch_existing_daily_keys(db: Session, keys: list[tuple]) -> set[tuple]:
    if not keys:
        return set()
    rows = db.execute(
        select(DailySales.portal_id, DailySales.product_id, DailySales.sale_date).where(
            tuple_(DailySales.portal_id, DailySales.product_id, DailySales.sale_date).in_(keys)
        )
    ).fetchall()
    return {(r[0], r[1], r[2]) for r in rows}


def _fetch_existing_inventory_keys(db: Session, keys: list[tuple]) -> set[tuple]:
    if not keys:
        return set()
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
            ).in_(keys)
        )
    ).fetchall()
    return {(r[0], r[1], r[2]) for r in rows}


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
