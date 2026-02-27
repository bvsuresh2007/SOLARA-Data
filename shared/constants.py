"""
Shared constants for SolaraDashboard.
Used by both the scraper service and the backend API.
"""

# ---------------------------------------------------------------------------
# Portal names (must match `portals.name` in DB)
# ---------------------------------------------------------------------------
PORTAL_SWIGGY   = "swiggy"
PORTAL_BLINKIT  = "blinkit"
PORTAL_AMAZON   = "amazon"
PORTAL_ZEPTO    = "zepto"
PORTAL_SHOPIFY  = "shopify"
PORTAL_MYNTRA   = "myntra"
PORTAL_FLIPKART = "flipkart"
PORTAL_EASYECOM = "easyecom"

ALL_PORTALS = [
    PORTAL_SWIGGY,
    PORTAL_BLINKIT,
    PORTAL_AMAZON,
    PORTAL_ZEPTO,
    PORTAL_SHOPIFY,
    PORTAL_MYNTRA,
    PORTAL_FLIPKART,
    PORTAL_EASYECOM,
]

# ---------------------------------------------------------------------------
# Geographic regions
# ---------------------------------------------------------------------------
REGION_NORTH = "North"
REGION_SOUTH = "South"
REGION_EAST  = "East"
REGION_WEST  = "West"

ALL_REGIONS = [REGION_NORTH, REGION_SOUTH, REGION_EAST, REGION_WEST]

# ---------------------------------------------------------------------------
# City name normalisation map
# Any portal may use variant spellings or old names. This map converts them
# to the canonical name stored in the DB.
# Key   = variant as seen in portal data (case-sensitive after strip)
# Value = canonical name in the cities table
# ---------------------------------------------------------------------------
CITY_NAME_MAP: dict[str, str] = {
    # ── Spelling fixes seen in Zepto data ───────────────────────────────────
    "Devangere":                    "Davanagere",
    "Davangere":                    "Davanagere",
    "HAPUR":                        "Hapur",
    "Roorke":                       "Roorkee",
    "Vadodra":                      "Vadodara",
    "Belgavi":                      "Belagavi",
    "Chatrapati Sambhaji Nagar":    "Chhatrapati Sambhajinagar",
    "Chhatrapati Sambhaji Nagar":   "Chhatrapati Sambhajinagar",
    "Karnal\n":                     "Karnal",
    "Anand\n":                      "Anand",
    "Mathura\n":                    "Mathura",
    "Mehsana\n":                    "Mehsana",
    "Salem\n":                      "Salem",
    "Udaipur\n":                    "Udaipur",

    # ── City code abbreviations ───────────────────────────────────────────
    "BLR":                          "Bengaluru",
    "blr":                          "Bengaluru",
    "NCR":                          "Delhi",
    "ncr":                          "Delhi",
    "HYD":                          "Hyderabad",
    "hyd":                          "Hyderabad",
    "AMD":                          "Ahmedabad",
    "amd":                          "Ahmedabad",

    # ── Common alternate / old names (future portals) ────────────────────
    "Bangalore":                    "Bengaluru",
    "Bangaluru":                    "Bengaluru",
    "Gurgaon":                      "Gurugram",
    "Bombay":                       "Mumbai",
    "Madras":                       "Chennai",
    "Calcutta":                     "Kolkata",
    "Baroda":                       "Vadodara",
    "Belgaum":                      "Belagavi",
    "Aurangabad":                   "Chhatrapati Sambhajinagar",
    "Mohali":                       "SAS Nagar",
    "Pondicherry":                  "Puducherry",
    "Vizag":                        "Visakhapatnam",
    "Trivandrum":                   "Thiruvananthapuram",
    "Mangalore":                    "Mangaluru",
    "Mysore":                       "Mysuru",
    "Hubli":                        "Hubballi",
    "Hubli-Dharwad":                "Hubballi",
    "New Delhi":                    "Delhi",
    "Greater Noida":                "Noida",
    "Trichi":                       "Tiruchirappalli",
    "Trichy":                       "Tiruchirappalli",
    "Cochin":                       "Kochi",
    "Allahabad":                    "Prayagraj",
    "Secunderabad":                 "Hyderabad",
}


def normalise_city(name: str | None) -> str | None:
    """Return the canonical city name for any portal variant. Returns None for empty input."""
    if not name:
        return None
    cleaned = name.strip().strip("\n").strip()
    if not cleaned:
        return None
    return CITY_NAME_MAP.get(cleaned, cleaned)


# ---------------------------------------------------------------------------
# Canonical city list (matches what is / will be in the cities table)
# ---------------------------------------------------------------------------
CITIES = [
    # ── North ────────────────────────────────────────────────────────────
    "Delhi", "Noida", "Ghaziabad", "Faridabad", "Gurugram",
    "Agra", "Mathura", "Meerut", "Bareilly", "Kanpur", "Lucknow",
    "Varanasi", "Prayagraj", "Gorakhpur", "Saharanpur", "Hapur",
    "Jaipur", "Kota", "Alwar", "Udaipur", "Neemrana", "Bhiwadi",
    "Amritsar", "Ludhiana", "Jalandhar", "Patiala", "SAS Nagar",
    "Chandigarh", "Panchkula",
    "Ambala", "Panipat", "Sonipat", "Hisar", "Karnal", "Kurukshetra", "Rewari",
    "Dehradun", "Haridwar", "Roorkee",
    # ── South ────────────────────────────────────────────────────────────
    "Bengaluru", "Mysuru", "Hubballi", "Davanagere", "Belagavi",
    "Hosur", "Tumkuru",
    "Chennai", "Coimbatore", "Madurai", "Salem", "Tiruchirappalli",
    "Vellore", "Puducherry",
    "Hyderabad", "Warangal", "Karimnagar",
    "Vijayawada", "Guntur",
    "Kochi", "Thrissur", "Palakkad",
    # ── West ─────────────────────────────────────────────────────────────
    "Mumbai", "Pune", "Nagpur", "Nashik", "Chhatrapati Sambhajinagar",
    "Ahmedabad", "Surat", "Vadodara", "Rajkot", "Anand", "Mehsana", "Valsad",
    "Indore",
    # ── East ─────────────────────────────────────────────────────────────
    "Kolkata",
]

