# Schema Planning

**Schema version:** v2 (12 tables)
**Last updated:** 2026-02-24

This document consolidates three schema planning concerns into one place:

- **Part 1 — Issues & Backlog:** Live data quality problems and their fix SQL
- **Part 2 — Recommended Additions:** New tables and columns not yet built
- **Part 3 — Forward-Looking Inventory:** Schema elements that exist but carry no meaningful data yet

---

## Part 1 — Issues & Backlog

**Assessed:** 2026-02-20
**Data state at assessment:** 329,401 daily_sales rows, 520 products, 11 months (Apr 2025 – Feb 2026)

All issues were identified through live diagnostic queries against the production database.
None of these block current imports. Pick them up when building dashboard features that depend on them.

---

### Critical

#### ISSUE-01 — TACOS analytics completely broken
**Table:** `monthly_ad_spend`
**Evidence:** `total_revenue = NULL` in all 71 rows. `tacos_pct = NULL` in all 71 rows. Only `ad_spend` has data (56/71 rows populated).
**Root cause:** The importer stores ad_spend from the Excel "Total Ad Spend" row but never resolved `total_revenue` — it tried to read a separate row that the parser didn't capture.
**Impact:** Any TACOS/ad-efficiency dashboard widget returns nothing. TACOS = ad_spend / total_revenue is uncalculable.
**Fix:** Run one UPDATE to populate `total_revenue` from `daily_sales` aggregates, then recompute `tacos_pct`:
```sql
UPDATE monthly_ad_spend mas
SET total_revenue = (
    SELECT ROUND(SUM(ds.revenue), 2)
    FROM daily_sales ds
    WHERE ds.portal_id = mas.portal_id
      AND EXTRACT(YEAR  FROM ds.sale_date) = mas.year
      AND EXTRACT(MONTH FROM ds.sale_date) = mas.month
),
tacos_pct = ROUND(
    mas.ad_spend / NULLIF((
        SELECT SUM(ds.revenue) FROM daily_sales ds
        WHERE ds.portal_id = mas.portal_id
          AND EXTRACT(YEAR  FROM ds.sale_date) = mas.year
          AND EXTRACT(MONTH FROM ds.sale_date) = mas.month
    ), 0) * 100, 4)
WHERE mas.ad_spend IS NOT NULL;
```

---

### High

#### ISSUE-02 — Flipkart April 2025 ASP = ₹1 (data import error)
**Table:** `daily_sales`
**Evidence:** Multiple Flipkart rows dated `2025-04-01` have `asp = 1.00`. Real ASPs for these SKUs are ₹1,399–₹2,499. Revenue is stored as `units × ₹1` instead of `units × ₹1,500+`.
**Root cause:** Flipkart April 2025 had fewer columns than later months (no DOC/MTD DRR columns). The ASP column position was misread — the importer picked up the wrong column for that sheet variant.
**Impact:** Revenue figures for Flipkart April 2025 are significantly understated.
**Fix:**
```sql
-- Inspect damage first
SELECT COUNT(*), SUM(units_sold) FROM daily_sales ds
JOIN portals por ON por.id = ds.portal_id
WHERE por.name = 'flipkart' AND ds.asp < 10 AND ds.units_sold > 0;

-- Null out the bad values (revenue becomes NULL, not wrong)
UPDATE daily_sales SET asp = NULL, revenue = NULL
WHERE portal_id = (SELECT id FROM portals WHERE name = 'flipkart')
  AND asp < 10
  AND sale_date < '2025-05-01';
```
Long-term fix: correct the column position detection in `scripts/excel_reader.py` for Flipkart April 2025 and re-import that sheet.

---

#### ISSUE-03 — 6 bumper accessory SKUs have wrong `default_asp`
**Table:** `products`
**Evidence:** `SOL-INS-WB-BMP-101` through `BMP-203` have `default_asp = 125.00` but actual average selling price across all portals is `₹244.81` — 96% higher.
**Affected SKUs:** SOL-INS-WB-BMP-101 through SOL-INS-WB-BMP-203 (6 SKUs)

**Fix:**
```sql
UPDATE products SET default_asp = 245 WHERE sku_code LIKE 'SOL-INS-WB-BMP-%';
```

---

