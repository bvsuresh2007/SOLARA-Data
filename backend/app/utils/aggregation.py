"""
Aggregation helpers used by the API and notification jobs.
"""
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.sales import SalesData
from ..models.metadata import City, Portal
from ..models.sales import Product


def revenue_for_period(db: Session, start: date, end: date, portal_id: int = None) -> Decimal:
    q = db.query(func.coalesce(func.sum(SalesData.revenue), 0)).filter(
        SalesData.sale_date.between(start, end)
    )
    if portal_id:
        q = q.filter(SalesData.portal_id == portal_id)
    return q.scalar() or Decimal(0)


def top_products(db: Session, start: date, end: date, limit: int = 5) -> list[dict]:
    rows = (
        db.query(
            Product.product_name,
            func.sum(SalesData.revenue).label("revenue"),
        )
        .join(SalesData, SalesData.product_id == Product.id)
        .filter(SalesData.sale_date.between(start, end))
        .group_by(Product.id, Product.product_name)
        .order_by(func.sum(SalesData.revenue).desc())
        .limit(limit)
        .all()
    )
    return [{"name": r.product_name, "revenue": float(r.revenue)} for r in rows]


def top_cities(db: Session, start: date, end: date, limit: int = 5) -> list[dict]:
    rows = (
        db.query(
            City.name,
            func.sum(SalesData.revenue).label("revenue"),
        )
        .join(SalesData, SalesData.city_id == City.id)
        .filter(SalesData.sale_date.between(start, end))
        .group_by(City.id, City.name)
        .order_by(func.sum(SalesData.revenue).desc())
        .limit(limit)
        .all()
    )
    return [{"name": r.name, "revenue": float(r.revenue)} for r in rows]


def week_over_week_pct(db: Session, current_start: date, current_end: date) -> float | None:
    days = (current_end - current_start).days + 1
    prev_end = current_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)

    current = float(revenue_for_period(db, current_start, current_end))
    previous = float(revenue_for_period(db, prev_start, prev_end))

    if previous == 0:
        return None
    return ((current - previous) / previous) * 100
