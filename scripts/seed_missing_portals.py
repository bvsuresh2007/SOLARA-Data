"""
Add easyecom and amazon_pi portals to the portals table, then seed their
product_portal_mapping entries:

  easyecom   → portal_sku = SOL-SKU (self-mapping; product must already exist)
  amazon_pi  → portal_sku = ASIN    (duplicate of amazon portal mappings)

Safe to re-run — all upserts use ON CONFLICT DO NOTHING / DO UPDATE.

Usage:
    python scripts/seed_missing_portals.py
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

from sqlalchemy import text
from scripts.db_utils import get_session


def _add_portals(session) -> None:
    session.execute(text("""
        INSERT INTO portals (name, display_name) VALUES
            ('easyecom',  'EasyEcom'),
            ('amazon_pi', 'Amazon PI')
        ON CONFLICT (name) DO NOTHING
    """))
    session.commit()
    logger.info("Portals easyecom + amazon_pi ensured.")


def _seed_easyecom(session) -> int:
    """
    For every product in the products table, create a product_portal_mapping
    row for easyecom with portal_sku = sku_code (EasyEcom uses SOL-SKU codes).
    """
    row = session.execute(
        text("SELECT id FROM portals WHERE name = 'easyecom'")
    ).fetchone()
    if not row:
        logger.error("easyecom portal not found — run _add_portals first.")
        return 0
    easyecom_portal_id = row[0]

    products = session.execute(
        text("SELECT id, sku_code, product_name FROM products")
    ).fetchall()

    count = 0
    for product_id, sku_code, product_name in products:
        session.execute(text("""
            INSERT INTO product_portal_mapping
                (product_id, portal_id, portal_sku, portal_product_name, updated_at)
            VALUES (:pid, :portal, :sku, :name, NOW())
            ON CONFLICT (portal_id, portal_sku) DO UPDATE SET
                product_id          = EXCLUDED.product_id,
                portal_product_name = COALESCE(EXCLUDED.portal_product_name,
                                               product_portal_mapping.portal_product_name),
                updated_at          = NOW()
        """), {
            "pid": product_id,
            "portal": easyecom_portal_id,
            "sku": sku_code,
            "name": product_name,
        })
        count += 1

    session.commit()
    logger.info("EasyEcom self-mapping: %d products.", count)
    return count


def _seed_amazon_pi(session) -> int:
    """
    Duplicate all amazon portal mappings under amazon_pi.
    Both portals use ASINs as portal_sku.
    """
    row_amz = session.execute(
        text("SELECT id FROM portals WHERE name = 'amazon'")
    ).fetchone()
    row_pi = session.execute(
        text("SELECT id FROM portals WHERE name = 'amazon_pi'")
    ).fetchone()
    if not row_amz or not row_pi:
        logger.error("amazon or amazon_pi portal missing — check portals table.")
        return 0

    amazon_id = row_amz[0]
    amazon_pi_id = row_pi[0]

    existing = session.execute(text("""
        SELECT product_id, portal_sku, portal_product_name
        FROM product_portal_mapping
        WHERE portal_id = :pid
    """), {"pid": amazon_id}).fetchall()

    count = 0
    for product_id, portal_sku, portal_product_name in existing:
        session.execute(text("""
            INSERT INTO product_portal_mapping
                (product_id, portal_id, portal_sku, portal_product_name, updated_at)
            VALUES (:pid, :portal, :sku, :name, NOW())
            ON CONFLICT (portal_id, portal_sku) DO UPDATE SET
                product_id          = EXCLUDED.product_id,
                portal_product_name = COALESCE(EXCLUDED.portal_product_name,
                                               product_portal_mapping.portal_product_name),
                updated_at          = NOW()
        """), {
            "pid": product_id,
            "portal": amazon_pi_id,
            "sku": portal_sku,
            "name": portal_product_name,
        })
        count += 1

    session.commit()
    logger.info("Amazon PI ASIN mapping: %d entries duplicated from amazon.", count)
    return count


def main():
    with get_session() as session:
        _add_portals(session)
        ee = _seed_easyecom(session)
        api = _seed_amazon_pi(session)
    logger.info("Done. EasyEcom: %d, Amazon PI: %d mappings.", ee, api)


if __name__ == "__main__":
    main()
