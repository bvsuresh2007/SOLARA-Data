# Scrapers — How They Work

**Last updated:** 2026-02-21

---

## Overview

The scraper service downloads daily sales and inventory reports from each portal and upserts them into PostgreSQL. It runs on a cron schedule (11:00 AM IST) inside the `scrapers` Docker container.

```
orchestrator.py
  └── for each portal scraper:
        scraper.run(report_date)   ← login → download → logout (with retry)
        excel_parser.parse_sales() ← extract rows from the downloaded file
        data_transformer.transform_sales_rows() ← normalise + resolve IDs
        _upsert_sales() / _upsert_inventory() ← ON CONFLICT DO UPDATE
        _log_scrape() ← write to scraping_logs table
  └── notify_scraping_complete() ← Slack summary
```

---

## Running the orchestrator

```bash
# All portals, yesterday's data (default)
python -m scrapers.orchestrator

# Specific date
python -m scrapers.orchestrator --date 2026-02-08
```

Downloaded files land in `data/raw/<portal>/` and are also uploaded to Google Drive at
`SolaraDashboard Reports / YYYY-MM / <Portal> / <filename>`.

---

## Base class — `scrapers/base_scraper.py`

All Playwright-based scrapers extend `BaseScraper`. It provides:

- `_init_browser()` — launches headless Chromium with a standard user-agent
- `_close_browser()` — safe teardown
- `_screenshot(label)` — saves `data/raw/<portal>/error_<label>_<ts>.png` on failure
- `run(report_date)` — full lifecycle with **3 retries** and exponential backoff (2 s, 4 s)

Subclasses must implement three methods:

```python
def login(self) -> None: ...
def download_report(self, report_date: date) -> Path: ...
def logout(self) -> None: ...
```

`run()` returns a result dict: `{"portal", "date", "file", "status", "error"}`.

Shopify is the only portal that does **not** extend `BaseScraper` — it uses the REST API directly.

---

## Portal scrapers

### EasyEcom (`scrapers/easyecom_scraper.py`) — **Working**

| Detail | Value |
|--------|-------|
| URL | `app.easyecom.io` |
| Auth | Persistent Chrome profile + fresh Google OAuth each run |
| Profile dir | `scrapers/sessions/easyecom_profile/` |
| Download format | ZIP → extract CSV |

**Key quirks:**
- PHP session expires in ~24 min — a fresh Google OAuth is required every run. The persistent profile auto-selects the Google account so no credentials are entered manually.
- A "New Features" Angular modal appears on **every page navigation**. Dismiss by dispatching a `MouseEvent('click')` on `button.new-ui-outline-btn` — `page.click()` is unreliable here.
- Date picker is a jQuery Bootstrap daterangepicker on `div#reportrange`. Trigger it → click "Yesterday" in `.daterangepicker .ranges li`. Auto-applies; no Submit needed.
- Report is queued via `window.queueMiniReport()` (direct JS call — the Bootstrap 3 dropdown it belongs to is broken). Server confirms with a browser `alert('Download Job Queued')`.
- Poll `https://app.easyecom.io/V2/reports/import-export-report?jobType=1` until "Download Ended At" (column index 4) is non-empty.
- Download button is `<a class="download_result">` with no `href`. Must click via `dispatchEvent(new MouseEvent('click', {bubbles:true}))` — `page.mouse.click()` does not work (Angular zone.js).

---

### Blinkit (`scrapers/blinkit_scraper.py`) — **Working (selectors need live verification)**

| Detail | Value |
|--------|-------|
| URL | `partnersbiz.com` (env: `BLINKIT_LINK`) |
| Auth | Persistent Chrome profile (OTP-based session) |
| Profile dir | `scrapers/sessions/blinkit_profile/` |

**First-time setup:** Run `auth_blinkit.py` once to complete the OTP login and save the session. After that, the scraper reuses the saved profile without triggering OTP again.

If the session expires, the scraper attempts a full re-auth using `gmail_otp.py` to fetch the OTP from `automation@solara.in`.

---

### Zepto (`scrapers/zepto_scraper.py`) — **Working**

| Detail | Value |
|--------|-------|
| URL | `brands.zepto.co.in` (env: `ZEPTO_LINK`) |
| Auth | Email + password + OTP from Gmail |
| Session file | `scrapers/sessions/zepto_session.json` |

