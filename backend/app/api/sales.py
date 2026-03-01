import datetime as _dt
from collections import defaultdict
from datetime import date
from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, extract, text
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.sales import DailySales, Product, ProductPortalMapping
from ..models.metadata import Portal, ProductCategory
from ..models.inventory import MonthlyTargets, InventorySnapshot
from ..schemas.sales import (
    SalesDataOut, SalesSummary, SalesByDimension, ProductOut,
    SalesTrend, SalesByCategory, TargetAchievement,
    PortalDailyRow, PortalDailyResponse,
)

router = APIRouter()


# Portal aliases: scraper-only portals whose data should be included under
# their canonical active portal.  If data accidentally lands under an aliased
# portal_id, these mappings ensure it still appears in dashboard queries.
_PORTAL_ALIASES: dict[str, str] = {
    "amazon_pi": "amazon",
}


def _included_portal_ids(db) -> list[int]:
    """Return portal IDs whose data the dashboard should show.

    Includes all active portals plus any aliased inactive portals whose
    canonical target is active (e.g. amazon_pi → amazon).
    """
    portals = db.query(Portal.id, Portal.name, Portal.is_active).all()
    portal_by_name = {p.name: p for p in portals}
    ids = {p.id for p in portals if p.is_active}
    for alias, canonical in _PORTAL_ALIASES.items():
        target = portal_by_name.get(canonical)
        source = portal_by_name.get(alias)
        if target and target.is_active and source:
            ids.add(source.id)
    return list(ids)


def _base_query(db, start_date, end_date, portal_id, product_id=None):
    # Exclude data rows belonging to inactive portals (e.g. EasyEcom — an aggregator
    # whose data duplicates the individual portal rows already in the DB).
    # Also include aliased portals (e.g. amazon_pi) whose data belongs to an
    # active canonical portal.
    included = _included_portal_ids(db)
    q = db.query(DailySales).filter(DailySales.portal_id.in_(included))
    if start_date:
        q = q.filter(DailySales.sale_date >= start_date)
    if end_date:
        q = q.filter(DailySales.sale_date <= end_date)
    if portal_id:
        q = q.filter(DailySales.portal_id == portal_id)
    if product_id:
        q = q.filter(DailySales.product_id == product_id)
    return q


