"use client";

import React, { useState, useMemo } from "react";
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
  return <span className={cls}>{v.toLocaleString("en-IN")}</span>;
}

function DocBadge({ v }: { v: number | null }) {
  if (v == null || !isFinite(v)) return <span className="text-zinc-700">—</span>;
  const cls = v < 7 ? "text-red-400 font-bold" : v < 14 ? "text-yellow-400 font-medium" : "text-green-400 font-medium";
  return <span className={cls}>{v.toFixed(1)}d</span>;
}

// ─── Sub-category canonical sort order ────────────────────────────────────────

const SUB_CATEGORY_ORDER: string[] = [
  "Air Fryer",
  "Air Fryer Combo",
  "Air Fryer Oven",
  "Air Fryer Oven Combo",
  "Blendkwik",
  "Cast Iron Cookware - Combo",
  "Cast Iron Cookware - Combo (Crwonstone)",
  "Cast Iron-Fry pan",
  "Cast Iron-Fry pan (Crownstone)",
  "Cast Iron-Kadhai",
  "Cast Iron-Kadhai (Crownstone)",
  "Cast Iron-Pancake Pan (Crownstone)",
  "Cast Iron-Paniyaram",
  "Cast Iron-Tawa",
  "Cast Iron-Tawa (Crownstone)",
  "Ceramic Cookware Set of 2",
  "Ceramic Cookware Set of 3",
  "Ceramic Cookware-Casserole (Belmont)",
  "Ceramic Cookware-Fry pan (Belmont)",
  "Ceramic Cookware-Tawa (Belmont)",
  "Chopping Board",
  "Electric Kettle",
  "Electric Kettle-MP",
  "Electric Lighter",
  "Food Thermometer",
  "Glass Tumbler",
  "Kids Lunch Boxes",
  "Kids Lunch Boxes combo",
  "Knife Set",
  "MontClaire Combo",
  "MontClaire Fry Pan",
  "MontClaire Kadai",
  "Mugs/Tumblers - Insulated (Classic)",
  "Mugs/Tumblers - Insulated (Echo)",
  "Mugs/Tumblers - Insulated (Elixir)",
  "Oil Sprayer",
  "Protein Shaker",
  "Shelf Liner",
  "Slow Juicer",
  "Spatula Sets",
  "Stand Blender",
  "Stand Blender- FBA",
  "Sterra Combo",
  "Sterra Fry Pan",
  "Sterra Kadai",
  "Sterra Sauce Pan",
  "Water Bottle - Gallon Motivational 3.8L",
  "Water Bottle - Insulated",
  "Water Bottle - Insulated (Orion)",
  "Water Bottle - Insulated Kids",
  "Water Bottle - Kids Motivational",
  "Water Bottle - Motivational",
  "Water Bottle - PG Motivational 2.2L",
  "Water Bottle - Stainless Steel",
];

const SUB_CAT_RANK = new Map(
  SUB_CATEGORY_ORDER.map((s, i) => [s.toLowerCase(), i])
);
function subCatRank(s: string | null) {
  if (!s) return 9999;
  return SUB_CAT_RANK.get(s.toLowerCase()) ?? 9999;
}

// ─── Sort icon ────────────────────────────────────────────────────────────────

function SortIcon({ active, dir }: { active: boolean; dir: "asc" | "desc" }) {
  if (!active) return <span className="ml-1 text-zinc-700 select-none">↕</span>;
  return <span className="ml-1 text-zinc-300 select-none">{dir === "asc" ? "↑" : "↓"}</span>;
}

// ─── Frozen column config ─────────────────────────────────────────────────────

const freeze = {
  row:      { w: 36,  left: 0   },
  sku:      { w: 180, left: 36  },
  product:  { w: 260, left: 216 },
} as const;

const FREEZE_END = 476;
const Z = { body: 10, header: 20, frozenHeader: 30, footer: 25, frozenFooter: 35 } as const;

function frozenStyle(col: { w: number; left: number }) {
  return { position: "sticky" as const, left: col.left, minWidth: col.w, width: col.w };
}

// ─── Sort key type ────────────────────────────────────────────────────────────

type SortKey =
  | "sku" | "product" | "portal_sku" | "bau_asp" | "wh_stock"
  | "swiggy_stock" | "zepto_stock" | "backend_qty" | "frontend_qty"
  | "mtd_units" | "drr" | "doc" | "mtd_value"
  | { date: string };

