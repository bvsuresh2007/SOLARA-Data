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

// ─── Frozen column config ───────────────────────────────────────────────────
// Only freeze 3 columns: #, SKU, Product — keeps it lightweight
// Widths: # = 36px, SKU = 110px, Product = 200px  → total = 346px

const freeze = {
  row:     { w: 36,  left: 0   },
  sku:     { w: 110, left: 36  },
  product: { w: 200, left: 146 },
} as const;

const FREEZE_END = 346; // last frozen col right edge

// z-layers: frozen-body=10, frozen-header=30, header-scrollable=20, footer=25, frozen-footer=35
const Z = { body: 10, header: 20, frozenHeader: 30, footer: 25, frozenFooter: 35 } as const;

/** Inline style for a frozen cell */
function frozenStyle(col: { w: number; left: number }) {
  return { position: "sticky" as const, left: col.left, minWidth: col.w, width: col.w };
}

// ─── Component ────────────────────────────────────────────────────────────────

interface Props {
  data: PortalDailyResponse | null;
  loading: boolean;
  portalSelected?: boolean; // kept for backwards compat, but no longer used
}

export function PortalDailyTable({ data, loading }: Props) {
  if (loading) return <Skeleton className="w-full rounded-xl" style={{ height: 360 }} />;

  if (!data || data.rows.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 px-6 py-10 text-center">
        <p className="text-sm text-zinc-500">No sales data for the selected portal and date range.</p>
      </div>
    );
  }

  const { dates, rows, portal_name } = data;

  // Shadow applied via box-shadow on the last frozen column
  const edgeShadow = "4px 0 6px -2px rgba(0,0,0,0.45)";

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden">
      {/* Card header */}
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

      {/* Scrollable container */}
      <div className="overflow-auto max-h-[70vh]">
        <table className="w-full text-xs whitespace-nowrap border-collapse">

          {/* ── HEADER ────────────────────────────────────────── */}
          <thead>
            {/* Group header row */}
            <tr className="border-b border-zinc-700/60">
              {/* Frozen: Product Info group spanning 3 frozen cols */}
              <th
                colSpan={3}
                className="py-1.5 px-3 text-left text-[10px] text-zinc-600 uppercase tracking-wider border-r border-zinc-700/60 bg-zinc-900"
                style={{ position: "sticky", top: 0, left: 0, zIndex: Z.frozenHeader, minWidth: FREEZE_END, boxShadow: edgeShadow }}
              >
                Product Info
              </th>
              {/* Non-frozen scrollable info cols */}
              <th
                colSpan={4}
                className="py-1.5 px-3 text-center text-[10px] text-zinc-600 uppercase tracking-wider border-r border-zinc-700/60 bg-zinc-900"
                style={{ position: "sticky", top: 0, zIndex: Z.header }}
              >
                Details
              </th>
              {/* Daily Units group */}
              <th
                colSpan={dates.length}
                className="py-1.5 px-3 text-center text-[10px] text-zinc-600 uppercase tracking-wider border-r border-zinc-700/60 bg-zinc-900"
                style={{ position: "sticky", top: 0, zIndex: Z.header }}
              >
                Daily Units Sold
              </th>
              {/* MTD group */}
              <th
                colSpan={2}
                className="py-1.5 px-3 text-center text-[10px] text-zinc-600 uppercase tracking-wider bg-zinc-900"
                style={{ position: "sticky", top: 0, zIndex: Z.header }}
              >
                MTD
              </th>
            </tr>

            {/* Column header row */}
            <tr className="border-b border-zinc-800">
              {/* ── Frozen columns ── */}
              <th
                className="py-2 px-2 text-zinc-500 font-medium text-right bg-zinc-900"
                style={{ ...frozenStyle(freeze.row), position: "sticky", top: 28, left: freeze.row.left, zIndex: Z.frozenHeader }}
              >
                #
              </th>
              <th
                className="py-2 px-3 text-left text-zinc-400 font-medium bg-zinc-900"
                style={{ ...frozenStyle(freeze.sku), position: "sticky", top: 28, left: freeze.sku.left, zIndex: Z.frozenHeader }}
              >
                SKU
              </th>
              <th
                className="py-2 px-3 text-left text-zinc-400 font-medium border-r border-zinc-700/60 bg-zinc-900"
                style={{ ...frozenStyle(freeze.product), position: "sticky", top: 28, left: freeze.product.left, zIndex: Z.frozenHeader, boxShadow: edgeShadow }}
              >
                Product
              </th>
              {/* ── Scrollable info columns ── */}
              <th className="py-2 px-3 text-left text-zinc-400 font-medium min-w-[140px] bg-zinc-900" style={{ position: "sticky", top: 28, zIndex: Z.header }}>
                Category
              </th>
              <th className="py-2 px-3 text-left text-zinc-400 font-medium min-w-[110px] bg-zinc-900" style={{ position: "sticky", top: 28, zIndex: Z.header }}>
                Portal SKU
              </th>
              <th className="py-2 px-3 text-right text-zinc-400 font-medium min-w-[72px] bg-zinc-900" style={{ position: "sticky", top: 28, zIndex: Z.header }}>
                BAU ASP
              </th>
              <th className="py-2 px-3 text-right text-zinc-400 font-medium min-w-[72px] border-r border-zinc-700/60 bg-zinc-900" style={{ position: "sticky", top: 28, zIndex: Z.header }}>
                WH Stock
              </th>
              {/* ── Date columns ── */}
              {dates.map((d) => (
                <th key={d} className="py-2 px-2 text-center text-zinc-400 font-medium min-w-[48px] bg-zinc-900" style={{ position: "sticky", top: 28, zIndex: Z.header }}>
                  {fmtDate(d)}
                </th>
              ))}
              {/* ── MTD columns ── */}
              <th className="py-2 px-3 text-right text-zinc-400 font-medium border-l border-zinc-700/60 bg-zinc-900" style={{ position: "sticky", top: 28, zIndex: Z.header }}>
                Units
              </th>
              <th className="py-2 px-3 text-right text-zinc-400 font-medium bg-zinc-900" style={{ position: "sticky", top: 28, zIndex: Z.header }}>
                Value
              </th>
            </tr>
          </thead>

          {/* ── BODY ──────────────────────────────────────────── */}
          <tbody className="divide-y divide-zinc-800/50">
            {rows.map((row: PortalDailyRow, i: number) => (
              <tr key={row.sku_code} className="hover:bg-zinc-800/30 transition-colors">
                {/* Frozen: # */}
                <td
                  className="py-1.5 px-2 text-zinc-600 text-right bg-zinc-900"
                  style={{ ...frozenStyle(freeze.row), zIndex: Z.body }}
                >
                  {i + 1}
                </td>
                {/* Frozen: SKU */}
                <td
                  className="py-1.5 px-3 font-mono text-zinc-400 bg-zinc-900"
                  style={{ ...frozenStyle(freeze.sku), zIndex: Z.body }}
                >
                  {row.sku_code}
                </td>
                {/* Frozen: Product (last frozen — has edge shadow) */}
                <td
                  className="py-1.5 px-3 text-zinc-200 border-r border-zinc-700/60 bg-zinc-900"
                  style={{ ...frozenStyle(freeze.product), zIndex: Z.body, boxShadow: edgeShadow }}
                >
                  <span className="block truncate max-w-[190px]" title={row.product_name}>{row.product_name}</span>
                </td>
                {/* Scrollable: Category */}
                <td className="py-1.5 px-3 text-zinc-500">{row.category}</td>
                {/* Scrollable: Portal SKU */}
                <td className="py-1.5 px-3 font-mono text-zinc-600 text-[11px]">{row.portal_sku}</td>
                {/* Scrollable: BAU ASP */}
                <td className="py-1.5 px-3 text-right text-zinc-300 font-mono">{fmtAsp(row.bau_asp)}</td>
                {/* Scrollable: WH Stock */}
                <td className="py-1.5 px-3 text-right border-r border-zinc-700/60">
                  <StockBadge v={row.wh_stock} />
                </td>
                {/* Date columns */}
                {dates.map((d) => {
                  const { text, cls } = unitCell(row.daily_units[d]);
                  return (
                    <td key={d} className={`py-1.5 px-2 text-center tabular-nums ${cls}`}>
                      {text}
                    </td>
                  );
                })}
                {/* MTD */}
                <td className="py-1.5 px-3 text-right font-semibold text-zinc-100 border-l border-zinc-700/60 tabular-nums">
                  {row.mtd_units.toLocaleString("en-IN")}
                </td>
                <td className="py-1.5 px-3 text-right text-orange-400 font-semibold font-mono tabular-nums">
                  {fmtRevenue(row.mtd_value)}
                </td>
              </tr>
            ))}
          </tbody>

          {/* ── FOOTER (Totals) ───────────────────────────────── */}
          <tfoot>
            <tr className="border-t-2 border-zinc-600 bg-zinc-800">
              {/* Frozen: spans the 3 frozen cols */}
              <td
                colSpan={3}
                className="py-2.5 px-3 text-zinc-300 font-bold text-right text-[11px] uppercase tracking-wider border-r border-zinc-700/60 bg-zinc-800"
                style={{ position: "sticky", left: 0, bottom: 0, zIndex: Z.frozenFooter, minWidth: FREEZE_END, boxShadow: edgeShadow }}
              >
                Total
              </td>
              {/* Scrollable info cols — empty */}
              <td className="py-2.5 bg-zinc-800" style={{ position: "sticky", bottom: 0, zIndex: Z.footer }} />
              <td className="py-2.5 bg-zinc-800" style={{ position: "sticky", bottom: 0, zIndex: Z.footer }} />
              <td className="py-2.5 bg-zinc-800" style={{ position: "sticky", bottom: 0, zIndex: Z.footer }} />
              <td className="py-2.5 border-r border-zinc-700/60 bg-zinc-800" style={{ position: "sticky", bottom: 0, zIndex: Z.footer }} />
              {/* Date totals */}
              {dates.map((d) => {
                const total = rows.reduce((s, r) => s + (r.daily_units[d] ?? 0), 0);
                const { cls } = unitCell(total || null);
                return (
                  <td
                    key={d}
                    className={`py-2.5 px-2 text-center font-semibold tabular-nums bg-zinc-800 ${cls}`}
                    style={{ position: "sticky", bottom: 0, zIndex: Z.footer }}
                  >
                    {total > 0 ? total : "—"}
                  </td>
                );
              })}
              {/* MTD totals */}
              <td
                className="py-2.5 px-3 text-right font-bold text-zinc-50 border-l border-zinc-700/60 tabular-nums bg-zinc-800"
                style={{ position: "sticky", bottom: 0, zIndex: Z.footer }}
              >
                {rows.reduce((s, r) => s + r.mtd_units, 0).toLocaleString("en-IN")}
              </td>
              <td
                className="py-2.5 px-3 text-right font-bold text-orange-400 font-mono tabular-nums bg-zinc-800"
                style={{ position: "sticky", bottom: 0, zIndex: Z.footer }}
              >
                {fmtRevenue(rows.reduce((s, r) => s + r.mtd_value, 0))}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
