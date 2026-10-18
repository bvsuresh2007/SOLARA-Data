---
name: update-dashboard
description: Keep the frontend dashboard aligned with latest backend changes. Reads manifest.md for context, discovers dashboard pages dynamically, treats Alembic migrations as high-weight signals, validates TypeScript (with npm install guard), uses cross-platform commands, and suggests /commit when done.
---

**Purpose**: When API endpoints, tables, scrapers, or schema change, update the dashboard — but only for changes with real user-facing value.

---

## Step 0: Orientation

Read `docs/manifest.md` and `CLAUDE.md`:
- Which portals exist and their scraper files
- Available API routes
- Current dashboard structure

---

## Step 1: Find Last Dashboard Update

Discover pages dynamically:

```bash
# Linux/Mac
find frontend/app/dashboard -name "*.tsx" 2>/dev/null

# Windows PowerShell
Get-ChildItem -Path frontend/app/dashboard -Recurse -Filter "*.tsx" -ErrorAction SilentlyContinue
```

Per file found:
```bash
# Linux/Mac
git log --oneline --follow -- <page-path> | head -3

# Windows PowerShell
git log --oneline --follow -- <page-path> | Select-Object -First 3
```

Use the most recent commit hash. Display:
"Dashboard last updated: [hash] on [date]: [message]"

---

## Step 2: Gather Commits Since Last Update

```bash
git log --oneline <last-commit>..HEAD
git diff --stat <last-commit>..HEAD
```

Summarize: N commits, areas changed (scrapers, backend, schema, scripts).

---

## Step 3: Classify Changes

**High weight** (update dashboard):
- New API endpoint or endpoint returning new fields
- New portal scraper (`*_scraper.py` created)
- New Alembic migration adding a table or columns
- New table populated with real data
- Scraper collecting a new metric

**Medium weight** (consider updating):
- Endpoint returns more data / new columns
- Inventory snapshot adds a stock column

**Low weight / skip**:
- Internal refactoring, no API surface change
- Bug fixes with no new data
- Config-only changes
- Alembic migrations adding only indexes or constraints

---

## Step 4: Read Current Dashboard

List and read all pages under `frontend/app/dashboard/`:

```bash
# Linux/Mac
find frontend/app/dashboard -name "*.tsx"

# Windows
Get-ChildItem -Path frontend/app/dashboard -Recurse -Filter "*.tsx"
```

Also read:
- `frontend/lib/api.ts` — existing API calls
- `frontend/components/` — reusable components:
  ```bash
  ls frontend/components/              # Linux/Mac
  Get-ChildItem frontend/components/   # Windows
  ```

---

## Step 5: Identify Updates

Per high/medium-weight change:
1. Is there a visible dashboard location for this?
2. Does a matching API call exist in `frontend/lib/api.ts`?
3. Is data populated? (Migration exists + scraper has run?)

All three yes → update.
API missing → note as "blocked update", skip.

---

## Step 6: Make Updates

- **Match existing style**: component patterns, spacing, imports
- **Reuse components**: check `frontend/components/` first
- **No new npm packages** unless essential (>50 lines to implement) — ask first
- **Plain business labels**: `Zepto`, `Blinkit`, `Amazon` — not DB column names
- Removing a section → ask for confirmation first

---

## Step 7: Verify

**Read-check:** Re-read modified files for syntax errors, missing imports, broken JSX.

**Install dependencies if needed:**
```bash
# Linux/Mac
[ -d frontend/node_modules ] || (cd frontend && npm install)

# Windows PowerShell
if (-not (Test-Path frontend/node_modules)) { Set-Location frontend; npm install; Set-Location .. }
```

**TypeScript check:**
```bash
# Linux/Mac
cd frontend && npx tsc --noEmit

# Windows PowerShell
Set-Location frontend; npx tsc --noEmit; Set-Location ..
```

TypeScript errors → fix before completing. Show error and fix applied.

**Logic check:** Confirm no existing feature was broken.

---

## Step 8: Summary

```
📊 Dashboard Update Report
==========================

Last Dashboard Update: [commit] on [date]
Commits Analyzed: [N]
Pages Discovered: [list]

Changes Made:
─────────────
✅ [description]
   └─ Page: [file]
   └─ Why: [capability surfaced]

Changes Skipped (low weight):
──────────────────────────────
⏭️  [description] — no user-facing impact

Blocked Updates (API not yet available):
─────────────────────────────────────────
⏸️  [description] — needs GET /api/xxx first

Removal Suggestions (requires confirmation):
─────────────────────────────────────────────
⚠️  Consider removing [section] — [reason]

TypeScript:  ✅ No errors  /  ⚠️ N errors fixed

Next Steps:
───────────
1. Confirm / reject removal suggestions
2. Test locally:  cd frontend && npm run dev
3. When satisfied:  /commit
```

---

## Notes

- **API-first**: never update UI for an endpoint that doesn't exist.
- **Portal names**: display names (`Zepto`, `Blinkit`) in UI, not internal constants.
- **Never guess**: verify migration exists AND scraper has run before surfacing data.
- Wait for confirmation before removing any existing dashboard content.
- Internal BI dashboard — data density and accuracy over visual polish.
