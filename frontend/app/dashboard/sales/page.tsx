"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type {
  SalesSummary, SalesByDimension, SalesTrend,
  TargetAchievement, Portal, PortalDailyResponse,
} from "@/lib/api";

import { SalesFilters }           from "@/components/sales/sales-filters";
import { KpiStrip }               from "@/components/sales/kpi-strip";
import { RevenueTrend }           from "@/components/sales/revenue-trend";
import { PortalBreakdown }        from "@/components/sales/portal-breakdown";

import { TargetAchievementPanel } from "@/components/sales/target-achievement";
import { PortalDailyTable }       from "@/components/sales/portal-daily-table";
import { Skeleton }               from "@/components/ui/skeleton";
import { NavTabs }                from "@/components/ui/nav-tabs";

function KpiSkeleton() {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {[...Array(4)].map((_, i) => (
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

  const [targetYear,  setTargetYear]  = useState(() => new Date().getFullYear());
  const [targetMonth, setTargetMonth] = useState(() => new Date().getMonth() + 1);

  const [portals,    setPortals]    = useState<Portal[]>([]);
  const [summary,    setSummary]    = useState<SalesSummary | null>(null);
  const [byPortal,   setByPortal]   = useState<SalesByDimension[]>([]);
  const [trend,      setTrend]      = useState<SalesTrend[]>([]);
  const [targets,    setTargets]    = useState<TargetAchievement[]>([]);

  const [dailyData,      setDailyData]      = useState<PortalDailyResponse | null>(null);
  const [dailyLoading,   setDailyLoading]   = useState(false);
  const [loading,        setLoading]        = useState(true);
  const [targetsLoading, setTargetsLoading] = useState(true);
  const [error,          setError]          = useState<string | null>(null);

  const fetchMain = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const fp = {
        ...(startDate ? { start_date: startDate } : {}),
        ...(endDate   ? { end_date: endDate }      : {}),
        ...(portalId  ? { portal_id: portalId }    : {}),
      };
      const [portalsRes, summaryRes, byPortalRes, trendRes] =
        await Promise.allSettled([
          api.portals(),
          api.salesSummary(fp),
          api.salesByPortal(fp),
          api.salesTrend(fp),
        ]);
      if (portalsRes.status  === "fulfilled") setPortals(portalsRes.value);
      if (summaryRes.status  === "fulfilled") setSummary(summaryRes.value);
      if (byPortalRes.status === "fulfilled") setByPortal(byPortalRes.value);
      if (trendRes.status    === "fulfilled") setTrend(trendRes.value);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load data");
    } finally { setLoading(false); }
  }, [startDate, endDate, portalId]);

  const fetchTargets = useCallback(async () => {
    setTargetsLoading(true);
    try { setTargets(await api.salesTargets({ year: targetYear, month: targetMonth })); }
    catch { setTargets([]); }
    finally { setTargetsLoading(false); }
  }, [targetYear, targetMonth]);

  const fetchPortalDaily = useCallback(async () => {
    if (!portalId) { setDailyData(null); return; }
    if (!portals.length) return;
    setDailyLoading(true);
    try {
      const portalName = portals.find(p => p.id === portalId)?.name;
      setDailyData(await api.portalDaily({
        ...(portalName ? { portal: portalName }    : {}),
        ...(startDate  ? { start_date: startDate } : {}),
        ...(endDate    ? { end_date: endDate }     : {}),
      }));
    } catch { setDailyData(null); }
    finally { setDailyLoading(false); }
  }, [portalId, portals, startDate, endDate]);

  useEffect(() => { fetchMain(); },        [fetchMain]);
  useEffect(() => { fetchTargets(); },     [fetchTargets]);
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

      {loading || !summary ? <KpiSkeleton /> : <KpiStrip summary={summary} productCount={0} />}
      {loading ? <ChartSkeleton h={320} /> : <RevenueTrend data={trend} />}
      {loading ? <ChartSkeleton h={360} /> : <PortalBreakdown data={byPortal} />}

      {targetsLoading ? <ChartSkeleton h={220} /> : (
        <TargetAchievementPanel
          data={targets} year={targetYear} month={targetMonth}
          onMonthChange={(y, m) => { setTargetYear(y); setTargetMonth(m); }}
        />
      )}
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
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => <div key={i} className="h-28 rounded-xl bg-zinc-800 animate-pulse" />)}
          </div>
          <div className="h-72 rounded-xl bg-zinc-800 animate-pulse" />
        </main>
      }
    >
      <SalesContent />
    </Suspense>
  );
}