**Login flow:** Email → password → click "Log In" → OTP screen appears → fetch OTP from `mailer@zeptonow.com` via `gmail_otp.py` → enter OTP → confirm. Session is saved to JSON after successful login and restored on the next run; if the saved session is still valid the login step is skipped entirely.

**Report flow:** Navigate to `/vendor/reports` → "Request Report" → select `Sales_F` type → fill date → Submit → reload → find the completed row → click Download.

---

### Swiggy (`scrapers/swiggy_scraper.py`) — **Stub (selectors unverified)**

| Detail | Value |
|--------|-------|
| URL | `vendor.swiggy.com` |
| Auth | Email + password (no OTP) |

Selectors use `data-testid` attributes that need to be verified against the live portal. The login and download flows are structurally correct but will need adjustment after first run.

---

### Amazon (`scrapers/amazon_scraper.py`) — **Stub (selectors unverified)**

| Detail | Value |
|--------|-------|
| URL | `sellercentral.amazon.in` |
| Auth | Email + password (2FA may be required) |

Scrapes daily sales from Seller Central's Report Central. Selectors need live verification. Note: this scraper is for **dashboard sales data** — it is unrelated to the ASIN price/BSR tool at `scrapers/tools/amazon_asin_scraper/`.

---

### Shopify (`scrapers/shopify_scraper.py`) — **Working**

| Detail | Value |
|--------|-------|
| API | Shopify Admin REST API v2024-04 |
| Auth | `SHOPIFY_API_KEY` + `SHOPIFY_API_SECRET` + `SHOPIFY_STORE_URL` |

No browser required. Fetches orders for the target date via the REST API and saves them as CSV. Does not extend `BaseScraper`.

---

## Supporting modules

| File | Purpose |
|------|---------|
| `excel_parser.py` | Portal-specific parsers. `get_parser(portal_name)` returns the right parser. Each parser implements `parse_sales(file)` and optionally `parse_inventory(file)`, returning a list of raw row dicts. |
| `data_transformer.py` | Normalises raw rows: resolves city name aliases (e.g. "BLR" → "Bangalore"), looks up portal/product/warehouse IDs from the DB, and returns DB-ready dicts. |
| `google_drive_upload.py` | `upload_to_drive(portal, report_date, file_path)` — uploads to `SolaraDashboard Reports / YYYY-MM / <Portal> /`. Uses the same OAuth token as Gmail (`token.json` or `GMAIL_TOKEN_JSON` env var). |
| `gmail_otp.py` | Reads the Gmail inbox of `automation@solara.in` to fetch OTP codes sent by portals (Zepto, Blinkit). |

---

## Session storage

```
scrapers/sessions/
  ├── easyecom_profile/   ← Chromium persistent profile (Google OAuth)
  ├── blinkit_profile/    ← Chromium persistent profile (OTP session)
  └── zepto_session.json  ← Playwright storage state (cookies + localStorage)
```

These are gitignored. They must exist on the machine running the scrapers.

---

## Error handling

- **Retries:** BaseScraper retries up to `MAX_RETRY_ATTEMPTS` times (default 3) with exponential backoff.
- **Screenshots:** Saved to `data/raw/<portal>/error_<label>_<timestamp>.png` when `SCREENSHOT_ON_ERROR=true`.
- **Logging:** Each scraper run is recorded in the `scraping_logs` table (`status`, `records_processed`, `error_message`).
- **Slack:** `notify_scraping_complete()` posts a summary after every orchestrator run; `notify_scraping_failure()` is available for individual portal failures.

---

## Adding a new scraper

1. Create `scrapers/newportal_scraper.py` extending `BaseScraper`:
   ```python
   class NewPortalScraper(BaseScraper):
       portal_name = "newportal"

       def login(self) -> None: ...
       def download_report(self, report_date: date) -> Path: ...
       def logout(self) -> None: ...
   ```
2. Add a parser class in `scrapers/excel_parser.py` and register it in the `get_parser()` factory.
3. Add `NewPortalScraper` to the `SCRAPERS` list in `scrapers/orchestrator.py`.
4. Add portal credentials to `.env` and `backend/app/config.py`.
5. Insert a row into the `portals` table.
