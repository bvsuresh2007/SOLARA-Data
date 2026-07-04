"""
Shopify Combo (Product Bundle) Inventory Sync.

Combos are NON-STOCK items in Atlas (they have no Bin of their own) — they are
Product Bundles that explode into component SKUs at Delivery Note time. That
means Shopify has no Atlas-fed number for them: left alone, Shopify just
decrements its own count on each sale and (with inventory_policy=continue)
drifts negative and oversells.

This module fixes that by pushing a COMPONENT-DRIVEN buildable count:

    buildable(combo) = min over children of ( Main-Warehouse available // qty )
    available        = max(actual_qty - reserved_qty, 0)

Because every combo is recomputed from the SAME live component pool on each run,
the shared-component overstatement (e.g. one fry-pan stock backing three combos)
is self-correcting between runs — the only exposure is the window between syncs,
which is why we also force inventory_policy=deny so a combo hard-stops at 0
instead of overselling if two combos race for the last shared component.

Auto-discovers every Atlas Product Bundle that has a matching Shopify variant
(by SKU), so it fixes the whole catalog, not a hardcoded list.

Run as part of the daily run (API-only, no browser):

    python -m scrapers.shopify_combo_inventory_sync           # push live buildable
    python -m scrapers.shopify_combo_inventory_sync --dry-run # report only, no writes

Optional env:
    COMBO_STOCK_BUFFER   units to hold back per combo (default 0) — extra safety
                         against same-window races on a scarce shared component.
"""

import os
import sys
import json
import logging

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("scrapers.shopify_combo_inventory_sync")

WAREHOUSE = "Main Warehouse - WTBBPL"
SHOP = "https://" + os.environ.get("SHOPIFY_STORE_URL", "dev-solara.myshopify.com").replace("https://", "")
API = "2024-01"
# Main location — variants are stocked here (read_locations scope is unavailable
# for this app token, so it is pinned; matches the rest of the sync scripts).
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


def fetch_bundles(url, h) -> dict[str, list[tuple[str, float]]]:
    """Return {combo_sku: [(child_sku, qty), ...]} for every Product Bundle."""
    r = requests.get(
        f"{url}/api/method/frappe.client.get_list",
        headers=h,
        params={
            "doctype": "Product Bundle",
            "filters": json.dumps([["disabled", "=", 0]]),
            "fields": json.dumps(["name", "new_item_code"]),
            "limit_page_length": 0,
        },
        timeout=60,
    )
    bundles = {}
    for b in r.json().get("message", []):
        doc = requests.get(f"{url}/api/resource/Product Bundle/{b['name']}", headers=h, timeout=30).json()["data"]
        children = [(it["item_code"], float(it.get("qty", 1) or 1)) for it in doc.get("items", [])]
        if children:
            bundles[b["new_item_code"]] = children
    return bundles


def main_available(url, h, skus: set[str]) -> dict[str, int]:
    """Return {sku: max(actual-reserved,0)} in Main Warehouse.

    Fetches ALL Main-Warehouse Bin rows in one paged sweep (filtered only on
    warehouse) and indexes locally. We deliberately avoid an ``in`` filter on
    item_code: for this API user the ``in`` filter is flaky and can silently
    return partial results, which would default real-stock SKUs to 0 and
    wrongly zero out (with policy=deny) combos that are actually buildable.
    """
    out = {}
    start = 0
    page = 2000
    while True:
        r = requests.get(
            f"{url}/api/method/frappe.client.get_list",
            headers=h,
            params={
                "doctype": "Bin",
                "filters": json.dumps([["warehouse", "=", WAREHOUSE]]),
                "fields": json.dumps(["item_code", "actual_qty", "reserved_qty"]),
                "limit_start": start,
                "limit_page_length": page,
            },
            timeout=120,
        )
        rows = r.json().get("message", [])
        for row in rows:
            out[row["item_code"]] = max(int(float(row["actual_qty"]) - float(row.get("reserved_qty", 0) or 0)), 0)
        if len(rows) < page:
            break
        start += page
    return out


