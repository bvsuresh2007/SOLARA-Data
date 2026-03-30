"use client";

import { useMemo, useState, useCallback } from "react";
import {
  ComposableMap, Geographies, Geography, Marker, ZoomableGroup,
} from "react-simple-maps";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SalesByDimension } from "@/lib/api";
import { fmtRevenue } from "@/lib/format";

/* ═══════════════════════════════════════════════════════════════════════════
   India Sales Map — state choropleth (left) + state bar chart (right)
   ═══════════════════════════════════════════════════════════════════════════ */

interface Props {
  data: SalesByDimension[];
}

const INDIA_TOPO = "/india-topo.json";
const INDIA_CENTER: [number, number] = [82, 22];

/* ── Known Indian state names (ALL CAPS in DB) ────────────────────────── */
const STATE_NAMES = new Set([
  "ANDHRA PRADESH", "ARUNACHAL PRADESH", "ASSAM", "BIHAR", "CHHATTISGARH",
  "CHATTISGARH", "GOA", "GUJARAT", "HARYANA", "HIMACHAL PRADESH", "JHARKHAND",
  "KARNATAKA", "KERALA", "MADHYA PRADESH", "MAHARASHTRA", "MANIPUR",
  "MEGHALAYA", "MIZORAM", "NAGALAND", "ODISHA", "PUNJAB", "RAJASTHAN",
  "SIKKIM", "TAMIL NADU", "TELANGANA", "TRIPURA", "UTTAR PRADESH",
  "UTTARAKHAND", "WEST BENGAL", "DELHI", "JAMMU & KASHMIR", "LADAKH",
  "PUDUCHERRY", "CHANDIGARH", "ANDAMAN AND NICOBAR", "DADRA AND NAGAR HAVELI",
  "DAMAN AND DIU", "LAKSHADWEEP", "NEW DELHI",
]);

