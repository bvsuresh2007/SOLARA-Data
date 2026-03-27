"use client";

import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SalesByDimension } from "@/lib/api";
import { fmtRevenue } from "@/lib/format";

/* ═══════════════════════════════════════════════════════════════════════════
   India Sales Map — SVG bubble map with gradient legend
   ═══════════════════════════════════════════════════════════════════════════ */

interface Props {
  data: SalesByDimension[];
}

/* ── City coordinates (lat/lng) for major Indian cities ─────────────────── */
const CITY_COORDS: Record<string, [number, number]> = {
  // [latitude, longitude]
  // Metros
  "mumbai": [19.076, 72.878], "delhi": [28.614, 77.209], "bengaluru": [12.972, 77.594],
  "bangalore": [12.972, 77.594], "hyderabad": [17.385, 78.487], "chennai": [13.083, 80.270],
  "kolkata": [22.573, 88.364], "pune": [18.52, 73.856], "ahmedabad": [23.023, 72.571],
  // Tier 1
  "jaipur": [26.912, 75.787], "lucknow": [26.847, 80.947], "surat": [21.170, 72.831],
  "chandigarh": [30.734, 76.779], "indore": [22.720, 75.858], "bhopal": [23.259, 77.413],
  "nagpur": [21.146, 79.089], "patna": [25.612, 85.145], "vadodara": [22.307, 73.181],
  "coimbatore": [11.017, 76.956], "kochi": [9.931, 76.267], "visakhapatnam": [17.687, 83.218],
  "guwahati": [26.145, 91.736], "bhubaneswar": [20.297, 85.825], "dehradun": [30.317, 78.032],
  "thiruvananthapuram": [8.524, 76.936], "mysuru": [12.296, 76.639], "mysore": [12.296, 76.639],
  "mangalore": [12.914, 74.856], "mangaluru": [12.914, 74.856],
  // Tier 2
  "noida": [28.535, 77.391], "gurugram": [28.459, 77.027], "gurgaon": [28.459, 77.027],
  "ghaziabad": [28.669, 77.438], "faridabad": [28.408, 77.317], "greater noida": [28.475, 77.504],
  "navi mumbai": [19.037, 73.030], "thane": [19.218, 72.978],
  "rajkot": [22.304, 70.802], "nashik": [19.998, 73.789], "aurangabad": [19.876, 75.343],
  "vijayawada": [16.506, 80.648], "warangal": [17.978, 79.599],
  "madurai": [9.925, 78.120], "tiruchirappalli": [10.791, 78.688], "trichy": [10.791, 78.688],
  "salem": [11.665, 78.146], "tiruppur": [11.109, 77.340],
  "ranchi": [23.345, 85.310], "jamshedpur": [22.805, 86.203],
  "raipur": [21.252, 81.630], "agra": [27.177, 78.015], "varanasi": [25.318, 82.991],
  "kanpur": [26.449, 80.332], "allahabad": [25.435, 81.846], "prayagraj": [25.435, 81.846],
  "meerut": [28.984, 77.706], "jodhpur": [26.279, 73.049], "udaipur": [24.585, 73.713],
  "kota": [25.180, 75.864], "amritsar": [31.634, 74.872], "ludhiana": [30.901, 75.857],
  "jalandhar": [31.326, 75.576], "jammu": [32.735, 74.857],
  "siliguri": [26.727, 88.395], "durgapur": [23.553, 87.322],
  "hubli": [15.364, 75.124], "belgaum": [15.849, 74.498], "belagavi": [15.849, 74.498],
  "calicut": [11.259, 75.780], "kozhikode": [11.259, 75.780],
  "thrissur": [10.527, 76.214], "trivandrum": [8.524, 76.936],
  // State-level entries (Amazon PI) — use state capital coordinates
  "karnataka": [12.972, 77.594], "maharashtra": [19.076, 72.878],
  "tamil nadu": [13.083, 80.270], "telangana": [17.385, 78.487],
  "uttar pradesh": [26.847, 80.947], "haryana": [28.459, 77.027],
  "west bengal": [22.573, 88.364], "kerala": [9.931, 76.267],
  "andhra pradesh": [16.506, 80.648], "gujarat": [23.023, 72.571],
  "rajasthan": [26.912, 75.787], "punjab": [30.734, 76.779],
  "madhya pradesh": [23.259, 77.413], "bihar": [25.612, 85.145],
  "assam": [26.145, 91.736], "odisha": [20.297, 85.825],
  "uttarakhand": [30.317, 78.032], "jharkhand": [23.345, 85.310],
  "chhattisgarh": [21.252, 81.630], "goa": [15.380, 73.876],
  "himachal pradesh": [31.105, 77.172], "tripura": [23.831, 91.286],
  "meghalaya": [25.578, 91.893], "manipur": [24.817, 93.950],
  "nagaland": [25.670, 94.120], "mizoram": [23.727, 92.718],
  "arunachal pradesh": [27.084, 93.615], "sikkim": [27.333, 88.617],
  "new delhi": [28.614, 77.209],
};