def shopify_variant_map(token, skus: list[str]) -> dict[str, dict]:
    """Resolve {sku: {inventory_item_id, variant_id, tracked}} via GraphQL (batched)."""
    gql = f"{SHOP}/admin/api/{API}/graphql.json"
    gh = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    out = {}
    for sku in skus:
        q = {"query": '{ productVariants(first:5, query:"sku:%s"){edges{node{sku legacyResourceId inventoryItem{legacyResourceId tracked}}}} }' % sku}
        r = requests.post(gql, headers=gh, json=q, timeout=30)
        for e in r.json().get("data", {}).get("productVariants", {}).get("edges", []):
            n = e["node"]
            if n["sku"] == sku:
                out[sku] = {
                    "variant_id": n["legacyResourceId"],
                    "inventory_item_id": n["inventoryItem"]["legacyResourceId"],
                    "tracked": n["inventoryItem"].get("tracked"),
                }
                break
    return out


def sync(dry_run: bool = False):
    buffer = int(os.environ.get("COMBO_STOCK_BUFFER", "0"))
    url, h = _atlas()
    token = _shopify_token(url, h)
    sh = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    bundles = fetch_bundles(url, h)
    logger.info("Atlas Product Bundles found: %d", len(bundles))
    if not bundles:
        return {"synced": 0, "combos": []}

    # component availability for all children across all bundles
    all_children = {c for kids in bundles.values() for c, _ in kids}
    avail = main_available(url, h, all_children)
    # safety: never push a catalog-wide zero-out on a failed/empty stock fetch
    covered = sum(1 for c in all_children if c in avail)
    if covered < max(1, len(all_children) // 2):
        raise RuntimeError(
            f"Aborting: stock fetch covered only {covered}/{len(all_children)} components "
            "— refusing to push (would wrongly zero combos with policy=deny)."
        )

    # only bundles that actually have a Shopify variant
    vmap = shopify_variant_map(token, list(bundles.keys()))

    results = []
    synced = 0
    for combo, children in bundles.items():
        buildable = min(int(avail.get(c, 0) // q) for c, q in children)
        target = max(buildable - buffer, 0)
        v = vmap.get(combo)
        if not v:
            results.append((combo, buildable, target, "not-on-shopify"))
            continue
        if dry_run:
            results.append((combo, buildable, target, "dry-run"))
            logger.info("[dry] %s buildable=%d target=%d", combo, buildable, target)
            continue
        iid = int(v["inventory_item_id"])
        if not v.get("tracked"):
            requests.post(
                f"{SHOP}/admin/api/{API}/graphql.json",
                headers=sh,
                json={"query": 'mutation{ inventoryItemUpdate(id:"gid://shopify/InventoryItem/%s", input:{tracked:true}){inventoryItem{id}}}' % iid},
                timeout=30,
            )
        # policy -> deny (stop overselling between runs)
        requests.put(
            f"{SHOP}/admin/api/{API}/variants/{v['variant_id']}.json",
            headers=sh,
            json={"variant": {"id": int(v["variant_id"]), "inventory_policy": "deny"}},
            timeout=30,
        )
        rs = requests.post(
            f"{SHOP}/admin/api/{API}/inventory_levels/set.json",
            headers=sh,
            json={"location_id": LOCATION_ID, "inventory_item_id": iid, "available": target},
            timeout=30,
        )
        ok = rs.status_code in (200, 201)
        synced += 1 if ok else 0
        results.append((combo, buildable, target, "OK" if ok else f"FAIL{rs.status_code}"))
        logger.info("%s buildable=%d -> pushed=%d %s", combo, buildable, target, "OK" if ok else f"FAIL{rs.status_code}")

    on_shop = [r for r in results if r[3] not in ("not-on-shopify",)]
    logger.info("=== Combo inventory sync: %d/%d pushed (buffer=%d) ===", synced, len(on_shop), buffer)
    return {"synced": synced, "combos": results}


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    out = sync(dry_run=dry)
    print(f"\n{'SKU':<22} {'Buildable':<10} {'Pushed':<8} Result")
    print("=" * 55)
    for combo, buildable, target, status in out["combos"]:
        print(f"{combo:<22} {buildable:<10} {target:<8} {status}")
