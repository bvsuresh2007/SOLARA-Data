"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { format, subDays, subMonths } from "date-fns";
import type { Portal } from "@/lib/api";

const PRESETS = [
  { label: "7D",  days: 7 },
  { label: "30D", days: 30 },
  { label: "3M",  months: 3 },
  { label: "6M",  months: 6 },
  { label: "All", clear: true },
] as const;

interface Props {
  portals: Portal[];
}

export function SalesFilters({ portals }: Props) {
  const router = useRouter();
  const params = useSearchParams();
  const today = new Date();

  const startDate = params.get("start_date");
  const endDate   = params.get("end_date");
  const activePortal = params.get("portal_id") ?? "all";

  function push(updates: Record<string, string | null>) {
    const p = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(updates)) {
      if (v === null) p.delete(k);
      else p.set(k, v);
    }
    router.push(`?${p.toString()}`);
  }

  function applyPreset(preset: (typeof PRESETS)[number]) {
    if ("clear" in preset) {
      push({ start_date: null, end_date: null });
    } else {
      const end = format(today, "yyyy-MM-dd");
      const start = "months" in preset
        ? format(subMonths(today, preset.months), "yyyy-MM-dd")
        : format(subDays(today, preset.days), "yyyy-MM-dd");
      push({ start_date: start, end_date: end });
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Preset buttons */}
      <div className="flex gap-1 bg-zinc-800 rounded-lg p-1">
        {PRESETS.map((preset) => {
          const isActive = "clear" in preset
            ? !startDate && !endDate
            : (() => {
                if (!startDate || !endDate) return false;
                const expectedEnd = format(today, "yyyy-MM-dd");
                if (endDate !== expectedEnd) return false;
                const expectedStart = "months" in preset
                  ? format(subMonths(today, preset.months), "yyyy-MM-dd")
                  : format(subDays(today, preset.days), "yyyy-MM-dd");
                return startDate === expectedStart;
              })();
          return (
            <button
              key={preset.label}
              onClick={() => applyPreset(preset)}
              className={`px-3 py-1 text-sm rounded-md transition-colors ${
                isActive
                  ? "bg-orange-500 text-white"
                  : "text-zinc-300 hover:bg-zinc-700 hover:text-zinc-50"
              }`}
            >
              {preset.label}
            </button>
          );
        })}
      </div>

      {/* Date range inputs */}
      <div className="flex items-center gap-2 text-sm text-zinc-400">
        <input
          type="date"
          value={startDate ?? ""}
          onChange={(e) => push({ start_date: e.target.value || null })}
          className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-300 text-xs [color-scheme:dark]"
        />
        <span className="text-zinc-600">→</span>
        <input
          type="date"
          value={endDate ?? ""}
          onChange={(e) => push({ end_date: e.target.value || null })}
          className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-300 text-xs [color-scheme:dark]"
        />
      </div>

      {/* Portal selector */}
      <select
        value={activePortal}
        onChange={(e) =>
          push({ portal_id: e.target.value === "all" ? null : e.target.value })
        }
        className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-300 cursor-pointer"
      >
        <option value="all">All Portals</option>
        {portals.map((p) => (
          <option key={p.id} value={String(p.id)}>
            {p.display_name}
          </option>
        ))}
      </select>
    </div>
  );
}
