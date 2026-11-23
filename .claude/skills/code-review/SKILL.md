---
name: code-review
description: Child of /commit (Step 2). Also works standalone. Reviews unstaged and untracked code changes for quality, security, performance, test coverage, and debug artifacts. Deduplicates against existing open issues. Only appends to docs/code-review.md when there is something to write. Skips the open-issues prompt when 0 issues exist. Uses session-prefixed IDs. Never removes issues — only marks FIXED.
---

**READ-ONLY on source code.** Appends findings to `docs/code-review.md`. Does not modify source files.

---

## Step 0: Orientation

Read `docs/manifest.md` if it exists — helps identify each file's role accurately.

---

## Step 1: Triage Existing Issues

Read `docs/code-review.md`. Count all `OPEN` issues.

**N > 0:**
> "N open issues from previous sessions. Any now fixed? List IDs and I'll mark them FIXED."

Mark confirmed-fixed as `FIXED YYYY-MM-DD`. Never delete a row.

**N = 0:** Skip prompt → Step 2.

File absent → create fresh in Step 7.

---

## Step 2: Get Changed Files

```bash
git status
git diff
git ls-files --others --exclude-standard
```

Collect unstaged modified + untracked files (not yet committed).

---

## Step 3: Read Each File

- ≤ 300 lines: read fully.
- > 300 lines: read changed function(s) + immediate callers/callees.
- Identify role via `docs/manifest.md`: scraper, API route, importer, frontend component, migration, etc.

---

## Step 4: Quality Checks

### General
- Consistent formatting and naming
- Error handling and error messages
- Type hints (Python) or type definitions (TypeScript)
- Unused or missing imports

### DRY
- Duplicate blocks extractable into functions
- Hardcoded values that should be constants

### Performance
- **Database**: N+1 queries, `SELECT *`, missing pagination
- **Scrapers**: repeated calls, missing timeouts/retry logic
- **Memory**: large datasets loaded fully instead of streamed

### Security
- Hardcoded credentials, API keys, secrets — 🔴 Critical
- SQL injection (raw SQL with user input — use parameterized queries or SQLAlchemy)
- Missing input validation on API endpoints
- Sensitive data in logs or API responses
- `print()` exposing credentials/session data — 🔴 Critical; otherwise 🟡 Medium

### Debug Artifacts
- Any `print()`, `console.log()`, `debugger`, `pdb.set_trace()` in production code
- 🟡 Medium (🔴 if printing credentials, tokens, or passwords)

### Test Coverage
- For each new function, class, or endpoint: check if a test exists:
  ```bash
  # Linux/Mac
  find tests/ backend/tests/ -name "test_*.py" 2>/dev/null | xargs grep -l "<module-name>" 2>/dev/null
  # Windows PowerShell
  Get-ChildItem -Recurse -Path tests/,backend/tests/ -Filter "test_*.py" -ErrorAction SilentlyContinue | Select-String -Pattern "<module-name>"
  ```
- No test found → flag 🟡 Medium with suggestion.

### Gitignore Check
Untracked files that should be gitignored:
- `__pycache__/`, `*.pyc`, `.next/`, `node_modules/`
- `.env`, `.env.local`
- `scrapers/sessions/` (browser profiles)
- `*.csv`, `*.xlsx` in `data/`

---

## Step 5: Deduplicate

Before logging, check existing OPEN issues for:
- Same file path, AND
- Similar description (same bug, function, or security concern)

Match found → skip. Note: "Issue in `file.py` ~N already logged as `<ID>`."

---

## Step 6: Assign ID, Priority, Environment

Per new issue:

**ID:** `{YYYY-MM-DD}-{NN}` — zero-padded, no upper limit (01, 02 … 10, 11 …)

**Priority:** 🔴 Critical / 🟡 Medium / 🟢 Low

**Environment:** 🔴 Prod only / 🟢 Dev OK / 🟡 Both

**Status:** `OPEN`

---

## Step 7: Append to `docs/code-review.md`

**Append only if:** new issues found, or issues marked FIXED. Otherwise leave unchanged.

Never delete/overwrite previous entries. Append:

```markdown
# Code Review Log

<!-- Issues are never deleted. Mark fixed with: FIXED YYYY-MM-DD -->

---

## Session: YYYY-MM-DD — <branch-name>

### Files Reviewed
- `path/to/file.py`

### New Issues

| ID | File | Line | Priority | Env | Issue | Status |
|----|------|------|----------|-----|-------|--------|
| 2026-05-25-01 | `scrapers/zepto_scraper.py` | 42 | 🔴 Critical | 🔴 Prod | Hardcoded API key `ZEPTO_KEY = "abc123"` | OPEN |
| 2026-05-25-02 | `backend/app/api/sales.py` | 87 | 🟡 Medium | 🟡 Both | Missing pagination — full table scan on `/sales` | OPEN |
| 2026-05-25-03 | `scrapers/blinkit_scraper.py` | 115 | 🟡 Medium | 🟢 Dev | `print(session_data)` debug artifact | OPEN |
| 2026-05-25-04 | `backend/app/api/inventory.py` | — | 🟡 Medium | 🟡 Both | No test for new `GET /inventory/snapshot` endpoint | OPEN |

### Skipped (already logged)
- `scrapers/zepto_scraper.py` ~55 — already logged as `2026-04-10-03`

### Session Summary
- 🔴 Critical: N   🟡 Medium: N   🟢 Low: N  (this session)
- Total OPEN: N
```

FIXED: update Status cell in place. Never remove the row:
```
FIXED 2026-05-25
```

---

## Step 8: Present Results

- New issues grouped by priority.
- Total OPEN across all sessions.
- End: "Findings appended to `docs/code-review.md`. N total open issues."
- Nothing found/fixed: "✅ No new issues. `docs/code-review.md` unchanged."

---

## Project-Specific Notes

- **Scrapers**: Playwright selector robustness; portal UI change handling; session file paths
- **Importers**: column index off-by-one; NaN handling; upsert correctness
- **FastAPI routes**: input validation; auth; correct Pydantic schema
- **Frontend**: API error states; loading states; TypeScript type safety
- Credential/session files in `git diff` → 🔴 Critical immediately
