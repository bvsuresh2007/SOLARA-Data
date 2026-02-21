---
name: fix-github-actions
description: Fetch a failed GitHub Actions run by ID, diagnose the root cause, and apply fixes to the workflow file.
argument-hint: <run-id>
---

**Usage**: `/fix-github-actions <RUN_ID>`

---

## Step 1: Parse and Validate Input

- Extract the run ID from `$ARGUMENTS`
- Validate it is a numeric ID
- If missing: "Please provide a run ID. Usage: `/fix-github-actions <RUN_ID>`"

## Step 2: Fetch Run Details

```bash
gh run view $ARGUMENTS
gh run view $ARGUMENTS --log-failed
ls .github/workflows/
```

Extract:
- Workflow name and file path
- Run status and conclusion
- Failed job/step names
- Error messages from logs

## Step 3: Identify Failure Pattern

Match error output against common patterns:

### Python Import / Dependency Error
- **Error**: `ModuleNotFoundError`, `ImportError`, `No module named`
- **Fix**: Ensure `pip install -r requirements.txt` step exists before the failing step

### Missing Environment Variable / Secret
- **Error**: `KeyError`, `os.environ[`, `secret not found`
- **Fix**: Document the missing variable — user must add it in GitHub repo Settings → Secrets

### Playwright Browser Missing
- **Error**: `Executable doesn't exist`, `playwright install`, `chromium`
- **Fix**: Add `playwright install chromium` step before the failing step

### Python Version Mismatch
- **Error**: `SyntaxError`, `requires Python 3.x`
- **Fix**: Update `python-version` in the `setup-python` step to `'3.12'`

### PostgreSQL Connection Failure
- **Error**: `could not connect to server`, `FATAL: role does not exist`, `Connection refused`
- **Fix**: Ensure a `postgres` service is configured and `DATABASE_URL` is set as a secret

### Lint / Formatting Failure
- **Error**: `flake8`, `black`, `eslint`, `tsc` errors
- **Fix**: Run linter locally and fix flagged lines, or update lint config

### Timeout
- **Error**: `exceeded the maximum execution time`
- **Fix**: Add/increase `timeout-minutes` on the job

## Step 4: Read the Workflow File

- Find the workflow file under `.github/workflows/`
- Read its full content
- Understand the current steps, services, and environment

## Step 5: Apply Fixes

Modify the YAML to fix the identified issue. Common additions:

```yaml
# Install Python dependencies
- name: Install dependencies
  run: pip install -r requirements.txt

# Install Playwright browsers
- name: Install Playwright browsers
  run: |
    playwright install chromium
    playwright install-deps chromium || true

# Set up Python
- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: '3.12'
    cache: 'pip'

# Increase timeout
jobs:
  ci:
    runs-on: ubuntu-latest
    timeout-minutes: 30
```

Do NOT duplicate steps that already exist — check before adding.

## Step 6: Verify YAML Syntax

- Correct indentation (YAML is space-sensitive)
- Unique step names
- All required secrets referenced correctly

## Step 7: Display Summary

```
🔍 Analyzing GitHub Actions Run #<RUN_ID>

📋 Run Details:
  - Workflow: <name>
  - File: .github/workflows/<file>.yml
  - Status: ❌ Failed

🔎 Issues Found:
  1. ❌ <description>
     Error: <error line>

🔧 Fixes Applied:
  ✅ <description>
  📝 Updated: .github/workflows/<file>.yml

✅ Next Steps:
  1. git diff .github/workflows/<file>.yml
  2. git commit -m "fix: resolve GitHub Actions failure"
  3. git push to trigger a new run
```

## Notes

- Secrets cannot be auto-fixed — note them and tell the user to add them in GitHub Settings → Secrets
- Playwright scrapers in CI require headless mode and browser installation steps
- Always preserve existing working steps — do not remove or reorder unless necessary
