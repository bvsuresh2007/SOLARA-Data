"use client";

import { useMemo, useState } from "react";
import {
  ComposableMap, Geographies, Geography, Marker, ZoomableGroup,
} from "react-simple-maps";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SalesByDimension } from "@/lib/api";
import { fmtRevenue } from "@/lib/format";

/* ═══════════════════════════════════════════════════════════════════════════
   India Sales Map — city bubbles (left) + state bar chart (right)
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
  // Metros
  "mumbai": [72.878, 19.076], "delhi": [77.209, 28.614], "new delhi": [77.209, 28.614],
  "bengaluru": [77.594, 12.972], "bangalore": [77.594, 12.972],
  "hyderabad": [78.487, 17.385], "chennai": [80.270, 13.083],
  "kolkata": [88.364, 22.573], "pune": [73.856, 18.52], "ahmedabad": [72.571, 23.023],
  // North India
  "jaipur": [75.787, 26.912], "lucknow": [80.947, 26.847], "agra": [78.015, 27.177],
  "varanasi": [82.991, 25.318], "kanpur": [80.332, 26.449], "prayagraj": [81.846, 25.435],
  "allahabad": [81.846, 25.435], "meerut": [77.706, 28.984], "aligarh": [78.078, 27.883],
  "bareilly": [79.432, 28.367], "moradabad": [78.773, 28.839], "gorakhpur": [83.379, 26.760],
  "mathura": [77.673, 27.492], "saharanpur": [77.541, 29.964], "muzaffarnagar": [77.707, 29.473],
  "firozabad": [78.395, 27.150], "shahjahanpur": [79.905, 27.883],
  "noida": [77.391, 28.535], "gurugram": [77.027, 28.459], "gurgaon": [77.027, 28.459],
  "ghaziabad": [77.438, 28.669], "faridabad": [77.317, 28.408], "greater noida": [77.504, 28.475],
  "gautam buddha nagar": [77.504, 28.475], // Greater Noida district
  "chandigarh": [76.779, 30.734], "dehradun": [78.032, 30.317],
  "amritsar": [74.872, 31.634], "ludhiana": [75.857, 30.901], "jalandhar": [75.576, 31.326],
  "jammu": [74.857, 32.735], "patiala": [76.387, 30.340], "bathinda": [74.951, 30.211],
  "panipat": [76.968, 29.390], "karnal": [76.990, 29.686], "ambala": [76.777, 30.378],
  "rohtak": [76.606, 28.894], "hisar": [75.723, 29.154], "sonipat": [77.016, 28.994],
  "shimla": [77.172, 31.105], "haridwar": [78.169, 29.946],
  // West India
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
  // South India
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
  // East India
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

/* ── Color interpolation — cyan → amber → red ────────────────────────── */
function interpolateColor(t: number): string {
  if (t < 0.5) {
    const s = t * 2;
    return `rgb(${Math.round(34 + s * 211)},${Math.round(211 - s * 53)},${Math.round(238 - s * 227)})`;
  }
  const s = (t - 0.5) * 2;
  return `rgb(${Math.round(245 - s * 6)},${Math.round(158 - s * 90)},${Math.round(11 + s * 57)})`;
}

