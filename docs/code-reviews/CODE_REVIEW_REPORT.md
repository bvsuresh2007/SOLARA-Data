# SolaraDashboard — Code Review Reports

---

## Review: 2026-02-21

**Branch:** `claude/merge-solara-projects-Qo5Sd`

**Files reviewed:**

*Modified (unstaged):*
- `.gitignore`
- `backend/app/config.py`
- `backend/app/models/__init__.py`, `inventory.py`, `metadata.py`, `sales.py`
- `backend/app/utils/slack.py`
- `requirements.txt`
- `scrapers/blinkit_scraper.py`, `easyecom_scraper.py`, `zepto_scraper.py`
- `shared/constants.py`

*New (untracked):*
- `scrapers/gmail_otp.py`
- `scrapers/totp_helper.py`
- `scrapers/amazon_pi_scraper.py`
- `scrapers/flipkart_email_scraper.py`
- `scrapers/sessions/` (browser profiles + session file)
- `scripts/db_utils.py`, `import_excel_sales.py`, `excel_reader.py`, and others

*Deleted:*
- `auth_blinkit.py` (moved into `scrapers/`)
- `main.py`, `src/scraper.py`, `src/slack_notifier.py` (moved to `scrapers/tools/amazon_asin_scraper/`)

---

### Executive Summary

The changes represent a significant schema alignment (v1 → v2 model renames, new tables), a full Zepto scraper implementation, new OTP/TOTP infrastructure, and importer scripts for Excel data. The overall quality is high — good docstrings, consistent patterns, proper upsert logic. Two issues require attention before committing: the browser profile directories are not gitignored (would commit auth credentials to the repo), and `gmail_otp.py` bundles a Drive scope into a module named for Gmail OTP only.

---

### 🔴 Critical

---

#### C-01 — Browser profiles not gitignored
**Files:** `.gitignore`, `scrapers/sessions/`
**Status:** ✅ Resolved — `scrapers/sessions/*_profile/` added to `.gitignore`; Drive-based profile sync implemented in `profile_sync.py`

`scrapers/sessions/blinkit_profile/` and `scrapers/sessions/easyecom_profile/` are large Chromium persistent profiles that contain auth cookies and cached Google/Blinkit sessions. They are **not covered by `.gitignore`**. Running `git add scrapers/` would commit them, leaking auth tokens into the repository.

**CI/CD solution (implemented: Option A — Google Drive storage):**
- Profile zips stored in `SolaraDashboard Profiles` Drive folder
- `scrapers/profile_sync.py` — `download_profile(portal)` / `upload_profile(portal)` handles sync
- Silent no-op when `PROFILE_STORAGE_DRIVE_FOLDER_ID` is unset (local dev)

---

#### C-02 — `gmail_otp.py` requests Drive scope it doesn't need
**File:** `scrapers/gmail_otp.py:29–32`

```python
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.file",   # ← Drive scope in OTP module
]
```

The `drive.file` scope was added so `gmail_otp.py` and `google_drive_upload.py` can share a single `token.json`. The shared token covers both Gmail read and Drive write — this is documented but the Drive scope remains in `gmail_otp.py` for practical reasons (single token file).

---

### 🟡 Medium

---

#### M-01 — `zepto_scraper.py` uses Linux-only `%-d` date format
**File:** `scrapers/zepto_scraper.py:207`
**Status:** ✅ Fixed — changed to `f"{report_date.day} {report_date.strftime('%b %Y')}"`

---

#### M-02 — `CITY_ALIASES` in `data_transformer.py` duplicates `CITY_NAME_MAP` in `shared/constants.py`
**Files:** `scrapers/data_transformer.py:18–39`, `shared/constants.py:44–86`

Two sources of truth for city normalisation will cause inconsistencies between Excel imports (using `constants.py`) and scraper data (using `data_transformer.py`).

**Suggestion:** Remove `CITY_ALIASES` from `data_transformer.py` and replace the normalisation logic with `from shared.constants import normalise_city`.

---

#### M-03 — `gmail_otp.py` token path is relative to CWD, not project root
**File:** `scrapers/gmail_otp.py:42`
**Status:** ✅ Fixed — path anchored to `Path(__file__).resolve().parent.parent / "token.json"`

---

#### M-04 — `amazon_pi_scraper.py` raises `NotImplementedError` in `download_report()`
**Status:** ✅ Resolved — Amazon PI scraper fully implemented with complete download flow

---

#### M-05 — `scripts/import_excel_sales.py` imports private function `_clean_sku`
**File:** `scripts/import_excel_sales.py:37`

**Suggestion:** Rename `_clean_sku` to `clean_sku` in `excel_reader.py` and add it to its `__all__`.

---

#### M-06 — `scripts/db_utils.py` constructs DB URL at import time with no validation
**File:** `scripts/db_utils.py:41–50`

If `POSTGRES_PASSWORD` is not set, the URL becomes silently malformed. **Suggestion:** Assert required vars before building the URL.

---

### 🟢 Low

---

#### L-01 — `scrapers/sessions/` directory is untracked
**Status:** ✅ Resolved — `sessions/__init__.py` committed; profiles gitignored

---

#### L-02 — `load_dotenv()` called at module level in individual scrapers
**Suggestion:** Call `load_dotenv()` once in `orchestrator.py` at startup and remove per-module calls.

---

#### L-03 — `notify_monthly_drive_folder()` has no trigger
The new `notify_monthly_drive_folder()` function is defined but never called anywhere in the codebase.

---

#### L-04 — `database/alembic/versions/` is untracked
Migration files should be committed once the schema stabilises.

---

### Gitignore Check (untracked files)

| Path | Status |
|------|--------|
| `scrapers/sessions/zepto_session.json` | ✅ Covered by `*_session.json` |
| `scrapers/sessions/blinkit_profile/` | ✅ Fixed — covered by `*_profile/` |
| `scrapers/sessions/easyecom_profile/` | ✅ Fixed — covered by `*_profile/` |
| `scrapers/sessions/__init__.py` | ✅ Committed |
| `database/alembic/versions/` | Should be committed once schema stabilises |
| `scripts/` (importer tools) | ✅ Committed |
| `docs/` | ✅ Committed |

---

### Positive Notes

- **Model changes** are well-structured with clear grain comments, appropriate `Numeric` types, consistent `UniqueConstraint` definitions.
- **`totp_helper.py`** handles the near-expiry edge case (waiting for the next 30-second window).
- **`zepto_scraper.py`** session save/restore logic is solid.
- **`shared/constants.py`** city normalisation map is comprehensive and well-commented.

---

### Action Plan

