---
name: audit-docs
description: Audit project documentation — check docs/ inventory, find stray docs outside docs/, check freshness against recent git changes, and flag stale or redundant files. Read-only report.
---

**Purpose**: Audit all project documentation — ensure docs live in `docs/`, check freshness against recent git changes, and flag redundant or stale files. This command **produces a report and recommendations only** — it does not move or edit files automatically.

**Allowed root-level docs (only these two)**: `README.md`, `CLAUDE.md`. All other documentation must be in `docs/`.

---

## Step 1: Inventory `docs/`

- List all files under `docs/` (including subdirectories).
- For each file note: path, apparent purpose (from filename + first heading).
- Produce a concise table or list.

## Step 2: Find Documentation Outside `docs/`

- Search the entire project for `*.md` files **outside** `docs/`.
- Exclude:
  - `.claude/commands/*.md` and `.claude/skills/*/SKILL.md` — these are slash-command prompts, not project docs
  - `node_modules/`, `venv/`, `.git/`
  - `scrapers/tools/amazon_asin_scraper/README.md` — belongs to the embedded tool, keep in place
- **Allowed at root**: `README.md`, `CLAUDE.md` only. Any other `.md` at root must be moved to `docs/`.
- For each file found outside `docs/`: record path, purpose, recommendation (Move to `docs/` or Keep in place with reason).

## Step 3: Check Freshness Against Recent Git Changes

- Run `git log -n 20 --oneline` and `git diff --stat HEAD~10..HEAD` to see recent activity.
- Derive which **code areas** changed (e.g. scrapers, backend API, database schema, frontend).
- Cross-check: for each `docs/` file that covers a changed area, note whether the doc was also updated in those commits.
- List:
  - Recently changed code paths
  - `docs/` files that cover those areas + whether they were updated

## Step 4: Review Older Docs for Removal or Merge

- Briefly check existing docs (especially older-looking files) for:
  - **Superseded**: fully covered by another doc
  - **Redundant**: content duplicated elsewhere — suggest merge
  - **Obsolete**: describes removed features or old architecture
- List candidates with: path, short reason, recommendation (Remove / Merge into X / Keep)

## Step 5: Generate Report

### 5.1 Docs in `docs/` — inventory
### 5.2 Docs outside `docs/` — with move/keep recommendations
### 5.3 Freshness — stale docs that likely need updating (reference git diff and code)
### 5.4 Removal/merge candidates
### 5.5 Action items
- **Consolidation**: files to move into `docs/`
- **Updates**: docs to update and what to change (no new files unless unavoidable)
- **Removal/merge**: candidates from 5.4

## Notes

- **Read-only**: only report; user decides what to do.
- **Fewer files is better**: do not recommend creating new docs unless content cannot fit in any existing file.
- **Root exceptions**: only `README.md` and `CLAUDE.md` may stay at project root.
- Re-run after applying changes to verify.
