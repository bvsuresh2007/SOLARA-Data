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

from shared.constants import normalise_city, CITY_REGION_MAP
from shared.pincode_lookup import pincode_lookup, normalise_city_name

logger = logging.getLogger(__name__)

# Portal name aliases — map scraper-only portal names to the canonical portal
# that the dashboard reads from.  Prevents data from landing under an inactive
# portal (e.g. "amazon_pi" → "amazon") if the parser ever emits the wrong slug.
PORTAL_ALIASES: dict[str, str] = {
    "amazon_pi": "amazon",
}


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
        self._sku_cache: dict[str, int] = {}         # sku_code → product_id (direct lookup)

    def _get_portal_id(self, name: str) -> int | None:
        canonical = PORTAL_ALIASES.get(name, name)
        if canonical not in self._portal_cache:
            from backend.app.models.metadata import Portal
            portal = self.db.query(Portal).filter_by(name=canonical).first()
            if portal:
                self._portal_cache[canonical] = portal.id
        if name != canonical:
            self._portal_cache[name] = self._portal_cache.get(canonical)
        return self._portal_cache.get(canonical)

    def _get_or_create_city(self, city_name: str, pincode: str = None) -> int | None:
        """
        Resolve city name to city_id.  If a pincode is supplied we use it to
        derive a canonical city + state, which avoids duplicate entries from
        free-text city names (e.g. Shopify shipping addresses).
        """
        # 1. If pincode is given, try pincode lookup first
        pin_city = pin_state = pin_region = None
        if pincode:
            pin_city, pin_state, pin_region = pincode_lookup(pincode)

        # 2. Determine canonical city name
        if pin_city:
            canonical = normalise_city(pin_city) or pin_city
        else:
            canonical = normalise_city(city_name)

        if not canonical:
            return None

        # 3. Look up / create city in DB
        if canonical not in self._city_cache:
            from backend.app.models.metadata import City
            city = self.db.query(City).filter_by(name=canonical).first()
            if not city:
                region = pin_region or CITY_REGION_MAP.get(canonical)
                city = City(name=canonical, state=pin_state, region=region)
                self.db.add(city)
                self.db.flush()
                logger.info("Created city: %s (state=%s, region=%s)", canonical, pin_state, region)
            else:
                # Backfill state if we have it and it's missing in DB
                updated = False
                if pin_state and not city.state:
                    city.state = pin_state
                    updated = True
                if pin_region and not city.region:
                    city.region = pin_region
                    updated = True
                if updated:
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

    def _get_product_id_by_sku(self, sku_code: str) -> int | None:
        """Look up product_id by SOL-XXXX sku_code directly (no portal mapping needed)."""
        sku = sku_code.strip()
        if sku not in self._sku_cache:
            from backend.app.models.sales import Product
            product = self.db.query(Product).filter_by(sku_code=sku).first()
            if product:
                self._sku_cache[sku] = product.id
            else:
                logger.warning("No product found for sku_code=%s", sku)
                return None
        return self._sku_cache.get(sku)

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

    def transform_sales_rows_by_sku(self, rows: list[dict]) -> list[dict]:
        """
        Like transform_sales_rows() but resolves product via sku_code directly
        (products.sku_code) instead of product_portal_mapping.

        Used for EasyEcom and Shopify, which use SOL-XXXX internal SKU codes — no
        product_portal_mapping entries are needed for the target portals.
        """
        out = []
        for row in rows:
            portal_id = self._get_portal_id(row.get("portal", ""))
            if not portal_id:
                continue
            city_id = self._get_or_create_city(row.get("city"), pincode=row.get("pincode"))
            if city_id is None:
                logger.warning("Skipping row — unknown city: %r (pincode=%r)", row.get("city"), row.get("pincode"))
                continue
            product_id = self._get_product_id_by_sku(row.get("portal_product_id", ""))
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

    def transform_sales_rows(self, rows: list[dict]) -> list[dict]:
        """Returns list of dicts ready to upsert into sales_data."""
        out = []
        for row in rows:
            portal_id = self._get_portal_id(row.get("portal", ""))
            if not portal_id:
                continue
            city_id = self._get_or_create_city(row.get("city"), pincode=row.get("pincode"))
            if city_id is None:
                logger.warning("Skipping row — unknown city: %r (pincode=%r)", row.get("city"), row.get("pincode"))
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