/* ── Mercator projection: lat/lng → SVG x/y ────────────────────────────── */
// India bounding box (approx): lat 6–36, lng 68–98
const LAT_MIN = 6, LAT_MAX = 36, LNG_MIN = 68, LNG_MAX = 98;
const SVG_W = 500, SVG_H = 580;
const PAD = 30;

function project(lat: number, lng: number): [number, number] {
  const x = PAD + ((lng - LNG_MIN) / (LNG_MAX - LNG_MIN)) * (SVG_W - 2 * PAD);
  const y = PAD + ((LAT_MAX - lat) / (LAT_MAX - LAT_MIN)) * (SVG_H - 2 * PAD);
  return [x, y];
}

/* ── Color interpolation for gradient ──────────────────────────────────── */
function interpolateColor(t: number): string {
  // Dark teal → Orange gradient (matches brand)
  // t = 0 → #134e4a (low), t = 1 → #f97316 (high)
  const r = Math.round(19 + t * (249 - 19));
  const g = Math.round(78 + t * (115 - 78));
  const b = Math.round(74 + t * (22 - 74));
  return `rgb(${r},${g},${b})`;
}

/* ── Simplified India outline (SVG path) ──────────────────────────────── */
// Major coastline + borders — simplified polygon
function indiaOutlinePath(): string {
  const points: [number, number][] = [
    [32.5, 76.8], // Kashmir
    [34.0, 77.5],
    [33.0, 79.0],
    [31.5, 79.5],
    [30.4, 80.2],
    [29.0, 81.0], // Nepal border
    [28.5, 84.0],
    [27.5, 85.0],
    [27.0, 87.0],
    [26.5, 88.5],
    [26.5, 89.0], // NE
    [28.0, 92.0],
    [27.5, 97.0], // Arunachal
    [25.5, 96.0],
    [24.5, 94.5],
    [22.0, 93.0], // Myanmar border
    [21.0, 92.5],
    [22.0, 91.0], // Bangladesh re-entry
    [24.5, 92.5],
    [25.0, 90.5],
    [26.0, 90.0],
    [26.5, 89.0], // Chicken's neck
    [25.0, 88.5],
    [24.0, 88.5], // Bangladesh west
    [23.5, 88.5],
    [22.0, 88.9], // Kolkata coast
    [21.5, 87.5],
    [20.5, 87.0],
    [19.5, 85.5], // Odisha coast
    [18.5, 84.5],
    [17.5, 83.5], // AP coast
    [16.0, 81.5],
    [15.0, 80.0],
    [14.0, 80.2],
    [13.0, 80.3], // Chennai
    [11.5, 79.8],
    [10.0, 79.3],
    [8.5, 77.5],  // Kanyakumari
    [8.3, 77.0],
    [9.0, 76.3],
    [10.0, 76.0], // Kerala coast
    [11.5, 75.5],
    [12.5, 75.0],
    [14.5, 74.0], // Goa
    [16.0, 73.5],
    [17.5, 73.0],
    [19.0, 73.0], // Mumbai
    [20.5, 73.0],
    [21.0, 72.5],
    [22.5, 69.5], // Gujarat coast
    [23.0, 68.5],
    [23.5, 68.5], // Kutch
    [24.0, 69.0],
    [24.5, 70.0],
    [24.5, 71.0], // Rajasthan border
    [27.0, 70.5],
    [28.0, 70.0],
    [29.5, 71.0],
    [30.5, 73.5],
    [31.5, 74.5],
    [32.5, 76.8], // back to Kashmir
  ];

  return points.map(([lat, lng], i) => {
    const [x, y] = project(lat, lng);
    return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ") + " Z";
}

/* ── Component ─────────────────────────────────────────────────────────── */

export default function IndiaSalesMap({ data }: Props) {
  const [hoveredCity, setHoveredCity] = useState<string | null>(null);

  const { mapped, maxRevenue, totalRevenue } = useMemo(() => {
    if (!data || data.length === 0) return { mapped: [], maxRevenue: 0, totalRevenue: 0 };

    const totalRevenue = data.reduce((s, d) => s + d.total_revenue, 0);
    let maxRev = 0;

    const mapped = data
      .map((d) => {
        const key = d.dimension_name.toLowerCase().trim();
        const coords = CITY_COORDS[key];
        if (!coords) return null;
        const [lat, lng] = coords;
        const [x, y] = project(lat, lng);
        if (d.total_revenue > maxRev) maxRev = d.total_revenue;
        return {
          name: d.dimension_name,
          revenue: d.total_revenue,
          quantity: d.total_quantity,
          share: totalRevenue > 0 ? d.total_revenue / totalRevenue : 0,
          x, y,
        };
      })
      .filter(Boolean) as {
        name: string; revenue: number; quantity: number; share: number; x: number; y: number;
      }[];

    return { mapped, maxRevenue: maxRev, totalRevenue };
  }, [data]);

  if (!data || data.length === 0) {
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

  const outlinePath = indiaOutlinePath();

  // Top 10 cities for sidebar
  const top10 = [...mapped].sort((a, b) => b.revenue - a.revenue).slice(0, 10);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-zinc-100 flex items-center justify-between">
          <span>City-wise Sales Distribution</span>
          <span className="text-[10px] text-zinc-500 font-normal">
            {mapped.length} cities mapped / {data.length} total
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex gap-4">
          {/* ── Map ─────────────────────────────────────────────────── */}
          <div className="flex-1 min-w-0">
            <svg
              viewBox={`0 0 ${SVG_W} ${SVG_H}`}
              className="w-full h-auto"
              style={{ maxHeight: 480 }}
            >
              {/* India outline */}
              <path
                d={outlinePath}
                fill="#1c1c1f"
                stroke="#3f3f46"
                strokeWidth={1.2}
              />

              {/* City bubbles */}
              {mapped.map((c) => {
                const t = maxRevenue > 0 ? c.revenue / maxRevenue : 0;
                const radius = 3 + Math.sqrt(t) * 12;
                const color = interpolateColor(t);
                const isHovered = hoveredCity === c.name;

                return (
                  <g key={c.name}>
                    <circle
                      cx={c.x}
                      cy={c.y}
                      r={isHovered ? radius * 1.4 : radius}
                      fill={color}
                      fillOpacity={isHovered ? 0.95 : 0.75}
                      stroke={isHovered ? "#fff" : color}
                      strokeWidth={isHovered ? 1.5 : 0.5}
                      className="cursor-pointer transition-all duration-150"
                      onMouseEnter={() => setHoveredCity(c.name)}
                      onMouseLeave={() => setHoveredCity(null)}
                    />
                    {/* Label for top cities or hovered */}
                    {(isHovered || c.share > 0.03) && (
                      <text
                        x={c.x}
                        y={c.y - radius - 4}
                        textAnchor="middle"
                        fontSize={isHovered ? 11 : 9}
                        fill="#e4e4e7"
                        fontWeight={isHovered ? 600 : 400}
                        className="pointer-events-none"
                      >
                        {c.name}
                      </text>
                    )}
                  </g>
                );
              })}

              {/* Gradient legend bar */}
              <defs>
                <linearGradient id="salesGradient" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor={interpolateColor(0)} />
                  <stop offset="50%" stopColor={interpolateColor(0.5)} />
                  <stop offset="100%" stopColor={interpolateColor(1)} />
                </linearGradient>
              </defs>
              <g transform={`translate(${SVG_W / 2 - 100}, ${SVG_H - 30})`}>
                <rect width={200} height={10} rx={4} fill="url(#salesGradient)" />
                <text x={0} y={22} fontSize={9} fill="#71717a">Low</text>
                <text x={200} y={22} fontSize={9} fill="#71717a" textAnchor="end">High</text>
                <text x={100} y={22} fontSize={9} fill="#71717a" textAnchor="middle">Revenue Share</text>
              </g>

              {/* Tooltip on hover */}
              {hoveredCity && (() => {
                const c = mapped.find((m) => m.name === hoveredCity);
                if (!c) return null;
                const tw = 140, th = 52;
                let tx = c.x + 15, ty = c.y - 30;
                if (tx + tw > SVG_W - 10) tx = c.x - tw - 15;
                if (ty < 10) ty = c.y + 15;
                return (
                  <g className="pointer-events-none">
                    <rect x={tx} y={ty} width={tw} height={th} rx={6}
                      fill="#18181b" stroke="#3f3f46" strokeWidth={1} />
                    <text x={tx + 8} y={ty + 16} fontSize={11} fill="#e4e4e7" fontWeight={600}>
                      {c.name}
                    </text>
                    <text x={tx + 8} y={ty + 30} fontSize={10} fill="#a1a1aa">
                      {fmtRevenue(c.revenue)} ({(c.share * 100).toFixed(1)}%)
                    </text>
                    <text x={tx + 8} y={ty + 43} fontSize={10} fill="#a1a1aa">
                      {Math.round(c.quantity).toLocaleString("en-IN")} units
                    </text>
                  </g>
                );
              })()}
            </svg>
          </div>

          {/* ── Top 10 sidebar ──────────────────────────────────────── */}
          <div className="w-44 flex-shrink-0">
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">Top 10 Cities</p>
            <div className="space-y-1.5">
              {top10.map((c, i) => (
                <div
                  key={c.name}
                  className="flex items-center gap-2 text-xs cursor-pointer hover:bg-zinc-800/50 rounded px-1.5 py-1"
                  onMouseEnter={() => setHoveredCity(c.name)}
                  onMouseLeave={() => setHoveredCity(null)}
                >
                  <span className="text-zinc-600 w-4 text-right font-mono text-[10px]">{i + 1}</span>
                  <div
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: interpolateColor(maxRevenue > 0 ? c.revenue / maxRevenue : 0) }}
                  />
                  <span className="text-zinc-300 truncate flex-1">{c.name}</span>
                  <span className="text-zinc-500 tabular-nums">{(c.share * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
            <div className="mt-3 pt-2 border-t border-zinc-800">
              <p className="text-[10px] text-zinc-500">Total mapped</p>
              <p className="text-sm text-zinc-200 font-medium">{fmtRevenue(totalRevenue)}</p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
