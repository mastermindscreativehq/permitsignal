"use client";

import type { Lead } from "@/lib/types";
import { titleCase } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { SectionCard } from "./SectionCard";

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 80 ? "bg-status-positive" :
    pct >= 50 ? "bg-status-caution" :
    "bg-status-neutral";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-surface">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-[11px] text-foreground-faint">{pct}%</span>
    </div>
  );
}

export function PredictionsCard({ lead }: { lead: Lead }) {
  const preds = lead.predictions;
  if (!preds) return null;

  const hasAnyData =
    preds.outcome_prediction ||
    preds.likely_outcome ||
    preds.confidence_level ||
    preds.approval_probability != null ||
    preds.outcome_confidence != null ||
    (preds.contributing_factors?.length ?? 0) > 0 ||
    (preds.risk_factors?.length ?? 0) > 0 ||
    preds.reasoning;

  if (!hasAnyData) return null;

  return (
    <SectionCard
      title="Predictions"
      description="Outcome prediction and contributing factors."
    >
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {preds.outcome_prediction && (
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">Predicted Outcome</p>
            <div className="mt-1">
              <Badge
                variant={
                  preds.outcome_prediction === "approval" ? "status-positive" :
                  preds.outcome_prediction === "denial" ? "status-negative" :
                  preds.outcome_prediction === "continuance" ? "status-caution" :
                  "status-neutral"
                }
              >
                {titleCase(preds.outcome_prediction)}
              </Badge>
            </div>
          </div>
        )}
        {preds.likely_outcome && !preds.outcome_prediction && (
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">Likely Outcome</p>
            <p className="mt-1 text-sm font-medium text-foreground">{preds.likely_outcome}</p>
          </div>
        )}
        {preds.confidence_level && (
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">Confidence</p>
            <p className="mt-1 text-sm font-medium text-foreground">{titleCase(preds.confidence_level)}</p>
          </div>
        )}
        {preds.approval_probability != null && (
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">Approval Probability</p>
            <div className="mt-1">
              <ConfidenceBar value={preds.approval_probability} />
            </div>
          </div>
        )}
        {preds.outcome_confidence != null && !preds.approval_probability && (
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">Outcome Confidence</p>
            <div className="mt-1">
              <ConfidenceBar value={preds.outcome_confidence} />
            </div>
          </div>
        )}
      </div>

      {preds.contributing_factors && preds.contributing_factors.length > 0 && (
        <div className="mt-3">
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-foreground-faint">
            Contributing Factors ({preds.contributing_factors.length})
          </p>
          <ul className="space-y-1">
            {preds.contributing_factors.map((f, i) => (
              <li key={i} className="flex items-start gap-2 rounded bg-surface/60 px-3 py-1.5 text-xs text-foreground-muted">
                <span className="shrink-0 text-status-positive">+</span>
                <span>{f}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {preds.risk_factors && preds.risk_factors.length > 0 && (
        <div className="mt-3">
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-status-caution">
            Risk Factors ({preds.risk_factors.length})
          </p>
          <ul className="space-y-1">
            {preds.risk_factors.map((f, i) => (
              <li key={i} className="flex items-start gap-2 rounded bg-surface/60 px-3 py-1.5 text-xs text-foreground-muted">
                <span className="shrink-0 text-status-caution">!</span>
                <span>{f}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {preds.reasoning && (
        <div className="mt-3 rounded-lg border border-border-subtle bg-surface p-3">
          <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">Reasoning</p>
          <p className="mt-1 text-xs leading-relaxed text-foreground-muted">{preds.reasoning}</p>
        </div>
      )}
    </SectionCard>
  );
}
