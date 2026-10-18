---
name: fix-github-actions
description: Fetch a failed GitHub Actions run by ID, diagnose root cause against known patterns (including Docker Compose and Node.js), apply fixes, validate YAML with actual parser, and suggest /commit + gh run rerun. Guards against missing workflows directory.
argument-hint: <run-id>
---

**Usage**: `/fix-github-actions <RUN_ID>`

---

## Step 1: Validate Input

- Extract run ID from `$ARGUMENTS`. Validate: numeric.
- Missing → stop: "Provide a run ID: `/fix-github-actions <RUN_ID>`"

---

## Step 2: Check Workflows Directory

```bash
# Linux/Mac
ls .github/workflows/ 2>/dev/null || echo "NOT FOUND"

# Windows
Get-ChildItem .github\workflows\ 2>$null
```

Absent or empty → stop:
> "No workflows in `.github/workflows/`. Nothing to fix. Want help setting one up?"

---

## Step 3: Fetch Run Details

```bash
gh run view $ARGUMENTS
gh run view $ARGUMENTS --log-failed
```

Extract: workflow name + file path, run status, failed job/step name, full error output.

---

## Step 4: Identify Failure Pattern

### Python Dependency Error
- **Error**: `ModuleNotFoundError`, `ImportError`, `No module named`
- **Fix**: Add `pip install -r requirements.txt` before the failing step

### Missing Secret / Env Var
- **Error**: `KeyError`, `os.environ[`, `secret not found`, `Required environment variable`
- **Fix**: Tell user to add it in GitHub Settings → Secrets

### Playwright Browser Missing
- **Error**: `Executable doesn't exist`, `playwright install`, `chromium`, `browserType.launch`
- **Fix**: Add `playwright install chromium` and `playwright install-deps chromium || true`

### Python Version Mismatch
- **Error**: `SyntaxError`, `requires Python 3.x`, `python3.x: command not found`
- **Fix**: Update `python-version` in `setup-python` to `'3.12'`

### PostgreSQL Connection Failure
- **Error**: `could not connect to server`, `FATAL: role does not exist`, `ECONNREFUSED 5432`
- **Fix**: Add a `postgres` service under `services:`, set `DATABASE_URL` as a secret

### Docker Compose Failure
- **Error**: `docker-compose: command not found`, `service failed to start`, `health check failed`, `container exited`, `port is already allocated`
- **Fix**:
  - Missing command: use `docker compose` (v2) or install `docker-compose` (v1)
  - Service failed: add `depends_on: condition: service_healthy`
  - Port conflict: use dynamic port mapping

### Node.js / npm Failure
- **Error**: `npm ERR!`, `Cannot find module`, `next: command not found`, `npm WARN EBADENGINE`
- **Fix**:
  - Missing setup: add `actions/setup-node@v4` with `node-version`
  - Missing install: add `npm ci` before `npm run build`
  - Wrong version: update `node-version` to `'20'` or `'18'`

### Lint / Format Failure
- **Error**: `flake8`, `black`, `eslint`, `tsc --noEmit`
- **Fix**: Fix flagged lines locally or update lint config

### Timeout
- **Error**: `exceeded the maximum execution time`
- **Fix**: Add/increase `timeout-minutes` on the failing job

### Unknown Pattern
- Show the full raw error output.
- Ask: "I don't recognize this pattern. Describe what you think is wrong or paste more context."
- Wait for input before attempting a fix.

---

## Step 5: Read the Workflow File

Read the full workflow file from Step 3. **Do not duplicate existing steps.**

---

## Step 6: Apply Fixes

Common additions:

```yaml
# Python dependencies
- name: Install dependencies
  run: pip install -r requirements.txt

# Playwright browsers
- name: Install Playwright browsers
  run: |
    playwright install chromium
    playwright install-deps chromium || true

# Python setup
- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: '3.12'
    cache: 'pip'

# Node.js setup
- name: Set up Node.js
  uses: actions/setup-node@v4
  with:
    node-version: '20'
    cache: 'npm'
    cache-dependency-path: frontend/package-lock.json

# Frontend dependencies
- name: Install frontend dependencies
  run: cd frontend && npm ci

# PostgreSQL service
services:
  postgres:
    image: postgres:15
    env:
      POSTGRES_DB: solara_test
      POSTGRES_USER: solara
      POSTGRES_PASSWORD: ${{ secrets.DB_PASSWORD }}
    options: >-
      --health-cmd pg_isready
      --health-interval 10s
      --health-timeout 5s
      --health-retries 5

# Timeout
jobs:
  ci:
    runs-on: ubuntu-latest
    timeout-minutes: 30
```

Never remove or reorder working steps.

---

## Step 7: Validate YAML

Substitute actual filename from Step 3:

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/FILENAME.yml')); print('YAML valid')"
```

If Python unavailable:
```bash
node -e "require('js-yaml').load(require('fs').readFileSync('.github/workflows/FILENAME.yml','utf8')); console.log('YAML valid')"
```

On failure: show error, fix, re-validate. Common pitfalls:
- Indentation: consistent spaces, no tabs
- Step names must be unique within a job
- Secrets: `${{ secrets.NAME }}`

---

## Step 8: Summary

```
🔍 GitHub Actions Fix — Run #<RUN_ID>

📋 Run Details:
  Workflow: <name>
  File:     .github/workflows/<file>.yml
  Status:   ❌ Failed
  Failed step: <step name>

🔎 Issues Found:
  1. ❌ <description>
     Error: <error line>

🔧 Fixes Applied:
  ✅ <description>
  📝 Updated: .github/workflows/<file>.yml
  ✅ YAML syntax validated

✅ Next Steps:
  1. Review:    git diff .github/workflows/<file>.yml
  2. Commit:    /commit
  3. Retry:     gh run rerun --failed <RUN_ID>
```

---

## Notes

- Secrets: provide the exact name; user adds it in GitHub Settings → Secrets.
- Playwright in CI: needs headless mode + browser install steps.
- Never remove or reorder working steps.
- Unknown errors: ask the user first, never guess.
