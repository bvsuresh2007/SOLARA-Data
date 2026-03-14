"use client";

import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SalesByCategory } from "@/lib/api";
import { fmtRevenue } from "@/lib/format";
import { CHART_COLORS, TOOLTIP_STYLE, TOOLTIP_LABEL_STYLE, TOOLTIP_ITEM_STYLE } from "@/lib/chart-colors";

interface Props {
  data: SalesByCategory[];
}

const RADIAN         = Math.PI / 180;
const PIE_CX_RATIO   = 0.33;
const LEGEND_X_RATIO = 0.58;
const ITEM_H         = 52;
const ARROW_SIZE     = 7;
const CONNECTOR_MIN  = 0.005;

function makeLabelRenderer(sorted: SalesByCategory[], total: number) {
  return function LabelRenderer({
    cx, cy, midAngle, outerRadius, fill,
    value, percent, index,
  }: {
    cx: number; cy: number; midAngle: number; outerRadius: number;
    fill: string; value: number; percent: number; index: number;
  }) {
    const svgW = Math.round(cx / PIE_CX_RATIO);
    const svgH = cy * 2;

    const dynamicItemH = Math.min(ITEM_H, Math.floor((svgH - 20) / sorted.length));

    const legX   = svgW * LEGEND_X_RATIO;
    const totalH = sorted.length * dynamicItemH;
    const topY   = (svgH - totalH) / 2;
    const itemY  = topY + index * dynamicItemH + dynamicItemH / 2;

    const name = sorted[index]?.category ?? "";

    const legendContent = (
      <>
        <circle cx={legX + 7} cy={itemY} r={5} fill={fill} />
        <text
          x={legX + 19} y={itemY - 5}
          fill="#d4d4d8" fontSize={13} fontWeight={600}
        >
          {name}
        </text>
        <text
          x={legX + 19} y={itemY + 12}
          fill="#71717a" fontSize={12}
        >
          {fmtRevenue(value)} &middot; {(percent * 100).toFixed(1)}%
        </text>
      </>
    );

    if (percent < CONNECTOR_MIN) {
      return <g>{legendContent}</g>;
    }

    const cos = Math.cos(-midAngle * RADIAN);
    const sin = Math.sin(-midAngle * RADIAN);
    const sx  = cx + outerRadius * cos;
    const sy  = cy + outerRadius * sin;

    const ex  = legX - 10;
    const ey  = itemY;
    const cpx = sx + (ex - sx) * 0.55;

    return (
      <g>
        <path
          d={`M ${sx},${sy} C ${cpx},${sy} ${cpx},${ey} ${ex},${ey}`}
          stroke={fill}
          strokeWidth={1.5}
          fill="none"
          opacity={0.5}
        />
        <polygon
          points={`
            ${ex + ARROW_SIZE},${ey}
            ${ex},${ey - ARROW_SIZE * 0.45}
            ${ex},${ey + ARROW_SIZE * 0.45}
          `}
          fill={fill}
          opacity={0.8}
        />
        {legendContent}
      </g>
    );
  };
}

export function CategoryBreakdown({ data }: Props) {
  const total  = data.reduce((s, d) => s + d.total_revenue, 0);
  const sorted = [...data].sort((a, b) => b.total_revenue - a.total_revenue);

  const renderLabel = makeLabelRenderer(sorted, total);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Category Share</CardTitle>
      </CardHeader>
      <CardContent className="p-0 pb-4">
        <ResponsiveContainer width="100%" height={480}>
          <PieChart>
            <Pie
              data={sorted}
              dataKey="total_revenue"
              nameKey="category"
              cx={`${Math.round(PIE_CX_RATIO * 100)}%`}
              cy="50%"
              innerRadius={85}
              outerRadius={148}
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
      </CardContent>
    </Card>
  );
}
