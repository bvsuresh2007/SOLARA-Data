---
name: check-temp-files
description: Child of /commit (Step 1 — pre-flight). Also works standalone. Scans unstaged/untracked files for temp/backup patterns, flags .env* files as Critical, and flags temp/backup junk at root. Always asks before acting — never assumes. Does NOT handle moving project files to subdirectories (that is doc-consolidate's job).
---

**Scope:** Unstaged and untracked files only.

**Ownership:**
- This skill: temp files, backup copies, scratch files, draft files, `.env*` credential files — anywhere in the project.
- `doc-consolidate`: moving legitimate source files to correct subdirectories.

**Rule: ask before any action. Never delete or gitignore without confirmation.**

---

## Step 1: Get Status

```bash
git status
```

Focus on unstaged (modified, not staged) and untracked files only.

---

## Step 2: Flag Credential Files (Critical)

Flag any `.env*` file that is unstaged or untracked — **regardless of `.gitignore`**:
- `.env`, `.env.local`, `.env.production`, `.env.staging`, `.env.development`, any `.env.*`

> "🔴 CRITICAL: `.env.local` is untracked. May contain credentials — verify it is gitignored."

Always warn even if gitignored; credentials must never be committed.

---

## Step 3: Scan for Temp/Backup Patterns

Flag each unstaged/untracked file matching:

**Copy:** names with ` - Copy`, `_copy`, `.copy`, `(copy)`, `Copy of`

**Backup:** extensions `.bak`, `.backup`; names with `_backup`, `_bak`, `backup_`; pattern `*.backup.*`

**Temp/scratch:** names with `scratch`, `temp_`, `_temp`, `tmp_`, `_tmp`, `draft`, `wip`

**Temp directories:** any file inside `tmp/`, `temp/`, `scratch/`, `drafts/`, `wip/`, `.tmp/`

**Stray tests:** "test" in the name but NOT in `tests/`, `test/`, `__tests__/`, or `backend/tests/`

**Stray docs:** `.md` or `.txt` outside `docs/` with names containing `temp`, `tmp`, `scratch`, `draft`, `wip`, `note`, `todo` — except `README.md` and `CLAUDE.md`

---

## Step 4: Root Scan

Flag at root if matching temp/backup patterns:
- `*.bak`, `*.backup`, `*.tmp`
- Names with ` - Copy`, `_copy`, `(copy)`, `Copy of`
- Pattern `*.backup.*`
- Names with `scratch_`, `draft_`, `wip_`, `_temp`, `temp_`

**Do NOT flag:** `README.md`, `CLAUDE.md`, `docker-compose*.yml`, `.env.example`, `requirements.txt`, `.gitignore`, `.gitattributes`, `alembic.ini`, `pyproject.toml`, `setup.cfg`, `Makefile`, config dirs, project subdirectories, `.py` scripts.

---

## Step 5: Skip Gitignored Files (except `.env*`)

```bash
git check-ignore -v <file>
```

If gitignored → skip (won't be committed). Exception: always report `.env*` regardless.

---

## Step 6: Report and Decide

Group by: **🔴 Credential Files** | **⚠️ Temp / Copy / Backup** | **⚠️ Root Junk**

Per file: show path, type, git status, options:
- **Untracked** → delete (`rm` / `Remove-Item`) / add to `.gitignore` / keep
- **Unstaged** → `git restore <file>` / delete / keep

> "`force_shopify_d2c.backup.py` looks like a backup. Delete, add `*.backup.*` to `.gitignore`, or keep?"

No action without explicit user instruction.

---

## Step 7: Results

- 🔴 credential, ⚠️ temp/backup, ✅ clean
- All clear: "✅ No temp, backup, or credential files found."
- **As child of `/commit`:** stop the chain if anything is flagged and unresolved.

---

## Notes

- Files in `docs/` are not flagged even if names contain "temp".
- Files in proper test directories are not flagged.
- `.env.example` is safe — keys without values, meant to be committed.
- Moving source files to correct subdirectories is `doc-consolidate`'s job.
