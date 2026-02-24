import { api } from "@/lib/api";
import { formatCurrency, formatNumber } from "@/lib/utils";
import MetricCard from "@/components/charts/metric-card";
import SalesBarChart from "@/components/charts/bar-chart";
import { ScrapingStatusTable } from "@/components/tables/data-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NavTabs } from "@/components/ui/nav-tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

export const revalidate = 300;

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
        <NavTabs />
      </header>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Total Revenue"  value={formatCurrency(summary.total_revenue)} />
        <MetricCard label="Net Revenue"    value={formatCurrency(summary.total_net_revenue)} />
        <MetricCard label="Total Quantity" value={formatNumber(summary.total_quantity)} />
        <MetricCard label="Records"        value={formatNumber(summary.record_count)} />
      </section>

      <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Revenue by Portal</CardTitle>
          </CardHeader>
          <CardContent>
            <SalesBarChart
              data={byPortal.map(d => ({ name: d.dimension_name, value: d.total_revenue }))}
              dataKey="value"
              label="Revenue"
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Top 10 Products by Revenue</CardTitle>
          </CardHeader>
          <CardContent>
            <SalesBarChart
              data={byProduct.slice(0, 10).map(d => ({ name: d.dimension_name.slice(0, 20), value: d.total_revenue }))}
              dataKey="value"
              label="Revenue"
            />
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Top Products by Revenue</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          <Table>
            <TableHeader>
              <TableRow className="border-zinc-800">
                <TableHead className="h-9 px-2 text-zinc-500 font-medium">Product</TableHead>
                <TableHead className="h-9 px-2 text-right text-zinc-500 font-medium">Revenue</TableHead>
                <TableHead className="h-9 px-2 text-right text-zinc-500 font-medium">Qty Sold</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {byProduct.slice(0, 10).map((p, i) => (
                <TableRow key={p.dimension_id} className="border-zinc-800/50">
                  <TableCell className="py-2 px-2 text-zinc-200">{i + 1}. {p.dimension_name}</TableCell>
                  <TableCell className="py-2 px-2 text-right font-mono text-zinc-100">{formatCurrency(p.total_revenue)}</TableCell>
                  <TableCell className="py-2 px-2 text-right text-zinc-400">{formatNumber(p.total_quantity)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Recent Scraping Jobs</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          <ScrapingStatusTable logs={logs} />
        </CardContent>
      </Card>
    </main>
  );
}
