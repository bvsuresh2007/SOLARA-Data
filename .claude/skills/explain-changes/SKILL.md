---
name: explain-changes
description: Explain code changes in plain language with real-world analogies. Choose between uncommitted changes, staged changes, or specific files. Useful for understanding what was built and why.
---

**Purpose**: Understand code changes in simple terms with real-world analogies — no jargon.

---

## Step 1: Ask What to Review

Present options:
1. **Uncommitted changes** — modified files not yet committed
2. **Staged changes** — files added with `git add` but not committed
3. **Specific files or folders** — user specifies paths
4. **All changes** — uncommitted + staged combined

Wait for the user's choice before proceeding.

## Step 2: Get the Changes

Based on choice:
- **Uncommitted**: `git diff` + `git ls-files --others --exclude-standard`
- **Staged**: `git diff --cached`
- **Specific files**: `git diff <path>` or read directly if untracked
- **All**: combine both

## Step 3: Read and Understand Each File

- Read the full content (or changed sections)
- Understand what the file does and why it changed
- Note the language and the file's role (scraper, importer, API route, frontend page, etc.)

## Step 4: Explain Each Change Simply

For each change:

### What Changed?
- Simple description: "We added a function that imports Zepto sales data from Excel"
- Before/After: show what was there and what's there now

### Why Did It Change?
- The problem it solves or the feature it enables

### How Does It Work?
- Break the code into plain-language steps
- No jargon — explain any technical term you use

**Analogies to use for this project:**
- A **scraper** is like a robot that opens a website, reads the numbers on screen, and writes them down
- An **upsert** is like filling in a form: if it's a new entry, add it; if it already exists, update it
- An **Excel importer** reads a spreadsheet row by row and enters the data into a database
- An **API endpoint** is a window: the frontend asks a question, the backend answers through it
- A **Playwright script** remote-controls a browser — it clicks, types, and reads pages automatically
- A **portal scraper** logs into a platform's seller dashboard and copies the sales report
- A **foreign key** is like a reference number — "this sale belongs to product #42"
- A **migration** is a script that updates the database structure (like renovating a room)

## Step 5: Teach Programming Concepts Used

For each concept that appears in the changes:

| Concept | Simple explanation |
|---------|-------------------|
| Function | A recipe — give it inputs, it produces an output |
| Variable | A labeled box that holds a value |
| Loop | Doing something repeatedly — like checking every row in a spreadsheet |
| If/else | Making a decision — "if X is true, do this, otherwise do that" |
| Dict/Map | A lookup table — like a phone book |
| Upsert | Insert if new, update if already exists |
| Async/await | Start a task and wait for it — like ordering food then waiting for delivery |
| ORM model | A Python class that represents a database table |
| Schema | The shape of data — what columns a table has and their types |
| Index | A shortcut that makes database lookups faster — like a book index |

## Step 6: Summary Report

1. **Overview**: files changed, lines added/removed, one-sentence summary
2. **File-by-file breakdown**: what changed, why, how it works, concepts used
3. **Concepts learned**: unique list with simple explanations
4. **Closing**: "Ask me about any concept and I'll explain it further!"

## Notes

- Always use simple, everyday language
- Use analogies from the project context (scrapers, sales data, portals, Excel imports)
- Break everything into small steps
- Be encouraging — provide concrete examples from the actual code, not generic ones
