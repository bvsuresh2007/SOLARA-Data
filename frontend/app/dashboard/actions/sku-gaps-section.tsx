"use client"

import { useState, useEffect, useMemo } from "react"
import { useRouter } from "next/navigation"
import { Dialog } from "@/components/ui/dialog"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

interface PortalSkuGap {
  portal: string; portal_sku: string; portal_name: string
  matched_sol_sku: string; matched_name: string
  score: number; status: string
}
interface Product { id: number; sku_code: string; product_name: string }

type Step = "form" | "confirm"

function GapStatusBadge({ status }: { status: string }) {
  if (status === "UNMATCHED")      return <Badge variant="danger">Unmatched</Badge>
  if (status === "LOW_CONFIDENCE") return <Badge variant="warning">Low confidence</Badge>
  return <Badge variant="muted">{status}</Badge>
}

function FieldRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[120px_1fr] gap-2 text-sm">
      <span className="text-zinc-500">{label}</span>
      <span className="text-zinc-200 font-mono text-xs break-all">{value || "—"}</span>
    </div>
  )
}

export function SkuGapsSection({ skuGaps }: { skuGaps: PortalSkuGap[] }) {
  const router = useRouter()
  const [products, setProducts] = useState<Product[]>([])
  const [dialog, setDialog] = useState<PortalSkuGap | null>(null)
  const [step, setStep] = useState<Step>("form")
  const [createMode, setCreateMode] = useState(false)
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [search, setSearch] = useState("")
  const [newSkuCode, setNewSkuCode] = useState("")
  const [newProductName, setNewProductName] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${BASE}/api/sales/products`)
      .then(r => r.ok ? r.json() : [])
      .then(setProducts)
      .catch(() => {})
  }, [])

  const filteredProducts = useMemo(() => {
    if (search.length < 2) return []
    const q = search.toLowerCase()
    return products
      .filter(p => p.product_name.toLowerCase().includes(q) || p.sku_code.toLowerCase().includes(q))
      .slice(0, 8)
  }, [products, search])

  function openDialog(gap: PortalSkuGap) {
    setDialog(gap)
    setStep("form")
    setCreateMode(gap.status === "UNMATCHED")
    setSelectedProduct(null)
    setSearch("")
    setNewSkuCode("")
    setNewProductName(gap.portal_name.slice(0, 120))
    setError(null)
    setSaving(false)
  }

  function handleReview() {
    if (createMode) {
      if (!newSkuCode.trim()) { setError("Enter a SOL-SKU code"); return }
      if (!newProductName.trim()) { setError("Enter a product name"); return }
    } else {
      if (!selectedProduct) { setError("Select a product from search results"); return }
    }
    setError(null)
    setStep("confirm")
  }

  async function handleSave() {
    if (!dialog) return
    setSaving(true)
    setError(null)
    const body = createMode
      ? { portal_name: dialog.portal, portal_sku: dialog.portal_sku, portal_product_name: dialog.portal_name, new_sku_code: newSkuCode.trim(), new_product_name: newProductName.trim() }
      : { portal_name: dialog.portal, portal_sku: dialog.portal_sku, portal_product_name: dialog.portal_name, product_id: selectedProduct!.id }

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

  const unmatched = skuGaps.filter(g => g.status === "UNMATCHED")
  const lowConf   = skuGaps.filter(g => g.status === "LOW_CONFIDENCE")

  return (
    <>
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center gap-3">
            <CardTitle className="text-lg text-zinc-100">Portal SKUs Missing from Product Catalog</CardTitle>
            {unmatched.length > 0 && <Badge variant="danger">{unmatched.length} unmatched</Badge>}
            {lowConf.length > 0  && <Badge variant="warning">{lowConf.length} low confidence</Badge>}
          </div>
          <p className="text-sm text-zinc-400 mt-1">
            Portal SKUs that couldn&apos;t be matched to any EasyEcom product. Sales for these SKUs is not captured.
          </p>
        </CardHeader>
        <CardContent>
          {skuGaps.length === 0 ? (
            <p className="py-6 text-center text-zinc-600 text-sm">All portal SKUs matched</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-zinc-800">
                  <TableHead className="h-9 px-2 text-zinc-500 font-medium">Portal</TableHead>
                  <TableHead className="h-9 px-2 text-zinc-500 font-medium">Portal SKU</TableHead>
                  <TableHead className="h-9 px-2 text-zinc-500 font-medium">Product Name on Portal</TableHead>
                  <TableHead className="h-9 px-2 text-zinc-500 font-medium">Status</TableHead>
                  <TableHead className="h-9 px-2 text-right text-zinc-500 font-medium">Score</TableHead>
                  <TableHead className="h-9 px-2 text-zinc-500 font-medium">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {skuGaps.map((row, i) => (
                  <TableRow key={`${row.portal}-${row.portal_sku}-${i}`} className="border-zinc-800/50">
                    <TableCell className="py-2 px-2 text-zinc-300 capitalize text-sm">{row.portal}</TableCell>
                    <TableCell className="py-2 px-2 font-mono text-xs text-zinc-400">{row.portal_sku}</TableCell>
                    <TableCell className="py-2 px-2 text-zinc-300 text-sm max-w-xs truncate" title={row.portal_name}>{row.portal_name}</TableCell>
                    <TableCell className="py-2 px-2"><GapStatusBadge status={row.status} /></TableCell>
                    <TableCell className="py-2 px-2 text-right font-mono text-xs text-zinc-500">{(row.score * 100).toFixed(0)}%</TableCell>
                    <TableCell className="py-2 px-2">
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 px-2 text-xs border-zinc-700 bg-transparent hover:bg-zinc-800 text-zinc-300"
                        onClick={() => openDialog(row)}
                      >
                        {row.status === "UNMATCHED" ? "Link Product" : "Edit Mapping"}
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
        title={step === "confirm" ? "Confirm Mapping" : (dialog?.status === "UNMATCHED" ? "Link Portal SKU to Product" : "Edit Portal SKU Mapping")}
        maxWidth="max-w-xl"
      >
        {dialog && step === "form" && (
          <div className="space-y-4">
            {/* Portal SKU info */}
            <div className="bg-zinc-800/60 rounded-lg p-3 space-y-2">
              <FieldRow label="Portal"      value={dialog.portal} />
              <FieldRow label="Portal SKU"  value={dialog.portal_sku} />
              <FieldRow label="Portal name" value={dialog.portal_name} />
              {dialog.status === "LOW_CONFIDENCE" && dialog.matched_sol_sku && (
                <div className="pt-1 border-t border-zinc-700">
                  <p className="text-xs text-yellow-500 mb-1">Current match ({(dialog.score * 100).toFixed(0)}% confidence):</p>
                  <FieldRow label="SOL-SKU"   value={dialog.matched_sol_sku} />
                  <FieldRow label="Name"      value={dialog.matched_name} />
                </div>
              )}
            </div>

            {/* Mode toggle */}
            <div className="flex gap-2">
              <button
                onClick={() => { setCreateMode(false); setError(null) }}
                className={`text-xs px-3 py-1.5 rounded-md transition-colors ${!createMode ? "bg-zinc-700 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"}`}
              >
                Link existing product
              </button>
              <button
                onClick={() => { setCreateMode(true); setError(null) }}
                className={`text-xs px-3 py-1.5 rounded-md transition-colors ${createMode ? "bg-zinc-700 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"}`}
              >
                Create new product
              </button>
            </div>

            {!createMode ? (
              <div className="space-y-2">
                <label className="text-xs text-zinc-400">Search products</label>
                <Input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Type SKU or product name…"
                  className="bg-zinc-800 border-zinc-700 text-zinc-100 text-sm h-9"
                />
                {filteredProducts.length > 0 && (
                  <div className="rounded-md border border-zinc-700 overflow-hidden">
                    {filteredProducts.map(p => (
                      <button
                        key={p.id}
                        onClick={() => { setSelectedProduct(p); setSearch(`${p.sku_code} — ${p.product_name}`) }}
                        className={`w-full text-left px-3 py-2 text-xs hover:bg-zinc-700 transition-colors ${selectedProduct?.id === p.id ? "bg-zinc-700" : "bg-zinc-800"}`}
                      >
                        <span className="font-mono text-orange-400">{p.sku_code}</span>
                        <span className="text-zinc-300 ml-2">{p.product_name}</span>
                      </button>
                    ))}
                  </div>
                )}
                {selectedProduct && (
                  <p className="text-xs text-green-400">✓ Selected: {selectedProduct.sku_code}</p>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                <div className="space-y-1">
                  <label className="text-xs text-zinc-400">New SOL-SKU code</label>
                  <Input
                    value={newSkuCode}
                    onChange={e => setNewSkuCode(e.target.value)}
                    placeholder="e.g. SOL-INS-WB-XXX"
                    className="bg-zinc-800 border-zinc-700 text-zinc-100 text-sm h-9 font-mono"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-zinc-400">Product name</label>
                  <Input
                    value={newProductName}
                    onChange={e => setNewProductName(e.target.value)}
                    placeholder="Product name"
                    className="bg-zinc-800 border-zinc-700 text-zinc-100 text-sm h-9"
                  />
                </div>
              </div>
            )}

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
              <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-2">Portal Mapping</p>
              <FieldRow label="Portal"     value={dialog.portal} />
              <FieldRow label="Portal SKU" value={dialog.portal_sku} />
              <FieldRow label="Portal name" value={dialog.portal_name} />
            </div>

            <div className="bg-zinc-800/60 rounded-lg p-4 space-y-2 border border-zinc-700">
              <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-2">
                {createMode ? "New Product (will be created)" : "Existing Product (will be linked)"}
              </p>
              {createMode ? (
                <>
                  <FieldRow label="SKU"  value={newSkuCode} />
                  <FieldRow label="Name" value={newProductName} />
                </>
              ) : (
                <>
                  <FieldRow label="SKU"  value={selectedProduct!.sku_code} />
                  <FieldRow label="Name" value={selectedProduct!.product_name} />
                </>
              )}
            </div>

            <p className="text-xs text-zinc-500">
              Tables affected: <span className="font-mono text-zinc-400">product_portal_mapping</span>
              {createMode && <>, <span className="font-mono text-zinc-400">products</span></>}
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
