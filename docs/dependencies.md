# Dependency Management Reference

**Last Updated**: 2026-02-25

---

## Requirements File Map

| File | Installed by | Purpose |
|------|-------------|---------|
| `requirements.txt` | pip cache key in `monthly-drive-setup.yml` | Root-level scripts (Drive folder setup, one-off utilities) |
| `backend/requirements.txt` | `backend/Dockerfile` | FastAPI service |
| `scrapers/requirements.txt` | `scrapers/Dockerfile` + all scraper CI workflows | Portal scrapers + CI runner environment |
| `scrapers/tools/*/requirements.txt` | Manual / standalone use only | Self-contained CLI price-scraper tools |

---

## Canonical Playwright Version

**`playwright==1.44.0`** — pinned in `scrapers/requirements.txt`.

This is the version used in all CI workflows and Docker. The standalone tools use `playwright>=1.40.0` (a floor, not a pin) so they stay compatible without needing a separate update step.

### Upgrading Playwright

1. Update `scrapers/requirements.txt` to the new pinned version.
2. Run the updated workflows once to verify.
3. The tool `requirements.txt` files need no change unless the new version breaks a floor (`>=1.40.0`).

---

## `scrapers/requirements.txt` — Authoritative Scraper Deps

This is the **single source of truth** for all scraper-related Python packages. All CI workflows (`scraper-blinkit.yml`, `scraper-swiggy.yml`, `scraper-zepto.yml`, `scraper-amazon-pi.yml`) install from this file.

Previously, `pyotp`, `google-auth*`, and `python-dotenv` were hardcoded inside every workflow YAML's `pip install` step. They are now consolidated here to prevent drift.

| Package | Version | Why |
|---------|---------|-----|
| `playwright` | `==1.44.0` | Browser automation for all portal scrapers |
| `pandas` | `==2.2.2` | Excel/CSV parsing |
| `openpyxl` | `==3.1.2` | `.xlsx` read/write |
| `requests` | `==2.32.3` | HTTP for Slack webhooks, Shopify API |
| `psycopg2-binary` | `==2.9.9` | PostgreSQL driver |
| `sqlalchemy` | `==2.0.30` | ORM / DB upserts |
| `google-auth` | `==2.29.0` | Drive profile sync + Gmail OTP |
| `google-auth-oauthlib` | `==1.2.0` | Google OAuth flow |
| `google-api-python-client` | `==2.126.0` | Drive API client |
| `pyotp` | `==2.9.0` | Amazon PI 2FA (TOTP) |
| `python-dotenv` | `==1.0.1` | `.env` loading in local runs |

---

## Standalone Tool Requirements

Each of the 4 price-scraper CLI tools has its own minimal `requirements.txt` so they can be installed and run independently without the full scraper service stack.

| Tool | Requirements |
|------|-------------|
| `scrapers/tools/blinkit_price_scraper/` | `playwright>=1.40.0` |
| `scrapers/tools/swiggy_price_scraper/` | `playwright>=1.40.0` |
| `scrapers/tools/zepto_price_scraper/` | `playwright>=1.40.0` |
| `scrapers/tools/amazon_asin_scraper/` | `playwright>=1.40.0`, `requests`, `beautifulsoup4`, `lxml` |

The Amazon ASIN tool also needs `requests` (Slack notifier) and `beautifulsoup4` + `lxml` (server-side HTML parsing via BeautifulSoup).

---

## Version Drift Rules

1. **Never hardcode packages in workflow YAML `pip install` steps.** All scraper deps belong in `scrapers/requirements.txt`. Workflow YAML should only call `pip install -r scrapers/requirements.txt`.

2. **Playwright is always pinned (`==`) in `scrapers/requirements.txt`.** The tools use a floor (`>=`) — this is intentional and correct.

3. **Root `requirements.txt` covers only root-level scripts.** Do not add scraper or backend deps here.

4. **When adding a new package to a scraper**, add it to `scrapers/requirements.txt`, not to the workflow YAML and not to any tool `requirements.txt` unless the tool genuinely needs it standalone.

5. **BeautifulSoup/lxml belong only in `amazon_asin_scraper/`.** The other 3 price tools do all extraction via `page.evaluate()` — no HTML parsing library needed.
