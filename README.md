# SolaraDashboard

A comprehensive sales & inventory data aggregation platform for multi-portal e-commerce businesses.

## What's Inside

This repository combines two tools:

| Tool | Path | Purpose |
|------|------|---------|
| **SolaraDashboard** | (root) | Full-stack BI platform — scrapes, stores, and visualises daily sales & inventory data from Swiggy, Blinkit, Amazon, Zepto, Shopify, Myntra, Flipkart |
| **Amazon ASIN Scraper** | `scrapers/tools/amazon_asin_scraper/` | Standalone CLI tool — fetches real-time price, BSR, and seller info for individual Amazon ASINs |

---

## Architecture

```
SolaraDashboard/
├── backend/          # FastAPI REST API
├── scrapers/         # Portal scrapers + standalone ASIN tool
│   └── tools/
│       └── amazon_asin_scraper/   # Preserved SOLARA-Data CLI
├── database/         # PostgreSQL schema + Alembic migrations
├── frontend/         # Next.js 14 dashboard
├── shared/           # Shared Python constants
└── data/             # Raw & processed data files (gitignored)
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 18+ (for local frontend dev)
- Python 3.10+ (for local backend/scraper dev)

### 1. Configure environment
```bash
cp .env.example .env
# Edit .env with your credentials
```

### 2. Start all services
```bash
docker-compose up -d
```

### 3. Run database migrations
```bash
docker-compose exec backend alembic upgrade head
```

### 4. Access the dashboard
- **Dashboard**: http://localhost:3000
- **API docs**: http://localhost:8000/docs

---

## Amazon ASIN Scraper (Standalone CLI)

Located in `scrapers/tools/amazon_asin_scraper/`. Works independently without Docker.

```bash
cd scrapers/tools/amazon_asin_scraper

# Install dependencies
pip install -r requirements.txt

# Scrape a single ASIN
python main.py B0CZHTGKJN -m in

# Scrape multiple ASINs, export CSV
python main.py B0CZHTGKJN B09G9HD6PD -o results.csv -m in

# Use Selenium to bypass CAPTCHA
python main.py B0CZHTGKJN --browser -m in

# Bulk scrape from file
python main.py -f asins.txt -o results.csv -m in

# Filter by seller, post to Slack
python main.py -f asins.txt --seller "Solara" --slack
```

### ASIN Scraper Features
- Price, BSR (main + sub-category), seller, ships-from, fulfilled-by
- Dual mode: `requests` (fast) or `--browser` Selenium (CAPTCHA bypass)
- CSV export with UTF-8 BOM (Excel-compatible)
- Slack webhook notifications
- Multi-marketplace support (`-m in`, `co.uk`, `de`, etc.)

---

## Services

| Service | Port | Description |
|---------|------|-------------|
| Frontend | 3000 | Next.js dashboard |
| Backend API | 8000 | FastAPI + automatic docs at `/docs` |
| PostgreSQL | 5432 | Primary database |
| Scrapers | — | Runs on cron schedule (default 2:00 AM IST) |

---

## Database Schema

9-table optimised schema:

- **portals** — Portal master (Swiggy, Blinkit, Amazon, Zepto, Shopify, Myntra, Flipkart)
- **cities** — City/region master
- **warehouses** — Facility-level tracking
- **product_categories** — 3-level category hierarchy
- **products** — Unified product master (Solara SKUs)
- **product_portal_mapping** — Maps portal-specific IDs (ASIN ↔ item_id ↔ SKU)
- **sales_data** — Daily sales (revenue, quantity, orders, discounts)
- **inventory_data** — Daily inventory snapshots (warehouse & city level)
- **scraping_logs** — Audit trail

---

## Portal Support

| Portal | Sales | Inventory | Auth Method |
|--------|-------|-----------|-------------|
| Swiggy | ✅ | ✅ | Email/Password |
| Blinkit | ✅ | ✅ | Email/Password |
| Amazon | ✅ | ✅ | Email/Password |
| Zepto | ✅ | ✅ | Email/Password |
| Shopify | ✅ | — | API Key |
| Myntra | ✅ | — | Email/Password |
| Flipkart | ✅ | — | Email/Password |

---

## Slack Notifications

- **Daily**: Scraping status, records processed, failures
- **Weekly**: Sales summary, top products & cities
- **Monthly**: Growth metrics, inventory turnover
- **Alerts**: Low stock, scraping failures, data anomalies

---

## Environment Variables

See `.env.example` for all required variables.

---

## Documentation

Full technical documentation lives in [`docs/`](./docs/README.md):

| Doc | Contents |
|-----|----------|
| [`docs/database.md`](./docs/database.md) | Schema reference — all 13 tables, indexes, duplicate prevention |
| [`docs/scrapers.md`](./docs/scrapers.md) | Portal scrapers — run modes, env vars, session management |
| [`docs/upload_api.md`](./docs/upload_api.md) | Upload REST API — endpoints, file types, parser registry |
| [`docs/git_workflows.md`](./docs/git_workflows.md) | GitHub Actions workflows — triggers, secrets, failure handling |
| [`docs/frontend.md`](./docs/frontend.md) | Next.js architecture, components, API client |
| [`docs/price-scraper-guide.md`](./docs/price-scraper-guide.md) | Step-by-step guide to running the Amazon ASIN price scraper |

For Claude Code context and project conventions, see [`CLAUDE.md`](./CLAUDE.md).

---

## License

To be determined.