| Priority | Action | Status |
|----------|--------|--------|
| 🔴 C-01 | Add `scrapers/sessions/*_profile/` to `.gitignore`; Drive profile sync | ✅ Done |
| 🔴 C-02 | Document Drive scope in `gmail_otp.py` | ✅ Documented |
| 🟡 M-01 | Fix `%-d` in `zepto_scraper.py` | ✅ Done |
| 🟡 M-02 | Remove `CITY_ALIASES` from `data_transformer.py` | Open |
| 🟡 M-03 | Anchor `token.json` path to project root in `gmail_otp.py` | ✅ Done |
| 🟡 M-05 | Make `_clean_sku` public in `excel_reader.py` | Open |
| 🟡 M-06 | Add env var validation in `db_utils.py` | Open |
| 🟢 L-01 | Commit `scrapers/sessions/__init__.py` | ✅ Done |
| 🟢 L-04 | Commit `database/alembic/versions/` once schema stabilises | Open |

---

## Review: 2026-02-24

**Branch**: main
**Reviewer**: Claude Code (automated, read-only)
**Scope**: 22 modified files (git diff) + 17 untracked new files

---

### Executive Summary

This diff represents a substantial architectural evolution: the data model migrated from `CityDailySales`/`city_id`-centric to `DailySales`-centric, the Sales dashboard was rewritten as a full client-side React page with six new API endpoints, and a file-upload pipeline (manual Excel + portal CSV ingest) was added. The code quality is generally high — well-structured, well-commented, with good separation of concerns. The most urgent issues are a hardcoded database credential in a committed script, a `sslmode=require` setting that will break local Docker development, and several fields in the API that are silently stubbed to `0` (masking missing data). There are also moderate DRY violations in the frontend (five copies of `fmtRevenue`) and a missing file-size limit on the upload endpoint.

---

## 🔴 Critical Issues

### 1. `sslmode=require` breaks local Docker Compose — `backend/app/database.py:10`

```python
connect_args={"sslmode": "require"},
```

**Problem**: This breaks every local Docker Compose setup where PostgreSQL runs without SSL. Correct for Supabase/cloud Postgres, wrong for local development. Will cause `sqlalchemy.exc.OperationalError` on first startup.

**Suggestion**:
```python
connect_args={"sslmode": "require"} if settings.db_ssl else {},
```

---

### 2. Silently stubbed API fields — `backend/app/api/sales.py:55–58, 107–115, 162–168`

```python
total_net_revenue=rev,   # ← aliased to gross revenue (not real net)
total_orders=0,          # ← hardcoded zero
total_discount=0.0,      # ← hardcoded zero
record_count=0,          # ← hardcoded zero in portal/product breakdowns
```

**Problem**: `total_net_revenue` is silently aliased to `total_revenue` (they are not the same). `total_orders` and `total_discount` always return `0`. Dashboard consumers receive fabricated data with no indication it is inaccurate.

**Suggestion**: Mark these fields `Optional` and return `None`, or remove them from the schema entirely until the DB schema supports them. Never alias one metric to another silently.

---

### 3. No file size limit on upload endpoint — `backend/app/api/uploads.py:89–95`

```python
content = await file.read()  # reads entire file into memory, no size check
```

**Problem**: An attacker or user can upload arbitrarily large files, exhausting server RAM. FastAPI does not enforce limits by default.

**Suggestion**:
```python
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
content = await file.read()
if len(content) > MAX_UPLOAD_BYTES:
    raise HTTPException(status_code=413, detail="File exceeds 50 MB limit")
```

---

### 4. Hardcoded database password — `scripts/replicate_to_supabase.py:17–20`

```python
LOCAL_URL = os.environ.get(
    "LOCAL_DATABASE_URL",
    "postgresql://solara_user:solara123@localhost:5432/solara_dashboard",
)
```

**Problem**: `solara123` is a hardcoded default password committed to version control. Even as a dev default, this violates credential hygiene and triggers secret-scanning tools.

**Suggestion**:
```python
LOCAL_URL = os.environ["LOCAL_DATABASE_URL"]  # fail fast if not set
```

---

## 🟡 Medium Issues

### 5. `UploadResult` early-return returns placeholder values — `backend/app/api/uploads.py:184–260`

When the early-return path (empty batch) is hit, the `UploadResult` has `file_type=""`, `file_name=""`, `rows_parsed=0` sent to the client. The caller's field overwrite in `upload_file()` is bypassed on this path.

**Suggestion**: Pass `filename`, `file_type`, `rows_parsed` as parameters to each `_process_*` function, or move result assembly inside the function itself.

---

### 6. Silent `IntegrityError` swallowing — `backend/app/api/uploads.py:248–250`

```python
except IntegrityError:
    db.rollback()
    logger.warning("IntegrityError during sales insert — some rows may have been skipped")
    # inserted count is NOT reset — caller returns incorrect non-zero count
```

**Problem**: `inserted=N` is returned to the client even though the rollback cleared all inserts.

**Suggestion**: Set `inserted = 0` in the except block and add a descriptive entry to `errors`.

---

### 7. `fetchPortalDaily` depends on `portals` state being populated — `frontend/app/dashboard/sales/page.tsx:432–448`

```typescript
const portalName = portals.find(p => p.id === portalId)?.name;
// If portals=[] on first load, portalName=undefined → backend defaults to "swiggy" silently
const data = await api.portalDaily({
    ...(portalName ? { portal: portalName } : {}),
```

**Problem**: When `portalId` is in the URL on first load, `portals` may still be empty. `portalName` resolves to `undefined` and the API is called without a portal filter, silently returning the wrong portal's data.

**Suggestion**: Guard with `if (!portals.length) return;` or read the portal slug directly from URL params instead of resolving through the `portals` state array.

---

### 8. DRY violation — `fmtRevenue` copy-pasted across 6 components

The same INR currency formatter (`₹X Cr / ₹X L / ₹X K`) appears in:
- `frontend/components/sales/kpi-strip.tsx:6–10` — `fmt()`
- `frontend/components/sales/portal-breakdown.tsx:20–25` — `fmtRevenue()`
- `frontend/components/sales/revenue-trend.tsx:46–51` — `fmtRevenue()`
- `frontend/components/sales/target-achievement.tsx:22–27` — `fmtRevenue()`
- `frontend/components/sales/category-chart.tsx:9–14` — `fmtRevenue()`
- `frontend/components/sales/product-table.tsx:11–16` — `fmtRevenue()`
- `frontend/components/sales/portal-daily-table.tsx:18–23` — `fmtValue()`

**Suggestion**: Extract to `frontend/lib/format.ts` and import from there.

---

### 9. `iterrows()` called 10+ times in `excel_parsers.py`

