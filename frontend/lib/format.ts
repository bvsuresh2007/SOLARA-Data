/**
 * Shared INR revenue formatter used across all sales components.
 * ₹1.23 Cr / ₹1.23 L / ₹1.2 K / ₹999
 */
export function fmtRevenue(v: number): string {
  if (v < 0) return `-${fmtRevenue(-v)}`;
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`;
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(1)} K`;
  return `₹${Math.round(v)}`;
}
