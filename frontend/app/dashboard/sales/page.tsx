"use client";

import { useEffect, useState, useCallback, useMemo, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type {
  SalesSummary, SalesByDimension, SalesTrend,
  Portal, PortalDailyResponse,
} from "@/lib/api";
import { format, differenceInCalendarDays, subDays } from "date-fns";

import { SalesFilters }           from "@/components/sales/sales-filters";
import { KpiStrip }               from "@/components/sales/kpi-strip";
import { RevenueTrend }           from "@/components/sales/revenue-trend";
import { PortalBreakdown }        from "@/components/sales/portal-breakdown";

import { PortalDailyTable }       from "@/components/sales/portal-daily-table";
import { Skeleton }               from "@/components/ui/skeleton";
import { NavTabs }                from "@/components/ui/nav-tabs";

function KpiSkeleton() {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
      {[...Array(5)].map((_, i) => (
        <Skeleton key={i} className="h-28 rounded-xl" />
      ))}
    </div>
  );
}
function ChartSkeleton({ h = 300 }: { h?: number }) {
  return <Skeleton className="rounded-xl w-full" style={{ height: h }} />;
}

function SalesContent() {
  const params = useSearchParams();

  const startDate   = params.get("start_date")  ?? undefined;
  const endDate     = params.get("end_date")    ?? undefined;
  const portalIdStr = params.get("portal_id")   ?? undefined;
  const portalId    = portalIdStr ? Number(portalIdStr) : undefined;

  const [portals,       setPortals]       = useState<Portal[]>([]);
  const [summary,       setSummary]       = useState<SalesSummary | null>(null);
  const [byPortal,      setByPortal]      = useState<SalesByDimension[]>([]);
  const [trend,         setTrend]         = useState<SalesTrend[]>([]);
  const [topByRevenue,  setTopByRevenue]  = useState<SalesByDimension | null>(null);
  const [topByUnits,    setTopByUnits]    = useState<SalesByDimension | null>(null);

  const [prevSummary,    setPrevSummary]    = useState<SalesSummary | null>(null);

  const [dailyData,      setDailyData]      = useState<PortalDailyResponse | null>(null);
  const [dailyLoading,   setDailyLoading]   = useState(false);
  const [loading,        setLoading]        = useState(true);
  const [error,          setError]          = useState<string | null>(null);

  // Calculate previous period dates for growth comparison
  const prevPeriod = useMemo(() => {
    if (!startDate || !endDate) return null;          // "All" — no comparison
    const s = new Date(startDate + "T00:00:00");
    const e = new Date(endDate + "T00:00:00");
    const span = differenceInCalendarDays(e, s);      // e.g. 6 for a 7-day window
    const prevEnd   = subDays(s, 1);
    const prevStart = subDays(prevEnd, span);
    return {
      start_date: format(prevStart, "yyyy-MM-dd"),
      end_date:   format(prevEnd,   "yyyy-MM-dd"),
    };
  }, [startDate, endDate]);

  const fetchMain = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const fp = {
        ...(startDate ? { start_date: startDate } : {}),
        ...(endDate   ? { end_date: endDate }      : {}),
        ...(portalId  ? { portal_id: portalId }    : {}),
      };

      // Build previous-period params (null when "All" is selected)
      const prevFp = prevPeriod
        ? { start_date: prevPeriod.start_date, end_date: prevPeriod.end_date, ...(portalId ? { portal_id: portalId } : {}) }
        : null;

      const promises = [
        api.portals(),                                              // 0
        api.salesSummary(fp),                                       // 1
        api.salesByPortal(fp),                                      // 2
        api.salesTrend(fp),                                         // 3
        api.salesByProduct({ ...fp, limit: 1, sort_by: "revenue" }),// 4
        api.salesByProduct({ ...fp, limit: 1, sort_by: "units" }), // 5
        ...(prevFp ? [api.salesSummary(prevFp)] : []),              // 6 (optional)
      ];

      const results = await Promise.allSettled(promises);

      const [portalsRes, summaryRes, byPortalRes, trendRes, topRevRes, topUnitsRes] = results;
      const prevSummaryRes = prevFp ? results[6] : undefined;

      if (portalsRes.status    === "fulfilled") setPortals(portalsRes.value as Portal[]);
      if (summaryRes.status    === "fulfilled") setSummary(summaryRes.value as SalesSummary);
      if (byPortalRes.status   === "fulfilled") setByPortal(byPortalRes.value as SalesByDimension[]);
      if (trendRes.status      === "fulfilled") setTrend(trendRes.value as SalesTrend[]);

      if (topRevRes.status === "fulfilled" && (topRevRes.value as SalesByDimension[]).length > 0) {
        setTopByRevenue((topRevRes.value as SalesByDimension[])[0]);
      } else {
        setTopByRevenue(null);
      }
      if (topUnitsRes.status === "fulfilled" && (topUnitsRes.value as SalesByDimension[]).length > 0) {
        setTopByUnits((topUnitsRes.value as SalesByDimension[])[0]);
      } else {
        setTopByUnits(null);
      }

      // Previous-period summary for growth calculation
      if (prevSummaryRes?.status === "fulfilled") {
        setPrevSummary(prevSummaryRes.value as SalesSummary);
      } else {
        setPrevSummary(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load data");
    } finally { setLoading(false); }
  }, [startDate, endDate, portalId, prevPeriod]);

  const fetchPortalDaily = useCallback(async () => {
    if (!portals.length) return;
    setDailyLoading(true);
    try {
      const portalSlug = portalId
        ? portals.find(p => p.id === portalId)?.name ?? "all"
        : "all";
      setDailyData(await api.portalDaily({
        portal: portalSlug,
        ...(startDate  ? { start_date: startDate } : {}),
        ...(endDate    ? { end_date: endDate }     : {}),
      }));
    } catch { setDailyData(null); }
    finally { setDailyLoading(false); }
  }, [portalId, portals, startDate, endDate]);

  useEffect(() => { fetchMain(); },        [fetchMain]);
  useEffect(() => { fetchPortalDaily(); }, [fetchPortalDaily]);

  return (
    <main className="min-h-screen bg-zinc-950 p-6 space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-zinc-50">Sales Analytics</h1>
          <p className="text-sm text-zinc-500 mt-0.5">Revenue, units, and category breakdown across all portals</p>
        </div>
        <NavTabs />
      </header>

      <SalesFilters portals={portals} />

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/30 px-4 py-3 text-sm text-red-400">{error}</div>
      )}

      {loading || !summary ? <KpiSkeleton /> : (
        <KpiStrip
          summary={summary}
          prevSummary={prevSummary}
          topByRevenue={topByRevenue ? { name: topByRevenue.dimension_name, value: topByRevenue.total_revenue } : null}
          topByUnits={topByUnits ? { name: topByUnits.dimension_name, value: topByUnits.total_quantity } : null}
        />
      )}
      {loading ? <ChartSkeleton h={320} /> : <RevenueTrend data={trend} />}
      {loading ? <ChartSkeleton h={360} /> : <PortalBreakdown data={byPortal} />}
      <PortalDailyTable data={dailyData} loading={dailyLoading} portalSelected={!!portalId} />
    </main>
  );
}

export default function SalesDashboardPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-zinc-950 p-6 space-y-6">
          <div className="h-8 w-48 rounded bg-zinc-800 animate-pulse" />
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
            {[...Array(5)].map((_, i) => <div key={i} className="h-28 rounded-xl bg-zinc-800 animate-pulse" />)}
          </div>
          <div className="h-72 rounded-xl bg-zinc-800 animate-pulse" />
        </main>
      }
    >
      <SalesContent />
    </Suspense>
  );
}
