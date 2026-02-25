# Scrapers — How They Work

**Last updated:** 2026-02-25

---

## Overview

The scraper service downloads daily sales and inventory reports from each portal and upserts them into PostgreSQL.

**Two execution modes:**

| Mode | Where | Trigger |
|------|--------|---------|
| **Docker cron** | `scrapers` container via `orchestrator.py` | 11:00 AM IST daily (all portals) |
| **GitHub Actions** | `ubuntu-latest` runner | 11 AM–2 PM IST daily (per-portal) |

GitHub Actions workflows (`.github/workflows/scraper-*.yml`) run EasyEcom, Zepto, Amazon PI, Blinkit, and Swiggy individually. They use headless Chromium, sync Chrome profiles via Google Drive (`PROFILE_STORAGE_DRIVE_FOLDER_ID`), and upload downloaded files as run artifacts (7-day retention). Each workflow also supports `workflow_dispatch` for manual runs with an optional custom date.

```
orchestrator.py
  └── for each portal scraper:
        scraper.run(report_date)        ← login → download → logout (with retry)
        excel_parser.parse_sales()      ← extract rows from the downloaded file
        data_transformer.transform_sales_rows() ← normalise + resolve IDs
        _upsert_sales()                 ← city_daily_sales (ON CONFLICT DO UPDATE)
        _upsert_daily_sales()           ← daily_sales aggregated (dashboard reads this)
        _upsert_inventory()             ← inventory_snapshots (if parser supports it)
        _log_scrape()                   ← write to import_logs table
  └── notify_scraping_complete() ← Slack summary
```

### Backfill entry point — `populate_portal_data()`

The CI workflows (and `scripts/populate_db.py`) use `populate_portal_data()` rather than the full `run()` function. It skips the browser scraping step and goes directly to parse → transform → upsert, using files already present in `data/raw/<portal>/`:

```python
from scrapers.orchestrator import populate_portal_data
result = populate_portal_data("blinkit", date(2026, 2, 10))
# result: {"status": "success", "records_imported": 142, "files": [...]}
```

Writes to both `city_daily_sales` and `daily_sales`. Status values: `"success"`, `"failed"`, `"no_parser"`, `"no_file"`.

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

## GitHub Actions secrets required

Add these in **GitHub → Settings → Secrets and variables → Actions**:

| Secret | Used by | Description |
|--------|---------|-------------|
| `POSTGRES_HOST` | all | Supabase host (e.g. `db.xxxx.supabase.co`) |
| `POSTGRES_PORT` | all | `5432` |
| `POSTGRES_DB` | all | `postgres` |
| `POSTGRES_USER` | all | `postgres` |
| `POSTGRES_PASSWORD` | all | Supabase DB password |
| `GOOGLE_TOKEN_JSON` | all | `base64 -w0 token.json` — OAuth token for Drive/Gmail |
| `PROFILE_STORAGE_DRIVE_FOLDER_ID` | all | Drive folder ID for Chrome profile sync |
| `ZEPTO_LINK` | zepto | Login URL |
| `ZEPTO_EMAIL` | zepto | Vendor email |
| `ZEPTO_PASSWORD` | zepto | Vendor password |
| `AMAZON_PI_LINK` | amazon-pi | `https://pi.amazon.in` login URL |
| `AMAZON_PI_EMAIL` | amazon-pi | Seller email |
| `AMAZON_PI_PASSWORD` | amazon-pi | Seller password |
| `AMAZON_PI_TOTP_SECRET` | amazon-pi | Base32 TOTP secret for 2FA |
| `SWIGGY_LINK` | swiggy | Portal URL (`https://partner.swiggy.com/instamart/sales`) |
| `SWIGGY_EMAIL` | swiggy | Vendor email (OTP sent here via Gmail) |

To encode `token.json` for the secret:
```bash
base64 -w0 token.json  # Linux
base64 -i token.json   # macOS
```

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

**Note:** EasyEcom, Blinkit, and Amazon PI override `run()` entirely to use `launch_persistent_context()` and profile sync. They do not use the base retry loop.

