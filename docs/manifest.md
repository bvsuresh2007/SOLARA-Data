# Project Manifest
_Updated: 2026-05-25_

## Structure

```
backend/app/
  main.py            # FastAPI entrypoint
  config.py          # Pydantic settings
  database.py        # Engine + session
  models/            # SQLAlchemy ORM models
  schemas/           # Pydantic response schemas
  api/               # Route handlers
  utils/             # slack.py, aggregation.py, excel_parsers.py
scrapers/
  base_scraper.py              # Abstract base (Playwright + retry)
  orchestrator.py              # Runs all scrapers on schedule
  amazon_scraper.py            # Amazon Seller Central (Playwright)
  amazon_pi_scraper.py         # Amazon PI portal (Playwright)
  amazon_sp_api_scraper.py     # Amazon SP-API (REST)
  blinkit_scraper.py           # Blinkit Seller Portal (Playwright)
  easyecom_scraper.py          # EasyEcom (Playwright)
  easyecom_inventory_scraper.py# EasyEcom inventory (Playwright)
  flipkart_email_scraper.py    # Flipkart (email-based)
  shopify_scraper.py           # Shopify Admin (REST API)
  swiggy_scraper.py            # Swiggy Vendor Dashboard (Playwright)
  zepto_scraper.py             # Zepto Vendor Dashboard (Playwright)
  hourly_shopify_sync.py       # Hourly Shopify sync job
  tools/amazon_asin_scraper/   # Standalone ASIN CLI (SOLARA-Data)
database/            # init_db.sql + Alembic migrations
frontend/app/        # Next.js pages (dashboard/, login/)
frontend/lib/        # API client + utilities
shared/              # Shared Python constants
scripts/             # Seed / import / backfill scripts
docs/                # All project documentation (see Docs Index below)
.claude/skills/      # Slash commands
```

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI entrypoint |
| `scrapers/orchestrator.py` | Runs all scrapers |
| `scrapers/shopify_scraper.py` | Primary sales data scraper (REST) |
| `frontend/app/dashboard/page.tsx` | Dashboard home |
| `frontend/lib/api.ts` | API client |
| `database/init_db.sql` | DB schema |
| `docker-compose.yml` | Start all services |
| `ingest_daily.py` | Daily portal ingestion runner (root) |
| `scrapers/tools/amazon_asin_scraper/main.py` | ASIN price/BSR CLI |

## Portals

| Portal | Scraper | Auth |
|--------|---------|------|
| Amazon Seller Central | `amazon_scraper.py` | Playwright |
| Amazon PI | `amazon_pi_scraper.py` | Playwright |
| Amazon SP-API | `amazon_sp_api_scraper.py` | REST API |
| Blinkit | `blinkit_scraper.py` | Playwright |
| EasyEcom | `easyecom_scraper.py` | Playwright |
| EasyEcom Inventory | `easyecom_inventory_scraper.py` | Playwright |
| Flipkart | `flipkart_email_scraper.py` | Email |
| Shopify | `shopify_scraper.py` | REST API |
| Swiggy | `swiggy_scraper.py` | Playwright |
| Zepto | `zepto_scraper.py` | Playwright |

## Docs Index

| Doc | Covers |
|-----|--------|
| `README.md` | Docs directory overview |
| `branches.md` | Branch strategy and naming |
| `database.md` | DB schema, tables, migrations |
| `dependencies.md` | Python/Node dependency notes |
| `frontend.md` | Frontend architecture, components, decisions |
| `git_workflows.md` | Git workflows, GitHub Actions |
| `inventory_download_guide.md` | How to download inventory reports |
| `ISSUES-BACKLOG.md` | Known issues and backlog |
| `missing_data_backfill.md` | Backfill procedures for missing data |
| `price-scraper-guide.md` | Amazon ASIN price scraper usage |
| `schema_planning.md` | DB schema design notes |
| `scrapers.md` | How scrapers work, execution modes |
| `upload_api.md` | Upload API endpoints and usage |
