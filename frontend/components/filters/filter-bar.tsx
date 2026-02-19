"use client";

import type { Portal, City } from "@/lib/api";

interface FilterBarProps {
  portals: Portal[];
  cities: City[];
  onPortalChange?: (id: string) => void;
  onCityChange?: (id: string) => void;
  onDateChange?: (start: string, end: string) => void;
}

export default function FilterBar({
  portals,
  cities,
  onPortalChange,
  onCityChange,
  onDateChange,
}: FilterBarProps) {
  return (
    <div className="flex flex-wrap gap-3 items-center bg-white rounded-xl border border-gray-200 px-4 py-3">
      <select
        className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500"
        onChange={e => onPortalChange?.(e.target.value)}
      >
        <option value="">All Portals</option>
        {portals.map(p => (
          <option key={p.id} value={String(p.id)}>{p.display_name}</option>
        ))}
      </select>

      <select
        className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500"
        onChange={e => onCityChange?.(e.target.value)}
      >
        <option value="">All Cities</option>
        {cities.map(c => (
          <option key={c.id} value={String(c.id)}>{c.name}</option>
        ))}
      </select>

      <div className="flex items-center gap-2">
        <label className="text-xs text-gray-500 font-medium">From</label>
        <input
          type="date"
          className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-brand-500"
          onChange={e => onDateChange?.(e.target.value, "")}
        />
        <label className="text-xs text-gray-500 font-medium">To</label>
        <input
          type="date"
          className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-brand-500"
          onChange={e => onDateChange?.("", e.target.value)}
        />
      </div>
    </div>
  );
}