---

## Common patterns across all scrapers

These conventions are shared by every scraper. New scrapers should follow them.

### 1. Browser context type

| Scraper | Context type | Why |
|---------|-------------|-----|
| EasyEcom | `launch_persistent_context()` | Google OAuth session must survive restarts |
| Blinkit | `launch_persistent_context()` | OTP-based session; avoids re-auth per run |
| Amazon PI | `launch_persistent_context()` | TOTP 2FA session; avoids re-auth per run |
| Zepto | Regular context + JSON storage state | Lighter; session saved as cookies/localStorage |
| Swiggy | `launch_persistent_context()` | OTP-based session; avoids re-auth per run |
| Shopify | None (HTTP API) | No browser needed |

**Rule of thumb:** use `launch_persistent_context()` when the portal uses OTP or OAuth (session is expensive to obtain). Use JSON storage state or plain context when you have a password you can re-use each run.

### 2. Profile sync (Drive ↔ local)

Scrapers using `launch_persistent_context()` sync their Chrome profile to Google Drive so that CI/headless runs pick up the session that was authenticated interactively.

**Standard pattern** — appears in EasyEcom, Blinkit, Amazon PI:

```python
try:
    from scrapers.profile_sync import download_profile, upload_profile
except ImportError:
    from profile_sync import download_profile, upload_profile

try:
    download_profile("portal_name")   # before _init_browser()
    self._init_browser()
    ...
finally:
    self._close_browser()             # must close before zipping profile
    upload_profile("portal_name")     # after browser is closed
```

- `download_profile` / `upload_profile` are **silent no-ops** when `PROFILE_STORAGE_DRIVE_FOLDER_ID` is not set, so local dev works without Drive access.
- Profile zips exclude `Cache/`, `Code Cache/`, `GPUCache/` etc. — keeps them under ~1 MB.
- Drive folder: **"SolaraDashboard Profiles"** (separate from Reports folder).

### 3. Google Drive report upload

After a file is successfully downloaded, upload it to Drive. Standard call:

```python
drive_link = _upload_to_drive(
    portal="Portal Name",   # display name used as subfolder
    report_date=report_date,
    file_path=file_path,    # Path object
)
```

Folder structure: `SolaraDashboard Reports / YYYY-MM / <Portal> / <filename>`

Import at the top of each scraper file:
```python
try:
    from .google_drive_upload import upload_to_drive as _upload_to_drive
except ImportError:
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location(
        "google_drive_upload", Path(__file__).parent / "google_drive_upload.py"
    )
    try:
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _upload_to_drive = _mod.upload_to_drive
    except Exception:
        _upload_to_drive = None
```

The dual try/except import handles both `python -m scrapers.X` (relative import works) and `python scrapers/X.py` (relative import fails — falls back to direct file load via importlib).

### 4. OTP / MFA handling

| Scraper | MFA type | How fetched |
|---------|----------|-------------|
| Amazon PI | TOTP (HOTP-based, no email) | `scrapers/totp_helper.py` reads `AMAZON_PI_TOTP_SECRET` env var and generates the 6-digit code via `pyotp` |
| EasyEcom | Google OAuth (not OTP) | Persistent Chrome profile auto-selects the Google account — no code entry needed |
| Zepto | Email OTP from `mailer@zeptonow.com` | `scrapers/gmail_otp.py` reads Gmail inbox of `automation@solara.in` |
| Blinkit | Email OTP from `noreply@partnersbiz.com` | `scrapers/gmail_otp.py` — same mechanism as Zepto |
| Swiggy | Email OTP from `no-reply@swiggy.in` | `scrapers/gmail_otp.py` — same mechanism as Zepto/Blinkit |
| Shopify | None | API key |

**Gmail OTP pattern (Zepto / Blinkit / Swiggy):** Record a timestamp before triggering OTP → poll Gmail for the OTP email from the expected sender that arrived after that timestamp → parse the code → fill the OTP input. Retries up to 3–5 times with ~10-second intervals.

