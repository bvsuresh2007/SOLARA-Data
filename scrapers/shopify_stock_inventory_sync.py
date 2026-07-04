"""
Shopify Standalone (stock-item) Inventory Sync  →  Atlas Main-Warehouse stock.

Pushes live Atlas Main-Warehouse availability to every Shopify variant whose SKU
is a real Atlas STOCK item (is_stock_item=1). This is the standalone-product
counterpart to shopify_combo_inventory_sync (which handles non-stock Product
Bundles); the two together keep the whole Shopify catalog aligned to Atlas.

    available = max(actual_qty - reserved_qty, 0)   in "Main Warehouse - WTBBPL"

Combos (Product Bundles) are is_stock_item=0, so they are naturally excluded
here and left to the combo sync. SKUs on Shopify that don't map to an Atlas
stock item are skipped (reported), never zeroed.

Run as part of the daily run (API-only, no browser; run after WH stock is
current):

    python -m scrapers.shopify_stock_inventory_sync            # push
    python -m scrapers.shopify_stock_inventory_sync --dry-run  # report only
"""

import os
import sys
import json
import time
import logging

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("scrapers.shopify_stock_inventory_sync")

WAREHOUSE = "Main Warehouse - WTBBPL"
SHOP = "https://" + os.environ.get("SHOPIFY_STORE_URL", "dev-solara.myshopify.com").replace("https://", "")
API = "2024-01"
LOCATION_ID = int(os.environ.get("SHOPIFY_MAIN_LOCATION_ID", "15392473133"))


def _atlas():
    url = os.environ["ERPNEXT_URL"].rstrip("/")
    h = {
        "Authorization": f'token {os.environ["ERPNEXT_API_KEY"]}:{os.environ["ERPNEXT_API_SECRET"]}',
        "Content-Type": "application/json",
    }
    return url, h


def _shopify_token(url, h):
    r = requests.get(
        f"{url}/api/method/frappe.client.get_value",
        headers=h,
        params={"doctype": "Shopify Setting", "fieldname": json.dumps(["password"])},
        timeout=30,
    )
    return r.json()["message"]["password"]


def _paged(url, h, doctype, filters, fields, page=2000):
    """Fetch all rows of a doctype via frappe.client.get_list (paged, no IN filter)."""
    out = []
    start = 0
    while True:
        r = requests.get(
            f"{url}/api/method/frappe.client.get_list",
            headers=h,
            params={
                "doctype": doctype,
                "filters": json.dumps(filters),
                "fields": json.dumps(fields),
                "limit_start": start,
                "limit_page_length": page,
            },
            timeout=120,
        )
        rows = r.json().get("message", [])
        out.extend(rows)
        if len(rows) < page:
            break
        start += page
    return out


def stock_item_codes(url, h) -> set:
    rows = _paged(url, h, "Item", [["is_stock_item", "=", 1], ["disabled", "=", 0]], ["item_code"])
    return {r["item_code"] for r in rows}


def main_available(url, h) -> dict:
    rows = _paged(url, h, "Bin", [["warehouse", "=", WAREHOUSE]], ["item_code", "actual_qty", "reserved_qty"])
    return {r["item_code"]: max(int(float(r["actual_qty"]) - float(r.get("reserved_qty", 0) or 0)), 0) for r in rows}


def iter_shopify_variants(token):
    """Yield {sku, inv_item_id, tracked, qty} for EVERY variant.

    Uses REST /products.json cursor pagination (Link header). GraphQL's global
    productVariants connection was observed to silently drop variants here,
    which broke dedupe (missed duplicates never got zeroed) and could skip
    stock variants entirely — so we enumerate via the reliable REST product feed.
    """
    st = {"X-Shopify-Access-Token": token}
    url = f"{SHOP}/admin/api/{API}/products.json?limit=250&fields=id,variants"
    while url:
        r = requests.get(url, headers=st, timeout=60)
        for p in r.json().get("products", []):
            for v in p.get("variants", []):
                if not v.get("sku"):
                    continue
                yield {
                    "sku": v["sku"],
                    "inv_item_id": v.get("inventory_item_id"),
                    "tracked": (v.get("inventory_management") == "shopify"),
                    "qty": v.get("inventory_quantity"),
                }
        # follow Link: <...>; rel="next"
        nxt = None
        for part in r.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                nxt = part[part.find("<") + 1 : part.find(">")]
        url = nxt


