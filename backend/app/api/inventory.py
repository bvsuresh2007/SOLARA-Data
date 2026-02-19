from datetime import date
from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.inventory import InventoryData
from ..models.sales import Product
from ..schemas.inventory import InventoryDataOut, InventorySummary

router = APIRouter()


@router.get("/current", response_model=List[InventoryDataOut])
def current_inventory(
    portal_id: Optional[int] = Query(None),
    city_id: Optional[int] = Query(None),
    product_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    # Subquery for latest snapshot per product/portal/warehouse
    latest = (
        db.query(
            InventoryData.product_id,
            InventoryData.portal_id,
            InventoryData.warehouse_id,
            func.max(InventoryData.snapshot_date).label("max_date"),
        )
        .group_by(
            InventoryData.product_id,
            InventoryData.portal_id,
            InventoryData.warehouse_id,
        )
        .subquery()
    )
    q = (
        db.query(InventoryData)
        .join(
            latest,
            (InventoryData.product_id == latest.c.product_id)
            & (InventoryData.portal_id == latest.c.portal_id)
            & (InventoryData.snapshot_date == latest.c.max_date),
        )
    )
    if portal_id:
        q = q.filter(InventoryData.portal_id == portal_id)
    if city_id:
        q = q.filter(InventoryData.city_id == city_id)
    if product_id:
        q = q.filter(InventoryData.product_id == product_id)
    return q.order_by(InventoryData.available_quantity.asc()).all()


@router.get("/trends", response_model=List[InventoryDataOut])
def inventory_trends(
    product_id: int = Query(...),
    portal_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(InventoryData).filter(InventoryData.product_id == product_id)
    if portal_id:
        q = q.filter(InventoryData.portal_id == portal_id)
    if start_date:
        q = q.filter(InventoryData.snapshot_date >= start_date)
    if end_date:
        q = q.filter(InventoryData.snapshot_date <= end_date)
    return q.order_by(InventoryData.snapshot_date.asc()).all()


@router.get("/low-stock", response_model=List[InventorySummary])
def low_stock(
    threshold: Decimal = Query(Decimal("100")),
    portal_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    latest = (
        db.query(
            InventoryData.product_id,
            func.max(InventoryData.snapshot_date).label("max_date"),
        )
        .group_by(InventoryData.product_id)
        .subquery()
    )
    q = (
        db.query(
            Product.id.label("product_id"),
            Product.product_name,
            Product.sku_code,
            func.sum(InventoryData.stock_quantity).label("total_stock"),
            func.sum(InventoryData.available_quantity).label("total_available"),
            func.sum(InventoryData.reserved_quantity).label("total_reserved"),
            func.count(InventoryData.portal_id.distinct()).label("portal_count"),
        )
        .join(InventoryData, InventoryData.product_id == Product.id)
        .join(
            latest,
            (InventoryData.product_id == latest.c.product_id)
            & (InventoryData.snapshot_date == latest.c.max_date),
        )
    )
    if portal_id:
        q = q.filter(InventoryData.portal_id == portal_id)
    rows = (
        q.group_by(Product.id, Product.product_name, Product.sku_code)
        .having(func.sum(InventoryData.available_quantity) < threshold)
        .order_by(func.sum(InventoryData.available_quantity).asc())
        .all()
    )
    return [
        InventorySummary(
            product_id=r.product_id,
            product_name=r.product_name,
            sku_code=r.sku_code,
            total_stock=r.total_stock,
            total_available=r.total_available,
            total_reserved=r.total_reserved,
            portal_count=r.portal_count,
        )
        for r in rows
    ]
