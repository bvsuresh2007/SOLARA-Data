"use client";

import { useMemo, useState } from "react";
import {
  ComposableMap, Geographies, Geography, Marker, ZoomableGroup,
} from "react-simple-maps";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SalesByDimension } from "@/lib/api";
import { fmtRevenue } from "@/lib/format";

/* ═══════════════════════════════════════════════════════════════════════════
   India Sales Map — proper TopoJSON state boundaries + city bubbles
   ═══════════════════════════════════════════════════════════════════════════ */

interface Props {
  data: SalesByDimension[];
}

const INDIA_TOPO = "/india-topo.json";
const INDIA_CENTER: [number, number] = [82, 22];
const INDIA_ZOOM = 4.5;

/* ── Known Indian state names (ALL CAPS in DB) — filter these out of city data ── */
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

/* ── City coordinates [lng, lat] for react-simple-maps (note: [lng, lat] not [lat, lng]) ── */
const CITY_COORDS: Record<string, [number, number]> = {
  // Metros
  "mumbai": [72.878, 19.076], "delhi": [77.209, 28.614], "bengaluru": [77.594, 12.972],
  "bangalore": [77.594, 12.972], "hyderabad": [78.487, 17.385], "chennai": [80.270, 13.083],
  "kolkata": [88.364, 22.573], "pune": [73.856, 18.52], "ahmedabad": [72.571, 23.023],
  // Tier 1
  "jaipur": [75.787, 26.912], "lucknow": [80.947, 26.847], "surat": [72.831, 21.170],
  "chandigarh": [76.779, 30.734], "indore": [75.858, 22.720], "bhopal": [77.413, 23.259],
  "nagpur": [79.089, 21.146], "patna": [85.145, 25.612], "vadodara": [73.181, 22.307],
  "coimbatore": [76.956, 11.017], "kochi": [76.267, 9.931], "visakhapatnam": [83.218, 17.687],
  "guwahati": [91.736, 26.145], "bhubaneswar": [85.825, 20.297], "dehradun": [78.032, 30.317],
  "thiruvananthapuram": [76.936, 8.524], "mysuru": [76.639, 12.296], "mysore": [76.639, 12.296],
  "mangalore": [74.856, 12.914], "mangaluru": [74.856, 12.914],
  // NCR
  "noida": [77.391, 28.535], "gurugram": [77.027, 28.459], "gurgaon": [77.027, 28.459],
  "ghaziabad": [77.438, 28.669], "faridabad": [77.317, 28.408], "greater noida": [77.504, 28.475],
  // Mumbai region
  "navi mumbai": [73.030, 19.037], "thane": [72.978, 19.218],
  // Others
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
  "panaji": [73.876, 15.380], "goa": [73.876, 15.380],
  "shimla": [77.172, 31.105],
  // Duplicate city names in ALL CAPS that are actually cities (not states)
  "BANGALORE": [77.594, 12.972], "MUMBAI": [72.878, 19.076],
  "PUNE": [73.856, 18.52], "HYDERABAD": [78.487, 17.385],
  "CHENNAI": [80.270, 13.083], "THANE": [72.978, 19.218],
  "KOLKATA": [88.364, 22.573],
};

/* ── Color interpolation — bright, visible gradient ───────────────────── */
function interpolateColor(t: number): string {
  // #22d3ee (cyan-400) → #f59e0b (amber-500) → #ef4444 (red-500)
  if (t < 0.5) {
    const s = t * 2; // 0→1 within first half
    const r = Math.round(34 + s * (245 - 34));
    const g = Math.round(211 + s * (158 - 211));
    const b = Math.round(238 + s * (11 - 238));
    return `rgb(${r},${g},${b})`;
  }
  const s = (t - 0.5) * 2; // 0→1 within second half
  const r = Math.round(245 + s * (239 - 245));
  const g = Math.round(158 + s * (68 - 158));
  const b = Math.round(11 + s * (68 - 11));
  return `rgb(${r},${g},${b})`;
}

/* ── Component ─────────────────────────────────────────────────────────── */

