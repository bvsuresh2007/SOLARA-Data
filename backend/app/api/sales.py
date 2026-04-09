import datetime as _dt
from collections import defaultdict
from datetime import date
from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, extract, text, case, and_
from sqlalchemy.orm import Session, aliased

from ..database import get_db
from ..models.sales import DailySales, Product, ProductPortalMapping
from ..models.metadata import Portal, ProductCategory
from ..models.inventory import MonthlyTargets, InventorySnapshot


def _bau_revenue_expr(ppm_alias=None):
    """SQL expression: use portal-specific BAU ASP from product_portal_mapping
    when available; fall back to products.default_asp; then to daily_sales.revenue.

    Args:
        ppm_alias: An aliased ProductPortalMapping joined on
                   (product_id, portal_id) matching daily_sales.  When None,
                   uses only products.default_asp as the BAU source.
    """
    if ppm_alias is not None:
        return case(
            (
                ppm_alias.bau_asp.isnot(None),
                ppm_alias.bau_asp * DailySales.units_sold,
            ),
            (
                and_(Product.default_asp.isnot(None), Product.default_asp > 0),
                Product.default_asp * DailySales.units_sold,
            ),
            else_=DailySales.revenue,
        )
    return case(
        (
            and_(Product.default_asp.isnot(None), Product.default_asp > 0),
            Product.default_asp * DailySales.units_sold,
        ),
        else_=DailySales.revenue,
    )
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


