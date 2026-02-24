"use client";

import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SalesByDimension } from "@/lib/api";

const COLORS = [
  "#f97316", // orange  — Swiggy
  "#3b82f6", // blue    — Blinkit
  "#22c55e", // green   — Amazon
  "#a855f7", // purple  — Zepto
  "#eab308", // yellow  — Flipkart
  "#ec4899", // pink    — Myntra
  "#71717a", // zinc    — others
];

function fmtRevenue(v: number): string {
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(1)}Cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)}L`;
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(0)}K`;
  return `₹${v}`;
}

interface Props {
  data: SalesByDimension[];
}

export function PortalBreakdown({ data }: Props) {
  const total = data.reduce((s, d) => s + d.total_revenue, 0);
  const sorted = [...data].sort((a, b) => b.total_revenue - a.total_revenue);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      {/* Donut */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Revenue Share</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={sorted}
                dataKey="total_revenue"
                nameKey="dimension_name"
                cx="50%"
                cy="50%"
                innerRadius={55}
                outerRadius={85}
                paddingAngle={2}
              >
                {sorted.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: "#18181b",
                  border: "1px solid #3f3f46",
                  borderRadius: "8px",
                  fontSize: "12px",
                }}
                formatter={(v: number, name: string) => [
                  `${fmtRevenue(v)} (${total > 0 ? ((v / total) * 100).toFixed(1) : 0}%)`,
                  name,
                ]}
              />
            </PieChart>
          </ResponsiveContainer>
          {/* Legend */}
          <div className="mt-3 space-y-1.5">
            {sorted.map((d, i) => (
              <div key={d.dimension_id} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span
                    className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{ backgroundColor: COLORS[i % COLORS.length] }}
                  />
                  <span className="text-zinc-400">{d.dimension_name}</span>
                </div>
                <span className="text-zinc-300 font-medium">
                  {total > 0 ? ((d.total_revenue / total) * 100).toFixed(1) : 0}%
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Horizontal bar */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Revenue by Portal</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={Math.max(200, sorted.length * 44)}>
            <BarChart
              data={sorted}
              layout="vertical"
              margin={{ top: 0, right: 70, left: 10, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" horizontal={false} />
              <XAxis
                type="number"
                tickFormatter={fmtRevenue}
                tick={{ fill: "#71717a", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                type="category"
                dataKey="dimension_name"
                tick={{ fill: "#a1a1aa", fontSize: 12 }}
                axisLine={false}
                tickLine={false}
                width={70}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#18181b",
                  border: "1px solid #3f3f46",
                  borderRadius: "8px",
                  fontSize: "12px",
                }}
                formatter={(v: number) => [fmtRevenue(v), "Revenue"]}
                cursor={{ fill: "#27272a" }}
              />
              <Bar dataKey="total_revenue" radius={[0, 4, 4, 0]} label={{ position: "right", formatter: fmtRevenue, fill: "#71717a", fontSize: 11 }}>
                {sorted.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}
