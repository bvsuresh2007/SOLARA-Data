# SolaraDashboard API — team access

Programmatic read access to the dashboard's sales & inventory data. The web
dashboard (https://solara-frontend-891651347357.asia-south1.run.app) stays
Google-SSO gated for `@solara.in`; this is for scripts/tools/teammates that need
the data directly.

## Base URL
```
https://solara-backend-goe6h2dneq-el.a.run.app
```

## Authentication
Every `/api/*` call needs your personal API key (issued to you by the admin; see
`scripts/generate_api_keys.py`). Send it as a header — either works:

```
X-API-Key: <your-key>
Authorization: Bearer <your-key>
```

- `GET /health` needs no key.
- Keys are per-person and logged by owner, so **don't share yours** — sharing
  makes the logs lie and means a leak is traced to you. Ask the admin to revoke
  (remove your `label:key` entry) + reissue if yours leaks.
- A missing/invalid key returns `401`.

## Endpoints (read-only)
Most accept query params like `start_date=YYYY-MM-DD`, `end_date=YYYY-MM-DD`,
`portal_id`. Dates are IST; `imported_at` timestamps in the data are UTC.

| Path | Returns |
|------|---------|
| `GET /api/sales/summary` | revenue, units, orders, active SKUs for a period |
| `GET /api/sales/by-portal` | sales split by portal |
| `GET /api/sales/by-city` | sales split by city |
| `GET /api/sales/by-product` | sales split by SKU |
| `GET /api/sales/trend` | daily revenue/units/ASP series |
| `GET /api/sales/by-category` | sales by product category |
| `GET /api/sales/targets` | target vs actual by portal |
| `GET /api/sales/portal-daily` | per-portal daily grid (`portal`, `start_date`, `end_date`) |
| `GET /api/sales/latest-date` | newest `sale_date` in the DB (optional `portal_id`) |
| `GET /api/inventory/current` | latest inventory snapshot rows |
| `GET /api/inventory/low-stock` | SKUs under a `threshold` (default 100) |
| `GET /api/metadata/portals` · `/cities` · `/scraping-logs` · `/action-items` | reference + run health |

Interactive reference: `GET /docs` (OpenAPI/Swagger).

## Examples
curl:
```bash
curl -H "X-API-Key: $SOLARA_API_KEY" \
  "https://solara-backend-goe6h2dneq-el.a.run.app/api/sales/summary?start_date=2026-10-01&end_date=2026-10-04"
```

Python:
```python
import os, requests
BASE = "https://solara-backend-goe6h2dneq-el.a.run.app"
H = {"X-API-Key": os.environ["SOLARA_API_KEY"]}
r = requests.get(f"{BASE}/api/sales/by-portal",
                 params={"start_date": "2026-10-01", "end_date": "2026-10-04"}, headers=H)
r.raise_for_status()
print(r.json())
```

## For the admin — issuing & revoking keys
- **Issue:** `python scripts/generate_api_keys.py alice bob …` → writes each
  person's `<label>.txt` plus a `DASHBOARD_API_KEYS.secret.txt`.
- **Enable:** set that value as the GitHub secret `DASHBOARD_API_KEYS` (Settings →
  Secrets and variables → Actions). The backend deploy wires it in
  (`.github/workflows/deploy.yml`), so the next deploy enforces keys.
- **Revoke one person:** remove their `label:key` entry from the secret, redeploy.
- **Note:** while `DASHBOARD_API_KEYS` is unset the API is **open** (no key
  required) — set it to close that.
