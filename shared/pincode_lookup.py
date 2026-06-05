"""
Pincode → City / State / Region lookup for India.

Uses the pincode master CSV (data/pincode_master.csv) which maps ~24K Indian
pincodes to city, district, and state.  We apply canonical normalisation so
that city/state names match what the rest of the codebase expects (e.g.
"Bangalore" → "Bengaluru", "Orissa" → "Odisha").

Usage:
    from shared.pincode_lookup import pincode_lookup
    city, state, region = pincode_lookup("500001")
    # → ("Hyderabad", "Telangana", "South")
"""

from __future__ import annotations

import csv
import logging
from functools import lru_cache
from pathlib import Path

from shared.constants import CITY_NAME_MAP, CITY_REGION_MAP

logger = logging.getLogger(__name__)

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "pincode_master.csv"

# ── State name normalisation ───────────────────────────────────────────────
# Maps raw state names in the CSV to the canonical names used in the dashboard.
STATE_NAME_MAP: dict[str, str] = {
    # Old / alternate names
    "Orissa":                    "Odisha",
    "Uttaranchal":               "Uttarakhand",
    "Pondicherry":               "Puducherry",
    "Lakshdweep":                "Lakshadweep",
    "Andaman Nicobar":           "Andaman & Nicobar Islands",
    "Dadra & Nagar Haveli":      "Dadra & Nagar Haveli and Daman & Diu",
    "Daman & Diu":               "Dadra & Nagar Haveli and Daman & Diu",
    # Telangana split — pincodes starting with 50x are Telangana
    # (handled specially below, not via this map)
}

# City names in the pincode CSV that need normalisation to match our DB.
# Extends CITY_NAME_MAP from constants.py with extra entries seen in pincode data.
PINCODE_CITY_NAME_MAP: dict[str, str] = {
    **{k: v for k, v in CITY_NAME_MAP.items()},
    # Additional pincode-dataset-specific fixes
    "Bangalore":              "Bengaluru",
    "Bangalore Rural":        "Bengaluru",
    "Bangalore Urban":        "Bengaluru",
    "Gurgaon":                "Gurugram",
    "New Delhi":              "Delhi",
    "Central Delhi":          "Delhi",
    "East Delhi":             "Delhi",
    "New Delhi":              "Delhi",
    "North Delhi":            "Delhi",
    "North East Delhi":       "Delhi",
    "North West Delhi":       "Delhi",
    "Shahdara":               "Delhi",
    "South Delhi":            "Delhi",
    "South East Delhi":       "Delhi",
    "South West Delhi":       "Delhi",
    "West Delhi":             "Delhi",
    "Bombay":                 "Mumbai",
    "Mumbai Suburban":        "Mumbai",
    "Thane":                  "Mumbai",
    "Raigad":                 "Mumbai",
    "Palghar":                "Mumbai",
    "Calcutta":               "Kolkata",
    "Madras":                 "Chennai",
    "Kancheepuram":           "Chennai",
    "Chengalpattu":           "Chennai",
    "Tiruvallur":             "Chennai",
    "Rangareddy":             "Hyderabad",
    "Ranga Reddy":            "Hyderabad",
    "Medchal Malkajgiri":     "Hyderabad",
    "Medchal-Malkajgiri":     "Hyderabad",
    "Sangareddy":             "Hyderabad",
    "Baroda":                 "Vadodara",
    "Belgaum":                "Belagavi",
    "Mysore":                 "Mysuru",
    "Mangalore":              "Mangaluru",
    "Hubli":                  "Hubballi",
    "Shimoga":                "Shivamogga",
    "Tumkur":                 "Tumkuru",
    "Aurangabad":             "Chhatrapati Sambhajinagar",
    "Trivandrum":             "Thiruvananthapuram",
    "Allahabad":              "Prayagraj",
    "Benaras":                "Varanasi",
    "Ghaziabad":              "Ghaziabad",
    "Gautam Buddha Nagar":    "Noida",
    "G.B. Nagar":             "Noida",
    "Ernakulam":              "Kochi",
    "Pune":                   "Pune",
    "Khordha":                "Bhubaneswar",
}

# Telangana pincodes: 500xxx-509xxx are Telangana (not Andhra Pradesh)
_TELANGANA_PIN_PREFIXES = {"500", "501", "502", "503", "504", "505", "506", "507", "508", "509"}

