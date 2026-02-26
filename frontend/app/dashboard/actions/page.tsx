import { api } from "@/lib/api";
import { NavTabs } from "@/components/ui/nav-tabs";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { PipelineHealthSection } from "./pipeline-health-section";
import { SkuGapsSection } from "./sku-gaps-section";
import { UnmappedSection } from "./unmapped-section";

export const revalidate = 300;

export default async function ActionsPage() {
  const data = await api.actionItems().catch(() => null);

  const importHealth   = data?.import_health    ?? [];
  const portalCoverage = data?.portal_coverage  ?? [];
  const unmapped       = data?.unmapped_products ?? [];
  const totalProducts  = data?.total_products    ?? 0;
  const skuGaps        = data?.portal_sku_gaps   ?? [];
  const noApiData      = data === null;

  return (
    <main className="min-h-screen bg-zinc-950 p-6 space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-zinc-50">Actions</h1>
          <p className="text-sm text-zinc-500 mt-0.5">Pipeline health and product mapping gaps</p>
        </div>
        <NavTabs />
      </header>

      {noApiData && (
        <div className="rounded-lg border border-yellow-800 bg-yellow-900/20 px-4 py-3 text-sm text-yellow-400">
          Could not reach the backend API. Restart the backend service and refresh.
        </div>
      )}

      {/* Section A — Data Pipeline Health (client — expandable failure rows) */}
      <PipelineHealthSection importHealth={importHealth} noApiData={noApiData} />

      {/* Section B — Portal Mapping Coverage (static tiles, no mutations needed) */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg text-zinc-100">Portal Mapping Coverage</CardTitle>
          <p className="text-sm text-zinc-400">
            Products from the EasyEcom catalog mapped to each portal
            {totalProducts > 0 && ` — ${totalProducts} products total`}
          </p>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {portalCoverage.length === 0 ? (
              <p className="col-span-4 text-zinc-600 text-sm">
                {noApiData ? "—" : "No portal data"}
              </p>
            ) : portalCoverage.map(p => {
              const pct = p.total_products > 0 ? Math.round((p.mapped_products / p.total_products) * 100) : 0;
              return (
                <div key={p.portal_name} className="bg-zinc-800 rounded-lg p-4 space-y-2">
                  <p className="font-semibold text-zinc-100 text-sm">{p.display_name}</p>
                  <p className="text-2xl font-bold text-zinc-50 font-mono">
                    {p.mapped_products}
                    <span className="text-base font-normal text-zinc-500"> / {p.total_products}</span>
                  </p>
                  <Progress value={pct} className="h-2 bg-zinc-700" />
                  {p.gap === 0
                    ? <Badge variant="success">Full coverage</Badge>
                    : <Badge variant="muted">{p.gap} not on portal</Badge>
                  }
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Section C — Portal SKU Gaps (client — Link / Edit buttons) */}
      <SkuGapsSection skuGaps={skuGaps} />

      {/* Section D — Catalog Products Not Mapped (client — Add SKU buttons) */}
      <UnmappedSection unmapped={unmapped} />
    </main>
  );
}
