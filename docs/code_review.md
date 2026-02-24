# Code Review Reports

---

## Review: 2026-02-21

**Branch:** `claude/merge-solara-projects-Qo5Sd`

**Files reviewed:**

*Modified (unstaged):*
- `.gitignore`
- `backend/app/config.py`
- `backend/app/models/__init__.py`, `inventory.py`, `metadata.py`, `sales.py`
- `backend/app/utils/slack.py`
- `requirements.txt`
- `scrapers/blinkit_scraper.py`, `easyecom_scraper.py`, `zepto_scraper.py`
- `shared/constants.py`

*New (untracked):*
- `scrapers/gmail_otp.py`
- `scrapers/totp_helper.py`
- `scrapers/amazon_pi_scraper.py`
- `scrapers/flipkart_email_scraper.py`
- `scrapers/sessions/` (browser profiles + session file)
- `scripts/db_utils.py`, `import_excel_sales.py`, `excel_reader.py`, and others

*Deleted:*
- `auth_blinkit.py` (moved into `scrapers/`)
- `main.py`, `src/scraper.py`, `src/slack_notifier.py` (moved to `scrapers/tools/amazon_asin_scraper/`)

---

### Executive Summary

The changes represent a significant schema alignment (v1 → v2 model renames, new tables), a full Zepto scraper implementation, new OTP/TOTP infrastructure, and importer scripts for Excel data. The overall quality is high — good docstrings, consistent patterns, proper upsert logic. Two issues require attention before committing: the browser profile directories are not gitignored (would commit auth credentials to the repo), and `gmail_otp.py` bundles a Drive scope into a module named for Gmail OTP only.

---

### 🔴 Critical

---

#### C-01 — Browser profiles not gitignored
**Files:** `.gitignore`, `scrapers/sessions/`
**Status:** 🗓️ Deferred — solution selected, implementation pending

`scrapers/sessions/blinkit_profile/` and `scrapers/sessions/easyecom_profile/` are large Chromium persistent profiles that contain auth cookies and cached Google/Blinkit sessions. They are **not covered by `.gitignore`**. Running `git add scrapers/` would commit them, leaking auth tokens into the repository.

Current coverage in `.gitignore`:
```
*_session.json        ← covers zepto_session.json ✓
token.json            ← covers Gmail/Drive token ✓
                      ← blinkit_profile/ and easyecom_profile/ NOT covered ✗
```

**Immediate fix — add to `.gitignore`:**
```gitignore
# ── Scraper browser profiles (auth credentials — never commit) ───────────────
scrapers/sessions/*_profile/
```

**CI/CD solution (selected: Option A — Google Drive storage):**

GitHub-hosted runners are ephemeral — profiles must be fetched from external storage on each run. Selected approach:

1. **One-time setup:** Compress each profile dir → upload to a dedicated private Drive folder
2. **Each CI run start:** Download the zip from Drive → extract to `scrapers/sessions/`
3. **Each CI run end:** Re-upload updated profiles so fresh cookies are preserved for the next run
4. **Secret needed:** Add `PROFILE_STORAGE_DRIVE_FOLDER_ID` to GitHub Secrets

This reuses the existing `google_drive_upload.py` / `token.json` infrastructure. Profiles are ~10–50 MB compressed — well within Drive limits.

**Known limitation:** Concurrent runs would overwrite each other's profiles. Acceptable given scrapes run on a fixed daily schedule.

**Implementation deferred** — to be picked up after all open issues are reviewed.

---

#### C-02 — `gmail_otp.py` requests Drive scope it doesn't need
**File:** `scrapers/gmail_otp.py:29–32`

```python
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.file",   # ← Drive scope in OTP module
]
```

This module's declared purpose is fetching OTP codes from Gmail. The `drive.file` scope grants write access to Google Drive files the app creates. Any OAuth token generated using this module's scope list will have Drive access — broader than OTP fetching requires.

The Drive scope was likely added here so `gmail_otp.py` and `google_drive_upload.py` can share a single `token.json`. But embedding it here is misleading and grants unnecessary permissions if the token is ever misused.

**Suggestion:** Move the combined scope list to a central place (e.g., a `GMAIL_SCOPES` constant in `google_drive_upload.py` or a shared `auth.py`), and document that the shared token covers both Gmail read and Drive write. Remove the Drive scope from `gmail_otp.py`'s own `SCOPES` constant, or add a comment explaining why it's there.

