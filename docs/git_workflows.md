# GitHub Actions Workflows

**Last updated:** 2026-02-24

All workflows live in `.github/workflows/`.

---

## Workflow inventory

| File | Name | Trigger | Status |
|------|------|---------|--------|
| `ci.yml` | CI | push / PR to main | ✅ Active |
| `monthly-drive-setup.yml` | Monthly Drive Folder Setup | 1st of month 00:30 IST + manual | ✅ Active |
| `scraper-easyecom.yml` | Scraper — EasyEcom | 11:00 AM IST daily + manual | ✅ Active |
| `scraper-zepto.yml` | Scraper — Zepto | 11:30 AM IST daily + manual | ✅ Active |
| `scraper-amazon-pi.yml` | Scraper — Amazon PI | 12:00 PM IST daily + manual | ✅ Active |
| `scraper-blinkit.yml` | Scraper — Blinkit | 12:30 PM IST daily + manual | ✅ Active |
| `scraper-swiggy.yml` | Scraper — Swiggy | 2:00 PM IST daily + manual | ✅ Active |
| `scraper-retry.yml` | Scraper — Retry Failed Runs | 3:00 PM IST daily + manual | ✅ Active |
| `seed-products.yml` | Seed Product Mappings | Manual only (`workflow_dispatch`) | ✅ Active |

> Shopify and Amazon Seller Central do not have workflows yet — their scrapers are stubs with unverified selectors and are not part of the daily automation.

---

## CI (`ci.yml`)

**Triggers:** push to `main`/`master`/`claude/**`, PR to `main`/`master`

Runs two parallel jobs:
- **Backend lint** — `ruff check backend/ scrapers/ shared/` (continue-on-error)
- **Frontend type check** — `npm run lint` in `frontend/` (continue-on-error)

No secrets required.

---

## Monthly Drive Folder Setup (`monthly-drive-setup.yml`)

**Triggers:** 1st of every month at 00:30 IST, or manually with an optional `month` input (format `YYYY-MM`).

Creates the `YYYY-MM` folder and per-portal subfolders inside `SolaraDashboard Reports` on Google Drive, then posts a Slack message with the folder link.

**Secrets used:** `GMAIL_TOKEN_JSON`, `GOOGLE_DRIVE_ROOT_FOLDER_ID`, `SLACK_WEBHOOK_URL`

---

## Scraper workflows — common structure

All five scraper workflows follow the same pattern:

```
checkout → setup Python 3.11 → pip install → playwright install chromium
→ restore token.json from GOOGLE_TOKEN_JSON secret
→ mkdir data/raw/<portal>
→ python inline script: resolve date → scraper.run(report_date)
→ upload-artifact: data files (always, 7 days)
→ upload-artifact: debug screenshots (on failure, 3 days)
→ curl Slack webhook (on failure)
```

**Manually triggering a run:**
```
GitHub → Actions → select workflow → Run workflow → enter date (or leave blank for yesterday)
```

**Checking downloaded files:**
Go to the workflow run → scroll to Artifacts → download the `<portal>-data-<run_id>` zip.

**Session expired?** Each profile-based scraper posts a Slack alert on failure with exact steps to re-authenticate locally and re-trigger.

---

## Scraper — EasyEcom (`scraper-easyecom.yml`)

| Property | Value |
|----------|-------|
| Schedule | `30 5 * * *` → 11:00 AM IST |
| Timeout | 60 min |
| Auth type | Persistent Chrome profile (Google OAuth) |
| Profile sync | Yes — `easyecom_profile` |
| Drive upload | Yes |

**Secrets used:** `GOOGLE_TOKEN_JSON`, `PROFILE_STORAGE_DRIVE_FOLDER_ID`, `POSTGRES_*`, `SLACK_WEBHOOK_URL`

**Session expiry:** Google OAuth session in profile persists well, but if it expires the Slack alert instructs you to run `python scrapers/easyecom_scraper.py` locally (visible mode), complete the Google login, then re-trigger the workflow.

---

## Scraper — Zepto (`scraper-zepto.yml`)

