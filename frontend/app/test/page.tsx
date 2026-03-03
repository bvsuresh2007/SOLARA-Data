"use client";

import { PortalBreakdown } from "@/components/sales/portal-breakdown";
import { PortalDailyTable } from "@/components/sales/portal-daily-table";
import type { SalesByDimension, PortalDailyResponse } from "@/lib/api";

// ── Mock data: portal revenue breakdown ──────────────────────────────────────
const mockPortalData: SalesByDimension[] = [
  { dimension_id: 1, dimension_name: "Amazon",       total_revenue: 58180000, total_quantity: 1064 },
  { dimension_id: 2, dimension_name: "Shopify",      total_revenue: 36170000, total_quantity: 820 },
  { dimension_id: 3, dimension_name: "Blinkit",      total_revenue: 18970000, total_quantity: 540 },
  { dimension_id: 4, dimension_name: "Swiggy",       total_revenue:  9040000, total_quantity: 310 },
  { dimension_id: 5, dimension_name: "Flipkart",     total_revenue:  7290000, total_quantity: 260 },
  { dimension_id: 6, dimension_name: "Zepto",        total_revenue:  3410000, total_quantity: 140 },
  { dimension_id: 7, dimension_name: "Myntra",       total_revenue:  1330000, total_quantity:  90 },
  { dimension_id: 8, dimension_name: "Offline",      total_revenue:   729600, total_quantity:  60 },
  { dimension_id: 9, dimension_name: "CRED",         total_revenue:   225000, total_quantity:  30 },
  { dimension_id:10, dimension_name: "Vaaree",       total_revenue:    36000, total_quantity:  12 },
  { dimension_id:11, dimension_name: "Nykaa Fashion",total_revenue:    10200, total_quantity:   5 },
  { dimension_id:12, dimension_name: "Meesho",       total_revenue:    33000, total_quantity:  18 },
];

// ── Mock data: portal daily table (7-day window) ─────────────────────────────
const dates = ["2026-02-24","2026-02-25","2026-02-26","2026-02-27","2026-02-28","2026-03-01","2026-03-02"];

const mockDailyData: PortalDailyResponse = {
  portal_name: "Amazon",
  dates,
  rows: [
    {
      sku_code: "SOL-CI-DT-101", product_name: "SOL-CI-DT-101", category: "Coolers",
      portal_sku: "B0CLPB7CTY", bau_asp: 1299, wh_stock: null,
      daily_units: { "2026-02-24":157,"2026-02-25":140,"2026-02-26":133,"2026-02-27":144,"2026-02-28":152,"2026-03-01":179,"2026-03-02":159 },
      mtd_units: 1064, mtd_value: 1382136,
    },
    {
      sku_code: "SOL-AF-124", product_name: "SOL-AF-124", category: "Air Fresheners",
      portal_sku: "B0F9FKRVTJ", bau_asp: 3599, wh_stock: null,
      daily_units: { "2026-02-24":105,"2026-02-25":77,"2026-02-26":71,"2026-02-27":83,"2026-02-28":52,"2026-03-01":null,"2026-03-02":38 },
      mtd_units: 426, mtd_value: 1533174,
    },
    {
      sku_code: "SOL-CI-PNY-101", product_name: "SOL-CI-PNY-101", category: "Coolers",
      portal_sku: "B0CLP5XW7L", bau_asp: 1199, wh_stock: null,
      daily_units: { "2026-02-24":63,"2026-02-25":56,"2026-02-26":49,"2026-02-27":46,"2026-02-28":63,"2026-03-01":51,"2026-03-02":32 },
      mtd_units: 360, mtd_value: 431640,
    },
    {
      sku_code: "SOL-AF-501", product_name: "SOL-AF-501", category: "Air Fresheners",
      portal_sku: "B0CZHTGKJN", bau_asp: 7999, wh_stock: null,
      daily_units: { "2026-02-24":35,"2026-02-25":4,"2026-02-26":49,"2026-02-27":54,"2026-02-28":47,"2026-03-01":63,"2026-03-02":31 },
      mtd_units: 283, mtd_value: 2263717,
    },
    {
      sku_code: "SOL-INS-WB-406", product_name: "SOL-INS-WB-406", category: "Water Bottles",
      portal_sku: "B0B2NWGWZH", bau_asp: 999, wh_stock: null,
      daily_units: { "2026-02-24":54,"2026-02-25":44,"2026-02-26":37,"2026-02-27":34,"2026-02-28":50,"2026-03-01":9,"2026-03-02":19 },
      mtd_units: 247, mtd_value: 246753,
    },
    {
      sku_code: "SOL-CI-DT-103", product_name: "SOL-CI-DT-103", category: "Coolers",
      portal_sku: "B0DJGL22KN", bau_asp: 1649, wh_stock: null,
      daily_units: { "2026-02-24":24,"2026-02-25":17,"2026-02-26":42,"2026-02-27":29,"2026-02-28":36,"2026-03-01":34,"2026-03-02":36 },
      mtd_units: 218, mtd_value: 359482,
    },
  ],
};

export default function TestPage() {
  return (
    <main className="min-h-screen bg-zinc-950 p-6 space-y-8">
      <div>
        <h1 className="text-xl font-bold text-zinc-100 mb-1">UI Preview — Test Page</h1>
        <p className="text-xs text-zinc-500">Mock data · not connected to backend</p>
      </div>

      {/* Legend fix preview */}
      <section>
        <p className="text-xs text-zinc-600 uppercase tracking-wider mb-3">Revenue Share Legend (fixed gap + font size)</p>
        <PortalBreakdown data={mockPortalData} />
      </section>

      {/* DRR column preview */}
      <section>
        <p className="text-xs text-zinc-600 uppercase tracking-wider mb-3">Daily Units Table — DRR column (7-day window)</p>
        <PortalDailyTable data={mockDailyData} loading={false} />
      </section>
    </main>
  );
}
