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
        key = (portal_id, sku)
        if key not in self._product_cache:
            row = (
                self._db.query(ProductPortalMapping)
                .filter(
                    ProductPortalMapping.portal_id == portal_id,
                    ProductPortalMapping.portal_sku == sku,
                )
                .first()
            )
            self._product_cache[key] = row.product_id if row else None
        return self._product_cache[key]

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
        if name not in self._city_cache:
            row = self._db.query(City).filter(City.name == name).first()
            self._city_cache[name] = row.id if row else None
            if row is None:
                logger.debug("City not found in DB: %s", city_name)
        return self._city_cache[name]
