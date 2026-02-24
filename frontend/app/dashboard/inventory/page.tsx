import { api } from "@/lib/api";
import MetricCard from "@/components/charts/metric-card";

export const revalidate = 300;

const LOW_STOCK_PREVIEW = 20;

export default async function InventoryDashboardPage() {
  const [inventory, lowStock] = await Promise.all([
    api.currentInventory().catch(() => []),
    api.lowStock(100).catch(() => []),
  ]);

  const productCount = new Set(inventory.map(r => r.product_id)).size;
  const portalCount  = new Set(inventory.map(r => r.portal_id)).size;

  return (
    <main className="min-h-screen bg-zinc-950 p-6 space-y-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-zinc-50">Inventory Management</h1>
          <p className="text-sm text-zinc-500 mt-0.5">Stock levels, low-stock alerts, and warehouse snapshots</p>
        </div>
        <nav className="flex gap-4 text-sm font-medium">
          <a href="/dashboard"              className="text-zinc-500 hover:text-zinc-200 transition-colors">Overview</a>
          <a href="/dashboard/sales"        className="text-zinc-500 hover:text-zinc-200 transition-colors">Sales</a>
          <a href="/dashboard/inventory"    className="text-orange-400 border-b border-orange-400 pb-0.5">Inventory</a>
          <a href="/dashboard/upload"       className="text-zinc-500 hover:text-zinc-200 transition-colors">Upload</a>
        </nav>
      </header>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Snapshot Records"  value={String(inventory.length)} />
        <MetricCard label="Products Tracked"  value={String(productCount)} />
        <MetricCard label="Portals Covered"   value={String(portalCount)} />
        <MetricCard
          label="Low Stock Alerts"
          value={String(lowStock.length)}
          highlight={lowStock.length > 0}
        />
      </section>

      {lowStock.length > 0 && (
        <div className="bg-red-950/30 border border-red-800 rounded-xl p-4">
          <h2 className="font-semibold text-red-400 mb-4">
            Low Stock Alert — {lowStock.length} products at zero portal stock
          </h2>
          <table className="w-full text-sm">
            <thead className="text-left border-b border-red-800/50">
              <tr>
                <th className="pb-2 text-red-500 font-medium">Product</th>
                <th className="pb-2 text-red-500 font-medium">SKU</th>
                <th className="pb-2 text-right text-red-500 font-medium">Portal Stock</th>
                <th className="pb-2 text-right text-red-500 font-medium">Portals</th>
              </tr>
            </thead>
            <tbody>
              {lowStock.slice(0, LOW_STOCK_PREVIEW).map(item => (
                <tr key={item.product_id} className="border-b border-red-900/50 last:border-0">
                  <td className="py-2 font-medium text-red-300">{item.product_name}</td>
                  <td className="py-2 font-mono text-xs text-red-500">{item.sku_code ?? "—"}</td>
                  <td className="py-2 text-right text-red-400 font-bold font-mono">{item.total_portal_stock ?? "0"}</td>
                  <td className="py-2 text-right text-zinc-400">{item.portal_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {lowStock.length > LOW_STOCK_PREVIEW && (
            <p className="mt-3 text-xs text-red-600">
              Showing {LOW_STOCK_PREVIEW} of {lowStock.length} products.{" "}
              <a href="/dashboard/upload" className="underline hover:text-red-400 transition-colors">
                Upload updated stock data
              </a>{" "}
              to resolve.
            </p>
          )}
        </div>
      )}

      <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-4">
        <h2 className="font-semibold text-zinc-100 mb-4">Current Inventory Snapshot</h2>
        <table className="w-full text-sm">
          <thead className="text-left border-b border-zinc-800">
            <tr>
              <th className="pb-2 text-zinc-500 font-medium">Portal</th>
              <th className="pb-2 text-zinc-500 font-medium">Product</th>
              <th className="pb-2 text-zinc-500 font-medium">Date</th>
              <th className="pb-2 text-right text-zinc-500 font-medium">Portal Stock</th>
              <th className="pb-2 text-right text-zinc-500 font-medium">Backend Stock</th>
              <th className="pb-2 text-right text-zinc-500 font-medium">Solara Stock</th>
            </tr>
          </thead>
          <tbody>
            {inventory.slice(0, 50).map(row => {
              const portalStockNum = parseFloat(row.portal_stock ?? "0");
              return (
                <tr key={row.id} className="border-b border-zinc-800/50 last:border-0 hover:bg-zinc-800/30">
                  <td className="py-2 text-zinc-500 text-xs">#{row.portal_id}</td>
                  <td className="py-2 text-zinc-500 text-xs">#{row.product_id}</td>
                  <td className="py-2 text-zinc-600 text-xs">{row.snapshot_date}</td>
                  <td className={`py-2 text-right font-mono text-xs font-medium ${portalStockNum === 0 ? "text-red-400" : "text-green-400"}`}>
                    {row.portal_stock ?? "—"}
                  </td>
                  <td className="py-2 text-right font-mono text-xs text-zinc-500">
                    {row.backend_stock ?? "—"}
                  </td>
                  <td className="py-2 text-right font-mono text-xs text-zinc-500">
                    {row.solara_stock ?? "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {inventory.length > 50 && (
          <p className="mt-3 text-xs text-zinc-600">Showing 50 of {inventory.length} records.</p>
        )}
      </div>
    </main>
  );
}
