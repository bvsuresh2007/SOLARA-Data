"use client";

import { useState, useMemo } from "react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { format, startOfWeek, parseISO } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { SalesTrend } from "@/lib/api";

type Granularity = "day" | "week" | "month";

interface Props {
  data: SalesTrend[];
}

function aggregate(data: SalesTrend[], g: Granularity): SalesTrend[] {
  if (g === "day") return data;
  const map = new Map<string, { revenue: number; quantity: number }>();
  for (const d of data) {
    const dt = parseISO(d.date);
    const key =
      g === "week"
        ? format(startOfWeek(dt, { weekStartsOn: 1 }), "yyyy-MM-dd")
        : format(dt, "yyyy-MM");
    const prev = map.get(key) ?? { revenue: 0, quantity: 0 };
    map.set(key, {
      revenue: prev.revenue + d.total_revenue,
      quantity: prev.quantity + d.total_quantity,
    });
  }
  return Array.from(map.entries()).map(([date, v]) => ({
    date,
    total_revenue: v.revenue,
    total_quantity: v.quantity,
    avg_asp: v.quantity > 0 ? v.revenue / v.quantity : 0,
  }));
}

function tickLabel(dateStr: string, g: Granularity): string {
  const dt = parseISO(dateStr);
  if (g === "month") return format(dt, "MMM yy");
  return format(dt, "d MMM");
}

function fmtRevenue(v: number): string {
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(1)}Cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)}L`;
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(0)}K`;
  return `₹${v}`;
}

const GRANULARITIES: { key: Granularity; label: string }[] = [
  { key: "day",   label: "Day" },
  { key: "week",  label: "Week" },
  { key: "month", label: "Month" },
];

export function RevenueTrend({ data }: Props) {
  const [gran, setGran] = useState<Granularity>("day");
  const chartData = useMemo(() => aggregate(data, gran), [data, gran]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-base">Revenue Trend</CardTitle>
        <div className="flex gap-1 bg-zinc-800 rounded-lg p-1">
          {GRANULARITIES.map(({ key, label }) => (
            <Button
              key={key}
              variant="ghost"
              size="sm"
              onClick={() => setGran(key)}
              className={cn(
                "h-7 px-3 text-xs rounded-md transition-colors",
                gran === key
                  ? "bg-orange-500 text-white hover:bg-orange-400"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-transparent"
              )}
            >
              {label}
            </Button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
            <defs>
              <linearGradient id="revenueGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#f97316" stopOpacity={0.35} />
                <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={(v) => tickLabel(v, gran)}
              tick={{ fill: "#71717a", fontSize: 11 }}
              axisLine={{ stroke: "#3f3f46" }}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tickFormatter={fmtRevenue}
              tick={{ fill: "#71717a", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              width={65}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#18181b",
                border: "1px solid #3f3f46",
                borderRadius: "8px",
                fontSize: "12px",
              }}
              labelStyle={{ color: "#a1a1aa", marginBottom: 4 }}
              itemStyle={{ color: "#f97316" }}
              formatter={(v: number) => [fmtRevenue(v), "Revenue"]}
              labelFormatter={(v) => tickLabel(v, gran)}
            />
            <Area
              type="monotone"
              dataKey="total_revenue"
              stroke="#f97316"
              strokeWidth={2}
              fill="url(#revenueGrad)"
              dot={false}
              activeDot={{ r: 4, fill: "#f97316" }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