### 5. Dual import pattern

Every module-level import of a sibling scraper file uses this guard so the file works both as a module (`python -m scrapers.X`) and standalone (`python scrapers/X.py`):

```python
try:
    from scrapers.some_module import some_function
except ImportError:
    from some_module import some_function
```

### 6. Headless vs. visible mode

- **Standalone** (`python scrapers/X.py` / `if __name__ == "__main__"`) always runs `headless=False` — so you can watch the browser, handle unexpected dialogs, and refresh the session.
- **Orchestrator / CI** always runs `headless=True`.
- `slow_mo` is set to `200` (ms) when `headless=False`, `0` when `headless=True`. This slows actions enough for the human to follow along without making CI slow.

```python
slow_mo=200 if not self.headless else 0
```

### 7. Date default

Every scraper defaults to **yesterday** when no date is supplied:

```python
if report_date is None:
    report_date = date.today() - timedelta(days=1)
```

### 8. Windows-safe date formatting

`%-d` (day without leading zero) is Linux-only and crashes on Windows. Use this pattern instead:

```python
# Wrong on Windows:
report_date.strftime("%-d %b %Y")   # "8 Feb 2026"

# Cross-platform:
f"{report_date.day} {report_date.strftime('%b %Y')}"   # "8 Feb 2026"
f"{report_date.day}/{report_date.month}/{report_date.year}"  # "8/2/2026"
```

### 9. JS click for unclickable elements

Playwright's `element.click()` fails on elements with zero bounding box, zero opacity, or elements inside Angular/React zones. Three escape hatches, in order of preference:

```python
# 1. For AUI hidden inputs (radio buttons, calendar inputs):
element.dispatch_event('click')        # for radio/tab selection
element.evaluate("el => el.click()")   # for cal inputs — opens calendar popover

# 2. For Angular zone.js elements (EasyEcom download button, Blinkit company selector):
element.evaluate("el => dispatchEvent(new MouseEvent('click', {bubbles: true}))")

# 3. For row-indexed clicks when there's no reliable locator:
page.evaluate("(idx) => rows[idx].querySelector('button').click()", row_idx)
```

**Never** use `element.click(force=True)` on a truly hidden element — Playwright can't calculate the click point and it will raise.

### 10. `expect_download` is on `page`, not `context`

```python
# Correct:
with self._page.expect_download(timeout=60_000) as dl_info:
    trigger_element.click()

# Wrong — BrowserContext has no expect_download:
with self._ctx.expect_download(...) as dl_info:   # AttributeError
```

### 11. nativeSetter for React/AUI date inputs

When a date input is controlled by a JS framework (React, AUI), directly setting `.value` via Playwright has no effect because the framework doesn't detect the change. Use the native setter pattern to bypass the framework:

```python
element.evaluate("""(el, val) => {
    const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value').set;
    setter.call(el, val);
    el.dispatchEvent(new Event('input',  {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
}""", date_str)
```

### 12. Screenshot on error

Every Playwright scraper calls `self._shot(label)` / `self._screenshot(label)` before raising or after a failed action. Screenshots land in `data/raw/<portal>/debug_<label>_<timestamp>.png`. Always take a screenshot at the point closest to the failure — it's the single most useful debugging tool.

### 13. Result dict shape

`run()` always returns:

```python
{
    "portal": str,        # portal_name
    "date":   date,       # report_date
    "file":   Path|None,  # single file (most scrapers)
    "files":  list|None,  # multiple files (Amazon PI — 6 categories)
    "status": str,        # "success" | "partial" | "failed"
    "error":  str|None,   # exception message on failure
    "drive_link":  str|None,  # Drive URL (single file)
    "drive_links": list|None, # Drive URLs (multiple files)
}
```

---

## Portal scrapers

### EasyEcom (`scrapers/easyecom_scraper.py`) — **Working**