#### ISSUE-04 — Myntra inventory data is 82% empty
**Table:** `inventory_snapshots`
**Evidence:** Of 11 monthly snapshots for Myntra, only May 2025 and September 2025 have `portal_stock` populated (346 rows). 1,365 of 1,711 Myntra inventory rows have `portal_stock = NULL`.
**Root cause:** Myntra's Excel sheets only occasionally include the inventory column with actual values.
**Fix options:**
1. Accept it as a source data limitation — display "N/A" for Myntra inventory in months without data.
2. Add a `data_confidence` flag to `inventory_snapshots` (`'complete' | 'partial' | 'missing'`) so the dashboard can show a data-quality warning.

---

### Medium

#### ISSUE-05 — Three tables are completely empty (25% of schema is dormant)
**Tables:** `cities`, `warehouses`, `city_daily_sales`
**Evidence:** All three have 0 rows.
**Context:** These tables were designed for city-level sales analysis (portal CSV exports → city breakdowns). The CSV scraper pipeline was never wired up to populate them.
**Decision needed:** Decide whether to implement city-level scraping in the near term or defer it. If deferred beyond 6 months, consider whether these tables should remain or be removed to reduce schema complexity.

**Update (2026-02-24):** `city_daily_sales` is now populated by the upload API (`POST /api/uploads/file`) for Blinkit, Swiggy, and Zepto CSV uploads. The `cities` and `warehouses` tables remain empty.

---

#### ISSUE-06 — Flat inventory columns will not scale to new storage locations
**Table:** `inventory_snapshots`
**Current structure:** `portal_stock | backend_stock | frontend_stock | solara_stock | amazon_fc_stock` — 5 hard-coded columns.
**Problem:** Adding a new storage location requires an `ALTER TABLE`.
**Better design — child table for positions:**
```sql
CREATE TABLE inventory_positions (
    snapshot_id  INTEGER REFERENCES inventory_snapshots(id) ON DELETE CASCADE,
    location     VARCHAR(50) NOT NULL,
    units        NUMERIC(12, 2),
    PRIMARY KEY (snapshot_id, location)
);
```
**When to act:** When a new portal or warehouse type is onboarded that doesn't fit the existing 5 columns.

---

#### ISSUE-07 — ASP stored redundantly on 329,401 rows instead of ~6,000
**Table:** `daily_sales`
**Evidence:** ASP has zero intra-month variation — it is a monthly constant per portal+SKU, yet it is stored on every daily row (~31× repetition).
**Better design:**
```sql
CREATE TABLE product_portal_pricing (
    portal_id   INTEGER NOT NULL REFERENCES portals(id),
    product_id  INTEGER NOT NULL REFERENCES products(id),
    year        SMALLINT NOT NULL,
    month       SMALLINT NOT NULL,
    asp         NUMERIC(10, 2),
    PRIMARY KEY (portal_id, product_id, year, month)
);
```
**When to act:** When building a pricing history or price-change analysis feature.

---

#### ISSUE-08 — Returns mixed into `units_sold`, no clean gross vs net split
**Table:** `daily_sales`
**Evidence:** 36 rows have negative `units_sold` (35 Shopify, 1 Amazon). Indistinguishable from sales without `WHERE units_sold > 0`.
**Better design:**
```sql
ALTER TABLE daily_sales ADD COLUMN gross_units  NUMERIC(12, 2) NOT NULL DEFAULT 0;
ALTER TABLE daily_sales ADD COLUMN return_units NUMERIC(12, 2) NOT NULL DEFAULT 0;
```
**When to act:** When returns become significant or gross vs net reporting is needed.

---

### Low

#### ISSUE-09 — No product lifecycle tracking (207 dead SKUs appear active)
**Tables:** `product_portal_mapping`, `products`
**Evidence:** `is_active = TRUE` for all 1,300 portal mapping rows — never set to FALSE. 207 of 520 SKUs (40%) have zero sales in the last 90 days.
**Fix:**
```sql
ALTER TABLE product_portal_mapping ADD COLUMN listed_date   DATE;
ALTER TABLE product_portal_mapping ADD COLUMN delisted_date DATE;
```
**When to act:** When building active-SKU filtering or doing catalogue hygiene.

---