/* ── Title case helper ────────────────────────────────────────────────── */
function titleCase(s: string): string {
  return s.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ── City name normalisation — merge duplicates & aliases ─────────────── */
const CITY_ALIASES: Record<string, string> = {
  "bangalore": "Bengaluru",
  "gurgaon": "Gurugram",
  "trivandrum": "Thiruvananthapuram",
  "calicut": "Kozhikode",
  "mysore": "Mysuru",
  "mangalore": "Mangaluru",
  "allahabad": "Prayagraj",
  "trichy": "Tiruchirappalli",
  "belgaum": "Belagavi",
  "new delhi": "Delhi",
  "ernakulam": "Kochi",
  "gautam buddha nagar": "Greater Noida",
  "kalyan": "Thane",          // Kalyan-Dombivli = Thane metro
  "vasai": "Thane",            // Vasai-Virar = Thane metro
  "bhiwandi": "Thane",         // Bhiwandi = Thane district
  "howrah": "Kolkata",         // Howrah = Kolkata metro
  "palghar": "Navi Mumbai",    // Palghar = Mumbai metro
  "gulbarga": "Kalaburagi",
  "shimoga": "Shivamogga",
  "bellary": "Ballari",
  "tumkur": "Tumakuru",
};

function normalizeCityName(raw: string): string {
  const trimmed = raw.trim();
  const titled = titleCase(trimmed);
  const alias = CITY_ALIASES[trimmed.toLowerCase()];
  return alias ?? titled;
}

/* ── State name normalisation — merge duplicates & aliases ────────────── */
const STATE_ALIASES: Record<string, string> = {
  "chattisgarh": "Chhattisgarh",
  "orissa": "Odisha",
  "pondicherry": "Puducherry",
  "uttaranchal": "Uttarakhand",
  "new delhi": "Delhi",
  "nct of delhi": "Delhi",
  "ncr": "Delhi",
  "jammu and kashmir": "Jammu & Kashmir",
  "jammu & kashmir": "Jammu & Kashmir",
  "j&k": "Jammu & Kashmir",
  "dadra and nagar haveli and daman and diu": "Dadra & Nagar Haveli",
  "dadra and nagar haveli": "Dadra & Nagar Haveli",
  "daman and diu": "Daman & Diu",
  "andaman and nicobar": "Andaman & Nicobar",
  "andaman and nicobar islands": "Andaman & Nicobar",
};

function normalizeStateName(raw: string): string {
  const trimmed = raw.trim();
  const titled = titleCase(trimmed);
  const alias = STATE_ALIASES[trimmed.toLowerCase()];
  return alias ?? titled;
}

/* ── City → State mapping (for deriving state totals from city data) ── */
const CITY_TO_STATE: Record<string, string> = {
  // Maharashtra
  "mumbai": "Maharashtra", "pune": "Maharashtra", "nashik": "Maharashtra", "nagpur": "Maharashtra",
  "aurangabad": "Maharashtra", "navi mumbai": "Maharashtra", "thane": "Maharashtra",
  "kolhapur": "Maharashtra", "solapur": "Maharashtra", "sangli": "Maharashtra",
  "palghar": "Maharashtra", "kalyan": "Maharashtra", "vasai": "Maharashtra", "bhiwandi": "Maharashtra",
  // Karnataka
  "bengaluru": "Karnataka", "bangalore": "Karnataka", "mysuru": "Karnataka", "mysore": "Karnataka",
  "mangalore": "Karnataka", "mangaluru": "Karnataka", "hubli": "Karnataka",
  "belgaum": "Karnataka", "belagavi": "Karnataka", "davanagere": "Karnataka",
  "bellary": "Karnataka", "shimoga": "Karnataka", "tumkur": "Karnataka",
  "gulbarga": "Karnataka", "udupi": "Karnataka", "hassan": "Karnataka",
  // Tamil Nadu
  "chennai": "Tamil Nadu", "coimbatore": "Tamil Nadu", "madurai": "Tamil Nadu",
  "tiruchirappalli": "Tamil Nadu", "trichy": "Tamil Nadu", "salem": "Tamil Nadu",
  "tiruppur": "Tamil Nadu", "vellore": "Tamil Nadu", "erode": "Tamil Nadu",
  "thanjavur": "Tamil Nadu", "dindigul": "Tamil Nadu", "thoothukudi": "Tamil Nadu",
  "tirunelveli": "Tamil Nadu", "chengalpattu": "Tamil Nadu",
  // Telangana
  "hyderabad": "Telangana", "warangal": "Telangana", "karimnagar": "Telangana",
  "nizamabad": "Telangana",
  // Andhra Pradesh
  "visakhapatnam": "Andhra Pradesh", "vijayawada": "Andhra Pradesh", "guntur": "Andhra Pradesh",
  "nellore": "Andhra Pradesh", "rajahmundry": "Andhra Pradesh", "kakinada": "Andhra Pradesh",
  "tirupati": "Andhra Pradesh", "kadapa": "Andhra Pradesh", "anantapur": "Andhra Pradesh",
  "kurnool": "Andhra Pradesh",
  // Kerala
  "kochi": "Kerala", "ernakulam": "Kerala", "thiruvananthapuram": "Kerala",
  "trivandrum": "Kerala", "kozhikode": "Kerala", "calicut": "Kerala",
  "thrissur": "Kerala", "kollam": "Kerala", "palakkad": "Kerala",
  "kottayam": "Kerala", "kannur": "Kerala", "malappuram": "Kerala",
  // Gujarat
  "ahmedabad": "Gujarat", "surat": "Gujarat", "vadodara": "Gujarat", "rajkot": "Gujarat",
  "anand": "Gujarat", "gandhinagar": "Gujarat", "bhavnagar": "Gujarat", "jamnagar": "Gujarat",
  // Rajasthan
  "jaipur": "Rajasthan", "jodhpur": "Rajasthan", "udaipur": "Rajasthan", "kota": "Rajasthan",
  // Uttar Pradesh
  "lucknow": "Uttar Pradesh", "agra": "Uttar Pradesh", "varanasi": "Uttar Pradesh",
  "kanpur": "Uttar Pradesh", "prayagraj": "Uttar Pradesh", "allahabad": "Uttar Pradesh",
  "meerut": "Uttar Pradesh", "noida": "Uttar Pradesh", "ghaziabad": "Uttar Pradesh",
  "greater noida": "Uttar Pradesh", "gautam buddha nagar": "Uttar Pradesh",
  "aligarh": "Uttar Pradesh", "bareilly": "Uttar Pradesh", "moradabad": "Uttar Pradesh",
  "gorakhpur": "Uttar Pradesh", "mathura": "Uttar Pradesh", "saharanpur": "Uttar Pradesh",
  "muzaffarnagar": "Uttar Pradesh", "firozabad": "Uttar Pradesh", "shahjahanpur": "Uttar Pradesh",
  // Delhi / NCR
  "delhi": "Delhi", "new delhi": "Delhi",
  // Haryana
  "gurugram": "Haryana", "gurgaon": "Haryana", "faridabad": "Haryana",
  "panipat": "Haryana", "karnal": "Haryana", "ambala": "Haryana",
  "rohtak": "Haryana", "hisar": "Haryana", "sonipat": "Haryana",
  // Punjab
  "amritsar": "Punjab", "ludhiana": "Punjab", "jalandhar": "Punjab",
  "patiala": "Punjab", "bathinda": "Punjab",
  // West Bengal
  "kolkata": "West Bengal", "siliguri": "West Bengal", "durgapur": "West Bengal",
  "howrah": "West Bengal", "asansol": "West Bengal", "kharagpur": "West Bengal",
  // Bihar
  "patna": "Bihar", "muzaffarpur": "Bihar", "gaya": "Bihar", "bhagalpur": "Bihar",
  // Jharkhand
  "ranchi": "Jharkhand", "jamshedpur": "Jharkhand", "bokaro": "Jharkhand", "dhanbad": "Jharkhand",
  // Odisha
  "bhubaneswar": "Odisha", "cuttack": "Odisha", "sambalpur": "Odisha", "berhampur": "Odisha",
  // Chhattisgarh
  "raipur": "Chhattisgarh", "bilaspur": "Chhattisgarh", "durg": "Chhattisgarh", "bhilai": "Chhattisgarh",
  // Madhya Pradesh
  "indore": "Madhya Pradesh", "bhopal": "Madhya Pradesh",
  // Assam
  "guwahati": "Assam", "jorhat": "Assam", "dibrugarh": "Assam", "tezpur": "Assam",
  // Other NE & UTs
  "imphal": "Manipur", "shillong": "Meghalaya", "agartala": "Tripura",
  "chandigarh": "Chandigarh", "jammu": "Jammu & Kashmir",
  "dehradun": "Uttarakhand", "haridwar": "Uttarakhand",
  "shimla": "Himachal Pradesh",
  "panaji": "Goa", "goa": "Goa",
};

/* ══════════════════════════════════════════════════════════════════════════
   Component
   ══════════════════════════════════════════════════════════════════════════ */

export default function IndiaSalesMap({ data }: Props) {
  const [hovered, setHovered] = useState<string | null>(null);
  const isAnyHovered = hovered !== null;

  const { cities, states, maxRevenue, totalCityRevenue, totalStateRevenue, maxStateRevenue } = useMemo(() => {
    if (!data?.length) return { cities: [], states: [], maxRevenue: 0, totalCityRevenue: 0, totalStateRevenue: 0, maxStateRevenue: 0 };

    const stateAgg = new Map<string, { revenue: number; quantity: number }>();
    const cityEntries: typeof data = [];

    // Helper to add revenue to state aggregation
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
        // State-level entry — always add to state aggregation
        addToState(normalizeStateName(name), d.total_revenue, d.total_quantity);
        // Also show as city bubble if coords exist (Delhi, Goa, Chandigarh)
        if (hasCoords) cityEntries.push(d);
      } else {
        // City entry — add to city list
        cityEntries.push(d);
        // Also derive state from city→state mapping and add to state agg
        const parentState = CITY_TO_STATE[lower];
        if (parentState) {
          addToState(parentState, d.total_revenue, d.total_quantity);
        }
      }
    }

    const totalCityRevenue = cityEntries.reduce((s, d) => s + d.total_revenue, 0);

    // Merge duplicates: normalise names then aggregate revenue/quantity
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
      return {
        name,
        coords: v.coords,
        revenue: v.revenue,
        quantity: v.quantity,
        share: totalCityRevenue > 0 ? v.revenue / totalCityRevenue : 0,
      };
    });

    // Convert state map to sorted array
    const stateList = Array.from(stateAgg.entries())
      .map(([name, v]) => ({ name, revenue: v.revenue, quantity: v.quantity }))
      .sort((a, b) => b.revenue - a.revenue);
    const totalStateRevenue = stateList.reduce((s, d) => s + d.revenue, 0);
    const maxStateRevenue = stateList.length > 0 ? stateList[0].revenue : 0;

    return {
      cities,
      states: stateList.map((s) => ({
        ...s,
        share: totalStateRevenue > 0 ? s.revenue / totalStateRevenue : 0,
      })),
      maxRevenue: maxRev,
      totalCityRevenue,
      totalStateRevenue,
      maxStateRevenue,
    };
  }, [data]);

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
         LEFT: City-wise India Map
         ════════════════════════════════════════════════════════════════════ */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-zinc-100 flex items-center justify-between">
            <span>City-wise Sales</span>
            <span className="text-[10px] text-zinc-500 font-normal">
              {cities.length} cities &middot; {fmtRevenue(totalCityRevenue)}
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="relative" style={{ width: 420, maxWidth: "100%" }}>
            <ComposableMap
              projection="geoMercator"
              projectionConfig={{ center: INDIA_CENTER, scale: 680 }}
              width={420}
              height={440}
              style={{ width: "100%", height: "auto" }}
            >
              <ZoomableGroup center={INDIA_CENTER} zoom={1} minZoom={1} maxZoom={4}>
                {/* State boundaries */}
                <Geographies geography={INDIA_TOPO}>
                  {({ geographies }) =>
                    geographies.map((geo) => (
                      <Geography
                        key={geo.rsmKey}
                        geography={geo}
                        fill={isAnyHovered ? "#1a1a1d" : "#27272a"}
                        stroke="#ffffff"
                        strokeWidth={0.5}
                        style={{
                          default: { outline: "none", transition: "fill 0.2s" },
                          hover: { fill: isAnyHovered ? "#1a1a1d" : "#3f3f46", outline: "none" },
                          pressed: { outline: "none" },
                        }}
                      />
                    ))
                  }
                </Geographies>

                {/* Dim overlay when a city is hovered */}
                {isAnyHovered && (
                  <rect x={-200} y={-200} width={2000} height={2000}
                    fill="black" fillOpacity={0.35} style={{ pointerEvents: "none" }} />
                )}

                {/* City bubbles */}
                {cities.map((c) => {
                  const t = maxRevenue > 0 ? c.revenue / maxRevenue : 0;
                  const radius = 2 + Math.sqrt(t) * 8;
                  const color = interpolateColor(t);
                  const isThis = hovered === c.name;
                  const dimmed = isAnyHovered && !isThis;

                  return (
                    <Marker
                      key={c.name}
                      coordinates={c.coords}
                      onMouseEnter={() => setHovered(c.name)}
                      onMouseLeave={() => setHovered(null)}
                    >
                      <circle
                        r={isThis ? radius * 1.6 : radius}
                        fill={color}
                        fillOpacity={dimmed ? 0.25 : isThis ? 1 : 0.85}
                        stroke={isThis ? "#fff" : dimmed ? "transparent" : "rgba(255,255,255,0.3)"}
                        strokeWidth={isThis ? 2 : 0.5}
                        className="cursor-pointer"
                        style={{ transition: "all 0.15s" }}
                      />

                      {isThis && (
                        <g style={{ pointerEvents: "none" }}>
                          {/* Tooltip background */}
                          <rect
                            x={-70} y={-radius - 42}
                            width={140} height={34}
                            rx={5}
                            fill="#09090b" stroke="#52525b" strokeWidth={0.8}
                            fillOpacity={0.95}
                          />
                          <text textAnchor="middle" y={-radius - 26}
                            style={{ fontSize: 11, fill: "#ffffff", fontWeight: 700 }}>
                            {c.name}
                          </text>
                          <text textAnchor="middle" y={-radius - 13}
                            style={{ fontSize: 10, fill: "#d4d4d8" }}>
                            {fmtRevenue(c.revenue)} &middot; {Math.round(c.quantity).toLocaleString("en-IN")} units
                          </text>
                        </g>
                      )}
                    </Marker>
                  );
                })}
              </ZoomableGroup>
            </ComposableMap>

            {/* Gradient legend */}
            <div className="flex items-center justify-start gap-2 mt-1 ml-2">
              <span className="text-[10px] text-zinc-500">Low</span>
              <div className="h-2 rounded-full"
                style={{ width: 160, background: `linear-gradient(to right, ${interpolateColor(0)}, ${interpolateColor(0.5)}, ${interpolateColor(1)})` }} />
              <span className="text-[10px] text-zinc-500">High</span>
              <span className="text-[10px] text-zinc-600 ml-1">Revenue</span>
            </div>
          </div>

          {/* Top 10 Cities legend */}
          <div className="mt-3 pt-3 border-t border-zinc-800">
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">Top 10 Cities</p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
              {[...cities].sort((a, b) => b.revenue - a.revenue).slice(0, 10).map((c, i) => {
                const t = maxRevenue > 0 ? c.revenue / maxRevenue : 0;
                return (
                  <div
                    key={c.name}
                    className={`flex items-center gap-1.5 text-xs cursor-pointer rounded px-1 py-0.5 transition-colors
                      ${hovered === c.name ? "bg-zinc-800" : "hover:bg-zinc-800/50"}`}
                    onMouseEnter={() => setHovered(c.name)}
                    onMouseLeave={() => setHovered(null)}
                  >
                    <span className="text-white w-3 text-right font-mono text-[10px] font-bold">{i + 1}</span>
                    <div className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ backgroundColor: interpolateColor(t) }} />
                    <span className="text-zinc-300 truncate flex-1 text-[11px]">{c.name}</span>
                    <span className="text-zinc-200 tabular-nums text-[10px] font-medium">{fmtRevenue(c.revenue)}</span>
                  </div>
                );
              })}
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
              return (
                <div key={s.name} className="group">
                  <div className="flex items-center gap-1.5 text-xs">
                    <span className="text-white w-4 text-right font-mono text-[9px] font-bold">{i + 1}</span>
                    <span className="text-zinc-300 w-28 truncate text-[10px]">{s.name}</span>
                    <div className="flex-1 h-3 bg-zinc-800/50 rounded overflow-hidden relative">
                      <div
                        className="h-full rounded transition-all duration-300"
                        style={{
                          width: `${barPct}%`,
                          backgroundColor: interpolateColor(t),
                          opacity: 0.85,
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