# ── State → Region mapping ────────────────────────────────────────────────
STATE_REGION_MAP: dict[str, str] = {
    "Andhra Pradesh":                          "South",
    "Arunachal Pradesh":                       "East",
    "Assam":                                   "East",
    "Bihar":                                   "East",
    "Chhattisgarh":                            "East",
    "Goa":                                     "West",
    "Gujarat":                                 "West",
    "Haryana":                                 "North",
    "Himachal Pradesh":                        "North",
    "Jharkhand":                               "East",
    "Karnataka":                               "South",
    "Kerala":                                  "South",
    "Madhya Pradesh":                          "West",
    "Maharashtra":                             "West",
    "Manipur":                                 "East",
    "Meghalaya":                               "East",
    "Mizoram":                                 "East",
    "Nagaland":                                "East",
    "Odisha":                                  "East",
    "Punjab":                                  "North",
    "Rajasthan":                               "North",
    "Sikkim":                                  "East",
    "Tamil Nadu":                              "South",
    "Telangana":                               "South",
    "Tripura":                                 "East",
    "Uttar Pradesh":                           "North",
    "Uttarakhand":                             "North",
    "West Bengal":                             "East",
    "Delhi":                                   "North",
    "Chandigarh":                              "North",
    "Puducherry":                              "South",
    "Jammu & Kashmir":                         "North",
    "Ladakh":                                  "North",
    "Lakshadweep":                             "South",
    "Andaman & Nicobar Islands":               "South",
    "Dadra & Nagar Haveli and Daman & Diu":    "West",
}


def _normalise_city(raw: str) -> str:
    """Normalise city/district name to canonical form."""
    name = raw.strip().title()
    return PINCODE_CITY_NAME_MAP.get(name, CITY_NAME_MAP.get(name, name))


def _normalise_state(raw: str, pincode: str = "") -> str:
    """Normalise state name. Handles Telangana split via pincode prefix."""
    name = raw.strip()
    # Telangana fix: pincode CSV lists Hyderabad as Andhra Pradesh
    if name == "Andhra Pradesh" and pincode[:3] in _TELANGANA_PIN_PREFIXES:
        return "Telangana"
    return STATE_NAME_MAP.get(name, name)


@lru_cache(maxsize=1)
def _load_pincode_db() -> dict[str, tuple[str, str, str]]:
    """
    Load pincode CSV into a dict: pincode → (city, state, region).
    Uses the first occurrence per pincode (usually the main city).
    """
    if not _DATA_FILE.exists():
        logger.warning("Pincode master file not found: %s", _DATA_FILE)
        return {}

    db: dict[str, tuple[str, str, str]] = {}
    with open(_DATA_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pin = row.get("Pincode", "").strip()
            if not pin or len(pin) != 6:
                continue
            if pin in db:
                continue  # keep first occurrence

            raw_city = row.get("City", "") or row.get("DistrictsName", "")
            raw_state = row.get("State", "")

            state = _normalise_state(raw_state, pin)
            city = _normalise_city(raw_city)
            region = STATE_REGION_MAP.get(state, "")

            # Also try to resolve city via CITY_REGION_MAP for better region
            if city in CITY_REGION_MAP:
                region = CITY_REGION_MAP[city]

            db[pin] = (city, state, region)

    logger.info("Loaded %d pincodes from %s", len(db), _DATA_FILE.name)
    return db


def pincode_lookup(pincode: str | None) -> tuple[str | None, str | None, str | None]:
    """
    Look up a pincode and return (city, state, region).
    Returns (None, None, None) if pincode is invalid or not found.
    """
    if not pincode:
        return None, None, None

    pin = str(pincode).strip().replace(" ", "")

    # Handle pincodes with country prefix or extra chars
    if len(pin) > 6:
        pin = pin[-6:]

    if len(pin) != 6 or not pin.isdigit():
        return None, None, None

    db = _load_pincode_db()
    result = db.get(pin)
    if result:
        return result
    return None, None, None


def normalise_city_name(raw: str) -> str:
    """Public helper: normalise a city name (for use outside pincode context)."""
    return _normalise_city(raw)


def normalise_state_name(raw: str) -> str:
    """Public helper: normalise a state name."""
    return STATE_NAME_MAP.get(raw.strip(), raw.strip())
