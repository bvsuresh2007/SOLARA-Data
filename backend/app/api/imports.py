"""
Import endpoints for daily sales and inventory snapshots.

POST /api/imports/sales
POST /api/imports/inventory

Duplicate detection:
  - Checks for existing rows with the same composite key BEFORE inserting.
  - If ANY duplicate is found, returns HTTP 409 Conflict with the conflicting keys.
  - If no duplicates, bulk-inserts all rows and returns HTTP 201.

This prevents both:
  - A manual Excel upload after a scraper has already run for that date.
  - A scraper run after a manual upload for the same date.

The DB-level UNIQUE constraints are a second safety net for concurrent inserts.
"""

from datetime import datetime, timezone
from typing import List, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.sales import DailySales
from ..models.inventory import InventorySnapshot, ImportLog
from ..schemas.imports import (
    DailySalesImportIn,
    InventoryImportIn,
    ImportResult,
    DuplicateKey,
)

router = APIRouter()


# ─── helpers ──────────────────────────────────────────────────────────────────

def _find_sales_duplicates(db: Session, rows) -> List[DuplicateKey]:
    """Return rows whose (portal_id, product_id, sale_date) already exist."""
    keys = [(r.portal_id, r.product_id, r.sale_date) for r in rows]
    existing = db.execute(
        select(DailySales.portal_id, DailySales.product_id, DailySales.sale_date).where(
            tuple_(
                DailySales.portal_id,
                DailySales.product_id,
                DailySales.sale_date,
            ).in_(keys)
        )
    ).fetchall()
    return [
        DuplicateKey(portal_id=r[0], product_id=r[1], date=r[2])
        for r in existing
    ]


def _find_inventory_duplicates(db: Session, rows) -> List[DuplicateKey]:
    """Return rows whose (portal_id, product_id, snapshot_date) already exist."""
    keys = [(r.portal_id, r.product_id, r.snapshot_date) for r in rows]
    existing = db.execute(
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
    return [
        DuplicateKey(portal_id=r[0], product_id=r[1], date=r[2])
        for r in existing
    ]


def _log_import(
    db: Session,
    source_type: str,
    portal_id: int | None,
    import_date,
    records_imported: int,
    status: str,
    error_message: str | None = None,
) -> None:
    log = ImportLog(
        source_type=source_type,
        portal_id=portal_id,
        import_date=import_date,
        end_time=datetime.now(timezone.utc),
        status=status,
        records_imported=records_imported,
        error_message=error_message,
    )
    db.add(log)


# ─── routes ───────────────────────────────────────────────────────────────────

@router.post(
    "/sales",
    status_code=status.HTTP_201_CREATED,
    response_model=ImportResult,
    summary="Import daily sales rows",
    description=(
        "Bulk-insert daily sales rows. "
        "Returns 409 Conflict if any row's (portal_id, product_id, sale_date) "
        "already exists in the database."
    ),
)
def import_sales(body: DailySalesImportIn, db: Session = Depends(get_db)):
    if not body.rows:
        raise HTTPException(status_code=400, detail="rows list is empty")
    if len(body.rows) > 10_000:
        raise HTTPException(status_code=400, detail="Too many rows (max 10,000 per request)")

    duplicates = _find_sales_duplicates(db, body.rows)
    if duplicates:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"{len(duplicates)} row(s) already exist for the given "
                    "(portal_id, product_id, sale_date) combination(s). "
                    "No data was imported."
                ),
                "duplicates": [
                    {"portal_id": d.portal_id, "product_id": d.product_id, "date": str(d.date)}
                    for d in duplicates
                ],
            },
        )

    # Determine import_date for the log (earliest sale_date in the batch)
    import_date = min(r.sale_date for r in body.rows)
    portal_ids = {r.portal_id for r in body.rows}
    portal_id = next(iter(portal_ids)) if len(portal_ids) == 1 else None

    try:
        db_rows = [
            DailySales(
                portal_id=r.portal_id,
                product_id=r.product_id,
                sale_date=r.sale_date,
                units_sold=r.units_sold,
                asp=r.asp,
                revenue=r.revenue,
                data_source=r.data_source,
            )
            for r in body.rows
        ]
        db.bulk_save_objects(db_rows)
        _log_import(
            db,
            source_type="excel_upload",
            portal_id=portal_id,
            import_date=import_date,
            records_imported=len(db_rows),
            status="success",
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Duplicate key constraint violated during insert.",
                "detail": str(exc.orig),
            },
        ) from exc

    return ImportResult(inserted=len(body.rows))


@router.post(
    "/inventory",
    status_code=status.HTTP_201_CREATED,
    response_model=ImportResult,
    summary="Import inventory snapshots",
    description=(
        "Bulk-insert inventory snapshots. "
        "Returns 409 Conflict if any row's (portal_id, product_id, snapshot_date) "
        "already exists in the database."
    ),
)
def import_inventory(body: InventoryImportIn, db: Session = Depends(get_db)):
    if not body.rows:
        raise HTTPException(status_code=400, detail="rows list is empty")
    if len(body.rows) > 10_000:
        raise HTTPException(status_code=400, detail="Too many rows (max 10,000 per request)")

    duplicates = _find_inventory_duplicates(db, body.rows)
    if duplicates:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"{len(duplicates)} row(s) already exist for the given "
                    "(portal_id, product_id, snapshot_date) combination(s). "
                    "No data was imported."
                ),
                "duplicates": [
                    {"portal_id": d.portal_id, "product_id": d.product_id, "date": str(d.date)}
                    for d in duplicates
                ],
            },
        )

    import_date = min(r.snapshot_date for r in body.rows)
    portal_ids = {r.portal_id for r in body.rows}
    portal_id = next(iter(portal_ids)) if len(portal_ids) == 1 else None

    try:
        db_rows = [
            InventorySnapshot(
                portal_id=r.portal_id,
                product_id=r.product_id,
                snapshot_date=r.snapshot_date,
                portal_stock=r.portal_stock,
                backend_stock=r.backend_stock,
                frontend_stock=r.frontend_stock,
                solara_stock=r.solara_stock,
                amazon_fc_stock=r.amazon_fc_stock,
                open_po=r.open_po,
                doc=r.doc,
            )
            for r in body.rows
        ]
        db.bulk_save_objects(db_rows)
        _log_import(
            db,
            source_type="excel_upload",
            portal_id=portal_id,
            import_date=import_date,
            records_imported=len(db_rows),
            status="success",
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Duplicate key constraint violated during insert.",
                "detail": str(exc.orig),
            },
        ) from exc

    return ImportResult(inserted=len(body.rows))
