import { api } from "@/lib/api";
import { formatCurrency, formatNumber } from "@/lib/utils";
import MetricCard from "@/components/charts/metric-card";
import SalesBarChart from "@/components/charts/bar-chart";
import { ScrapingStatusTable } from "@/components/tables/data-table";

export const revalidate = 300; // revalidate every 5 min

export default async function DashboardPage() {
  const [summary, byPortal, byCity, byProduct, logs] = await Promise.all([
    api.salesSummary(),
    api.salesByPortal(),
    api.salesByCity(),
    api.salesByProduct(),
    api.scrapingLogs(10),
  ]);

  return (
    <main className="p-6 space-y-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">SolaraDashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">Multi-portal sales & inventory overview</p>
        </div>
        <nav className="flex gap-4 text-sm font-medium">
          <a href="/dashboard"           className="text-brand-600">Overview</a>
          <a href="/dashboard/sales"     className="text-gray-500 hover:text-gray-900">Sales</a>
          <a href="/dashboard/inventory" className="text-gray-500 hover:text-gray-900">Inventory</a>
        </nav>
      </header>

      {/* KPI cards */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Total Revenue"    value={formatCurrency(summary.total_revenue)}   />
        <MetricCard label="Net Revenue"      value={formatCurrency(summary.total_net_revenue)} />
        <MetricCard label="Total Orders"     value={formatNumber(summary.total_orders)}       />
        <MetricCard label="Total Quantity"   value={formatNumber(summary.total_quantity)}     />
      </section>

      {/* Charts */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <h2 className="font-semibold mb-4">Revenue by Portal</h2>
          <SalesBarChart
            data={byPortal.map(d => ({ name: d.dimension_name, value: d.total_revenue }))}
            dataKey="value"
            label="Revenue (₹)"
          />
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <h2 className="font-semibold mb-4">Top 10 Cities by Revenue</h2>
          <SalesBarChart
            data={byCity.slice(0, 10).map(d => ({ name: d.dimension_name, value: d.total_revenue }))}
            dataKey="value"
            label="Revenue (₹)"
          />
        </div>
      </section>

      {/* Top Products */}
      <section className="bg-white rounded-xl border border-gray-200 p-4">
        <h2 className="font-semibold mb-4">Top Products by Revenue</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-gray-500 border-b">
            <tr>
              <th className="pb-2">Product</th>
              <th className="pb-2 text-right">Revenue</th>
              <th className="pb-2 text-right">Qty Sold</th>
              <th className="pb-2 text-right">Orders</th>
            </tr>
          </thead>
          <tbody>
            {byProduct.slice(0, 10).map((p, i) => (
              <tr key={p.dimension_id} className="border-b last:border-0">
                <td className="py-2 text-gray-900">{i + 1}. {p.dimension_name}</td>
                <td className="py-2 text-right font-mono">{formatCurrency(p.total_revenue)}</td>
                <td className="py-2 text-right text-gray-600">{formatNumber(p.total_quantity)}</td>
                <td className="py-2 text-right text-gray-600">{formatNumber(p.total_orders)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* Scraping Status */}
      <section className="bg-white rounded-xl border border-gray-200 p-4">
        <h2 className="font-semibold mb-4">Recent Scraping Jobs</h2>
        <ScrapingStatusTable logs={logs} />
      </section>
    </main>
  );
}