| Detail | Value |
|--------|-------|
| URL | `app.easyecom.io` |
| Auth | Persistent Chrome profile + fresh Google OAuth each run |
| Profile dir | `scrapers/sessions/easyecom_profile/` |
| Profile sync | Yes — `"easyecom"` |
| Drive upload | Yes — `"EasyEcom"` |
| Download format | ZIP → extract CSV |

**Key quirks:**
- PHP session expires in ~24 min — a fresh Google OAuth is required every run. The persistent profile auto-selects the Google account so no credentials are entered manually.
- A "New Features" Angular modal appears on **every page navigation**. Dismiss by dispatching a `MouseEvent('click')` on `button.new-ui-outline-btn` — `page.click()` is unreliable here.
- Date picker is a jQuery Bootstrap daterangepicker on `div#reportrange`. Trigger it → click "Yesterday" in `.daterangepicker .ranges li`. Auto-applies; no Submit needed.
- Report is queued via `window.queueMiniReport()` (direct JS call — the Bootstrap 3 dropdown it belongs to is broken). Server confirms with a browser `alert('Download Job Queued')`.
- Poll `https://app.easyecom.io/V2/reports/import-export-report?jobType=1` until "Download Ended At" (column index 4) is non-empty.
- Download button is `<a class="download_result">` with no `href`. Must click via `dispatchEvent(new MouseEvent('click', {bubbles:true}))` — `page.mouse.click()` does not work (Angular zone.js).

---

### Blinkit (`scrapers/blinkit_scraper.py`) — **Working**

| Detail | Value |
|--------|-------|
| URL | `partnersbiz.com` (env: `BLINKIT_LINK`) |
| Auth | Persistent Chrome profile (OTP-based session) |
| Profile dir | `scrapers/sessions/blinkit_profile/` |
| Profile sync | Yes — `"blinkit"` |
| Drive upload | Yes — `"Blinkit"` |
| Download format | XLSX |

**Login flow:** Navigate to login → fill email (`input[placeholder="Enter Email ID"]`) → click "Request OTP" → fetch OTP from Gmail (`noreply@partnersbiz.com` → `automation@solara.in`) → fill 6 individual digit inputs (`input[maxlength="1"]`) → select company from company-selector modal.

**Date picker:** Ant Design RangePicker. Click `.ant-picker-input input` → find `td[title="YYYY-MM-DD"]` → click twice (start + end). Fallback: type date directly into the input + Enter.

**Report flow:** Click "Download Sales Data" → set date range → "Request Data" → navigate to `/app/report-requests` → poll every 30 s (up to 20 polls) for the row matching the date → `expect_download()` on the Download button.

**Key quirks:**
- First-time setup: run `auth_blinkit.py` once interactively to complete OTP login and save the session to the profile.
- Heavy JS `evaluate()` for company selector — Angular zone.js blocks Playwright's native `click()`.
- OTP timeout is generous: 120 seconds (portals can be slow to send).

---

### Zepto (`scrapers/zepto_scraper.py`) — **Working**

| Detail | Value |
|--------|-------|
| URL | `brands.zepto.co.in` (env: `ZEPTO_LINK`) |
| Auth | Email + password + OTP, session saved as JSON |
| Session file | `scrapers/sessions/zepto_session.json` |
| Profile sync | No (JSON state is small enough to gitignore locally) |
| Drive upload | Yes — `"Zepto"` |
| Download format | XLSX |

**Standalone CLI:** Run `python scrapers/zepto_scraper.py` (or `python scrapers/zepto_scraper.py --date 2026-02-20`) to trigger a single visible-browser run. Useful for refreshing the session JSON interactively.

**Login flow:** Email → password → "Log In" → OTP screen → fetch from Gmail (`mailer@zeptonow.com` → `automation@solara.in`) → fill `#otp` → confirm. Saves session state to JSON; skips login if session is still valid on the next run.

**Date picker:** MUI drawer modal. Select `Sales_F` from dropdown → fill two `input[type="tel"][placeholder="mm/dd/yyyy"]` fields → Submit.

**Report flow:** Navigate to `/vendor/reports` → "Request Report" → fill form → submit → reload until the row for the date appears with status "Completed" → `expect_download()` on the Download button.