/* ── City coordinates [lng, lat] ──────────────────────────────────────── */
const CITY_COORDS: Record<string, [number, number]> = {
  "mumbai": [72.878, 19.076], "delhi": [77.209, 28.614], "new delhi": [77.209, 28.614],
  "bengaluru": [77.594, 12.972], "bangalore": [77.594, 12.972],
  "hyderabad": [78.487, 17.385], "chennai": [80.270, 13.083],
  "kolkata": [88.364, 22.573], "pune": [73.856, 18.52], "ahmedabad": [72.571, 23.023],
  "jaipur": [75.787, 26.912], "lucknow": [80.947, 26.847], "agra": [78.015, 27.177],
  "varanasi": [82.991, 25.318], "kanpur": [80.332, 26.449], "prayagraj": [81.846, 25.435],
  "allahabad": [81.846, 25.435], "meerut": [77.706, 28.984], "aligarh": [78.078, 27.883],
  "bareilly": [79.432, 28.367], "moradabad": [78.773, 28.839], "gorakhpur": [83.379, 26.760],
  "mathura": [77.673, 27.492], "saharanpur": [77.541, 29.964], "muzaffarnagar": [77.707, 29.473],
  "firozabad": [78.395, 27.150], "shahjahanpur": [79.905, 27.883],
  "noida": [77.391, 28.535], "gurugram": [77.027, 28.459], "gurgaon": [77.027, 28.459],
  "ghaziabad": [77.438, 28.669], "faridabad": [77.317, 28.408], "greater noida": [77.504, 28.475],
  "gautam buddha nagar": [77.504, 28.475],
  "chandigarh": [76.779, 30.734], "dehradun": [78.032, 30.317],
  "amritsar": [74.872, 31.634], "ludhiana": [75.857, 30.901], "jalandhar": [75.576, 31.326],
  "jammu": [74.857, 32.735], "patiala": [76.387, 30.340], "bathinda": [74.951, 30.211],
  "panipat": [76.968, 29.390], "karnal": [76.990, 29.686], "ambala": [76.777, 30.378],
  "rohtak": [76.606, 28.894], "hisar": [75.723, 29.154], "sonipat": [77.016, 28.994],
  "shimla": [77.172, 31.105], "haridwar": [78.169, 29.946],
  "surat": [72.831, 21.170], "vadodara": [73.181, 22.307], "rajkot": [70.802, 22.304],
  "nashik": [73.789, 19.998], "aurangabad": [75.343, 19.876],
  "navi mumbai": [73.030, 19.037], "thane": [72.978, 19.218],
  "nagpur": [79.089, 21.146], "indore": [75.858, 22.720], "bhopal": [77.413, 23.259],
  "jodhpur": [73.049, 26.279], "udaipur": [73.713, 24.585], "kota": [75.864, 25.180],
  "panaji": [73.876, 15.380], "goa": [73.876, 15.380],
  "kolhapur": [74.234, 16.705], "solapur": [75.910, 17.659], "sangli": [74.563, 16.853],
  "palghar": [72.770, 19.694], "kalyan": [73.130, 19.244], "vasai": [72.801, 19.365],
  "bhiwandi": [73.059, 19.301], "anand": [72.929, 22.560], "gandhinagar": [72.680, 23.215],
  "bhavnagar": [72.153, 21.764], "jamnagar": [70.066, 22.471],
  "coimbatore": [76.956, 11.017], "kochi": [76.267, 9.931], "ernakulam": [76.267, 9.931],
  "visakhapatnam": [83.218, 17.687], "vijayawada": [80.648, 16.506],
  "thiruvananthapuram": [76.936, 8.524], "trivandrum": [76.936, 8.524],
  "mysuru": [76.639, 12.296], "mysore": [76.639, 12.296],
  "mangalore": [74.856, 12.914], "mangaluru": [74.856, 12.914],
  "madurai": [78.120, 9.925], "tiruchirappalli": [78.688, 10.791], "trichy": [78.688, 10.791],
  "salem": [78.146, 11.665], "tiruppur": [77.340, 11.109],
  "warangal": [79.599, 17.978], "guntur": [80.436, 16.307],
  "hubli": [75.124, 15.364], "belgaum": [74.498, 15.849], "belagavi": [74.498, 15.849],
  "kozhikode": [75.780, 11.259], "calicut": [75.780, 11.259],
  "thrissur": [76.214, 10.527], "kollam": [76.583, 8.893], "palakkad": [76.651, 10.776],
  "kottayam": [76.522, 9.591], "kannur": [75.370, 11.869], "malappuram": [76.084, 11.042],
  "tirunelveli": [77.713, 8.727], "vellore": [79.133, 12.916], "erode": [77.727, 11.341],
  "thanjavur": [79.138, 10.787], "dindigul": [77.976, 10.368], "thoothukudi": [78.136, 8.764],
  "nellore": [79.986, 14.450], "rajahmundry": [81.804, 17.005], "kakinada": [82.231, 16.960],
  "tirupati": [79.420, 13.629], "kadapa": [78.824, 14.468], "anantapur": [77.600, 14.680],
  "kurnool": [78.037, 15.828], "karimnagar": [79.128, 18.437], "nizamabad": [78.094, 18.673],
  "chengalpattu": [79.978, 12.694], "davanagere": [75.923, 14.467], "bellary": [76.386, 15.143],
  "shimoga": [75.568, 13.930], "tumkur": [77.101, 13.340], "gulbarga": [76.838, 17.329],
  "udupi": [74.746, 13.341], "hassan": [76.100, 13.008],
  "patna": [85.145, 25.612], "ranchi": [85.310, 23.345], "jamshedpur": [86.203, 22.805],
  "bhubaneswar": [85.825, 20.297], "guwahati": [91.736, 26.145],
  "raipur": [81.630, 21.252], "siliguri": [88.395, 26.727], "durgapur": [87.322, 23.553],
  "cuttack": [85.879, 20.462], "bokaro": [86.151, 23.669], "dhanbad": [86.433, 23.796],
  "muzaffarpur": [85.391, 26.121], "gaya": [84.999, 24.796], "bhagalpur": [86.992, 25.244],
  "howrah": [88.263, 22.593], "asansol": [86.953, 23.681], "kharagpur": [87.323, 22.346],
  "bilaspur": [82.145, 22.075], "durg": [81.285, 21.190], "bhilai": [81.380, 21.209],
  "sambalpur": [83.976, 21.467], "berhampur": [84.794, 19.315],
  "jorhat": [94.216, 26.757], "dibrugarh": [94.912, 27.473], "tezpur": [92.796, 26.637],
  "imphal": [93.937, 24.817], "shillong": [91.886, 25.578], "agartala": [91.276, 23.831],
};

