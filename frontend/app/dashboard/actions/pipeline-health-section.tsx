"use client"

import React, { useState, useEffect } from "react"
import { ChevronRight, ChevronDown } from "lucide-react"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import type { PortalImportHealth, ImportFailure } from "@/lib/api"

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

function formatDate(iso: string | null): string {
  if (!iso) return "Never"
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: false,
    timeZone: "Asia/Kolkata",
  })
}

function StatusBadge({ status }: { status: string | null }) {
  if (status === "success") return <Badge variant="success">Success</Badge>
  if (status === "failed")  return <Badge variant="danger">Failed</Badge>
  if (status === "running") return <Badge variant="default">Running</Badge>
  return <Badge variant="muted">No data</Badge>
}

export function PipelineHealthSection({
  importHealth,
  noApiData,
}: {
  importHealth: PortalImportHealth[]
  noApiData: boolean
}) {
  const [failures, setFailures] = useState<ImportFailure[]>([])
  const [loadingFailures, setLoadingFailures] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${BASE}/api/metadata/import-failures`)
      .then(r => r.ok ? r.json() : [])
      .then(setFailures)
      .catch(() => {})
      .finally(() => setLoadingFailures(false))
  }, [])

  const portalFailures = (name: string) => failures.filter(f => f.portal_name === name)

  return (
    <Card className="bg-zinc-900 border-zinc-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg text-zinc-100">Data Pipeline Health</CardTitle>
        <p className="text-sm text-zinc-400">Last scraper import per portal — click a row to see failure details</p>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow className="border-zinc-800">
              <TableHead className="h-9 px-2 text-zinc-500 font-medium">Portal</TableHead>
              <TableHead className="h-9 px-2 text-zinc-500 font-medium">Last Import</TableHead>
              <TableHead className="h-9 px-2 text-zinc-500 font-medium">Status</TableHead>
              <TableHead className="h-9 px-2 text-right text-zinc-500 font-medium">Total Runs</TableHead>
              <TableHead className="h-9 px-2 text-right text-zinc-500 font-medium">Failures</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {importHealth.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-zinc-600">
                  {noApiData ? "—" : "No import runs recorded yet"}
                </TableCell>
              </TableRow>
            ) : importHealth.map(row => (
              <React.Fragment key={row.portal_name}>
                <TableRow
                  className={`border-zinc-800/50 ${row.failed_runs > 0 ? "cursor-pointer hover:bg-zinc-800/30" : ""}`}
                  onClick={() => row.failed_runs > 0 && setExpanded(
                    expanded === row.portal_name ? null : row.portal_name
                  )}
                >
                  <TableCell className="py-2 px-2 font-medium text-zinc-200">
                    <span className="inline-flex items-center gap-1.5">
                      {/* Always reserve space for chevron so names align */}
                      <span className="w-3.5 h-3.5 flex-shrink-0 inline-flex items-center justify-center">
                        {row.failed_runs > 0 && (
                          expanded === row.portal_name
                            ? <ChevronDown className="w-3.5 h-3.5 text-zinc-500" />
                            : <ChevronRight className="w-3.5 h-3.5 text-zinc-500" />
                        )}
                      </span>
                      {row.display_name}
                    </span>
                  </TableCell>
                  <TableCell className="py-2 px-2 text-zinc-400 text-sm">{formatDate(row.last_import_at)}</TableCell>
                  <TableCell className="py-2 px-2"><StatusBadge status={row.last_status} /></TableCell>
                  <TableCell className="py-2 px-2 text-right text-zinc-400 font-mono text-sm">{row.total_imports}</TableCell>
                  <TableCell className={`py-2 px-2 text-right font-mono text-sm ${row.failed_runs > 0 ? "text-red-400 font-bold" : "text-zinc-500"}`}>
                    {row.failed_runs > 0 ? `${row.failed_runs} ▼` : row.failed_runs}
                  </TableCell>
                </TableRow>

                {expanded === row.portal_name && (
                  <TableRow className="border-zinc-800/50 bg-red-950/10">
                    <TableCell colSpan={5} className="px-4 pb-3 pt-0">
                      {loadingFailures ? (
                        <p className="text-xs text-zinc-600 py-2">Loading…</p>
                      ) : portalFailures(row.portal_name).length === 0 ? (
                        <p className="text-xs text-zinc-600 py-2">No detailed failure records found.</p>
                      ) : (
                        <div className="space-y-2 mt-2">
                          {portalFailures(row.portal_name).map(f => (
                            <div key={f.id} className="bg-red-950/30 border border-red-900/40 rounded-lg p-3">
                              <div className="flex items-center justify-between mb-1.5 gap-2">
                                <span className="text-xs font-mono text-red-400 truncate">
                                  {f.file_name ?? f.source_type}
                                </span>
                                <span className="text-xs text-zinc-500 whitespace-nowrap">{formatDate(f.start_time)}</span>
                              </div>
                              <p className="text-xs text-red-300 font-mono whitespace-pre-wrap break-all leading-relaxed">
                                {f.error_message ?? "No error message recorded"}
                              </p>
                            </div>
                          ))}
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                )}
              </React.Fragment>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
