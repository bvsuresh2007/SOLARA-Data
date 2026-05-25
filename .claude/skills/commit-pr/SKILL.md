---
name: commit-pr
description: Child of /commit (Step 9 — PR creation only, push already done). Also works standalone. Warns if on main/master, checks for existing PR before creating, groups and commits any remaining changes, pushes only if not already pushed, then creates or updates a PR with a structured body.
disable-model-invocation: true
---

**Dual mode:**
- **Child of `/commit`**: push already done — skip Step 3, go to Step 4. `/commit` passes this instruction explicitly.
- **Standalone**: full flow — commit, push, then create/update PR.

---

## Step 0: Branch Safety Check

```bash
git branch --show-current
```

If on `main` or `master`:
> "⚠️ You are on `main`. Creating a PR from the default branch is unusual. Are you sure?"

Wait for confirmation.

---

## Step 1: Check Git Status

```bash
git status
git diff
```

- No uncommitted changes → skip to Step 4.
- Uncommitted changes → continue to Step 2.

---

## Step 2: Group and Commit Changes

| Area | Paths | Prefix |
|------|-------|--------|
| Schema / DB | `database/`, `scripts/seed_*.py`, `scripts/import_*.py` | `data:` |
| Scrapers | `scrapers/*.py` (per portal if multiple) | `feat:` / `fix:` |
| Backend API | `backend/app/` | `feat:` / `fix:` |
| Frontend | `frontend/` | `feat:` / `fix:` |
| Config / infra | `docker-compose.yml`, `.env.example`, `requirements.txt` | `chore:` |
| Docs | `docs/`, `README.md`, `CLAUDE.md` | `docs:` |
| Shared utilities | `shared/`, `scripts/` | `refactor:` / `feat:` |

```bash
git add <specific files — never git add -A or git add .>
git commit -m "$(cat <<'EOF'
<prefix>: <description>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

**Never stage:** `.env`, `scrapers/sessions/`, `data/source/`. Stop if merge conflicts.

---

## Step 3: Push _(standalone only — skip if called by `/commit`)_

```bash
git status -sb
```

If "up to date with 'origin/<branch>'" → skip. Otherwise:
```bash
git push -u origin <current-branch>
```

---

## Step 4: Check for Existing PR

```bash
gh pr list --head <current-branch> --json number,url,title,state
```

- **PR exists** → show number, title, URL, state.
  - Ask: "PR #N exists. Update its description?"
  - Yes → Step 5 with `gh pr edit`. No → output URL and stop.
- **No PR** → Step 5 to create one.

---

## Step 5: Create or Update PR

```bash
git remote show origin | grep "HEAD branch"
```

If detection fails, ask the user for the base branch.

**PR body template:**

```
## Summary
- <what changed, 2-4 bullets>

## Changes by area
- **<area>**: <what was added/fixed>

## Test plan
- [ ] <primary change verification>
- [ ] <edge case or regression>
- [ ] Docker services start cleanly: `docker-compose up -d`

## Breaking changes
<"None" or list with migration steps>

## Related issues
Closes #<issue-number>  ← remove if not linked
```

**Create:**
```bash
gh pr create --title "<under 70 chars>" --body "$(cat <<'EOF'
<body>
EOF
)" --base <default-branch>
```

**Update:**
```bash
gh pr edit <number> --body "$(cat <<'EOF'
<body>
EOF
)"
```

---

## Step 6: Confirm

Output: PR URL, title, base branch, commits included.

---

## Safety Rules

- Never `git add -A` or `git add .`
- Never `--no-verify`
- Never stage `scrapers/sessions/`, `data/source/`, or `.env` files
- Stop on merge conflicts
- Never create a duplicate PR — always check Step 4 first