| Property | Value |
|----------|-------|
| Schedule | `0 6 * * *` → 11:30 AM IST |
| Timeout | 60 min |
| Auth type | Email + password + Gmail OTP |
| Profile sync | No (JSON storage state) |
| Drive upload | Yes |

**Secrets used:** `GOOGLE_TOKEN_JSON`, `PROFILE_STORAGE_DRIVE_FOLDER_ID`, `ZEPTO_LINK`, `ZEPTO_EMAIL`, `ZEPTO_PASSWORD`, `POSTGRES_*`, `SLACK_WEBHOOK_URL`

---

## Scraper — Amazon PI (`scraper-amazon-pi.yml`)

| Property | Value |
|----------|-------|
| Schedule | `30 6 * * *` → 12:00 PM IST |
| Timeout | 90 min (report generation + polling takes up to 15 min) |
| Auth type | Persistent Chrome profile (Email + password + TOTP) |
| Profile sync | Yes — `amazon_pi_profile` |
| Drive upload | Yes (6 files — one per category) |

**Secrets used:** `GOOGLE_TOKEN_JSON`, `PROFILE_STORAGE_DRIVE_FOLDER_ID`, `GOOGLE_DRIVE_ROOT_FOLDER_ID`, `AMAZON_PI_LINK`, `AMAZON_PI_EMAIL`, `AMAZON_PI_PASSWORD`, `AMAZON_PI_TOTP_SECRET`, `POSTGRES_*`, `SLACK_WEBHOOK_URL`

**Session expiry:** Run `python scrapers/amazon_pi_scraper.py` locally to complete the TOTP login and refresh the profile.

---

## Scraper — Blinkit (`scraper-blinkit.yml`)

| Property | Value |
|----------|-------|
| Schedule | `0 7 * * *` → 12:30 PM IST |
| Timeout | 60 min |
| Auth type | Persistent Chrome profile (Email + Gmail OTP) |
| Profile sync | Yes — `blinkit_profile` |
| Drive upload | Yes |

**Secrets used:** `GOOGLE_TOKEN_JSON`, `PROFILE_STORAGE_DRIVE_FOLDER_ID`, `GOOGLE_DRIVE_ROOT_FOLDER_ID`, `BLINKIT_LINK`, `BLINKIT_EMAIL`, `POSTGRES_*`, `SLACK_WEBHOOK_URL`

**Session expiry:** Run `python scrapers/blinkit_scraper.py` locally to complete the OTP login and refresh the profile.

---

## Scraper — Swiggy (`scraper-swiggy.yml`)

| Property | Value |
|----------|-------|
| Schedule | `30 8 * * *` → 2:00 PM IST |
| Timeout | 30 min (covers 2–10 min report generation + polling) |
| Auth type | Persistent Chrome profile (Email + Gmail OTP) |
| Profile sync | Yes — `swiggy_profile` |
| Drive upload | Yes |

**Secrets used:** `GOOGLE_TOKEN_JSON`, `PROFILE_STORAGE_DRIVE_FOLDER_ID`, `GOOGLE_DRIVE_ROOT_FOLDER_ID`, `SWIGGY_LINK`, `SWIGGY_EMAIL`, `SLACK_WEBHOOK_URL`

**Session expiry:** Run `python scrapers/swiggy_scraper.py` locally (headed mode) to complete the OTP login and refresh the profile. Profile auto-uploads to Drive on exit.

---

## Scraper — Retry (`scraper-retry.yml`)

| Property | Value |
|----------|-------|
| Schedule | `30 9 * * *` → 3:00 PM IST |
| Timeout | 15 min |
| Auth type | GitHub API only (`GITHUB_TOKEN`) |

