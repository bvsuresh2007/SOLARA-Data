# Missing Sales Data — Backfill Plan

**Scanned**: 2026-02-25
**Range**: 2026-01-01 to 2026-02-25 (56 calendar days)
**Script**: `scripts/find_missing_dates.py` (re-run anytime to refresh)
**CSV**: `data/source/missing_dates.csv`

---

## Summary

| Portal     | Has Data | Missing | Coverage |
|------------|----------|---------|----------|
| Swiggy     | 40 days  | 16 days | 71.4%    |
| Blinkit    | 41 days  | 15 days | 73.2%    |
| Zepto      | 41 days  | 15 days | 73.2%    |
| Amazon PI  | 40 days  | 16 days | 71.4%    |
| EasyEcom   | 0 days   | 56 days | 0.0%     |

---

## Missing Dates by Portal

### Swiggy (16 days)
- 2026-02-09 to 2026-02-19 (11 days)
- 2026-02-21 to 2026-02-25 (5 days)

### Blinkit (15 days)
- 2026-02-09 to 2026-02-19 (11 days)
- 2026-02-21 (1 day)
- 2026-02-23 to 2026-02-25 (3 days)

### Zepto (15 days)
- 2026-02-09 to 2026-02-19 (11 days)
- 2026-02-21 (1 day)
- 2026-02-23 to 2026-02-25 (3 days)

### Amazon PI (16 days)
- 2026-02-09 to 2026-02-19 (11 days)
- 2026-02-21 to 2026-02-25 (5 days)

### EasyEcom (56 days — entire range)
- 2026-01-01 to 2026-02-25 (56 days)
- Note: portal not registered in DB under `"easyecom"`; fallback portals (`myntra`, `shopify`) also have no data. Needs DB portal entry + full backfill.

---

## Key Observations

1. **January fully covered** for all 4 active scrapers — data Jan 1–Feb 8 is clean.
2. **Feb 9–19 common gap** across all portals — scrapers appear to have stopped for ~11 days.
3. **Feb 20+ is spotty** — partial runs resumed but not consistently through Feb 25.
4. **EasyEcom is entirely missing** — zero imports for the whole period.

---

## Work Items (for backfill branch)

- [ ] Investigate why scrapers stopped on Feb 9 (CI failure? credential expiry? Drive profile?)
- [ ] Manually download missing date ranges from each portal and run `scripts/populate_db.py`
- [ ] Register `easyecom` as a portal in the DB (or map to existing `myntra`/`shopify` entries)
- [ ] Backfill EasyEcom data for the full Jan–Feb range
- [ ] Add a scheduled alert (Slack or dashboard badge) when a portal goes >2 days without data
- [ ] Consider adding a "data freshness" indicator to the dashboard