// ─── Component ────────────────────────────────────────────────────────────────

interface Props {
  data: PortalDailyResponse | null;
  loading: boolean;
  portalSelected?: boolean;
}

export function PortalDailyTable({ data, loading }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("mtd_value");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [search, setSearch]   = useState("");
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set());

  const rows        = data?.rows        ?? [];
  const dates       = data?.dates       ?? [];
  const portal_name = data?.portal_name ?? "";

  const showSwiggyStock  = portal_name.toLowerCase() === "swiggy";
  const showZeptoStock   = portal_name.toLowerCase() === "zepto";
  const showBlinkitStock = portal_name.toLowerCase() === "blinkit";
  const showDoc = showSwiggyStock || showZeptoStock || showBlinkitStock;

  function calcDoc(row: PortalDailyRow, drr: number): number | null {
    if (drr <= 0) return null;
    if (showBlinkitStock) {
      const total = (row.backend_qty ?? 0) + (row.frontend_qty ?? 0);
      return total / drr;
    }
    if (showSwiggyStock) return row.swiggy_stock != null ? row.swiggy_stock / drr : null;
    if (showZeptoStock)  return row.zepto_stock  != null ? row.zepto_stock  / drr : null;
    return null;
  }

  function toggleCat(cat: string) {
    setExpandedCats(prev => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat); else next.add(cat);
      return next;
    });
  }

  // ─── Sorting ───────────────────────────────────────────────────────────────

  function toggleSort(key: SortKey) {
    const keyStr = typeof key === "string" ? key : key.date;
    const curStr = typeof sortKey === "string" ? sortKey : (sortKey as { date: string }).date;
    if (keyStr === curStr) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      const textCols: SortKey[] = ["sku", "product", "portal_sku"];
      const isText = typeof key === "string" && (textCols as string[]).includes(key);
      setSortDir(isText ? "asc" : "desc");
    }
  }

  function isActive(key: SortKey): boolean {
    if (typeof key === "object" && typeof sortKey === "object")
      return key.date === (sortKey as { date: string }).date;
    return key === sortKey;
  }

  function rowVal(row: PortalDailyRow): string | number {
    const drr = dates.length > 0 ? row.mtd_units / dates.length : 0;
    if (typeof sortKey === "object") return row.daily_units[sortKey.date] ?? -Infinity;
    switch (sortKey) {
      case "sku":          return row.sku_code;
      case "product":      return row.product_name;
      case "portal_sku":   return row.portal_sku ?? "";
      case "bau_asp":      return row.bau_asp ?? -Infinity;
      case "wh_stock":     return row.wh_stock ?? -Infinity;
      case "swiggy_stock": return row.swiggy_stock ?? -Infinity;
      case "zepto_stock":  return row.zepto_stock ?? -Infinity;
      case "backend_qty":  return row.backend_qty ?? -Infinity;
      case "frontend_qty": return row.frontend_qty ?? -Infinity;
      case "mtd_units":    return row.mtd_units;
      case "drr":          return drr;
      case "doc":          return calcDoc(row, drr) ?? -Infinity;
      case "mtd_value":    return row.mtd_value;
      default:             return 0;
    }
  }

  // Sort individual SKU rows (within each group, always by mtd_value desc)
  const sortedRows = useMemo(() => {
    return [...rows].sort((a, b) => {
      const av = rowVal(a), bv = rowVal(b);
      if (typeof av === "string" && typeof bv === "string")
        return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      const an = av as number, bn = bv as number;
      return sortDir === "asc" ? an - bn : bn - an;
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, sortKey, sortDir]);

  // ─── Search filter ─────────────────────────────────────────────────────────
  const q = search.trim().toLowerCase();
  const visibleRows = q
    ? sortedRows.filter(r =>
        r.sku_code.toLowerCase().includes(q) ||
        r.product_name.toLowerCase().includes(q) ||
        (r.portal_sku ?? "").toLowerCase().includes(q)
      )
    : sortedRows;

  // ─── Group by sub-category ─────────────────────────────────────────────────
  const groups = useMemo(() => {
    const map = new Map<string, PortalDailyRow[]>();
    for (const row of visibleRows) {
      const key = row.sub_category ?? "—";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(row);
    }
    return map;
  }, [visibleRows]);

  // Sort groups by the active sort key's aggregate
  const sortedCats = useMemo(() => {
    const cats = Array.from(groups.keys());
    const agg = (catRows: PortalDailyRow[]): number => {
      if (typeof sortKey === "object")
        return catRows.reduce((s, r) => s + (r.daily_units[sortKey.date] ?? 0), 0);
      switch (sortKey) {
        case "mtd_units":    return catRows.reduce((s, r) => s + r.mtd_units, 0);
        case "mtd_value":    return catRows.reduce((s, r) => s + r.mtd_value, 0);
        case "wh_stock":     return catRows.reduce((s, r) => s + (r.wh_stock ?? 0), 0);
        case "swiggy_stock": return catRows.reduce((s, r) => s + (r.swiggy_stock ?? 0), 0);
        case "zepto_stock":  return catRows.reduce((s, r) => s + (r.zepto_stock ?? 0), 0);
        case "backend_qty":  return catRows.reduce((s, r) => s + (r.backend_qty ?? 0), 0);
        case "frontend_qty": return catRows.reduce((s, r) => s + (r.frontend_qty ?? 0), 0);
        case "drr":          return dates.length > 0 ? catRows.reduce((s, r) => s + r.mtd_units, 0) / dates.length : 0;
        default:             return 0;
      }
    };
    return cats.sort((a, b) => {
      const av = agg(groups.get(a)!), bv = agg(groups.get(b)!);
      return sortDir === "asc" ? av - bv : bv - av;
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groups, sortKey, sortDir, dates]);

  // When searching, auto-expand all matching groups
  const effectiveExpanded = q ? new Set(sortedCats) : expandedCats;

  // ─── Early returns AFTER all hooks ────────────────────────────────────────
  if (loading) return <Skeleton className="w-full rounded-xl" style={{ height: 360 }} />;

  if (!data || rows.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 px-6 py-10 text-center">
        <p className="text-sm text-zinc-500">No sales data for the selected portal and date range.</p>
      </div>
    );
  }

  // ─── CSV Download ──────────────────────────────────────────────────────────
  function downloadCsv() {
    const headers = [
      "#", "SKU", "Product Name", "Portal SKU", "BAU ASP", "WH Stock",
      ...(showSwiggyStock  ? ["Swiggy Stock"] : []),
      ...(showZeptoStock   ? ["Zepto Stock"]  : []),
      ...(showBlinkitStock ? ["Backend Qty", "Frontend Qty"] : []),
      ...dates.map(fmtDate),
      "MTD Units", "DRR", ...(showDoc ? ["DOC"] : []), "MTD Value",
    ];

    const csvRows = visibleRows.map((row, i) => [
      i + 1, row.sku_code, row.product_name, row.portal_sku,
      row.bau_asp != null ? `₹${row.bau_asp.toFixed(0)}` : "—",
      row.wh_stock != null ? row.wh_stock : "—",
      ...(showSwiggyStock  ? [row.swiggy_stock  != null ? row.swiggy_stock  : "—"] : []),
      ...(showZeptoStock   ? [row.zepto_stock   != null ? row.zepto_stock   : "—"] : []),
      ...(showBlinkitStock ? [row.backend_qty   != null ? row.backend_qty   : "—",
                              row.frontend_qty  != null ? row.frontend_qty  : "—"] : []),
      ...dates.map(d => row.daily_units[d] ?? "—"),
      row.mtd_units,
      dates.length > 0 ? (row.mtd_units / dates.length).toFixed(1) : "—",
      ...(showDoc ? (() => {
        const drr = dates.length > 0 ? row.mtd_units / dates.length : 0;
        const doc = calcDoc(row, drr);
        return [doc != null && isFinite(doc) ? `${doc.toFixed(1)}d` : "—"];
      })() : []),
      fmtRevenue(row.mtd_value),
    ]);

    const totals = [
      "Total", "", "", "", "", "", "",
      ...(showSwiggyStock  ? [""] : []),
      ...(showZeptoStock   ? [""] : []),
      ...(showBlinkitStock ? ["", ""] : []),
      ...dates.map(d => visibleRows.reduce((s, r) => s + (r.daily_units[d] ?? 0), 0)),
      visibleRows.reduce((s, r) => s + r.mtd_units, 0),
      dates.length > 0 ? (visibleRows.reduce((s, r) => s + r.mtd_units, 0) / dates.length).toFixed(1) : "—",
      ...(showDoc ? [""] : []),
      fmtRevenue(visibleRows.reduce((s, r) => s + r.mtd_value, 0)),
    ];

    const escape = (v: unknown) => {
      const s = String(v);
      return s.includes(",") || s.includes('"') || s.includes("\n")
        ? `"${s.replace(/"/g, '""')}"` : s;
    };

    const csv = [headers, ...csvRows, totals].map(row => row.map(escape).join(",")).join("\n");
    const dateFrom = dates[0] ?? "start";
    const dateTo   = dates[dates.length - 1] ?? "end";
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = `${portal_name}_${dateFrom}_${dateTo}.csv`; a.click();
    URL.revokeObjectURL(url);
  }

  const edgeShadow = "4px 0 6px -2px rgba(0,0,0,0.45)";
  const thCls = "cursor-pointer select-none hover:text-zinc-200 transition-colors";

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden">
      {/* Card header */}
      <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h2 className="font-semibold text-zinc-100 text-base">Daily Units Breakdown</h2>
          <p className="text-xs text-zinc-500 mt-0.5">
            {portal_name} · {dates[0] ? fmtDate(dates[0]) : "—"} – {dates[dates.length - 1] ? fmtDate(dates[dates.length - 1]) : "—"}
          </p>
        </div>
        {/* Search */}
        <div className="relative flex-1 min-w-[160px] max-w-[280px]">
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500 text-xs pointer-events-none">🔍</span>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search SKU / product…"
            className="w-full pl-7 pr-7 py-1.5 rounded-lg border border-zinc-700 bg-zinc-800 text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500"
          />
          {search && (
            <button onClick={() => setSearch("")} className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 text-xs">✕</button>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-zinc-500">
            {q ? (
              <><span className="text-zinc-300 font-semibold">{visibleRows.length}</span>/<span className="text-zinc-500">{rows.length}</span> products</>
            ) : (
              <><span className="text-zinc-300 font-semibold">{rows.length}</span> products</>
            )}{" "}·{" "}
            <span className="text-zinc-300 font-semibold">{dates.length}</span> days
          </span>
          <button
            onClick={downloadCsv}
            className="flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100 transition-colors"
          >
            ↓ Download CSV
          </button>
        </div>
      </div>

      {/* Scrollable container */}
      <div className="overflow-auto max-h-[70vh]">
        <table className="w-full text-xs whitespace-nowrap border-collapse">

          {/* ── HEADER ── */}
          <thead>
            <tr className="border-b border-zinc-800">
              <th className={`py-2 px-2 text-zinc-500 font-medium text-right bg-zinc-900 ${thCls}`}
                style={{ ...frozenStyle(freeze.row), position: "sticky", top: 0, left: freeze.row.left, zIndex: Z.frozenHeader }}
                onClick={() => toggleSort("sku")}>#</th>
              <th className={`py-2 px-3 text-left text-zinc-400 font-medium bg-zinc-900 ${thCls}`}
                style={{ ...frozenStyle(freeze.sku), position: "sticky", top: 0, left: freeze.sku.left, zIndex: Z.frozenHeader }}
                onClick={() => toggleSort("sku")}>
                SKU<SortIcon active={isActive("sku")} dir={sortDir} />
              </th>
<th className={`py-2 px-3 text-left text-zinc-400 font-medium border-r border-zinc-700/60 bg-zinc-900 ${thCls}`}
                style={{ ...frozenStyle(freeze.product), position: "sticky", top: 0, left: freeze.product.left, zIndex: Z.frozenHeader, boxShadow: edgeShadow }}
                onClick={() => toggleSort("product")}>
                Product Name<SortIcon active={isActive("product")} dir={sortDir} />
              </th>
              <th className={`py-2 px-3 text-left text-zinc-400 font-medium min-w-[110px] bg-zinc-900 ${thCls}`}
                style={{ position: "sticky", top: 0, zIndex: Z.header }} onClick={() => toggleSort("portal_sku")}>
                Portal SKU<SortIcon active={isActive("portal_sku")} dir={sortDir} />
              </th>
              <th className={`py-2 px-3 text-right text-zinc-400 font-medium min-w-[72px] bg-zinc-900 ${thCls}`}
                style={{ position: "sticky", top: 0, zIndex: Z.header }} onClick={() => toggleSort("bau_asp")}>
                BAU ASP<SortIcon active={isActive("bau_asp")} dir={sortDir} />
              </th>
              <th className={`py-2 px-3 text-right text-zinc-400 font-medium min-w-[72px] bg-zinc-900 ${thCls}`}
                style={{ position: "sticky", top: 0, zIndex: Z.header }} onClick={() => toggleSort("wh_stock")}>
                WH Stock<SortIcon active={isActive("wh_stock")} dir={sortDir} />
              </th>
              {showSwiggyStock && (
                <th className={`py-2 px-3 text-right text-zinc-400 font-medium min-w-[80px] border-r border-zinc-700/60 bg-zinc-900 ${thCls}`}
                  style={{ position: "sticky", top: 0, zIndex: Z.header }} onClick={() => toggleSort("swiggy_stock")}>
                  Swiggy Stock<SortIcon active={isActive("swiggy_stock")} dir={sortDir} />
                </th>
              )}
              {showZeptoStock && (
                <th className={`py-2 px-3 text-right text-zinc-400 font-medium min-w-[80px] border-r border-zinc-700/60 bg-zinc-900 ${thCls}`}
                  style={{ position: "sticky", top: 0, zIndex: Z.header }} onClick={() => toggleSort("zepto_stock")}>
                  Zepto Stock<SortIcon active={isActive("zepto_stock")} dir={sortDir} />
                </th>
              )}
              {showBlinkitStock && (
                <th className={`py-2 px-3 text-right text-zinc-400 font-medium min-w-[80px] bg-zinc-900 ${thCls}`}
                  style={{ position: "sticky", top: 0, zIndex: Z.header }} onClick={() => toggleSort("backend_qty")}>
                  Backend Qty<SortIcon active={isActive("backend_qty")} dir={sortDir} />
                </th>
              )}
              {showBlinkitStock && (
                <th className={`py-2 px-3 text-right text-zinc-400 font-medium min-w-[80px] border-r border-zinc-700/60 bg-zinc-900 ${thCls}`}
                  style={{ position: "sticky", top: 0, zIndex: Z.header }} onClick={() => toggleSort("frontend_qty")}>
                  Frontend Qty<SortIcon active={isActive("frontend_qty")} dir={sortDir} />
                </th>
              )}
              {dates.map((d) => (
                <th key={d} className={`py-2 px-2 text-center text-zinc-400 font-medium min-w-[48px] bg-zinc-900 ${thCls}`}
                  style={{ position: "sticky", top: 0, zIndex: Z.header }} onClick={() => toggleSort({ date: d })}>
                  {fmtDate(d)}<SortIcon active={isActive({ date: d })} dir={sortDir} />
                </th>
              ))}
              <th className={`py-2 px-3 text-right text-zinc-400 font-medium border-l border-zinc-700/60 bg-zinc-900 ${thCls}`}
                style={{ position: "sticky", top: 0, zIndex: Z.header }} onClick={() => toggleSort("mtd_units")}>
                Units<SortIcon active={isActive("mtd_units")} dir={sortDir} />
              </th>
              <th className={`py-2 px-3 text-right text-sky-500 font-medium bg-zinc-900 ${thCls}`}
                style={{ position: "sticky", top: 0, zIndex: Z.header }} onClick={() => toggleSort("drr")}>
                DRR<SortIcon active={isActive("drr")} dir={sortDir} />
              </th>
              {showDoc && (
                <th className={`py-2 px-3 text-right text-amber-500 font-medium min-w-[60px] bg-zinc-900 ${thCls}`}
                  style={{ position: "sticky", top: 0, zIndex: Z.header }} onClick={() => toggleSort("doc")}>
                  DOC<SortIcon active={isActive("doc")} dir={sortDir} />
                </th>
              )}
              <th className={`py-2 px-3 text-right text-zinc-400 font-medium bg-zinc-900 ${thCls}`}
                style={{ position: "sticky", top: 0, zIndex: Z.header }} onClick={() => toggleSort("mtd_value")}>
                Value<SortIcon active={isActive("mtd_value")} dir={sortDir} />
              </th>
            </tr>
          </thead>

          {/* ── BODY ── */}
          <tbody className="divide-y divide-zinc-800/50">
            {sortedCats.map((cat, catIdx) => {
              const catRows = groups.get(cat)!;
              const isOpen  = effectiveExpanded.has(cat);

              // Group aggregates
              const totalWh      = catRows.reduce((s, r) => s + (r.wh_stock      ?? 0), 0);
              const totalSwiggy  = catRows.reduce((s, r) => s + (r.swiggy_stock  ?? 0), 0);
              const totalZepto   = catRows.reduce((s, r) => s + (r.zepto_stock   ?? 0), 0);
              const totalBackend = catRows.reduce((s, r) => s + (r.backend_qty   ?? 0), 0);
              const totalFront   = catRows.reduce((s, r) => s + (r.frontend_qty  ?? 0), 0);
              const totalMtd     = catRows.reduce((s, r) => s + r.mtd_units, 0);
              const totalValue   = catRows.reduce((s, r) => s + r.mtd_value, 0);
              const groupDrr     = dates.length > 0 ? totalMtd / dates.length : 0;
              const groupDoc = (() => {
                if (!showDoc || groupDrr <= 0) return null;
                if (showBlinkitStock) return (totalBackend + totalFront) / groupDrr;
                if (showSwiggyStock)  return totalSwiggy / groupDrr;
                if (showZeptoStock)   return totalZepto  / groupDrr;
                return null;
              })();

              const groupBg     = "bg-zinc-800/70";
              const groupBgFrz  = "bg-zinc-800";

              return (
                <React.Fragment key={cat}>
                  {/* ── Sub-category group row ── */}
                  <tr
                    className={`border-t border-zinc-700 cursor-pointer hover:brightness-125 transition-all ${groupBg}`}
                    onClick={() => toggleCat(cat)}
                  >
                    {/* Frozen: rank + expand + name + SKU count */}
                    <td
                      colSpan={3}
                      className={`py-2 px-3 font-semibold border-r border-zinc-700/60 ${groupBgFrz}`}
                      style={{ position: "sticky", left: 0, zIndex: Z.body + 1, minWidth: FREEZE_END, boxShadow: edgeShadow }}
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-zinc-500 text-[10px] font-mono w-4 shrink-0">{catIdx + 1}</span>
                        <span className="text-zinc-500 text-[10px] select-none shrink-0">{isOpen ? "▼" : "▶"}</span>
                        <span className="text-zinc-100 font-semibold text-[12px]">{cat}</span>
                        <span className="text-zinc-500 text-[10px] shrink-0">{catRows.length} SKU{catRows.length !== 1 ? "s" : ""}</span>
                      </div>
                    </td>
                    {/* Portal SKU — blank */}
                    <td className={`py-2 ${groupBg}`} />
                    {/* BAU ASP — blank */}
                    <td className={`py-2 ${groupBg}`} />
                    {/* WH Stock */}
                    <td className={`py-2 px-3 text-right font-semibold tabular-nums ${groupBg}${!showSwiggyStock && !showZeptoStock && !showBlinkitStock ? " border-r border-zinc-700/60" : ""}`}>
                      <StockBadge v={totalWh} />
                    </td>
                    {showSwiggyStock && (
                      <td className={`py-2 px-3 text-right font-semibold border-r border-zinc-700/60 ${groupBg}`}><StockBadge v={totalSwiggy} /></td>
                    )}
                    {showZeptoStock && (
                      <td className={`py-2 px-3 text-right font-semibold border-r border-zinc-700/60 ${groupBg}`}><StockBadge v={totalZepto} /></td>
                    )}
                    {showBlinkitStock && (
                      <td className={`py-2 px-3 text-right font-semibold ${groupBg}`}><StockBadge v={totalBackend} /></td>
                    )}
                    {showBlinkitStock && (
                      <td className={`py-2 px-3 text-right font-semibold border-r border-zinc-700/60 ${groupBg}`}><StockBadge v={totalFront} /></td>
                    )}
                    {dates.map(d => {
                      const total = catRows.reduce((s, r) => s + (r.daily_units[d] ?? 0), 0);
                      const { cls } = unitCell(total || null);
                      return (
                        <td key={d} className={`py-2 px-2 text-center tabular-nums font-semibold ${groupBg} ${cls}`}>
                          {total > 0 ? total : "—"}
                        </td>
                      );
                    })}
                    <td className={`py-2 px-3 text-right font-bold text-zinc-50 border-l border-zinc-700/60 tabular-nums ${groupBg}`}>
                      {totalMtd.toLocaleString("en-IN")}
                    </td>
                    <td className={`py-2 px-3 text-right text-sky-400 font-semibold tabular-nums ${groupBg}`}>
                      {dates.length > 0 ? groupDrr.toFixed(1) : "—"}
                    </td>
                    {showDoc && (
                      <td className={`py-2 px-3 text-right tabular-nums ${groupBg}`}><DocBadge v={groupDoc} /></td>
                    )}
                    <td className={`py-2 px-3 text-right text-orange-400 font-bold font-mono tabular-nums ${groupBg}`}>
                      {fmtRevenue(totalValue)}
                    </td>
                  </tr>

                  {/* ── Expanded SKU rows ── */}
                  {isOpen && catRows.map((row, i) => (
                    <tr key={row.sku_code} className="hover:bg-zinc-800/30 transition-colors">
                      <td className="py-1.5 px-2 text-zinc-600 text-right bg-zinc-900" style={{ ...frozenStyle(freeze.row), zIndex: Z.body }}>
                        {i + 1}
                      </td>
                      <td className="py-1.5 px-3 font-mono text-zinc-400 bg-zinc-900" style={{ ...frozenStyle(freeze.sku), zIndex: Z.body }}>
                        <span className="pl-2 border-l-2 border-zinc-700">{row.sku_code}</span>
                      </td>
<td className="py-1.5 px-3 text-[10px] text-zinc-200 border-r border-zinc-700/60 bg-zinc-900" style={{ ...frozenStyle(freeze.product), zIndex: Z.body, boxShadow: edgeShadow }}>
                        {row.product_name}
                      </td>
                      <td className="py-1.5 px-3 font-mono text-zinc-600 text-[11px]">{row.portal_sku}</td>
                      <td className="py-1.5 px-3 text-right text-zinc-300 font-mono">{fmtAsp(row.bau_asp)}</td>
                      <td className={`py-1.5 px-3 text-right${!showSwiggyStock && !showZeptoStock && !showBlinkitStock ? " border-r border-zinc-700/60" : ""}`}>
                        <StockBadge v={row.wh_stock} />
                      </td>
                      {showSwiggyStock && (
                        <td className="py-1.5 px-3 text-right border-r border-zinc-700/60"><StockBadge v={row.swiggy_stock} /></td>
                      )}
                      {showZeptoStock && (
                        <td className="py-1.5 px-3 text-right border-r border-zinc-700/60"><StockBadge v={row.zepto_stock} /></td>
                      )}
                      {showBlinkitStock && (
                        <td className="py-1.5 px-3 text-right"><StockBadge v={row.backend_qty} /></td>
                      )}
                      {showBlinkitStock && (
                        <td className="py-1.5 px-3 text-right border-r border-zinc-700/60"><StockBadge v={row.frontend_qty} /></td>
                      )}
                      {dates.map((d) => {
                        const { text, cls } = unitCell(row.daily_units[d]);
                        return <td key={d} className={`py-1.5 px-2 text-center tabular-nums ${cls}`}>{text}</td>;
                      })}
                      <td className="py-1.5 px-3 text-right font-semibold text-zinc-100 border-l border-zinc-700/60 tabular-nums">
                        {row.mtd_units.toLocaleString("en-IN")}
                      </td>
                      <td className="py-1.5 px-3 text-right text-sky-400 font-medium tabular-nums">
                        {dates.length > 0 ? (row.mtd_units / dates.length).toFixed(1) : "—"}
                      </td>
                      {showDoc && (() => {
                        const drr = dates.length > 0 ? row.mtd_units / dates.length : 0;
                        return <td className="py-1.5 px-3 text-right tabular-nums"><DocBadge v={calcDoc(row, drr)} /></td>;
                      })()}
                      <td className="py-1.5 px-3 text-right text-orange-400 font-semibold font-mono tabular-nums">
                        {fmtRevenue(row.mtd_value)}
                      </td>
                    </tr>
                  ))}
                </React.Fragment>
              );
            })}
          </tbody>

          {/* ── FOOTER (Totals) ── */}
          <tfoot>
            <tr className="border-t-2 border-zinc-600 bg-zinc-800">
              <td colSpan={3} className="py-2.5 px-3 text-zinc-300 font-bold text-right text-[11px] uppercase tracking-wider border-r border-zinc-700/60 bg-zinc-800"
                style={{ position: "sticky", left: 0, bottom: 0, zIndex: Z.frozenFooter, minWidth: FREEZE_END, boxShadow: edgeShadow }}>
                Total
              </td>
              <td className="py-2.5 bg-zinc-800" style={{ position: "sticky", bottom: 0, zIndex: Z.footer }} />
              <td className="py-2.5 bg-zinc-800" style={{ position: "sticky", bottom: 0, zIndex: Z.footer }} />
              <td className={`py-2.5 px-3 text-right font-bold tabular-nums text-zinc-200 bg-zinc-800${!showSwiggyStock && !showZeptoStock && !showBlinkitStock ? " border-r border-zinc-700/60" : ""}`}
                style={{ position: "sticky", bottom: 0, zIndex: Z.footer }}>
                {visibleRows.reduce((s, r) => s + (r.wh_stock ?? 0), 0).toLocaleString("en-IN")}
              </td>
              {showSwiggyStock && (
                <td className="py-2.5 px-3 text-right font-bold tabular-nums text-zinc-200 border-r border-zinc-700/60 bg-zinc-800" style={{ position: "sticky", bottom: 0, zIndex: Z.footer }}>
                  {visibleRows.reduce((s, r) => s + (r.swiggy_stock ?? 0), 0).toLocaleString("en-IN")}
                </td>
              )}
              {showZeptoStock && (
                <td className="py-2.5 px-3 text-right font-bold tabular-nums text-zinc-200 border-r border-zinc-700/60 bg-zinc-800" style={{ position: "sticky", bottom: 0, zIndex: Z.footer }}>
                  {visibleRows.reduce((s, r) => s + (r.zepto_stock ?? 0), 0).toLocaleString("en-IN")}
                </td>
              )}
              {showBlinkitStock && (
                <td className="py-2.5 px-3 text-right font-bold tabular-nums text-zinc-200 bg-zinc-800" style={{ position: "sticky", bottom: 0, zIndex: Z.footer }}>
                  {visibleRows.reduce((s, r) => s + (r.backend_qty ?? 0), 0).toLocaleString("en-IN")}
                </td>
              )}
              {showBlinkitStock && (
                <td className="py-2.5 px-3 text-right font-bold tabular-nums text-zinc-200 border-r border-zinc-700/60 bg-zinc-800" style={{ position: "sticky", bottom: 0, zIndex: Z.footer }}>
                  {visibleRows.reduce((s, r) => s + (r.frontend_qty ?? 0), 0).toLocaleString("en-IN")}
                </td>
              )}
              {dates.map((d) => {
                const total = visibleRows.reduce((s, r) => s + (r.daily_units[d] ?? 0), 0);
                const { cls } = unitCell(total || null);
                return (
                  <td key={d} className={`py-2.5 px-2 text-center font-semibold tabular-nums bg-zinc-800 ${cls}`} style={{ position: "sticky", bottom: 0, zIndex: Z.footer }}>
                    {total > 0 ? total : "—"}
                  </td>
                );
              })}
              <td className="py-2.5 px-3 text-right font-bold text-zinc-50 border-l border-zinc-700/60 tabular-nums bg-zinc-800" style={{ position: "sticky", bottom: 0, zIndex: Z.footer }}>
                {visibleRows.reduce((s, r) => s + r.mtd_units, 0).toLocaleString("en-IN")}
              </td>
              <td className="py-2.5 px-3 text-right font-bold text-sky-400 tabular-nums bg-zinc-800" style={{ position: "sticky", bottom: 0, zIndex: Z.footer }}>
                {dates.length > 0 ? (visibleRows.reduce((s, r) => s + r.mtd_units, 0) / dates.length).toFixed(1) : "—"}
              </td>
              {showDoc && (
                <td className="py-2.5 bg-zinc-800" style={{ position: "sticky", bottom: 0, zIndex: Z.footer }} />
              )}
              <td className="py-2.5 px-3 text-right font-bold text-orange-400 font-mono tabular-nums bg-zinc-800" style={{ position: "sticky", bottom: 0, zIndex: Z.footer }}>
                {fmtRevenue(visibleRows.reduce((s, r) => s + r.mtd_value, 0))}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
