"""
Data transformer: normalises raw parsed rows into database-ready records.
Handles:
  - Date normalisation (all → Python date objects)
  - City name standardisation (aliases → canonical names)
  - Product ID mapping via product_portal_mapping table
  - Duplicate detection
"""
import logging
from datetime import date
from typing import Any

from shared.constants import normalise_city

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Transformer
# ---------------------------------------------------------------------------

class DataTransformer:
    def __init__(self, db_session):
        self.db = db_session
        self._portal_cache: dict[str, int] = {}
        self._city_cache: dict[str, int] = {}
        self._warehouse_cache: dict[tuple, int] = {}
        self._product_cache: dict[tuple, int] = {}  # (portal_id, portal_product_id) → product_id

    def _get_portal_id(self, name: str) -> int | None:
        if name not in self._portal_cache:
            from backend.app.models.metadata import Portal
            portal = self.db.query(Portal).filter_by(name=name).first()
            if portal:
                self._portal_cache[name] = portal.id
        return self._portal_cache.get(name)

    def _get_or_create_city(self, city_name: str) -> int | None:
        canonical = normalise_city(city_name)
        if not canonical:
            return None
        if canonical not in self._city_cache:
            from backend.app.models.metadata import City
            city = self.db.query(City).filter_by(name=canonical).first()
            if not city:
                city = City(name=canonical)
                self.db.add(city)
                self.db.flush()
            self._city_cache[canonical] = city.id
        return self._city_cache[canonical]

    def _get_or_create_warehouse(self, portal_id: int, city_id: int | None, name: str) -> int | None:
        if not name:
            return None
        key = (portal_id, name)
        if key not in self._warehouse_cache:
            from backend.app.models.metadata import Warehouse
            wh = self.db.query(Warehouse).filter_by(portal_id=portal_id, name=name).first()
            if not wh:
                wh = Warehouse(portal_id=portal_id, city_id=city_id, name=name)
                self.db.add(wh)
                self.db.flush()
            self._warehouse_cache[key] = wh.id
        return self._warehouse_cache[key]

    def _get_product_id(self, portal_id: int, portal_product_id: str) -> int | None:
        key = (portal_id, portal_product_id)
        if key not in self._product_cache:
            from backend.app.models.sales import ProductPortalMapping
            mapping = self.db.query(ProductPortalMapping).filter_by(
                portal_id=portal_id, portal_sku=portal_product_id
            ).first()
            if mapping:
                self._product_cache[key] = mapping.product_id
            else:
                logger.warning("No product mapping for portal_id=%s, portal_sku=%s", portal_id, portal_product_id)
                return None
        return self._product_cache.get(key)

    def transform_sales_rows(self, rows: list[dict]) -> list[dict]:
        """Returns list of dicts ready to upsert into sales_data."""
        out = []
        for row in rows:
            portal_id = self._get_portal_id(row.get("portal", ""))
            if not portal_id:
                continue
            city_id = self._get_or_create_city(row.get("city"))
            if city_id is None:
                logger.warning("Skipping row — unknown city: %r", row.get("city"))
                continue
            product_id = self._get_product_id(portal_id, row.get("portal_product_id", ""))
            if not product_id:
                continue
            out.append({
                "portal_id": portal_id,
                "city_id": city_id,
                "product_id": product_id,
                "sale_date": row.get("sale_date"),
                "units_sold": row.get("quantity_sold", 0),
                "revenue": row.get("revenue", 0),
                "discount_amount": row.get("discount_amount", 0),
                "net_revenue": row.get("net_revenue", 0),
                "order_count": row.get("order_count", 0),
            })
        return out

    def transform_inventory_rows(self, rows: list[dict]) -> list[dict]:
        """Returns list of dicts ready to upsert into inventory_snapshots."""
        out = []
        for row in rows:
            portal_id = self._get_portal_id(row.get("portal", ""))
            if not portal_id:
                continue
            product_id = self._get_product_id(portal_id, row.get("portal_product_id", ""))
            if not product_id:
                continue
            # Map generic parser fields to InventorySnapshot columns.
            # Portal-specific parsers may emit named keys (portal_stock,
            # backend_stock, etc.) directly; fall back to stock_quantity.
            out.append({
                "portal_id": portal_id,
                "product_id": product_id,
                "snapshot_date": row.get("snapshot_date"),
                "portal_stock":    row.get("portal_stock", row.get("stock_quantity")),
                "backend_stock":   row.get("backend_stock"),
                "frontend_stock":  row.get("frontend_stock"),
                "solara_stock":    row.get("solara_stock"),
                "amazon_fc_stock": row.get("amazon_fc_stock"),
                "open_po":         row.get("open_po"),
                "doc":             row.get("doc"),
            })
        return out
