import { api } from "@/lib/api";
import { formatCurrency, formatNumber } from "@/lib/utils";
import MetricCard from "@/components/charts/metric-card";
import SalesBarChart from "@/components/charts/bar-chart";

export const revalidate = 300;

export default async function SalesDashboardPage() {
  const [summary, byPortal, byCity, byProduct] = await Promise.all([
    api.salesSummary(),
    api.salesByPortal(),
    api.salesByCity(),
    api.salesByProduct({ limit: "20" }),
  ]);

  return (
    <main className="p-6 space-y-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Sales Analytics</h1>
          <p className="text-sm text-gray-500 mt-0.5">Revenue, quantity, and order breakdown across all portals</p>
        </div>
        <nav className="flex gap-4 text-sm font-medium">
          <a href="/dashboard"           className="text-gray-500 hover:text-gray-900">Overview</a>
          <a href="/dashboard/sales"     className="text-brand-600">Sales</a>
          <a href="/dashboard/inventory" className="text-gray-500 hover:text-gray-900">Inventory</a>
        </nav>
      </header>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Gross Revenue"   value={formatCurrency(summary.total_revenue)} />
        <MetricCard label="Net Revenue"     value={formatCurrency(summary.total_net_revenue)} />
        <MetricCard label="Total Discounts" value={formatCurrency(summary.total_discount)} />
        <MetricCard label="Total Orders"    value={formatNumber(summary.total_orders)} />
      </section>

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
          <h2 className="font-semibold mb-4">Orders by Portal</h2>
          <SalesBarChart
            data={byPortal.map(d => ({ name: d.dimension_name, value: d.total_orders }))}
            dataKey="value"
            label="Orders"
            color="#6366f1"
          />
        </div>
      </section>

      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <h2 className="font-semibold mb-4">Top 15 Cities</h2>
        <SalesBarChart
          data={byCity.slice(0, 15).map(d => ({ name: d.dimension_name, value: d.total_revenue }))}
          dataKey="value"
          label="Revenue (₹)"
          horizontal
        />
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <h2 className="font-semibold mb-4">Top 20 Products</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-gray-500 border-b">
            <tr>
              <th className="pb-2">#</th>
              <th className="pb-2">Product</th>
              <th className="pb-2 text-right">Gross Revenue</th>
              <th className="pb-2 text-right">Net Revenue</th>
              <th className="pb-2 text-right">Qty Sold</th>
              <th className="pb-2 text-right">Orders</th>
            </tr>
          </thead>
          <tbody>
            {byProduct.map((p, i) => (
              <tr key={p.dimension_id} className="border-b last:border-0 hover:bg-gray-50">
                <td className="py-2 text-gray-400 text-xs">{i + 1}</td>
                <td className="py-2 font-medium">{p.dimension_name}</td>
                <td className="py-2 text-right font-mono text-sm">{formatCurrency(p.total_revenue)}</td>
                <td className="py-2 text-right font-mono text-sm text-green-600">{formatCurrency(p.total_net_revenue)}</td>
                <td className="py-2 text-right text-gray-600">{formatNumber(p.total_quantity)}</td>
                <td className="py-2 text-right text-gray-600">{formatNumber(p.total_orders)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
