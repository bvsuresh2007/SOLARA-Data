/** Shared Recharts colour constants — edit once, applies across all charts */

export const CHART_COLORS = [
  "#f97316", // orange  — Swiggy / brand
  "#3b82f6", // blue    — Blinkit
  "#22c55e", // green   — Amazon
  "#a855f7", // purple  — Zepto
  "#eab308", // yellow  — Flipkart
  "#ec4899", // pink    — Myntra
  "#71717a", // zinc    — others
] as const;

export const TOOLTIP_STYLE = {
  backgroundColor: "#18181b",
  border: "1px solid #3f3f46",
  borderRadius: "8px",
  fontSize: "12px",
  color: "#e4e4e7",
} as const;

export const TOOLTIP_LABEL_STYLE = { color: "#a1a1aa" } as const;
export const TOOLTIP_ITEM_STYLE  = { color: "#e4e4e7" } as const;
