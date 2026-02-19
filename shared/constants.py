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

ALL_PORTALS = [
    PORTAL_SWIGGY,
    PORTAL_BLINKIT,
    PORTAL_AMAZON,
    PORTAL_ZEPTO,
    PORTAL_SHOPIFY,
    PORTAL_MYNTRA,
    PORTAL_FLIPKART,
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
# Major Indian cities (canonical names used in the DB)
# ---------------------------------------------------------------------------
CITIES = [
    # Metro
    "Bangalore", "Mumbai", "Delhi", "Chennai", "Kolkata", "Hyderabad",
    # Tier-1
    "Pune", "Ahmedabad", "Jaipur", "Lucknow", "Surat", "Kochi",
    # Tier-2
    "Indore", "Bhopal", "Nagpur", "Patna", "Bhubaneswar", "Chandigarh",
    "Coimbatore", "Vadodara", "Visakhapatnam", "Agra", "Nashik", "Rajkot",
]

CITY_REGION_MAP: dict[str, str] = {
    "Delhi": REGION_NORTH,
    "Jaipur": REGION_NORTH,
    "Lucknow": REGION_NORTH,
    "Chandigarh": REGION_NORTH,
    "Agra": REGION_NORTH,
    "Mumbai": REGION_WEST,
    "Pune": REGION_WEST,
    "Ahmedabad": REGION_WEST,
    "Surat": REGION_WEST,
    "Vadodara": REGION_WEST,
    "Nashik": REGION_WEST,
    "Rajkot": REGION_WEST,
    "Nagpur": REGION_WEST,
    "Bangalore": REGION_SOUTH,
    "Chennai": REGION_SOUTH,
    "Hyderabad": REGION_SOUTH,
    "Kochi": REGION_SOUTH,
    "Coimbatore": REGION_SOUTH,
    "Visakhapatnam": REGION_SOUTH,
    "Kolkata": REGION_EAST,
    "Patna": REGION_EAST,
    "Bhubaneswar": REGION_EAST,
    "Indore": REGION_WEST,
    "Bhopal": REGION_WEST,
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
