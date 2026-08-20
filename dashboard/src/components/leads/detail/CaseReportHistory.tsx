"use client";

import { useCallback, useEffect, useState } from "react";
import { GlassCard } from "@/components/ui/GlassCard";

const PERMITSIGNAL_API_URL = process.env.NEXT_PUBLIC_PERMITSIGNAL_API_URL ?? "http://localhost:8000";

interface CaseReportRecord {
  id: string;
  application_number: string;
  version: number;
  generated_at: string;
  generated_by: string;
  page_count: number;
  file_size_bytes: number;
  checksum: string;
}

interface ReportsResponse {
  status: string;
  application_number: string;
  count: number;
  reports: CaseReportRecord[];
  storage: string;
}

interface GenerateResponse {
  status: string;
  version: number;
  generated_at: string;
  page_count: number;
  file_size_bytes: number;
  storage: string;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function CaseReportHistory({ applicationNumber }: { applicationNumber: string }) {
  const [reports, setReports] = useState<CaseReportRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [storage, setStorage] = useState<string>("unknown");

  const fetchReports = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`${PERMITSIGNAL_API_URL}/leads/${applicationNumber}/reports`, {
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ReportsResponse = await res.json();
      setReports(data.reports ?? []);
      setStorage(data.storage ?? "unknown");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load report history");
    } finally {
      setLoading(false);
    }
  }, [applicationNumber]);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  const handleGenerate = useCallback(async () => {
    try {
      setGenerating(true);
      setError(null);
      const res = await fetch(`${PERMITSIGNAL_API_URL}/leads/${applicationNumber}/report`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: GenerateResponse = await res.json();
      // Refresh the list
      await fetchReports();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate report");
    } finally {
      setGenerating(false);
    }
  }, [applicationNumber, fetchReports]);

  return (
    <GlassCard>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Case Report History</h2>
          <p className="mt-0.5 text-xs text-foreground-muted">
            Versioned PDF case reports for this property
          </p>
        </div>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs font-medium text-foreground-muted transition-colors hover:border-accent hover:text-accent-strong disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {generating ? "Generating\u2026" : "Generate Report"}
        </button>
      </div>

      {error && (
        <p className="mt-3 rounded-md bg-status-negative-soft px-3 py-2 text-xs text-status-negative">
          {error}
        </p>
      )}

      {storage === "not_configured" && !loading && (
        <p className="mt-3 rounded-md bg-status-caution-soft px-3 py-2 text-xs text-status-caution">
          Supabase is not configured. Reports are generated on-the-fly but not stored.
          Configure SUPABASE_URL and SUPABASE_KEY to enable version history.
        </p>
      )}

      {loading ? (
        <p className="mt-4 text-xs text-foreground-faint">Loading report history\u2026</p>
      ) : reports.length === 0 ? (
        <p className="mt-4 text-xs text-foreground-faint">
          No stored reports yet. Click &ldquo;Generate Report&rdquo; to create one.
        </p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-border-subtle text-foreground-faint">
                <th className="pb-2 pr-3 font-medium">Version</th>
                <th className="pb-2 pr-3 font-medium">Generated</th>
                <th className="pb-2 pr-3 font-medium">Pages</th>
                <th className="pb-2 pr-3 font-medium">Size</th>
                <th className="pb-2 font-medium">Source</th>
                <th className="pb-2 pl-3 text-right font-medium">PDF</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.id} className="border-b border-border-subtle last:border-0">
                  <td className="py-2 pr-3 font-mono text-foreground">v{r.version}</td>
                  <td className="py-2 pr-3 text-foreground-muted">{formatTimestamp(r.generated_at)}</td>
                  <td className="py-2 pr-3 text-foreground-muted">{r.page_count || "\u2014"}</td>
                  <td className="py-2 pr-3 text-foreground-muted">{formatBytes(r.file_size_bytes)}</td>
                  <td className="py-2 text-foreground-faint">{r.generated_by}</td>
                  <td className="py-2 pl-3 text-right">
                    <a
                      href={`${PERMITSIGNAL_API_URL}/leads/${applicationNumber}/reports/${r.version}/pdf`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-accent-strong transition-colors hover:text-accent"
                    >
                      Download
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </GlassCard>
  );
}
