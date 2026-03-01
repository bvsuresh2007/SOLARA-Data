"use client";

import { useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { format, subDays, subMonths, startOfMonth, endOfMonth } from "date-fns";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { Portal } from "@/lib/api";
import { AMAInput } from "@/components/sales/ama-input";

const PRESETS = [
  { label: "7D",     key: "7d",     days: 7 },
  { label: "30D",    key: "30d",    days: 30 },
  { label: "3M",     key: "3m",     months: 3 },
  { label: "This M", key: "this_m", thisMonth: true },
  { label: "Last M", key: "last_m", lastMonth: true },
  { label: "All",    key: "all",    clear: true },
] as const;

interface Props {
  portals: Portal[];
  latestDate?: string | null;  // latest sale_date in DB (anchors presets)
}

/** Compute start/end dates for a given preset using the anchor date */
function computePresetDates(
  preset: (typeof PRESETS)[number],
  anchor: Date,
): { start: string; end: string } | null {
  if ("clear" in preset) return null;
  if ("lastMonth" in preset) {
    const lastMonth = subMonths(new Date(), 1);
    return {
      start: format(startOfMonth(lastMonth), "yyyy-MM-dd"),
      end:   format(endOfMonth(lastMonth), "yyyy-MM-dd"),
    };
  }
  if ("thisMonth" in preset) {
    return {
      start: format(startOfMonth(anchor), "yyyy-MM-dd"),
      end:   format(anchor, "yyyy-MM-dd"),
    };
  }
  // Day/month presets: anchor is the end date, start is computed back from anchor
  const end = format(anchor, "yyyy-MM-dd");
  const start = "months" in preset
    ? format(subMonths(anchor, preset.months), "yyyy-MM-dd")
    : format(subDays(anchor, preset.days - 1), "yyyy-MM-dd");
  return { start, end };
}

export function SalesFilters({ portals, latestDate }: Props) {
  const router = useRouter();
  const params = useSearchParams();
  const prevLatestRef = useRef<string | null | undefined>(undefined);

  // Anchor = latest sale_date from DB, fallback to yesterday
  const anchor = latestDate
    ? new Date(latestDate + "T00:00:00")
    : subDays(new Date(), 1);

  const startDate    = params.get("start_date");
  const endDate      = params.get("end_date");
  const activePortal = params.get("portal_id") ?? "all";
  const activePreset = params.get("preset");

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
      push({ start_date: null, end_date: null, preset: null });
      return;
    }
    const dates = computePresetDates(preset, anchor);
    if (dates) {
      push({ start_date: dates.start, end_date: dates.end, preset: preset.key });
    }
  }

  // Auto-recompute dates when latestDate changes and a preset is active
  useEffect(() => {
    if (prevLatestRef.current === undefined) {
      // First mount — don't auto-apply, just record
      prevLatestRef.current = latestDate;
      return;
    }
    if (latestDate === prevLatestRef.current) return; // no change
    prevLatestRef.current = latestDate;

    // If a preset is active in the URL, recompute its dates with new anchor
    if (activePreset && latestDate) {
      const preset = PRESETS.find(p => p.key === activePreset);
      if (preset && !("clear" in preset)) {
        const newAnchor = new Date(latestDate + "T00:00:00");
        const dates = computePresetDates(preset, newAnchor);
        if (dates) {
          push({ start_date: dates.start, end_date: dates.end, preset: activePreset });
        }
      }
    }
  }, [latestDate]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Preset buttons */}
      <div className="flex gap-1 bg-zinc-800 rounded-lg p-1">
        {PRESETS.map((preset) => {
          // Highlight if this preset's key matches the URL param
          const isActive = "clear" in preset
            ? !startDate && !endDate && !activePreset
            : activePreset === preset.key;
          return (
            <Button
              key={preset.label}
              variant="ghost"
              size="sm"
              onClick={() => applyPreset(preset)}
              className={cn(
                "h-7 px-3 text-sm rounded-md transition-colors",
                isActive
                  ? "bg-orange-500 text-white hover:bg-orange-400"
                  : "text-zinc-300 hover:bg-zinc-700 hover:text-zinc-50"
              )}
            >
              {preset.label}
            </Button>
          );
        })}
      </div>

      {/* Date range inputs */}
      <div className="flex items-center gap-2">
        <Input
          type="date"
          value={startDate ?? ""}
          onChange={(e) => push({ start_date: e.target.value || null, preset: null })}
          className="h-8 w-36 bg-zinc-800 border-zinc-700 text-zinc-300 text-xs [color-scheme:dark]"
        />
        <span className="text-zinc-600">to</span>
        <Input
          type="date"
          value={endDate ?? ""}
          onChange={(e) => push({ end_date: e.target.value || null, preset: null })}
          className="h-8 w-36 bg-zinc-800 border-zinc-700 text-zinc-300 text-xs [color-scheme:dark]"
        />
      </div>

      {/* Portal selector */}
      <Select
        value={activePortal}
        onValueChange={(v) => push({ portal_id: v === "all" ? null : v })}
      >
        <SelectTrigger className="h-8 w-40 bg-zinc-800 border-zinc-700 text-zinc-300 text-sm">
          <SelectValue placeholder="All Portals" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Portals</SelectItem>
          {portals.map((p) => (
            <SelectItem key={p.id} value={String(p.id)}>
              {p.display_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Separator + Ask Me Anything */}
      <div className="h-6 w-px bg-zinc-700" />
      <AMAInput
        startDate={startDate ?? undefined}
        endDate={endDate ?? undefined}
        portalId={activePortal !== "all" ? Number(activePortal) : undefined}
      />
    </div>
  );
}