export default function IndiaSalesMap({ data }: Props) {
  const [hovered, setHovered] = useState<string | null>(null);

  const { cities, maxRevenue, totalRevenue } = useMemo(() => {
    if (!data?.length) return { cities: [], maxRevenue: 0, totalRevenue: 0 };

    // Separate state vs city entries
    const cityEntries = data.filter((d) => {
      const name = d.dimension_name.trim();
      // Skip known state names (but allow city names that happen to be UPPER CASE like BANGALORE)
      if (STATE_NAMES.has(name.toUpperCase()) && !CITY_COORDS[name]) return false;
      return true;
    });

    const totalRevenue = cityEntries.reduce((s, d) => s + d.total_revenue, 0);
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
          share: totalRevenue > 0 ? d.total_revenue / totalRevenue : 0,
        };
      })
      .filter(Boolean) as {
        name: string; coords: [number, number]; revenue: number;
        quantity: number; share: number;
      }[];

    return { cities, maxRevenue: maxRev, totalRevenue };
  }, [data]);

  if (!data?.length) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-zinc-100">Sales by City</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-zinc-500 text-xs">No city-level data available</p>
        </CardContent>
      </Card>
    );
  }

  const top10 = [...cities].sort((a, b) => b.revenue - a.revenue).slice(0, 10);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-zinc-100 flex items-center justify-between">
          <span>City-wise Sales Distribution</span>
          <span className="text-[10px] text-zinc-500 font-normal">
            {cities.length} cities mapped
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col lg:flex-row gap-6 items-center justify-center">
          {/* ── Map ─────────────────────────────────────────────────── */}
          <div className="min-w-0" style={{ width: 400, maxHeight: 420 }}>
            <ComposableMap
              projection="geoMercator"
              projectionConfig={{ center: INDIA_CENTER, scale: 650 }}
              width={400}
              height={420}
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
                        fill="#27272a"
                        stroke="#52525b"
                        strokeWidth={0.5}
                        style={{
                          default: { outline: "none" },
                          hover: { fill: "#3f3f46", outline: "none" },
                          pressed: { outline: "none" },
                        }}
                      />
                    ))
                  }
                </Geographies>

                {/* City bubbles */}
                {cities.map((c) => {
                  const t = maxRevenue > 0 ? c.revenue / maxRevenue : 0;
                  const radius = 2 + Math.sqrt(t) * 8;
                  const color = interpolateColor(t);
                  const isHovered = hovered === c.name;

                  return (
                    <Marker
                      key={c.name}
                      coordinates={c.coords}
                      onMouseEnter={() => setHovered(c.name)}
                      onMouseLeave={() => setHovered(null)}
                    >
                      <circle
                        r={isHovered ? radius * 1.5 : radius}
                        fill={color}
                        fillOpacity={isHovered ? 1 : 0.85}
                        stroke={isHovered ? "#fff" : "rgba(255,255,255,0.3)"}
                        strokeWidth={isHovered ? 1.5 : 0.5}
                        className="cursor-pointer"
                      />
                      {(isHovered || c.share > 0.05) && (
                        <text
                          textAnchor="middle"
                          y={-radius - 4}
                          style={{
                            fontSize: isHovered ? 10 : 8,
                            fill: "#e4e4e7",
                            fontWeight: isHovered ? 600 : 400,
                            pointerEvents: "none",
                          }}
                        >
                          {c.name}
                        </text>
                      )}
                    </Marker>
                  );
                })}
              </ZoomableGroup>
            </ComposableMap>

            {/* Gradient legend */}
            <div className="flex items-center justify-center gap-2 -mt-4">
              <span className="text-[10px] text-zinc-500">Low</span>
              <div
                className="h-2 rounded-full"
                style={{
                  width: 180,
                  background: `linear-gradient(to right, ${interpolateColor(0)}, ${interpolateColor(0.5)}, ${interpolateColor(1)})`,
                }}
              />
              <span className="text-[10px] text-zinc-500">High</span>
            </div>
            <p className="text-center text-[10px] text-zinc-600 mt-0.5">Revenue Share</p>
          </div>

          {/* ── Top 10 sidebar ──────────────────────────────────────── */}
          <div className="w-48 flex-shrink-0">
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">Top 10 Cities</p>
            <div className="space-y-1.5">
              {top10.map((c, i) => {
                const t = maxRevenue > 0 ? c.revenue / maxRevenue : 0;
                return (
                  <div
                    key={c.name}
                    className={`flex items-center gap-2 text-xs cursor-pointer rounded px-1.5 py-1 transition-colors
                      ${hovered === c.name ? "bg-zinc-800" : "hover:bg-zinc-800/50"}`}
                    onMouseEnter={() => setHovered(c.name)}
                    onMouseLeave={() => setHovered(null)}
                  >
                    <span className="text-zinc-600 w-4 text-right font-mono text-[10px]">{i + 1}</span>
                    <div
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ backgroundColor: interpolateColor(t) }}
                    />
                    <span className="text-zinc-300 truncate flex-1">{c.name}</span>
                    <span className="text-zinc-500 tabular-nums text-[10px]">{fmtRevenue(c.revenue)}</span>
                  </div>
                );
              })}
            </div>
            <div className="mt-3 pt-2 border-t border-zinc-800">
              <div className="flex justify-between text-[10px] text-zinc-500">
                <span>Total (mapped cities)</span>
              </div>
              <p className="text-sm text-zinc-200 font-medium">{fmtRevenue(totalRevenue)}</p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
