---
name: update-dashboard
description: Keep the frontend dashboard pages aligned with latest backend changes. Analyzes git history since the last dashboard update, identifies high-value changes to surface in the UI, and updates frontend/app/dashboard/ accordingly.
---

**Purpose**: When new API endpoints, data tables, scrapers, or schema changes are added, keep the dashboard reflecting them — but only for changes that carry real user-facing value.

---

## Step 1: Find When the Dashboard Was Last Updated

```bash
git log --oneline --follow -- frontend/app/dashboard/page.tsx | head -3
git log --oneline --follow -- frontend/app/dashboard/sales/page.tsx | head -3
git log --oneline --follow -- frontend/app/dashboard/inventory/page.tsx | head -3
```

Extract the most recent dashboard commit hash and display:
"Dashboard was last updated in commit [hash] on [date]: [message]"

## Step 2: Gather All Commits Since Last Dashboard Update

```bash
git log --oneline <last-dashboard-commit>..HEAD
git diff --stat <last-dashboard-commit>..HEAD
```

Summarize: number of commits, which areas changed (scrapers, backend API, schema, scripts).

## Step 3: Deep Analysis of Changes

For each changed file/area:

**High weight** (dashboard should reflect this):
- New API endpoint added or existing endpoint returns new fields
- New portal scraper added
- New table populated with real data (e.g. `product_rankings`, `monthly_targets`)
- Scraper now collects a new metric

**Medium weight** (consider updating):
- Existing endpoint returns more data / new columns
- Inventory snapshot adds a new stock column

**Low weight / skip**:
- Internal refactoring with no API surface change
- Bug fixes that don't add new data
- Config-only changes

## Step 4: Read Current Dashboard Pages

Read completely before making any changes:
- `frontend/app/dashboard/page.tsx`
- `frontend/app/dashboard/sales/page.tsx`
- `frontend/app/dashboard/inventory/page.tsx`
- `frontend/lib/api.ts`

Understand current structure: KPI cards, charts by portal/date, top-SKU tables, inventory alerts, scraping status.

## Step 5: Identify Updates to Make

For each high/medium-weight change, ask:
1. Is there a visible place in the dashboard to surface this?
2. Does a matching API call already exist in `frontend/lib/api.ts`?
3. Is the data actually populated in the DB?

If yes to all three → make the update.
If the API endpoint doesn't exist yet → note as "blocked update" in report, don't touch the frontend.

## Step 6: Make Updates

- **Preserve existing style**: match existing component patterns, spacing, imports
- **Reuse existing components**: `MetricCard`, `BarChart`, `DataTable`, `FilterBar` from `components/`
- **No new npm packages** unless essential
- **Plain business labels** in UI: use `Zepto`, `Blinkit`, `Amazon`, etc. — not DB column names
- When adding new content, suggest removing a less useful section to maintain clarity (ask for confirmation before removing)

## Step 7: Verify Changes

- Re-read modified files for syntax errors
- Check all imports are present
- Verify TypeScript types are consistent
- Confirm page still flows logically

## Step 8: Display Summary

```
📊 Dashboard Update Report
==========================

Last Dashboard Update: [commit] on [date]
Commits Analyzed: [N] since last update

Changes Made:
─────────────
✅ [description]
   └─ Location: [page / section]
   └─ Why: [what new capability this surfaces]

Changes Skipped (low weight):
──────────────────────────────
⏭️  [description] — no user-facing impact

Blocked Updates (API not yet available):
─────────────────────────────────────────
⏸️  [description] — needs GET /api/xxx before frontend can show this

Removal Suggestions (requires your confirmation):
──────────────────────────────────────────────────
⚠️  Consider removing [section] — [reason]

Files Modified:
───────────────
[list]

Next Steps:
───────────
1. Review changes
2. Confirm/reject any removal suggestions
3. cd frontend && npm run dev to test locally
```

## Notes

- **API-first**: never update the UI for a feature whose API endpoint doesn't exist yet
- **Portal names**: use display names (`Zepto`, `Blinkit`, etc.) in UI, not lowercase internal constants
- **Never guess at data**: check whether a table is actually populated before surfacing it
- **Wait for confirmation** before removing any existing dashboard content
- This is an internal BI dashboard — prioritize data density and accuracy over visual polish