---

### 🟡 Medium

---

#### M-01 — `zepto_scraper.py` uses Linux-only `%-d` date format
**File:** `scrapers/zepto_scraper.py:207`

```python
date_display = report_date.strftime("%-d %b %Y")  # e.g. "18 Feb 2026"
```

`%-d` (no zero-padding) works on Linux/macOS but **raises `ValueError` on Windows**. The dev environment is Windows 11; the production container is Linux — so this will fail in local testing.

**Suggestion:**
```python
date_display = f"{report_date.day} {report_date.strftime('%b %Y')}"
# e.g. "18 Feb 2026" — cross-platform
```

---

#### M-02 — `CITY_ALIASES` in `data_transformer.py` duplicates `CITY_NAME_MAP` in `shared/constants.py`
**Files:** `scrapers/data_transformer.py:18–39`, `shared/constants.py:44–86`

`data_transformer.py` has its own `CITY_ALIASES` dict that partially overlaps with the new `CITY_NAME_MAP` in `shared/constants.py`. They also disagree on canonical names:

```python
# data_transformer.py
"bangalore": "Bangalore"   # ← maps to "Bangalore"
# shared/constants.py
"Bangalore": "Bengaluru"   # ← maps to "Bengaluru"
```

Two sources of truth for city normalisation will cause inconsistencies between Excel imports (using `constants.py`) and scraper data (using `data_transformer.py`).

**Suggestion:** Remove `CITY_ALIASES` from `data_transformer.py` and replace the normalisation logic with `from shared.constants import normalise_city`.

---

#### M-03 — `gmail_otp.py` token path is relative to CWD, not project root
**File:** `scrapers/gmail_otp.py:42`

```python
elif Path("token.json").exists():
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
```

`Path("token.json")` resolves relative to whatever the current working directory is at runtime. If the scraper is invoked from a directory other than the project root (e.g., `cd scrapers && python gmail_otp.py`), the token will not be found even though it exists.

**Suggestion:**
```python
_TOKEN_PATH = Path(__file__).resolve().parent.parent / "token.json"
# ...
elif _TOKEN_PATH.exists():
    creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), SCOPES)
```

---

#### M-04 — `amazon_pi_scraper.py` raises `NotImplementedError` in `download_report()`
**File:** `scrapers/amazon_pi_scraper.py:86–89`

```python
def download_report(self, report_date: date) -> Path:
    raise NotImplementedError(
        "Amazon PI report download not yet implemented. ..."
    )
```

