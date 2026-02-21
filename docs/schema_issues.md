# Database Schema Issues & Improvement Backlog

**Assessed:** 2026-02-20
**Schema version:** v2 (12 tables)
**Data state at assessment:** 329,401 daily_sales rows, 520 products, 11 months (Apr 2025 – Feb 2026)

All issues were identified through live diagnostic queries against the production database.
None of these block current imports. Pick them up when building dashboard features that depend on them.

---

## Critical

### ISSUE-01 — TACOS analytics completely broken
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

## High

### ISSUE-02 — Flipkart April 2025 ASP = ₹1 (data import error)
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

### ISSUE-03 — 6 bumper accessory SKUs have wrong `default_asp`
**Table:** `products`
**Evidence:** `SOL-INS-WB-BMP-101` through `BMP-203` have `default_asp = 125.00` but actual average selling price across all portals is `₹244.81` — 96% higher. `default_asp` is used as a revenue fallback when a daily_sales row has no ASP.
**Affected SKUs:**
- SOL-INS-WB-BMP-101 — Bumper Black (small)
- SOL-INS-WB-BMP-102 — Straw 2L
- SOL-INS-WB-BMP-103 — Bumper Blue (small)
- SOL-INS-WB-BMP-201 — Bumper Black (large)
- SOL-INS-WB-BMP-202 — Bumper Pink (large)
- SOL-INS-WB-BMP-203 — Bumper Blue (large)

**Fix:**
```sql
UPDATE products SET default_asp = 245 WHERE sku_code LIKE 'SOL-INS-WB-BMP-%';
```

---

### ISSUE-04 — Myntra inventory data is 82% empty
**Table:** `inventory_snapshots`
**Evidence:** Of 11 monthly snapshots for Myntra, only May 2025 and September 2025 have `portal_stock` populated (346 rows). The other 9 months have 0 stock data. 1,365 of 1,711 Myntra inventory rows have `portal_stock = NULL`.
**Root cause:** Myntra's Excel sheets only occasionally include the inventory column with actual values. It is frequently blank in the source data.
**Impact:** Myntra stock levels and DOC cannot be shown on the inventory dashboard for most months.
**Fix options:**
1. Accept it as a source data limitation — display "N/A" for Myntra inventory in months without data.
2. Add a `data_confidence` flag to `inventory_snapshots` (`'complete' | 'partial' | 'missing'`) so the dashboard can show a data-quality warning.

---

## Medium

### ISSUE-05 — Three tables are completely empty (25% of schema is dormant)
**Tables:** `cities`, `warehouses`, `city_daily_sales`
**Evidence:** All three have 0 rows.
**Context:** These tables were designed for city-level sales analysis (portal CSV exports → city breakdowns). The CSV scraper pipeline was never wired up to populate them.
**Impact:** No city-level filtering, regional analysis, or GMV vs net revenue breakdown is possible yet.
**Decision needed:** Decide whether to implement city-level scraping in the near term or defer it. If deferred beyond 6 months, consider whether these tables should remain or be removed to reduce schema complexity.

---

### ISSUE-06 — Flat inventory columns will not scale to new storage locations
**Table:** `inventory_snapshots`
**Current structure:** `portal_stock | backend_stock | frontend_stock | solara_stock | amazon_fc_stock` — 5 hard-coded columns, one per storage concept.
**Problem:** Adding a new storage location (3PL warehouse, new FC, additional Blinkit region) requires an `ALTER TABLE`. Also, querying "total stock across all locations" requires knowing all column names upfront.
**Better design — child table for positions:**
```sql
CREATE TABLE inventory_positions (
    snapshot_id  INTEGER REFERENCES inventory_snapshots(id) ON DELETE CASCADE,
    location     VARCHAR(50) NOT NULL,
    -- e.g. 'portal_wh', 'backend', 'frontend', 'solara_wh', 'amazon_fc'
    units        NUMERIC(12, 2),
    PRIMARY KEY (snapshot_id, location)
);
```
New locations can be added with no schema change — just a new `location` string value.
**When to act:** When a new portal or warehouse type is onboarded that doesn't fit the existing 5 columns.

---

