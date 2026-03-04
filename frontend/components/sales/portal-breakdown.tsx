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

const RADIAN          = Math.PI / 180;
const PIE_CX_RATIO    = 0.33;   // donut center at 33% from left
const LEGEND_X_RATIO  = 0.58;   // legend column starts at 58% of SVG width
const ITEM_H          = 46;     // px per legend row
const ARROW_SIZE      = 7;      // arrowhead size in px
const CONNECTOR_MIN   = 0.005;  // draw connector only for slices ≥ 0.5%

/* ── Label + connector renderer (runs inside Recharts SVG per slice) ─────── */

function makeLabelRenderer(sorted: SalesByDimension[], total: number) {
  return function LabelRenderer({
    cx, cy, midAngle, outerRadius, fill,
    value, percent, index,
  }: {
    cx: number; cy: number; midAngle: number; outerRadius: number;
    fill: string; value: number; percent: number; index: number;
  }) {
    // Derive full SVG size from the known cx/cy ratios
    const svgW = Math.round(cx / PIE_CX_RATIO);
    const svgH = cy * 2;

    // Shrink row height if many items so legend always fits inside SVG
    const dynamicItemH = Math.min(ITEM_H, Math.floor((svgH - 20) / sorted.length));

    const legX   = svgW * LEGEND_X_RATIO;
    const totalH = sorted.length * dynamicItemH;
    const topY   = (svgH - totalH) / 2;
    const itemY  = topY + index * dynamicItemH + dynamicItemH / 2;

    const name = sorted[index]?.dimension_name ?? "";

    // Legend dot + text (always rendered for every slice)
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

    // No connector for very small slices — just show the legend entry
    if (percent < CONNECTOR_MIN) {
      return <g>{legendContent}</g>;
    }

    // Outer-edge start point on the slice
    const cos = Math.cos(-midAngle * RADIAN);
    const sin = Math.sin(-midAngle * RADIAN);
    const sx  = cx + outerRadius * cos;
    const sy  = cy + outerRadius * sin;

    // Arrow tip — just to the left of the legend dot
    const ex = legX - 10;
    const ey = itemY;

    // Cubic bezier: leave slice horizontally, arrive at legend horizontally
    const cpx = sx + (ex - sx) * 0.55;

    return (
      <g>
        {/* Curved connector line */}
        <path
          d={`M ${sx},${sy} C ${cpx},${sy} ${cpx},${ey} ${ex},${ey}`}
          stroke={fill}
          strokeWidth={1.5}
          fill="none"
          opacity={0.5}
        />
        {/* Arrowhead pointing right into legend */}
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

/* ── Component ──────────────────────────────────────────────────────────────── */

export function PortalBreakdown({ data }: Props) {
  const total  = data.reduce((s, d) => s + d.total_revenue, 0);
  const sorted = [...data].sort((a, b) => b.total_revenue - a.total_revenue);

  const renderLabel = makeLabelRenderer(sorted, total);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Revenue Share</CardTitle>
      </CardHeader>
      <CardContent className="p-0 pb-4">
        <ResponsiveContainer width="100%" height={480}>
          <PieChart>
            <Pie
              data={sorted}
              dataKey="total_revenue"
              nameKey="dimension_name"
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
