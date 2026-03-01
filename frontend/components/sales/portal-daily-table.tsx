"use client";

import { format, parseISO } from "date-fns";
import { Skeleton } from "@/components/ui/skeleton";
import type { PortalDailyResponse, PortalDailyRow } from "@/lib/api";
import { fmtRevenue } from "@/lib/format";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtDate(iso: string) {
  try { return format(parseISO(iso), "dd-MMM"); } catch { return iso; }
}

function fmtAsp(v: number | null) {
  if (v == null) return "—";
  return `₹${v.toFixed(0)}`;
}

function unitCell(units: number | null | undefined) {
  if (units == null) return { text: "—", cls: "text-zinc-700" };
  if (units === 0)   return { text: "0",  cls: "text-zinc-600" };
  if (units >= 50)   return { text: String(units), cls: "text-green-400 font-semibold" };
  if (units >= 10)   return { text: String(units), cls: "text-zinc-200" };
  return               { text: String(units), cls: "text-zinc-400" };
}

function StockBadge({ v }: { v: number | null }) {
  if (v == null) return <span className="text-zinc-700">—</span>;
  const cls = v === 0 ? "text-red-400 font-bold" : v < 20 ? "text-yellow-400" : "text-green-400";
  return <span className={cls}>{v}</span>;
}

// ─── Sticky column styles ────────────────────────────────────────────────────
// Each frozen column needs an explicit left offset so they stack correctly.
// Widths: # = 36px, SKU = 120px, Product = 220px, Category = 160px,
//         Portal SKU = 120px, BAU ASP = 80px, WH Stock = 80px
// Total frozen width = 816px

const COL = {
  row:       { w: "w-9",          left: "left-0",            minW: 36  },
  sku:       { w: "min-w-[120px]", left: "left-[36px]",      minW: 120 },
  product:   { w: "min-w-[220px]", left: "left-[156px]",     minW: 220 },
  category:  { w: "min-w-[160px]", left: "left-[376px]",     minW: 160 },
  portalSku: { w: "min-w-[120px]", left: "left-[536px]",     minW: 120 },
  asp:       { w: "min-w-[80px]",  left: "left-[656px]",     minW: 80  },
  stock:     { w: "min-w-[80px]",  left: "left-[736px]",     minW: 80  },
};

const FROZEN_TOTAL_W = 816; // sum of all frozen col widths

/** Common classes for every frozen cell */
const stickyTd = "sticky z-10 bg-zinc-900";
const stickyTh = "sticky z-20 bg-zinc-900";
const stickyThGroup = "sticky z-30 bg-zinc-900";
/** Shadow on the last frozen column to visually separate from scrolling area */
const lastFrozenShadow = "shadow-[4px_0_8px_-2px_rgba(0,0,0,0.5)]";

// ─── Component ────────────────────────────────────────────────────────────────

interface Props {
  data: PortalDailyResponse | null;
  loading: boolean;
  portalSelected: boolean;
}