`pandas.DataFrame.iterrows()` is 10–100x slower than vectorised operations. Called in every portal parser for every row.

**Suggestion**: Replace with `df.to_dict("records")` for row iteration, or vectorise transformations using `df.assign()` / `df.apply()`.

---

### 10. `sys.path` mutation + private import from `scripts/` — `backend/app/utils/excel_parsers.py:409–417`

```python
def _ensure_scripts_on_path() -> None:
    import sys
    project_root = os.path.dirname(...)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from scripts.excel_reader import iter_sheets, clean_sku, _float  # type: ignore
```

**Problem**: Mutates `sys.path` at request time (fragile in multi-worker ASGI deployments — race condition). Imports a `_`-prefixed private function from a CLI utility, tying the backend Docker image to `scripts/` being present.

**Suggestion**: Move the shared parsing logic into `backend/app/utils/` as a proper module.

---

### 11. Case-sensitive city lookup — `backend/app/utils/portal_resolver.py:61–66`

`portal_id()` lowercases its input but `city_id()` does not. Portal CSV exports with inconsistent casing ("Mumbai" vs "mumbai") cause silent mismatches.

**Suggestion**: Apply `.lower()` consistently, or use `func.lower()` in the DB filter.

---

### 12. No row limit on `POST /api/imports/sales` — `backend/app/api/imports.py:116`

No upper bound on `body.rows`. A single POST can submit 100,000 rows, consuming significant memory and blocking the DB session.

**Suggestion**:
```python
if len(body.rows) > 10_000:
    raise HTTPException(status_code=400, detail="Too many rows (max 10,000 per request)")
```

---

### 13. f-string SQL with schema-derived column names — `scripts/replicate_to_supabase.py:262–269`

```python
src_cur.execute(f'SELECT {col_list} FROM "{table}"')
```

`col_list` is assembled from `information_schema` column names. Not directly user-controllable, but violates parameterised query best practice.

**Suggestion**: Use `psycopg2.sql.Identifier` for table and column names.

---

### 14. `GOOGLE_TOKEN_JSON` secret written to runner disk — `.github/workflows/scraper-swiggy.yml:35`

```yaml
run: echo "${{ secrets.GOOGLE_TOKEN_JSON }}" | base64 -d > token.json
```

Low risk given scoped artifact uploads (only `data/raw/swiggy/`), but worth noting. Verify no `upload-artifact` step ever includes the working root directory.

---

### 15. `scrapers/amazon_pi_diagnose.py` — dev tool left untracked

Contains `input("\nPress Enter to close...")` — clearly a debug script. `KeyError` if `AMAZON_PI_LINK` env var is unset (uses `os.environ["AMAZON_PI_LINK"]` without `.get()`).

**Suggestion**: Add to `.gitignore`, or move to `scrapers/dev/`.

---

## 🟢 Low Issues

### 16. Dead `city_id` query parameter silently discarded — `backend/app/api/sales.py:42, 68, 135`

```python
city_id: Optional[int] = Query(None),   # kept for backward compat, ignored
```

Callers passing `?city_id=5` get wrong results with no error.

**Suggestion**: Return HTTP 400 if `city_id` is provided, or remove the parameter entirely.

---

### 17. `ORDER BY func.sum()` re-evaluates aggregate — `backend/app/api/sales.py:101, 153`

```python
.order_by(func.sum(DailySales.revenue).desc().nullslast())
```

**Suggestion**: Use `.order_by(text("total_revenue DESC NULLS LAST"))` to reference the SELECT alias.

---

### 18. Inconsistent default date range — `backend/app/api/sales.py:174–175`

90-day default applied only in `sales_trend`. Other endpoints return all-time data. Inconsistency is undocumented.

**Suggestion**: Document the default with `description=` in `Query(...)`, or apply a consistent default across all endpoints.

---

### 19. `datetime.utcnow()` deprecated in Python 3.12+ — `backend/app/api/imports.py:95`, `uploads.py:240, 344, 453`

```python
end_time=datetime.utcnow(),
```

**Suggestion**: Replace with `datetime.now(timezone.utc)`.

---

### 20. `new Date()` called inline in component body — `frontend/app/dashboard/sales/page.tsx:356–358`

```typescript
const today = new Date();
const [targetYear, setTargetYear] = useState(today.getFullYear());
```

Could produce SSR hydration mismatches near midnight.

**Suggestion**: Use lazy `useState` initialisers: `useState(() => new Date().getFullYear())`.

---

### 21. Duplicate Recharts tooltip style — 4 components

Same `contentStyle` object (`backgroundColor: "#18181b"`, `border: "1px solid #3f3f46"`, etc.) copy-pasted across `portal-breakdown.tsx`, `revenue-trend.tsx`, `category-chart.tsx`, `bar-chart.tsx`.

**Suggestion**: Export `RECHARTS_TOOLTIP_STYLE` constant from `frontend/lib/chart-config.ts`.

---

### 22. No client-side file type validation — `frontend/app/dashboard/upload/page.tsx:219–221`

`accept=".xlsx,.xls,.csv"` is trivially bypassed by the user.

**Suggestion**: Add extension check in `pickFile()` before setting file state.

---

### 23. Dynamic import fallback pattern in scrapers — `scrapers/swiggy_scraper.py:31–43`

```python
try:
    from .google_drive_upload import upload_to_drive as _upload_to_drive
except ImportError:
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location(...)
```

Appears in multiple scrapers. Fragile and hard to debug.

**Suggestion**: Use `if __name__ == "__main__": sys.path.insert(0, ...)` in `__main__` blocks only.

---

### 24. Dark mode hardcoded on `<html>` — `frontend/app/layout.tsx:11`

```tsx
<html lang="en" className="dark">
```

Ignores `prefers-color-scheme`. If dark-only is intentional, remove the unused light-mode CSS variables from `globals.css` to reduce dead code.

---

### 25. `frontend/next-env.d.ts` should be gitignored

Auto-generated by Next.js on every `next build` / `next dev`. Creates noisy diffs and merge conflicts.

---

### 26. `scripts/replicate_to_supabase.py` has embedded DDL diverging from Alembic migrations

200 lines of schema SQL in the replication script — three sources of truth (`init_db.sql`, Alembic migrations, this script).

**Suggestion**: Commit the script and add a CI check to validate schema consistency.

---

## Gitignore Audit

