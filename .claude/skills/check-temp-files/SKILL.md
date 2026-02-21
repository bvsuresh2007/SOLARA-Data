---
name: check-temp-files
description: Scan unstaged and untracked files for temporary file patterns (copies, backups, scratch files, temp test files) before they accidentally get committed.
---

**Scope**: Checks **unstaged and untracked files only** — files NOT yet added to git. Catches temporary files BEFORE they enter the repository.

---

## Step 1: Check Git Status

- Run `git status` to see all current changes.
- Focus ONLY on:
  - **Unstaged files** (modified but not yet staged with `git add`)
  - **Untracked files** (new files not yet added to git)
- Do NOT check files already staged or committed.

## Step 2: Analyze Files for Temporary Patterns

For each unstaged/untracked file, check for:

### Copy Files
- Names containing ` - Copy`, `_copy`, `.copy`, `(copy)`, `Copy of`

### Backup Files
- Extensions `.bak`, `.backup`
- Names containing `_backup`, `_bak`, `backup_`

### Temporary Test Files
- Files with "test" in the name that are NOT in a proper test directory
- Valid test directories: `tests/`, `test/`, `__tests__/`, `backend/tests/`
- Flag test files outside these directories

### Temporary Documents
- `.md` or `.txt` files outside `docs/` whose names contain: `temp`, `tmp`, `scratch`, `draft`, `wip`, `note`, `todo`

### Scratch/Temp Files
- Names containing: `scratch`, `temp_`, `_temp`, `tmp_`, `_tmp`, `draft`, `wip`

### Files in Temporary Directories
- Files in directories named: `tmp/`, `temp/`, `scratch/`, `drafts/`, `wip/`, `.tmp/`

## Step 3: Categorize Findings

Group by type: Copy Files, Backup Files, Temporary Test Files, Temporary Documents, Scratch/Temp Files, Files in Temp Directories.

For each file: full path, type, reason it's flagged, git status (unstaged/untracked).

## Step 4: Recommendations

For each file found:
- **Untracked files**: suggest `rm <file>` (or `del <file>` on Windows) or add to `.gitignore`
- **Unstaged files**: suggest `git restore <file>` to discard, or `rm <file>` if not needed

## Step 5: Display Results

- Use ⚠️ for issues, ✅ for clean
- Group by category
- Show actionable recommendations

## Notes

- Files in `docs/` are generally OK even if the name contains "temp".
- Files in proper test directories should NOT be flagged.
- If no temporary files found, report ✅ with a clean status message.
