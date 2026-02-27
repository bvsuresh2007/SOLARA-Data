"use client";

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SalesByCategory } from "@/lib/api";
import { fmtRevenue } from "@/lib/format";
import { CHART_COLORS, TOOLTIP_STYLE } from "@/lib/chart-colors";

interface Props {
  data: SalesByCategory[];
}

export function CategoryChart({ data }: Props) {
  const sorted = [...data].sort((a, b) => b.total_revenue - a.total_revenue);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Sub-category Breakdown</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={Math.max(180, sorted.length * 48)}>
          <BarChart
            data={sorted}
            layout="vertical"
            margin={{ top: 0, right: 80, left: 10, bottom: 0 }}
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
              dataKey="category"
              tick={{ fill: "#a1a1aa", fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              width={150}
            />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              formatter={(v: number, _: string, item) => {
                const p = item.payload as SalesByCategory | undefined;
                return [`${fmtRevenue(v)}${p ? ` · ${p.product_count} SKUs` : ""}`, "Revenue"];
              }}
              cursor={{ fill: "#27272a" }}
            />
            <Bar
              dataKey="total_revenue"
              radius={[0, 4, 4, 0]}
              label={{
                position: "right",
                formatter: fmtRevenue,
                fill: "#71717a",
                fontSize: 11,
              }}
            >
              {sorted.map((_, i) => (
                <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
