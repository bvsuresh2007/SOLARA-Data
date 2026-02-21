# Schema — Forward-Looking Tables & Columns

**Assessed:** 2026-02-21
**Schema version:** v2 (12 tables)

These are tables and columns that exist in the schema for future use but carry no meaningful data today. None of them block current operations.

---

## Entire Tables That Are Forward-Looking

| Table | Designed For | Why Empty |
|-------|-------------|-----------|
| `warehouses` | Physical warehouse registry — name, code, portal, city | No source data exists. Also, `inventory_snapshots` currently uses flat columns (`solara_stock`, `amazon_fc_stock`, etc.) instead of a `warehouse_id` FK, so the table isn't wired into anything yet. Will become relevant when adding a new 3PL, second FC, or regional Blinkit hub. |
| `city_daily_sales` | City-level daily sales from portal CSV exports | The portal CSV import pipeline was never built. Data would come from per-portal CSV downloads (Zepto city export, Amazon order-level report, etc.), not from the master Excel. |

---

## Forward-Looking Columns Inside Active Tables

### `portals`
| Column | Current State | Purpose |
|--------|--------------|---------|
| `updated_at` | Always NULL | Audit timestamp for when a portal record is edited or deactivated |
| `is_active` | Always TRUE | Flag for deactivating a portal relationship (e.g. if Solara stops selling on a platform) |

### `cities`
| Column | Current State | Purpose |
|--------|--------------|---------|
| `state` | NULL for all 75 cities | Enables state-level filtering (e.g. all Karnataka cities). Needs manual population or an external geodata source. |

### `product_categories`
| Column | Current State | Purpose |
|--------|--------------|---------|
| `l1_name` | Always `'Kitchen & Dining'` for all 520 products | Supports multi-category expansion when Solara enters new product lines (electronics, personal care, etc.). Currently meaningless as a filter. |

### `products`
| Column | Current State | Purpose |
|--------|--------------|---------|
| `unit_type` | Always `'pieces'` | Designed for products sold by weight or volume (e.g. coffee, spices). Not needed for current catalogue. |
| `updated_at` | Never populated | Audit timestamp — not written by the importer. |

### `product_portal_mapping`
| Column | Current State | Purpose |
|--------|--------------|---------|
| `is_active` | Always TRUE for all 1,300 rows | Lifecycle tracking — should be set to FALSE when a SKU is delisted from a portal. Currently never updated. See SCHEMA_ISSUES.md ISSUE-09. |
| `portal_product_name` | Never populated (NULL) | The portal's own listing title for the product (separate from the internal `products.product_name`). The importer only stored `portal_sku`, not the listing name. |
| `updated_at` | Never populated | Audit timestamp — not written by the importer. |

### `daily_sales`
| Column | Current State | Purpose |
|--------|--------------|---------|
| `data_source` | Always `'excel'` | Will distinguish Excel-imported rows from scraper-written rows (`'excel'` vs `'scraper'`). Becomes meaningful when portal scrapers go live. See SCHEMA_ISSUES.md ISSUE-10. |

### `monthly_ad_spend`
| Column | Current State | Purpose |
|--------|--------------|---------|
| `total_revenue` | NULL for all 71 rows | Portal monthly revenue — needed to compute TACOS. The importer captured `ad_spend` but never resolved this field. See SCHEMA_ISSUES.md ISSUE-01. |
| `tacos_pct` | NULL for all 71 rows | TACOS % = `ad_spend / total_revenue × 100`. Blocked by `total_revenue` being NULL. See SCHEMA_ISSUES.md ISSUE-01. |

---

## Summary

| Category | Count |
|----------|-------|
| Forward-looking entire tables | 2 (`warehouses`, `city_daily_sales`) |
| Columns always stuck at one value | 4 (`unit_type`, `l1_name`, `data_source`, `is_active` × 2 tables) |
| Columns never populated by importer | 5 (`updated_at` × 3, `portal_product_name`, `total_revenue`, `tacos_pct`) |
| Columns needing external data | 1 (`cities.state`) |

---

## Related Files

- `database/SCHEMA_ISSUES.md` — data quality issues and fix SQL for broken fields
- `database/schema_v2.sql` — full DDL
- `shared/constants.py` — `CITY_NAME_MAP`, `CITY_REGION_MAP` for normalisation
