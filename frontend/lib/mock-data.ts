/**
 * Mock data for frontend development when the backend API is unavailable.
 * Mirrors real Pydantic response shapes from the FastAPI backend.
 */
import type {
  Portal, SalesSummary, SalesByDimension, SalesTrend,
  SalesByCategory, TargetAchievement, ScrapingLog,
  PortalDailyResponse, InventoryItem, InventorySummary,
  ActionItemsResponse,
} from "./api";

// ── Portals ──────────────────────────────────────────────
export const MOCK_PORTALS: Portal[] = [
  { id: 1,  name: "swiggy",        display_name: "Swiggy",               is_active: true },
  { id: 2,  name: "blinkit",       display_name: "Blinkit",              is_active: true },
  { id: 3,  name: "amazon",        display_name: "Amazon",               is_active: true },
  { id: 4,  name: "zepto",         display_name: "Zepto",                is_active: true },
  { id: 5,  name: "shopify",       display_name: "Shopify",              is_active: true },
  { id: 6,  name: "myntra",        display_name: "Myntra",               is_active: true },
  { id: 7,  name: "flipkart",      display_name: "Flipkart",             is_active: true },
  { id: 8,  name: "meesho",        display_name: "Meesho",               is_active: true },
  { id: 9,  name: "nykaa_fashion", display_name: "Nykaa Fashion",        is_active: true },
  { id: 10, name: "cred",          display_name: "CRED",                 is_active: true },
  { id: 11, name: "vaaree",        display_name: "Vaaree",               is_active: true },
  { id: 12, name: "offline",       display_name: "Offline",              is_active: true },
];

// ── Sales Summary ────────────────────────────────────────
export const MOCK_SALES_SUMMARY: SalesSummary = {
  total_revenue:     133_12_00_000,   // ₹133.12 Cr
  total_net_revenue: 119_80_00_000,
  total_quantity:    4_85_320,
  total_orders:      2_10_450,
  total_discount:    13_32_00_000,
  record_count:      78_540,
  active_skus:       142,
};

// ── Sales by Portal ──────────────────────────────────────
export const MOCK_SALES_BY_PORTAL: SalesByDimension[] = [
  { dimension_id: 3,  dimension_name: "Amazon",        total_revenue: 61_41_00_000, total_net_revenue: 55_27_00_000, total_quantity: 1_82_400, total_orders: 72_500,  record_count: 24_300 },
  { dimension_id: 5,  dimension_name: "Shopify",       total_revenue: 29_68_00_000, total_net_revenue: 27_71_00_000, total_quantity: 88_200,   total_orders: 41_200,  record_count: 15_600 },
  { dimension_id: 2,  dimension_name: "Blinkit",       total_revenue: 20_10_00_000, total_net_revenue: 18_09_00_000, total_quantity: 72_500,   total_orders: 35_100,  record_count: 12_400 },
  { dimension_id: 1,  dimension_name: "Swiggy",        total_revenue: 9_74_00_000,  total_net_revenue: 8_76_00_000,  total_quantity: 42_800,   total_orders: 21_500,  record_count: 8_200  },
  { dimension_id: 7,  dimension_name: "Flipkart",      total_revenue: 6_64_00_000,  total_net_revenue: 5_97_00_000,  total_quantity: 31_200,   total_orders: 15_800,  record_count: 6_100  },
  { dimension_id: 4,  dimension_name: "Zepto",         total_revenue: 3_92_00_000,  total_net_revenue: 3_53_00_000,  total_quantity: 28_400,   total_orders: 12_200,  record_count: 5_400  },
  { dimension_id: 6,  dimension_name: "Myntra",        total_revenue: 1_44_00_000,  total_net_revenue: 1_30_00_000,  total_quantity: 18_600,   total_orders: 7_800,   record_count: 3_200  },
  { dimension_id: 10, dimension_name: "CRED",          total_revenue: 13_66_000,    total_net_revenue: 12_30_000,    total_quantity: 4_200,    total_orders: 1_800,   record_count: 1_100  },
  { dimension_id: 11, dimension_name: "Vaaree",        total_revenue: 1_83_000,     total_net_revenue: 1_65_000,     total_quantity: 1_200,    total_orders: 520,     record_count: 420    },
  { dimension_id: 12, dimension_name: "Offline",       total_revenue: 1_43_000,     total_net_revenue: 1_29_000,     total_quantity: 980,      total_orders: 410,     record_count: 340    },
  { dimension_id: 9,  dimension_name: "Nykaa Fashion", total_revenue: 98_500,       total_net_revenue: 88_650,       total_quantity: 620,      total_orders: 280,     record_count: 220    },
  { dimension_id: 8,  dimension_name: "Meesho",        total_revenue: 25_500,       total_net_revenue: 22_950,       total_quantity: 220,      total_orders: 90,      record_count: 60     },
];