def _mapped_product_ids(db, portal_id: int) -> list[int]:
    """Return product IDs that have a valid product_portal_mapping entry for
    the given portal_id.  Only products explicitly listed in the SKU mapping
    file (with a non-empty portal_sku) are considered 'mapped'.
    When portal_id is None (All Portals), returns an empty list meaning no filter."""
    rows = (
        db.query(ProductPortalMapping.product_id)
        .filter(ProductPortalMapping.portal_id == portal_id)
        .filter(ProductPortalMapping.is_active == True)
        .all()
    )
    return [r[0] for r in rows]


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
    included = _included_portal_ids(db)
    ppm = aliased(ProductPortalMapping, flat=True)
    bau_rev = _bau_revenue_expr(ppm)
    q = (
        db.query(
            func.coalesce(func.sum(bau_rev), Decimal("0")).label("total_revenue"),
            func.coalesce(func.sum(DailySales.units_sold), Decimal("0")).label("total_quantity"),
            func.count(DailySales.id).label("record_count"),
            func.count(func.distinct(DailySales.product_id)).label("active_skus"),
            func.max(DailySales.imported_at).label("data_as_of"),
        )
        .join(Product, DailySales.product_id == Product.id)
        .outerjoin(ppm, and_(
            ppm.product_id == DailySales.product_id,
            ppm.portal_id == DailySales.portal_id,
        ))
        .filter(DailySales.portal_id.in_(included))
    )
    if start_date:
        q = q.filter(DailySales.sale_date >= start_date)
    if end_date:
        q = q.filter(DailySales.sale_date <= end_date)
    if portal_id:
        q = q.filter(DailySales.portal_id == portal_id)
        mapped = _mapped_product_ids(db, portal_id)
        if mapped:
            q = q.filter(DailySales.product_id.in_(mapped))
    if product_id:
        q = q.filter(DailySales.product_id == product_id)
    row = q.one()
    data_as_of = row.data_as_of.isoformat() if row.data_as_of else None
    return SalesSummary(
        total_revenue=float(row.total_revenue),
        total_quantity=float(row.total_quantity),
        record_count=row.record_count,
        active_skus=row.active_skus,
        data_as_of=data_as_of,
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
    ppm = aliased(ProductPortalMapping, flat=True)
    bau_rev = _bau_revenue_expr(ppm)
    q = (
        db.query(
            Portal.id.label("dimension_id"),
            Portal.display_name.label("dimension_name"),
            func.coalesce(func.sum(bau_rev), Decimal("0")).label("total_revenue"),
            func.coalesce(func.sum(DailySales.units_sold), Decimal("0")).label("total_quantity"),
        )
        .filter(Portal.is_active == True)
        .join(DailySales, DailySales.portal_id == Portal.id, isouter=True)
        .outerjoin(Product, DailySales.product_id == Product.id)
        .outerjoin(ppm, and_(
            ppm.product_id == DailySales.product_id,
            ppm.portal_id == DailySales.portal_id,
        ))
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
        alias_ids = list(alias_target_ids.keys())
        ppm2 = aliased(ProductPortalMapping, flat=True)
        bau_rev2 = _bau_revenue_expr(ppm2)
        alias_q = (
            db.query(
                DailySales.portal_id,
                func.coalesce(func.sum(bau_rev2), Decimal("0")).label("total_revenue"),
                func.coalesce(func.sum(DailySales.units_sold), Decimal("0")).label("total_quantity"),
            )
            .join(Product, DailySales.product_id == Product.id)
            .outerjoin(ppm2, and_(
                ppm2.product_id == DailySales.product_id,
                ppm2.portal_id == DailySales.portal_id,
            ))
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
    from ..models.sales import CityDailySales
    from ..models.metadata import City

    q = (
        db.query(
            City.id.label("dimension_id"),
            City.name.label("dimension_name"),
            func.coalesce(func.sum(CityDailySales.revenue), 0).label("total_revenue"),
            func.coalesce(func.sum(CityDailySales.units_sold), 0).label("total_quantity"),
        )
        .join(City, City.id == CityDailySales.city_id)
    )
    if start_date:
        q = q.filter(CityDailySales.sale_date >= start_date)
    if end_date:
        q = q.filter(CityDailySales.sale_date <= end_date)
    if portal_id:
        q = q.filter(CityDailySales.portal_id == portal_id)

    rows = q.group_by(City.id, City.name).order_by(func.sum(CityDailySales.revenue).desc()).all()

    return [
        SalesByDimension(
            dimension_id=r.dimension_id,
            dimension_name=r.dimension_name,
            total_revenue=float(r.total_revenue),
            total_quantity=float(r.total_quantity),
        )
        for r in rows
    ]


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
    ppm = aliased(ProductPortalMapping, flat=True)
    bau_rev = _bau_revenue_expr(ppm)
    q = (
        db.query(
            Product.id.label("dimension_id"),
            Product.sku_code.label("sku_code"),
            Product.product_name.label("dimension_name"),
            func.coalesce(func.sum(bau_rev), Decimal("0")).label("total_revenue"),
            func.coalesce(func.sum(DailySales.units_sold), Decimal("0")).label("total_quantity"),
        )
        .join(DailySales, DailySales.product_id == Product.id)
        .outerjoin(ppm, and_(
            ppm.product_id == DailySales.product_id,
            ppm.portal_id == DailySales.portal_id,
        ))
        .filter(DailySales.portal_id.in_(included))
    )
    if start_date:
        q = q.filter(DailySales.sale_date >= start_date)
    if end_date:
        q = q.filter(DailySales.sale_date <= end_date)
    if portal_id:
        q = q.filter(DailySales.portal_id == portal_id)
        mapped = _mapped_product_ids(db, portal_id)
        if mapped:
            q = q.filter(DailySales.product_id.in_(mapped))
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
    ppm = aliased(ProductPortalMapping, flat=True)
    bau_rev = _bau_revenue_expr(ppm)
    q = (
        db.query(
            DailySales.sale_date.label("dt"),
            func.coalesce(func.sum(bau_rev), Decimal("0")).label("total_revenue"),
            func.coalesce(func.sum(DailySales.units_sold), Decimal("0")).label("total_quantity"),
        )
        .join(Product, DailySales.product_id == Product.id)
        .outerjoin(ppm, and_(
            ppm.product_id == DailySales.product_id,
            ppm.portal_id == DailySales.portal_id,
        ))
        .filter(DailySales.portal_id.in_(included))
    )
    if start_date:
        q = q.filter(DailySales.sale_date >= start_date)
    if end_date:
        q = q.filter(DailySales.sale_date <= end_date)
    if portal_id:
        q = q.filter(DailySales.portal_id == portal_id)
        mapped = _mapped_product_ids(db, portal_id)
        if mapped:
            q = q.filter(DailySales.product_id.in_(mapped))

    rows = q.group_by(DailySales.sale_date).order_by(DailySales.sale_date.asc()).all()
    return [
        SalesTrend(
            date=str(r.dt),
            total_revenue=float(r.total_revenue),
            total_quantity=float(r.total_quantity),
            avg_asp=float(r.total_revenue) / float(r.total_quantity) if float(r.total_quantity) > 0 else 0.0,
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
    ppm = aliased(ProductPortalMapping, flat=True)
    bau_rev = _bau_revenue_expr(ppm)
    q = (
        db.query(
            ProductCategory.l1_name.label("category"),
            func.coalesce(func.sum(bau_rev), Decimal("0")).label("total_revenue"),
            func.coalesce(func.sum(DailySales.units_sold), Decimal("0")).label("total_quantity"),
            func.count(func.distinct(DailySales.product_id)).label("product_count"),
        )
        .join(Product, DailySales.product_id == Product.id)
        .join(ProductCategory, Product.category_id == ProductCategory.id)
        .outerjoin(ppm, and_(
            ppm.product_id == DailySales.product_id,
            ppm.portal_id == DailySales.portal_id,
        ))
        .filter(DailySales.portal_id.in_(included))
        .filter(ProductCategory.l1_name.in_(["Drinkware", "Cookware", "Kitchen Appliances"]))
    )
    if start_date:
        q = q.filter(DailySales.sale_date >= start_date)
    if end_date:
        q = q.filter(DailySales.sale_date <= end_date)
    if portal_id:
        q = q.filter(DailySales.portal_id == portal_id)
        mapped = _mapped_product_ids(db, portal_id)
        if mapped:
            q = q.filter(DailySales.product_id.in_(mapped))

    rows = (
        q.group_by(ProductCategory.l1_name)
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
    ppm = aliased(ProductPortalMapping, flat=True)
    bau_rev = _bau_revenue_expr(ppm)
    actual_sq = (
        db.query(
            DailySales.portal_id.label("portal_id"),
            func.coalesce(func.sum(bau_rev), Decimal("0")).label("actual_revenue"),
            func.coalesce(func.sum(DailySales.units_sold), Decimal("0")).label("actual_units"),
        )
        .join(Product, DailySales.product_id == Product.id)
        .outerjoin(ppm, and_(
            ppm.product_id == DailySales.product_id,
            ppm.portal_id == DailySales.portal_id,
        ))
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


@router.get("/latest-date")
def latest_sale_date(
    portal_id: Optional[int] = Query(None, description="Filter by portal; omit for cross-portal max"),
    db: Session = Depends(get_db),
):
    """Return the most recent sale_date present in daily_sales.

    When portal_id is supplied, returns the latest date for that specific
    portal.  Otherwise returns the global max across all included (active +
    aliased) portals.  The frontend uses this to anchor date-range presets
    to real data instead of the calendar date.
    """
    included = _included_portal_ids(db)
    q = db.query(func.max(DailySales.sale_date)).filter(
        DailySales.portal_id.in_(included),
    )
    if portal_id:
        q = q.filter(DailySales.portal_id == portal_id)
    latest = q.scalar()
    return {"date": str(latest) if latest else None}


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
    #    For specific portals, only include products that have a valid mapping
    #    (i.e. listed in the SKU mapping file with a portal code).
    sales_q = (
        db.query(func.distinct(DailySales.product_id))
        .filter(
            DailySales.portal_id.in_(portal_ids_for_query),
            DailySales.sale_date >= start_date,
            DailySales.sale_date <= end_date,
        )
    )
    mapped = []
    if portal_obj_id is not None:
        mapped = _mapped_product_ids(db, portal_obj_id)
        if mapped:
            sales_q = sales_q.filter(DailySales.product_id.in_(mapped))
    sales_product_ids = sales_q.all()
    product_ids = set(r[0] for r in sales_product_ids)

    # Also include products that have inventory for this portal (even with no sales).
    # Applies to Blinkit (backend_stock/frontend_stock), Swiggy, Zepto (portal_stock),
    # and Amazon (amazon_fc_stock/open_po).
    if portal_obj_id is not None and not is_all_portals:
        _inv_portals = {"blinkit", "swiggy", "zepto", "amazon"}
        if portal.lower() in _inv_portals:
            inv_q = db.query(func.distinct(InventorySnapshot.product_id)).filter(
                InventorySnapshot.portal_id == portal_obj_id,
            )
            if portal.lower() == "blinkit":
                from sqlalchemy import or_
                inv_q = inv_q.filter(
                    or_(
                        InventorySnapshot.backend_stock.isnot(None),
                        InventorySnapshot.frontend_stock.isnot(None),
                    )
                )
            elif portal.lower() == "amazon":
                from sqlalchemy import or_
                inv_q = inv_q.filter(
                    or_(
                        InventorySnapshot.amazon_fc_stock.isnot(None),
                        InventorySnapshot.open_po.isnot(None),
                    )
                )
            else:
                inv_q = inv_q.filter(InventorySnapshot.portal_stock.isnot(None))
            if mapped:
                inv_q = inv_q.filter(InventorySnapshot.product_id.in_(mapped))
            product_ids |= set(r[0] for r in inv_q.all())

    product_ids = list(product_ids)
    if not product_ids:
        return PortalDailyResponse(portal_name=portal_display_name, dates=dates, rows=[])

    if portal_obj_id is not None:
        # Specific portal: LEFT JOIN mapping for portal_sku
        pq = (
            db.query(
                Product.id,
                Product.sku_code,
                Product.product_name,
                Product.sub_category,
                Product.default_asp,
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
                Product.sub_category,
                Product.default_asp,
                ProductCategory.l2_name.label("category"),
                literal(None).label("portal_sku"),
            )
            .outerjoin(ProductCategory, Product.category_id == ProductCategory.id)
        )
    product_rows = pq.filter(Product.id.in_(product_ids)).all()
    product_map = {r.id: r for r in product_rows}

    # 3b. Load portal-specific BAU ASP from product_portal_mapping
    portal_bau_map: dict[int, float] = {}  # product_id → bau_asp
    if portal_obj_id is not None:
        bau_rows = (
            db.query(ProductPortalMapping.product_id, ProductPortalMapping.bau_asp)
            .filter(
                ProductPortalMapping.portal_id == portal_obj_id,
                ProductPortalMapping.product_id.in_(product_ids),
                ProductPortalMapping.bau_asp.isnot(None),
            )
            .all()
        )
        portal_bau_map = {r.product_id: float(r.bau_asp) for r in bau_rows}

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

    # 5. Latest WH stock per product from EasyEcom inventory snapshots.
    #    EasyEcom's 'old_quantity' is stored as solara_stock and represents
    #    the Solara warehouse stock — shown as WH Stock for all portal views.
    inv_map: dict[int, float | None] = {}
    easyecom_portal = db.query(Portal).filter(func.lower(Portal.name) == "easyecom").first()
    if easyecom_portal and product_ids:
        latest_sq = (
            db.query(
                InventorySnapshot.product_id,
                func.max(InventorySnapshot.snapshot_date).label("max_date"),
            )
            .filter(
                InventorySnapshot.portal_id == easyecom_portal.id,
                InventorySnapshot.product_id.in_(product_ids),
                InventorySnapshot.solara_stock.isnot(None),
            )
            .group_by(InventorySnapshot.product_id)
            .subquery()
        )
        inv_rows = (
            db.query(InventorySnapshot.product_id, InventorySnapshot.solara_stock)
            .join(
                latest_sq,
                (InventorySnapshot.product_id == latest_sq.c.product_id)
                & (InventorySnapshot.snapshot_date == latest_sq.c.max_date),
            )
            .filter(InventorySnapshot.portal_id == easyecom_portal.id)
            .all()
        )
        inv_map = {
            r.product_id: float(r.solara_stock) if r.solara_stock is not None else None
            for r in inv_rows
        }

    # 5a2. Latest Amazon FC stock + open PO from inventory snapshots.
    amazon_stock_map: dict[int, float | None] = {}
    open_po_map: dict[int, float | None] = {}
    amazon_portal = db.query(Portal).filter(func.lower(Portal.name) == "amazon").first()
    if amazon_portal and product_ids:
        amz_latest_sq = (
            db.query(
                InventorySnapshot.product_id,
                func.max(InventorySnapshot.snapshot_date).label("max_date"),
            )
            .filter(
                InventorySnapshot.portal_id == amazon_portal.id,
                InventorySnapshot.product_id.in_(product_ids),
            )
            .group_by(InventorySnapshot.product_id)
            .subquery()
        )
        amz_inv_rows = (
            db.query(
                InventorySnapshot.product_id,
                InventorySnapshot.amazon_fc_stock,
                InventorySnapshot.open_po,
            )
            .join(
                amz_latest_sq,
                (InventorySnapshot.product_id == amz_latest_sq.c.product_id)
                & (InventorySnapshot.snapshot_date == amz_latest_sq.c.max_date),
            )
            .filter(InventorySnapshot.portal_id == amazon_portal.id)
            .all()
        )
        for r in amz_inv_rows:
            amazon_stock_map[r.product_id] = (
                float(r.amazon_fc_stock) if r.amazon_fc_stock is not None else None
            )
            open_po_map[r.product_id] = (
                float(r.open_po) if r.open_po is not None else None
            )

    # 5b. Latest Swiggy portal_stock from inventory snapshots.
    swiggy_stock_map: dict[int, float | None] = {}
    swiggy_portal = db.query(Portal).filter(func.lower(Portal.name) == "swiggy").first()
    if swiggy_portal and product_ids:
        sw_latest_sq = (
            db.query(
                InventorySnapshot.product_id,
                func.max(InventorySnapshot.snapshot_date).label("max_date"),
            )
            .filter(
                InventorySnapshot.portal_id == swiggy_portal.id,
                InventorySnapshot.product_id.in_(product_ids),
            )
            .group_by(InventorySnapshot.product_id)
            .subquery()
        )
        sw_inv_rows = (
            db.query(InventorySnapshot.product_id, InventorySnapshot.portal_stock)
            .join(
                sw_latest_sq,
                (InventorySnapshot.product_id == sw_latest_sq.c.product_id)
                & (InventorySnapshot.snapshot_date == sw_latest_sq.c.max_date),
            )
            .filter(InventorySnapshot.portal_id == swiggy_portal.id)
            .all()
        )
        for r in sw_inv_rows:
            swiggy_stock_map[r.product_id] = (
                float(r.portal_stock) if r.portal_stock is not None else None
            )

    # 5c. Latest Zepto portal_stock from inventory snapshots.
    zepto_stock_map: dict[int, float | None] = {}
    zepto_portal = db.query(Portal).filter(func.lower(Portal.name) == "zepto").first()
    if zepto_portal and product_ids:
        zt_latest_sq = (
            db.query(
                InventorySnapshot.product_id,
                func.max(InventorySnapshot.snapshot_date).label("max_date"),
            )
            .filter(
                InventorySnapshot.portal_id == zepto_portal.id,
                InventorySnapshot.product_id.in_(product_ids),
            )
            .group_by(InventorySnapshot.product_id)
            .subquery()
        )
        zt_inv_rows = (
            db.query(InventorySnapshot.product_id, InventorySnapshot.portal_stock)
            .join(
                zt_latest_sq,
                (InventorySnapshot.product_id == zt_latest_sq.c.product_id)
                & (InventorySnapshot.snapshot_date == zt_latest_sq.c.max_date),
            )
            .filter(InventorySnapshot.portal_id == zepto_portal.id)
            .all()
        )
        for r in zt_inv_rows:
            zepto_stock_map[r.product_id] = (
                float(r.portal_stock) if r.portal_stock is not None else None
            )

    # 5d. Latest Blinkit backend_stock + frontend_stock from inventory snapshots.
    blinkit_backend_map: dict[int, float | None] = {}
    blinkit_frontend_map: dict[int, float | None] = {}
    blinkit_portal = db.query(Portal).filter(func.lower(Portal.name) == "blinkit").first()
    if blinkit_portal and product_ids:
        bl_latest_sq = (
            db.query(
                InventorySnapshot.product_id,
                func.max(InventorySnapshot.snapshot_date).label("max_date"),
            )
            .filter(
                InventorySnapshot.portal_id == blinkit_portal.id,
                InventorySnapshot.product_id.in_(product_ids),
            )
            .group_by(InventorySnapshot.product_id)
            .subquery()
        )
        bl_inv_rows = (
            db.query(
                InventorySnapshot.product_id,
                InventorySnapshot.backend_stock,
                InventorySnapshot.frontend_stock,
            )
            .join(
                bl_latest_sq,
                (InventorySnapshot.product_id == bl_latest_sq.c.product_id)
                & (InventorySnapshot.snapshot_date == bl_latest_sq.c.max_date),
            )
            .filter(InventorySnapshot.portal_id == blinkit_portal.id)
            .all()
        )
        for r in bl_inv_rows:
            blinkit_backend_map[r.product_id] = (
                float(r.backend_stock) if r.backend_stock is not None else None
            )
            blinkit_frontend_map[r.product_id] = (
                float(r.frontend_stock) if r.frontend_stock is not None else None
            )

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

    # 7. Assemble rows — products with sales + inventory-only products
    result_rows: List[PortalDailyRow] = []
    assembled_pids: set = set()
    for pid, agg in sales_agg.items():
        if pid not in product_map:
            continue
        assembled_pids.add(pid)
        p = product_map[pid]
        # Use portal-specific BAU ASP from product_portal_mapping first;
        # fall back to products.default_asp; then calculated average
        if pid in portal_bau_map:
            bau_asp = portal_bau_map[pid]
        elif p.default_asp is not None and float(p.default_asp) > 0:
            bau_asp = float(p.default_asp)
        else:
            asps = agg["asps"]
            bau_asp = round(sum(asps) / len(asps), 2) if asps else None
        # MTD value: use BAU ASP * units when available and non-zero, else raw revenue
        if bau_asp is not None and bau_asp > 0:
            mtd_value = round(bau_asp * agg["total_units"], 0)
        elif bau_asp == 0:
            mtd_value = 0
        else:
            mtd_value = round(agg["total_value"], 0)
        result_rows.append(
            PortalDailyRow(
                sku_code=p.sku_code,
                product_name=p.product_name,
                sub_category=p.sub_category or None,
                category=p.category or "—",
                portal_sku=p.portal_sku or "—",
                bau_asp=bau_asp,
                wh_stock=inv_map.get(pid),
                amazon_stock=amazon_stock_map.get(pid),
                open_po=open_po_map.get(pid),
                swiggy_stock=swiggy_stock_map.get(pid),
                zepto_stock=zepto_stock_map.get(pid),
                backend_qty=blinkit_backend_map.get(pid),
                frontend_qty=blinkit_frontend_map.get(pid),
                daily_units={d: agg["daily"].get(d) for d in dates},
                mtd_units=agg["total_units"],
                mtd_value=mtd_value,
            )
        )

    # 7b. Inventory-only products (have stock but no sales in this date range)
    for pid in product_ids:
        if pid in assembled_pids or pid not in product_map:
            continue
        p = product_map[pid]
        bau_asp = portal_bau_map.get(pid)
        if bau_asp is None and p.default_asp is not None and float(p.default_asp) > 0:
            bau_asp = float(p.default_asp)
        result_rows.append(
            PortalDailyRow(
                sku_code=p.sku_code,
                product_name=p.product_name,
                sub_category=p.sub_category or None,
                category=p.category or "—",
                portal_sku=p.portal_sku or "—",
                bau_asp=bau_asp,
                wh_stock=inv_map.get(pid),
                amazon_stock=amazon_stock_map.get(pid),
                swiggy_stock=swiggy_stock_map.get(pid),
                zepto_stock=zepto_stock_map.get(pid),
                backend_qty=blinkit_backend_map.get(pid),
                frontend_qty=blinkit_frontend_map.get(pid),
                daily_units={d: None for d in dates},
                mtd_units=0,
                mtd_value=0.0,
            )
        )

    result_rows.sort(key=lambda r: r.mtd_units, reverse=True)

    return PortalDailyResponse(
        portal_name=portal_display_name,
        dates=dates,
        rows=result_rows,
    )
