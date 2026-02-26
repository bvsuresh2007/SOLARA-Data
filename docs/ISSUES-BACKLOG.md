# Issues Backlog

Extracted from automated code reviews in [`code-reviews/CODE_REVIEW_REPORT.md`](./code-reviews/CODE_REVIEW_REPORT.md).
Update the **Status** column as issues are resolved. Add new issues as they are discovered.

**Severity key:** 🔴 Critical · 🟡 Medium · 🟢 Low

---

## 🔴 Critical

| ID | File | Issue | Status |
|----|------|-------|--------|
| C-01 | `scripts/backfill_missing_dates.py:62` | Hardcoded production DB credentials in source — `DATABASE_URL` including password and IPv6 host committed to repo. **Rotate password immediately; replace with `os.environ["DATABASE_URL"]`.** | ⬜ Open |

---

## 🟡 Medium

| ID | File | Issue | Status |
|----|------|-------|--------|
| M-01 | `scrapers/easyecom_inventory_scraper.py:349` | `upload_profile("easyecom")` called while browser is still open — should move to `finally` block after `_close_browser()`. Risk: corrupted Drive profile. | ⬜ Open |
| M-02 | `scripts/backfill_run_ids.json` | Ephemeral generated state file committed to repo. Add to `.gitignore`. | ⬜ Open |
| M-03 | `scrapers/easyecom_inventory_scraper.py:28` | Non-standard `importlib.util` import pattern — all other scrapers use the simple two-except pattern. | ⬜ Open |
| M-04 | `scrapers/easyecom_inventory_scraper.py:71` | `logging` accessed via `__import__()` anti-pattern. Add `import logging` at top, use `logging.getLogger(...)` directly. | ⬜ Open |
| M-05 | `scrapers/orchestrator.py` | `populate_all_portal_files` return value semantics unclear — CI only fails on `"failed"` but may silently pass with `"partial"` after real import failures. Verify contract and document when each status is returned. | ⬜ Open |
| M-06 | `backend/app/api/imports.py` | `IntegrityError` catch block returns incorrect `inserted=N` count after rollback — should reset to `inserted=0` and populate `errors`. | ⬜ Open |
| M-07 | `frontend/app/dashboard/sales/page.tsx:432` | `fetchPortalDaily` reads `portals` state before it's populated on first load → `portalName=undefined` → API silently returns wrong portal's data. Guard with `if (!portals.length) return` or read portal slug from URL params. | ⬜ Open |

---

## 🟢 Low

| ID | File | Issue | Status |
|----|------|-------|--------|
| L-01 | `scrapers/easyecom_inventory_scraper.py:55` | `INVENTORY_URL` is a best-guess placeholder — verify against actual EasyEcom Manage Inventory page before first CI run. | ⬜ Open |
| L-02 | `scripts/run_backfill_local.py:96` | No validation that `--start <= --end` — silently runs zero iterations if reversed. Add early exit with error message. | ⬜ Open |
| L-03 | `frontend/app/dashboard/inventory/page.tsx` | `portal_name ?? '#' + portal_id` produces `"#undefined"` when both are null. Fix: `portal_name ?? (portal_id != null ? \`#\${portal_id}\` : '—')`. | ⬜ Open |
| L-04 | `.github/workflows/scraper-backfill.yml:367` | Zepto backfill job missing `GOOGLE_DRIVE_ROOT_FOLDER_ID` env var — add comment confirming intentional omission or add the var. | ⬜ Open |
| L-05 | `scrapers/easyecom_scraper.py` + `easyecom_inventory_scraper.py` | Both scrapers share the same Drive profile key `"easyecom"` — concurrent runs (re-run + scheduled) cause last-writer-wins corruption. Long-term fix: use `"easyecom_inventory"` for the inventory scraper. | ⬜ Open |
| L-06 | `scripts/backfill_missing_dates.py:191` | `cmd_verify(args)` never uses `args` — minor signature inconsistency. | ⬜ Open |
| L-07 | `scripts/backfill_missing_dates.py:38` | Hardcoded date ranges become stale after backfill completes. Consider renaming to `backfill_feb2026.py` to signal it's a one-time artifact. | ⬜ Open |
| L-08 | `scripts/backfill_missing_dates.py:87` | f-string table name in SQL query (`f"SELECT ... FROM {table}"`). Table comes from a hardcoded list so no immediate injection risk, but use `psycopg2.sql.Identifier` to avoid misleading future maintainers. | ⬜ Open |
| L-09 | `frontend/` (6 components) | `fmtRevenue` / `fmt` currency formatter copy-pasted across `kpi-strip`, `portal-breakdown`, `revenue-trend`, `target-achievement`, `category-chart`, `product-table`, `portal-daily-table`. Extract to `frontend/lib/format.ts`. | ⬜ Open |
| L-10 | `backend/app/utils/excel_parsers.py` | `pandas.iterrows()` called in every portal parser — 10–100× slower than `df.to_dict("records")`. Replace for performance. | ⬜ Open |
| L-11 | `backend/app/utils/excel_parsers.py:409` | `sys.path` mutated at request time to import `scripts.excel_reader`. Fragile in multi-worker ASGI. Move shared parsing logic into `backend/app/utils/`. | ⬜ Open |
| L-12 | `backend/app/utils/portal_resolver.py:61` | `city_id()` lookup is case-sensitive while `portal_id()` lowercases. Portal CSVs with inconsistent casing cause silent city mismatches. Apply `.lower()` consistently. | ⬜ Open |
| L-13 | `backend/app/api/imports.py:116` | No row limit on `POST /api/imports/sales` — a single request can submit 100K+ rows. Add `if len(body.rows) > 10_000: raise HTTPException(400, ...)`. | ⬜ Open |
| L-14 | `scripts/replicate_to_supabase.py:262` | f-string SQL with schema-derived column/table names. Not directly user-controllable but violates parameterised query best practice. Use `psycopg2.sql.Identifier`. | ⬜ Open |

---

## Resolved

| ID | File | Issue | Resolved in | Notes |
|----|------|-------|-------------|-------|
| — | — | — | — | Move resolved items here |

---

*Source: [`code-reviews/CODE_REVIEW_REPORT.md`](./code-reviews/CODE_REVIEW_REPORT.md) · Reviews: 2026-02-24, 2026-02-25*
