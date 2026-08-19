"use client";

import { useState, useCallback } from "react";
import type { Lead } from "@/lib/types";
import { formatDate } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { SectionCard } from "./SectionCard";

type Intel = NonNullable<Lead["approval_intelligence"]>;

// ---------------------------------------------------------------------------
// Evidence trust badge — maps backend classification to a visual indicator
// ---------------------------------------------------------------------------
function TrustBadge({ classification }: { classification?: string }) {
  if (!classification) return null;
  const c = classification.toUpperCase();
  if (c === "FACT") return <Badge variant="status-positive">VERIFIED GOVERNMENT EVIDENCE</Badge>;
  if (c === "INFERENCE") return <Badge variant="status-caution">DERIVED / INFERRED</Badge>;
  if (c === "RECOMMENDATION") return <Badge variant="priority-medium">PERMITSIGNAL RECOMMENDATION</Badge>;
  return <Badge variant="status-neutral">NOT VERIFIED</Badge>;
}

// ---------------------------------------------------------------------------
// Confidence dot — inline confidence indicator
// ---------------------------------------------------------------------------
function ConfidenceDot({ confidence }: { confidence?: string | number }) {
  if (confidence === undefined || confidence === null) return null;
  const val = typeof confidence === "string" ? confidence.toUpperCase() : confidence;
  const label = typeof confidence === "number" ? `${(confidence * 100).toFixed(0)}%` : String(confidence);
  if (val === "HIGH" || (typeof val === "number" && val >= 0.8))
    return <span className="text-[10px] text-status-positive" title={`Confidence: ${label}`}>{label}</span>;
  if (val === "MEDIUM" || (typeof val === "number" && val >= 0.5))
    return <span className="text-[10px] text-status-caution" title={`Confidence: ${label}`}>{label}</span>;
  return <span className="text-[10px] text-status-negative" title={`Confidence: ${label}`}>{label}</span>;
}

