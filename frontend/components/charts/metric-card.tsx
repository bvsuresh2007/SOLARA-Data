"use client";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  value: string;
  highlight?: boolean;
  subtext?: string;
}

export default function MetricCard({ label, value, highlight = false, subtext }: MetricCardProps) {
  return (
    <Card className={cn(highlight && "border-red-800 bg-red-950/30")}>
      <CardContent className="pt-6">
        <p className={cn(
          "text-xs font-medium uppercase tracking-wide",
          highlight ? "text-red-400" : "text-zinc-500"
        )}>
          {label}
        </p>
        <p className={cn(
          "text-2xl font-bold mt-1",
          highlight ? "text-red-400" : "text-zinc-100"
        )}>
          {value}
        </p>
        {subtext && <p className="text-xs text-zinc-600 mt-1">{subtext}</p>}
      </CardContent>
    </Card>
  );
}