| File | Action |
|------|--------|
| `frontend/next-env.d.ts` | ✅ **Add to `.gitignore`** — auto-generated by Next.js |
| `scrapers/amazon_pi_diagnose.py` | ✅ **Add to `.gitignore`** — dev/debug tool with `input()` prompts |
| `frontend/package-lock.json` | ✅ Commit — needed for reproducible installs |
| `scripts/replicate_to_supabase.py` | ✅ Commit — clean utility script |
| All other untracked `backend/`, `frontend/`, `.github/` files | ✅ Commit — no concerns |

---

## Prioritised Action Plan

### Immediate — Before Next Production Deploy
1. **[Issue 1]** Fix `sslmode=require` in `database.py` — make conditional on env var
2. **[Issue 3]** Add 50 MB file size limit to `POST /api/uploads/file`
3. **[Issue 4]** Remove hardcoded `solara123` password from `scripts/replicate_to_supabase.py`
4. **[Issue 2]** Address stubbed `total_net_revenue` / `total_orders` / `total_discount` fields returning `0`

### Short Term — Next Sprint
5. **[Issue 5]** Fix `UploadResult` early-return bug (wrong values returned to client)
6. **[Issue 6]** Fix silent `IntegrityError` swallowing (incorrect `inserted` count after rollback)
7. **[Issue 7]** Guard `fetchPortalDaily` against empty `portals` state on first load
8. **[Issue 8]** Extract `fmtRevenue` to `frontend/lib/format.ts` (7 copies → 1)
9. **[Issue 9]** Replace `iterrows()` with `df.to_dict("records")` in `excel_parsers.py`
10. **[Issue 11]** Fix case-sensitive city lookup in `portal_resolver.py`
11. **[Issue 12]** Add row limit to `POST /api/imports/sales`

### Housekeeping
12. **[Issue 10]** Remove `sys.path` mutation and `scripts/` import from `excel_parsers.py`
13. **[Issue 16]** Remove deprecated `city_id` query parameter (or return HTTP 400)
14. **[Issue 19]** Replace `datetime.utcnow()` with `datetime.now(timezone.utc)`
15. **[Issue 25]** Add `frontend/next-env.d.ts` to `.gitignore`
16. **[Issue 15]** Add `scrapers/amazon_pi_diagnose.py` to `.gitignore`

---

## 2026-02-24 — Frontend UI: shadcn/ui Migration (feature/dashboard-overhaul)

**Branch**: `feature/dashboard-overhaul`
**Reviewer**: Claude Code (automated, read-only)
**Scope**: 18 modified files + 9 untracked new files — frontend only

### Files Reviewed (27 total)

**Modified (18):**
`frontend/app/dashboard/{page,sales/page,inventory/page,upload/page}.tsx`,
`frontend/app/globals.css`, `frontend/tailwind.config.js`,
`frontend/package.json`, `frontend/package-lock.json`,
`frontend/components/charts/metric-card.tsx`,
`frontend/components/filters/filter-bar.tsx` *(deleted — correct)*,
`frontend/components/sales/{product-table,revenue-trend,sales-filters,target-achievement}.tsx`,
`frontend/components/tables/data-table.tsx`,
`frontend/components/ui/{badge,card,skeleton}.tsx`

**New — Untracked (9):**
`docs/frontend.md`,
`frontend/components.json`,
`frontend/components/ui/{button,input,nav-tabs,progress,select,separator,table}.tsx`

---

### Executive Summary

Full migration from hand-rolled HTML to shadcn/ui component primitives. The CSS variable theming strategy, dark mode approach, CVA badge extension, and URL-driven filter state are all well-executed. Build compiles cleanly with zero TypeScript errors (`npm run build` → 8/8 static pages, no warnings).

**No critical or security issues.** Four medium issues and five low-priority observations below.

---

### 🟡 Medium Issues

---

**M-1 · `frontend/package.json:17` — Dead dependency: `@tanstack/react-table`**

```json
"@tanstack/react-table": "^8.17.3",
```

`@tanstack/react-table` is listed as a dependency but is not imported in any component. shadcn's `<Table>` is a plain styled HTML table — it does not require TanStack Table. This adds ~40 KB to the bundle unnecessarily.

*Suggestion*: `npm uninstall @tanstack/react-table`

---

**M-2 · `frontend/app/dashboard/upload/page.tsx:82–95` — No client-side file size guard**

```tsx
async function handleUpload() {
  if (!file || !selectedType || uploading) return;
  setUploading(true); clearResult();
  const form = new FormData(); form.append("file", file);
  const res = await fetch(`${BASE}/api/uploads/file?...`, { method: "POST", body: form });
```

No check on `file.size` before POSTing. A user who picks a 200 MB file triggers a long browser freeze with the spinner spinning — no early feedback. The backend already has a 50 MB server-side limit (Issue 3 from prior review).

*Suggestion*: Add before `setUploading(true)`:
```tsx
const MAX_BYTES = 50 * 1024 * 1024;
if (file.size > MAX_BYTES) {
  setNetworkError(`File too large (${(file.size/1024/1024).toFixed(1)} MB). Max 50 MB.`);
  return;
}
```

---

**M-3 · `frontend/components/sales/product-table.tsx:106` — Silent truncation at 50 rows**

```tsx
{rows.slice(0, 50).map((p, i) => { ... })}
```

No indicator when results exceed 50 rows. A user searching for a product that's ranked #51+ will see no results and assume the product doesn't exist. The inventory page correctly handles this with "Showing 50 of N records."

*Suggestion*:
```tsx
{rows.length > 50 && (
  <p className="text-xs text-zinc-600 mt-3 px-1">
    Showing 50 of {rows.length} products{search ? ` matching "${search}"` : ""}.
  </p>
)}
```

---

**M-4 · `frontend/app/dashboard/sales/page.tsx:69–77` — `Promise.all` fails entirely on a single endpoint error**

```tsx
const [portalsData, summaryData, byPortalData, trendData, byCatData, byProdData] =
  await Promise.all([
    api.portals(), api.salesSummary(fp), api.salesByPortal(fp),
    api.salesTrend(fp), api.salesByCategory(fp), api.salesByProduct({ ...fp, limit: 50 }),
  ]);
```

If any single endpoint returns an error, the entire `Promise.all` rejects and all charts go blank. On a dashboard, showing 5/6 panels with partial data is almost always preferable.

*Suggestion*: Switch to `Promise.allSettled` with per-endpoint fallbacks so individual failures degrade gracefully.

---

### 🟢 Low Issues

---

**L-1 · `frontend/components/ui/skeleton.tsx:6` — `React.HTMLAttributes` without importing React**

```tsx
import { cn } from "@/lib/utils"   // ← no React import

function Skeleton({
  className, ...props
}: React.HTMLAttributes<HTMLDivElement>) {
```