### ISSUE-07 — ASP stored redundantly on 329,401 rows instead of ~6,000
**Table:** `daily_sales`
**Evidence:** ASP has zero intra-month variation (confirmed by diagnostic query — no SKU+portal+month combination has more than 1 distinct ASP value within the same month). ASP is a monthly constant per portal+SKU, yet it is stored on every daily row, repeating the same value ~31 times per month per SKU.
**Impact:** ~323K redundant ASP values stored. More importantly, if ASP needs correction for a month, you must update ~31 rows instead of 1.
**Better design — dedicated pricing table:**
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
Then `daily_sales` drops `asp`, and `revenue = units × lookup(pricing)`.
**Benefit:** Price history is clean, queryable, and correctable. One source of truth for pricing.
**When to act:** When building a pricing history or price-change analysis feature.

---

### ISSUE-08 — Returns mixed into `units_sold`, no clean gross vs net split
**Table:** `daily_sales`
**Evidence:** 36 rows have negative `units_sold` (35 Shopify, 1 Amazon). These are returns/reversals recorded in the Excel. They are indistinguishable from sales in a `SUM(units_sold)` query unless filtered with `WHERE units_sold > 0`.
**Impact:** Any query that forgets the `> 0` filter silently includes returns in gross sales figures. Reporting gross vs net sales requires awkward `CASE WHEN` expressions.
**Better design:**
```sql
ALTER TABLE daily_sales ADD COLUMN gross_units  NUMERIC(12, 2) NOT NULL DEFAULT 0;
ALTER TABLE daily_sales ADD COLUMN return_units NUMERIC(12, 2) NOT NULL DEFAULT 0;
-- units_sold remains as gross_units - return_units for backward compatibility
```
**When to act:** When returns become significant in volume or when gross vs net reporting is needed.

---

## Low

### ISSUE-09 — No product lifecycle tracking (207 dead SKUs appear active)
**Tables:** `product_portal_mapping`, `products`
**Evidence:** `is_active = TRUE` for all 1,300 portal mapping rows — it has never been set to FALSE. 207 of 520 SKUs (40%) have zero sales in the last 90 days but appear fully active with no flag.
**Impact:** Dashboard "active SKU count" is inflated. Inventory alerts include discontinued products. No way to know when a product was first listed or removed from a portal.
**Fix:** Add lifecycle dates to the mapping table:
```sql
ALTER TABLE product_portal_mapping ADD COLUMN listed_date   DATE;
ALTER TABLE product_portal_mapping ADD COLUMN delisted_date DATE;
```
Set `is_active = FALSE` and `delisted_date = CURRENT_DATE` when a product stops appearing in monthly Excel sheets.
**When to act:** When building active-SKU filtering for dashboards or when doing catalogue hygiene.

---

### ISSUE-10 — Scraper data will conflict with Excel data (future risk)
**Table:** `daily_sales`
**Evidence:** All 329,401 rows currently have `data_source = 'excel'`. When portal scrapers start running (Zepto, Blinkit daily scrapes), they will write to the same table for the same `(portal_id, product_id, sale_date)` rows via `ON CONFLICT DO UPDATE`, silently overwriting Excel values.
**Problem:** There is no rule for which source wins. If the scraper data for a day differs from the Excel, the original Excel value is lost permanently with no audit trail.
**Fix options:**
1. Let scraper data always win (fresher, more granular) — but log the overwrite in `import_logs`.
2. Add `excel_units` and `scraper_units` as separate columns and surface discrepancies.
3. Minimum viable fix: store the previous value in `import_logs.error_message` when a conflict occurs.

**When to act:** Before the portal scrapers are activated for production use.

---

## Informational (no action needed)

### INFO-01 — `unit_type` column always 'pieces'
**Table:** `products`
All 520 products have `unit_type = 'pieces'`. The column exists for future use (e.g., products sold by weight or volume) but currently adds no value. Leave as-is.

### INFO-02 — `portals.updated_at` never populated
**Table:** `portals`
The `updated_at` column on the portals table is always NULL. Since portal records rarely change, this is not a problem. Populate it if portal metadata is ever edited.

### INFO-03 — `product_categories` L1 is always 'Kitchen & Dining'
**Table:** `product_categories`
All 520 products share the same L1 category. The L2 breakdown (Air Fryer, Water Bottles, etc.) is meaningful. L1 filtering in dashboards is currently pointless but the structure is correct for when Solara expands into other product lines.

### INFO-04 — Shopify has no inventory snapshots
**Table:** `inventory_snapshots`
Expected — Shopify is a direct-to-consumer storefront, not a warehouse-holding portal. Stock on Shopify is fulfilled from Solara WH or Amazon FC, which are already tracked under those portals.

---

## Fix Priority Order (when you're ready)

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