@router.get("/summary", response_model=SalesSummary)
def sales_summary(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    portal_id: Optional[int] = Query(None),
    product_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = _base_query(db, start_date, end_date, portal_id, product_id)
    row = q.with_entities(
        func.coalesce(func.sum(DailySales.revenue), Decimal("0")).label("total_revenue"),
        func.coalesce(func.sum(DailySales.units_sold), Decimal("0")).label("total_quantity"),
        func.count(DailySales.id).label("record_count"),
        func.count(func.distinct(DailySales.product_id)).label("active_skus"),
    ).one()
    rev = float(row.total_revenue)
    return SalesSummary(
        total_revenue=rev,
        total_quantity=float(row.total_quantity),
        record_count=row.record_count,
        active_skus=row.active_skus,
    )


@router.get("/daily", response_model=List[SalesDataOut])
def daily_sales(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    portal_id: Optional[int] = Query(None),
    product_id: Optional[int] = Query(None),
    limit: int = Query(500, le=5000),
    db: Session = Depends(get_db),
):
    return (
        _base_query(db, start_date, end_date, portal_id, product_id)
        .order_by(DailySales.sale_date.desc())
        .limit(limit)
        .all()
    )


@router.get("/by-portal", response_model=List[SalesByDimension])
def sales_by_portal(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    q = (
        db.query(
            Portal.id.label("dimension_id"),
            Portal.display_name.label("dimension_name"),
            func.coalesce(func.sum(DailySales.revenue), Decimal("0")).label("total_revenue"),
            func.coalesce(func.sum(DailySales.units_sold), Decimal("0")).label("total_quantity"),
        )
        .filter(Portal.is_active == True)
        .join(DailySales, DailySales.portal_id == Portal.id, isouter=True)
    )
    if start_date:
        q = q.filter(DailySales.sale_date >= start_date)
    if end_date:
        q = q.filter(DailySales.sale_date <= end_date)
    rows = (
        q.group_by(Portal.id, Portal.display_name)
        .order_by(text("total_revenue DESC NULLS LAST"))
        .all()
    )
    # Merge aliased portal revenue into canonical portal (e.g. amazon_pi → Amazon)
    alias_target_ids: dict[int, int] = {}
    portals_by_name = {p.name: p for p in db.query(Portal).all()}
    for alias, canonical in _PORTAL_ALIASES.items():
        src = portals_by_name.get(alias)
        tgt = portals_by_name.get(canonical)
        if src and tgt:
            alias_target_ids[src.id] = tgt.id

    if alias_target_ids:
        # Fetch aliased portal revenue separately and merge into canonical row
        alias_ids = list(alias_target_ids.keys())
        alias_q = (
            db.query(
                DailySales.portal_id,
                func.coalesce(func.sum(DailySales.revenue), Decimal("0")).label("total_revenue"),
                func.coalesce(func.sum(DailySales.units_sold), Decimal("0")).label("total_quantity"),
            )
            .filter(DailySales.portal_id.in_(alias_ids))
        )
        if start_date:
            alias_q = alias_q.filter(DailySales.sale_date >= start_date)
        if end_date:
            alias_q = alias_q.filter(DailySales.sale_date <= end_date)
        alias_rows = alias_q.group_by(DailySales.portal_id).all()

        extra: dict[int, dict] = {}
        for ar in alias_rows:
            target_id = alias_target_ids.get(ar.portal_id)
            if target_id:
                if target_id not in extra:
                    extra[target_id] = {"revenue": 0.0, "quantity": 0.0}
                extra[target_id]["revenue"] += float(ar.total_revenue)
                extra[target_id]["quantity"] += float(ar.total_quantity)

        return [
            SalesByDimension(
                dimension_id=r.dimension_id,
                dimension_name=r.dimension_name,
                total_revenue=float(r.total_revenue) + extra.get(r.dimension_id, {}).get("revenue", 0.0),
                total_quantity=float(r.total_quantity) + extra.get(r.dimension_id, {}).get("quantity", 0.0),
            )
            for r in rows
        ]

    return [
        SalesByDimension(
            dimension_id=r.dimension_id,
            dimension_name=r.dimension_name,
            total_revenue=float(r.total_revenue),
            total_quantity=float(r.total_quantity),
        )
        for r in rows
    ]


@router.get("/by-city", response_model=List[SalesByDimension])
def sales_by_city(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    portal_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    # DailySales has no city-level breakdown — return empty list
    return []


@router.get("/by-product", response_model=List[SalesByDimension])
def sales_by_product(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    portal_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    sort_by: str = Query("revenue", description="Sort by 'revenue' or 'units'"),
    db: Session = Depends(get_db),
):
    included = _included_portal_ids(db)
    q = (
        db.query(
            Product.id.label("dimension_id"),
            Product.sku_code.label("sku_code"),
            Product.product_name.label("dimension_name"),
            func.coalesce(func.sum(DailySales.revenue), Decimal("0")).label("total_revenue"),
            func.coalesce(func.sum(DailySales.units_sold), Decimal("0")).label("total_quantity"),
        )
        .join(DailySales, DailySales.product_id == Product.id)
        .filter(DailySales.portal_id.in_(included))
    )
    if start_date:
        q = q.filter(DailySales.sale_date >= start_date)
    if end_date:
        q = q.filter(DailySales.sale_date <= end_date)
    if portal_id:
        q = q.filter(DailySales.portal_id == portal_id)
    order_col = "total_quantity" if sort_by == "units" else "total_revenue"
    rows = (
        q.group_by(Product.id, Product.sku_code, Product.product_name)
        .order_by(text(f"{order_col} DESC NULLS LAST"))
        .limit(limit)
        .all()
    )
    return [
        SalesByDimension(
            dimension_id=r.dimension_id,
            sku_code=r.sku_code,
            dimension_name=r.dimension_name,
            total_revenue=float(r.total_revenue),
            total_quantity=float(r.total_quantity),
        )
        for r in rows
    ]


@router.get("/trend", response_model=List[SalesTrend])
def sales_trend(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD). Defaults to 90 days ago when neither date is provided."),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD). Defaults to today when neither date is provided."),
    portal_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    # Default to last 90 days when no date range given
    if not start_date and not end_date:
        end_date = _dt.date.today()
        start_date = end_date - _dt.timedelta(days=90)

    included = _included_portal_ids(db)
    q = db.query(
        DailySales.sale_date.label("dt"),
        func.coalesce(func.sum(DailySales.revenue), Decimal("0")).label("total_revenue"),
        func.coalesce(func.sum(DailySales.units_sold), Decimal("0")).label("total_quantity"),
        func.coalesce(func.avg(DailySales.asp), Decimal("0")).label("avg_asp"),
    ).filter(DailySales.portal_id.in_(included))
    if start_date:
        q = q.filter(DailySales.sale_date >= start_date)
    if end_date:
        q = q.filter(DailySales.sale_date <= end_date)
    if portal_id:
        q = q.filter(DailySales.portal_id == portal_id)

    rows = q.group_by(DailySales.sale_date).order_by(DailySales.sale_date.asc()).all()
    return [
        SalesTrend(
            date=str(r.dt),
            total_revenue=float(r.total_revenue),
            total_quantity=float(r.total_quantity),
            avg_asp=float(r.avg_asp),
        )
        for r in rows
    ]


@router.get("/by-category", response_model=List[SalesByCategory])
def sales_by_category(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    portal_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    included = _included_portal_ids(db)
    q = (
        db.query(
            ProductCategory.l2_name.label("category"),
            func.coalesce(func.sum(DailySales.revenue), Decimal("0")).label("total_revenue"),
            func.coalesce(func.sum(DailySales.units_sold), Decimal("0")).label("total_quantity"),
            func.count(func.distinct(DailySales.product_id)).label("product_count"),
        )
        .join(Product, DailySales.product_id == Product.id)
        .join(ProductCategory, Product.category_id == ProductCategory.id)
        .filter(DailySales.portal_id.in_(included))
        .filter(ProductCategory.l2_name.isnot(None))
        .filter(func.lower(ProductCategory.l2_name) != "select a category")
    )
    if start_date:
        q = q.filter(DailySales.sale_date >= start_date)
    if end_date:
        q = q.filter(DailySales.sale_date <= end_date)
    if portal_id:
        q = q.filter(DailySales.portal_id == portal_id)

    rows = (
        q.group_by(ProductCategory.l2_name)
        .having(func.sum(DailySales.revenue) > 0)
        .order_by(text("total_revenue DESC NULLS LAST"))
        .all()
    )
    return [
        SalesByCategory(
            category=r.category,
            total_revenue=float(r.total_revenue),
            total_quantity=float(r.total_quantity),
            product_count=r.product_count,
        )
        for r in rows
    ]


@router.get("/targets", response_model=List[TargetAchievement])
def sales_targets(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    today = _dt.date.today()
    if year is None:
        year = today.year
    if month is None:
        month = today.month

    # Actual sales sub-query for the given year/month
    actual_sq = (
        db.query(
            DailySales.portal_id.label("portal_id"),
            func.coalesce(func.sum(DailySales.revenue), Decimal("0")).label("actual_revenue"),
            func.coalesce(func.sum(DailySales.units_sold), Decimal("0")).label("actual_units"),
        )
        .filter(extract("year", DailySales.sale_date) == year)
        .filter(extract("month", DailySales.sale_date) == month)
        .group_by(DailySales.portal_id)
        .subquery()
    )

    rows = (
        db.query(
            Portal.display_name.label("portal_name"),
            func.coalesce(func.sum(MonthlyTargets.target_revenue), Decimal("0")).label("target_revenue"),
            func.coalesce(func.sum(MonthlyTargets.target_units), Decimal("0")).label("target_units"),
            func.coalesce(actual_sq.c.actual_revenue, Decimal("0")).label("actual_revenue"),
            func.coalesce(actual_sq.c.actual_units, Decimal("0")).label("actual_units"),
        )
        .join(MonthlyTargets, MonthlyTargets.portal_id == Portal.id)
        .outerjoin(actual_sq, actual_sq.c.portal_id == Portal.id)
        .filter(MonthlyTargets.year == year, MonthlyTargets.month == month)
        .group_by(
            Portal.id, Portal.display_name,
            actual_sq.c.actual_revenue, actual_sq.c.actual_units,
        )
        .order_by(func.sum(MonthlyTargets.target_revenue).desc())
        .all()
    )

    return [
        TargetAchievement(
            portal_name=r.portal_name,
            target_revenue=float(r.target_revenue),
            actual_revenue=float(r.actual_revenue),
            achievement_pct=(
                float(r.actual_revenue) / float(r.target_revenue) * 100
                if float(r.target_revenue) > 0 else 0.0
            ),
            target_units=float(r.target_units),
            actual_units=float(r.actual_units),
        )
        for r in rows
    ]


@router.get("/products", response_model=List[ProductOut])
def list_products(db: Session = Depends(get_db)):
    return db.query(Product).order_by(Product.product_name).all()


@router.get("/portal-daily", response_model=PortalDailyResponse)
def portal_daily_sales(
    portal: str = Query("all", description="Portal name slug (e.g. swiggy, blinkit) or 'all' for cross-portal aggregation"),
    start_date: Optional[date] = Query(None, description="Start of date range (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End of date range (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    today = _dt.date.today()
    if not end_date:
        end_date = today
    if not start_date:
        start_date = today.replace(day=1)

    is_all_portals = portal.lower() == "all"

    if is_all_portals:
        # Cross-portal aggregation: include all active portals + aliases
        portal_ids_for_query = _included_portal_ids(db)
        portal_display_name = "All Portals"
        portal_obj_id = None  # used for portal_sku / inventory lookups
    else:
        # 1. Resolve portal by name slug (+ any aliases that map here)
        portal_obj = db.query(Portal).filter(func.lower(Portal.name) == portal.lower()).first()
        if not portal_obj:
            return PortalDailyResponse(portal_name=portal, dates=[], rows=[])

        portal_display_name = portal_obj.display_name
        portal_obj_id = portal_obj.id

        # Collect portal IDs that should be included (canonical + aliases)
        portal_ids_for_query = [portal_obj.id]
        all_portals_map = {p.name: p for p in db.query(Portal).all()}
        for alias, canonical in _PORTAL_ALIASES.items():
            if canonical == portal_obj.name:
                alias_portal = all_portals_map.get(alias)
                if alias_portal:
                    portal_ids_for_query.append(alias_portal.id)

    # 2. Build ordered dates list for the range
    dates: List[str] = []
    d = start_date
    while d <= end_date:
        dates.append(str(d))
        d += _dt.timedelta(days=1)

    # 3. Discover products that actually have sales in this portal + date range.
    #    Previously this required product_portal_mapping entries (which are often
    #    incomplete), causing many products to be invisible in the daily table
    #    even though they had sales data.  Now we query daily_sales directly and
    #    LEFT JOIN the mapping for the optional portal_sku column.
    sales_product_ids = (
        db.query(func.distinct(DailySales.product_id))
        .filter(
            DailySales.portal_id.in_(portal_ids_for_query),
            DailySales.sale_date >= start_date,
            DailySales.sale_date <= end_date,
        )
        .all()
    )
    product_ids = [r[0] for r in sales_product_ids]
    if not product_ids:
        return PortalDailyResponse(portal_name=portal_display_name, dates=dates, rows=[])

    if portal_obj_id is not None:
        # Specific portal: LEFT JOIN mapping for portal_sku
        pq = (
            db.query(
                Product.id,
                Product.sku_code,
                Product.product_name,
                ProductCategory.l2_name.label("category"),
                ProductPortalMapping.portal_sku,
            )
            .outerjoin(ProductCategory, Product.category_id == ProductCategory.id)
            .outerjoin(
                ProductPortalMapping,
                (ProductPortalMapping.product_id == Product.id)
                & (ProductPortalMapping.portal_id == portal_obj_id),
            )
        )
    else:
        # "All portals" — no single portal_sku to show; use NULL literal
        from sqlalchemy import literal
        pq = (
            db.query(
                Product.id,
                Product.sku_code,
                Product.product_name,
                ProductCategory.l2_name.label("category"),
                literal(None).label("portal_sku"),
            )
            .outerjoin(ProductCategory, Product.category_id == ProductCategory.id)
        )
    product_rows = pq.filter(Product.id.in_(product_ids)).all()
    product_map = {r.id: r for r in product_rows}

    # 4. Daily sales in the date range (include aliased portal IDs)
    sales_rows = (
        db.query(
            DailySales.product_id,
            DailySales.sale_date,
            DailySales.units_sold,
            DailySales.asp,
            DailySales.revenue,
        )
        .filter(
            DailySales.portal_id.in_(portal_ids_for_query),
            DailySales.product_id.in_(product_ids),
            DailySales.sale_date >= start_date,
            DailySales.sale_date <= end_date,
        )
        .all()
    )

    # 5. Latest inventory snapshot per product
    inv_map: dict[int, float | None] = {}
    if portal_obj_id is not None:
        # Specific portal — show portal stock
        latest_sq = (
            db.query(
                InventorySnapshot.product_id,
                func.max(InventorySnapshot.snapshot_date).label("max_date"),
            )
            .filter(
                InventorySnapshot.portal_id == portal_obj_id,
                InventorySnapshot.product_id.in_(product_ids),
            )
            .group_by(InventorySnapshot.product_id)
            .subquery()
        )
        inv_rows = (
            db.query(InventorySnapshot.product_id, InventorySnapshot.portal_stock)
            .join(
                latest_sq,
                (InventorySnapshot.product_id == latest_sq.c.product_id)
                & (InventorySnapshot.snapshot_date == latest_sq.c.max_date),
            )
            .filter(InventorySnapshot.portal_id == portal_obj_id)
            .all()
        )
        inv_map = {
            r.product_id: float(r.portal_stock) if r.portal_stock is not None else None
            for r in inv_rows
        }
    # "All portals" — skip inventory (no single portal stock to show)

    # 6. Pivot: aggregate sales per product (SUM across portals for same product+date)
    sales_agg = defaultdict(lambda: {"daily": {}, "asps": [], "total_units": 0, "total_value": 0.0})
    for row in sales_rows:
        pid = row.product_id
        date_str = str(row.sale_date)
        units = int(row.units_sold) if row.units_sold is not None else 0
        # Sum units across portals (critical for "All Portals" mode where
        # the same product may appear on multiple portals on the same day)
        sales_agg[pid]["daily"][date_str] = sales_agg[pid]["daily"].get(date_str, 0) + units
        if row.asp is not None:
            sales_agg[pid]["asps"].append(float(row.asp))
        if row.units_sold and row.units_sold > 0:
            sales_agg[pid]["total_units"] += int(row.units_sold)
            sales_agg[pid]["total_value"] += float(row.revenue or 0)

    # 7. Assemble — only products that had at least one sale record
    result_rows: List[PortalDailyRow] = []
    for pid, agg in sales_agg.items():
        if pid not in product_map:
            continue
        p = product_map[pid]
        asps = agg["asps"]
        bau_asp = round(sum(asps) / len(asps), 2) if asps else None
        result_rows.append(
            PortalDailyRow(
                sku_code=p.sku_code,
                product_name=p.product_name,
                category=p.category or "—",
                portal_sku=p.portal_sku or "—",
                bau_asp=bau_asp,
                wh_stock=inv_map.get(pid),
                daily_units={d: agg["daily"].get(d) for d in dates},
                mtd_units=agg["total_units"],
                mtd_value=round(agg["total_value"], 0),
            )
        )

    result_rows.sort(key=lambda r: r.mtd_units, reverse=True)

    return PortalDailyResponse(
        portal_name=portal_display_name,
        dates=dates,
        rows=result_rows,
    )
