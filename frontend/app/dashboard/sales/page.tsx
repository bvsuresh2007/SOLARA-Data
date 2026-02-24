"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type {
  SalesSummary, SalesByDimension, SalesTrend,
  SalesByCategory, TargetAchievement, Portal, PortalDailyResponse,
} from "@/lib/api";

import { SalesFilters }          from "@/components/sales/sales-filters";
import { KpiStrip }              from "@/components/sales/kpi-strip";
import { RevenueTrend }          from "@/components/sales/revenue-trend";
import { PortalBreakdown }       from "@/components/sales/portal-breakdown";
import { CategoryChart }         from "@/components/sales/category-chart";
import { TargetAchievementPanel } from "@/components/sales/target-achievement";
import { ProductTable }          from "@/components/sales/product-table";
import { PortalDailyTable }      from "@/components/sales/portal-daily-table";
import { Skeleton }              from "@/components/ui/skeleton";

// ─── Skeleton placeholders ────────────────────────────────────────────────────
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

// ─── Inner content (uses useSearchParams) ────────────────────────────────────
function SalesContent() {
  const params = useSearchParams();

  const startDate  = params.get("start_date")  ?? undefined;
  const endDate    = params.get("end_date")    ?? undefined;
  const portalIdStr = params.get("portal_id") ?? undefined;
  const portalId   = portalIdStr ? Number(portalIdStr) : undefined;

  // Target month state — independent of date range filter
  const today = new Date();
  const [targetYear,  setTargetYear]  = useState(today.getFullYear());
  const [targetMonth, setTargetMonth] = useState(today.getMonth() + 1);

  // Data state
  const [portals,     setPortals]     = useState<Portal[]>([]);
  const [summary,     setSummary]     = useState<SalesSummary | null>(null);
  const [byPortal,    setByPortal]    = useState<SalesByDimension[]>([]);
  const [trend,       setTrend]       = useState<SalesTrend[]>([]);
  const [byCategory,  setByCategory]  = useState<SalesByCategory[]>([]);
  const [byProduct,   setByProduct]   = useState<SalesByDimension[]>([]);
  const [targets,     setTargets]     = useState<TargetAchievement[]>([]);

  const [dailyData,   setDailyData]   = useState<PortalDailyResponse | null>(null);
  const [dailyLoading, setDailyLoading] = useState(false);

  const [loading,     setLoading]     = useState(true);
  const [targetsLoading, setTargetsLoading] = useState(true);
  const [error,       setError]       = useState<string | null>(null);

  // Fetch main data when date/portal filter changes
  const fetchMain = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const filterParams = {
        ...(startDate  ? { start_date: startDate }  : {}),
        ...(endDate    ? { end_date: endDate }       : {}),
        ...(portalId   ? { portal_id: portalId }     : {}),
      };

      const [portalsData, summaryData, byPortalData, trendData, byCatData, byProdData] =
        await Promise.all([
          api.portals(),
          api.salesSummary(filterParams),
          api.salesByPortal(filterParams),
          api.salesTrend(filterParams),
          api.salesByCategory(filterParams),
          api.salesByProduct({ ...filterParams, limit: 50 }),
        ]);

      setPortals(portalsData);
      setSummary(summaryData);
      setByPortal(byPortalData);
      setTrend(trendData);
      setByCategory(byCatData);
      setByProduct(byProdData);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate, portalId]);

  // Fetch target data when target month changes
  const fetchTargets = useCallback(async () => {
    setTargetsLoading(true);
    try {
      const data = await api.salesTargets({ year: targetYear, month: targetMonth });
      setTargets(data);
    } catch {
      setTargets([]);
    } finally {
      setTargetsLoading(false);
    }
  }, [targetYear, targetMonth]);

  // Fetch portal daily breakdown when a specific portal is selected
  const fetchPortalDaily = useCallback(async () => {
    if (!portalId) { setDailyData(null); return; }
    setDailyLoading(true);
    try {
      const portalName = portals.find(p => p.id === portalId)?.name;
      const data = await api.portalDaily({
        ...(portalName   ? { portal: portalName }       : {}),
        ...(startDate    ? { start_date: startDate }    : {}),
        ...(endDate      ? { end_date: endDate }        : {}),
      });
      setDailyData(data);
    } catch {
      setDailyData(null);
    } finally {
      setDailyLoading(false);
    }
  }, [portalId, portals, startDate, endDate]);

  useEffect(() => { fetchMain(); },         [fetchMain]);
  useEffect(() => { fetchTargets(); },      [fetchTargets]);
  useEffect(() => { fetchPortalDaily(); },  [fetchPortalDaily]);

  const totalRevenue = summary?.total_revenue ?? 0;
  const productCount = byProduct.length;

  return (
    <main className="min-h-screen bg-zinc-950 p-6 space-y-6">
      {/* Header */}
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-zinc-50">Sales Analytics</h1>
          <p className="text-sm text-zinc-500 mt-0.5">
            Revenue, units, and category breakdown across all portals
          </p>
        </div>
        <nav className="flex gap-4 text-sm font-medium">
          <a href="/dashboard"              className="text-zinc-500 hover:text-zinc-200 transition-colors">Overview</a>
          <a href="/dashboard/sales"        className="text-orange-400 border-b border-orange-400 pb-0.5">Sales</a>
          <a href="/dashboard/inventory"    className="text-zinc-500 hover:text-zinc-200 transition-colors">Inventory</a>
          <a href="/dashboard/upload"       className="text-zinc-500 hover:text-zinc-200 transition-colors">Upload</a>
        </nav>
      </header>

      {/* Filters */}
      <SalesFilters portals={portals} />

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/30 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* KPI strip */}
      {loading || !summary ? (
        <KpiSkeleton />
      ) : (
        <KpiStrip summary={summary} productCount={productCount} />
      )}

      {/* Revenue trend */}
      {loading ? (
        <ChartSkeleton h={320} />
      ) : (
        <RevenueTrend data={trend} />
      )}

      {/* Portal breakdown */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <ChartSkeleton h={360} />
          <ChartSkeleton h={360} />
        </div>
      ) : (
        <PortalBreakdown data={byPortal} />
      )}

      {/* Category chart */}
      {loading ? (
        <ChartSkeleton h={260} />
      ) : (
        <CategoryChart data={byCategory} />
      )}

      {/* Target achievement */}
      {targetsLoading ? (
        <ChartSkeleton h={220} />
      ) : (
        <TargetAchievementPanel
          data={targets}
          year={targetYear}
          month={targetMonth}
          onMonthChange={(y, m) => { setTargetYear(y); setTargetMonth(m); }}
        />
      )}

      {/* Product table */}
      {loading ? (
        <ChartSkeleton h={400} />
      ) : (
        <ProductTable data={byProduct} totalRevenue={totalRevenue} />
      )}

      {/* Daily units breakdown (visible only when a portal is selected) */}
      <PortalDailyTable
        data={dailyData}
        loading={dailyLoading}
        portalSelected={!!portalId}
      />
    </main>
  );
}

// ─── Page export with Suspense boundary ──────────────────────────────────────
export default function SalesDashboardPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-zinc-950 p-6 space-y-6">
          <div className="h-8 w-48 rounded bg-zinc-800 animate-pulse" />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-28 rounded-xl bg-zinc-800 animate-pulse" />
            ))}
          </div>
          <div className="h-72 rounded-xl bg-zinc-800 animate-pulse" />
        </main>
      }
    >
      <SalesContent />
    </Suspense>
  );
}
