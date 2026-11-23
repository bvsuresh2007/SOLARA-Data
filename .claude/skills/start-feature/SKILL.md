---
name: start-feature
description: Pull latest main, create a dated branch with a user-supplied tag prefix, then begin development. Checks for dirty state, pops stash after branch creation, checks for similar existing branches, derives GitHub URL from remote. Reads CLAUDE.md + manifest.md before coding. Usage: /start-feature <tag> [feature description]
---

Bootstraps a feature/fix branch from the latest `main`. Branch format: `{tag}/{YYYY-MM-DD}-{feature-slug}`

Examples:
- `/start-feature feat add inventory export` → `feat/2026-05-25-add-inventory-export`
- `/start-feature fix scraper timeout on blinkit` → `fix/2026-05-25-scraper-timeout-on-blinkit`
- `/start-feature atlas` → `atlas/2026-05-25`

---

## Step 1: Parse Arguments

From `$ARGUMENTS`:
- **First word** = tag prefix (e.g. `feat`, `fix`, `chore`). Required — if missing, stop: "Provide a tag prefix. Usage: `/start-feature <tag> [description]`"
- **Remaining words** = description (optional) — lowercase kebab-case, strip special chars.

Branch name:
- With description: `{tag}/{YYYY-MM-DD}-{slug}`
- Without: `{tag}/{YYYY-MM-DD}`

Date: `Get-Date -Format "yyyy-MM-dd"` (Windows) / `date +%F` (Linux/Mac)

---

## Step 2: Check for Uncommitted Changes

```bash
git status --short
```

If uncommitted changes exist:
> "Uncommitted changes detected. What would you like to do?
> 1. Stash (`git stash`) — restored after branch creation
> 2. Commit first (run `/commit`, then return)
> 3. Proceed anyway (carry them to the new branch)"

Wait; record choice — affects Step 5.

---

## Step 3: Fetch Latest Main

```bash
git fetch origin
git checkout main
git pull origin main
```

If `main` doesn't exist, try `master`. If both fail, stop and list:
```bash
git branch -r
```

---

## Step 4: Check for Branch Name Collision

```bash
# Linux/Mac
git branch --list {branch-name}
git ls-remote --heads origin {branch-name} 2>/dev/null || echo "(remote check skipped — no network)"

# Windows PowerShell
git branch --list {branch-name}
$remoteResult = git ls-remote --heads origin {branch-name} 2>$null
if (-not $?) { Write-Output "(remote check skipped — no network)" }
```

- **Local collision** → append `-2`, `-3`, etc. until free.
- **Remote collision** → ask: "Branch exists on remote. Use a different name, or check it out?"
  - Different name → ask for new slug and rebuild.
  - Check out existing → `git checkout {branch-name} && git pull origin {branch-name}` → skip to Step 7.
- **No network** → proceed; push catches any collision.

---

## Step 5: Create Branch

```bash
git checkout -b {branch-name}
```

**If user chose Stash (Step 2):** pop now:
```bash
git stash pop
```

Stash pop conflicts → stop, show conflicted files, ask to resolve.

---

## Step 6: Check for Similar Existing Branches

```bash
# Linux/Mac
git branch -r | grep -i {feature-slug}

# Windows PowerShell
git branch -r | Select-String -Pattern {feature-slug} -SimpleMatch
```

If found:
> "Similar branch exists: `origin/<branch>`. Related work or duplicate? Check it out instead?"

Wait for answer.

---

## Step 7: Show Branch Info

```bash
git remote get-url origin
```

Convert SSH → HTTPS if needed.

```
Branch created: {branch-name}
GitHub:  https://github.com/<org>/<repo>/tree/{branch-name}
```

**No description:** "Branch ready. What are the requirements? Describe what to build." Stop and wait.

**Description given:** "Branch `{branch-name}` ready. Starting: _{feature description}_" → Step 8.

---

## Step 8: Understand the Codebase

Before writing code:
1. Read `CLAUDE.md` for conventions, structure, rules.
2. Read `docs/manifest.md` for project layout.
3. Identify area: Scrapers → `scrapers/` | Backend → `backend/app/` | Frontend → `frontend/` | DB → `database/`, `scripts/` | Shared → `shared/`
4. Read files most likely affected. Understand existing patterns.

---

## Step 9: Develop

Key rules (from `CLAUDE.md`):
- **Python**: type hints, no hardcoded secrets, extend base classes
- **FastAPI routes**: validate input, Pydantic schemas, correct router
- **Scrapers**: extend `BaseScraper`, session-file auth, existing Playwright patterns
- **Frontend**: TypeScript strict mode, `frontend/lib/api.ts` patterns
- **Database**: Alembic migrations for schema changes — never modify `init_db.sql` directly
- **Never stage** `.env`, `data/source/`, `scrapers/sessions/`

Implement incrementally:
1. Schema / model changes (if needed)
2. Backend logic
3. API endpoint
4. Frontend integration (if needed)
5. Verify each layer before proceeding:
   - Backend: `curl` or FastAPI `/docs`
   - Frontend: `npm run dev` in browser
   - Scraper: `--dry-run` or test account

---

## Step 10: Confirm Completion

Summarize:
- Files created / modified
- How to test (specific commands)
- Manual steps needed (e.g. `alembic upgrade head`, Docker restart)
- New env vars → update `.env.example` (keys + description comments, no values)
- Suggest `/commit` when ready

---

## Branch Tag Reference

| Tag | Use for |
|-----|---------|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Restructure, no behavior change |
| `chore` | Config, deps, tooling |
| `docs` | Documentation only |
| Any custom tag | Team-specific |
