# Schema — Recommended Additions

**Assessed:** 2026-02-21
**Schema version:** v2 (12 tables)

These are tables and columns not currently in the schema that would add significant analytical value. None are required for the system to function today — they are prioritised by business impact.

---

## Missing Tables

### 1. `product_portal_pricing` — Price History

**Why it matters:** ASP is currently stored on every `daily_sales` row but there is no way to see when prices changed or whether a price cut drove a sales spike. That context is permanently lost.

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

**Enables:**
- Price elasticity analysis ("did the Feb 3rd price drop cause the sales jump?")
- Month-over-month ASP trend per SKU per portal
- Identifying which portals are discounting most aggressively

---

### 2. `portal_fee_structure` — Commission & Fees

**Why it matters:** Revenue is tracked but actual margins are invisible. Each portal takes a different commission. Without this table, "which portal is most profitable per unit?" is unanswerable.

```sql
CREATE TABLE portal_fee_structure (
    portal_id           INTEGER NOT NULL REFERENCES portals(id),
    category_id         INTEGER REFERENCES product_categories(id),
    effective_from      DATE NOT NULL,
    effective_to        DATE,
    commission_pct      NUMERIC(5,2),
    fulfillment_fee     NUMERIC(10,2),  -- flat fee per unit
    payment_gateway_pct NUMERIC(5,2),
    PRIMARY KEY (portal_id, category_id, effective_from)
);
```

**Enables:**
- Net margin per portal after platform fees
- Contribution margin per SKU per portal
- Portal profitability ranking
- Full P&L when combined with `products.cost_price`

---

### 3. `product_rankings` — BSR & Ratings

**Why it matters:** The Amazon ASIN scraper already collects BSR data but it posts to Slack and is never stored. Rankings sitting alongside sales data would let you correlate rank movement directly with sales velocity.

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

**Enables:**
- Rank vs sales correlation over time
- Review velocity tracking (how fast are reviews accumulating?)
- Early warning system when BSR drops sharply
- Connecting the existing ASIN scraper output into the main analytics system

---

### 4. `promotions` — Deals & Campaigns

**Why it matters:** When Zepto sales spike on a particular day, there is currently no way to know if it was organic demand or a deal of the day. Without this context, sales patterns are harder to interpret and impossible to replicate deliberately.

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

**Enables:**
- Baseline vs promotional sales separation
- ROI per campaign ("did this deal of the day generate incremental volume?")
- Promotion calendar planning informed by past performance

---

### 5. `stockout_events` — Lost Revenue Tracking

**Why it matters:** When a product goes out of stock, the `daily_sales` table just shows zero — indistinguishable from zero demand. Every day of stockout is lost revenue that currently has no representation in the data.

```sql
CREATE TABLE stockout_events (
    id                     SERIAL PRIMARY KEY,
    portal_id              INTEGER NOT NULL REFERENCES portals(id),
    product_id             INTEGER NOT NULL REFERENCES products(id),
    stockout_date          DATE NOT NULL,
    restocked_date         DATE,
    estimated_lost_units   NUMERIC(12,2),   -- based on pre-stockout DRR
    estimated_lost_revenue NUMERIC(14,2),
    UNIQUE (portal_id, product_id, stockout_date)
);
```

**Enables:**
- True lost revenue quantification
- Holding inventory and supply chain teams accountable
- Better-calibrated reorder alerts
- Separating "zero sales = no demand" from "zero sales = no stock"

---

### 6. `product_bundles` — Combo SKU Mapping

**Why it matters:** Combo SKUs exist in the Excel (e.g. Amazon Combo sheets) but there is no relationship between a combo SKU and its component products. Combo sales cannot be rolled up into individual SKU performance.

```sql
CREATE TABLE product_bundles (
    bundle_product_id    INTEGER NOT NULL REFERENCES products(id),
    component_product_id INTEGER NOT NULL REFERENCES products(id),
    quantity             NUMERIC(5,2) NOT NULL DEFAULT 1,
    PRIMARY KEY (bundle_product_id, component_product_id)
);
```

**Enables:**
- True per-SKU volume including combo contribution
- Combo vs standalone performance comparison
- Understanding which individual products drive combo attach rates

---

## Missing Columns on Existing Tables

### `products`

| Column | Type | Why |
|--------|------|-----|
| `cost_price` | `NUMERIC(10,2)` | Manufacturing or procurement cost per unit. Without it, gross margin and P&L are completely impossible regardless of how much revenue data exists. Probably the single highest-value missing column in the entire schema. |
| `launch_date` | `DATE` | When was this SKU first listed on any portal? Enables new vs established SKU segmentation and age-of-listing analysis. |
| `is_discontinued` | `BOOLEAN DEFAULT FALSE` | Cleaner than inferring discontinuation from portal mapping inactivity. |

### `product_portal_mapping`

| Column | Type | Why |
|--------|------|-----|
| `listed_date` | `DATE` | When did this SKU go live on this specific portal? Age of listing directly affects expected sales velocity and should inform target-setting. |
| `delisted_date` | `DATE` | When was it removed from this portal? Enables clean active-SKU filtering without relying on the `is_active` flag that is currently never updated. (See SCHEMA_ISSUES.md ISSUE-09.) |
| `min_stock_threshold` | `NUMERIC(12,2)` | Reorder point per SKU per portal. Enables low-stock alerts calibrated per product rather than a global threshold. A fast-moving SKU on Zepto needs a different threshold than a slow mover on Myntra. |

### `daily_sales`

| Column | Type | Why |
|--------|------|-----|
| `return_units` | `NUMERIC(12,2)` | Separates gross units sold from returns instead of encoding returns as negative `units_sold`. Enables clean gross vs net reporting without `WHERE units_sold > 0` guards everywhere. (See SCHEMA_ISSUES.md ISSUE-08.) |

---

## Priority Order

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

## Related Files

- `database/SCHEMA_ISSUES.md` — existing data quality issues and fix SQL
- `docs/schema_forward_looking.md` — tables and columns already in schema but unused
- `database/schema_v2.sql` — current full DDL