#### ISSUE-10 — Scraper data will conflict with Excel data (future risk)
**Table:** `daily_sales`
**Evidence:** All 329,401 rows currently have `data_source = 'excel'`. When portal scrapers start running, they will write to the same table via `ON CONFLICT DO UPDATE`, silently overwriting Excel values.
**Fix options:**
1. Let scraper data always win — but log the overwrite in `import_logs`.
2. Add `excel_units` and `scraper_units` as separate columns and surface discrepancies.
3. Minimum viable fix: store the previous value in `import_logs.error_message` when a conflict occurs.

**When to act:** Before the portal scrapers are activated for production use.

---

### Informational (no action needed)

- **INFO-01:** `unit_type` column always `'pieces'` — leave as-is, designed for future expansion.
- **INFO-02:** `portals.updated_at` never populated — not a problem; portal records rarely change.
- **INFO-03:** `product_categories` L1 is always `'Kitchen & Dining'` — L2 breakdown is meaningful; L1 filtering is pointless now but correct structure for multi-category expansion.
- **INFO-04:** Shopify has no inventory snapshots — expected; Shopify is fulfilled from Solara WH or Amazon FC.

---

### Fix Priority Order

| Order | Issue | Time to Fix | Unblocks |
|-------|-------|-------------|----------|
| 1 | ISSUE-01: TACOS NULL | 5 min (1 SQL) | Ad spend / TACOS dashboard |
| 2 | ISSUE-02: Flipkart Apr-25 ASP=1 | 5 min (1 SQL) | Correct revenue for Apr-25 |
| 3 | ISSUE-03: Bumper ASP wrong | 2 min (1 SQL) | Revenue fallback accuracy |
| 4 | ISSUE-09: Lifecycle tracking | 1 hr (2 ALTER + importer update) | Active SKU filtering |
| 5 | ISSUE-04: Myntra inventory | Depends on source data | Myntra stock dashboard |
| 6 | ISSUE-08: Gross vs net units | 2 hrs (2 ALTER + importer) | Clean returns reporting |
| 7 | ISSUE-05: Populate cities/warehouses | Day+ (scraper work) | City-level analysis |
| 8 | ISSUE-07: ASP pricing table | Half day (migration) | Price history feature |
| 9 | ISSUE-06: Inventory positions | Half day (migration) | New storage locations |
| 10 | ISSUE-10: Scraper conflict strategy | 1 hr (design + code) | Before scrapers go live |

---

## Part 2 — Recommended Additions

**Assessed:** 2026-02-21

These are tables and columns not currently in the schema that would add significant analytical value. None are required for the system to function today.

---

### Missing Tables

#### 1. `product_portal_pricing` — Price History

**Why it matters:** ASP is currently stored on every `daily_sales` row but there is no way to see when prices changed or whether a price cut drove a sales spike.

```sql
CREATE TABLE product_portal_pricing (
    portal_id      INTEGER NOT NULL REFERENCES portals(id),
    product_id     INTEGER NOT NULL REFERENCES products(id),
    effective_from DATE NOT NULL,
    effective_to   DATE,           -- NULL = currently active price
    mrp            NUMERIC(10,2),
    asp            NUMERIC(10,2),
    discount_pct   NUMERIC(5,2),
    PRIMARY KEY (portal_id, product_id, effective_from)
);
```

**Enables:** Price elasticity analysis, month-over-month ASP trend, identifying which portals discount most aggressively.

---

#### 2. `portal_fee_structure` — Commission & Fees

**Why it matters:** Revenue is tracked but actual margins are invisible.

```sql
CREATE TABLE portal_fee_structure (
    portal_id           INTEGER NOT NULL REFERENCES portals(id),
    category_id         INTEGER REFERENCES product_categories(id),
    effective_from      DATE NOT NULL,
    effective_to        DATE,
    commission_pct      NUMERIC(5,2),
    fulfillment_fee     NUMERIC(10,2),
    payment_gateway_pct NUMERIC(5,2),
    PRIMARY KEY (portal_id, category_id, effective_from)
);
```

**Enables:** Net margin per portal, contribution margin per SKU, portal profitability ranking, full P&L when combined with `products.cost_price`.

---

#### 3. `product_rankings` — BSR & Ratings

