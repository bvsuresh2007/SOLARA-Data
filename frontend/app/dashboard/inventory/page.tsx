import { api } from "@/lib/api";
import MetricCard from "@/components/charts/metric-card";
import { NavTabs } from "@/components/ui/nav-tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import Link from "next/link";

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
        <NavTabs />
      </header>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Snapshot Records" value={String(inventory.length)} />
        <MetricCard label="Products Tracked" value={String(productCount)} />
        <MetricCard label="Portals Covered"  value={String(portalCount)} />
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
          <Table>
            <TableHeader>
              <TableRow className="border-red-800/50">
                <TableHead className="h-9 px-2 text-red-500 font-medium">Product</TableHead>
                <TableHead className="h-9 px-2 text-red-500 font-medium">SKU</TableHead>
                <TableHead className="h-9 px-2 text-right text-red-500 font-medium">Portal Stock</TableHead>
                <TableHead className="h-9 px-2 text-right text-red-500 font-medium">Portals</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lowStock.slice(0, LOW_STOCK_PREVIEW).map(item => (
                <TableRow key={item.product_id} className="border-red-900/50">
                  <TableCell className="py-2 px-2 font-medium text-red-300">{item.product_name}</TableCell>
                  <TableCell className="py-2 px-2 font-mono text-xs text-red-500">{item.sku_code ?? "—"}</TableCell>
                  <TableCell className="py-2 px-2 text-right text-red-400 font-bold font-mono">{item.total_portal_stock ?? "0"}</TableCell>
                  <TableCell className="py-2 px-2 text-right text-zinc-400">{item.portal_count}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {lowStock.length > LOW_STOCK_PREVIEW && (
            <p className="mt-3 text-xs text-red-600">
              Showing {LOW_STOCK_PREVIEW} of {lowStock.length} products.{" "}
              <Link href="/dashboard/upload" className="underline hover:text-red-400 transition-colors">
                Upload updated stock data
              </Link>{" "}
              to resolve.
            </p>
          )}
        </div>
      )}

      <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-4">
        <h2 className="font-semibold text-zinc-100 mb-4">Current Inventory Snapshot</h2>
        <Table>
          <TableHeader>
            <TableRow className="border-zinc-800">
              <TableHead className="h-9 px-2 text-zinc-500 font-medium">Portal</TableHead>
              <TableHead className="h-9 px-2 text-zinc-500 font-medium">Product</TableHead>
              <TableHead className="h-9 px-2 text-zinc-500 font-medium">Date</TableHead>
              <TableHead className="h-9 px-2 text-right text-zinc-500 font-medium">Portal Stock</TableHead>
              <TableHead className="h-9 px-2 text-right text-zinc-500 font-medium">Backend Stock</TableHead>
              <TableHead className="h-9 px-2 text-right text-zinc-500 font-medium">Solara Stock</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {inventory.slice(0, 50).map(row => {
              const portalStockNum = parseFloat(row.portal_stock ?? "0");
              return (
                <TableRow key={row.id} className="border-zinc-800/50">
                  <TableCell className="py-2 px-2 text-zinc-500 text-xs">{row.portal_name ?? `#${row.portal_id}`}</TableCell>
                  <TableCell className="py-2 px-2 text-zinc-500 text-xs">{row.product_name ?? `#${row.product_id}`}</TableCell>
                  <TableCell className="py-2 px-2 text-zinc-600 text-xs">{row.snapshot_date}</TableCell>
                  <TableCell className={`py-2 px-2 text-right font-mono text-xs font-medium ${portalStockNum === 0 ? "text-red-400" : "text-green-400"}`}>
                    {row.portal_stock ?? "—"}
                  </TableCell>
                  <TableCell className="py-2 px-2 text-right font-mono text-xs text-zinc-500">{row.backend_stock ?? "—"}</TableCell>
                  <TableCell className="py-2 px-2 text-right font-mono text-xs text-zinc-500">{row.solara_stock ?? "—"}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        {inventory.length > 50 && (
          <p className="mt-3 text-xs text-zinc-600">Showing 50 of {inventory.length} records.</p>
        )}
      </div>
    </main>
  );
}
