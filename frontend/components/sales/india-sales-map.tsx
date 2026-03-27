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
  "mumbai": [72.878, 19.076], "delhi": [77.209, 28.614], "bengaluru": [77.594, 12.972],
  "bangalore": [77.594, 12.972], "hyderabad": [78.487, 17.385], "chennai": [80.270, 13.083],
  "kolkata": [88.364, 22.573], "pune": [73.856, 18.52], "ahmedabad": [72.571, 23.023],
  "jaipur": [75.787, 26.912], "lucknow": [80.947, 26.847], "surat": [72.831, 21.170],
  "chandigarh": [76.779, 30.734], "indore": [75.858, 22.720], "bhopal": [77.413, 23.259],
  "nagpur": [79.089, 21.146], "patna": [85.145, 25.612], "vadodara": [73.181, 22.307],
  "coimbatore": [76.956, 11.017], "kochi": [76.267, 9.931], "visakhapatnam": [83.218, 17.687],
  "guwahati": [91.736, 26.145], "bhubaneswar": [85.825, 20.297], "dehradun": [78.032, 30.317],
  "thiruvananthapuram": [76.936, 8.524], "mysuru": [76.639, 12.296], "mysore": [76.639, 12.296],
  "mangalore": [74.856, 12.914], "mangaluru": [74.856, 12.914],
  "noida": [77.391, 28.535], "gurugram": [77.027, 28.459], "gurgaon": [77.027, 28.459],
  "ghaziabad": [77.438, 28.669], "faridabad": [77.317, 28.408], "greater noida": [77.504, 28.475],
  "navi mumbai": [73.030, 19.037], "thane": [72.978, 19.218],
  "rajkot": [70.802, 22.304], "nashik": [73.789, 19.998], "aurangabad": [75.343, 19.876],
  "vijayawada": [80.648, 16.506], "warangal": [79.599, 17.978],
  "madurai": [78.120, 9.925], "tiruchirappalli": [78.688, 10.791], "trichy": [78.688, 10.791],
  "salem": [78.146, 11.665], "tiruppur": [77.340, 11.109],
  "ranchi": [85.310, 23.345], "jamshedpur": [86.203, 22.805],
  "raipur": [81.630, 21.252], "agra": [78.015, 27.177], "varanasi": [82.991, 25.318],
  "kanpur": [80.332, 26.449], "prayagraj": [81.846, 25.435], "allahabad": [81.846, 25.435],
  "meerut": [77.706, 28.984], "jodhpur": [73.049, 26.279], "udaipur": [73.713, 24.585],
  "kota": [75.864, 25.180], "amritsar": [74.872, 31.634], "ludhiana": [75.857, 30.901],
  "jalandhar": [75.576, 31.326], "jammu": [74.857, 32.735],
  "siliguri": [88.395, 26.727], "durgapur": [87.322, 23.553],
  "hubli": [75.124, 15.364], "belgaum": [74.498, 15.849], "belagavi": [74.498, 15.849],
  "kozhikode": [75.780, 11.259], "calicut": [75.780, 11.259],
  "thrissur": [76.214, 10.527], "trivandrum": [76.936, 8.524],
  "panaji": [73.876, 15.380], "goa": [73.876, 15.380], "shimla": [77.172, 31.105],
  "BANGALORE": [77.594, 12.972], "MUMBAI": [72.878, 19.076],
  "PUNE": [73.856, 18.52], "HYDERABAD": [78.487, 17.385],
  "CHENNAI": [80.270, 13.083], "THANE": [72.978, 19.218],
  "KOLKATA": [88.364, 22.573],
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

/* ══════════════════════════════════════════════════════════════════════════
   Component
   ══════════════════════════════════════════════════════════════════════════ */

export default function IndiaSalesMap({ data }: Props) {
  const [hovered, setHovered] = useState<string | null>(null);
  const isAnyHovered = hovered !== null;

  const { cities, states, maxRevenue, totalCityRevenue, totalStateRevenue, maxStateRevenue } = useMemo(() => {
    if (!data?.length) return { cities: [], states: [], maxRevenue: 0, totalCityRevenue: 0, totalStateRevenue: 0, maxStateRevenue: 0 };

    const stateEntries: { name: string; revenue: number; quantity: number }[] = [];
    const cityEntries: typeof data = [];

    for (const d of data) {
      const name = d.dimension_name.trim();
      if (STATE_NAMES.has(name.toUpperCase()) && !CITY_COORDS[name]) {
        stateEntries.push({ name: titleCase(name), revenue: d.total_revenue, quantity: d.total_quantity });
      } else {
        cityEntries.push(d);
      }
    }

    const totalCityRevenue = cityEntries.reduce((s, d) => s + d.total_revenue, 0);
    let maxRev = 0;

    const cities = cityEntries
      .map((d) => {
        const key = d.dimension_name.trim();
        const coords = CITY_COORDS[key] ?? CITY_COORDS[key.toLowerCase()];
        if (!coords) return null;
        if (d.total_revenue > maxRev) maxRev = d.total_revenue;
        return {
          name: d.dimension_name,
          coords: coords as [number, number],
          revenue: d.total_revenue,
          quantity: d.total_quantity,
          share: totalCityRevenue > 0 ? d.total_revenue / totalCityRevenue : 0,
        };
      })
      .filter(Boolean) as {
        name: string; coords: [number, number]; revenue: number;
        quantity: number; share: number;
      }[];

    // Sort states by revenue descending
    stateEntries.sort((a, b) => b.revenue - a.revenue);
    const totalStateRevenue = stateEntries.reduce((s, d) => s + d.revenue, 0);
    const maxStateRevenue = stateEntries.length > 0 ? stateEntries[0].revenue : 0;

    return {
      cities,
      states: stateEntries.map((s) => ({
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
          <div className="space-y-1.5 max-h-[460px] overflow-y-auto pr-1">
            {states.map((s, i) => {
              const barPct = maxStateRevenue > 0 ? (s.revenue / maxStateRevenue) * 100 : 0;
              const t = maxStateRevenue > 0 ? s.revenue / maxStateRevenue : 0;
              return (
                <div key={s.name} className="group">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-zinc-600 w-5 text-right font-mono text-[10px]">{i + 1}</span>
                    <span className="text-zinc-300 w-32 truncate text-[11px]">{s.name}</span>
                    <div className="flex-1 h-4 bg-zinc-800/50 rounded overflow-hidden relative">
                      <div
                        className="h-full rounded transition-all duration-300"
                        style={{
                          width: `${barPct}%`,
                          backgroundColor: interpolateColor(t),
                          opacity: 0.85,
                        }}
                      />
                    </div>
                    <span className="text-zinc-400 tabular-nums text-[11px] w-16 text-right">{fmtRevenue(s.revenue)}</span>
                    <span className="text-zinc-600 tabular-nums text-[10px] w-10 text-right">{(s.share * 100).toFixed(1)}%</span>
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
