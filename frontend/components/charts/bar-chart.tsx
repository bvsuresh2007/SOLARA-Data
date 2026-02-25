"use client";

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { formatCurrency, formatNumber } from "@/lib/utils";
import { TOOLTIP_STYLE } from "@/lib/chart-colors";

interface DataPoint { name: string; value: number }

interface SalesBarChartProps {
  data: DataPoint[];
  dataKey?: string;
  label?: string;
  color?: string;
  horizontal?: boolean;
}

export default function SalesBarChart({
  data,
  dataKey = "value",
  label = "Value",
  color = "#f97316",
  horizontal = false,
}: SalesBarChartProps) {
  const fmt = (v: number) =>
    label.includes("₹") ? formatCurrency(v) : formatNumber(v);

  const axisStyle = { fontSize: 11, fill: "#71717a" };
  const gridColor = "#3f3f46";

  if (horizontal) {
    return (
      <ResponsiveContainer width="100%" height={data.length * 28 + 40}>
        <BarChart data={data} layout="vertical" margin={{ left: 100 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke={gridColor} />
          <XAxis type="number" tickFormatter={fmt} tick={axisStyle} />
          <YAxis dataKey="name" type="category" tick={axisStyle} width={100} />
          <Tooltip formatter={(v: number) => [fmt(v), label]} contentStyle={TOOLTIP_STYLE} />
          <Bar dataKey={dataKey} fill={color} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ bottom: 24 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridColor} />
        <XAxis dataKey="name" tick={axisStyle} angle={-20} textAnchor="end" />
        <YAxis tickFormatter={fmt} tick={axisStyle} />
        <Tooltip formatter={(v: number) => [fmt(v), label]} contentStyle={TOOLTIP_STYLE} />
        <Bar dataKey={dataKey} fill={color} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
