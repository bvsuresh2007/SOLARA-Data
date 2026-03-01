import { SalesContent } from "@/components/sales/sales-content";

// Force dynamic rendering — standalone output + Cloud Run doesn't serve
// prerendered static HTML correctly, causing 404 on direct URL access.
export const dynamic = "force-dynamic";

export default function SalesDashboardPage() {
  return <SalesContent />;
}
