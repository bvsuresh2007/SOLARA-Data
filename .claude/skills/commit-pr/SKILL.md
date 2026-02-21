---
name: commit-pr
description: Group uncommitted changes into logical commits and create a pull request. Stages specific files by area — never uses git add -A.
disable-model-invocation: true
---

## Step 1: Check Git Status

- Run `git status` and `git diff` to see all current changes.
- If there are no changes, inform the user and stop.

## Step 2: Group Related Changes

Analyze changed files and group by logical area:
- **Schema / DB**: `database/`, `scripts/seed_*.py`, `scripts/import_*.py`
- **Scrapers**: `scrapers/*.py` (group by portal if multiple portals changed)
- **Backend API**: `backend/app/`
- **Frontend**: `frontend/`
- **Config / infra**: `docker-compose.yml`, `.env.example`, `requirements.txt`
- **Docs**: `docs/`, `README.md`, `CLAUDE.md`
- **Shared utilities**: `shared/`, `scripts/`

Create separate commits for unrelated areas.

## Step 3: Commit Each Group

For each group:
- Stage only that group's files using `git add <specific files>` — **never `git add -A` or `git add .`**
- Write a commit message using conventional commit format:
  - `feat:` — new feature
  - `fix:` — bug fix
  - `refactor:` — restructuring without behavior change
  - `docs:` — documentation only
  - `chore:` — config, build, dependency updates
  - `data:` — schema or importer changes (project convention)
- Pass message via HEREDOC to preserve formatting

Continue until all changes are committed.

## Step 4: Create Pull Request

- Detect the default base branch:
  ```bash
  git remote show origin | grep "HEAD branch"
  ```
  Use that as the base. If detection fails, ask the user which branch to target.
- Push: `git push -u origin <current-branch>`
- Create PR with `gh pr create`:
  - Title: concise (under 70 characters)
  - Body: bullet-point summary of what changed and why, plus a test plan
  - Base: the detected default branch

## Step 5: Confirm

- Output the PR URL
- List all commits that were created

## Safety Rules

- **Never** use `git add -A` or `git add .` — always stage specific named files
- **Never** use `--no-verify` unless user explicitly asks
- **Never** stage files from `scrapers/sessions/` (browser profiles, session tokens)
- **Never** stage files from `data/source/` (Excel/CSV data files — gitignored)
- **Never** stage `.env` files
- Stop and notify the user if there are unresolved merge conflicts
