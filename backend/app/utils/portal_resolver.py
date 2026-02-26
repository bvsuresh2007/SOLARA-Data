"""
Resolves raw parsed strings (portal names, portal SKUs, city names) to DB integer IDs.

Uses a simple dict cache per resolver instance to avoid N+1 queries per file.
One PortalResolver instance should be created per upload request and discarded after.
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from ..models.metadata import Portal, City
from ..models.sales import Product, ProductPortalMapping

logger = logging.getLogger(__name__)


class PortalResolver:
    def __init__(self, db: Session):
        self._db = db
        self._portal_cache: dict[str, Optional[int]] = {}
        self._product_cache: dict[tuple[int, str], Optional[int]] = {}
        self._sku_cache: dict[str, Optional[int]] = {}   # sku_code → product_id (master Excel)
        self._city_cache: dict[str, Optional[int]] = {}
        # Tracks which portal_ids have been bulk-loaded into _product_cache already
        self._product_portals_loaded: set[int] = set()
        # Tracks whether all cities have been bulk-loaded into _city_cache
        self._cities_loaded: bool = False

    def portal_id(self, portal_name: str) -> Optional[int]:
        name = portal_name.lower().strip()
        if name not in self._portal_cache:
            row = self._db.query(Portal).filter(Portal.name == name).first()
            self._portal_cache[name] = row.id if row else None
            if row is None:
                logger.warning("Portal not found in DB: %s", portal_name)
        return self._portal_cache[name]

    def product_id(self, portal_id: int, portal_sku: str) -> Optional[int]:
        sku = portal_sku.strip()
        # Bulk-load all mappings for this portal on first access — 1 query instead of N
        if portal_id not in self._product_portals_loaded:
            rows = (
                self._db.query(ProductPortalMapping)
                .filter(ProductPortalMapping.portal_id == portal_id)
                .all()
            )
            for row in rows:
                self._product_cache[(portal_id, row.portal_sku)] = row.product_id
            self._product_portals_loaded.add(portal_id)
        return self._product_cache.get((portal_id, sku))

    def product_id_by_sku(self, sku_code: str) -> Optional[int]:
        """Look up product_id by SOL- sku_code (used for master Excel which has raw SKU codes)."""
        sku = sku_code.strip()
        if sku not in self._sku_cache:
            row = self._db.query(Product).filter(Product.sku_code == sku).first()
            self._sku_cache[sku] = row.id if row else None
            if row is None:
                logger.debug("Product not found by sku_code: %s", sku_code)
        return self._sku_cache[sku]

    def city_id(self, city_name: str) -> Optional[int]:
        name = city_name.lower().strip()
        # Bulk-load all cities on first access — 1 query instead of N
        if not self._cities_loaded:
            for row in self._db.query(City).all():
                self._city_cache[row.name.lower()] = row.id
            self._cities_loaded = True
        return self._city_cache.get(name)
