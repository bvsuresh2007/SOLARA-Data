"use client";

import { useEffect, useState, useRef } from "react";
import type { DragEvent, ChangeEvent } from "react";
import {
  Upload, FileSpreadsheet, Check, AlertTriangle, X, Loader2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { NavTabs } from "@/components/ui/nav-tabs";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface FileType {
  value: string;
  label: string;
  description: string;
  target_tables: string[];
}

interface RowError {
  row: number;
  reason: string;
}

interface UploadResult {
  file_type: string;
  file_name: string;
  rows_parsed: number;
  inserted: number;
  skipped: number;
  errors: RowError[];
  import_log_id: number | null;
  time_taken_s: number | null;
}

interface ParseError422 {
  message: string;
  missing_columns?: string[];
  columns_found_in_file?: string[];
}

export default function UploadPage() {
  const [fileTypes, setFileTypes]       = useState<FileType[]>([]);
  const [selectedType, setSelectedType] = useState<string>("");
  const [file, setFile]                 = useState<File | null>(null);
  const [dragging, setDragging]         = useState(false);
  const [uploading, setUploading]       = useState(false);
  const [result, setResult]             = useState<UploadResult | null>(null);
  const [parseError, setParseError]     = useState<ParseError422 | null>(null);
  const [networkError, setNetworkError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch(`${BASE}/api/uploads/types`)
      .then((r) => r.json())
      .then((data: FileType[]) => {
        setFileTypes(data);
        if (data.length > 0) setSelectedType(data[0].value);
      })
      .catch(() => setNetworkError("Could not load file types — is the backend running?"));
  }, []);

  const selectedTypeInfo = fileTypes.find((t) => t.value === selectedType);

  function clearResult() { setResult(null); setParseError(null); setNetworkError(null); }
  function pickFile(f: File) {
    const ext = f.name.split(".").pop()?.toLowerCase() ?? "";
    if (!["xlsx", "xls", "csv"].includes(ext)) {
      clearResult();
      setNetworkError(`Unsupported file type ".${ext}". Please upload an .xlsx, .xls, or .csv file.`);
      return;
    }
    setFile(f); clearResult();
  }
  function onDragOver(e: DragEvent<HTMLDivElement>) { e.preventDefault(); setDragging(true); }
  function onDragLeave(e: DragEvent<HTMLDivElement>) { e.preventDefault(); setDragging(false); }
  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files[0]; if (f) pickFile(f);
  }
  function onInputChange(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]; if (f) pickFile(f); e.target.value = "";
  }

  async function handleUpload() {
    if (!file || !selectedType || uploading) return;
    if (file.size > 50 * 1024 * 1024) {
      setNetworkError(`File too large (${(file.size / 1024 / 1024).toFixed(1)} MB). Max 50 MB.`);
      return;
    }
    setUploading(true); clearResult();
    const form = new FormData(); form.append("file", file);
    try {
      const res = await fetch(`${BASE}/api/uploads/file?file_type=${selectedType}`, { method: "POST", body: form });
      const data = await res.json();
      if (res.status === 422) setParseError(data.detail ?? data);
      else if (res.ok) setResult(data as UploadResult);
      else setNetworkError(`Server error ${res.status}: ${data?.detail ?? "unknown error"}`);
    } catch (err) {
      console.error("[Upload] network error:", err);
      setNetworkError("Network error — could not reach the backend.");
    } finally { setUploading(false); }
  }

  const canUpload = !!file && !!selectedType && !uploading;

  return (
    <main className="min-h-screen bg-zinc-950 p-6 space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-zinc-50">Upload Data</h1>
          <p className="text-sm text-zinc-500 mt-0.5">
            Push portal CSV exports or master Excel directly into the database
          </p>
        </div>
        <NavTabs />
      </header>

      <div className="max-w-2xl space-y-4">
        {/* Step 1 */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-xs text-zinc-500 font-semibold uppercase tracking-widest">
              1 · Select File Type
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {fileTypes.length === 0 && !networkError ? (
              <div className="h-9 rounded-lg bg-zinc-800 animate-pulse" />
            ) : (
              <Select value={selectedType} onValueChange={(v) => { setSelectedType(v); clearResult(); }}>
                <SelectTrigger className="w-full bg-zinc-800 border-zinc-700 text-zinc-100">
                  <SelectValue placeholder="Select file type…" />
                </SelectTrigger>
                <SelectContent>
                  {fileTypes.map((t) => (
                    <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {selectedTypeInfo && (
              <div className="space-y-2 pt-1">
                <p className="text-xs text-zinc-400 leading-relaxed">{selectedTypeInfo.description}</p>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[10px] text-zinc-600 uppercase tracking-wider">Tables:</span>
                  {selectedTypeInfo.target_tables.map((t) => (
                    <Badge key={t} variant="muted">{t}</Badge>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Step 2 */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-xs text-zinc-500 font-semibold uppercase tracking-widest">
              2 · Drop Your File
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div
              onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`relative rounded-xl border-2 border-dashed cursor-pointer transition-all duration-150 p-12 text-center select-none ${
                dragging ? "border-orange-500 bg-orange-500/5"
                  : file ? "border-zinc-600 bg-zinc-800/40"
                  : "border-zinc-700 hover:border-zinc-500 hover:bg-zinc-800/20"
              }`}
            >
              <input ref={fileInputRef} type="file" accept=".xlsx,.xls,.csv" onChange={onInputChange} className="hidden" />
              {file ? (
                <div className="space-y-2">
                  <FileSpreadsheet size={36} className="mx-auto text-orange-400" />
                  <p className="text-zinc-100 font-medium text-sm">{file.name}</p>
                  <p className="text-zinc-500 text-xs">{(file.size / 1024).toFixed(1)} KB</p>
                  <Button
                    variant="ghost" size="sm"
                    onClick={(e) => { e.stopPropagation(); setFile(null); clearResult(); }}
                    className="text-xs text-zinc-600 hover:text-zinc-300 h-auto py-1"
                  >
                    Remove
                  </Button>
                </div>
              ) : (
                <div className="space-y-3">
                  <Upload size={36} className={`mx-auto transition-colors ${dragging ? "text-orange-400" : "text-zinc-600"}`} />
                  <div>
                    <p className="text-zinc-300 text-sm font-medium">Drag & drop or click to browse</p>
                    <p className="text-zinc-600 text-xs mt-1">.xlsx · .xls · .csv</p>
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Upload button */}
        <Button onClick={handleUpload} disabled={!canUpload} className="w-full rounded-xl py-6 text-sm font-semibold">
          {uploading ? <><Loader2 size={16} className="animate-spin" />Uploading…</> : <><Upload size={16} />Upload File</>}
        </Button>

        {networkError && (
          <div className="flex items-start gap-3 rounded-xl border border-red-800 bg-red-950/30 px-4 py-3">
            <X size={16} className="text-red-400 mt-0.5 flex-shrink-0" />
            <p className="text-sm text-red-300">{networkError}</p>
          </div>
        )}

        {parseError && (
          <Card className="border-red-800">
            <CardHeader className="pb-2">
              <CardTitle className="text-red-400 text-sm flex items-center gap-2">
                <X size={16} />Column Mismatch — File Not Imported
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-xs">
              <p className="text-zinc-300 leading-relaxed">{parseError.message}</p>
              {parseError.missing_columns && parseError.missing_columns.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-[10px] text-zinc-600 uppercase tracking-wider">Expected (missing from file)</p>
                  <div className="flex flex-wrap gap-1.5">
                    {parseError.missing_columns.map((c) => (
                      <span key={c} className="bg-red-900/40 text-red-300 border border-red-800 rounded px-2 py-0.5 font-mono text-[11px]">{c}</span>
                    ))}
                  </div>
                </div>
              )}
              {parseError.columns_found_in_file && parseError.columns_found_in_file.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-[10px] text-zinc-600 uppercase tracking-wider">Columns found in uploaded file</p>
                  <div className="flex flex-wrap gap-1.5">
                    {parseError.columns_found_in_file.map((c) => (
                      <span key={c} className="bg-zinc-800 text-zinc-400 rounded px-2 py-0.5 font-mono text-[11px]">{c}</span>
                    ))}
                  </div>
                </div>
              )}
              <p className="text-zinc-600 leading-relaxed">
                Common causes: wrong file type selected, portal changed their export format, or file was re-saved in Excel.
              </p>
            </CardContent>
          </Card>
        )}

        {result && (
          <Card className={result.inserted > 0 ? "border-green-800" : "border-zinc-700"}>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2">
                {result.inserted > 0
                  ? <Check size={16} className="text-green-400" />
                  : <AlertTriangle size={16} className="text-yellow-400" />}
                <span className="text-zinc-100">
                  {result.inserted > 0 ? "Import Complete" : "No New Rows — All Duplicates"}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid grid-cols-3 gap-4 text-center">
                <div>
                  <p className="text-3xl font-bold text-green-400">{result.inserted}</p>
                  <p className="text-xs text-zinc-500 mt-1">Inserted</p>
                </div>
                <div>
                  <p className="text-3xl font-bold text-zinc-400">{result.skipped}</p>
                  <p className="text-xs text-zinc-500 mt-1">Skipped</p>
                </div>
                <div>
                  <p className={`text-3xl font-bold ${result.errors.length > 0 ? "text-yellow-400" : "text-zinc-700"}`}>
                    {result.errors.length}
                  </p>
                  <p className="text-xs text-zinc-500 mt-1">Errors</p>
                </div>
              </div>

              {result.rows_parsed > 0 && (
                <div>
                  <div className="h-2 bg-zinc-800 rounded-full overflow-hidden flex">
                    <div className="h-full bg-green-500 transition-all" style={{ width: `${(result.inserted / result.rows_parsed) * 100}%` }} />
                    <div className="h-full bg-zinc-600 transition-all" style={{ width: `${(result.skipped / result.rows_parsed) * 100}%` }} />
                    {result.errors.length > 0 && (
                      <div className="h-full bg-yellow-600 transition-all" style={{ width: `${(result.errors.length / result.rows_parsed) * 100}%` }} />
                    )}
                  </div>
                  <div className="flex items-center gap-4 mt-2 text-[10px] text-zinc-500">
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500 inline-block" />Inserted</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-zinc-600 inline-block" />Skipped (duplicate)</span>
                    {result.errors.length > 0 && (
                      <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-yellow-600 inline-block" />Errors</span>
                    )}
                    <span className="ml-auto">{result.rows_parsed} rows parsed</span>
                  </div>
                </div>
              )}

              {result.errors.length > 0 && (
                <div>
                  <p className="text-xs text-yellow-400 font-medium mb-2 flex items-center gap-1.5">
                    <AlertTriangle size={12} />
                    {result.errors.length} row{result.errors.length !== 1 ? "s" : ""} skipped — unmapped SKUs or bad data
                  </p>
                  <div className="max-h-48 overflow-y-auto rounded-lg bg-zinc-800/50 p-3 space-y-1.5">
                    {result.errors.slice(0, 50).map((e, i) => (
                      <div key={i} className="flex gap-3 text-xs">
                        <span className="text-zinc-600 w-14 flex-shrink-0 font-mono">row {e.row}</span>
                        <span className="text-zinc-400">{e.reason}</span>
                      </div>
                    ))}
                    {result.errors.length > 50 && (
                      <p className="text-zinc-600 text-xs pt-1">…and {result.errors.length - 50} more</p>
                    )}
                  </div>
                </div>
              )}

              <div className="flex items-center gap-4 text-[10px] text-zinc-600">
                {result.import_log_id && (
                  <span>Audit log ID: {result.import_log_id}</span>
                )}
                {result.time_taken_s != null && (
                  <span className="ml-auto">Processed in {result.time_taken_s}s</span>
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </main>
  );
}
