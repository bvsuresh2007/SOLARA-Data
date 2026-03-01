import {
  MOCK_PORTALS, MOCK_SALES_SUMMARY, MOCK_SALES_BY_PORTAL,
  MOCK_SALES_BY_PRODUCT, MOCK_SALES_TREND, MOCK_SALES_BY_CATEGORY,
  MOCK_TARGETS, MOCK_SCRAPING_LOGS, MOCK_PORTAL_DAILY,
  MOCK_INVENTORY, MOCK_LOW_STOCK, MOCK_ACTION_ITEMS,
} from "./mock-data";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Map of API paths to mock fallback data */
const MOCK_MAP: Record<string, unknown> = {
  "/api/metadata/portals":      MOCK_PORTALS,
  "/api/metadata/scraping-logs": MOCK_SCRAPING_LOGS,
  "/api/sales/summary":         MOCK_SALES_SUMMARY,
  "/api/sales/by-portal":       MOCK_SALES_BY_PORTAL,
  "/api/sales/by-city":         MOCK_SALES_BY_PORTAL,
  "/api/sales/by-product":      MOCK_SALES_BY_PRODUCT,
  "/api/sales/trend":           MOCK_SALES_TREND,
  "/api/sales/by-category":     MOCK_SALES_BY_CATEGORY,
  "/api/sales/targets":         MOCK_TARGETS,
  "/api/sales/portal-daily":    MOCK_PORTAL_DAILY,
  "/api/sales/products":        [],
  "/api/metadata/cities":       [],
  "/api/inventory/current":     MOCK_INVENTORY,
  "/api/inventory/low-stock":   MOCK_LOW_STOCK,
  "/api/metadata/action-items": MOCK_ACTION_ITEMS,
};

async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(`${BASE}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
    });
  }
  try {
    const res = await fetch(url.toString(), { cache: "no-store" });
    if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
    return res.json();
  } catch {
    // Backend unreachable — return mock data
    if (path in MOCK_MAP) return MOCK_MAP[path] as T;
    throw new Error(`API unreachable and no mock data for: ${path}`);
  }
}

// ---------- Types ----------
export interface Portal   { id: number; name: string; display_name: string; is_active: boolean }
export interface City     { id: number; name: string; state?: string; region?: string }
export interface Product  { id: number; sku_code: string; product_name: string; unit_type?: string }

export interface SalesSummary {
  total_revenue: number;
  total_net_revenue: number | null;
  total_quantity: number;
  total_orders: number | null;
  total_discount: number | null;
  record_count: number;
  active_skus: number;
}

export interface SalesByDimension {
  dimension_id: number;
  dimension_name: string;
  sku_code?: string | null;
  total_revenue: number;
  total_net_revenue: number | null;
  total_quantity: number;
  total_orders: number | null;
  record_count: number | null;
}

export interface SalesTrend {
  date: string;
  total_revenue: number;
  total_quantity: number;
  avg_asp: number;
}

export interface SalesByCategory {
  category: string;
  total_revenue: number;
  total_quantity: number;
  product_count: number;
}

export interface TargetAchievement {
  portal_name: string;
  target_revenue: number;
  actual_revenue: number;
  achievement_pct: number;
  target_units: number;
  actual_units: number;
}

export interface InventoryItem {
  id: number;
  portal_id: number;
  portal_name: string | null;
  product_id: number;
  product_name: string | null;
  snapshot_date: string;
  portal_stock: string | null;
  backend_stock: string | null;
  frontend_stock: string | null;
  solara_stock: string | null;
  open_po: string | null;
  doc: string | null;
  imported_at: string;
}

export interface InventorySummary {
  product_id: number;
  product_name: string;
  sku_code: string;
  total_portal_stock: string;
  portal_count: number;
}

export interface PortalDailyRow {
  sku_code: string;
  product_name: string;
  category: string;
  portal_sku: string;
  bau_asp: number | null;
  wh_stock: number | null;
  daily_units: Record<string, number | null>;
  mtd_units: number;
  mtd_value: number;
}

export interface PortalDailyResponse {
  portal_name: string;
  dates: string[];
  rows: PortalDailyRow[];
}

export interface PortalImportHealth {
  portal_name: string;
  display_name: string;
  last_import_at: string | null;
  last_status: string | null;
  total_imports: number;
  failed_runs: number;
}
export interface PortalCoverage {
  portal_name: string;
  display_name: string;
  mapped_products: number;
  total_products: number;
  gap: number;
}
export interface UnmappedProduct {
  product_id: number;
  sku_code: string;
  product_name: string;
  missing_portals: string;
  missing_portal_slugs: string;
  missing_count: number;
}
export interface PortalSkuGap {
  portal: string;
  portal_sku: string;
  portal_name: string;
  matched_sol_sku: string;
  matched_name: string;
  score: number;
  status: string;
}
export interface ActionItemsResponse {
  total_products: number;
  import_health: PortalImportHealth[];
  portal_coverage: PortalCoverage[];
  unmapped_products: UnmappedProduct[];
  portal_sku_gaps: PortalSkuGap[];
}
export interface ImportFailure {
  id: number;
  portal_name: string | null;
  display_name: string | null;
  file_name: string | null;
  import_date: string;
  start_time: string;
  error_message: string | null;
  source_type: string;
}

export interface AMAResponse {
  answer: string;
  sql?: string | null;
  error?: string | null;
}

export interface ScrapingLog {
  id: number;
  portal_id?: number;
  portal_name?: string;
  sheet_name?: string;
  file_name?: string;
  import_date: string;
  status: string;
  records_imported: number | null;
  error_message?: string;
  start_time: string;
  end_time?: string;
}

// ---------- API calls ----------
export const api = {
  portals:       ()                                    => get<Portal[]>("/api/metadata/portals"),
  cities:        ()                                    => get<City[]>("/api/metadata/cities"),
  products:      ()                                    => get<Product[]>("/api/sales/products"),
  scrapingLogs:  (limit = 20)                          => get<ScrapingLog[]>("/api/metadata/scraping-logs", { limit }),

  salesSummary: (params?: Record<string, string | number | undefined>) =>
    get<SalesSummary>("/api/sales/summary", params),

  salesByPortal:  (params?: Record<string, string | number | undefined>) => get<SalesByDimension[]>("/api/sales/by-portal",  params),
  salesByCity:    (params?: Record<string, string | number | undefined>) => get<SalesByDimension[]>("/api/sales/by-city",    params),
  salesByProduct: (params?: Record<string, string | number | undefined>) => get<SalesByDimension[]>("/api/sales/by-product", params),

  salesTrend: (params?: Record<string, string | number | undefined>) =>
    get<SalesTrend[]>("/api/sales/trend", params),

  salesByCategory: (params?: Record<string, string | number | undefined>) =>
    get<SalesByCategory[]>("/api/sales/by-category", params),

  salesTargets: (params?: Record<string, string | number | undefined>) =>
    get<TargetAchievement[]>("/api/sales/targets", params),

  currentInventory: (params?: Record<string, string | number>) =>
    get<InventoryItem[]>("/api/inventory/current", params),

  lowStock: (threshold = 100) =>
    get<InventorySummary[]>("/api/inventory/low-stock", { threshold }),

  portalDaily: (params: { portal?: string; start_date?: string; end_date?: string }) =>
    get<PortalDailyResponse>("/api/sales/portal-daily", params),

  actionItems: () => get<ActionItemsResponse>("/api/metadata/action-items"),
};
