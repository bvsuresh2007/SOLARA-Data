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

/** Format an ISO yyyy-MM-dd range as a compact label, e.g. "20 Aug \u2013 31 Aug 2026". */
function fmtRangeLabel(start?: string | null, end?: string | null): string | null {
  if (!start || !end) return null;
  const s = new Date(start + "T00:00:00");
  const e = new Date(end + "T00:00:00");
  if (isNaN(s.getTime()) || isNaN(e.getTime())) return null;
  const mon = (d: Date) => d.toLocaleString("en-IN", { month: "short" });
  const left = `${s.getDate()} ${mon(s)}${s.getFullYear() !== e.getFullYear() ? " " + s.getFullYear() : ""}`;
  const right = `${e.getDate()} ${mon(e)} ${e.getFullYear()}`;
  return `${left} \u2013 ${right}`;
}

/** Small info glyph with a native-tooltip explanation. */
function InfoDot({ text }: { text: string }) {
  return (
    <span
      role="img"
      aria-label="info"
      title={text}
      className="ml-1 inline-flex h-3.5 w-3.5 cursor-help items-center justify-center rounded-full border border-zinc-600 text-[9px] font-semibold leading-none text-zinc-400 align-middle"
    >
      i
    </span>
  );
}

function GrowthBadge({ pct, title }: { pct: number | null; title?: string }) {
  if (pct == null) return null;
  const isUp = pct >= 0;
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-0.5 text-xs font-medium ${
        isUp ? "text-emerald-400" : "text-red-400"
      } ${title ? "cursor-help" : ""}`}
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
  prevRange?: { start_date: string; end_date: string } | null;
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

function DataAsOf({ iso }: { iso: string | null }) {
  if (!iso) return null;
  const d = new Date(iso);
  const ist = new Date(d.getTime() + 5.5 * 60 * 60 * 1000);
  const h = ist.getUTCHours();
  const m = ist.getUTCMinutes();
  const ampm = h >= 12 ? "PM" : "AM";
  const h12 = h % 12 || 12;
  const mm = m.toString().padStart(2, "0");
  const day = ist.getUTCDate();
  const mon = ist.toLocaleString("en-IN", { month: "short", timeZone: "UTC" });
  return (
    <span className="text-[11px] text-zinc-500 font-normal">
      Data as of {h12}:{mm} {ampm} IST, {day} {mon}
    </span>
  );
}

export function KpiStrip({ summary, prevSummary, prevRange, topByRevenue, topByUnits }: Props) {
  const asp =
    summary.total_quantity > 0
      ? summary.total_revenue / summary.total_quantity
      : 0;

  const prevAsp =
    prevSummary && prevSummary.total_quantity > 0
      ? prevSummary.total_revenue / prevSummary.total_quantity
      : null;

  // Comparison window (previous equal-length period) for the growth badges/tooltips.
  const cmpLabel = fmtRangeLabel(prevRange?.start_date, prevRange?.end_date);
  const cmpTitle = cmpLabel ? `Growth vs the previous period (${cmpLabel})` : undefined;
  const cmpSuffix = cmpLabel
    ? ` Growth compares the selected range against the previous equal-length period (${cmpLabel}).`
    : "";

  const BAU_NOTE =
    "Gross Revenue is BAU (business-as-usual) revenue: units sold \u00d7 each SKU's standard reference price (bau_asp), " +
    "NOT actual realized revenue. It strips out day-to-day discount/promo price swings.";
  const ASP_NOTE =
    "Average selling price on a BAU basis (BAU revenue \u00f7 units). Changes here reflect product-mix shifts " +
    "toward higher- or lower-priced SKUs, not actual price changes.";

  const kpis = [
    {
      label: "Gross Revenue",
      value: fmtRevenue(summary.total_revenue),
      accent: true,
      growth: growthPct(summary.total_revenue, prevSummary?.total_revenue),
      info: BAU_NOTE + cmpSuffix,
    },
    {
      label: "Units Sold",
      value: fmtNum(summary.total_quantity),
      accent: false,
      growth: growthPct(summary.total_quantity, prevSummary?.total_quantity),
      info: cmpLabel ? `Actual units sold.${cmpSuffix}` : null,
    },
    {
      label: "Avg ASP",
      value: fmtRevenue(asp),
      accent: false,
      growth: growthPct(asp, prevAsp),
      info: ASP_NOTE + cmpSuffix,
    },
  ];

  return (
    <div className="space-y-1">
      {summary.data_as_of && (
        <div className="flex justify-end">
          <DataAsOf iso={summary.data_as_of} />
        </div>
      )}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
      {kpis.map((kpi) => (
        <Card key={kpi.label}>
          <CardContent className="pt-6">
            <p className="text-xs text-zinc-500 mb-2 uppercase tracking-wider">
              {kpi.label}
              {kpi.info ? <InfoDot text={kpi.info} /> : null}
            </p>
            <div className="flex items-baseline gap-2">
              <p
                className={`text-2xl font-bold ${
                  kpi.accent ? "text-orange-400" : "text-zinc-50"
                }`}
              >
                {kpi.value}
              </p>
              <GrowthBadge pct={kpi.growth} title={cmpTitle} />
            </div>
          </CardContent>
        </Card>
      ))}

      <TopSkuCard label="Top SKU by Revenue" sku={topByRevenue} formatter={fmtRevenue} />
      <TopSkuCard label="Top SKU by Units" sku={topByUnits} formatter={fmtNum} />
    </div>
    </div>
  );
}
