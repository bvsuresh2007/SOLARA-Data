"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { SalesSummary } from "@/lib/api";
import { fmtRevenue } from "@/lib/format";

function fmtNum(value: number): string {
  return new Intl.NumberFormat("en-IN").format(Math.round(value));
}

/** Calculate growth % — returns null when previous value is 0 or missing */
function growthPct(current: number, previous: number | null | undefined): number | null {
  if (previous == null || previous === 0) return null;
  return ((current - previous) / previous) * 100;
}

function GrowthBadge({ pct }: { pct: number | null }) {
  if (pct == null) return null;
  const isUp = pct >= 0;
  return (
    <span
      className={`inline-flex items-center gap-0.5 text-xs font-medium ${
        isUp ? "text-emerald-400" : "text-red-400"
      }`}
    >
      {isUp ? "\u2191" : "\u2193"}
      {Math.abs(pct).toFixed(1)}%
    </span>
  );
}

interface TopSku {
  name: string;
  value: number;
}

interface Props {
  summary: SalesSummary;
  prevSummary?: SalesSummary | null;
  topByRevenue: TopSku | null;
  topByUnits: TopSku | null;
}

function TopSkuCard({ label, sku, formatter }: { label: string; sku: TopSku | null; formatter: (v: number) => string }) {
  return (
    <Card>
      <CardContent className="pt-6">
        <p className="text-xs text-zinc-500 mb-2 uppercase tracking-wider">{label}</p>
        {sku ? (
          <>
            <p className="text-sm font-semibold text-zinc-50 leading-tight line-clamp-2" title={sku.name}>
              {sku.name}
            </p>
            <p className="text-lg font-bold text-orange-400 mt-1">{formatter(sku.value)}</p>
          </>
        ) : (
          <p className="text-sm text-zinc-600">&mdash;</p>
        )}
      </CardContent>
    </Card>
  );
}

export function KpiStrip({ summary, prevSummary, topByRevenue, topByUnits }: Props) {
  const asp =
    summary.total_quantity > 0
      ? summary.total_revenue / summary.total_quantity
      : 0;

  const prevAsp =
    prevSummary && prevSummary.total_quantity > 0
      ? prevSummary.total_revenue / prevSummary.total_quantity
      : null;

  const kpis = [
    {
      label: "Gross Revenue",
      value: fmtRevenue(summary.total_revenue),
      accent: true,
      growth: growthPct(summary.total_revenue, prevSummary?.total_revenue),
    },
    {
      label: "Units Sold",
      value: fmtNum(summary.total_quantity),
      accent: false,
      growth: growthPct(summary.total_quantity, prevSummary?.total_quantity),
    },
    {
      label: "Avg ASP",
      value: fmtRevenue(asp),
      accent: false,
      growth: growthPct(asp, prevAsp),
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
      {kpis.map((kpi) => (
        <Card key={kpi.label}>
          <CardContent className="pt-6">
            <p className="text-xs text-zinc-500 mb-2 uppercase tracking-wider">
              {kpi.label}
            </p>
            <div className="flex items-baseline gap-2">
              <p
                className={`text-2xl font-bold ${
                  kpi.accent ? "text-orange-400" : "text-zinc-50"
                }`}
              >
                {kpi.value}
              </p>
              <GrowthBadge pct={kpi.growth} />
            </div>
          </CardContent>
        </Card>
      ))}

      <TopSkuCard label="Top SKU by Revenue" sku={topByRevenue} formatter={fmtRevenue} />
      <TopSkuCard label="Top SKU by Units" sku={topByUnits} formatter={fmtNum} />
    </div>
  );
}
