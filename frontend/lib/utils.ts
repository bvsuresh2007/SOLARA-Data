import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const _inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const _num = new Intl.NumberFormat("en-IN");

export function formatCurrency(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_00_00_000) {                          // ≥ 1 Cr
    const cr = abs / 1_00_00_000;
    return `${sign}₹${cr % 1 === 0 ? cr.toFixed(0) : cr.toFixed(2)} Cr`;
  }
  if (abs >= 1_00_000) {                             // ≥ 1 L
    const lakh = abs / 1_00_000;
    return `${sign}₹${lakh % 1 === 0 ? lakh.toFixed(0) : lakh.toFixed(2)} L`;
  }
  return _inr.format(value);
}

export function formatNumber(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_00_00_000) {
    const cr = abs / 1_00_00_000;
    return `${sign}${cr % 1 === 0 ? cr.toFixed(0) : cr.toFixed(2)} Cr`;
  }
  if (abs >= 1_00_000) {
    const lakh = abs / 1_00_000;
    return `${sign}${lakh % 1 === 0 ? lakh.toFixed(0) : lakh.toFixed(2)} L`;
  }
  return _num.format(value);
}

export function formatPct(value: number, decimals = 1): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(decimals)}%`;
}
