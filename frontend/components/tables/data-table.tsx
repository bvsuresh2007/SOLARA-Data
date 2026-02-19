"use client";

import type { ScrapingLog } from "@/lib/api";

const STATUS_CLASSES: Record<string, string> = {
  success: "bg-green-100 text-green-800",
  failed:  "bg-red-100  text-red-800",
  partial: "bg-yellow-100 text-yellow-800",
  running: "bg-blue-100  text-blue-800",
};

export function ScrapingStatusTable({ logs }: { logs: ScrapingLog[] }) {
  if (!logs.length) {
    return <p className="text-sm text-gray-500">No scraping logs found.</p>;
  }
  return (
    <table className="w-full text-sm">
      <thead className="text-left text-gray-500 border-b">
        <tr>
          <th className="pb-2">Portal</th>
          <th className="pb-2">Date</th>
          <th className="pb-2">Status</th>
          <th className="pb-2 text-right">Records</th>
          <th className="pb-2">Error</th>
        </tr>
      </thead>
      <tbody>
        {logs.map(log => (
          <tr key={log.id} className="border-b last:border-0 hover:bg-gray-50">
            <td className="py-2 font-mono text-xs text-gray-600">{log.portal_id ?? "—"}</td>
            <td className="py-2 text-gray-600">{log.scrape_date}</td>
            <td className="py-2">
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_CLASSES[log.status] ?? "bg-gray-100 text-gray-600"}`}>
                {log.status}
              </span>
            </td>
            <td className="py-2 text-right text-gray-700">{log.records_processed.toLocaleString("en-IN")}</td>
            <td className="py-2 text-xs text-red-600 truncate max-w-xs" title={log.error_message ?? ""}>
              {log.error_message ?? "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
