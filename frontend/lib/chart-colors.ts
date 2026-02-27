/** Shared Recharts colour constants — edit once, applies across all charts */

export const CHART_COLORS = [
  "#f97316", // orange  — Swiggy / brand
  "#3b82f6", // blue    — Blinkit
  "#22c55e", // green   — Amazon
  "#a855f7", // purple  — Zepto
  "#06b6d4", // cyan    — EasyEcom
  "#eab308", // yellow  — Flipkart
  "#ec4899", // pink    — Myntra
  "#71717a", // zinc    — others
] as const;

export const TOOLTIP_STYLE = {
  backgroundColor: "#18181b",
  border: "1px solid #3f3f46",
  borderRadius: "8px",
  fontSize: "12px",
} as const;