// ── Sales by Product ─────────────────────────────────────
const productNames = [
  "Solara Stainless Steel Flask 1L",
  "Solara Vacuum Flask 750ml",
  "Solara Copper Bottle 950ml",
  "Solara Glass Water Bottle 500ml",
  "Solara Thermos Tiffin 3-Tier",
  "Solara Insulated Mug 350ml",
  "Solara Kids Bottle 400ml",
  "Solara Sports Sipper 750ml",
  "Solara Tea Infuser Flask 500ml",
  "Solara Travel Tumbler 450ml",
  "Solara Hot & Cold Jug 1.5L",
  "Solara Bamboo Lid Bottle 600ml",
];
export const MOCK_SALES_BY_PRODUCT: SalesByDimension[] = productNames.map((name, i) => ({
  dimension_id: i + 1,
  dimension_name: name,
  sku_code: `SOL-${String(i + 101).padStart(4, "0")}`,
  total_revenue:     Math.round(22_00_00_000 / (i + 1.2)),
  total_net_revenue: Math.round(19_80_00_000 / (i + 1.2)),
  total_quantity:    Math.round(82_000 / (i + 1.2)),
  total_orders:      Math.round(35_000 / (i + 1.2)),
  record_count:      Math.round(12_000 / (i + 1.2)),
}));

// ── Sales Trend (last 30 days) ───────────────────────────
function generateTrend(): SalesTrend[] {
  const days: SalesTrend[] = [];
  const now = new Date();
  for (let i = 29; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const base = 3_50_00_000 + Math.random() * 1_50_00_000;
    const qty  = 12_000 + Math.random() * 6_000;
    days.push({
      date: d.toISOString().slice(0, 10),
      total_revenue: Math.round(base),
      total_quantity: Math.round(qty),
      avg_asp: Math.round(base / qty),
    });
  }
  return days;
}
export const MOCK_SALES_TREND: SalesTrend[] = generateTrend();

// ── Sales by Category ────────────────────────────────────
export const MOCK_SALES_BY_CATEGORY: SalesByCategory[] = [
  { category: "Flasks & Bottles",   total_revenue: 54_20_00_000, total_quantity: 1_92_000, product_count: 18 },
  { category: "Tiffins & Lunch",    total_revenue: 28_40_00_000, total_quantity: 98_000,   product_count: 8  },
  { category: "Mugs & Tumblers",    total_revenue: 22_10_00_000, total_quantity: 84_000,   product_count: 12 },
  { category: "Kitchen Accessories", total_revenue: 15_30_00_000, total_quantity: 62_000,  product_count: 10 },
  { category: "Kids Range",         total_revenue: 13_12_00_000, total_quantity: 49_320,   product_count: 6  },
];

// ── Target Achievement ───────────────────────────────────
export const MOCK_TARGETS: TargetAchievement[] = [
  { portal_name: "Amazon",   target_revenue: 65_00_00_000, actual_revenue: 61_41_00_000, achievement_pct: 94.5, target_units: 1_90_000, actual_units: 1_82_400 },
  { portal_name: "Shopify",  target_revenue: 32_00_00_000, actual_revenue: 29_68_00_000, achievement_pct: 92.8, target_units: 95_000,   actual_units: 88_200   },
  { portal_name: "Blinkit",  target_revenue: 22_00_00_000, actual_revenue: 20_10_00_000, achievement_pct: 91.4, target_units: 80_000,   actual_units: 72_500   },
  { portal_name: "Swiggy",   target_revenue: 12_00_00_000, actual_revenue: 9_74_00_000,  achievement_pct: 81.2, target_units: 50_000,   actual_units: 42_800   },
  { portal_name: "Flipkart", target_revenue: 8_00_00_000,  actual_revenue: 6_64_00_000,  achievement_pct: 83.0, target_units: 38_000,   actual_units: 31_200   },
  { portal_name: "Zepto",    target_revenue: 5_00_00_000,  actual_revenue: 3_92_00_000,  achievement_pct: 78.4, target_units: 35_000,   actual_units: 28_400   },
];