Uses the `React` namespace for a type reference without importing it. Works in Next.js 14 because `@types/react` makes it available globally, but is non-idiomatic and would silently break in a plain TypeScript project.

*Suggestion*:
```tsx
import type { HTMLAttributes } from "react"
// use: HTMLAttributes<HTMLDivElement>
```

---

**L-2 · `frontend/components/sales/revenue-trend.tsx:93–133` — Hardcoded hex colours in Recharts config**

```tsx
<stop stopColor="#f97316" />
<CartesianGrid stroke="#27272a" />
<XAxis tick={{ fill: "#71717a" }} />
<Tooltip contentStyle={{ backgroundColor: "#18181b" }} />
```

The same pattern exists in `bar-chart.tsx`, `portal-breakdown.tsx`, and `category-chart.tsx`. SVG cannot reliably consume CSS custom properties, so this is inherent to Recharts. However, having 4 copies of the same colour map means a brand change touches 4 files.

*Suggestion*: Extract to `frontend/lib/chart-colors.ts`:
```ts
export const CHART = {
  brand: "#f97316", grid: "#27272a", axis: "#71717a",
  axisBorder: "#3f3f46", tooltipBg: "#18181b", tooltipBorder: "#3f3f46",
} as const;
```

---

**L-3 · `frontend/app/dashboard/upload/page.tsx:92–94` — catch block discards the error**

```tsx
} catch {
  setNetworkError("Network error — could not reach the backend.");
}
```

The caught exception is silently discarded. CORS failures, JSON parse errors, and DNS failures all look identical in production with no way to diagnose via browser console.

*Suggestion*:
```tsx
} catch (err) {
  console.error("[Upload] network error:", err);
  setNetworkError("Network error — could not reach the backend.");
}
```

---

**L-4 · `frontend/components/ui/nav-tabs.tsx:18` — Exact pathname match breaks for nested routes**

```tsx
const isActive = pathname === href;
```

Current routes are all flat (`/dashboard`, `/dashboard/sales`, etc.) — this works today. If a sub-route is added (e.g. `/dashboard/sales/[id]`), the parent tab won't highlight.

*Suggestion*:
```tsx
const isActive = href === "/dashboard"
  ? pathname === href
  : pathname.startsWith(href);
```

---

**L-5 · Git CRLF warnings for `badge.tsx`, `card.tsx`, `skeleton.tsx`**

```
warning: LF will be replaced by CRLF the next time Git touches it
```

Three shadcn-generated files have LF endings on a Windows CRLF repo. Causes noisy diffs on future edits.

*Suggestion*: Add a `frontend/.gitattributes`:
```gitattributes
* text=auto eol=lf
*.tsx text eol=lf
*.ts  text eol=lf
*.css text eol=lf
```

---

### ✅ Patterns Done Well

| Pattern | Where | Why |
|---------|-------|-----|
| CSS `--primary: 24 95% 53%` for orange | `globals.css` | One variable recolours all buttons/focus rings automatically |
| Badge CVA extension (no fork) | `badge.tsx` | `success`/`warning`/`danger`/`muted` variants added without touching shadcn defaults |
| URL-driven filter state | `sales-filters.tsx` | Filters are shareable/bookmarkable; no React state duplication |
| `cn()` for all conditional classes | Throughout | `tailwind-merge` deduplicates conflicting Tailwind classes correctly |
| RSC `Promise.all` on data pages | `dashboard/page.tsx`, `inventory/page.tsx` | Parallel fetches, no waterfall, no client JS for data |
| `Suspense` boundary at page root | `sales/page.tsx` | Required by App Router for `useSearchParams()`; correctly placed |
| `[&>div]:bg-green-500` Progress override | `target-achievement.tsx` | Correct shadcn pattern; avoids inline styles |
| `forwardRef` + `displayName` on all primitives | `ui/*.tsx` | Enables React DevTools and Radix composition |
| `NavTabs` with `usePathname()` | `nav-tabs.tsx` | URL-driven active state; no prop drilling |

---

### Gitignore Check — New Untracked Files

| File | Verdict |
|------|---------|
| `docs/frontend.md` | ✅ Commit — project documentation |
| `frontend/components.json` | ✅ Commit — shadcn config; required for `npx shadcn add` |
| `frontend/components/ui/*.tsx` | ✅ Commit — owned shadcn component copies |

No new files need to be gitignored.

---

### Action Plan

| Priority | Action | Effort |
|----------|--------|--------|
| 🟡 M-1 | `npm uninstall @tanstack/react-table` | 2 min |
| 🟡 M-2 | Add 50 MB size guard in `upload/page.tsx` before POST | 5 min |
| 🟡 M-3 | Add row count below product table when > 50 rows | 5 min |
| 🟡 M-4 | Switch `Promise.all` → `Promise.allSettled` in `sales/page.tsx` | 15 min |
| 🟢 L-1 | Fix React import in `skeleton.tsx` | 2 min |
| 🟢 L-2 | Extract Recharts colours to `lib/chart-colors.ts` | 10 min |
| 🟢 L-3 | Add `console.error` in upload catch block | 2 min |
| 🟢 L-4 | Switch NavTabs to `startsWith` match | 3 min |
| 🟢 L-5 | Add `frontend/.gitattributes` for LF normalisation | 5 min |

---

## Review: 2026-02-25

**Branch**: `feature/consolidate-price-scrapers`
**Reviewer**: Claude Code (automated, read-only)
**Scope**: 12 modified files + 6 untracked new files — Actions dashboard (new) + backend metadata API + config

---

### Files Reviewed

**Modified (12):**
`backend/app/api/metadata.py` (+224 lines — 3 new endpoints),
`backend/app/config.py` (DATABASE_URL support + Pydantic v2 model_config),
`backend/app/database.py` (minor: `get_db_url()` call),
`backend/app/main.py` (guarded `create_all`),
`backend/app/schemas/metadata.py` (+70 lines — 6 new schemas),
`frontend/components/ui/nav-tabs.tsx` (+1 line — Actions tab),
`frontend/lib/api.ts` (+34 lines — 2 interfaces + `actionItems()`),
`docs/` (4 doc files — audit-docs follow-up)

**New — Untracked (6):**
`frontend/app/dashboard/actions/page.tsx`,
`frontend/app/dashboard/actions/pipeline-health-section.tsx`,
`frontend/app/dashboard/actions/sku-gaps-section.tsx`,
`frontend/app/dashboard/actions/unmapped-section.tsx`,
`frontend/components/ui/dialog.tsx`,
`docs/branches.md`

---

### Executive Summary