---

### Amazon PI (`scrapers/amazon_pi_scraper.py`) — **Working**

| Detail | Value |
|--------|-------|
| URL | `pi.amazon.in/reports/sbg` (env: `AMAZON_PI_LINK`) |
| Auth | Email + password + TOTP 2FA |
| Profile dir | `scrapers/sessions/amazon_pi_profile/` |
| Profile sync | Yes — `"amazon_pi"` |
| Drive upload | Yes — `"Amazon PI"` |
| Download format | XLSX (one file per category × 6 categories) |

**Login flow:** Email → password → TOTP code (generated from `AMAZON_PI_TOTP_SECRET` via `pyotp`).

**Report flow (critical — do not change this order):**
1. Navigate to `/reports/sbg` **once**.
2. Set Brand = SOLARA **once**.
3. Set Time Period = Daily | From = To = report_date **once** (before any category is selected — the Time Period modal requires the chart to be loaded; at brand-only state the chart always loads cleanly).
4. Loop over 6 categories by changing `select#category-dropdown` only (AJAX, same page — Time Period state persists). For each: set report type → click "Generate Excel".
5. Navigate to `/download-center` → poll until all 6 rows show status "Ready" → download each.

**Amazon UI (AUI) quirks:**
- All AUI radio/button/calendar inputs (`a-button-input` class) are **always hidden by CSS**. Never use `wait_for("visible")` on them — use `wait_for("attached")`.
- Radio tab selection: `dispatch_event('click')`.
- Calendar input: `inp.evaluate("el => el.click()")` opens the popover; then use nativeSetter to set the date value; then click the day cell `a[data-action="a-cal-select-date"]`.
- Download Center table column 5 (`csv_name`) = "ASIN wise revenue and unit sales" — **not** column 4 (`report`) = "Sales by Geography". Filter on `csv_name`.
- Download Center status = **"Ready"** (not "Completed") when the file is downloadable.
- Download button is `<button>` (not `<a>`). Click via row-index JS evaluate.

---

### Swiggy (`scrapers/swiggy_scraper.py`) — **Working**

| Detail | Value |
|--------|-------|
| URL | `partner.swiggy.com/instamart/sales` (env: `SWIGGY_LINK`) |
| Auth | Persistent Chrome profile (Email + Gmail OTP) |
| Profile dir | `scrapers/sessions/swiggy_profile/` |
| Profile sync | Yes — `"swiggy"` |
| Drive upload | Yes — `"Swiggy"` |
| Download format | CSV |

**Login flow:** Navigate to `SWIGGY_LINK` → fill email (`SWIGGY_EMAIL`) → click "Send OTP" (`[data-testid="submit-phone-number"]`, waits for button to become enabled) → fetch OTP from Gmail (`no-reply@swiggy.in` → `automation@solara.in`) → fill individual digit inputs → auto-submits on last digit → may redirect to `/instamart/account-select` (handled automatically by `_handle_account_select()`).

**Date picker:** Custom React dropdown. Trigger: `[data-testid*="date" i]` (the "This Week" button). Opens a preset list; click "Custom Date Range" → fill start/end inputs with DD/MM/YYYY via nativeSetter → click "Select Range" to confirm → press Escape to dismiss any remaining overlay.

**Report flow:**
1. Click "Generate Report" via JS `dispatchEvent` — Playwright's native `click()` is blocked by the floating calendar overlay that remains open after date selection.
2. **Phase 1** (up to 60s): Wait for the new report name (`IMSales_MMDDYY_HHMM`) to appear in the "Available Reports" section with "Generation in progress" status — confirms the portal accepted the request.
3. **Phase 2** (up to 10 min): Reload every 30s and read section text line-by-line. Report is ready when the line immediately after the report name starts with "Generated on".
4. Download via `[data-testid="download-icon"]` Playwright locator wrapped in `page.expect_download()` context manager.

