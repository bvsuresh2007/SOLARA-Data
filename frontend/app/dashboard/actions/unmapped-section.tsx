"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Dialog } from "@/components/ui/dialog"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { UnmappedProduct } from "@/lib/api"

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

type Step = "form" | "confirm"

function FieldRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[120px_1fr] gap-2 text-sm">
      <span className="text-zinc-500">{label}</span>
      <span className="text-zinc-200 font-mono text-xs break-all">{value || "—"}</span>
    </div>
  )
}

export function UnmappedSection({ unmapped }: { unmapped: UnmappedProduct[] }) {
  const router = useRouter()
  const [dialog, setDialog] = useState<UnmappedProduct | null>(null)
  const [step, setStep] = useState<Step>("form")
  const [selectedPortal, setSelectedPortal] = useState("")
  const [portalSku, setPortalSku] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function openDialog(product: UnmappedProduct) {
    setDialog(product)
    setStep("form")
    const slugs = product.missing_portal_slugs.split(",").filter(Boolean)
    setSelectedPortal(slugs.length === 1 ? slugs[0] : "")
    setPortalSku("")
    setError(null)
    setSaving(false)
  }

  function handleReview() {
    if (!selectedPortal) { setError("Select a portal"); return }
    if (!portalSku.trim()) { setError("Enter the portal SKU"); return }
    setError(null)
    setStep("confirm")
  }

  async function handleSave() {
    if (!dialog) return
    setSaving(true)
    setError(null)
    const body = {
      portal_name: selectedPortal,
      portal_sku: portalSku.trim(),
      portal_product_name: dialog.product_name,
      product_id: dialog.product_id,
    }
    try {
      const r = await fetch(`${BASE}/api/metadata/portal-mappings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
      if (!r.ok) {
        const err = await r.json().catch(() => ({}))
        setError(err.detail ?? "Save failed")
        setSaving(false)
        return
      }
      setDialog(null)
      router.refresh()
    } catch {
      setError("Network error")
      setSaving(false)
    }
  }

  // Build display name from slug: "amazon_pi" → "Amazon PI"
  const displayName = (slug: string) =>
    slug.split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")

  return (
    <>
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg text-zinc-100">
            Catalog Products Not Mapped to Portal ({unmapped.length})
          </CardTitle>
          <p className="text-sm text-zinc-400">
            EasyEcom products with no portal SKU entry. Click &quot;Add SKU&quot; to create a mapping.
          </p>
        </CardHeader>
        <CardContent>
          {unmapped.length === 0 ? (
            <div className="py-8 text-center">
              <Badge variant="success" className="text-sm px-4 py-1">All catalog products mapped</Badge>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-zinc-800">
                  <TableHead className="h-9 px-2 text-zinc-500 font-medium">SKU</TableHead>
                  <TableHead className="h-9 px-2 text-zinc-500 font-medium">Product Name</TableHead>
                  <TableHead className="h-9 px-2 text-zinc-500 font-medium">Not Mapped To</TableHead>
                  <TableHead className="h-9 px-2 text-zinc-500 font-medium">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {unmapped.map(row => (
                  <TableRow key={`${row.product_id}`} className="border-zinc-800/50">
                    <TableCell className="py-2 px-2 font-mono text-xs text-zinc-400">{row.sku_code || "—"}</TableCell>
                    <TableCell className="py-2 px-2 text-zinc-200 text-sm">{row.product_name}</TableCell>
                    <TableCell className="py-2 px-2">
                      <div className="flex flex-wrap gap-1">
                        {row.missing_portals.split(", ").map(name => (
                          <Badge key={name} variant="muted" className="text-xs">{name}</Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell className="py-2 px-2">
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 px-2 text-xs border-zinc-700 bg-transparent hover:bg-zinc-800 text-zinc-300"
                        onClick={() => openDialog(row)}
                      >
                        Add SKU
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={!!dialog}
        onClose={() => !saving && setDialog(null)}
        title={step === "confirm" ? "Confirm Portal Mapping" : "Add Portal SKU"}
        maxWidth="max-w-lg"
      >
        {dialog && step === "form" && (
          <div className="space-y-4">
            <div className="bg-zinc-800/60 rounded-lg p-3 space-y-2">
              <FieldRow label="Product"  value={`${dialog.sku_code || "—"} — ${dialog.product_name}`} />
            </div>

            <div className="space-y-1">
              <label className="text-xs text-zinc-400">Portal</label>
              <select
                value={selectedPortal}
                onChange={e => setSelectedPortal(e.target.value)}
                className="w-full h-9 rounded-md border border-zinc-700 bg-zinc-800 px-3 text-sm text-zinc-200 focus:outline-none focus:ring-2 focus:ring-orange-500"
              >
                <option value="">Select portal…</option>
                {dialog.missing_portal_slugs.split(",").filter(Boolean).map(slug => (
                  <option key={slug} value={slug}>{displayName(slug)}</option>
                ))}
              </select>
            </div>

            <div className="space-y-1">
              <label className="text-xs text-zinc-400">Portal SKU</label>
              <Input
                value={portalSku}
                onChange={e => setPortalSku(e.target.value)}
                placeholder="e.g. B0XXXXXXXX or 12345678"
                className="bg-zinc-800 border-zinc-700 text-zinc-100 text-sm h-9 font-mono"
              />
              <p className="text-xs text-zinc-600">Enter the SKU / ASIN / EAN / item_id as it appears in the portal export.</p>
            </div>

            {error && <p className="text-xs text-red-400">{error}</p>}

            <div className="flex justify-end gap-2 pt-2 border-t border-zinc-800">
              <Button variant="ghost" size="sm" onClick={() => setDialog(null)} className="text-zinc-400 hover:text-zinc-200">Cancel</Button>
              <Button size="sm" onClick={handleReview} className="bg-orange-600 hover:bg-orange-700 text-white">
                Review →
              </Button>
            </div>
          </div>
        )}

        {dialog && step === "confirm" && (
          <div className="space-y-4">
            <p className="text-sm text-zinc-300">You are about to write the following to the database:</p>

            <div className="bg-zinc-800/60 rounded-lg p-4 space-y-2 border border-zinc-700">
              <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-2">New Portal Mapping</p>
              <FieldRow label="Product"    value={`${dialog.sku_code} — ${dialog.product_name}`} />
              <FieldRow label="Portal"     value={displayName(selectedPortal)} />
              <FieldRow label="Portal SKU" value={portalSku} />
            </div>

            <p className="text-xs text-zinc-500">
              Table affected: <span className="font-mono text-zinc-400">product_portal_mapping</span>
            </p>

            {error && <p className="text-xs text-red-400">{error}</p>}

            <div className="flex justify-end gap-2 pt-2 border-t border-zinc-800">
              <Button variant="ghost" size="sm" onClick={() => setStep("form")} className="text-zinc-400" disabled={saving}>← Back</Button>
              <Button
                size="sm"
                onClick={handleSave}
                disabled={saving}
                className="bg-green-700 hover:bg-green-600 text-white"
              >
                {saving ? "Saving…" : "✓ Confirm & Save"}
              </Button>
            </div>
          </div>
        )}
      </Dialog>
    </>
  )
}
