"use client";

interface MetricCardProps {
  label: string;
  value: string;
  highlight?: boolean;
  subtext?: string;
}

export default function MetricCard({ label, value, highlight = false, subtext }: MetricCardProps) {
  return (
    <div
      className={`rounded-xl border p-4 ${
        highlight
          ? "bg-red-950/30 border-red-800"
          : "bg-zinc-900 border-zinc-800"
      }`}
    >
      <p className={`text-xs font-medium uppercase tracking-wide ${highlight ? "text-red-400" : "text-zinc-500"}`}>
        {label}
      </p>
      <p className={`text-2xl font-bold mt-1 ${highlight ? "text-red-400" : "text-zinc-100"}`}>
        {value}
      </p>
      {subtext && <p className="text-xs text-zinc-600 mt-1">{subtext}</p>}
    </div>
  );
}
