---
name: explain-changes
description: Explain code changes in plain language with real-world analogies. Pass an optional argument (all/staged/uncommitted) to skip the menu. Detects when there are no changes. Reads manifest.md for project context. Includes project-specific concepts in the glossary.
---

**Purpose**: Explain changes in simple terms — no jargon, project-context analogies.

---

## Step 0: Orientation

Read `docs/manifest.md` if it exists — knowing `scrapers/zepto_scraper.py` is a Zepto scraper (not a generic script) makes explanations accurate.

---

## Step 1: Determine Scope

| Argument | Action |
|----------|--------|
| `all` or empty | Explain uncommitted + staged combined |
| `uncommitted` | Unstaged modified + untracked only |
| `staged` | Files added with `git add` but not committed |
| A file/folder path | That path only |

Route by table. Never show a menu.

---

## Step 2: Get the Changes

- **Uncommitted**: `git diff` + `git ls-files --others --exclude-standard`
- **Staged**: `git diff --cached`
- **Path**: `git diff <path>` or read directly if untracked
- **All**: combine both

**No changes found:**
> "No uncommitted changes. Did you want to explain:
> - The last commit? `git show --stat HEAD`
> - A specific branch? Tell me the name."

Stop.

---

## Step 3: Read Each File

- ≤ 300 lines: read fully.
- > 300 lines: read changed sections + surrounding function context.
- Identify role via `docs/manifest.md`.

---

## Step 4: Explain Each Change

### What Changed?
Plain description. Before/After: show old and new.

### Why Did It Change?
The problem solved or feature enabled.

### How Does It Work?
Plain-language steps. Explain technical terms.

**Project analogies:**
- **Scraper** — robot that opens a website, reads numbers, writes them down
- **Upsert** — add if new, update if already exists
- **Excel importer** — reads a spreadsheet row by row, enters data into the DB
- **API endpoint** — frontend asks a question; backend answers through it
- **Playwright script** — remote-controls a browser: clicks, types, reads pages
- **Portal scraper** — logs into a seller dashboard (Swiggy, Blinkit, etc.) and copies the report
- **Foreign key** — reference number: "this sale belongs to product #42"
- **Migration** — updates DB structure (like renovating a room before moving in)

---

## Step 5: Teach Concepts Used

Only explain concepts that actually appeared — skip unused rows.

| Concept | Simple explanation |
|---------|-------------------|
| Function | A recipe — give it inputs, it produces an output |
| Variable | A labeled box holding a value |
| Loop | Repeating something — like checking every row in a spreadsheet |
| If/else | A decision — "if X, do this; otherwise do that" |
| Dict/Map | A lookup table — like a phone book |
| Upsert | Insert if new, update if exists |
| Async/await | Start a task and wait — like ordering food then waiting |
| ORM model | A Python class representing a DB table |
| Schema | The shape of data — columns and their types |
| Index | A DB shortcut for faster lookups — like a book index |
| Portal scraper | Logs into a platform (Zepto, Blinkit, etc.) and downloads sales data |
| Orchestrator | Scheduler that runs all scrapers in sequence |
| Session auth | Saves logged-in browser state so scraper skips re-login |
| Alembic migration | Numbered script that updates DB structure in a controlled, reversible way |
| Pydantic schema | Python class that validates data shape going into/out of the API |
| BaseScraper | Shared parent class all scrapers inherit — retries, logging, Playwright setup |
| Playwright session | Real browser instance controlled by code — for JS-heavy sites |

---

## Step 6: Summary Report

1. **Overview**: files changed, one-sentence summary
2. **File-by-file**: what changed, why, how it works, concepts used
3. **Concepts learned**: only those that appeared, with simple explanations
4. **Closing**: "Ask me about any concept and I'll explain it further!"

---

## Notes

- Simple, everyday language only.
- Use actual code examples, not generic ones.
- Only explain concepts that appeared — skip unused table rows.
