"""
Shared helper: declared-value lookup for Clickpost shipments.

Single source of truth so that MANUAL Clickpost fallbacks declare the SAME
value the Atlas auto-trigger ("Create Clickpost Shipment" v6) uses — the MRP
price list. Before this, manual fallbacks passed the DN line rate (often a ₹1
token on free replacements) which under-declared the parcel value.

Rule (mirrors the LIVE server script as of 2026-06-23):
  declared_value(sku) = MRP price-list rate  if the SKU has an MRP entry
                        else valuation_rate  (fallback, logged as a warning)

Item.msrp custom field no longer exists on LIVE — the MRP price list is the
only source. 307 SKUs are populated; all common replacement SKUs are covered.

Usage:
    from clickpost_mrp import mrp_value, mrp_total
    val = mrp_value(BASE, H, 'SOL-AF-501')          # -> 12999.0
    total = mrp_total(BASE, H, ['SOL-AF-501', ...]) # sum of per-SKU MRP
"""
import json
import requests

_MRP_CACHE = {}
_VAL_CACHE = {}


def _fetch_mrp(BASE, H, sku):
    r = requests.get(f'{BASE}/api/method/frappe.client.get_list', headers=H, params={
        'doctype': 'Item Price',
        'filters': json.dumps([['price_list', '=', 'MRP'], ['item_code', '=', sku]]),
        'fields': json.dumps(['price_list_rate'])}, timeout=15)
    rows = r.json().get('message', []) if r.status_code == 200 else []
    return float(rows[0]['price_list_rate']) if rows else None


def _fetch_valuation(BASE, H, sku):
    r = requests.get(f'{BASE}/api/resource/Item/{sku}', headers=H, params={
        'fields': json.dumps(['valuation_rate', 'last_purchase_rate', 'standard_rate'])}, timeout=15)
    if r.status_code != 200:
        return 0.0
    d = r.json()['data']
    for f in ('valuation_rate', 'last_purchase_rate', 'standard_rate'):
        v = float(d.get(f) or 0)
        if v > 0:
            return v
    return 0.0


def mrp_value(BASE, H, sku, warn=True):
    """Declared value for one SKU: MRP if available, else valuation_rate (fallback)."""
    if sku not in _MRP_CACHE:
        _MRP_CACHE[sku] = _fetch_mrp(BASE, H, sku)
    mrp = _MRP_CACHE[sku]
    if mrp is not None:
        return mrp
    if sku not in _VAL_CACHE:
        _VAL_CACHE[sku] = _fetch_valuation(BASE, H, sku)
    val = _VAL_CACHE[sku]
    if warn:
        print(f'  [clickpost_mrp] WARN: {sku} has no MRP price-list entry -> falling back to valuation_rate {val}')
    return val


def mrp_total(BASE, H, skus, warn=True):
    """Sum of per-SKU declared values for a multi-line parcel."""
    return sum(mrp_value(BASE, H, s, warn=warn) for s in skus)