**Why it matters:** The Amazon ASIN scraper already collects BSR data but never stores it. Rankings alongside sales data would let you correlate rank movement with sales velocity.

```sql
CREATE TABLE product_rankings (
    portal_id         INTEGER NOT NULL REFERENCES portals(id),
    product_id        INTEGER NOT NULL REFERENCES products(id),
    rank_date         DATE NOT NULL,
    category_rank     INTEGER,
    sub_category_rank INTEGER,
    category_name     VARCHAR(200),
    rating            NUMERIC(3,1),
    review_count      INTEGER,
    PRIMARY KEY (portal_id, product_id, rank_date)
);
```

**Enables:** Rank vs sales correlation, review velocity tracking, early warning when BSR drops sharply, connecting ASIN scraper output into the main analytics system.

---

#### 4. `promotions` — Deals & Campaigns

**Why it matters:** When Zepto sales spike, there is no way to know if it was organic demand or a deal of the day.

```sql
CREATE TABLE promotions (
    id           SERIAL PRIMARY KEY,
    portal_id    INTEGER NOT NULL REFERENCES portals(id),
    product_id   INTEGER REFERENCES products(id),  -- NULL = portal-wide deal
    promo_name   VARCHAR(200),
    promo_type   VARCHAR(50),   -- 'deal_of_day', 'flash_sale', 'coupon', 'combo'
    start_date   DATE NOT NULL,
    end_date     DATE NOT NULL,
    discount_pct NUMERIC(5,2),
    notes        TEXT
);
```

**Enables:** Baseline vs promotional sales separation, ROI per campaign, promotion calendar planning.

---

#### 5. `stockout_events` — Lost Revenue Tracking

**Why it matters:** When a product goes out of stock, `daily_sales` just shows zero — indistinguishable from zero demand.

```sql
CREATE TABLE stockout_events (
    id                     SERIAL PRIMARY KEY,
    portal_id              INTEGER NOT NULL REFERENCES portals(id),
    product_id             INTEGER NOT NULL REFERENCES products(id),
    stockout_date          DATE NOT NULL,
    restocked_date         DATE,
    estimated_lost_units   NUMERIC(12,2),
    estimated_lost_revenue NUMERIC(14,2),
    UNIQUE (portal_id, product_id, stockout_date)
);
```

**Enables:** True lost revenue quantification, supply chain accountability, better-calibrated reorder alerts.

---

#### 6. `product_bundles` — Combo SKU Mapping

**Why it matters:** Combo SKUs exist in the Excel but there is no relationship between a combo SKU and its components. Combo sales cannot be rolled up into individual SKU performance.

```sql
CREATE TABLE product_bundles (
    bundle_product_id    INTEGER NOT NULL REFERENCES products(id),
    component_product_id INTEGER NOT NULL REFERENCES products(id),
    quantity             NUMERIC(5,2) NOT NULL DEFAULT 1,
    PRIMARY KEY (bundle_product_id, component_product_id)
);
```

---

### Missing Columns on Existing Tables

#### `products`

| Column | Type | Why |
|--------|------|-----|
| `cost_price` | `NUMERIC(10,2)` | Manufacturing or procurement cost per unit. Without it, gross margin and P&L are impossible. Highest-value missing column in the schema. |
| `launch_date` | `DATE` | When was this SKU first listed on any portal? Enables new vs established SKU segmentation. |
| `is_discontinued` | `BOOLEAN DEFAULT FALSE` | Cleaner than inferring discontinuation from portal mapping inactivity. |

#### `product_portal_mapping`

| Column | Type | Why |
|--------|------|-----|
| `listed_date` | `DATE` | When did this SKU go live on this portal? Age of listing informs target-setting. |
| `delisted_date` | `DATE` | When was it removed? Enables clean active-SKU filtering. (See ISSUE-09.) |
| `min_stock_threshold` | `NUMERIC(12,2)` | Reorder point per SKU per portal — calibrates low-stock alerts per product rather than a global threshold. |

#### `daily_sales`

| Column | Type | Why |
|--------|------|-----|
| `return_units` | `NUMERIC(12,2)` | Separates gross units from returns instead of encoding returns as negative `units_sold`. (See ISSUE-08.) |

---

### Priority Order

