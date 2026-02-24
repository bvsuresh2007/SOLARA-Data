# Database Reference

**Last updated:** 2026-02-23

PostgreSQL 15+ (`solara_dashboard` database, `public` schema).
12 tables across 4 logical groups: **master**, **product**, **transactional**, **audit**.

---

## Table Map

```
portals           ─┐
cities            ─┼─▶ daily_sales
products          ─┤   city_daily_sales
product_categories─┤   inventory_snapshots
                   │   monthly_targets
                   │   monthly_ad_spend
                   │   import_logs
                   │
warehouses ────────┘  (linked to portals + cities; not yet populated)
product_portal_mapping (join table: products ↔ portals)
```

---

## Master tables

### `portals`

Lookup for the 7 e-commerce portals Solara sells on.

| Column | Type | Notes |
|--------|------|-------|
| id | integer PK | auto-increment |
| name | varchar(50) UNIQUE | slug used in code — `easyecom`, `blinkit`, `zepto`, etc. |
| display_name | varchar(100) | Human label shown in UI |
| is_active | boolean | Filter inactive portals from UI/API |
| created_at | timestamp | |
| updated_at | timestamp | Nullable — set on edits |

**Why it exists:** Normalises portal identity across all transactional tables. Instead of storing `"Amazon PI"` in 329K rows, we store `portal_id=3`. Changing a display name is one row update.

---

### `cities`

75 Indian cities where products are sold or warehoused.

| Column | Type | Notes |
|--------|------|-------|
| id | integer PK | |
| name | varchar(100) | |
| state | varchar(100) | Nullable |
| region | varchar(50) | e.g. `North`, `South`, `West` |
| is_active | boolean | |
| created_at | timestamp | |

**Unique constraint:** `(name, COALESCE(state, ''))` — prevents duplicate city+state pairs.

**Why it exists:** Zepto, Blinkit, and EasyEcom report at city level. City IDs are used in `city_daily_sales`.

---

### `product_categories`

Two-level category hierarchy (L1 → L2).

| Column | Type | Notes |
|--------|------|-------|
| id | integer PK | |
| l1_name | varchar(100) | Top-level category (e.g. `Foods`) |
| l2_name | varchar(100) | Sub-category (e.g. `Healthy Snacks`) — nullable for top-level-only |

**Unique constraint:** `(l1_name, COALESCE(l2_name, ''))` — prevents duplicates even when l2 is null.

**Why it exists:** Products belong to a category; the frontend uses categories for filtering and rollup aggregations.

---

### `warehouses`

Solara's physical warehouse locations (0 rows currently — schema ready).

| Column | Type | Notes |
|--------|------|-------|
| id | integer PK | |
| name | varchar(200) | |
| code | varchar(100) | Short warehouse code |
| portal_id | integer FK → portals | Which portal fulfils from this warehouse |
| city_id | integer FK → cities | Location |
| is_active | boolean | |
| created_at | timestamp | |

**Why it exists:** For future inventory-in-transit tracking and fulfilment analytics.

---

## Product tables

### `products`

520 SKUs that Solara sells across all portals.