`BaseScraper.run()` has no guard for `NotImplementedError`. If this scraper is ever added to the `SCRAPERS` list in `orchestrator.py` before `download_report()` is implemented, it will raise an unhandled exception mid-orchestration and abort the Slack notification. Not a problem today (it's not in the SCRAPERS list), but a clear trap.

**Suggestion:** Add a comment above the class definition:
```python
# NOT in orchestrator.SCRAPERS — download_report() not implemented yet.
```

---

#### M-05 — `scripts/import_excel_sales.py` imports private function `_clean_sku`
**File:** `scripts/import_excel_sales.py:37`

```python
from scripts.excel_reader import (
    ...
    _clean_sku,    # ← private by convention
    ...
)
```

Importing an underscore-prefixed function from another module is fragile: any refactor of `excel_reader.py` that renames or inlines `_clean_sku` will break `import_excel_sales.py` at runtime without a linting warning.

**Suggestion:** Rename `_clean_sku` to `clean_sku` in `excel_reader.py` and add it to its `__all__`, making the cross-module dependency explicit and safe.

---

#### M-06 — `scripts/db_utils.py` constructs DB URL at import time with no validation
**File:** `scripts/db_utils.py:41–50`

```python
_DB_URL = (
    f"postgresql://"
    f"{os.environ.get('POSTGRES_USER', 'solara_user')}:"
    f"{os.environ.get('POSTGRES_PASSWORD', '')}@"   # ← empty string if not set
    ...
)
engine = create_engine(_DB_URL, pool_pre_ping=True)
```

If `POSTGRES_PASSWORD` is not set, the URL becomes `postgresql://solara_user:@localhost:5432/...` — a silently malformed URL. The engine is created (and possibly used) before `.env` is loaded in some import orders.

**Suggestion:** Assert the required vars are set before building the URL, or raise a clear error:
```python
password = os.environ.get("POSTGRES_PASSWORD")
if not password:
    raise RuntimeError("POSTGRES_PASSWORD is not set. Check your .env file.")
```

---

### 🟢 Low

---

#### L-01 — `scrapers/sessions/` directory is untracked
**Item:** `scrapers/sessions/` in `git ls-files --others`

The `sessions/` directory and its contents (`__init__.py`, `zepto_session.json`) are untracked. `zepto_session.json` is correctly gitignored via `*_session.json`. The browser profiles need gitignore entries (see C-01). `__init__.py` appears to be an empty marker file — it should be committed.

---

#### L-02 — `load_dotenv()` called at module level in individual scrapers
**Files:** `scrapers/zepto_scraper.py:27`, `scrapers/amazon_pi_scraper.py:18`, `scrapers/easyecom_scraper.py:50`

`load_dotenv()` is called at the top of each scraper module. When the orchestrator imports all scrapers, this call runs three or more times. It's harmless (python-dotenv is idempotent), but it's inconsistent — some scrapers do it, others don't.

**Suggestion:** Call `load_dotenv()` once in `orchestrator.py` at startup and remove the per-module calls.

---

#### L-03 — `notify_monthly_drive_folder()` has no trigger
**File:** `backend/app/utils/slack.py`

The new `notify_monthly_drive_folder()` function is defined but never called anywhere in the codebase — no cron job, no orchestrator hook. This is not a bug, but the function is orphaned until a caller is wired up.

---

#### L-04 — `database/alembic/versions/` is untracked
**Item:** `database/alembic/versions/` in `git ls-files --others`

Migration files should be committed — they're required to reproduce the schema in new environments. These being untracked is likely WIP state, but they should be reviewed and committed intentionally once the schema stabilises.

---

### Gitignore Check (untracked files)

| Path | Status |
|------|--------|
| `scrapers/sessions/zepto_session.json` | ✅ Covered by `*_session.json` |
| `scrapers/sessions/blinkit_profile/` | 🔴 **NOT gitignored** — see C-01 |
| `scrapers/sessions/easyecom_profile/` | 🔴 **NOT gitignored** — see C-01 |
| `scrapers/sessions/__init__.py` | Should be committed |
| `database/alembic/versions/` | Should be committed |
| `scripts/` (importer tools) | Should be committed |
| `docs/` | Should be committed |
| `.claude/` | Dev tooling — gitignore optional |

---

### Positive Notes

- **Model changes** (`inventory.py`, `sales.py`, `metadata.py`) are well-structured: clear grain comments on each table, appropriate use of `Numeric` over `Decimal`, consistent `UniqueConstraint` definitions, and good docstrings.
- **`totp_helper.py`** is clean and handles the near-expiry edge case (waiting for the next 30-second window) — a subtle but important detail.
- **`zepto_scraper.py`** session save/restore logic is solid: checks if session is still valid before skipping login, saves immediately after successful auth.
- **`shared/constants.py`** city normalisation map is comprehensive and well-commented.

---

### Action Plan

| Priority | Action |
|----------|--------|
| 🔴 C-01 | Add `scrapers/sessions/*_profile/` to `.gitignore` now; implement Drive-based profile storage for CI (Option A) — deferred |
| 🔴 C-02 | Document or relocate Drive scope in `gmail_otp.py` |
| 🟡 M-01 | Fix `%-d` → `f"{report_date.day} {report_date.strftime('%b %Y')}"` in `zepto_scraper.py` |
| 🟡 M-02 | Remove `CITY_ALIASES` from `data_transformer.py`, use `normalise_city` from `shared.constants` |
| 🟡 M-03 | Anchor `token.json` path to project root in `gmail_otp.py` |
| 🟡 M-05 | Make `_clean_sku` public in `excel_reader.py` |
| 🟡 M-06 | Add env var validation before DB URL construction in `db_utils.py` |
| 🟢 L-01 | Commit `scrapers/sessions/__init__.py` |
| 🟢 L-04 | Commit `database/alembic/versions/` once schema stabilises |
