"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { TargetAchievement } from "@/lib/api";

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const PORTAL_COLORS: Record<string, string> = {
  Swiggy:   "bg-orange-900/40 text-orange-300",
  Blinkit:  "bg-blue-900/40 text-blue-300",
  Amazon:   "bg-green-900/40 text-green-300",
  Zepto:    "bg-purple-900/40 text-purple-300",
  Flipkart: "bg-yellow-900/40 text-yellow-300",
  Myntra:   "bg-pink-900/40 text-pink-300",
};

function fmtRevenue(v: number): string {
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`;
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(1)} K`;
  return `₹${Math.round(v)}`;
}

function achievementVariant(pct: number): "success" | "warning" | "danger" {
  if (pct >= 100) return "success";
  if (pct >= 75)  return "warning";
  return "danger";
}

interface Props {
  data: TargetAchievement[];
  year: number;
  month: number;
  onMonthChange: (year: number, month: number) => void;
}

export function TargetAchievementPanel({ data, year, month, onMonthChange }: Props) {
  function prev() {
    if (month === 1) onMonthChange(year - 1, 12);
    else onMonthChange(year, month - 1);
  }
  function next() {
    if (month === 12) onMonthChange(year + 1, 1);
    else onMonthChange(year, month + 1);
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-base">Target Achievement</CardTitle>
        <div className="flex items-center gap-2">
          <button
            onClick={prev}
            className="p-1 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <ChevronLeft size={16} />
          </button>
          <span className="text-sm text-zinc-300 min-w-[80px] text-center">
            {MONTH_NAMES[month - 1]} {year}
          </span>
          <button
            onClick={next}
            className="p-1 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <p className="text-sm text-zinc-500 text-center py-6">
            No target data for {MONTH_NAMES[month - 1]} {year}
          </p>
        ) : (
          <div className="space-y-4">
            {/* Header row */}
            <div className="grid grid-cols-[130px_1fr_90px_90px_70px] gap-3 text-xs text-zinc-500 uppercase tracking-wider pb-1 border-b border-zinc-800">
              <span>Portal</span>
              <span>Progress</span>
              <span className="text-right">Target</span>
              <span className="text-right">Actual</span>
              <span className="text-right">Achiev.</span>
            </div>
            {data.map((row) => {
              const pct = Math.min(row.achievement_pct, 100);
              const portalColor =
                Object.entries(PORTAL_COLORS).find(([k]) =>
                  row.portal_name.toLowerCase().includes(k.toLowerCase())
                )?.[1] ?? "bg-zinc-800 text-zinc-300";

              return (
                <div
                  key={row.portal_name}
                  className="grid grid-cols-[130px_1fr_90px_90px_70px] gap-3 items-center"
                >
                  {/* Portal badge */}
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium truncate ${portalColor}`}
                  >
                    {row.portal_name}
                  </span>

                  {/* Progress bar */}
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${
                          pct >= 100
                            ? "bg-green-500"
                            : pct >= 75
                            ? "bg-yellow-500"
                            : "bg-red-500"
                        }`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>

                  <span className="text-right text-xs text-zinc-400">
                    {fmtRevenue(row.target_revenue)}
                  </span>
                  <span className="text-right text-xs text-zinc-200 font-medium">
                    {fmtRevenue(row.actual_revenue)}
                  </span>

                  <div className="flex justify-end">
                    <Badge variant={achievementVariant(row.achievement_pct)}>
                      {row.achievement_pct.toFixed(0)}%
                    </Badge>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
