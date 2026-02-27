"use client";

import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SalesByDimension } from "@/lib/api";
import { fmtRevenue } from "@/lib/format";
import { CHART_COLORS, TOOLTIP_STYLE, TOOLTIP_LABEL_STYLE, TOOLTIP_ITEM_STYLE } from "@/lib/chart-colors";

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
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelStyle={TOOLTIP_LABEL_STYLE}
                itemStyle={TOOLTIP_ITEM_STYLE}
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
                    style={{ backgroundColor: CHART_COLORS[i % CHART_COLORS.length] }}
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
                contentStyle={TOOLTIP_STYLE}
                labelStyle={TOOLTIP_LABEL_STYLE}
                itemStyle={TOOLTIP_ITEM_STYLE}
                formatter={(v: number) => [fmtRevenue(v), "Revenue"]}
                cursor={{ fill: "#27272a" }}
              />
              <Bar dataKey="total_revenue" radius={[0, 4, 4, 0]} label={{ position: "right", formatter: fmtRevenue, fill: "#71717a", fontSize: 11 }}>
                {sorted.map((_, i) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}
