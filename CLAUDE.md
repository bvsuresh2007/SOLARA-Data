# SolaraDashboard — Merged Project Guide

**Last Updated**: 2026-02-19
**Version**: 1.0.0 (Merged & Implemented)

---

## What This Repository Contains

This repository is the result of merging two projects:

| Project | Description | Location |
|---------|-------------|----------|
| **SolaraDashboard** | Full-stack BI platform for multi-portal e-commerce | (root) |
| **SOLARA-Data** (Amazon ASIN Scraper) | Standalone CLI for Amazon price/BSR scraping | `scrapers/tools/amazon_asin_scraper/` |

Both projects are fully functional. No functionality was lost.

---

## Project Structure

```
SolaraDashboard/
├── backend/                      # FastAPI REST API
│   ├── app/
│   │   ├── main.py              # FastAPI app entrypoint
│   │   ├── config.py            # Pydantic settings (reads .env)
│   │   ├── database.py          # SQLAlchemy engine + session
│   │   ├── models/              # ORM models (metadata, sales, inventory)
│   │   ├── schemas/             # Pydantic response schemas
│   │   ├── api/                 # Route handlers (metadata, sales, inventory)
│   │   └── utils/               # slack.py, aggregation.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── scrapers/                     # Portal scraping service
│   ├── base_scraper.py          # Abstract base (Playwright + retry logic)
│   ├── swiggy_scraper.py        # Swiggy Vendor Dashboard
│   ├── blinkit_scraper.py       # Blinkit Seller Portal
│   ├── amazon_scraper.py        # Amazon Seller/Vendor Central
│   ├── zepto_scraper.py         # Zepto Vendor Dashboard
│   ├── shopify_scraper.py       # Shopify Admin API (no browser)
│   ├── excel_parser.py          # Per-portal Excel/CSV parsers
│   ├── data_transformer.py      # Normalise + map to DB IDs
│   ├── orchestrator.py          # Main entry: runs all scrapers, upserts data
│   ├── crontab                  # Cron schedule (configurable via .env)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── tools/
│       └── amazon_asin_scraper/ # ← SOLARA-Data (preserved as-is)
│           ├── main.py          # CLI entry point
│           ├── scraper.py       # AmazonScraper class (HTTP + Selenium)
│           ├── slack_notifier.py# Slack webhook for ASIN results
│           ├── requirements.txt
│           └── README.md
│
├── database/                     # DB schema & migrations
│   ├── init_db.sql              # 9-table schema (seed data included)
│   ├── alembic.ini
│   └── alembic/
│       ├── env.py
│       └── versions/            # Migration scripts go here
│
├── frontend/                     # Next.js 14 dashboard
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx             # Redirects → /dashboard
│   │   └── dashboard/
│   │       ├── page.tsx         # Overview: KPIs, portal/city charts, scraping status
│   │       ├── sales/page.tsx   # Sales breakdown: portal, city, product
│   │       └── inventory/page.tsx # Inventory: low-stock alerts, snapshots
│   ├── components/
│   │   ├── charts/metric-card.tsx
│   │   ├── charts/bar-chart.tsx
│   │   ├── tables/data-table.tsx
│   │   └── filters/filter-bar.tsx
│   ├── lib/api.ts               # Type-safe API client
│   ├── lib/utils.ts             # formatCurrency, formatNumber, cn()
│   ├── package.json
│   └── Dockerfile
│
├── shared/
│   ├── __init__.py
│   └── constants.py             # Portal names, cities, regions, status codes
│
├── data/
│   ├── raw/                     # Downloaded Excel/CSV files (gitignored)
│   └── processed/               # Archived files (gitignored)
│
├── .github/workflows/ci.yml     # Lint CI for backend + frontend
├── docker-compose.yml           # Orchestrates all 4 services
├── .env.example                 # All required env vars
├── .gitignore
└── README.md
```

---

## Database Schema (9 Tables)

**Master** (4): `portals`, `cities`, `warehouses`, `product_categories`
**Product** (2): `products`, `product_portal_mapping`
**Transaction** (2): `sales_data`, `inventory_data`
**Audit** (1): `scraping_logs`

See `database/init_db.sql` for full DDL with indexes and constraints.

---

## Quick Start

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env — add DB password, portal credentials, Slack webhook

# 2. Start all services
docker-compose up -d