CITY_REGION_MAP: dict[str, str] = {
    # North
    "Delhi":                      REGION_NORTH,
    "Noida":                      REGION_NORTH,
    "Ghaziabad":                  REGION_NORTH,
    "Faridabad":                  REGION_NORTH,
    "Gurugram":                   REGION_NORTH,
    "Agra":                       REGION_NORTH,
    "Mathura":                    REGION_NORTH,
    "Meerut":                     REGION_NORTH,
    "Bareilly":                   REGION_NORTH,
    "Kanpur":                     REGION_NORTH,
    "Lucknow":                    REGION_NORTH,
    "Varanasi":                   REGION_NORTH,
    "Prayagraj":                  REGION_NORTH,
    "Gorakhpur":                  REGION_NORTH,
    "Saharanpur":                 REGION_NORTH,
    "Hapur":                      REGION_NORTH,
    "Jaipur":                     REGION_NORTH,
    "Kota":                       REGION_NORTH,
    "Alwar":                      REGION_NORTH,
    "Udaipur":                    REGION_NORTH,
    "Neemrana":                   REGION_NORTH,
    "Bhiwadi":                    REGION_NORTH,
    "Amritsar":                   REGION_NORTH,
    "Ludhiana":                   REGION_NORTH,
    "Jalandhar":                  REGION_NORTH,
    "Patiala":                    REGION_NORTH,
    "SAS Nagar":                  REGION_NORTH,
    "Chandigarh":                 REGION_NORTH,
    "Panchkula":                  REGION_NORTH,
    "Ambala":                     REGION_NORTH,
    "Panipat":                    REGION_NORTH,
    "Sonipat":                    REGION_NORTH,
    "Hisar":                      REGION_NORTH,
    "Karnal":                     REGION_NORTH,
    "Kurukshetra":                REGION_NORTH,
    "Rewari":                     REGION_NORTH,
    "Dehradun":                   REGION_NORTH,
    "Haridwar":                   REGION_NORTH,
    "Roorkee":                    REGION_NORTH,
    # South
    "Bengaluru":                  REGION_SOUTH,
    "Mysuru":                     REGION_SOUTH,
    "Hubballi":                   REGION_SOUTH,
    "Davanagere":                 REGION_SOUTH,
    "Belagavi":                   REGION_SOUTH,
    "Hosur":                      REGION_SOUTH,
    "Tumkuru":                    REGION_SOUTH,
    "Chennai":                    REGION_SOUTH,
    "Coimbatore":                 REGION_SOUTH,
    "Madurai":                    REGION_SOUTH,
    "Salem":                      REGION_SOUTH,
    "Tiruchirappalli":            REGION_SOUTH,
    "Vellore":                    REGION_SOUTH,
    "Puducherry":                 REGION_SOUTH,
    "Hyderabad":                  REGION_SOUTH,
    "Warangal":                   REGION_SOUTH,
    "Karimnagar":                 REGION_SOUTH,
    "Vijayawada":                 REGION_SOUTH,
    "Guntur":                     REGION_SOUTH,
    "Kochi":                      REGION_SOUTH,
    "Thrissur":                   REGION_SOUTH,
    "Palakkad":                   REGION_SOUTH,
    # West
    "Mumbai":                     REGION_WEST,
    "Pune":                       REGION_WEST,
    "Nagpur":                     REGION_WEST,
    "Nashik":                     REGION_WEST,
    "Chhatrapati Sambhajinagar":  REGION_WEST,
    "Ahmedabad":                  REGION_WEST,
    "Surat":                      REGION_WEST,
    "Vadodara":                   REGION_WEST,
    "Rajkot":                     REGION_WEST,
    "Anand":                      REGION_WEST,
    "Mehsana":                    REGION_WEST,
    "Valsad":                     REGION_WEST,
    "Indore":                     REGION_WEST,
    # East
    "Kolkata":                    REGION_EAST,
}

# ---------------------------------------------------------------------------
# Scraping job statuses
# ---------------------------------------------------------------------------
STATUS_RUNNING  = "running"
STATUS_SUCCESS  = "success"
STATUS_FAILED   = "failed"
STATUS_PARTIAL  = "partial"

# ---------------------------------------------------------------------------
# Low stock threshold (units)
# ---------------------------------------------------------------------------
LOW_STOCK_THRESHOLD = 100

# ---------------------------------------------------------------------------
# Amazon marketplace codes (used by amazon_asin_scraper tool)
# ---------------------------------------------------------------------------
AMAZON_MARKETPLACE_INDIA = "in"
AMAZON_MARKETPLACE_US    = "com"
AMAZON_MARKETPLACE_UK    = "co.uk"
AMAZON_MARKETPLACE_DE    = "de"
AMAZON_MARKETPLACE_JP    = "co.jp"
