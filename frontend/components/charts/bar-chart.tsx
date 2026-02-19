"use client";

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { formatCurrency, formatNumber } from "@/lib/utils";

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

  if (horizontal) {
    return (
      <ResponsiveContainer width="100%" height={data.length * 28 + 40}>
        <BarChart data={data} layout="vertical" margin={{ left: 100 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" tickFormatter={fmt} tick={{ fontSize: 11 }} />
          <YAxis dataKey="name" type="category" tick={{ fontSize: 11 }} width={100} />
          <Tooltip formatter={(v: number) => [fmt(v), label]} />
          <Bar dataKey={dataKey} fill={color} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ bottom: 24 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-20} textAnchor="end" />
        <YAxis tickFormatter={fmt} tick={{ fontSize: 11 }} />
        <Tooltip formatter={(v: number) => [fmt(v), label]} />
        <Bar dataKey={dataKey} fill={color} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