**What it does:** Runs 30 minutes after Blinkit finishes (giving Amazon PI's 90-min window time to complete). Uses `gh run list --event schedule` to find today's scheduled run for each scraper workflow and checks its conclusion. Re-triggers any that failed — **exactly once**.

**Retry-once guarantee:** The workflow filters by `--event schedule`, so it only sees the original cron-triggered runs — not the `workflow_dispatch` runs it fires. A retry run that fails a second time is invisible to this workflow. The individual scraper's own Slack failure step handles second-failure notifications.

**Secrets used:** `GITHUB_TOKEN` (built-in), `SLACK_WEBHOOK_URL`

**No additional secrets needed** — `GITHUB_TOKEN` has `actions: write` permission (set in the workflow file).

**Slack notifications:**
- Always posts a summary: what was retried, what was already OK, what was still running at check time.
- If no failures → green message.
- If retries were fired → yellow message listing which portals were re-triggered.
- If retried scrapers then fail again → each scraper's own failure alert fires (red Slack message from the individual scraper workflow).

**Manual use:** Trigger via `workflow_dispatch` to force a re-check at any time. Accepts an optional `report_date` to override the date passed to retried scrapers.

---

## Schedule at a glance (IST)

```
11:00 AM  EasyEcom       (05:30 UTC)
11:30 AM  Zepto          (06:00 UTC)
12:00 PM  Amazon PI      (06:30 UTC)
12:30 PM  Blinkit        (07:00 UTC)
 2:00 PM  Swiggy         (08:30 UTC)
 3:00 PM  Retry check    (09:30 UTC)  ← re-fires any that failed above

 1st of month 00:30 AM  Monthly Drive Folder Setup  (18:30 UTC prev day)
```

---

## All secrets — complete reference

Go to: **GitHub repo → Settings → Secrets and variables → Actions → Secrets**

| Secret | Used by | Description |
|--------|---------|-------------|
| `GOOGLE_TOKEN_JSON` | EasyEcom, Zepto, Amazon PI, Blinkit, Swiggy | `base64 -w0 token.json` — OAuth token for Drive + Gmail. Generate with `python auth_gmail.py`. |
| `GMAIL_TOKEN_JSON` | Monthly Drive setup | Same token, different var name used by the setup script. Set to the same base64 value. |
| `GOOGLE_DRIVE_ROOT_FOLDER_ID` | Monthly Drive setup, Amazon PI, Blinkit, Swiggy | ID of the `SolaraDashboard Reports` root Drive folder. |
| `PROFILE_STORAGE_DRIVE_FOLDER_ID` | EasyEcom, Zepto, Amazon PI, Blinkit, Swiggy | ID of the `SolaraDashboard Profiles` Drive folder. |
| `SLACK_WEBHOOK_URL` | EasyEcom, Amazon PI, Blinkit, Swiggy, Monthly setup, Retry | Incoming webhook URL from Slack app. |
| `POSTGRES_HOST` | All scrapers | Supabase host, e.g. `db.xxxx.supabase.co` |
| `POSTGRES_PORT` | All scrapers | `5432` |
| `POSTGRES_DB` | All scrapers | `postgres` |
| `POSTGRES_USER` | All scrapers | `postgres` |
| `POSTGRES_PASSWORD` | All scrapers | Supabase DB password |
| `ZEPTO_LINK` | Zepto | Portal login URL |
| `ZEPTO_EMAIL` | Zepto | Vendor email |
| `ZEPTO_PASSWORD` | Zepto | Vendor password |
| `AMAZON_PI_LINK` | Amazon PI | `https://pi.amazon.in/brand-summary` |
| `AMAZON_PI_EMAIL` | Amazon PI | Seller email |
| `AMAZON_PI_PASSWORD` | Amazon PI | Seller password |
| `AMAZON_PI_TOTP_SECRET` | Amazon PI | Base32 TOTP secret (from Amazon 2FA setup) |
| `BLINKIT_LINK` | Blinkit | Portal login URL (`https://partnersbiz.com/app/soh`) |
| `BLINKIT_EMAIL` | Blinkit | Vendor email (OTP sent here via Gmail) |
| `SWIGGY_LINK` | Swiggy | Portal URL (`https://partner.swiggy.com/instamart/sales`) |
| `SWIGGY_EMAIL` | Swiggy | Vendor email — OTP sent to this address via `no-reply@swiggy.in` |

