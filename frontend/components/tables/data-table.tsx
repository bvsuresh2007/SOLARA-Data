"use client";

import type { ScrapingLog } from "@/lib/api";

const STATUS_CLASSES: Record<string, string> = {
  success: "bg-green-900/40 text-green-400",
  failed:  "bg-red-900/40  text-red-400",
  partial: "bg-yellow-900/40 text-yellow-400",
  running: "bg-blue-900/40  text-blue-400",
};

export function ScrapingStatusTable({ logs }: { logs: ScrapingLog[] }) {
  if (!logs.length) {
    return <p className="text-sm text-zinc-500">No scraping logs found.</p>;
  }
  return (
    <table className="w-full text-sm">
      <thead className="text-left border-b border-zinc-800">
        <tr>
          <th className="pb-2 text-zinc-500 font-medium">Source</th>
          <th className="pb-2 text-zinc-500 font-medium">Date</th>
          <th className="pb-2 text-zinc-500 font-medium">Status</th>
          <th className="pb-2 text-right text-zinc-500 font-medium">Records</th>
          <th className="pb-2 text-zinc-500 font-medium">Error</th>
        </tr>
      </thead>
      <tbody>
        {logs.map(log => (
          <tr key={log.id} className="border-b border-zinc-800/50 last:border-0 hover:bg-zinc-800/30">
            <td className="py-2 text-xs text-zinc-400 max-w-[200px] truncate" title={log.sheet_name ?? log.file_name ?? String(log.portal_id ?? "—")}>
              {log.sheet_name ?? log.file_name ?? `Portal ${log.portal_id ?? "—"}`}
            </td>
            <td className="py-2 text-zinc-400">{log.import_date ?? "—"}</td>
            <td className="py-2">
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_CLASSES[log.status] ?? "bg-zinc-800 text-zinc-400"}`}>
                {log.status}
              </span>
            </td>
            <td className="py-2 text-right text-zinc-300">{(log.records_imported ?? 0).toLocaleString("en-IN")}</td>
            <td className="py-2 text-xs text-red-400 truncate max-w-xs" title={log.error_message ?? ""}>
              {log.error_message ?? "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
