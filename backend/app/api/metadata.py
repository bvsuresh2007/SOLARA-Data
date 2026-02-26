import csv
import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models.metadata import Portal, City, Warehouse
from ..models.inventory import ImportLog

from ..schemas.metadata import (
    PortalOut, CityOut, WarehouseOut,
    ActionItemsResponse, PortalImportHealth, PortalCoverage, UnmappedProduct,
    PortalSkuGap, ImportFailure, CreatePortalMappingRequest,
)
from ..config import settings
from ..schemas.inventory import ImportLogOut

logger = logging.getLogger(__name__)

# Portals not yet integrated — excluded from action-items and health queries
_EXCLUDED_PORTALS_SQL = "('myntra','flipkart')"

# Maximum rows returned from mapping_gaps.csv (guards against huge files on every request)
_MAX_GAPS_ROWS = 500


def _find_gaps_csv() -> Path | None:
    p = Path(settings.source_data_path) / "mapping_gaps.csv"
    return p if p.exists() else None

router = APIRouter()


@router.get("/portals", response_model=List[PortalOut])
def list_portals(active_only: bool = True, db: Session = Depends(get_db)):
    q = db.query(Portal)
    if active_only:
        q = q.filter(Portal.is_active == True)
    return q.order_by(Portal.name).all()