def sync(dry_run: bool = False):
    url, h = _atlas()
    token = _shopify_token(url, h)
    sh = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    stock = stock_item_codes(url, h)
    avail = main_available(url, h)
    logger.info("Atlas stock items: %d   Main-Warehouse bins: %d", len(stock), len(avail))
    if len(stock) < 50 or len(avail) < 50:
        raise RuntimeError(f"Aborting: Atlas fetch looks incomplete (stock={len(stock)}, bins={len(avail)}).")

    # Collect all stock-item variants, grouped by SKU. When a SKU maps to
    # multiple Shopify variants, only the PRIMARY variant (the live listing,
    # taken as the one with the highest current inventory) receives the full
    # Atlas Main figure; the duplicates are set to 0 so the same physical stock
    # is never advertised on more than one listing.
    from collections import defaultdict
    groups = defaultdict(list)
    skipped_nonstock = 0
    for v in iter_shopify_variants(token):
        sku = v["sku"]
        if sku not in stock:
            skipped_nonstock += 1  # combo or unmapped — left alone
            continue
        if v["inv_item_id"] is None:
            continue
        groups[sku].append(v)

    # decide target per variant
    plan = []  # (sku, variant, target, is_primary)
    for sku, variants in groups.items():
        main = avail.get(sku, 0)
        if len(variants) == 1:
            plan.append((sku, variants[0], main, True))
        else:
            # primary = highest current qty (None -> -inf), tie-break stable by inv_item_id
            primary = max(variants, key=lambda v: ((v["qty"] if v["qty"] is not None else -(10**9)), -int(v["inv_item_id"])))
            for v in variants:
                is_p = v["inv_item_id"] == primary["inv_item_id"]
                plan.append((sku, v, main if is_p else 0, is_p))

    pushed = changed = 0
    changes = []
    for sku, v, target, is_primary in plan:
        old = v["qty"]
        iid = v["inv_item_id"]
        tag = "" if len(groups[sku]) == 1 else ("dup-primary" if is_primary else "dup-zeroed")
        if dry_run:
            if old != target:
                changes.append((sku, old, target, tag))
            continue
        if not v["tracked"]:
            requests.post(
                f"{SHOP}/admin/api/{API}/graphql.json",
                headers=sh,
                json={"query": 'mutation{ inventoryItemUpdate(id:"gid://shopify/InventoryItem/%s", input:{tracked:true}){inventoryItem{id}}}' % iid},
                timeout=30,
            )
        rs = requests.post(
            f"{SHOP}/admin/api/{API}/inventory_levels/set.json",
            headers=sh,
            json={"location_id": LOCATION_ID, "inventory_item_id": int(iid), "available": target},
            timeout=30,
        )
        if rs.status_code in (200, 201):
            pushed += 1
            if old != target:
                changed += 1
                changes.append((sku, old, target, tag))
        else:
            logger.warning("set failed %s: %s %s", sku, rs.status_code, rs.text[:120])
        time.sleep(0.25)

    logger.info(
        "=== Standalone sync: %s%d stock variants, %d changed, %d skipped (combo/unmapped) ===",
        "[dry] " if dry_run else "", (len(changes) if dry_run else pushed), (len(changes) if dry_run else changed), skipped_nonstock,
    )
    return {"pushed": pushed, "changed": changed, "skipped_nonstock": skipped_nonstock, "changes": changes}


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    out = sync(dry_run=dry)
    print(f"\n{'SKU':<26} {'Shopify(old)':<13} {'-> set':<8} {'note'}")
    print("=" * 58)
    for sku, old, new, tag in sorted(out["changes"], key=lambda x: str(x[0])):
        print(f"{sku:<26} {str(old):<13} {str(new):<8} {tag}")
    print(f"\nchanged={len(out['changes'])}  skipped(combo/unmapped)={out['skipped_nonstock']}")