This diff introduces the **Actions dashboard** — a new page surfacing data pipeline health, portal mapping coverage gaps, portal SKUs without product mappings, and a "link SKU" workflow that writes directly to the database. The code is well-structured with a clear server-component / client-component split, proper confirmation steps before mutations, and good error degradation patterns. The most important findings are: TypeScript interface duplication across three files (same types defined locally instead of imported from `api.ts`), a fragile multi-depth CSV path probe that should use config/env, and an accessibility gap in the custom Dialog component (no focus trap). No security issues — the mutation endpoint uses parameterised queries throughout.

---

## 🟡 Medium Issues

---

**M-1 · Interface duplication — `pipeline-health-section.tsx`, `sku-gaps-section.tsx`, `unmapped-section.tsx`**

All three client components define their own local TypeScript interfaces that duplicate types already exported from `frontend/lib/api.ts`:

| Component | Local interface | Already in `api.ts` |
|-----------|----------------|----------------------|
| `pipeline-health-section.tsx:11–21` | `PortalImportHealth`, `ImportFailure` | ✅ Exported |
| `sku-gaps-section.tsx:14–18` | `PortalSkuGap` | ✅ Exported |
| `unmapped-section.tsx:14–17` | `UnmappedProduct` | ✅ Exported |

If a field is added to the backend schema and updated in `api.ts`, it won't automatically be reflected in the local interfaces — silent drift.

*Suggestion*: Import from `@/lib/api` instead of re-declaring:
```tsx
import type { PortalImportHealth, ImportFailure } from "@/lib/api"
```

---

**M-2 · `backend/app/api/metadata.py` — `_find_gaps_csv()` fragile depth-probe**

```python
def _find_gaps_csv() -> Path | None:
    here = Path(__file__).resolve()
    for depth in (2, 3, 4):
        candidate = here.parents[depth] / "data" / "source" / "mapping_gaps.csv"
        if candidate.exists():
            return candidate
    return None
```

Walking `parents[2..4]` is fragile: the correct depth changes if the file is ever moved, and the function silently returns `None` if the depth is wrong (wrong Docker volume mount, different layout). `settings.raw_data_path` already tracks the data root — a config-relative path would be more reliable and consistent with the rest of the codebase.

*Suggestion*: Add a `source_data_path: str = "./data/source"` setting and use:
```python
from ..config import settings
from pathlib import Path as _P

def _find_gaps_csv() -> _P | None:
    p = _P(settings.source_data_path) / "mapping_gaps.csv"
    return p if p.exists() else None
```

---

**M-3 · `sku-gaps-section.tsx:150` — Array index in React key**

```tsx
{skuGaps.map((row, i) => (
  <TableRow key={`${row.portal}-${row.portal_sku}-${i}`} ...>
```

`portal_sku` is unique per portal (`UNIQUE (portal_id, portal_sku)` in the DB), so `${row.portal}-${row.portal_sku}` is already a stable unique key. Adding `i` makes React treat list reordering as identity changes, causing unnecessary re-renders.

*Suggestion*: `key={`${row.portal}-${row.portal_sku}`}` — drop the index.

---

**M-4 · `pipeline-health-section.tsx:48–53` — No loading state for failure details fetch**

```tsx
useEffect(() => {
  fetch(`${BASE}/api/metadata/import-failures`)
    .then(r => r.ok ? r.json() : [])
    .then(setFailures)
    .catch(() => {})
}, [])
```

There is no loading indicator. When a user clicks to expand a portal row with failures, the detail panel briefly shows **"No detailed failure records found."** while the data is still in-flight. This appears as a false empty state until the fetch resolves.

*Suggestion*: Track a `loading` boolean; show a spinner or "Loading…" text in the expanded panel until the fetch completes.

---

**M-5 · `unmapped-section.tsx:87–88` — `displayName()` derives portal name from slug incorrectly**

```tsx
const displayName = (slug: string) =>
  slug.charAt(0).toUpperCase() + slug.slice(1).replace(/_/g, " ")
```

`"amazon_pi"` → `"Amazon pi"` (lowercase `pi`). The `portals` table has a `display_name` column (`"Amazon PI"`) that is already returned by the API in `missing_portals` (the display name string). However `missing_portal_slugs` only carries slugs, so the dropdown has to derive display names from slugs — losing casing information.

*Suggestion*: Return a `missing_portal_map: { slug: display_name }` from the API, or return `missing_portals` as a JSON array of `{ slug, display_name }` pairs instead of a plain comma-separated string.

---

**M-6 · `backend/app/api/metadata.py` — Duplicate FastAPI imports**

```python
from fastapi import APIRouter, Depends, Query   # line 5
...
from fastapi import HTTPException               # line 11 — separate import added later
```

Two separate `from fastapi import` statements. Minor but inconsistent with the rest of the codebase.

*Suggestion*: Merge into one: `from fastapi import APIRouter, Depends, HTTPException, Query`

---

## 🟢 Low Issues

---

**L-1 · `frontend/components/ui/dialog.tsx` — No focus trap (accessibility)**

The custom Dialog component handles the Escape key manually but does not trap focus. Keyboard-only users can Tab through elements behind the backdrop while the dialog is open — WCAG 2.1 SC 2.1.2 violation. The dialog also lacks `role="dialog"` and `aria-modal="true"`.

Since this is an internal ops tool, the impact is limited. A quick fix would be to use the Radix `@radix-ui/react-dialog` primitive (already available as a peer dep via shadcn) rather than a custom implementation.

*Suggestion (if accessibility matters)*: Replace with a `Dialog` built on `@radix-ui/react-dialog`, which provides focus trapping, scroll locking, and ARIA attributes out of the box.

---

**L-2 · `sku-gaps-section.tsx:51–64` — Full product list fetched client-side for search**

```tsx
useEffect(() => {
  fetch(`${BASE}/api/sales/products`)
    .then(r => r.ok ? r.json() : [])
    .then(setProducts)
    .catch(() => {})
}, [])
```

The entire product catalogue (520+ rows) is loaded into the client once on component mount, then filtered in-browser. At 520 items this is fine (<50 KB). Flag for awareness if the product catalogue grows significantly — above ~5 000 items a server-side search endpoint would be preferable.

---

**L-3 · `get_import_failures` — no minimum on `limit` parameter**

```python
def get_import_failures(limit: int = Query(100, le=500), db: Session = Depends(get_db)):
```

`le=500` caps the maximum but there's no `ge=1`. `limit=0` or `limit=-1` are accepted and produce a `LIMIT 0` or `LIMIT -1` query (PostgreSQL treats negative `LIMIT` as unlimited — unbounded result set).

*Suggestion*: `limit: int = Query(100, ge=1, le=500)`

---

**L-4 · `page.tsx:10` — `revalidate = 60` may over-query the database**

