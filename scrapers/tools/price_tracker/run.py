"""
Entry point for the Solara Price Tracker.

Usage:
    # From repo root (local):
    python -m scrapers.tools.price_tracker.run

    # From price_tracker directory:
    python run.py

    # With a specific date:
    INPUT_REPORT_DATE=2026-03-05 python -m scrapers.tools.price_tracker.run
"""

import logging
import os
import sys
from pathlib import Path

# Allow running from the price_tracker directory directly
_HERE = Path(__file__).resolve().parent
_TOOLS_DIR = _HERE.parent
sys.path.insert(0, str(_TOOLS_DIR))
sys.path.insert(0, str(_HERE))

# Load .env when running locally
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from price_tracker import run

if __name__ == "__main__":
    result = run()
    if result.get("status") not in ("success", "no_products"):
        sys.exit(1)
