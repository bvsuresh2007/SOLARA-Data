"use client";

import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SalesByDimension } from "@/lib/api";
import { fmtRevenue } from "@/lib/format";
import { CHART_COLORS, TOOLTIP_STYLE, TOOLTIP_LABEL_STYLE, TOOLTIP_ITEM_STYLE } from "@/lib/chart-colors";

interface Props {
  data: SalesByDimension[];
}

const RADIAN = Math.PI / 180;

function renderLabel({
  cx, cy, midAngle, innerRadius, outerRadius, value, percent,
}: {
  cx: number; cy: number; midAngle: number;
  innerRadius: number; outerRadius: number;
  value: number; percent: number;
}) {
  // Only show label on slices large enough (>= 4%)
  if (percent < 0.04) return null;
  const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);
  return (
    <text x={x} y={y} textAnchor="middle" dominantBaseline="central" fontSize={10} fill="#fff" fontWeight={600}>
      {fmtRevenue(value)}
    </text>
  );
}

export function PortalBreakdown({ data }: Props) {
  const total = data.reduce((s, d) => s + d.total_revenue, 0);
  const sorted = [...data].sort((a, b) => b.total_revenue - a.total_revenue);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Revenue Share</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={280}>
          <PieChart>
            <Pie
              data={sorted}
              dataKey="total_revenue"
              nameKey="dimension_name"
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={110}
              paddingAngle={2}
              label={renderLabel}
              labelLine={false}
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
                {fmtRevenue(d.total_revenue)} &middot; {total > 0 ? ((d.total_revenue / total) * 100).toFixed(1) : 0}%
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
