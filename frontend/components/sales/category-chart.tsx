"use client";

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SalesByCategory } from "@/lib/api";

function fmtRevenue(v: number): string {
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(1)}Cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)}L`;
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(0)}K`;
  return `₹${v}`;
}

const CAT_COLORS = ["#f97316", "#3b82f6", "#22c55e", "#a855f7", "#eab308", "#ec4899", "#71717a"];

interface Props {
  data: SalesByCategory[];
}

export function CategoryChart({ data }: Props) {
  const sorted = [...data].sort((a, b) => b.total_revenue - a.total_revenue);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Category Breakdown</CardTitle>
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
              contentStyle={{
                backgroundColor: "#18181b",
                border: "1px solid #3f3f46",
                borderRadius: "8px",
                fontSize: "12px",
              }}
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
                <Cell key={i} fill={CAT_COLORS[i % CAT_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
