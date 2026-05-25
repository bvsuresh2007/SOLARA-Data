---
name: audit-docs
description: Child of /commit (Step 3). Also works standalone. Scans docs/ (excluding archive/), finds stray docs, checks freshness against recent git changes — classifying removed-code docs as OBSOLETE not STALE — then APPLIES fixes. In standalone mode also handles merge/archive/delete with user confirmation. Always asks before destructive actions.
---

**In `/commit` chain:** Applies non-destructive fixes (move misplaced files, refresh stale content). Passes merge/archive/delete candidates to `doc-consolidate`.

**Standalone:** Applies all fixes including archive/delete (with user confirmation). Invokes `doc-consolidate` for merges.

**Allowed at root:** `README.md`, `CLAUDE.md` only. Everything else → `docs/`.

**Rule: ask before any destructive or ambiguous action. Never assume.**

---

## Step 0: Orientation

Read `docs/manifest.md` if it exists (absent = first run, proceed).

---

## Step 1: Inventory `docs/`

List all files in `docs/` **excluding `docs/archive/`** — archived files must not be re-classified.

Record path and purpose (filename + first heading) for each.

---

## Step 2: Find and Move Docs Outside `docs/`

Find `*.md` outside `docs/`. Exclude:
- `.claude/skills/*/SKILL.md` — skill prompts, not project docs
- `node_modules/`, `venv/`, `.git/`
- `scrapers/tools/amazon_asin_scraper/README.md` — embedded tool, keep in place
- `README.md`, `CLAUDE.md` — allowed at root

Per misplaced `.md`:
1. Show file and purpose.
2. Ask: "`path/to/file.md` is outside `docs/`. Move to `docs/<name>.md`?"
3. Confirmed: `git mv <source> docs/<name>.md` (tracked) or move + `git add` (untracked).
4. Update references in `CLAUDE.md` and `docs/manifest.md`.
5. Notify: "Moved `<source>` → `docs/<name>.md`"

---

## Step 3: Check Freshness Against Recent Git Changes

Get recent history (safe on repos with <10 commits):
```bash
git log -n 20 --oneline
git diff $(git rev-list --max-count=1 HEAD~9 2>/dev/null || git rev-list --max-parents=0 HEAD)..HEAD --stat
```

Windows PowerShell:
```powershell
git log -n 20 --oneline
$base = git rev-list --max-count=1 HEAD~9 2>$null
if (-not $base) { $base = git rev-list --max-parents=0 HEAD }
git diff "$base..HEAD" --stat
```

Identify changed areas (scrapers, backend, schema, frontend).

For each `docs/` file in a changed area not updated in those commits:
1. Read the doc.
2. Read the relevant changed source files.
3. Does the relevant code still exist?
   - **Exists but changed** → **STALE**. Update if clear/contained; ask if large/ambiguous.
   - **Removed entirely** → **OBSOLETE**. Pass to `doc-consolidate` for archive/deletion.
4. STALE + fix is clear/contained → apply directly. Notify.
5. Large/ambiguous → ask before rewriting.

---

## Step 4: Review for Redundancy and Obsolescence

Check docs (excluding `docs/archive/`) for:
- **Redundant** — content substantially duplicated elsewhere
- **Superseded** — fully covered by a newer doc
- **Obsolete** — describes a removed feature or old architecture

Record path, reason, classification for each.

**Child of `/commit`:** Pass candidates to `doc-consolidate`. Do not apply here.

**Standalone:**
- **Archive/Delete** — ask per candidate. Create `docs/archive/` if needed:
  - Windows: `New-Item -ItemType Directory -Force docs\archive`
  - Linux/Mac: `mkdir -p docs/archive`
  - Archive: `git mv docs/X.md docs/archive/X.md`. Delete: `git rm docs/X.md`. Only after explicit confirmation.
- **Merge candidates** — invoke `doc-consolidate` (merge logic lives there).

---

## Step 5: Update manifest.md

After all changes, check `docs/manifest.md`:
- Is every file in `docs/` (not `docs/archive/`) listed?
- Does it reflect any moves/renames?

Out of sync → note for `doc-consolidate` (child mode) or update directly (standalone).

---

## Step 6: Report

```
📋 Audit-Docs Report
─────────────────────
Moved in:   N  →  (list)
Updated:    N  →  (list: doc + section)
Deferred:   N  →  (ambiguous or user skipped)

Handing to doc-consolidate:
  Merge:    N  →  (list)
  Archive:  N  →  (list)
  Delete:   N  →  (list)
```

In standalone mode, replace the handoff section with what was applied.

---

## Notes

- Never create new docs — only update, move, or (standalone) archive/delete.
- Only `README.md` and `CLAUDE.md` may remain at root.
- `docs/archive/` is excluded from all inventory and freshness scans.
- Update only the stale section unless the whole file needs replacing.
- Read source code first; ask only when the code is also ambiguous.
