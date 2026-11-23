---
name: doc-consolidate
description: Child of /commit (Step 4). Also works standalone (invokes full audit-docs first). Merges redundant docs, resolves contradictions, archives/deletes obsolete docs, moves misplaced project files, slims CLAUDE.md, and updates docs/manifest.md from actual project structure. Excludes docs/archive/ from scans. Always asks before deleting or assuming.
---

Actively applies structural doc changes. Child of `/commit`: uses `audit-docs` findings from context. Standalone: invokes `audit-docs` first.

**Ownership:**
- This skill: merge docs, archive, delete, move project source files, slim `CLAUDE.md`, update `manifest.md`.
- `check-temp-files`: temp/backup + `.env*` detection.

**Rule: ask before any destructive or ambiguous action. Never assume.**

---

## Step 0: Orientation

Read `docs/manifest.md` and `CLAUDE.md` before making changes.

---

## Step 1: Load Audit Findings

**Child of `/commit`:** Use `audit-docs` findings in context. Do not re-scan.

**Standalone:** Invoke `audit-docs` now. Its output (moves, stale fixes, merge/archive/delete candidates) feeds the steps below.

---

## Step 2: Move Misplaced Project Files

Scan root for source files belonging in a subdirectory:
- Linux/Mac: `ls -1`
- Windows: `Get-ChildItem -Depth 0`

Do not re-flag temp/backup files (`check-temp-files`' job).

**Move candidates:**
- `.py` scripts at root that clearly belong in `scrapers/`, `scripts/`, or `backend/` (e.g. `ingest_daily.py`, `auth_gmail.py`)
- Config files that belong in a service directory

Per candidate, ask:
> "`ingest_daily.py` at root looks like a scraper script. Move to `scrapers/` or `scripts/`? Or keep at root?"

Never move without confirmation. Use `git mv`. Update references in `CLAUDE.md` and `docs/manifest.md`.

---

## Step 3: Merge Redundant Docs

Per merge candidate:
> "I can merge `docs/X.md` into `docs/Y.md` — both cover the same topic. Proceed?"

After confirmation:
- Read both files fully before writing — no content loss.
- Delete secondary: `git rm docs/X.md`
- Update cross-references in `CLAUDE.md` and other docs.
- Notify: "Merged `docs/X.md` into `docs/Y.md`."

---

## Step 4: Contradiction Resolution

For conflicting claims (ports, auth methods, schema columns, env var names): show both passages side-by-side. Check source code first — ask only if code is also ambiguous. Update both files once resolved.

---

## Step 5: Apply Remaining Changes

**STALE** — Update by reading source files. Ask before rewriting large sections.

**ARCHIVE** — Move to `docs/archive/`:
- Windows: `New-Item -ItemType Directory -Force docs\archive` then `git mv docs\X.md docs\archive\X.md`
- Linux/Mac: `mkdir -p docs/archive && git mv docs/X.md docs/archive/X.md`
- Update old-path references in `CLAUDE.md` and `docs/manifest.md`.

**OBSOLETE** — List all, ask once:
> "These files appear permanently obsolete: `docs/X.md` — [reason]. Delete? (confirm each or 'delete all')"

Delete only with explicit confirmation (`git rm`). Remove deleted-path references from `CLAUDE.md` and `docs/manifest.md`.

---

## Step 6: Slim CLAUDE.md

Read `CLAUDE.md`. Apply conservative trimming:

**Trim:**
- Duplicate sentences repeating the same rule
- Verbose filler: "In order to" → "To"; "It is important to note that" → remove
- Section headers that restate the content
- Example lists where 2 suffice — keep 2
- Notes that repeat a rule already stated

**Never trim:**
- Any concrete instruction, rule, or constraint
- File paths, commands, code snippets
- Section headers needed for navigation
- Project-specific context an agent can't derive from code

After trimming: verify every removed sentence is redundant or derivable. If unsure → leave it.

---

## Step 7: Update `docs/manifest.md`

Keep it short — tables and labels only, no prose.

Derive from actual files at runtime — list only what exists:
```bash
# Linux/Mac
ls -1; ls backend/app/; ls scrapers/; ls frontend/app/
ls docs/   # exclude archive/

# Windows
Get-ChildItem -Depth 0
Get-ChildItem backend/app/; Get-ChildItem scrapers/; Get-ChildItem frontend/app/
Get-ChildItem docs/ | Where-Object { $_.Name -ne 'archive' }
```

Portals: one row per `*_scraper.py` in `scrapers/`.
Docs Index: files directly in `docs/` (not `docs/archive/`).

Write with this structure, populated from real files:

```markdown
# Project Manifest
_Updated: YYYY-MM-DD_

## Structure

\`\`\`
backend/app/
  main.py            # FastAPI entrypoint
  config.py          # Pydantic settings
  database.py        # Engine + session
  models/            # SQLAlchemy ORM models
  schemas/           # Pydantic response schemas
  api/               # Route handlers
scrapers/
  base_scraper.py          # Abstract base (Playwright + retry)
  orchestrator.py          # Runs all scrapers on schedule
  <portal>_scraper.py      # One file per portal (derived from actual files)
  tools/amazon_asin_scraper/   # Standalone ASIN CLI
database/            # init_db.sql + Alembic migrations
frontend/app/        # Next.js pages
frontend/lib/        # API client + utilities
shared/              # Shared Python constants
scripts/             # Seed / import scripts
docs/                # All project documentation (see Docs Index below)
.claude/skills/      # Slash commands
\`\`\`

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI entrypoint |
| `scrapers/orchestrator.py` | Runs all scrapers |
| `frontend/app/dashboard/page.tsx` | Dashboard home |
| `frontend/lib/api.ts` | API client |
| `database/init_db.sql` | DB schema |
| `docker-compose.yml` | Start all services |
| `scrapers/tools/amazon_asin_scraper/main.py` | ASIN CLI |

## Portals

| Portal | Scraper | Auth |
|--------|---------|------|
(one row per *_scraper.py found in scrapers/ — portal name, filename, auth method)

## Docs Index

| Doc | Covers |
|-----|--------|
(one row per file in docs/ excluding archive/ — filename and one-line purpose)
```

**Update only changed sections.** Goal: keep the file small.

---

## Step 8: Report

```
📚 Doc Consolidation Report
────────────────────────────
Files moved:      N  →  (list)
Merged:           N  →  (list)
Archived:         N  →  (list)
Deleted:          N  →  (list — only after confirmation)
Updated (stale):  N  →  (list)
Deferred:         N  →  awaiting user

✂️  CLAUDE.md slimmed  →  was ~N lines, now ~N lines
🗂️  manifest.md updated  →  docs/manifest.md
```

---

## Notes

- `docs/code-review.md` is owned by `code-review` — do not edit it here.
- `docs/archive/` is excluded from all inventory, scan, and manifest steps.
- After any move, archive, or deletion: update references in `CLAUDE.md` and `docs/manifest.md`.
- `docs/manifest.md` is derived from reality — never add entries for files that don't exist.
