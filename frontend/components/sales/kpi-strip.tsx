"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { SalesSummary } from "@/lib/api";
import { fmtRevenue } from "@/lib/format";

function fmtNum(value: number): string {
  return new Intl.NumberFormat("en-IN").format(Math.round(value));
}

interface Props {
  summary: SalesSummary;
  productCount: number;
}

export function KpiStrip({ summary, productCount }: Props) {
  const asp =
    summary.total_quantity > 0
      ? summary.total_revenue / summary.total_quantity
      : 0;

  const kpis = [
    { label: "Gross Revenue", value: fmtRevenue(summary.total_revenue), accent: true },
    { label: "Units Sold",    value: fmtNum(summary.total_quantity) },
    { label: "Avg ASP",       value: fmtRevenue(asp) },
    { label: "Active SKUs",   value: fmtNum(productCount) },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {kpis.map((kpi) => (
        <Card key={kpi.label}>
          <CardContent className="pt-6">
            <p className="text-xs text-zinc-500 mb-2 uppercase tracking-wider">
              {kpi.label}
            </p>
            <p
              className={`text-2xl font-bold ${
                kpi.accent ? "text-orange-400" : "text-zinc-50"
              }`}
            >
              {kpi.value}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
