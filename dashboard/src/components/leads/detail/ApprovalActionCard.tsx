import type { Lead } from "@/lib/types";
import { approvalBasisVariant, approvalStatusVariant, formatDate, titleCase } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { SectionCard } from "./SectionCard";
import { Field } from "./Field";

const BASIS_COPY: Record<string, string> = {
  confirmed_requirement: "Confirmed by explicit government-record evidence (a denial/withdrawal outcome, or a scheduled hearing with explicit hearing-class evidence).",
  evidence_backed_recommendation: "A real signal exists in the record, but the specific recommended action is Provo Administrative Services Finance's own synthesis on top of it.",
  inferred_next_step: "Only weak/indirect evidence exists -- treat this as a hint, not a confirmed requirement.",
  unknown: "Insufficient evidence to recommend an action -- never guessed.",
};

/**
 * Phase 3 approval-action intelligence (backend/app/services/
 * approval_action_intelligence.py), surfaced verbatim -- see CLAUDE.md
 * Part 9 / DEVELOPMENT_RULES: an inferred next step must never be
 * presented as a confirmed government requirement, so approval_basis is
 * always shown alongside approval_action, not hidden behind it.
 */
export function ApprovalActionCard({ lead }: { lead: Lead }) {
  const hasApprovalIntelligence = Boolean(lead.approval_status);

  return (
    <SectionCard
      title="Approval-Action Intelligence"
      description="What Provo Administrative Services Finance believes needs to happen next to move this application toward approval, and why."
      actions={
        hasApprovalIntelligence ? (
          <Badge variant={approvalStatusVariant(lead.approval_status)}>{titleCase(lead.approval_status)}</Badge>
        ) : undefined
      }
    >
      {!hasApprovalIntelligence ? (
        <p className="text-sm text-foreground-faint">No approval-action evidence on record for this application.</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <Field label="Recommended Action" value={lead.approval_action ? titleCase(lead.approval_action) : null} />
            <Field label="Action Type" value={lead.approval_action_type ? titleCase(lead.approval_action_type) : null} />
            <Field label="Confidence" value={lead.approval_confidence ? titleCase(lead.approval_confidence) : null} />
            <Field label="Relevant Date" value={formatDate(lead.approval_relevant_date)} />
            <Field label="Source Type" value={lead.approval_source_type ? titleCase(lead.approval_source_type) : null} />
          </div>

          <div className="mt-4 flex items-center gap-2">
            <Badge variant={approvalBasisVariant(lead.approval_basis)}>{titleCase(lead.approval_basis)}</Badge>
            <span className="text-xs text-foreground-faint">
              {BASIS_COPY[lead.approval_basis ?? "unknown"] ?? BASIS_COPY.unknown}
            </span>
          </div>

          {lead.approval_reason && (
            <p className="mt-4 text-sm leading-relaxed text-foreground-muted">{lead.approval_reason}</p>
          )}

          {lead.approval_evidence && (
            <div className="mt-3 rounded-lg border border-border-subtle bg-surface p-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">Source Evidence</p>
              <p className="mt-1 text-sm leading-relaxed text-foreground-muted">{lead.approval_evidence}</p>
              {lead.approval_source && (
                <a
                  href={lead.approval_source}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-block text-xs text-accent-strong hover:underline"
                >
                  View source document →
                </a>
              )}
            </div>
          )}
        </>
      )}
    </SectionCard>
  );
}
