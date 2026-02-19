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
          ? "bg-red-50 border-red-200"
          : "bg-white border-gray-200"
      }`}
    >
      <p className={`text-xs font-medium uppercase tracking-wide ${highlight ? "text-red-500" : "text-gray-500"}`}>
        {label}
      </p>
      <p className={`text-2xl font-bold mt-1 ${highlight ? "text-red-700" : "text-gray-900"}`}>
        {value}
      </p>
      {subtext && <p className="text-xs text-gray-400 mt-1">{subtext}</p>}
    </div>
  );
}