// ── Scraping Logs ────────────────────────────────────────
export const MOCK_SCRAPING_LOGS: ScrapingLog[] = [
  { id: 1, portal_name: "Amazon",  import_date: "2026-02-28", status: "success", records_imported: 1240, start_time: "2026-02-28T02:00:00", end_time: "2026-02-28T02:04:32" },
  { id: 2, portal_name: "Shopify", import_date: "2026-02-28", status: "success", records_imported: 860,  start_time: "2026-02-28T02:05:00", end_time: "2026-02-28T02:06:15" },
  { id: 3, portal_name: "Blinkit", import_date: "2026-02-28", status: "success", records_imported: 620,  start_time: "2026-02-28T02:07:00", end_time: "2026-02-28T02:09:45" },
  { id: 4, portal_name: "Swiggy",  import_date: "2026-02-28", status: "partial", records_imported: 410,  start_time: "2026-02-28T02:10:00", end_time: "2026-02-28T02:12:10", error_message: "3 rows skipped: missing product mapping" },
  { id: 5, portal_name: "Zepto",   import_date: "2026-02-28", status: "success", records_imported: 380,  start_time: "2026-02-28T02:13:00", end_time: "2026-02-28T02:14:50" },
  { id: 6, portal_name: "Flipkart", import_date: "2026-02-27", status: "success", records_imported: 520, start_time: "2026-02-27T02:00:00", end_time: "2026-02-27T02:03:20" },
  { id: 7, portal_name: "Myntra",  import_date: "2026-02-27", status: "failed",  records_imported: 0,    start_time: "2026-02-27T02:04:00", end_time: "2026-02-27T02:04:12", error_message: "Login session expired" },
  { id: 8, portal_name: "Amazon",  import_date: "2026-02-27", status: "success", records_imported: 1180, start_time: "2026-02-27T02:05:00", end_time: "2026-02-27T02:09:10" },
  { id: 9, portal_name: "Shopify", import_date: "2026-02-27", status: "success", records_imported: 830,  start_time: "2026-02-27T02:10:00", end_time: "2026-02-27T02:11:20" },
  { id: 10, portal_name: "Blinkit", import_date: "2026-02-27", status: "success", records_imported: 590, start_time: "2026-02-27T02:12:00", end_time: "2026-02-27T02:14:30" },
];

// ── Portal Daily ─────────────────────────────────────────
export const MOCK_PORTAL_DAILY: PortalDailyResponse = {
  portal_name: "Amazon",
  dates: MOCK_SALES_TREND.slice(-7).map(t => t.date),
  rows: productNames.slice(0, 6).map((name, i) => ({
    sku_code: `SOL-${String(i + 101).padStart(4, "0")}`,
    product_name: name,
    category: MOCK_SALES_BY_CATEGORY[i % MOCK_SALES_BY_CATEGORY.length].category,
    portal_sku: `B0${String(Math.random()).slice(2, 10).toUpperCase()}`,
    bau_asp: 800 + i * 120,
    wh_stock: 500 + Math.round(Math.random() * 300),
    daily_units: Object.fromEntries(
      MOCK_SALES_TREND.slice(-7).map(t => [t.date, Math.round(20 + Math.random() * 40)])
    ),
    mtd_units: 600 + Math.round(Math.random() * 400),
    mtd_value: (600 + Math.round(Math.random() * 400)) * (800 + i * 120),
  })),
};

// ── Inventory ────────────────────────────────────────────
export const MOCK_INVENTORY: InventoryItem[] = [];
export const MOCK_LOW_STOCK: InventorySummary[] = [];

// ── Action Items ─────────────────────────────────────────
export const MOCK_ACTION_ITEMS: ActionItemsResponse = {
  total_products: 48,
  import_health: [],
  portal_coverage: [],
  unmapped_products: [],
  portal_sku_gaps: [],
};
