"use client";

import { useState, useMemo } from "react";
import { ChevronUp, ChevronDown, Search } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { SalesByDimension } from "@/lib/api";
import { fmtRevenue } from "@/lib/format";

type SortKey = "total_revenue" | "total_quantity" | "asp" | "share";
type SortDir = "asc" | "desc";

function fmtNum(v: number): string {
  return new Intl.NumberFormat("en-IN").format(Math.round(v));
}

interface Props {
  data: SalesByDimension[];
  totalRevenue: number;
}

export function ProductTable({ data, totalRevenue }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("total_revenue");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [search, setSearch] = useState("");

  const rows = useMemo(() => {
    const q = search.toLowerCase();
    let filtered = data.filter((d) =>
      d.dimension_name.toLowerCase().includes(q) ||
      (d.sku_code ?? "").toLowerCase().includes(q)
    );
    filtered = [...filtered].sort((a, b) => {
      let av = 0, bv = 0;
      if (sortKey === "total_revenue") { av = a.total_revenue; bv = b.total_revenue; }
      else if (sortKey === "total_quantity") { av = a.total_quantity; bv = b.total_quantity; }
      else if (sortKey === "asp") {
        av = a.total_quantity > 0 ? a.total_revenue / a.total_quantity : 0;
        bv = b.total_quantity > 0 ? b.total_revenue / b.total_quantity : 0;
      } else { av = a.total_revenue; bv = b.total_revenue; }
      return sortDir === "desc" ? bv - av : av - bv;
    });
    return filtered;
  }, [data, sortKey, sortDir, search]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    else { setSortKey(key); setSortDir("desc"); }
  }

  function SortIcon({ col }: { col: SortKey }) {
    if (col !== sortKey) return <ChevronDown size={12} className="text-zinc-600" />;
    return sortDir === "desc"
      ? <ChevronDown size={12} className="text-orange-400" />
      : <ChevronUp size={12} className="text-orange-400" />;
  }

  function ColHead({ col, label, right }: { col: SortKey; label: string; right?: boolean }) {
    return (
      <th
        className={`pb-2 text-xs font-medium text-zinc-500 cursor-pointer select-none hover:text-zinc-300 transition-colors ${right ? "text-right" : ""}`}
        onClick={() => toggleSort(col)}
      >
        <span className="inline-flex items-center gap-1">
          {right && <SortIcon col={col} />}
          {label}
          {!right && <SortIcon col={col} />}
        </span>
      </th>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-base">Top Products by Revenue</CardTitle>
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none" />
          <Input
            type="text"
            placeholder="Search products…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 w-48 pl-8 bg-zinc-800 border-zinc-700 text-zinc-300 text-xs placeholder:text-zinc-600 focus-visible:ring-0"
          />
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800">
                <th className="pb-2 text-xs font-medium text-zinc-500 w-8">#</th>
                <th className="pb-2 text-xs font-medium text-zinc-500 text-left">Product</th>
                <ColHead col="total_revenue" label="Revenue" right />
                <ColHead col="total_quantity" label="Units" right />
                <ColHead col="asp" label="ASP" right />
                <ColHead col="share" label="Share" right />
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/50">
              {rows.slice(0, 50).map((p, i) => {
                const asp = p.total_quantity > 0 ? p.total_revenue / p.total_quantity : 0;
                const share = totalRevenue > 0 ? (p.total_revenue / totalRevenue) * 100 : 0;
                return (
                  <tr key={p.dimension_id} className="hover:bg-zinc-800/40 transition-colors">
                    <td className="py-2.5 text-zinc-600 text-xs">{i + 1}</td>
                    <td className="py-2.5 text-zinc-200 max-w-xs">
                      <div className="group relative inline-block max-w-full">
                        <span className="line-clamp-1 cursor-default">
                          {p.sku_code ?? p.dimension_name}
                        </span>
                        {p.sku_code && (
                          <div className="pointer-events-none absolute bottom-full left-0 z-50 mb-1.5 hidden w-max max-w-xs rounded border border-zinc-700 bg-zinc-800 px-2.5 py-1.5 text-xs text-zinc-100 shadow-xl group-hover:block">
                            {p.dimension_name}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="py-2.5 text-right text-zinc-100 font-medium font-mono text-xs">{fmtRevenue(p.total_revenue)}</td>
                    <td className="py-2.5 text-right text-zinc-400 text-xs">{fmtNum(p.total_quantity)}</td>
                    <td className="py-2.5 text-right text-zinc-400 text-xs">{fmtRevenue(asp)}</td>
                    <td className="py-2.5 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-16 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                          <div className="h-full bg-orange-500/60 rounded-full" style={{ width: `${Math.min(share * 3, 100)}%` }} />
                        </div>
                        <span className="text-zinc-500 text-xs w-10 text-right">{share.toFixed(1)}%</span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {rows.length === 0 && (
            <p className="text-center text-zinc-600 text-sm py-8">No products found</p>
          )}
          {rows.length > 50 && (
            <p className="text-xs text-zinc-600 mt-3 px-1">
              Showing 50 of {rows.length} products{search ? ` matching "${search}"` : ""}.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
