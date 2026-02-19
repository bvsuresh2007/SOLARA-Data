import { api } from "@/lib/api";
import { formatNumber } from "@/lib/utils";
import MetricCard from "@/components/charts/metric-card";

export const revalidate = 300;

export default async function InventoryDashboardPage() {
  const [inventory, lowStock] = await Promise.all([
    api.currentInventory(),
    api.lowStock(100),
  ]);

  const totalStock     = inventory.reduce((s, r) => s + r.stock_quantity, 0);
  const totalAvailable = inventory.reduce((s, r) => s + r.available_quantity, 0);
  const totalReserved  = inventory.reduce((s, r) => s + r.reserved_quantity, 0);

  return (
    <main className="p-6 space-y-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Inventory Management</h1>
          <p className="text-sm text-gray-500 mt-0.5">Stock levels, low-stock alerts, and warehouse snapshots</p>
        </div>
        <nav className="flex gap-4 text-sm font-medium">
          <a href="/dashboard"           className="text-gray-500 hover:text-gray-900">Overview</a>
          <a href="/dashboard/sales"     className="text-gray-500 hover:text-gray-900">Sales</a>
          <a href="/dashboard/inventory" className="text-brand-600">Inventory</a>
        </nav>
      </header>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Total Stock"      value={formatNumber(totalStock)} />
        <MetricCard label="Available Stock"  value={formatNumber(totalAvailable)} />
        <MetricCard label="Reserved Stock"   value={formatNumber(totalReserved)} />
        <MetricCard
          label="Low Stock Alerts"
          value={String(lowStock.length)}
          highlight={lowStock.length > 0}
        />
      </section>

      {lowStock.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <h2 className="font-semibold text-red-800 mb-4">
            Low Stock Alert ({lowStock.length} products below threshold)
          </h2>
          <table className="w-full text-sm">
            <thead className="text-left text-red-600 border-b border-red-200">
              <tr>
                <th className="pb-2">Product</th>
                <th className="pb-2">SKU</th>
                <th className="pb-2 text-right">Available</th>
                <th className="pb-2 text-right">Total Stock</th>
                <th className="pb-2 text-right">Portals</th>
              </tr>
            </thead>
            <tbody>
              {lowStock.map(item => (
                <tr key={item.product_id} className="border-b border-red-100 last:border-0">
                  <td className="py-2 font-medium text-red-900">{item.product_name}</td>
                  <td className="py-2 font-mono text-xs text-red-600">{item.sku_code}</td>
                  <td className="py-2 text-right text-red-700 font-bold">{formatNumber(item.total_available)}</td>
                  <td className="py-2 text-right text-gray-600">{formatNumber(item.total_stock)}</td>
                  <td className="py-2 text-right text-gray-600">{item.portal_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <h2 className="font-semibold mb-4">Current Inventory Snapshot</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-gray-500 border-b">
            <tr>
              <th className="pb-2">Portal ID</th>
              <th className="pb-2">Product ID</th>
              <th className="pb-2">Date</th>
              <th className="pb-2 text-right">Stock</th>
              <th className="pb-2 text-right">Available</th>
              <th className="pb-2 text-right">Reserved</th>
            </tr>
          </thead>
          <tbody>
            {inventory.slice(0, 50).map(row => (
              <tr key={row.id} className="border-b last:border-0 hover:bg-gray-50">
                <td className="py-2 text-gray-500 text-xs">{row.portal_id}</td>
                <td className="py-2 text-gray-500 text-xs">{row.product_id}</td>
                <td className="py-2 text-gray-600 text-xs">{row.snapshot_date}</td>
                <td className="py-2 text-right">{formatNumber(row.stock_quantity)}</td>
                <td className={`py-2 text-right font-medium ${row.available_quantity < 50 ? "text-red-600" : "text-green-600"}`}>
                  {formatNumber(row.available_quantity)}
                </td>
                <td className="py-2 text-right text-gray-500">{formatNumber(row.reserved_quantity)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
