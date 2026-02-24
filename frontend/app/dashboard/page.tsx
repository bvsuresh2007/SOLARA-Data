import { api } from "@/lib/api";
import { formatCurrency, formatNumber } from "@/lib/utils";
import MetricCard from "@/components/charts/metric-card";
import SalesBarChart from "@/components/charts/bar-chart";
import { ScrapingStatusTable } from "@/components/tables/data-table";

export const revalidate = 300; // revalidate every 5 min

export default async function DashboardPage() {
  const [summary, byPortal, byProduct, logs] = await Promise.all([
    api.salesSummary().catch(() => ({
      total_revenue: 0, total_net_revenue: 0, total_quantity: 0,
      total_orders: 0, total_discount: 0, record_count: 0,
    })),
    api.salesByPortal().catch(() => []),
    api.salesByProduct().catch(() => []),
    api.scrapingLogs(10).catch(() => []),
  ]);

  return (
    <main className="min-h-screen bg-zinc-950 p-6 space-y-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-zinc-50">SolaraDashboard</h1>
          <p className="text-sm text-zinc-500 mt-0.5">Multi-portal sales &amp; inventory overview</p>
        </div>
        <nav className="flex gap-4 text-sm font-medium">
          <a href="/dashboard"              className="text-orange-400 border-b border-orange-400 pb-0.5">Overview</a>
          <a href="/dashboard/sales"        className="text-zinc-500 hover:text-zinc-200 transition-colors">Sales</a>
          <a href="/dashboard/inventory"    className="text-zinc-500 hover:text-zinc-200 transition-colors">Inventory</a>
          <a href="/dashboard/upload"       className="text-zinc-500 hover:text-zinc-200 transition-colors">Upload</a>
        </nav>
      </header>

      {/* KPI cards */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Total Revenue"    value={formatCurrency(summary.total_revenue)} />
        <MetricCard label="Net Revenue"      value={formatCurrency(summary.total_net_revenue)} />
        <MetricCard label="Total Quantity"   value={formatNumber(summary.total_quantity)} />
        <MetricCard label="Records"          value={formatNumber(summary.record_count)} />
      </section>

      {/* Charts */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-4">
          <h2 className="font-semibold text-zinc-100 mb-4">Revenue by Portal</h2>
          <SalesBarChart
            data={byPortal.map(d => ({ name: d.dimension_name, value: d.total_revenue }))}
            dataKey="value"
            label="Revenue (₹)"
          />
        </div>
        <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-4">
          <h2 className="font-semibold text-zinc-100 mb-4">Top 10 Products by Revenue</h2>
          <SalesBarChart
            data={byProduct.slice(0, 10).map(d => ({ name: d.dimension_name.slice(0, 20), value: d.total_revenue }))}
            dataKey="value"
            label="Revenue (₹)"
          />
        </div>
      </section>

      {/* Top Products Table */}
      <section className="bg-zinc-900 rounded-xl border border-zinc-800 p-4">
        <h2 className="font-semibold text-zinc-100 mb-4">Top Products by Revenue</h2>
        <table className="w-full text-sm">
          <thead className="text-left border-b border-zinc-800">
            <tr>
              <th className="pb-2 text-zinc-500 font-medium">Product</th>
              <th className="pb-2 text-right text-zinc-500 font-medium">Revenue</th>
              <th className="pb-2 text-right text-zinc-500 font-medium">Qty Sold</th>
            </tr>
          </thead>
          <tbody>
            {byProduct.slice(0, 10).map((p, i) => (
              <tr key={p.dimension_id} className="border-b border-zinc-800/50 last:border-0">
                <td className="py-2 text-zinc-200">{i + 1}. {p.dimension_name}</td>
                <td className="py-2 text-right font-mono text-zinc-100">{formatCurrency(p.total_revenue)}</td>
                <td className="py-2 text-right text-zinc-400">{formatNumber(p.total_quantity)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* Scraping Status */}
      <section className="bg-zinc-900 rounded-xl border border-zinc-800 p-4">
        <h2 className="font-semibold text-zinc-100 mb-4">Recent Scraping Jobs</h2>
        <ScrapingStatusTable logs={logs} />
      </section>
    </main>
  );
}