@router.get("/cities", response_model=List[CityOut])
def list_cities(
    active_only: bool = True,
    region: str = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(City)
    if active_only:
        q = q.filter(City.is_active == True)
    if region:
        q = q.filter(City.region == region)
    return q.order_by(City.name).all()


@router.get("/warehouses", response_model=List[WarehouseOut])
def list_warehouses(
    portal_id: int = Query(None),
    city_id: int = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Warehouse).filter(Warehouse.is_active == True)
    if portal_id is not None:
        q = q.filter(Warehouse.portal_id == portal_id)
    if city_id is not None:
        q = q.filter(Warehouse.city_id == city_id)
    return q.order_by(Warehouse.name).all()


@router.get("/action-items", response_model=ActionItemsResponse)
def get_action_items(db: Session = Depends(get_db)):
    # Total product count
    total_products = db.execute(text("SELECT COUNT(*) FROM products")).scalar() or 0

    # Query A — mapped product count per portal
    coverage_rows = db.execute(text(f"""
        SELECT
            po.name         AS portal_name,
            po.display_name,
            COUNT(DISTINCT ppm.product_id) AS mapped_products
        FROM portals po
        LEFT JOIN product_portal_mapping ppm
            ON ppm.portal_id = po.id AND ppm.is_active = true
        WHERE po.name NOT IN {_EXCLUDED_PORTALS_SQL}
        GROUP BY po.id, po.name, po.display_name
        ORDER BY COUNT(DISTINCT ppm.product_id) DESC
    """)).fetchall()

    portal_coverage = [
        PortalCoverage(
            portal_name=r.portal_name,
            display_name=r.display_name,
            mapped_products=r.mapped_products,
            total_products=total_products,
            gap=total_products - r.mapped_products,
        )
        for r in coverage_rows
    ]

    # Query B — products missing mapping for ≥1 portal
    unmapped_rows = db.execute(text(f"""
        WITH active_portals AS (
            SELECT id, name, display_name
            FROM portals
            WHERE name NOT IN {_EXCLUDED_PORTALS_SQL}
        )
        SELECT
            p.id AS product_id,
            p.sku_code,
            p.product_name,
            string_agg(ap.display_name, ', ' ORDER BY ap.display_name) AS missing_portals,
            string_agg(ap.name,         ','  ORDER BY ap.display_name) AS missing_portal_slugs,
            COUNT(*) AS missing_count
        FROM products p
        CROSS JOIN active_portals ap
        LEFT JOIN product_portal_mapping ppm
            ON ppm.product_id = p.id AND ppm.portal_id = ap.id AND ppm.is_active = true
        WHERE ppm.id IS NULL
        GROUP BY p.id, p.sku_code, p.product_name
        HAVING COUNT(*) > 0
        ORDER BY COUNT(*) DESC, p.product_name
        LIMIT 100
    """)).fetchall()

    unmapped_products = [
        UnmappedProduct(
            product_id=r.product_id,
            sku_code=r.sku_code or "",
            product_name=r.product_name,
            missing_portals=r.missing_portals,
            missing_portal_slugs=r.missing_portal_slugs,
            missing_count=r.missing_count,
        )
        for r in unmapped_rows
    ]

    # Query C — last pipeline run per portal
    health_rows = db.execute(text(f"""
        SELECT
            po.name         AS portal_name,
            po.display_name,
            MAX(il.end_time) AS last_import_at,
            (SELECT il2.status FROM import_logs il2
             WHERE il2.portal_id = po.id
             ORDER BY il2.end_time DESC NULLS LAST LIMIT 1) AS last_status,
            COUNT(il.id)    AS total_imports,
            COUNT(CASE WHEN il.status = 'failed' THEN 1 END) AS failed_runs
        FROM portals po
        LEFT JOIN import_logs il
            ON il.portal_id = po.id AND il.source_type = 'portal_scraper'
        WHERE po.name NOT IN {_EXCLUDED_PORTALS_SQL}
        GROUP BY po.id, po.name, po.display_name
        ORDER BY MAX(il.end_time) DESC NULLS LAST
    """)).fetchall()

    import_health = [
        PortalImportHealth(
            portal_name=r.portal_name,
            display_name=r.display_name,
            last_import_at=r.last_import_at,
            last_status=r.last_status,
            total_imports=r.total_imports,
            failed_runs=r.failed_runs,
        )
        for r in health_rows
    ]

    # Section D — portal SKU gaps from mapping_gaps.csv
    portal_sku_gaps: list[PortalSkuGap] = []
    gaps_path = _find_gaps_csv()
    if gaps_path:
        try:
            with open(gaps_path, newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    if len(portal_sku_gaps) >= _MAX_GAPS_ROWS:
                        break
                    portal_sku_gaps.append(PortalSkuGap(
                        portal=row.get("portal", ""),
                        portal_sku=row.get("portal_sku", ""),
                        portal_name=row.get("portal_name", ""),
                        matched_sol_sku=row.get("matched_sol_sku", ""),
                        matched_name=row.get("matched_name", ""),
                        score=float(row.get("score", 0)),
                        status=row.get("status", ""),
                    ))
        except Exception as exc:
            logger.warning("Could not read mapping_gaps.csv: %s", exc)
    else:
        logger.info("mapping_gaps.csv not found — portal_sku_gaps will be empty")

    return ActionItemsResponse(
        total_products=total_products,
        import_health=import_health,
        portal_coverage=portal_coverage,
        unmapped_products=unmapped_products,
        portal_sku_gaps=portal_sku_gaps,
    )


@router.get("/import-failures", response_model=List[ImportFailure])
def get_import_failures(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT
            il.id,
            po.name         AS portal_name,
            po.display_name,
            il.file_name,
            il.import_date::text  AS import_date,
            il.start_time::text   AS start_time,
            il.error_message,
            il.source_type
        FROM import_logs il
        LEFT JOIN portals po ON po.id = il.portal_id
        WHERE il.status = 'failed'
        ORDER BY il.start_time DESC NULLS LAST
        LIMIT :limit
    """), {"limit": limit}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/portal-mappings", status_code=201)
def create_portal_mapping(body: CreatePortalMappingRequest, db: Session = Depends(get_db)):
    # Resolve portal
    portal_row = db.execute(
        text("SELECT id FROM portals WHERE name = :n"), {"n": body.portal_name}
    ).fetchone()
    if not portal_row:
        raise HTTPException(status_code=404, detail=f"Portal '{body.portal_name}' not found")
    portal_id = portal_row[0]

    product_id = body.product_id
    if product_id is None:
        # Create new product first
        if not body.new_sku_code or not body.new_product_name:
            raise HTTPException(
                status_code=422,
                detail="Either product_id or new_sku_code + new_product_name is required",
            )
        row = db.execute(text("""
            INSERT INTO products (sku_code, product_name, updated_at)
            VALUES (:sku, :name, NOW())
            ON CONFLICT (sku_code)
            DO UPDATE SET product_name = EXCLUDED.product_name, updated_at = NOW()
            RETURNING id
        """), {"sku": body.new_sku_code.strip(), "name": body.new_product_name.strip()}).fetchone()
        db.flush()
        product_id = row[0]

    # Upsert portal mapping
    db.execute(text("""
        INSERT INTO product_portal_mapping
            (product_id, portal_id, portal_sku, portal_product_name, updated_at)
        VALUES (:pid, :portal, :sku, :name, NOW())
        ON CONFLICT (portal_id, portal_sku)
        DO UPDATE SET
            product_id          = EXCLUDED.product_id,
            portal_product_name = COALESCE(EXCLUDED.portal_product_name,
                                           product_portal_mapping.portal_product_name),
            updated_at          = NOW()
    """), {
        "pid":    product_id,
        "portal": portal_id,
        "sku":    body.portal_sku.strip(),
        "name":   body.portal_product_name,
    })
    db.commit()
    return {"ok": True, "product_id": product_id, "portal_id": portal_id}


@router.get("/scraping-logs", response_model=List[ImportLogOut])
def list_scraping_logs(
    portal_id: int = Query(None),
    status: str = Query(None),
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(ImportLog).options(joinedload(ImportLog.portal))
    if portal_id is not None:
        q = q.filter(ImportLog.portal_id == portal_id)
    if status:
        q = q.filter(ImportLog.status == status)
    rows = q.order_by(ImportLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "source_type": r.source_type,
            "portal_id": r.portal_id,
            "portal_name": r.portal.display_name if r.portal else None,
            "sheet_name": r.sheet_name,
            "file_name": r.file_name,
            "import_date": r.import_date,
            "start_time": r.start_time,
            "end_time": r.end_time,
            "status": r.status,
            "records_imported": r.records_imported,
            "error_message": r.error_message,
            "created_at": r.created_at,
        }
        for r in rows
    ]