**Key quirks:**
- OTP sender is `no-reply@swiggy.in` (not `.com`). OTP is in the email **body** (nested HTML), not the subject line.
- `gmail_otp.py` required a fix for deeply nested MIME: `multipart/mixed → multipart/alternative → text/html`. Fixed via recursive `_collect_parts()` descent.
- Report generation takes **2–10 minutes** on the portal side — the 30s reload loop tracks the specific named report card so it does not confuse earlier completed reports with the new one.
- Download format is CSV (not XLSX). The download button is `[data-testid="download-icon"]` SVG inside `div.imads__Ri7gC`.
- `expect_download` must wrap the locator `.click()` call — do **not** trigger via JS `dispatchEvent` before entering the context manager, or the download event fires before Playwright starts listening.

---

### Amazon Seller Central (`scrapers/amazon_scraper.py`) — **Stub (selectors unverified)**

| Detail | Value |
|--------|-------|
| URL | `sellercentral.amazon.in` |
| Auth | Email + password (2FA may be required) |

Scrapes daily sales from Seller Central Report Central. Selectors need live verification. **Note:** this is separate from both the Amazon PI scraper and the ASIN price tool at `scrapers/tools/amazon_asin_scraper/`.

---

### Shopify (`scrapers/shopify_scraper.py`) — **Working**

| Detail | Value |
|--------|-------|
| API | Shopify Admin REST API v2024-04 |
| Auth | `SHOPIFY_API_KEY` + `SHOPIFY_API_SECRET` + `SHOPIFY_STORE_URL` |
| Profile sync | N/A |
| Drive upload | Not yet implemented |
| Download format | CSV |

No browser required. Fetches orders for the target date via the REST API with pagination (`Link` header). Timestamps are in IST (`+05:30`). Does not extend `BaseScraper`.

---

## Supporting modules

| File | Purpose |
|------|---------|
| `base_scraper.py` | Abstract base: browser lifecycle, `_screenshot()`, `run()` with 3-retry backoff |
| `profile_sync.py` | `download_profile(portal)` / `upload_profile(portal)` — Drive ↔ local Chrome profile sync. No-op when `PROFILE_STORAGE_DRIVE_FOLDER_ID` is unset |
| `google_drive_upload.py` | `upload_to_drive(portal, report_date, file_path)` — uploads to `SolaraDashboard Reports / YYYY-MM / <Portal> /`. Uses same OAuth token as Gmail (`token.json` or `GMAIL_TOKEN_JSON` env) |
| `gmail_otp.py` | Reads Gmail inbox of `automation@solara.in` to fetch OTP codes sent by portals (Zepto, Blinkit, Swiggy). Handles nested MIME structures via recursive `_collect_parts()`. |
| `totp_helper.py` | `get_totp_code(env_var)` — reads a Base32 TOTP secret from an env var and returns the current 6-digit code via `pyotp` (used by Amazon PI) |
| `excel_parser.py` | Portal-specific parsers. `get_parser(portal_name)` returns the right parser. Each parser implements `parse_sales(file)` and optionally `parse_inventory(file)`, returning a list of raw row dicts |
| `data_transformer.py` | Normalises raw rows: resolves city name aliases (e.g. "BLR" → "Bangalore"), looks up portal/product/warehouse IDs from DB, returns DB-ready dicts |
| `orchestrator.py` | Runs all scrapers sequentially, parses files, upserts to DB, sends Slack notification |

---

## Price Scraper Tools (`scrapers/tools/`)

Standalone Playwright CLI tools for scraping **live product prices** from quick-commerce and e-commerce portals. Not part of the daily scraper service — run independently, on demand, without Docker.

Each tool has its own `requirements.txt` containing only `playwright>=1.40.0` (plus `requests`, `beautifulsoup4`, `lxml` for the Amazon ASIN tool).

| Tool | Portal | Input type | Key output |
|------|--------|-----------|------------|
| `blinkit_price_scraper/` | Blinkit | Product IDs or URLs | Price, MRP, discount, in-stock status |
| `swiggy_price_scraper/` | Swiggy Instamart | Product URLs | Price, MRP, discount, availability |
| `zepto_price_scraper/` | Zepto | Product URLs | Price, MRP, discount, rating |
| `amazon_asin_scraper/` | Amazon.in | ASINs | Price, BSR, seller, ships-from |

