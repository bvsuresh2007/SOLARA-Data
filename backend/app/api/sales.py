from datetime import date
from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.sales import CityDailySales, Product
from ..models.metadata import Portal, City
from ..schemas.sales import SalesDataOut, SalesSummary, SalesByDimension, ProductOut

router = APIRouter()


def _base_query(db, start_date, end_date, portal_id, city_id, product_id):
    q = db.query(CityDailySales)
    if start_date:
        q = q.filter(CityDailySales.sale_date >= start_date)
    if end_date:
        q = q.filter(CityDailySales.sale_date <= end_date)
    if portal_id:
        q = q.filter(CityDailySales.portal_id == portal_id)
    if city_id:
        q = q.filter(CityDailySales.city_id == city_id)
    if product_id:
        q = q.filter(CityDailySales.product_id == product_id)
    return q


@router.get("/summary", response_model=SalesSummary)
def sales_summary(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    portal_id: Optional[int] = Query(None),
    city_id: Optional[int] = Query(None),
    product_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = _base_query(db, start_date, end_date, portal_id, city_id, product_id)
    row = q.with_entities(
        func.coalesce(func.sum(CityDailySales.revenue), 0).label("total_revenue"),
        func.coalesce(func.sum(CityDailySales.net_revenue), 0).label("total_net_revenue"),
        func.coalesce(func.sum(CityDailySales.units_sold), 0).label("total_quantity"),
        func.coalesce(func.sum(CityDailySales.order_count), 0).label("total_orders"),
        func.coalesce(func.sum(CityDailySales.discount_amount), 0).label("total_discount"),
        func.count(CityDailySales.id).label("record_count"),
    ).one()
    return SalesSummary(
        total_revenue=row.total_revenue,
        total_net_revenue=row.total_net_revenue,
        total_quantity=row.total_quantity,
        total_orders=int(row.total_orders),
        total_discount=row.total_discount,
        record_count=row.record_count,
    )


@router.get("/daily", response_model=List[SalesDataOut])
def daily_sales(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    portal_id: Optional[int] = Query(None),
    city_id: Optional[int] = Query(None),
    product_id: Optional[int] = Query(None),
    limit: int = Query(500, le=5000),
    db: Session = Depends(get_db),
):
    return (
        _base_query(db, start_date, end_date, portal_id, city_id, product_id)
        .order_by(CityDailySales.sale_date.desc())
        .limit(limit)
        .all()
    )


@router.get("/by-portal", response_model=List[SalesByDimension])
def sales_by_portal(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            Portal.id.label("dimension_id"),
            Portal.display_name.label("dimension_name"),
            func.coalesce(func.sum(CityDailySales.revenue), 0).label("total_revenue"),
            func.coalesce(func.sum(CityDailySales.net_revenue), 0).label("total_net_revenue"),
            func.coalesce(func.sum(CityDailySales.units_sold), 0).label("total_quantity"),
            func.coalesce(func.sum(CityDailySales.order_count), 0).label("total_orders"),
            func.count(CityDailySales.id).label("record_count"),
        )
        .join(CityDailySales, CityDailySales.portal_id == Portal.id, isouter=True)
        .filter(*([] if not start_date else [CityDailySales.sale_date >= start_date]))
        .filter(*([] if not end_date else [CityDailySales.sale_date <= end_date]))
        .group_by(Portal.id, Portal.display_name)
        .order_by(func.sum(CityDailySales.revenue).desc().nullslast())
        .all()
    )
    return [SalesByDimension(**r._asdict()) for r in rows]


@router.get("/by-city", response_model=List[SalesByDimension])
def sales_by_city(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    portal_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = (
        db.query(
            City.id.label("dimension_id"),
            City.name.label("dimension_name"),
            func.coalesce(func.sum(CityDailySales.revenue), 0).label("total_revenue"),
            func.coalesce(func.sum(CityDailySales.net_revenue), 0).label("total_net_revenue"),
            func.coalesce(func.sum(CityDailySales.units_sold), 0).label("total_quantity"),
            func.coalesce(func.sum(CityDailySales.order_count), 0).label("total_orders"),
            func.count(CityDailySales.id).label("record_count"),
        )
        .join(CityDailySales, CityDailySales.city_id == City.id)
    )
    if start_date:
        q = q.filter(CityDailySales.sale_date >= start_date)
    if end_date:
        q = q.filter(CityDailySales.sale_date <= end_date)
    if portal_id:
        q = q.filter(CityDailySales.portal_id == portal_id)
    rows = q.group_by(City.id, City.name).order_by(func.sum(CityDailySales.revenue).desc()).all()
    return [SalesByDimension(**r._asdict()) for r in rows]


@router.get("/by-product", response_model=List[SalesByDimension])
def sales_by_product(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    portal_id: Optional[int] = Query(None),
    city_id: Optional[int] = Query(None),
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    q = (
        db.query(
            Product.id.label("dimension_id"),
            Product.product_name.label("dimension_name"),
            func.coalesce(func.sum(CityDailySales.revenue), 0).label("total_revenue"),
            func.coalesce(func.sum(CityDailySales.net_revenue), 0).label("total_net_revenue"),
            func.coalesce(func.sum(CityDailySales.units_sold), 0).label("total_quantity"),
            func.coalesce(func.sum(CityDailySales.order_count), 0).label("total_orders"),
            func.count(CityDailySales.id).label("record_count"),
        )
        .join(CityDailySales, CityDailySales.product_id == Product.id)
    )
    if start_date:
        q = q.filter(CityDailySales.sale_date >= start_date)
    if end_date:
        q = q.filter(CityDailySales.sale_date <= end_date)
    if portal_id:
        q = q.filter(CityDailySales.portal_id == portal_id)
    if city_id:
        q = q.filter(CityDailySales.city_id == city_id)
    rows = (
        q.group_by(Product.id, Product.product_name)
        .order_by(func.sum(CityDailySales.revenue).desc())
        .limit(limit)
        .all()
    )
    return [SalesByDimension(**r._asdict()) for r in rows]


@router.get("/products", response_model=List[ProductOut])
def list_products(db: Session = Depends(get_db)):
    return db.query(Product).order_by(Product.product_name).all()