```tsx
export const revalidate = 60
```

The `action-items` endpoint runs three aggregate SQL queries including a `CROSS JOIN` on products × portals. Re-fetching every 60 seconds in production is fine for a lightly used internal dashboard but could be relaxed to `300` (5 min) — the data changes at most once per scraper run (every few hours).

---

**L-5 · `api.ts` — packed interface style inconsistent with rest of file**

The six new interfaces use multiple properties per line:
```typescript
export interface PortalImportHealth {
  portal_name: string; display_name: string
  last_import_at: string | null; last_status: string | null
```

All prior interfaces in `api.ts` use one property per line. Inconsistent but harmless.

---

### ✅ Patterns Done Well

| Pattern | Where | Why |
|---------|-------|-----|
| `catch(() => null)` page-level degradation | `actions/page.tsx:13` | API down → `noApiData=true` → informative banner instead of crash |
| Confirmation step before mutations | `sku-gaps-section.tsx`, `unmapped-section.tsx` | Two-step review flow prevents accidental DB writes |
| `db.flush()` → `db.commit()` ordering | `metadata.py:create_portal_mapping` | Products INSERT returns ID before the mapping INSERT references it |
| `ON CONFLICT DO UPDATE` upsert | `metadata.py:create_portal_mapping` | Safe re-submission: idempotent, no duplicate product rows |
| `!saving` guard on `onClose` | Both dialog components | Prevents closing dialog mid-save |
| Parameterised queries throughout | `metadata.py` | All user-supplied values go through `{"key": value}` binding — no SQL injection |
| Server component data fetch + client subcomponents | `actions/page.tsx` | Static data (coverage, totals) is RSC; interactive expandable rows are client components — correct App Router pattern |
| `settings.get_db_url()` with `DATABASE_URL` override | `config.py`, `database.py` | Supabase connection string can be passed as a single URL, matching how Supabase recommends connecting |
| `try/except` around `create_all` | `main.py` | Server starts even when DB is temporarily unreachable — avoids cold-start failures |

---

### Gitignore Check — New Untracked Files

| File | Verdict |
|------|---------|
| `docs/branches.md` | ✅ Commit — project documentation |
| `frontend/app/dashboard/actions/*.tsx` | ✅ Commit — frontend source |
| `frontend/components/ui/dialog.tsx` | ✅ Commit — UI component |

No new files should be gitignored.

---

### Prioritised Action Plan

| Priority | Action | Effort |
|----------|--------|--------|
| 🟡 M-1 | Import shared types from `@/lib/api` in 3 client components (remove local re-declarations) | 10 min |
| 🟡 M-2 | Replace `_find_gaps_csv()` depth probe with a `source_data_path` config setting | 10 min |
| 🟡 M-3 | Remove index from `sku-gaps-section.tsx` row key | 2 min |
| 🟡 M-4 | Add `loading` state to `PipelineHealthSection` failures fetch | 5 min |
| 🟡 M-5 | Return `{ slug, display_name }` pairs from API instead of plain slug string | 15 min |
| 🟡 M-6 | Merge duplicate `from fastapi import` lines in `metadata.py` | 1 min |
| 🟢 L-1 | Add `role="dialog"` + `aria-modal` to `dialog.tsx`; consider Radix Dialog long-term | 5 min |
| 🟢 L-3 | Add `ge=1` to `limit` in `get_import_failures` | 1 min |

---

## Review: 2026-02-25 — fix/code-review-issues branch (code-review fixes batch)

**Branch**: `fix/code-review-issues`
**Reviewer**: Claude Code (automated, read-only)
**Scope**: 33 modified files + 4 untracked new files — systematic remediation of previous code review findings

---

### Files Reviewed

**Modified (33):**
`.gitignore`,
`backend/app/api/imports.py`, `metadata.py`, `sales.py`, `uploads.py`,
`backend/app/config.py`, `backend/app/database.py`,
`backend/app/schemas/sales.py`,
`backend/app/utils/excel_parsers.py`, `portal_resolver.py`,
`frontend/app/dashboard/actions/page.tsx`, `pipeline-health-section.tsx`, `sku-gaps-section.tsx`, `unmapped-section.tsx`,
`frontend/app/dashboard/page.tsx`, `sales/page.tsx`, `upload/page.tsx`,
`frontend/components/charts/bar-chart.tsx`,
`frontend/components/sales/category-chart.tsx`, `kpi-strip.tsx`, `portal-breakdown.tsx`, `portal-daily-table.tsx`, `product-table.tsx`, `revenue-trend.tsx`, `target-achievement.tsx`,
`frontend/components/ui/dialog.tsx`, `nav-tabs.tsx`, `skeleton.tsx`,
`frontend/lib/api.ts`, `frontend/package.json`, `frontend/package-lock.json`,
`scrapers/orchestrator.py`

**Deleted (1):** `scripts/replicate_to_supabase.py`

**New — Untracked (4):**
`frontend/.gitattributes`, `frontend/lib/chart-colors.ts`, `frontend/lib/format.ts`, `scripts/find_missing_dates.py`

---

### Executive Summary

This diff is a systematic code quality pass across the full stack — 25+ individual fixes applied to backend, frontend, and scrapers. The changes are well-executed with no regressions introduced and substantial improvements to security, correctness, and DX. **One critical issue** was introduced in a new utility script (`scripts/find_missing_dates.py`): a hardcoded production database password in plaintext. All other findings are medium or low priority. The new shared utilities (`format.ts`, `chart-colors.ts`) are clean and well-structured. The dialog accessibility improvements and interface formatting normalisation are high-quality.

---

## 🔴 Critical Issues

---

### C-1 · `scripts/find_missing_dates.py:26` — Hardcoded production database credentials

```python
DATABASE_URL = "postgresql://postgres:6LkqSuEXJ0zNLOCP@[2406:da1c:f42:ae08:77f3:eb0d:4af6:3eaf]:5432/postgres"
```

**Problem**: A real production password (`6LkqSuEXJ0zNLOCP`) and IPv6 host address are hardcoded as a module-level constant. If this file is committed, the credential is permanently in git history even after removal. The Supabase IPv6 endpoint is also exposed.

**Suggestion**: Read from environment:
```python
import os
from dotenv import load_dotenv
load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]  # fail fast if not set
```

---

## 🟡 Medium Issues

---

### M-1 · `imports.py:191` — `import_inventory` missing row count limit

`import_sales` guards against oversized payloads:
```python
if len(body.rows) > 10_000:
    raise HTTPException(status_code=400, detail="Too many rows (max 10,000 per request)")
```
`import_inventory` has no equivalent guard. A single POST can submit unlimited rows.

