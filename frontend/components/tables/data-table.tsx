"use client";

import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import type { ScrapingLog } from "@/lib/api";

type StatusVariant = "success" | "danger" | "warning" | "default";

const STATUS_VARIANT: Record<string, StatusVariant> = {
  success: "success",
  failed:  "danger",
  partial: "warning",
  running: "default",
};

export function ScrapingStatusTable({ logs }: { logs: ScrapingLog[] }) {
  if (!logs.length) {
    return <p className="text-sm text-zinc-500">No scraping logs found.</p>;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow className="border-zinc-800">
          <TableHead className="h-9 px-2 text-zinc-500 font-medium">Source</TableHead>
          <TableHead className="h-9 px-2 text-zinc-500 font-medium">Date</TableHead>
          <TableHead className="h-9 px-2 text-zinc-500 font-medium">Status</TableHead>
          <TableHead className="h-9 px-2 text-right text-zinc-500 font-medium">Records</TableHead>
          <TableHead className="h-9 px-2 text-zinc-500 font-medium">Error</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {logs.map(log => (
          <TableRow key={log.id} className="border-zinc-800/50">
            <TableCell className="py-2 px-2 text-xs text-zinc-400 max-w-[200px] truncate" title={log.sheet_name ?? log.file_name ?? String(log.portal_id ?? "—")}>
              {log.sheet_name ?? log.file_name ?? `Portal ${log.portal_id ?? "—"}`}
            </TableCell>
            <TableCell className="py-2 px-2 text-xs text-zinc-400">{log.import_date ?? "—"}</TableCell>
            <TableCell className="py-2 px-2">
              <Badge variant={STATUS_VARIANT[log.status] ?? "default"}>
                {log.status}
              </Badge>
            </TableCell>
            <TableCell className="py-2 px-2 text-right text-xs text-zinc-300">
              {(log.records_imported ?? 0).toLocaleString("en-IN")}
            </TableCell>
            <TableCell className="py-2 px-2 text-xs text-red-400 truncate max-w-xs" title={log.error_message ?? ""}>
              {log.error_message ?? "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