// ---------------------------------------------------------------------------
// Collapsible wrapper — progressive disclosure via details/summary
// ---------------------------------------------------------------------------
function Collapsible({
  title,
  count,
  badge,
  defaultOpen,
  children,
}: {
  title: string;
  count?: number;
  badge?: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  return (
    <details open={defaultOpen} className="group">
      <summary className="flex cursor-pointer items-center gap-2 select-none">
        <svg
          className="h-3 w-3 shrink-0 text-foreground-faint transition-transform group-open:rotate-90"
          viewBox="0 0 12 12"
          fill="currentColor"
        >
          <path d="M4.5 2l4 4-4 4" />
        </svg>
        <h4 className="text-[11px] font-semibold uppercase tracking-wider text-foreground-faint">
          {title}
          {count !== undefined && (
            <span className="ml-1 text-foreground-muted">({count})</span>
          )}
        </h4>
        {badge}
      </summary>
      <div className="mt-3 pl-5">{children}</div>
    </details>
  );
}

// ---------------------------------------------------------------------------
// Section heading (used inside collapsible sections for sub-groups)
// ---------------------------------------------------------------------------
function SubHeading({ label, count }: { label: string; count?: number }) {
  return (
    <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-foreground-faint">
      {label}
      {count !== undefined && <span className="ml-1 text-foreground-muted">({count})</span>}
    </p>
  );
}

// ============================================================================
// BLOCKERS
// ============================================================================
function BlockerList({ blockers }: { blockers: Intel["approval_blockers"] }) {
  if (!blockers?.length) return <p className="text-xs text-foreground-faint">No blockers identified</p>;
  return (
    <ul className="space-y-2">
      {blockers.map((b, i) => {
        const sev = (b.severity || "").toUpperCase();
        const sevVariant = sev === "CRITICAL" ? "status-negative" : sev === "HIGH" ? "priority-high" : sev === "MEDIUM" ? "status-caution" : "status-neutral";
        return (
          <li key={i} className="rounded-lg border border-border-subtle bg-surface p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={sevVariant}>{b.severity || "UNKNOWN"}</Badge>
              <span className="text-xs font-medium text-foreground">
                {b.blocker_type?.replace(/_/g, " ")}
              </span>
              <TrustBadge classification={b.classification} />
            </div>
            {b.statement && (
              <p className="mt-1.5 text-xs leading-relaxed text-foreground-muted">{b.statement}</p>
            )}
            {b.rationale && (
              <p className="mt-1 text-[11px] italic text-foreground-faint">{b.rationale}</p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

// ============================================================================
// DENIAL HISTORY
// ============================================================================
function DenialHistory({ history }: { history: Intel["denial_history"] }) {
  if (!history?.length) return <p className="text-xs text-foreground-faint">No denial history on record</p>;
  return (
    <ul className="space-y-2">
      {history.map((h, i) => {
        const type = (h.event_type || "").replace(/_/g, " ");
        const isRecurrence = h.is_recurrence;
        return (
          <li key={i} className="rounded-lg border border-border-subtle bg-surface p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={h.event_type === "denied" ? "status-negative" : h.event_type === "recommended_denial" ? "status-caution" : "status-neutral"}>
                {type}
              </Badge>
              {h.event_date && (
                <span className="font-mono text-xs text-foreground-faint">{formatDate(h.event_date)}</span>
              )}
              {h.objection_type && (
                <span className="text-[11px] text-foreground-muted">Objection: {h.objection_type}</span>
              )}
              {isRecurrence && (
                <Badge variant="status-caution">RECURRENCE</Badge>
              )}
              {h.confidence != null && (
                <span className="text-[11px] text-foreground-faint">
                  {(h.confidence * 100).toFixed(0)}% confidence
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

// ============================================================================
// REQUIREMENTS (Grouped A / B / C)
// ============================================================================
function RequirementsList({ requirements }: { requirements: Intel["requirements"] }) {
  if (!requirements?.length) return <p className="text-xs text-foreground-faint">No requirements identified</p>;

  const groups = [
    { key: "A", label: "Explicit Government Requirements", variant: "status-positive" as const },
    { key: "B", label: "Derived / Inferred", variant: "status-caution" as const },
    { key: "C", label: "PermitSignal Recommendations", variant: "priority-medium" as const },
  ];

  return (
    <div className="space-y-3">
      {groups.map(({ key, label, variant }) => {
        const items = requirements.filter((r) => r.group === key);
        if (items.length === 0) return null;
        return (
          <div key={key}>
            <div className="mb-1.5 flex items-center gap-2">
              <Badge variant={variant}>Group {key}</Badge>
              <span className="text-[11px] text-foreground-faint">{label}</span>
            </div>
            <ul className="space-y-1.5 pl-1">
              {items.map((r, i) => (
              <li key={i} className="rounded bg-surface/60 px-3 py-2">
                    <div className="flex items-start gap-2">
                      <ConfidenceDot confidence={r.confidence} />
                      <div className="min-w-0 flex-1">
                        <p className="text-xs text-foreground">{r.statement}</p>
                      {r.rationale && (
                        <p className="mt-0.5 text-[11px] italic text-foreground-faint">{r.rationale}</p>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

// ============================================================================
// RECOMMENDED ACTIONS
// ============================================================================
function ActionPlan({ actions }: { actions: Intel["recommended_actions"] }) {
  if (!actions?.length) return <p className="text-xs text-foreground-faint">No actions recommended</p>;
  const sorted = [...actions].sort((a, b) => (a.priority_rank ?? 99) - (b.priority_rank ?? 99));
  return (
    <ol className="space-y-2">
      {sorted.map((a, i) => (
        <li key={i} className="flex gap-3 rounded-lg bg-surface/40 px-3 py-2">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-priority-high-soft text-[10px] font-bold text-priority-high">
            {a.priority_rank ?? i + 1}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-xs leading-relaxed text-foreground">{a.action}</p>
            {a.deadline && (
              <p className="mt-0.5 text-[11px] text-foreground-faint">
                Deadline: <span className="font-mono">{formatDate(a.deadline)}</span>
              </p>
            )}
            {a.rationale && (
              <p className="mt-0.5 text-[11px] italic text-foreground-faint">{a.rationale}</p>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

// ============================================================================
// DECISION PATH
// ============================================================================
function DecisionPath({ path }: { path: Intel["decision_path"] }) {
  if (!path?.length) return <p className="text-xs text-foreground-faint">No decision path reconstructed</p>;
  return (
    <div className="space-y-2">
      {path.map((stage, i) => {
        const s = (stage.status || "").toLowerCase();
        const isComplete = s === "completed" || s === "completed_with_issues" || s === "previously_reviewed" || s === "concerns_raised";
        const isScheduled = s === "scheduled";
        const isNotReached = s === "not_reached";
        const variant = isComplete ? "status-positive" : isScheduled ? "status-caution" : isNotReached ? "status-neutral" : "status-caution";
        return (
          <div key={i} className="rounded-lg bg-surface/40 px-3 py-2">
            <div className="flex items-center gap-3">
              <Badge variant={variant}>{stage.stage_label || stage.stage}</Badge>
              <span className="text-[11px] text-foreground-faint capitalize">
                {stage.status?.replace(/_/g, " ")}
              </span>
              <TrustBadge classification={stage.classification} />
            </div>
            {stage.evidence && (
              <p className="mt-1 text-[11px] leading-relaxed text-foreground-muted">{stage.evidence}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ============================================================================
// STAKEHOLDERS (key is stakeholder_actions in backend)
// ============================================================================
function Stakeholders({ stakeholders }: { stakeholders: Intel["stakeholder_actions"] }) {
  if (!stakeholders?.length) return <p className="text-xs text-foreground-faint">No stakeholders identified</p>;
  return (
    <ul className="space-y-1.5">
      {stakeholders.map((s, i) => (
        <li key={i} className="flex items-start gap-2 rounded bg-surface/40 px-3 py-2">
          <Badge variant={s.stakeholder_type === "applicant" ? "status-positive" : s.stakeholder_type === "staff" ? "priority-medium" : "status-neutral"}>
            {s.stakeholder_type || "Unknown"}
          </Badge>
          <div className="min-w-0 flex-1">
            <span className="text-xs font-medium text-foreground">{s.name}</span>
            {s.role && (
              <span className="ml-1 text-[11px] text-foreground-faint">({s.role.replace(/_/g, " ")})</span>
            )}
            {s.email && (
              <span className="ml-1 text-[11px] text-accent-strong">{s.email}</span>
            )}
            {s.suggested_action && (
              <p className="mt-0.5 text-[11px] text-foreground-faint">{s.suggested_action}</p>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

// ============================================================================
// EVIDENCE REGISTRY
// ============================================================================
function EvidenceList({ evidence }: { evidence: Intel["evidence"] }) {
  if (!evidence?.length) return <p className="text-xs text-foreground-faint">No evidence on record</p>;
  return (
    <div className="flex max-h-96 flex-col gap-1.5 overflow-y-auto pr-1">
      {evidence.map((e, i) => (
        <div key={i} className="rounded-lg border border-border-subtle bg-surface px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[10px] text-foreground-faint">{e.evidence_id}</span>
            <Badge variant="status-neutral">{e.source_type?.replace(/_/g, " ")}</Badge>
            <TrustBadge classification={e.source_type === "application_extraction" ? "FACT" : e.source_type === "friction_analysis" ? "INFERENCE" : undefined} />
          </div>
          <p className="mt-1 text-xs leading-relaxed text-foreground-muted">{e.claim}</p>
          {e.excerpt && (
            <p className="mt-1 line-clamp-2 text-[11px] italic text-foreground-faint">&ldquo;{e.excerpt}&rdquo;</p>
          )}
          <div className="mt-1 flex items-center gap-2 text-[10px] text-foreground-faint">
            {e.document_name && <span>{e.document_name}</span>}
            {e.page && <span>p.{e.page}</span>}
            {e.date && <span className="font-mono">{formatDate(e.date)}</span>}
            {e.source_url && (
              <a href={e.source_url} target="_blank" rel="noreferrer" className="text-accent-strong hover:underline">
                Source
              </a>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ============================================================================
// PRICING
// ============================================================================
function PricingSection({ pricing, pricingInputs }: { pricing: Lead["pricing"]; pricingInputs?: Intel["pricing_inputs"] }) {
  const [expanded, setExpanded] = useState(false);

  if (!pricing || pricing.status === "error") return null;
  return (
    <div className="rounded-lg border border-border-subtle bg-surface p-4">
      <div className="flex flex-wrap items-center gap-4 text-xs">
        <div>
          <span className="text-foreground-faint">Range: </span>
          <span className="font-medium text-foreground">
            ${pricing.fee_low?.toLocaleString()} – ${pricing.fee_high?.toLocaleString()}
          </span>
        </div>
        <div>
          <span className="text-foreground-faint">Recommended: </span>
          <span className="font-semibold text-status-positive">
            ${pricing.recommended_fee?.toLocaleString()}
          </span>
        </div>
        <div>
          <span className="text-foreground-faint">Deposit: </span>
          <span className="font-medium text-foreground">
            {pricing.deposit_percent}% (${pricing.deposit_amount?.toLocaleString()})
          </span>
        </div>
      </div>

      {/* Why this price? — expandable */}
      {pricing.pricing_rationale && pricing.pricing_rationale.length > 0 && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-[11px] text-accent-strong hover:underline"
          >
            <svg
              className={`h-3 w-3 transition-transform ${expanded ? "rotate-90" : ""}`}
              viewBox="0 0 12 12"
              fill="currentColor"
            >
              <path d="M4.5 2l4 4-4 4" />
            </svg>
            Why this price?
          </button>
          {expanded && (
            <ul className="mt-2 space-y-0.5 pl-4">
              {pricing.pricing_rationale.map((line, i) => (
                <li key={i} className="text-[11px] text-foreground-faint">{line}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Pricing inputs — complexity signals (when available) */}
      {pricingInputs && Object.keys(pricingInputs).length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {typeof pricingInputs.complexity_tier === "string" && (
            <Badge variant={pricingInputs.complexity_tier === "complex" ? "status-negative" : pricingInputs.complexity_tier === "moderate" ? "status-caution" : "status-positive"}>
              Complexity: {pricingInputs.complexity_tier}
            </Badge>
          )}
          {typeof pricingInputs.urgency_signal === "string" && (
            <Badge variant={pricingInputs.urgency_signal === "urgent" ? "status-negative" : "status-caution"}>
              Urgency: {pricingInputs.urgency_signal}
            </Badge>
          )}
          {typeof pricingInputs.friction_score === "number" && (
            <Badge variant="status-neutral">Friction: {pricingInputs.friction_score}</Badge>
          )}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// CLIENT MESSAGE (editable)
// ============================================================================
function ClientMessageSection({ message }: { message: string }) {
  const [value, setValue] = useState(message);
  const [editing, setEditing] = useState(false);

  const handleSave = useCallback(() => {
    setEditing(false);
  }, []);

  return (
    <div className="rounded-lg border border-border-subtle bg-surface p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[11px] text-foreground-faint">Client-facing message (editable)</span>
        <button
          type="button"
          onClick={() => (editing ? handleSave() : setEditing(true))}
          className="text-[11px] text-accent-strong hover:underline"
        >
          {editing ? "Save" : "Edit"}
        </button>
      </div>
      {editing ? (
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          rows={12}
          className="w-full rounded border border-border-strong bg-background p-3 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-accent"
        />
      ) : (
        <p className="whitespace-pre-wrap text-xs leading-relaxed text-foreground-muted">{value}</p>
      )}
      <p className="mt-2 text-[10px] text-foreground-faint">
        Edits are local only and do not overwrite source government evidence.
      </p>
    </div>
  );
}

// ============================================================================
// INTERNAL STRATEGY (read-only, not for client distribution)
// ============================================================================
function InternalStrategySection({ strategy }: { strategy: string }) {
  return (
    <div className="rounded-lg border border-status-caution/20 bg-status-caution/5 p-4">
      <div className="mb-2 flex items-center gap-2">
        <Badge variant="status-caution">INTERNAL ONLY</Badge>
        <span className="text-[11px] text-foreground-faint">Not for client distribution</span>
      </div>
      <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-foreground-muted">{strategy}</pre>
    </div>
  );
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================
export function DeepIntelligenceCard({ lead }: { lead: Lead }) {
  const intel = lead.approval_intelligence;
  if (!intel || intel.status === "error") return null;

  const blockerCount = intel.approval_blockers?.length ?? 0;
  const criticalCount = intel.approval_blockers?.filter((b) => b.severity === "CRITICAL").length ?? 0;
  const requirementCount = intel.requirements?.length ?? 0;
  const actionCount = intel.recommended_actions?.length ?? 0;
  const evidenceCount = intel.evidence?.length ?? 0;
  const denialCount = intel.denial_history?.length ?? 0;

  return (
    <SectionCard title="Deep Approval Intelligence" description="Full evidence-backed intelligence package">
      <div className="space-y-5">

        {/* ── Executive Diagnosis (always visible, top priority) ── */}
        {intel.executive_diagnosis && (
          <div className="rounded-lg border border-status-positive/20 bg-status-positive/5 p-4">
            <p className="text-xs leading-relaxed text-foreground">{intel.executive_diagnosis}</p>
          </div>
        )}

        {/* ── Status Badges ── */}
        <div className="flex flex-wrap gap-2">
          {intel.approval_status && (
            <Badge
              variant={
                intel.approval_status.toLowerCase().includes("denied")
                  ? "status-negative"
                  : intel.approval_status.toLowerCase().includes("pending") || intel.approval_status.toLowerCase().includes("scheduled")
                  ? "status-caution"
                  : "status-positive"
              }
            >
              Status: {intel.approval_status}
            </Badge>
          )}
          {intel.approval_risk && (
            <Badge
              variant={
                intel.approval_risk === "HIGH"
                  ? "status-negative"
                  : intel.approval_risk === "MEDIUM"
                  ? "status-caution"
                  : "status-positive"
              }
            >
              Risk: {intel.approval_risk}
            </Badge>
          )}
          {intel.approval_readiness && (
            <Badge
              variant={
                intel.approval_readiness === "NOT_READY"
                  ? "status-negative"
                  : intel.approval_readiness === "PROVISIONAL"
                  ? "status-caution"
                  : "status-positive"
              }
            >
              Readiness: {intel.approval_readiness}
            </Badge>
          )}
          {lead.pricing?.recommended_fee && (
            <Badge variant="status-neutral">
              ${lead.pricing.recommended_fee.toLocaleString()}
            </Badge>
          )}
        </div>

        {/* ── Approval Detail Fields ── */}
        {(lead.approval_basis || lead.approval_reason || lead.approval_evidence) && (
          <div className="rounded-lg border border-border-subtle bg-surface/60 p-4">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-foreground-faint">Approval Detail</p>
            {lead.approval_basis && (
              <div className="mb-2">
                <p className="text-[10px] uppercase tracking-wide text-foreground-faint">Basis</p>
                <p className="mt-0.5 text-xs leading-relaxed text-foreground">{lead.approval_basis}</p>
              </div>
            )}
            {lead.approval_reason && (
              <div className="mb-2">
                <p className="text-[10px] uppercase tracking-wide text-foreground-faint">Reason</p>
                <p className="mt-0.5 text-xs leading-relaxed text-foreground">{lead.approval_reason}</p>
              </div>
            )}
            {lead.approval_evidence && (
              <div>
                <p className="text-[10px] uppercase tracking-wide text-foreground-faint">Evidence</p>
                <p className="mt-0.5 text-xs leading-relaxed text-foreground-muted">{lead.approval_evidence}</p>
              </div>
            )}
          </div>
        )}

        {/* ── Critical Blockers (always visible when present) ── */}
        {criticalCount > 0 && (
          <Collapsible title="Critical Blockers" count={criticalCount} defaultOpen badge={<Badge variant="status-negative">ACTION REQUIRED</Badge>}>
            <BlockerList blockers={intel.approval_blockers} />
          </Collapsible>
        )}

        {/* ── All Blockers (collapsed when no critical) ── */}
        {blockerCount > 0 && criticalCount === 0 && (
          <Collapsible title="Approval Blockers" count={blockerCount}>
            <BlockerList blockers={intel.approval_blockers} />
          </Collapsible>
        )}

        {/* ── Denial History ── */}
        {denialCount > 0 && (
          <Collapsible title="Denial History" count={denialCount} badge={<Badge variant="status-caution">PREVIOUS ATTEMPTS</Badge>}>
            <DenialHistory history={intel.denial_history} />
          </Collapsible>
        )}

        {/* ── Why Previous Attempts Failed ── */}
        {denialCount > 0 && (
          <Collapsible title="Why Previous Attempts Failed" defaultOpen={blockerCount > 0}>
            <div className="space-y-2">
              {intel.approval_blockers
                ?.filter((b) => b.severity === "CRITICAL" || b.severity === "HIGH")
                .map((b, i) => (
                  <div key={i} className="rounded-lg bg-surface/60 px-3 py-2">
                    <p className="text-xs font-medium text-foreground">
                      {b.blocker_type?.replace(/_/g, " ")}
                    </p>
                    {b.rationale && (
                      <p className="mt-0.5 text-[11px] text-foreground-faint">{b.rationale}</p>
                    )}
                  </div>
                ))}
              {intel.denial_history
                ?.filter((h) => h.objection_type && h.objection_type !== "unknown")
                .map((h, i) => (
                  <div key={i} className="rounded-lg bg-surface/60 px-3 py-2">
                    <p className="text-xs text-foreground">
                      Objection type: <span className="font-medium">{h.objection_type}</span>
                      {h.is_recurrence && <span className="ml-1 text-status-caution">(repeated)</span>}
                    </p>
                  </div>
                ))}
            </div>
          </Collapsible>
        )}

        {/* ── What Must Change ── */}
        {(intel.requirements?.length ?? 0) > 0 && (
          <Collapsible title="What Must Change" defaultOpen>
            <RequirementsList requirements={intel.requirements} />
          </Collapsible>
        )}

        {/* ── Recommended Actions ── */}
        {actionCount > 0 && (
          <Collapsible title="Action Plan" count={actionCount} defaultOpen badge={intel.service_recommendation ? <Badge variant="priority-high">{intel.service_recommendation}</Badge> : undefined}>
            <ActionPlan actions={intel.recommended_actions} />
            {intel.service_scope && (
              <p className="mt-2 text-[11px] text-foreground-faint italic">{intel.service_scope}</p>
            )}
          </Collapsible>
        )}

        {/* ── Decision Path ── */}
        {intel.decision_path && intel.decision_path.length > 0 && (
          <Collapsible title="Decision Path" count={intel.decision_path.length}>
            <DecisionPath path={intel.decision_path} />
          </Collapsible>
        )}

        {/* ── Stakeholders ── */}
        {intel.stakeholder_actions && intel.stakeholder_actions.length > 0 && (
          <Collapsible title="Stakeholders" count={intel.stakeholder_actions.length}>
            <Stakeholders stakeholders={intel.stakeholder_actions} />
          </Collapsible>
        )}

        {/* ── Pricing ── */}
        {(lead.pricing || intel.pricing_inputs) && (
          <Collapsible title="Pricing" defaultOpen>
            <PricingSection pricing={lead.pricing} pricingInputs={intel.pricing_inputs} />
          </Collapsible>
        )}

        {/* ── Evidence Registry ── */}
        {evidenceCount > 0 && (
          <Collapsible title="Evidence Registry" count={evidenceCount}>
            <EvidenceList evidence={intel.evidence} />
          </Collapsible>
        )}

        {/* ── Client Message (editable) ── */}
        {intel.client_message && (
          <Collapsible title="Client Message" defaultOpen>
            <ClientMessageSection message={intel.client_message} />
          </Collapsible>
        )}

        {/* ── Internal Strategy ── */}
        {intel.internal_strategy && (
          <Collapsible title="Internal Strategy">
            <InternalStrategySection strategy={intel.internal_strategy} />
          </Collapsible>
        )}

        {/* ── Unresolved Questions ── */}
        {intel.unresolved_questions && intel.unresolved_questions.length > 0 && (
          <Collapsible title="Unresolved Questions" count={intel.unresolved_questions.length}>
            <ul className="space-y-1.5">
              {intel.unresolved_questions.map((q, i) => (
                <li key={i} className="flex gap-2 rounded bg-surface/40 px-3 py-2 text-xs text-foreground-faint">
                  <span className="shrink-0 text-status-caution">?</span>
                  <span>{q}</span>
                </li>
              ))}
            </ul>
          </Collapsible>
        )}

        {/* ── Model Warnings ── */}
        {intel.model_warnings && intel.model_warnings.length > 0 && (
          <Collapsible title="Model Warnings" count={intel.model_warnings.length} badge={<Badge variant="status-caution">CAUTION</Badge>}>
            <div className="rounded-lg border border-status-caution/20 bg-status-caution/5 p-3">
              <ul className="space-y-1">
                {intel.model_warnings.map((w, i) => (
                  <li key={i} className="text-[11px] leading-relaxed text-status-caution">{w}</li>
                ))}
              </ul>
            </div>
          </Collapsible>
        )}
      </div>
    </SectionCard>
  );
}
