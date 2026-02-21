---
name: code-review
description: Review unstaged and untracked code changes for quality, security, performance, and best practices. Produces a report saved to docs/code-reviews/. Read-only — no code changes made automatically.
---

**IMPORTANT**: READ-ONLY. Analyzes code and produces a report with suggestions. Do NOT make any code changes automatically.

---

## Step 1: Get Changed Files

- Run `git status`, `git diff`, and `git ls-files --others --exclude-standard`.
- Analyze BOTH unstaged modified files AND untracked new files.
- Focus only on files not yet committed.

## Step 2: Read and Analyze Each File

For each changed/new file:
- Read the full file content (not just the diff)
- Understand its purpose and role (scraper, API endpoint, importer, frontend component, etc.)
- Identify the language (Python, TypeScript, SQL)

## Step 3: Code Quality Checks

### General Quality
- Consistent formatting, naming conventions
- Appropriate comments and docstrings
- Proper exception handling and error messages
- Type hints (Python) or type definitions (TypeScript)
- Unused or missing imports

### DRY (Don't Repeat Yourself)
- Duplicate code blocks that could be extracted into functions
- Hardcoded values that should be constants

### Loop Improvements
- Nested loops that could be optimized
- Loops replaceable with list comprehensions, `map`, `filter`, generators
- Missing early exits

### Performance Issues
- **Database**: N+1 query problems (queries inside loops), `SELECT *`, missing pagination
- **Scrapers**: unnecessary repeated calls, missing timeouts/retry logic
- **Memory**: large datasets loaded entirely into memory instead of streaming

### Security Issues
- Hardcoded credentials, API keys, or secrets in code
- SQL injection vulnerabilities (raw SQL with user input — use parameterized queries / SQLAlchemy)
- Missing input validation on API endpoints
- Sensitive data exposed in logs or API responses

### Gitignore Check
For each untracked file, check if it should be in `.gitignore`:
- `__pycache__/`, `*.pyc`, `.next/`, `node_modules/`
- `.env`, `.env.local`
- Browser profiles (`blinkit_profile/`, `easyecom_profile/`) — already in `scrapers/sessions/`
- Session/token files (`*.json` auth files) — already gitignored
- Data files: `*.csv`, `*.xlsx` in `data/`

## Step 4: Document Findings

For each issue:
- **File path** and **line numbers**
- **Issue type**
- **Current code snippet**
- **Suggested improvement** (suggestion only — do not apply)
- **Priority**: 🔴 Critical / 🟡 Medium / 🟢 Low
- **Environment**: 🔴 Production only / 🟢 Development OK / 🟡 Both

## Step 5: Save Report

Append a new dated section to `docs/code-reviews/CODE_REVIEW_REPORT.md` (create directory + file if they don't exist). Never overwrite previous entries — each run appends a new section.

Report per run:
- Date, branch, files reviewed
- Executive summary
- Issues by priority
- Production deployment requirements
- Recommended action plan

## Step 6: Display Results

- Present as a report — do NOT modify any code files
- Use 🔴 / 🟡 / 🟢 severity indicators
- Group findings by file
- End with: "Report saved to `docs/code-reviews/CODE_REVIEW_REPORT.md`"

## Project-Specific Notes

- **Scrapers**: check Playwright selector robustness, error handling if portal UI changes
- **Importers**: check for off-by-one errors in column indexing, NaN handling, upsert correctness
- **FastAPI routes**: check input validation, authentication, correct response schema
- **Frontend**: check API error states, loading states, TypeScript type safety
- If no issues found, ✅ congratulate and note clean code
