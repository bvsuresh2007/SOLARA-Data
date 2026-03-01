"use client";

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
  { label: "7D",     days: 7 },
  { label: "30D",    days: 30 },
  { label: "3M",     months: 3 },
  { label: "This M", thisMonth: true },
  { label: "Last M", lastMonth: true },
  { label: "All",    clear: true },
] as const;

interface Props {
  portals: Portal[];
}

export function SalesFilters({ portals }: Props) {
  const router = useRouter();
  const params = useSearchParams();
  const today = new Date();
  const yesterday = subDays(today, 1);

  const startDate   = params.get("start_date");
  const endDate     = params.get("end_date");
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
    } else if ("thisMonth" in preset) {
      push({
        start_date: format(startOfMonth(today), "yyyy-MM-dd"),
        end_date:   format(today, "yyyy-MM-dd"),
      });
    } else if ("lastMonth" in preset) {
      const lastMonth = subMonths(today, 1);
      push({
        start_date: format(startOfMonth(lastMonth), "yyyy-MM-dd"),
        end_date:   format(endOfMonth(lastMonth), "yyyy-MM-dd"),
      });
    } else {
      // Use yesterday as end date — today's data is typically incomplete
      // and would make growth comparisons look artificially negative.
      const end = format(yesterday, "yyyy-MM-dd");
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
            : "thisMonth" in preset
            ? startDate === format(startOfMonth(today), "yyyy-MM-dd") && endDate === format(today, "yyyy-MM-dd")
            : "lastMonth" in preset
            ? (() => {
                const lm = subMonths(today, 1);
                return startDate === format(startOfMonth(lm), "yyyy-MM-dd")
                    && endDate   === format(endOfMonth(lm),   "yyyy-MM-dd");
              })()
            : (() => {
                if (!startDate || !endDate) return false;
                const expectedEnd = format(yesterday, "yyyy-MM-dd");
                if (endDate !== expectedEnd) return false;
                const expectedStart = "months" in preset
                  ? format(subMonths(today, preset.months), "yyyy-MM-dd")
                  : format(subDays(today, preset.days), "yyyy-MM-dd");
                return startDate === expectedStart;
              })();
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
          onChange={(e) => push({ start_date: e.target.value || null })}
          className="h-8 w-36 bg-zinc-800 border-zinc-700 text-zinc-300 text-xs [color-scheme:dark]"
        />
        <span className="text-zinc-600">to</span>
        <Input
          type="date"
          value={endDate ?? ""}
          onChange={(e) => push({ end_date: e.target.value || null })}
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
