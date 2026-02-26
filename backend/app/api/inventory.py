from datetime import date
from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, case
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models.inventory import InventorySnapshot
from ..models.sales import Product
from ..schemas.inventory import InventorySnapshotOut, InventorySummary

router = APIRouter()


def _total_stock(model):
    """Sum all stock columns, treating NULL as 0."""
    return (
        func.coalesce(model.portal_stock, 0)
        + func.coalesce(model.backend_stock, 0)
        + func.coalesce(model.frontend_stock, 0)
        + func.coalesce(model.solara_stock, 0)
        + func.coalesce(model.amazon_fc_stock, 0)
    )


@router.get("/current", response_model=List[InventorySnapshotOut])
def current_inventory(
    portal_id: Optional[int] = Query(None),
    product_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    # Subquery: latest snapshot per (portal, product)
    latest = (
        db.query(
            InventorySnapshot.product_id,
            InventorySnapshot.portal_id,
            func.max(InventorySnapshot.snapshot_date).label("max_date"),
        )
        .group_by(InventorySnapshot.product_id, InventorySnapshot.portal_id)
        .subquery()
    )
    q = (
        db.query(InventorySnapshot)
        .join(
            latest,
            (InventorySnapshot.product_id == latest.c.product_id)
            & (InventorySnapshot.portal_id == latest.c.portal_id)
            & (InventorySnapshot.snapshot_date == latest.c.max_date),
        )
    )
    if portal_id is not None:
        q = q.filter(InventorySnapshot.portal_id == portal_id)
    if product_id is not None:
        q = q.filter(InventorySnapshot.product_id == product_id)
    rows = (
        q.options(
            joinedload(InventorySnapshot.portal),
            joinedload(InventorySnapshot.product),
        )
        .order_by(_total_stock(InventorySnapshot).asc())
        .all()
    )
    return [
        {
            "id": r.id,
            "portal_id": r.portal_id,
            "portal_name": r.portal.display_name if r.portal else None,
            "product_id": r.product_id,
            "product_name": r.product.product_name if r.product else None,
            "snapshot_date": r.snapshot_date,
            "portal_stock": r.portal_stock,
            "backend_stock": r.backend_stock,
            "frontend_stock": r.frontend_stock,
            "solara_stock": r.solara_stock,
            "amazon_fc_stock": r.amazon_fc_stock,
            "open_po": r.open_po,
            "doc": r.doc,
            "imported_at": r.imported_at,
        }
        for r in rows
    ]


@router.get("/trends", response_model=List[InventorySnapshotOut])
def inventory_trends(
    product_id: int = Query(...),
    portal_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(InventorySnapshot).filter(InventorySnapshot.product_id == product_id)
    if portal_id is not None:
        q = q.filter(InventorySnapshot.portal_id == portal_id)
    if start_date:
        q = q.filter(InventorySnapshot.snapshot_date >= start_date)
    if end_date:
        q = q.filter(InventorySnapshot.snapshot_date <= end_date)
    return q.order_by(InventorySnapshot.snapshot_date.asc()).all()


@router.get("/low-stock", response_model=List[InventorySummary])
def low_stock(
    threshold: Decimal = Query(Decimal("100")),
    portal_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    latest = (
        db.query(
            InventorySnapshot.product_id,
            func.max(InventorySnapshot.snapshot_date).label("max_date"),
        )
        .group_by(InventorySnapshot.product_id)
        .subquery()
    )
    q = (
        db.query(
            Product.id.label("product_id"),
            Product.product_name,
            Product.sku_code,
            func.sum(
                func.coalesce(InventorySnapshot.portal_stock, 0)
            ).label("total_portal_stock"),
            func.count(InventorySnapshot.portal_id.distinct()).label("portal_count"),
        )
        .join(InventorySnapshot, InventorySnapshot.product_id == Product.id)
        .join(
            latest,
            (InventorySnapshot.product_id == latest.c.product_id)
            & (InventorySnapshot.snapshot_date == latest.c.max_date),
        )
    )
    if portal_id is not None:
        q = q.filter(InventorySnapshot.portal_id == portal_id)
    rows = (
        q.group_by(Product.id, Product.product_name, Product.sku_code)
        .having(func.sum(func.coalesce(InventorySnapshot.portal_stock, 0)) < threshold)
        .order_by(func.sum(func.coalesce(InventorySnapshot.portal_stock, 0)).asc())
        .all()
    )
    return [
        InventorySummary(
            product_id=r.product_id,
            product_name=r.product_name,
            sku_code=r.sku_code,
            total_portal_stock=r.total_portal_stock,
            portal_count=r.portal_count,
        )
        for r in rows
    ]
