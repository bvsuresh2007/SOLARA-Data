const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(`${BASE}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
    });
  }
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

// ---------- Types ----------
export interface Portal   { id: number; name: string; display_name: string; is_active: boolean }
export interface City     { id: number; name: string; state?: string; region?: string }
export interface Product  { id: number; sku_code: string; product_name: string; unit_type?: string }

export interface SalesSummary {
  total_revenue: number;
  total_net_revenue: number;
  total_quantity: number;
  total_orders: number;
  total_discount: number;
  record_count: number;
}

export interface SalesByDimension {
  dimension_id: number;
  dimension_name: string;
  total_revenue: number;
  total_net_revenue: number;
  total_quantity: number;
  total_orders: number;
  record_count: number;
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
  product_id: number;
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

export interface ScrapingLog {
  id: number;
  portal_id?: number;
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
};