### Common flags (all tools)

| Flag | Effect |
|------|--------|
| `--no-headless` | Show the browser window (default: headless) |
| `-f <file>` | Read inputs from a text or CSV file (one per line) |
| `-o results.csv` | Export results to CSV |
| `-p <pincode>` | Set delivery pincode for location-aware pricing |

### Usage examples

```bash
# Blinkit — single product by ID, specific pincode
cd scrapers/tools/blinkit_price_scraper
pip install -r requirements.txt
playwright install chromium
python main.py -p 122009 627046

# Swiggy Instamart — bulk from file, batched to avoid rate limits
cd scrapers/tools/swiggy_price_scraper
python main.py -p 560103 -f urls.txt -o results.csv --batch-size 3 --batch-pause 480

# Zepto — single URL with pincode
cd scrapers/tools/zepto_price_scraper
python main.py -p 400093 "https://www.zeptonow.com/pn/solara-air-fryer/pvid/..."

# Amazon ASIN — bulk from file, India marketplace, Slack notification
cd scrapers/tools/amazon_asin_scraper
python main.py -m in -f asins.txt -o results.csv --slack
```

**Note:** These tools do **not** interact with the PostgreSQL database. Output is to stdout and/or CSV only. They are not invoked by `orchestrator.py`.

---

## Session storage

```
scrapers/sessions/
  ├── easyecom_profile/     ← Chromium persistent profile (Google OAuth)
  ├── blinkit_profile/      ← Chromium persistent profile (OTP session)
  ├── amazon_pi_profile/    ← Chromium persistent profile (TOTP session)
  ├── swiggy_profile/       ← Chromium persistent profile (OTP session)
  └── zepto_session.json    ← Playwright storage state (cookies + localStorage)
```

These are gitignored. On CI they are restored from Google Drive (`profile_sync.py`). Locally they are created on first interactive run.

---

## Error handling

- **Retries:** BaseScraper retries up to `MAX_RETRY_ATTEMPTS` times (default 3) with exponential backoff. Scrapers with custom `run()` (EasyEcom, Blinkit, Amazon PI) do not retry — they fail fast and surface the error to the orchestrator.
- **Screenshots:** Saved to `data/raw/<portal>/error_<label>_<timestamp>.png` when `SCREENSHOT_ON_ERROR=true`.
- **Logging:** Each scraper run is recorded in the `scraping_logs` table (`status`, `records_processed`, `error_message`).
- **Slack:** `notify_scraping_complete()` posts a summary after every orchestrator run; `notify_scraping_failure()` is available for individual portal failures.

---

## Adding a new scraper

1. Create `scrapers/newportal_scraper.py`. If the portal needs a persistent browser session:
   ```python
   class NewPortalScraper:
       portal_name = "newportal"

       def run(self, report_date: date = None) -> dict:
           try:
               from scrapers.profile_sync import download_profile, upload_profile
           except ImportError:
               from profile_sync import download_profile, upload_profile
           ...
           try:
               download_profile("newportal")
               self._init_browser()
               self.login()
               files = self.download_report(report_date)
               if _upload_to_drive and files:
                   _upload_to_drive(portal="New Portal", ...)
           finally:
               self._close_browser()
               upload_profile("newportal")
   ```
   If the portal has a stable password login (no OTP/OAuth), extend `BaseScraper` instead and implement `login()`, `download_report()`, `logout()`.

2. Add a parser class in `scrapers/excel_parser.py` and register it in the `get_parser()` factory.
3. Add `NewPortalScraper` to the `SCRAPERS` list in `scrapers/orchestrator.py`.
4. Add portal credentials to `.env` and `backend/app/config.py`.
5. Insert a row into the `portals` table.
6. Add the new `portal_name` to the GitHub Actions secrets list if running in CI.
