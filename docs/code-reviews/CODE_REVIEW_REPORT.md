# SolaraDashboard — Code Review Reports

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
