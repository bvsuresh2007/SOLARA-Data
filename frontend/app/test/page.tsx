"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { SalesByDimension, PortalDailyResponse } from "@/lib/api";
import { PortalBreakdown } from "@/components/sales/portal-breakdown";
import { PortalDailyTable } from "@/components/sales/portal-daily-table";

// Last 7 days ending yesterday (1-day reporting lag)
function getDateRange() {
  const today = new Date();
  const end = new Date(today);
  end.setDate(end.getDate() - 1);
  const start = new Date(end);
  start.setDate(start.getDate() - 6);
  const fmt = (d: Date) => d.toISOString().slice(0, 10);
  return { start_date: fmt(start), end_date: fmt(end) };
}

export default function TestPage() {
  const [portalData, setPortalData]   = useState<SalesByDimension[]>([]);
  const [dailyData,  setDailyData]    = useState<PortalDailyResponse | null>(null);
  const [loading,    setLoading]      = useState(true);
  const [error,      setError]        = useState<string | null>(null);

  useEffect(() => {
    const { start_date, end_date } = getDateRange();
    setLoading(true);
    Promise.allSettled([
      api.salesByPortal({ start_date, end_date }),
      api.portalDaily({ portal: "all", start_date, end_date }),
    ]).then(([portalRes, dailyRes]) => {
      if (portalRes.status === "fulfilled") setPortalData(portalRes.value as SalesByDimension[]);
      else setError((portalRes.reason as Error)?.message ?? "Failed to load portal data");

      if (dailyRes.status === "fulfilled") setDailyData(dailyRes.value as PortalDailyResponse);
      else if (!error) setError((dailyRes.reason as Error)?.message ?? "Failed to load daily data");
    }).finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { start_date, end_date } = getDateRange();

  return (
    <main className="min-h-screen bg-zinc-950 p-6 space-y-8">
      <div>
        <h1 className="text-xl font-bold text-zinc-100 mb-1">UI Preview — Test Page</h1>
        <p className="text-xs text-zinc-500">
          Live data · {start_date} → {end_date}
          {loading && " · Loading…"}
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/30 px-4 py-3 text-sm text-red-400">{error}</div>
      )}

      <section>
        <p className="text-xs text-zinc-600 uppercase tracking-wider mb-3">Revenue Share by Portal</p>
        {loading
          ? <div className="h-64 rounded-xl bg-zinc-800 animate-pulse" />
          : <PortalBreakdown data={portalData} />
        }
      </section>

      <section>
        <p className="text-xs text-zinc-600 uppercase tracking-wider mb-3">Daily Units Table — 7-day window</p>
        <PortalDailyTable data={dailyData} loading={loading} />
      </section>
    </main>
  );
}