**Suggestion**: Add the same limit check to `import_inventory` for consistency.

---

### M-2 · `uploads.py:543–548` — `_insert_city_sales` silently rolls back mid-transaction

```python
except IntegrityError:
    db.rollback()
    logger.warning("IntegrityError inserting city_daily_sales — some rows skipped")
```

`_insert_city_sales` is called without a surrounding savepoint. If it raises `IntegrityError` and calls `db.rollback()`, the session is cleared — but `_process_sales` then continues to insert `daily_sales` rows and commits successfully. Result: `daily_sales` is populated but `city_daily_sales` is silently empty. The user receives `inserted=N` with no indication that city-level data was lost.

**Suggestion**: Use a `SAVEPOINT` via `db.begin_nested()` to isolate the city_sales insert, so a failure only rolls back that sub-transaction without affecting the outer daily_sales commit. Or surface the failure as an entry in `errors[]`.

---

## 🟢 Low Issues

---

### L-1 · `scripts/find_missing_dates.py` — untracked, needs gitignore decision

The script is a useful diagnostic utility comparable to other committed `scripts/` tools. It should be committed once C-1 (hardcoded credential) is fixed. It auto-saves output to `data/source/missing_dates.csv` — that path is covered by the global `*.csv` gitignore rule, so the CSV output will be ignored correctly.

**Suggestion**: Fix C-1, then add the script to git. No gitignore entry needed for the script itself.

---

### L-2 · `format.ts:5–10` — `fmtRevenue` doesn't handle negative values

```typescript
export function fmtRevenue(v: number): string {
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`;
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(1)} K`;
  return `₹${Math.round(v)}`;
}
```

`fmtRevenue(-150000)` returns `₹-150000` — the rupee sign precedes the negative sign and no L/K suffix is applied. In practice revenue is never negative in this codebase, but if discount amounts or deltas are ever formatted with this function, the output would be visually incorrect.

**Suggestion**: Add a guard: `if (v < 0) return \`-${fmtRevenue(-v)}\`` as the first line.

---

### L-3 · `uploads.py:408` — inline import of private function `_parse_date_ymd`

```python
from ..utils.excel_parsers import _parse_date_ymd
```

The underscore prefix signals module-private. This import is buried inside `_process_master_excel()` rather than at the module top. Low risk since both files are in the same package, but inconsistent with conventions.

**Suggestion**: Either promote `_parse_date_ymd` to a public function, or move the import to the module top level alongside the existing `from ..utils.excel_parsers import ColumnMismatchError, parse_file`.

---

### L-4 · `excel_parsers.py:462` — `parse_master_excel` retains `iterrows()` with `.iloc`

The `iterrows()` → `to_dict("records")` optimisation was correctly applied to all 8 portal parsers. The remaining `iterrows()` in `parse_master_excel` was intentionally skipped because it uses positional `.iloc` indexing via a `col_map` object. This is documented behaviour, but worth noting as a future refactor opportunity: storing column positions as indices is fragile if the upstream `iter_sheets()` logic ever changes sheet structure.

---

## ✅ Patterns Done Well

| Pattern | Where | Why |
|---------|-------|-----|
| `TOOLTIP_STYLE` / `CHART_COLORS` constants | `lib/chart-colors.ts` | Single source of truth for Recharts colours across 4 components — correct abstraction level |
| `fmtRevenue` extracted to `lib/format.ts` | 7 sales components | Eliminates 7 near-identical local copies; consistent INR formatting |
| `Promise.allSettled` with per-result guards | `sales/page.tsx` | Partial API failure no longer blanks the entire dashboard |
| Lazy `useState` initialisers | `sales/page.tsx:44–45` | Prevents SSR/client date mismatch near midnight — correct React pattern |
| `role="dialog"` + `aria-modal` + `aria-labelledby` | `dialog.tsx` | Proper ARIA semantics; screen readers will announce dialog title on open |
| `db_ssl: bool = False` gate for `sslmode=require` | `database.py`, `config.py` | Allows local Docker dev without SSL while keeping cloud Postgres secure |
| `datetime.now(timezone.utc)` everywhere | `imports.py`, `uploads.py` | Correct UTC-aware timestamps; removes Python 3.12 deprecation warning |
| Client-side 50 MB + extension guard in `pickFile` | `upload/page.tsx` | Instant feedback before network round-trip; mirrors backend limits |
| `ge=1` on `limit` param | `metadata.py` | Prevents `LIMIT 0` / negative-LIMIT unbounded queries |
| `to_dict("records")` in all portal parsers | `excel_parsers.py` | 10–100× faster row iteration vs `iterrows()` |
| Monthly Drive folder Slack trigger | `orchestrator.py` | `REPORTS_DRIVE_FOLDER_URL` env guard makes it a safe no-op by default |

---

## Gitignore Check — New Untracked Files

| File | Verdict |
|------|---------|
| `frontend/.gitattributes` | ✅ Commit — enforces LF endings for the frontend tree |
| `frontend/lib/chart-colors.ts` | ✅ Commit — shared Recharts constants |
| `frontend/lib/format.ts` | ✅ Commit — shared INR formatter |
| `scripts/find_missing_dates.py` | ⚠️ Fix C-1 first, then commit |

---

## Post-Deployment Recommendations — 2026-02-25

### 1. Custom Domain
The production frontend URL (`solara-frontend-891651347357.asia-south1.run.app`) is auto-generated and unwieldy. Map a custom domain such as `dashboard.solara.in` to the Cloud Run service — free via GCP Console → Cloud Run → **Manage Custom Domains**.

### 2. Backend URL Exposure
`NEXT_PUBLIC_API_URL` is baked into the frontend JS bundle at build time and is visible in the browser source. This is acceptable for an internal dashboard but should be addressed before any public-facing use:
- **Option A**: Add API key / token authentication to the FastAPI backend
- **Option B**: Proxy all API calls through Next.js API routes (`/api/...`) so the backend URL is never exposed to the client

---

## Prioritised Action Plan

| Priority | Action | Effort |
|----------|--------|--------|
| 🔴 C-1 | Remove hardcoded `DATABASE_URL` from `find_missing_dates.py`; read from env | 2 min |
| 🟡 M-1 | Add `len(body.rows) > 10_000` guard to `import_inventory` | 2 min |
| 🟡 M-2 | Use `db.begin_nested()` savepoint in `_insert_city_sales` to isolate the rollback | 10 min |
| 🟢 L-2 | Add negative-value guard to `fmtRevenue` in `format.ts` | 2 min |
| 🟢 L-3 | Move `_parse_date_ymd` import to module top level in `uploads.py` | 1 min |