| Priority | Addition | Unlocks |
|----------|----------|---------|
| 1 | `products.cost_price` | Gross margin, P&L per portal and SKU |
| 2 | `portal_fee_structure` | Net margin after platform fees |
| 3 | `product_portal_pricing` | Price change impact on sales |
| 4 | `product_rankings` | Rank ↔ sales correlation (data already being scraped) |
| 5 | `promotions` | Baseline vs promotional sales separation |
| 6 | `stockout_events` | Lost revenue quantification |
| 7 | `product_portal_mapping` lifecycle columns | Clean active SKU lists and listing age |
| 8 | `product_bundles` | Combo SKU roll-up into component performance |

---

## Part 3 — Forward-Looking Inventory

**Assessed:** 2026-02-21

These are schema elements that already exist but carry no meaningful data. None block current operations.

---

### Entire Tables That Are Forward-Looking

| Table | Designed For | Why Empty |
|-------|-------------|-----------|
| `warehouses` | Physical warehouse registry — name, code, portal, city | No source data exists. `inventory_snapshots` uses flat columns instead of a `warehouse_id` FK. Will become relevant when adding a new 3PL, second FC, or regional hub. |
| `city_daily_sales` | City-level daily sales from portal CSV exports | Now partially populated via the upload API (Blinkit/Swiggy/Zepto CSV uploads). Scrapers do not yet write to it directly. |

---

### Forward-Looking Columns Inside Active Tables

#### `portals`
| Column | Current State | Purpose |
|--------|--------------|---------|
| `updated_at` | Always NULL | Audit timestamp for when a portal record is edited |
| `is_active` | Always TRUE | Flag for deactivating a portal (e.g. if Solara stops selling on a platform) |

#### `cities`
| Column | Current State | Purpose |
|--------|--------------|---------|
| `state` | NULL for all 75 cities | Enables state-level filtering — needs manual population or an external geodata source |

#### `product_categories`
| Column | Current State | Purpose |
|--------|--------------|---------|
| `l1_name` | Always `'Kitchen & Dining'` | Supports multi-category expansion when Solara enters new product lines |

#### `products`
| Column | Current State | Purpose |
|--------|--------------|---------|
| `unit_type` | Always `'pieces'` | Designed for products sold by weight or volume — not needed for current catalogue |
| `updated_at` | Never populated | Audit timestamp — not written by the importer |

#### `product_portal_mapping`
| Column | Current State | Purpose |
|--------|--------------|---------|
| `is_active` | Always TRUE for all 1,300 rows | Lifecycle tracking — should be set to FALSE when a SKU is delisted. (See ISSUE-09.) |
| `portal_product_name` | NULL for all rows | The portal's own listing title; the importer stored only `portal_sku`, not the name |
| `updated_at` | Never populated | Audit timestamp |

#### `daily_sales`
| Column | Current State | Purpose |
|--------|--------------|---------|
| `data_source` | Was always `'excel'`; now also `'portal_csv'`, `'master_excel'` from upload API | Distinguishes import origin. Becomes fully meaningful when automated scrapers go live. |

#### `monthly_ad_spend`
| Column | Current State | Purpose |
|--------|--------------|---------|
| `total_revenue` | NULL for all 71 rows | Needed to compute TACOS. Fix: see ISSUE-01. |
| `tacos_pct` | NULL for all 71 rows | TACOS % = `ad_spend / total_revenue × 100`. Blocked by `total_revenue` being NULL. |

---

### Summary

| Category | Count |
|----------|-------|
| Forward-looking entire tables | 2 (`warehouses`, `city_daily_sales`) |
| Columns always stuck at one value | 4 (`unit_type`, `l1_name`, `data_source`, `is_active` × 2 tables) |
| Columns never populated by importer | 5 (`updated_at` × 3, `portal_product_name`, `total_revenue`, `tacos_pct`) |
| Columns needing external data | 1 (`cities.state`) |

---

## Related Files

- `database/schema_v2.sql` — full DDL
- `database/pgadmin_queries.sql` — diagnostic queries used to produce the assessments above
- `docs/database.md` — table-by-table reference with column descriptions
- `shared/constants.py` — `CITY_NAME_MAP`, `CITY_REGION_MAP` for normalisation
