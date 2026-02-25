# Branch Status Overview

**Current working branch**: `feature/consolidate-price-scrapers`
**Updated**: 2026-02-25

---

## All Branches (excluding current)

| Branch | Merged? | Notes |
|--------|---------|-------|
| `main` | N/A | Production base. Current branch is 10+ commits ahead and has not been PR'd yet. |
| `claude/merge-solara-projects-Qo5Sd` | ✅ Fully merged | Ancestor of current branch. Current is 13+ commits ahead. Nothing to recover. |
| `claude/build-asin-scraper-UWQQf` | ✅ Fully merged | Original Amazon ASIN scraper build. Zero unique commits vs current. Entire history is contained in current branch. |
| `feature/dashboard-overhaul` | ⚠️ Partially merged | Remote was deleted. 10 commits NOT in current branch — see details below. |
| `origin/claude/restore-amazon-scraper-mCFln` | ✅ Fully merged | Zero unique commits vs current. Earlier state of the ASIN scraper before sub-BSR was added. |
| `origin/claude/social-media-feedback-collection-NXqKy` | ✅ Superseded | Amazon sub-BSR + seller tracking improvements from this branch are **already integrated** into `scrapers/tools/amazon_asin_scraper/scraper.py`. Old Blinkit Selenium scraper (`src/blinkit_scraper.py`) is superseded by the Playwright version in `scrapers/tools/blinkit_price_scraper/`. |
| `origin/claude/swiggy-clone-560103-f6Au8` | ✅ Superseded | 20+ commits of incremental improvements to an old Selenium-based Swiggy price scraper at `src/swiggy_scraper.py`. Fully superseded by `scrapers/tools/swiggy_price_scraper/swiggy_scraper.py` (Playwright). Our Playwright version is simpler, more reliable, and already has batch rate-limiting. |
| `origin/claude/zepto-product-scraper-UrEwF` | ✅ Superseded | 3 commits for an old Zepto scraper at `src/zepto_scraper.py`. Fully superseded by `scrapers/tools/zepto_price_scraper/zepto_scraper.py` (Playwright). |

---

## `feature/dashboard-overhaul` — Detail

Remote deleted but local branch still exists. Has **10 unique commits** not in `feature/consolidate-price-scrapers`:

| Commit | Description | Status |
|--------|-------------|--------|
| `9aedec3` | docs: frontend architecture + shadcn migration code review | Low priority — docs only |
| `f248b2a` | refactor(frontend): migrate all components and pages to shadcn primitives | Already done in current branch via `d8945c1` |
| `e700aff` | feat(frontend): add shadcn UI primitives and shared NavTabs component | Already done in current branch |
| `95bb2d6` | chore(frontend): install shadcn/ui and configure CSS variable theming | Already done in current branch |
| `dc078f5` | feat: populate DB after each scraper run | **May be worth reviewing** — adds DB write step to scraper workflows |
| `7b7058e` | fix: replace 'Amazon' portal folder with 'Amazon PI' in monthly Drive setup | Potentially useful — Drive folder name fix |
| `8a10673` | chore: reschedule scraper workflows with 10-min gaps from 11:00 AM IST | Workflow scheduling tweak |
| `718482b` | fix: restore Google token correctly + pin ubuntu-22.04 for all scrapers | CI/CD fix — may already be solved differently |
| `0701282` | fix: add pydantic-settings to monthly-drive-setup workflow deps | CI dependency fix |
| `7f287b3` | fix: resolve duplicate env key causing workflow YAML validation failure | CI fix |

The 4 frontend shadcn commits (`95bb2d6`, `e700aff`, `f248b2a`, `9aedec3`) are already superseded — the shadcn migration was cherry-picked/redone in the current branch (`d8945c1 feat(frontend): migrate dashboard UI to shadcn/ui component library`).

The workflow fixes (`7f287b3`, `0701282`, `718482b`, `8a10673`) and the Drive folder rename (`7b7058e`) could be selectively cherry-picked if those workflows are actively broken.

The `dc078f5 feat: populate DB after each scraper run` is the most substantive unique commit — worth reviewing if auto-populate is not yet wired into the current scraper workflows.

---

## Summary

- **Safe to delete**: `claude/build-asin-scraper-UWQQf`, `claude/merge-solara-projects-Qo5Sd`, `origin/claude/restore-amazon-scraper-mCFln`
- **Superseded, can delete**: `origin/claude/social-media-feedback-collection-NXqKy`, `origin/claude/swiggy-clone-560103-f6Au8`, `origin/claude/zepto-product-scraper-UrEwF`
- **Review before deleting**: `feature/dashboard-overhaul` (local only) — 3–5 commits may have useful CI/workflow fixes not yet in current branch
