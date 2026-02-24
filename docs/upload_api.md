# Upload API — Developer Guide

**Base path:** `/api/uploads`
**Added:** 2026-02-24

---

## Overview

The upload API lets users push portal CSV exports or the master Excel workbook directly into the database — without re-running scrapers. Unlike the older `/api/imports` endpoints (which reject the entire batch if any duplicate exists), this API always returns HTTP 200 with counts of what was inserted and what was skipped.

---

## Endpoints

### GET `/api/uploads/types`

Returns the list of all supported file types. Use this to populate the dropdown in the UI.

**Response:** `200 OK`

```json
[
  {
    "value": "blinkit_sales",
    "label": "Blinkit Sales CSV",
    "description": "Blinkit portal daily sales export with item_id, date, quantity, city columns",
    "target_tables": ["city_daily_sales", "daily_sales"]
  },
  ...
]
```

---

### POST `/api/uploads/file`

Upload and ingest a portal CSV or master Excel file.

**Query param:** `file_type` (required) — one of the `value` strings from `/types`
**Body:** `multipart/form-data`, field name `file`

**Response:** `200 OK` — always, even if nothing was inserted

```json
{
  "file_type": "blinkit_sales",
  "file_name": "blinkit sales data.csv",
  "rows_parsed": 300,
  "inserted": 150,
  "skipped": 150,
  "errors": [
    { "row": 42, "reason": "SKU 'BLK-99999' not mapped for portal 'blinkit'" }
  ],
  "import_log_id": 17
}
```

**Response:** `422 Unprocessable Entity` — if the file cannot be parsed at all (wrong format, missing columns)

```json
{
  "detail": {
    "message": "The uploaded file does not match the expected format for 'blinkit_sales'. It may be a different version of the export.",
    "missing_columns": ["item_id", "date"],
    "columns_found_in_file": ["Item ID", "Sale Date", "Qty", "City"]
  }
}
```

---

## Supported File Types

| `file_type` | Target tables | Key columns |
|---|---|---|
| `master_excel` | `daily_sales` | SOL- sku_code in each sheet, date columns |
| `blinkit_sales` | `city_daily_sales`, `daily_sales` | `item_id`, `date` (YYYY-MM-DD), `city`, `quantity`, `mrp` |
| `blinkit_inventory` | `inventory_snapshots` | `item_id`, `date`, `backend_inv_qty`, `frontend_inv_qty` |
| `swiggy_sales` | `city_daily_sales`, `daily_sales` | `ITEM_CODE`, `date` (YYYY-MM-DD), `GMV`, `area_name` |
| `swiggy_inventory` | `inventory_snapshots` | `ITEM_CODE`, `date`, `backend_inv_qty`, `frontend_inv_qty` |
| `zepto_sales` | `city_daily_sales`, `daily_sales` | `SKU Number`, `Date` (DD-MM-YYYY), `Units`, `GMV`, `City` |
| `zepto_inventory` | `inventory_snapshots` | `SKU Number`, `Date` (DD-MM-YYYY), `Units`, `City` |
| `amazon_pi` | `daily_sales` | `ASIN`, date columns (YYYY-MM-DD as column headers) |
| `shopify_sales` | `daily_sales` | `Lineitem sku`, `Created at` (ISO), `Lineitem quantity`, `Subtotal` |

---

## Column Mismatch Errors

If the uploaded file has **renamed or missing columns**, the API returns **HTTP 422** immediately with a clear message showing:
- Which columns are expected but missing
- Which columns were actually found in the file

This happens before any data is inserted, so the database is never partially modified.

**Common causes:**
- The portal changed their export format (column renamed)
- Wrong file type selected in the dropdown (e.g., uploading an inventory file as a sales type)
- File opened and re-saved in Excel (may alter column headers)

---

## Duplicate Handling

| Scenario | Behavior |
|---|---|
| Upload file with 30 days, 15 already in DB | `inserted: 15, skipped: 15` |
| Upload file with all new dates | `inserted: 30, skipped: 0` |
| Upload same file twice | `inserted: 0, skipped: 30` |
| Upload file with unmapped SKUs | errors[] contains unmapped rows; valid rows still inserted |
| Entirely duplicate file | HTTP 200, `inserted: 0, skipped: N` |

The `skipped` count means the row already existed — it was not overwritten.

---

## Understanding the Response

| Field | Meaning |
|---|---|
| `rows_parsed` | Total rows read from the file |
| `inserted` | Rows actually written to the DB |
| `skipped` | Rows that already existed (duplicates) |
| `errors` | Rows skipped due to unmapped SKUs, bad dates, or missing portals |
| `import_log_id` | ID in `import_logs` table for audit trail (null if nothing was inserted) |

`rows_parsed = inserted + skipped + len(errors)` (approximately — `skipped` tracks at the daily_sales grain after aggregation for city-level files)

---

## How Portal CSV Sales Are Processed

For `blinkit_sales`, `swiggy_sales`, `zepto_sales`:

1. Each CSV row → `city_daily_sales` (city-level grain)
2. After inserting city rows, they are **aggregated** to `(portal, product, date)` and inserted into `daily_sales`

For `amazon_pi`, `shopify_sales`:

- Inserted directly into `daily_sales` (no city breakdown)

---

## SKU Mapping

**Portal CSV files** (`blinkit_*`, `swiggy_*`, `zepto_*`, `amazon_pi`, `shopify_*`):
- The portal SKU (`item_id`, `ITEM_CODE`, `SKU Number`, `ASIN`, `Lineitem sku`) must exist in the `product_portal_mapping` table
- If not mapped: that row goes to `errors[]`, the rest are still inserted

**Master Excel** (`master_excel`):
- Uses the `SOL-XXXX` sku_code column directly from the workbook
- Looks up via the `products` table (`sku_code` field) — does not use `product_portal_mapping`
- Unmapped SOL- codes go to `errors[]`

---

## Frontend Integration

```typescript
// GET supported types
const types = await fetch('/api/uploads/types').then(r => r.json())

// POST a file
const form = new FormData()
form.append('file', file)
const result = await fetch(`/api/uploads/file?file_type=${selectedType}`, {
  method: 'POST',
  body: form,
}).then(r => r.json())

if (result.inserted === 0 && result.skipped > 0) {
  // All rows were duplicates — show info, not error
}
if (result.errors.length > 0) {
  // Some SKUs are not mapped — show warning with error details
}
```

---

## Audit Trail

Every successful insert writes an `ImportLog` row to `import_logs`:
- `source_type`: `"portal_csv"` or `"excel_import"`
- `file_name`: original filename
- `import_date`: earliest sale date in the batch
- `records_imported`: number of rows inserted
- `status`: `"success"`

Failed parses do not write a log entry.

---

## Status

| Endpoint | Status |
|---|---|
| `GET /api/uploads/types` | Complete |
| `POST /api/uploads/file` (blinkit_sales) | Complete |
| `POST /api/uploads/file` (blinkit_inventory) | Complete |
| `POST /api/uploads/file` (swiggy_sales) | Complete |
| `POST /api/uploads/file` (swiggy_inventory) | Complete |
| `POST /api/uploads/file` (zepto_sales) | Complete |
| `POST /api/uploads/file` (zepto_inventory) | Complete |
| `POST /api/uploads/file` (amazon_pi) | Complete |
| `POST /api/uploads/file` (shopify_sales) | Complete |
| `POST /api/uploads/file` (master_excel) | Complete — delegates to `scripts/excel_reader.py` |
