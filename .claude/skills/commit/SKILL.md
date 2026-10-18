---
name: commit
description: PRIMARY commit skill. Supports /commit (full chain) and /commit quick (skip review/docs). Warns if on main/master, runs check-temp-files → code-review → audit-docs → doc-consolidate, groups changes into feature-area commits, pushes, and optionally creates a PR via commit-pr.
---

**Usage:**
- `/commit` — full quality chain (default)
- `/commit quick` — skip review/docs; just group, commit, and push

**Full chain:**
1. `check-temp-files` — temp/backup pre-flight
2. `code-review` — review changes, log to `docs/code-review.md`
3. `audit-docs` — fix docs, pass merge/archive/delete candidates forward
4. `doc-consolidate` — structural doc changes + slim `CLAUDE.md` + update `manifest.md`
5. Group & commit by feature area, push
6. `commit-pr` — optionally create a PR

---

## Step 0: Branch Safety Check

```bash
git branch --show-current
```

If on `main` or `master`:
> "⚠️ You are on `main`. Committing directly to the default branch is usually unintended. Proceed?"

If no → stop.

---

## Step 0b: Check Mode

Parse `$ARGUMENTS`:
- `quick` → skip Steps 2, 3, 4. Jump to Step 5.
- Otherwise → run all steps. Full is the default — do not ask.

---

## Step 1: Pre-flight — Temp File Check

Invoke `check-temp-files`.

- Files found → **stop**. List them. Ask user to resolve, then re-run `/commit`.
- Clean → continue.

---

## Step 2: Code Review _(full mode only)_

Invoke `code-review`.

Present all **OPEN** issues (new + carried-over):
> "Which issues (if any) do you want to fix before committing? List IDs, or 'none' to proceed."

- User lists IDs → stop; re-run after fixing.
- "none" → continue.

---

## Step 3: Doc Audit _(full mode only)_

Invoke `audit-docs`.

---

## Step 4: Doc Consolidation _(full mode only)_

Invoke `doc-consolidate` with the `audit-docs` findings in context.

After it completes: `git add docs/ CLAUDE.md README.md`.

---

## Step 5: Inspect Changes

```bash
git status
git diff
git diff --cached
```

Compile the full list of files to commit.

---

## Step 6: Group Into Feature-Area Commits

| Area | Matching Paths | Prefix |
|------|---------------|--------|
| Schema / DB | `database/`, `scripts/seed_*.py`, `scripts/import_*.py` | `data:` |
| Scrapers — per portal | `scrapers/swiggy_*.py`, `scrapers/blinkit_*.py`, etc. | `feat:` / `fix:` |
| Scrapers — shared | `scrapers/base_scraper.py`, `scrapers/orchestrator.py` | `refactor:` / `fix:` |
| Backend API | `backend/app/` | `feat:` / `fix:` |
| Frontend | `frontend/` | `feat:` / `fix:` |
| Shared utilities | `shared/`, `scripts/` | `refactor:` / `feat:` |
| Config / infra | `docker-compose.yml`, `.env.example`, `requirements.txt` | `chore:` |
| Docs | `docs/`, `README.md`, `CLAUDE.md` | `docs:` |

**Rules:**
- One commit per area. Multiple portals = separate commits per portal.
- Backend + frontend feature = backend first, then frontend.
- `docs/code-review.md` and `docs/manifest.md` → `docs:` commit.
- Ambiguous grouping → **ask the user, never assume.**
- Obvious single-area change → skip confirmation.

Present the proposed grouping and wait for confirmation otherwise.

---

## Step 7: Create Each Commit

Order: data → scrapers → backend → frontend → shared → config → docs

```bash
git add <specific files — never git add -A or git add .>
git commit -m "$(cat <<'EOF'
<prefix>: <concise description>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

**Never stage:** `.env`, `scrapers/sessions/`, `data/source/`, credential files.

---

## Step 8: Push

```bash
git push -u origin <current-branch>
```

If rejected: `git pull --rebase origin <branch>` then push again.
If merge conflicts: **stop**, show conflicted files, ask user to resolve.

---

## Step 9: Pull Request (Optional)

```bash
gh pr list --head <current-branch> --json url,title,state
```

- **PR exists** → show URL + state. Ask: "Update its description?"
  - Yes → invoke `commit-pr` (skip push, go to PR update).
  - No → skip.
- **No PR** → ask: "Create a pull request?"
  - Yes → invoke `commit-pr` (skip push, go to PR creation).
  - No → remind: "Run `/commit-pr` when ready."

---

## Step 10: Summary

Derive remote URL: `git remote get-url origin` — convert SSH → HTTPS if needed, append `/tree/<branch>`.

```
✅ Commit Complete
──────────────────
Branch:  <branch-name>
Remote:  <derived URL>/tree/<branch-name>

Commits (N):
  1. <hash>  feat: ...
  2. <hash>  docs: ...

📋 Code Review  →  docs/code-review.md  (<N> open issues)
📚 Docs         →  <N> consolidated  /  <N> archived  /  <N> deleted
✂️  Slimmed      →  CLAUDE.md
🗂️  Manifest     →  docs/manifest.md updated
```

---

## Child Skill Reference

| Order | Skill | Role | Stop condition |
|-------|-------|------|----------------|
| 0 | _(inline)_ | Branch safety check | On main/master — user declines |
| 0b | _(inline)_ | Parse quick/full | — |
| 1 | `check-temp-files` | Pre-flight temp + `.env*` | Files found and unresolved |
| 2 | `code-review` | Code quality → `docs/code-review.md` | User wants to fix issues first |
| 3 | `audit-docs` | Move docs, refresh stale content | Ambiguous update — asks user |
| 4 | `doc-consolidate` | Structural doc changes + slim + manifest | User must confirm deletions |
| 5 | _(inline)_ | Group, commit, push | Merge conflict |
| 6 | `commit-pr` | Create or update PR (push already done) | User says no |