# 3. Run migrations (first time only)
docker-compose exec backend alembic upgrade head

# 4. Access
#   Dashboard: http://localhost:3000
#   API docs:  http://localhost:8000/docs
```

---

## Amazon ASIN Scraper (Standalone Tool)

Preserved from the original SOLARA-Data project. Works without Docker.

```bash
cd scrapers/tools/amazon_asin_scraper
pip install -r requirements.txt
python main.py B0CZHTGKJN -m in --slack
```

See `scrapers/tools/amazon_asin_scraper/README.md` for full usage.

---

## Implementation Status

### ✅ IMPLEMENTED

- [x] Full directory structure
- [x] Docker Compose (postgres, backend, frontend, scrapers)
- [x] PostgreSQL 9-table schema with indexes, constraints, seed data
- [x] Alembic migration scaffold
- [x] FastAPI backend: models, schemas, all API endpoints
  - GET /api/sales/summary, /daily, /by-portal, /by-city, /by-product
  - GET /api/inventory/current, /trends, /low-stock
  - GET /api/metadata/portals, /cities, /warehouses, /scraping-logs
- [x] Slack notifications (scraping complete, low stock, failure, weekly)
- [x] Portal scrapers (Playwright): Swiggy, Blinkit, Amazon, Zepto
- [x] Shopify scraper (REST API — no browser needed)
- [x] Excel/CSV parsers for all 5 portals (with date format normalisation)
- [x] Data transformer (city aliases, product mapping, warehouse lookup)
- [x] Orchestrator (runs all scrapers, upserts data, logs, notifies)
- [x] Configurable cron schedule via .env
- [x] Next.js frontend: Overview, Sales, Inventory dashboards
- [x] Shared constants (portals, cities, regions)
- [x] Amazon ASIN Scraper (preserved from SOLARA-Data)
- [x] CI workflow (GitHub Actions)

### ⏸️ AWAITING USER INPUT

- [ ] Portal login credentials (add to .env)
- [ ] Scraping schedule time (SCRAPE_SCHEDULE_HOUR / SCRAPE_SCHEDULE_MINUTE in .env)
- [ ] Slack workspace setup (SLACK_WEBHOOK_URL in .env)
- [ ] Product master data & portal ID mapping (product_portal_mapping table)
- [ ] Playwright scraper selectors — these will need adjustment once portal UIs are tested

---

## Key Environment Variables

| Variable | Description |
|----------|-------------|
| `POSTGRES_PASSWORD` | Required — DB password |
| `SWIGGY_EMAIL / PASSWORD` | Swiggy vendor login |
| `BLINKIT_EMAIL / PASSWORD` | Blinkit seller login |
| `AMAZON_EMAIL / PASSWORD` | Amazon seller central login |
| `ZEPTO_EMAIL / PASSWORD` | Zepto vendor login |
| `SHOPIFY_API_KEY / API_SECRET / STORE_URL` | Shopify API credentials |
| `SLACK_WEBHOOK_URL` | Incoming webhook for notifications |
| `SCRAPE_SCHEDULE_HOUR` | Cron hour (default: 2) |
| `SCRAPE_SCHEDULE_MINUTE` | Cron minute (default: 0) |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend | Next.js 14, Recharts, TailwindCSS |
| Backend API | FastAPI, SQLAlchemy 2.0, Pydantic v2 |
| Database | PostgreSQL 15, Alembic migrations |
| Scrapers | Playwright (portal dashboards), Requests (Shopify API) |
| ASIN Tool | Requests + BeautifulSoup4, Selenium (browser mode) |
| Notifications | Slack Incoming Webhooks |
| Containerisation | Docker, Docker Compose |
| Scheduling | Cron (inside scrapers container) |

---

## Merge Notes

The original SOLARA-Data was a Python CLI tool (`main.py`, `src/scraper.py`, `src/slack_notifier.py`) for scraping Amazon ASINs. It has been:

1. **Preserved unchanged** in `scrapers/tools/amazon_asin_scraper/`
2. **Import paths updated**: `from src.scraper import ...` → `from scraper import ...` (since it now runs from its own directory)
3. **Documented** with a dedicated `README.md`

The SolaraDashboard's `scrapers/amazon_scraper.py` serves a different purpose: it scrapes the Amazon Seller/Vendor Central dashboard for daily sales & inventory data. It is completely separate from the ASIN tool.
