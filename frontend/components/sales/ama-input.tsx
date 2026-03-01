"use client";

import { useState, useRef, useEffect } from "react";
import { Sparkles, X, ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import type { AMAResponse } from "@/lib/api";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Props {
  startDate?: string;
  endDate?: string;
  portalId?: number;
}

export function AMAInput({ startDate, endDate, portalId }: Props) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AMAResponse | null>(null);
  const [showSql, setShowSql] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close popover on click outside
  useEffect(() => {
    if (!result && !error) return;
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setResult(null);
        setError(null);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [result, error]);

  // Close on Escape
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setResult(null);
        setError(null);
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, []);

  async function handleSubmit() {
    const q = question.trim();
    if (!q || loading) return;

    setLoading(true);
    setResult(null);
    setError(null);
    setShowSql(false);

    try {
      const res = await fetch(`${BASE}/api/ama/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: q,
          ...(startDate ? { start_date: startDate } : {}),
          ...(endDate ? { end_date: endDate } : {}),
          ...(portalId ? { portal_id: portalId } : {}),
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setError(err.detail || `Request failed (${res.status})`);
        return;
      }

      const data: AMAResponse = await res.json();
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div ref={containerRef} className="relative">
      {/* Input row */}
      <div className="flex items-center gap-1.5">
        <div className="relative flex-1 min-w-[260px] max-w-[400px]">
          <Sparkles className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-orange-400" />
          <Input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything about your data..."
            className="h-8 pl-8 pr-3 bg-zinc-800 border-zinc-700 text-zinc-200 text-xs placeholder:text-zinc-500 focus-visible:ring-orange-500/50"
            disabled={loading}
          />
        </div>
        <Button
          size="sm"
          onClick={handleSubmit}
          disabled={!question.trim() || loading}
          className="h-8 px-3 bg-orange-600 hover:bg-orange-500 text-white text-xs"
        >
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Ask"}
        </Button>
      </div>

      {/* Response popover */}
      {(loading || result || error) && (
        <div className="absolute top-full left-0 mt-2 z-50 w-[460px] max-w-[90vw]">
          <div className="bg-zinc-900 border border-zinc-700 rounded-lg shadow-2xl overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-zinc-800">
              <div className="flex items-center gap-2">
                <Sparkles className="w-3.5 h-3.5 text-orange-400" />
                <span className="text-xs font-medium text-zinc-300">AI Answer</span>
              </div>
              {!loading && (
                <button
                  onClick={() => {
                    setResult(null);
                    setError(null);
                  }}
                  className="text-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Body */}
            <div className="px-4 py-3 max-h-[300px] overflow-y-auto">
              {loading && (
                <div className="flex items-center gap-3 py-4">
                  <Loader2 className="w-4 h-4 animate-spin text-orange-400" />
                  <span className="text-sm text-zinc-400">Analyzing your data...</span>
                </div>
              )}

              {error && <p className="text-sm text-red-400">{error}</p>}

              {result && (
                <div className="space-y-3">
                  <p className="text-sm text-zinc-200 leading-relaxed whitespace-pre-wrap">
                    {result.answer}
                  </p>

                  {result.sql && (
                    <div>
                      <button
                        onClick={() => setShowSql(!showSql)}
                        className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                      >
                        {showSql ? (
                          <ChevronUp className="w-3 h-3" />
                        ) : (
                          <ChevronDown className="w-3 h-3" />
                        )}
                        {showSql ? "Hide SQL" : "Show SQL"}
                      </button>
                      {showSql && (
                        <pre className="mt-1.5 p-2.5 bg-zinc-800 rounded text-xs text-zinc-400 overflow-x-auto font-mono leading-relaxed">
                          {result.sql}
                        </pre>
                      )}
                    </div>
                  )}

                  {result.error && (
                    <p className="text-xs text-yellow-500/80 mt-1">
                      Note: {result.error}
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