/* ── Title case helper ────────────────────────────────────────────────── */
function titleCase(s: string): string {
  return s.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ── City name normalisation ─────────────────────────────────────────── */
const CITY_ALIASES: Record<string, string> = {
  "bangalore": "Bengaluru", "gurgaon": "Gurugram", "trivandrum": "Thiruvananthapuram",
  "calicut": "Kozhikode", "mysore": "Mysuru", "mangalore": "Mangaluru",
  "allahabad": "Prayagraj", "trichy": "Tiruchirappalli", "belgaum": "Belagavi",
  "new delhi": "Delhi", "ernakulam": "Kochi", "gautam buddha nagar": "Greater Noida",
  "kalyan": "Thane", "vasai": "Thane", "bhiwandi": "Thane",
  "howrah": "Kolkata", "palghar": "Navi Mumbai",
  "gulbarga": "Kalaburagi", "shimoga": "Shivamogga", "bellary": "Ballari", "tumkur": "Tumakuru",
};

function normalizeCityName(raw: string): string {
  const alias = CITY_ALIASES[raw.trim().toLowerCase()];
  return alias ?? titleCase(raw.trim());
}

/* ── State name normalisation ────────────────────────────────────────── */
const STATE_ALIASES: Record<string, string> = {
  "chattisgarh": "Chhattisgarh", "orissa": "Odisha", "pondicherry": "Puducherry",
  "uttaranchal": "Uttarakhand", "new delhi": "Delhi", "nct of delhi": "Delhi", "ncr": "Delhi",
  "jammu and kashmir": "Jammu & Kashmir", "jammu & kashmir": "Jammu & Kashmir", "j&k": "Jammu & Kashmir",
  "dadra and nagar haveli and daman and diu": "Dadra & Nagar Haveli",
  "dadra and nagar haveli": "Dadra & Nagar Haveli", "daman and diu": "Daman & Diu",
  "andaman and nicobar": "Andaman & Nicobar", "andaman and nicobar islands": "Andaman & Nicobar",
};

function normalizeStateName(raw: string): string {
  const alias = STATE_ALIASES[raw.trim().toLowerCase()];
  return alias ?? titleCase(raw.trim());
}

/* ── City → State mapping ────────────────────────────────────────────── */
const CITY_TO_STATE: Record<string, string> = {
  "mumbai": "Maharashtra", "pune": "Maharashtra", "nashik": "Maharashtra", "nagpur": "Maharashtra",
  "aurangabad": "Maharashtra", "navi mumbai": "Maharashtra", "thane": "Maharashtra",
  "kolhapur": "Maharashtra", "solapur": "Maharashtra", "sangli": "Maharashtra",
  "palghar": "Maharashtra", "kalyan": "Maharashtra", "vasai": "Maharashtra", "bhiwandi": "Maharashtra",
  "bengaluru": "Karnataka", "bangalore": "Karnataka", "mysuru": "Karnataka", "mysore": "Karnataka",
  "mangalore": "Karnataka", "mangaluru": "Karnataka", "hubli": "Karnataka",
  "belgaum": "Karnataka", "belagavi": "Karnataka", "davanagere": "Karnataka",
  "bellary": "Karnataka", "shimoga": "Karnataka", "tumkur": "Karnataka",
  "gulbarga": "Karnataka", "udupi": "Karnataka", "hassan": "Karnataka",
  "chennai": "Tamil Nadu", "coimbatore": "Tamil Nadu", "madurai": "Tamil Nadu",
  "tiruchirappalli": "Tamil Nadu", "trichy": "Tamil Nadu", "salem": "Tamil Nadu",
  "tiruppur": "Tamil Nadu", "vellore": "Tamil Nadu", "erode": "Tamil Nadu",
  "thanjavur": "Tamil Nadu", "dindigul": "Tamil Nadu", "thoothukudi": "Tamil Nadu",
  "tirunelveli": "Tamil Nadu", "chengalpattu": "Tamil Nadu",
  "hyderabad": "Telangana", "warangal": "Telangana", "karimnagar": "Telangana", "nizamabad": "Telangana",
  "visakhapatnam": "Andhra Pradesh", "vijayawada": "Andhra Pradesh", "guntur": "Andhra Pradesh",
  "nellore": "Andhra Pradesh", "rajahmundry": "Andhra Pradesh", "kakinada": "Andhra Pradesh",
  "tirupati": "Andhra Pradesh", "kadapa": "Andhra Pradesh", "anantapur": "Andhra Pradesh", "kurnool": "Andhra Pradesh",
  "kochi": "Kerala", "ernakulam": "Kerala", "thiruvananthapuram": "Kerala",
  "trivandrum": "Kerala", "kozhikode": "Kerala", "calicut": "Kerala",
  "thrissur": "Kerala", "kollam": "Kerala", "palakkad": "Kerala",
  "kottayam": "Kerala", "kannur": "Kerala", "malappuram": "Kerala",
  "ahmedabad": "Gujarat", "surat": "Gujarat", "vadodara": "Gujarat", "rajkot": "Gujarat",
  "anand": "Gujarat", "gandhinagar": "Gujarat", "bhavnagar": "Gujarat", "jamnagar": "Gujarat",
  "jaipur": "Rajasthan", "jodhpur": "Rajasthan", "udaipur": "Rajasthan", "kota": "Rajasthan",
  "lucknow": "Uttar Pradesh", "agra": "Uttar Pradesh", "varanasi": "Uttar Pradesh",
  "kanpur": "Uttar Pradesh", "prayagraj": "Uttar Pradesh", "allahabad": "Uttar Pradesh",
  "meerut": "Uttar Pradesh", "noida": "Uttar Pradesh", "ghaziabad": "Uttar Pradesh",
  "greater noida": "Uttar Pradesh", "gautam buddha nagar": "Uttar Pradesh",
  "aligarh": "Uttar Pradesh", "bareilly": "Uttar Pradesh", "moradabad": "Uttar Pradesh",
  "gorakhpur": "Uttar Pradesh", "mathura": "Uttar Pradesh", "saharanpur": "Uttar Pradesh",
  "muzaffarnagar": "Uttar Pradesh", "firozabad": "Uttar Pradesh", "shahjahanpur": "Uttar Pradesh",
  "delhi": "Delhi", "new delhi": "Delhi",
  "gurugram": "Haryana", "gurgaon": "Haryana", "faridabad": "Haryana",
  "panipat": "Haryana", "karnal": "Haryana", "ambala": "Haryana",
  "rohtak": "Haryana", "hisar": "Haryana", "sonipat": "Haryana",
  "amritsar": "Punjab", "ludhiana": "Punjab", "jalandhar": "Punjab",
  "patiala": "Punjab", "bathinda": "Punjab",
  "kolkata": "West Bengal", "siliguri": "West Bengal", "durgapur": "West Bengal",
  "howrah": "West Bengal", "asansol": "West Bengal", "kharagpur": "West Bengal",
  "patna": "Bihar", "muzaffarpur": "Bihar", "gaya": "Bihar", "bhagalpur": "Bihar",
  "ranchi": "Jharkhand", "jamshedpur": "Jharkhand", "bokaro": "Jharkhand", "dhanbad": "Jharkhand",
  "bhubaneswar": "Odisha", "cuttack": "Odisha", "sambalpur": "Odisha", "berhampur": "Odisha",
  "raipur": "Chhattisgarh", "bilaspur": "Chhattisgarh", "durg": "Chhattisgarh", "bhilai": "Chhattisgarh",
  "indore": "Madhya Pradesh", "bhopal": "Madhya Pradesh",
  "guwahati": "Assam", "jorhat": "Assam", "dibrugarh": "Assam", "tezpur": "Assam",
  "imphal": "Manipur", "shillong": "Meghalaya", "agartala": "Tripura",
  "chandigarh": "Chandigarh", "jammu": "Jammu & Kashmir",
  "dehradun": "Uttarakhand", "haridwar": "Uttarakhand",
  "shimla": "Himachal Pradesh", "panaji": "Goa", "goa": "Goa",
};

/* ── TopoJSON NAME_1 → our normalized state name ─────────────────────── */
const TOPO_TO_STATE: Record<string, string> = {
  "Andaman and Nicobar": "Andaman & Nicobar",
  "Andhra Pradesh": "Andhra Pradesh",
  "Arunachal Pradesh": "Arunachal Pradesh",
  "Assam": "Assam",
  "Bihar": "Bihar",
  "Chandigarh": "Chandigarh",
  "Chhattisgarh": "Chhattisgarh",
  "Dadra and Nagar Haveli": "Dadra & Nagar Haveli",
  "Daman and Diu": "Daman & Diu",
  "Delhi": "Delhi",
  "Goa": "Goa",
  "Gujarat": "Gujarat",
  "Haryana": "Haryana",
  "Himachal Pradesh": "Himachal Pradesh",
  "Jammu and Kashmir": "Jammu & Kashmir",
  "Jharkhand": "Jharkhand",
  "Karnataka": "Karnataka",
  "Kerala": "Kerala",
  "Lakshadweep": "Lakshadweep",
  "Madhya Pradesh": "Madhya Pradesh",
  "Maharashtra": "Maharashtra",
  "Manipur": "Manipur",
  "Meghalaya": "Meghalaya",
  "Mizoram": "Mizoram",
  "Nagaland": "Nagaland",
  "Orissa": "Odisha",
  "Puducherry": "Puducherry",
  "Punjab": "Punjab",
  "Rajasthan": "Rajasthan",
  "Sikkim": "Sikkim",
  "Tamil Nadu": "Tamil Nadu",
  "Tripura": "Tripura",
  "Uttar Pradesh": "Uttar Pradesh",
  "Uttaranchal": "Uttarakhand",
  "West Bengal": "West Bengal",
};

/* ── State abbreviations (2-letter codes) ─────────────────────────────── */
const STATE_ABBREV: Record<string, string> = {
  "Andaman & Nicobar": "AN", "Andhra Pradesh": "AP", "Arunachal Pradesh": "AR",
  "Assam": "AS", "Bihar": "BR", "Chandigarh": "CH", "Chhattisgarh": "CG",
  "Dadra & Nagar Haveli": "DN", "Daman & Diu": "DD", "Delhi": "DL",
  "Goa": "GA", "Gujarat": "GJ", "Haryana": "HR", "Himachal Pradesh": "HP",
  "Jammu & Kashmir": "JK", "Jharkhand": "JH", "Karnataka": "KA", "Kerala": "KL",
  "Lakshadweep": "LD", "Madhya Pradesh": "MP", "Maharashtra": "MH", "Manipur": "MN",
  "Meghalaya": "ML", "Mizoram": "MZ", "Nagaland": "NL", "Odisha": "OR",
  "Puducherry": "PY", "Punjab": "PB", "Rajasthan": "RJ", "Sikkim": "SK",
  "Tamil Nadu": "TN", "Telangana": "TS", "Tripura": "TR", "Uttar Pradesh": "UP",
  "Uttarakhand": "UK", "West Bengal": "WB",
};

/* ── State centroids [lng, lat] for label placement ───────────────────── */
const STATE_CENTROIDS: Record<string, [number, number]> = {
  "Andaman & Nicobar": [92.7, 11.7],
  "Andhra Pradesh": [79.7, 15.9],
  "Arunachal Pradesh": [94.7, 28.2],
  "Assam": [92.9, 26.2],
  "Bihar": [85.3, 25.6],
  "Chandigarh": [76.8, 30.7],
  "Chhattisgarh": [81.9, 21.3],
  "Dadra & Nagar Haveli": [73.0, 20.2],
  "Daman & Diu": [72.8, 20.4],
  "Delhi": [77.1, 28.7],
  "Goa": [74.0, 15.4],
  "Gujarat": [71.6, 22.3],
  "Haryana": [76.1, 29.1],
  "Himachal Pradesh": [77.2, 31.8],
  "Jammu & Kashmir": [75.3, 33.8],
  "Jharkhand": [85.3, 23.6],
  "Karnataka": [75.7, 15.3],
  "Kerala": [76.3, 10.5],
  "Lakshadweep": [72.6, 10.6],
  "Madhya Pradesh": [78.7, 23.5],
  "Maharashtra": [75.7, 19.7],
  "Manipur": [93.9, 24.8],
  "Meghalaya": [91.4, 25.5],
  "Mizoram": [92.9, 23.2],
  "Nagaland": [94.6, 26.2],
  "Odisha": [84.0, 20.5],
  "Puducherry": [79.8, 11.9],
  "Punjab": [75.3, 31.1],
  "Rajasthan": [73.8, 26.6],
  "Sikkim": [88.5, 27.5],
  "Tamil Nadu": [78.7, 11.1],
  "Telangana": [79.0, 18.1],
  "Tripura": [91.7, 23.7],
  "Uttar Pradesh": [80.9, 27.2],
  "Uttarakhand": [79.1, 30.1],
  "West Bengal": [87.9, 23.0],
};

/* ── Choropleth color: light-to-dark blue (like the reference) ────────── */
function choroplethColor(share: number, maxShare: number): string {
  if (share <= 0 || maxShare <= 0) return "#2a2a3d"; // dark bg for 0%
  const t = Math.min(share / maxShare, 1);
  // Interpolate from light lavender (#c4c4e8) to deep indigo (#3b30a6)
  const r = Math.round(196 - t * 137);
  const g = Math.round(196 - t * 148);
  const b = Math.round(232 - t * 66);
  return `rgb(${r},${g},${b})`;
}

/* ── Color interpolation — cyan → amber → red (for bar chart) ────────── */
function interpolateColor(t: number): string {
  if (t < 0.5) {
    const s = t * 2;
    return `rgb(${Math.round(34 + s * 211)},${Math.round(211 - s * 53)},${Math.round(238 - s * 227)})`;
  }
  const s = (t - 0.5) * 2;
  return `rgb(${Math.round(245 - s * 6)},${Math.round(158 - s * 90)},${Math.round(11 + s * 57)})`;
}

/* ══════════════════════════════════════════════════════════════════════════
   Component
   ══════════════════════════════════════════════════════════════════════════ */

export default function IndiaSalesMap({ data }: Props) {
  const [hoveredState, setHoveredState] = useState<string | null>(null);

  const { cities, states, stateMap, maxRevenue, totalCityRevenue, totalStateRevenue, maxStateRevenue, maxStateShare } = useMemo(() => {
    if (!data?.length) return { cities: [], states: [], stateMap: new Map(), maxRevenue: 0, totalCityRevenue: 0, totalStateRevenue: 0, maxStateRevenue: 0, maxStateShare: 0 };

    const stateAgg = new Map<string, { revenue: number; quantity: number }>();
    const cityEntries: typeof data = [];

    const addToState = (stateName: string, revenue: number, quantity: number) => {
      const existing = stateAgg.get(stateName);
      if (existing) {
        existing.revenue += revenue;
        existing.quantity += quantity;
      } else {
        stateAgg.set(stateName, { revenue, quantity });
      }
    };

    for (const d of data) {
      const name = d.dimension_name.trim();
      const upper = name.toUpperCase();
      const lower = name.toLowerCase();
      const isState = STATE_NAMES.has(upper);
      const hasCoords = !!(CITY_COORDS[name] ?? CITY_COORDS[lower]);

      if (isState) {
        addToState(normalizeStateName(name), d.total_revenue, d.total_quantity);
        if (hasCoords) cityEntries.push(d);
      } else {
        cityEntries.push(d);
        const parentState = CITY_TO_STATE[lower];
        if (parentState) {
          addToState(parentState, d.total_revenue, d.total_quantity);
        }
      }
    }

    const totalCityRevenue = cityEntries.reduce((s, d) => s + d.total_revenue, 0);

    // City dedup
    const cityAgg = new Map<string, { revenue: number; quantity: number; coords: [number, number] }>();
    for (const d of cityEntries) {
      const raw = d.dimension_name.trim();
      const coords = CITY_COORDS[raw] ?? CITY_COORDS[raw.toLowerCase()];
      if (!coords) continue;
      const normalized = normalizeCityName(raw);
      const existing = cityAgg.get(normalized);
      if (existing) {
        existing.revenue += d.total_revenue;
        existing.quantity += d.total_quantity;
      } else {
        cityAgg.set(normalized, { revenue: d.total_revenue, quantity: d.total_quantity, coords: coords as [number, number] });
      }
    }

    let maxRev = 0;
    const cities = Array.from(cityAgg.entries()).map(([name, v]) => {
      if (v.revenue > maxRev) maxRev = v.revenue;
      return { name, coords: v.coords, revenue: v.revenue, quantity: v.quantity, share: totalCityRevenue > 0 ? v.revenue / totalCityRevenue : 0 };
    });

    const stateList = Array.from(stateAgg.entries())
      .map(([name, v]) => ({ name, revenue: v.revenue, quantity: v.quantity }))
      .sort((a, b) => b.revenue - a.revenue);
    const totalStateRevenue = stateList.reduce((s, d) => s + d.revenue, 0);
    const maxStateRevenue = stateList.length > 0 ? stateList[0].revenue : 0;
    const statesWithShare = stateList.map((s) => ({
      ...s,
      share: totalStateRevenue > 0 ? s.revenue / totalStateRevenue : 0,
    }));
    const maxStateShare = statesWithShare.length > 0 ? statesWithShare[0].share : 0;

    // Build map for quick lookup from state name → data
    const stateMap = new Map<string, { revenue: number; quantity: number; share: number }>();
    for (const s of statesWithShare) {
      stateMap.set(s.name, { revenue: s.revenue, quantity: s.quantity, share: s.share });
    }

    return {
      cities,
      states: statesWithShare,
      stateMap,
      maxRevenue: maxRev,
      totalCityRevenue,
      totalStateRevenue,
      maxStateRevenue,
      maxStateShare,
    };
  }, [data]);

  const getStateData = useCallback((topoName: string) => {
    const normalized = TOPO_TO_STATE[topoName] ?? titleCase(topoName);
    return { name: normalized, ...(stateMap.get(normalized) ?? { revenue: 0, quantity: 0, share: 0 }) };
  }, [stateMap]);

  if (!data?.length) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-zinc-100">Sales by Geography</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-zinc-500 text-xs">No city-level data available</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* ════════════════════════════════════════════════════════════════════
         LEFT: State Choropleth Map
         ════════════════════════════════════════════════════════════════════ */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-zinc-100 flex items-center justify-between">
            <span>State-wise Sales Map</span>
            <span className="text-[10px] text-zinc-500 font-normal">
              {states.length} states &middot; {fmtRevenue(totalStateRevenue)}
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-3">
            {/* Map */}
            <div className="relative flex-1" style={{ minWidth: 0 }}>
              <ComposableMap
                projection="geoMercator"
                projectionConfig={{ center: INDIA_CENTER, scale: 700 }}
                width={440}
                height={480}
                style={{ width: "100%", height: "auto" }}
              >
                <ZoomableGroup center={INDIA_CENTER} zoom={1} minZoom={1} maxZoom={4}>
                  <Geographies geography={INDIA_TOPO}>
                    {({ geographies }) =>
                      geographies.map((geo) => {
                        const topoName = geo.properties.NAME_1 as string;
                        const sd = getStateData(topoName);
                        const abbrev = STATE_ABBREV[sd.name] ?? "";
                        const pct = (sd.share * 100).toFixed(1);
                        const isHovered = hoveredState === sd.name;
                        const centroid = STATE_CENTROIDS[sd.name];

                        return (
                          <g key={geo.rsmKey}>
                            <Geography
                              geography={geo}
                              fill={isHovered
                                ? (sd.share > 0 ? "#f97316" : "#3f3f46")
                                : choroplethColor(sd.share, maxStateShare)
                              }
                              stroke="#ffffff"
                              strokeWidth={isHovered ? 1.5 : 0.5}
                              style={{
                                default: { outline: "none", transition: "fill 0.2s, stroke-width 0.2s" },
                                hover: { outline: "none" },
                                pressed: { outline: "none" },
                              }}
                              {...{ onMouseEnter: () => setHoveredState(sd.name), onMouseLeave: () => setHoveredState(null) } as any}
                            />
                            {/* State abbreviation + % label */}
                            {centroid && (
                              <Marker coordinates={centroid}>
                                <text
                                  textAnchor="middle"
                                  style={{
                                    fontSize: 8,
                                    fill: isHovered ? "#ffffff" : "#c4c4e8",
                                    fontWeight: 700,
                                    pointerEvents: "none",
                                    textShadow: "0 0 3px rgba(0,0,0,0.8)",
                                  }}
                                >
                                  {abbrev}
                                </text>
                                <text
                                  textAnchor="middle"
                                  y={10}
                                  style={{
                                    fontSize: 7,
                                    fill: isHovered ? "#fbbf24" : (sd.share > 0 ? "#e4e4f7" : "#71717a"),
                                    fontWeight: 600,
                                    pointerEvents: "none",
                                    textShadow: "0 0 3px rgba(0,0,0,0.8)",
                                  }}
                                >
                                  {pct}%
                                </text>
                              </Marker>
                            )}
                          </g>
                        );
                      })
                    }
                  </Geographies>
                </ZoomableGroup>
              </ComposableMap>

              {/* Hover tooltip */}
              {hoveredState && (() => {
                const sd = stateMap.get(hoveredState);
                return (
                  <div className="absolute top-2 left-2 bg-zinc-900/95 border border-zinc-700 rounded-lg px-3 py-2 pointer-events-none z-10">
                    <p className="text-white font-bold text-xs">{hoveredState}</p>
                    <p className="text-zinc-300 text-[10px]">
                      Sales: {fmtRevenue(sd?.revenue ?? 0)} &middot; {(((sd?.share ?? 0)) * 100).toFixed(1)}%
                    </p>
                  </div>
                );
              })()}
            </div>

            {/* Vertical gradient legend */}
            <div className="flex flex-col items-center justify-center gap-1 w-16 flex-shrink-0">
              <span className="text-[9px] text-zinc-400 font-medium">High Sales</span>
              <span className="text-[9px] text-zinc-500">100%</span>
              <div
                className="w-4 rounded"
                style={{
                  height: 120,
                  background: `linear-gradient(to bottom, ${choroplethColor(maxStateShare, maxStateShare)}, ${choroplethColor(maxStateShare * 0.5, maxStateShare)}, ${choroplethColor(0.001, maxStateShare)}, #2a2a3d)`,
                }}
              />
              <span className="text-[9px] text-zinc-500">0%</span>
              <span className="text-[9px] text-zinc-400 font-medium">Low Sales</span>
            </div>
          </div>

          {/* Top 10 Cities legend */}
          <div className="mt-3 pt-3 border-t border-zinc-800">
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">Top 10 Cities</p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
              {[...cities].sort((a, b) => b.revenue - a.revenue).slice(0, 10).map((c, i) => (
                <div key={c.name} className="flex items-center gap-1.5 text-xs">
                  <span className="text-white w-3 text-right font-mono text-[10px] font-bold">{i + 1}</span>
                  <span className="text-zinc-300 truncate flex-1 text-[11px]">{c.name}</span>
                  <span className="text-zinc-200 tabular-nums text-[10px] font-medium">{fmtRevenue(c.revenue)}</span>
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ════════════════════════════════════════════════════════════════════
         RIGHT: State-wise Distribution (horizontal bar chart)
         ════════════════════════════════════════════════════════════════════ */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-zinc-100 flex items-center justify-between">
            <span>State-wise Sales</span>
            <span className="text-[10px] text-zinc-500 font-normal">
              {states.length} states &middot; {fmtRevenue(totalStateRevenue)}
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-0.5">
            {states.map((s, i) => {
              const barPct = maxStateRevenue > 0 ? (s.revenue / maxStateRevenue) * 100 : 0;
              const t = maxStateRevenue > 0 ? s.revenue / maxStateRevenue : 0;
              const isHovered = hoveredState === s.name;
              return (
                <div
                  key={s.name}
                  className={`group rounded px-0.5 transition-colors ${isHovered ? "bg-zinc-800" : ""}`}
                  onMouseEnter={() => setHoveredState(s.name)}
                  onMouseLeave={() => setHoveredState(null)}
                >
                  <div className="flex items-center gap-1.5 text-xs">
                    <span className="text-white w-4 text-right font-mono text-[9px] font-bold">{i + 1}</span>
                    <span className="text-zinc-300 w-28 truncate text-[10px]">{s.name}</span>
                    <div className="flex-1 h-3 bg-zinc-800/50 rounded overflow-hidden relative">
                      <div
                        className="h-full rounded transition-all duration-300"
                        style={{
                          width: `${barPct}%`,
                          backgroundColor: interpolateColor(t),
                          opacity: isHovered ? 1 : 0.85,
                        }}
                      />
                    </div>
                    <span className="text-zinc-200 tabular-nums text-[10px] w-14 text-right font-medium">{fmtRevenue(s.revenue)}</span>
                    <span className="text-zinc-200 tabular-nums text-[9px] w-10 text-right font-medium">{(s.share * 100).toFixed(1)}%</span>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