| Column | Type | Notes |
|--------|------|-------|
| id | integer PK | |
| sku_code | varchar(100) UNIQUE | Internal Solara SKU — single source of truth |
| product_name | varchar(500) | Canonical product name |
| category_id | integer FK → product_categories | Nullable |
| default_asp | numeric | Default average selling price (fallback when portal doesn't report ASP) |
| unit_type | varchar(50) | `pieces`, `kg`, `ml` etc. — default `pieces` |
| created_at | timestamp | |
| updated_at | timestamp | |

**Why it exists:** Portal SKU codes differ across portals (Amazon has ASIN, Blinkit has their own IDs). Products normalises to a single Solara SKU. All transactional data links to this table.

---

### `product_portal_mapping`

1,300 rows — each row maps one Solara product to one portal SKU.

| Column | Type | Notes |
|--------|------|-------|
| id | integer PK | |
| product_id | integer FK → products | |
| portal_id | integer FK → portals | |
| portal_sku | varchar(500) | Portal's own SKU/ASIN/listing ID |
| portal_product_name | varchar(500) | Portal's display name for this SKU |
| is_active | boolean | Flag discontinued listings |
| created_at | timestamp | |
| updated_at | timestamp | |

**Unique constraint:** `(portal_id, portal_sku)` — one SKU per portal is unique.

**Why it exists:** Scrapers download files with portal SKUs. The data transformer looks up this table to resolve `portal_sku → product_id` before inserting into transactional tables.

---

## Transactional tables

All transactional tables have:
- A composite **UNIQUE constraint** that prevents duplicate data for the same (portal, product, date) combination
- `data_source` column to track whether a row came from a scraper (`portal_csv`) or a manual Excel upload (`excel`)
- `imported_at` timestamp for audit trail

### `daily_sales`

329,401 rows — the main sales fact table.

| Column | Type | Notes |
|--------|------|-------|
| id | integer PK | |
| portal_id | integer FK → portals | |
| product_id | integer FK → products | |
| sale_date | date | |
| units_sold | numeric | |
| asp | numeric | Average selling price for that day |
| revenue | numeric | `units_sold × asp` |
| data_source | varchar(30) | `excel` or `portal_csv` |
| imported_at | timestamp | |

**UNIQUE:** `(portal_id, product_id, sale_date)` — one row per product per portal per day.

**Duplicate prevention:** Database rejects a second INSERT for the same key with `UniqueViolation` (SQLSTATE 23505). The API returns HTTP 409 Conflict. Use `ON CONFLICT DO NOTHING` or `ON CONFLICT DO UPDATE` in bulk upsert scripts.

**Why it exists:** Primary data source for all revenue, sales velocity, and target-achievement metrics on the dashboard.

---

### `city_daily_sales`

City-level breakdown of sales (currently 0 rows; Blinkit and Zepto can populate this).

| Column | Type | Notes |
|--------|------|-------|
| id | integer PK | |
| portal_id | integer FK → portals | |
| product_id | integer FK → products | |
| city_id | integer FK → cities | |
| sale_date | date | |
| units_sold | numeric | |
| mrp | numeric | Maximum retail price |
| selling_price | numeric | Actual price sold at |
| revenue | numeric | |
| discount_amount | numeric | Default 0 |
| net_revenue | numeric | `revenue - discount_amount` |
| order_count | integer | Number of orders (not just units) |
| data_source | varchar(30) | |
| imported_at | timestamp | |

**UNIQUE:** `(portal_id, product_id, city_id, sale_date)` — one row per product per portal per city per day.

**Indexes:** `(sale_date DESC)`, `(portal_id, city_id, sale_date DESC)`, `(product_id, sale_date DESC)`

**Why it exists:** Granular geography analytics — which city drives the most revenue, city-level stock alignment vs. demand.

---

### `inventory_snapshots`

7,512 rows — daily stock snapshot per product per portal.

| Column | Type | Notes |
|--------|------|-------|
| id | integer PK | |
| portal_id | integer FK → portals | |
| product_id | integer FK → products | |
| snapshot_date | date | |
| portal_stock | numeric | Stock as reported by the portal |
| backend_stock | numeric | Backend/warehouse stock |
| frontend_stock | numeric | Front-of-warehouse / DC stock |
| solara_stock | numeric | Solara's internal stock count |
| amazon_fc_stock | numeric | Amazon fulfilment centre stock (Amazon PI only) |
| open_po | numeric | Units on open purchase order |
| doc | numeric | Days of cover — `stock / avg_daily_sales` |
| imported_at | timestamp | |

**UNIQUE:** `(portal_id, product_id, snapshot_date)` — one snapshot per product per portal per day.

**Indexes:** `(portal_id, snapshot_date DESC)`, `(product_id, snapshot_date DESC)`

**Why it exists:** Tracks stock health over time. `doc` (days of cover) is the key low-stock alert metric.

---

### `monthly_targets`

2,197 rows — sales targets set per product per portal per month.

| Column | Type | Notes |
|--------|------|-------|
| id | integer PK | |
| portal_id | integer FK → portals | |
| product_id | integer FK → products | |
| year | smallint | |
| month | smallint | 1–12 |
| target_units | numeric | Monthly unit target |
| target_revenue | numeric | Monthly revenue target |
| target_drr | numeric | Daily run rate target (target_units / days in month) |
| achievement_pct | numeric | Computed or manually set — actual/target × 100 |

**UNIQUE:** `(portal_id, product_id, year, month)` — one target row per product per portal per month.

**Index:** `(portal_id, year, month)` for filtering by period.

**Why it exists:** Business planning. The dashboard shows actual vs. target with achievement %. Targets are usually set by the ops team in Excel and uploaded manually.

---

### `monthly_ad_spend`

71 rows — advertising spend per portal per month.

| Column | Type | Notes |
|--------|------|-------|
| id | integer PK | |
| portal_id | integer FK → portals | |
| year | smallint | |
| month | smallint | |
| total_revenue | numeric | Total revenue for the month (for TACOS calc) |
| ad_spend | numeric | Total ad spend for the month |
| tacos_pct | numeric | TACOS = `ad_spend / total_revenue × 100` |

**UNIQUE:** `(portal_id, year, month)` — one row per portal per month.

**Why it exists:** TACOS (Total Advertising Cost of Sale) is a key profitability metric. Stored here separately from daily_sales because ad spend is reported monthly and managed manually.

---

## Audit table

### `import_logs`

317 rows — one row per import job (scraper run or manual Excel upload).

| Column | Type | Notes |
|--------|------|-------|
| id | integer PK | |
| source_type | varchar(30) | `'excel_import'` (master Excel via upload API), `'portal_csv'` (portal CSV via upload API), `'portal_scraper'` (automated scraper run), `'excel_upload'` (legacy `/api/imports` endpoint) |
| portal_id | integer FK → portals | Nullable (e.g. bulk uploads) |
| sheet_name | varchar(200) | Excel sheet or CSV file name |
| file_name | varchar(500) | Original file name |
| import_date | date | Business date the data covers |
| start_time | timestamp | When the import began |
| end_time | timestamp | Nullable — set when complete |
| status | varchar(20) | `running`, `success`, `partial`, `failed` |
| records_imported | integer | |
| error_message | text | Nullable — populated on failure |
| created_at | timestamp | |

**Indexes:** `(import_date DESC)`, `(portal_id, import_date DESC)`

**Why it exists:** Full audit trail of every data load. Lets the ops team see which portal was last scraped, when, and if it failed. Also used to debug duplicate import attempts.

---

## Duplicate prevention summary

| Table | Unique key | DB conflict |
|-------|-----------|-------------|
| `daily_sales` | `(portal_id, product_id, sale_date)` | DB raises 23505 |
| `city_daily_sales` | `(portal_id, product_id, city_id, sale_date)` | DB raises 23505 |
| `inventory_snapshots` | `(portal_id, product_id, snapshot_date)` | DB raises 23505 |
| `monthly_targets` | `(portal_id, product_id, year, month)` | DB raises 23505 |
| `monthly_ad_spend` | `(portal_id, year, month)` | DB raises 23505 |
| `portals` | `name` | Single source — rarely inserted |
| `products` | `sku_code` | Single source — rarely inserted |
| `product_portal_mapping` | `(portal_id, portal_sku)` | Single source — rarely inserted |
| `cities` | `(name, state)` | Single source — rarely inserted |
| `product_categories` | `(l1_name, l2_name)` | Single source — rarely inserted |

**Scraper inserts** use `ON CONFLICT DO NOTHING` directly on the DB — no API involved.

**Two upload/import API paths with different duplicate policies:**

| Endpoint | Duplicate policy | Success response |
|----------|-----------------|-----------------|
| `POST /api/imports/sales` | Reject entire batch if **any** duplicate exists | HTTP 201 `{"inserted": N}` |
| `POST /api/imports/inventory` | Reject entire batch if **any** duplicate exists | HTTP 201 `{"inserted": N}` |
| `POST /api/uploads/file` | Skip duplicate rows, insert the rest | HTTP 200 `{"inserted": N, "skipped": M, "errors": [...]}` |

Use `/api/imports/*` when strict all-or-nothing behaviour is required (e.g. scraper pipeline).
Use `/api/uploads/file` for manual file uploads where partial success is preferable to rejecting the whole batch.

The DB-level UNIQUE constraint is a second safety net that catches any duplicates that slip through (e.g. concurrent inserts).

---

## Indexes quick reference

All lookup-heavy columns have indexes. Key performance indexes:

| Index | Purpose |
|-------|---------|
| `idx_daily_sales_portal_date` | Dashboard: filter sales by portal + date range |
| `idx_daily_sales_product_date` | Product detail: sales history for one SKU |
| `idx_daily_sales_date` | Global date range queries |
| `idx_city_sales_portal_city` | City heatmap by portal |
| `idx_inv_portal_date` | Inventory dashboard by portal |
| `idx_inv_product_date` | Low-stock alert queries |
| `idx_targets_portal_period` | Achievement % by portal per month |
| `idx_import_logs_portal` | Last-scraped status per portal |

---

## Schema vs. CLAUDE.md discrepancy

CLAUDE.md documents a 9-table schema (`init_db.sql`). The actual deployed schema has **12 tables** because it evolved:

| Added table | Why |
|-------------|-----|
| `city_daily_sales` | City-level granularity for Blinkit/Zepto |
| `monthly_targets` | Planning/target tracking |
| `monthly_ad_spend` | TACOS metric tracking |

And table names changed:
- `sales_data` → `daily_sales`
- `inventory_data` → `inventory_snapshots`
- `scraping_logs` → `import_logs`

The `init_db.sql` in the repo is outdated. The source of truth is the live local DB schema.