export function PortalDailyTable({ data, loading, portalSelected }: Props) {
  if (!portalSelected) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 px-6 py-10 text-center">
        <p className="text-sm text-zinc-500">
          Select a specific portal above to see the daily units breakdown.
        </p>
      </div>
    );
  }

  if (loading) return <Skeleton className="w-full rounded-xl" style={{ height: 360 }} />;

  if (!data || data.rows.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 px-6 py-10 text-center">
        <p className="text-sm text-zinc-500">No sales data for the selected portal and date range.</p>
      </div>
    );
  }

  const { dates, rows, portal_name } = data;

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
        <div>
          <h2 className="font-semibold text-zinc-100 text-base">Daily Units Breakdown</h2>
          <p className="text-xs text-zinc-500 mt-0.5">
            {portal_name} · {dates[0] ? fmtDate(dates[0]) : "—"} – {dates[dates.length - 1] ? fmtDate(dates[dates.length - 1]) : "—"}
          </p>
        </div>
        <span className="text-xs text-zinc-500">
          <span className="text-zinc-300 font-semibold">{rows.length}</span> products ·{" "}
          <span className="text-zinc-300 font-semibold">{dates.length}</span> days
        </span>
      </div>

      {/* Scrollable table with freeze-panes */}
      <div className="overflow-auto max-h-[70vh]">
        <table className="w-full text-xs whitespace-nowrap border-collapse">
          <thead className="sticky top-0 z-30">
            {/* Group header */}
            <tr className="border-b border-zinc-700/60 bg-zinc-900">
              <th
                colSpan={7}
                className={`py-1.5 px-3 text-left text-[10px] text-zinc-600 uppercase tracking-wider border-r border-zinc-700/60 ${stickyThGroup} ${COL.row.left} ${lastFrozenShadow}`}
                style={{ minWidth: FROZEN_TOTAL_W }}
              >
                Product Info
              </th>
              <th colSpan={dates.length} className="py-1.5 px-3 text-center text-[10px] text-zinc-600 uppercase tracking-wider border-r border-zinc-700/60 bg-zinc-900">
                Daily Units Sold
              </th>
              <th colSpan={2} className="py-1.5 px-3 text-center text-[10px] text-zinc-600 uppercase tracking-wider bg-zinc-900">
                MTD
              </th>
            </tr>

            {/* Column headers */}
            <tr className="border-b border-zinc-800 bg-zinc-900">
              <th className={`py-2 px-2 text-zinc-500 font-medium text-right ${COL.row.w} ${stickyTh} ${COL.row.left}`}>#</th>
              <th className={`py-2 px-3 text-left text-zinc-400 font-medium ${COL.sku.w} ${stickyTh} ${COL.sku.left}`}>SKU</th>
              <th className={`py-2 px-3 text-left text-zinc-400 font-medium ${COL.product.w} ${stickyTh} ${COL.product.left}`}>Product</th>
              <th className={`py-2 px-3 text-left text-zinc-400 font-medium ${COL.category.w} ${stickyTh} ${COL.category.left}`}>Category</th>
              <th className={`py-2 px-3 text-left text-zinc-400 font-medium ${COL.portalSku.w} ${stickyTh} ${COL.portalSku.left}`}>Portal SKU</th>
              <th className={`py-2 px-3 text-right text-zinc-400 font-medium ${COL.asp.w} ${stickyTh} ${COL.asp.left}`}>BAU ASP</th>
              <th className={`py-2 px-3 text-right text-zinc-400 font-medium border-r border-zinc-700/60 ${COL.stock.w} ${stickyTh} ${COL.stock.left} ${lastFrozenShadow}`}>WH Stock</th>
              {dates.map((d) => (
                <th key={d} className="py-2 px-2 text-center text-zinc-400 font-medium min-w-[52px] bg-zinc-900">
                  {fmtDate(d)}
                </th>
              ))}
              <th className="py-2 px-3 text-right text-zinc-400 font-medium border-l border-zinc-700/60 bg-zinc-900">Units</th>
              <th className="py-2 px-3 text-right text-zinc-400 font-medium bg-zinc-900">Value</th>
            </tr>
          </thead>

          <tbody className="divide-y divide-zinc-800/50">
            {rows.map((row: PortalDailyRow, i: number) => (
              <tr key={row.sku_code} className="hover:bg-zinc-800/30 transition-colors group">
                <td className={`py-1.5 px-2 text-zinc-600 text-right ${COL.row.w} ${stickyTd} ${COL.row.left}`}>{i + 1}</td>
                <td className={`py-1.5 px-3 font-mono text-zinc-400 ${COL.sku.w} ${stickyTd} ${COL.sku.left}`}>{row.sku_code}</td>
                <td className={`py-1.5 px-3 text-zinc-200 ${COL.product.w} ${stickyTd} ${COL.product.left}`}>
                  <span className="line-clamp-1" title={row.product_name}>{row.product_name}</span>
                </td>
                <td className={`py-1.5 px-3 text-zinc-500 ${COL.category.w} ${stickyTd} ${COL.category.left}`}>{row.category}</td>
                <td className={`py-1.5 px-3 font-mono text-zinc-600 text-[11px] ${COL.portalSku.w} ${stickyTd} ${COL.portalSku.left}`}>{row.portal_sku}</td>
                <td className={`py-1.5 px-3 text-right text-zinc-300 font-mono ${COL.asp.w} ${stickyTd} ${COL.asp.left}`}>{fmtAsp(row.bau_asp)}</td>
                <td className={`py-1.5 px-3 text-right border-r border-zinc-700/60 ${COL.stock.w} ${stickyTd} ${COL.stock.left} ${lastFrozenShadow}`}>
                  <StockBadge v={row.wh_stock} />
                </td>
                {dates.map((d) => {
                  const { text, cls } = unitCell(row.daily_units[d]);
                  return (
                    <td key={d} className={`py-1.5 px-2 text-center tabular-nums ${cls}`}>
                      {text}
                    </td>
                  );
                })}
                <td className="py-1.5 px-3 text-right font-semibold text-zinc-100 border-l border-zinc-700/60 tabular-nums">
                  {row.mtd_units.toLocaleString("en-IN")}
                </td>
                <td className="py-1.5 px-3 text-right text-orange-400 font-semibold font-mono tabular-nums">
                  {fmtRevenue(row.mtd_value)}
                </td>
              </tr>
            ))}
          </tbody>

          {/* Totals footer */}
          <tfoot className="sticky bottom-0 z-20 border-t border-zinc-700 bg-zinc-800">
            <tr>
              <td
                colSpan={7}
                className={`py-2 px-3 text-zinc-400 font-semibold text-right border-r border-zinc-700/60 text-[11px] uppercase tracking-wider sticky ${COL.row.left} z-20 bg-zinc-800 ${lastFrozenShadow}`}
                style={{ minWidth: FROZEN_TOTAL_W }}
              >
                Total
              </td>
              {dates.map((d) => {
                const total = rows.reduce((s, r) => s + (r.daily_units[d] ?? 0), 0);
                const { cls } = unitCell(total || null);
                return (
                  <td key={d} className={`py-2 px-2 text-center font-semibold tabular-nums ${cls}`}>
                    {total > 0 ? total : "—"}
                  </td>
                );
              })}
              <td className="py-2 px-3 text-right font-bold text-zinc-50 border-l border-zinc-700/60 tabular-nums">
                {rows.reduce((s, r) => s + r.mtd_units, 0).toLocaleString("en-IN")}
              </td>
              <td className="py-2 px-3 text-right font-bold text-orange-400 font-mono tabular-nums">
                {fmtRevenue(rows.reduce((s, r) => s + r.mtd_value, 0))}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
