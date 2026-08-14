import type { Lead } from "@/lib/types";
import { formatCurrencyRange, publicFundingVariant, titleCase } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { SectionCard } from "./SectionCard";
import { Field } from "./Field";

const VALUE_SOURCE_COPY: Record<string, string> = {
  disclosed_document_value: "A dollar figure was disclosed directly in the government record.",
  construction_benchmark_estimate: "No disclosed figure -- estimated from a per-unit construction-cost benchmark. This is an ESTIMATE, not an official value.",
  insufficient_evidence: "No disclosed value and no extractable project-scale evidence in the record.",
};

/**
 * Phase 9 economic intelligence (backend/app/services/
 * economic_intelligence.py). Project value and public/government spend are
 * always shown as two separate figures -- a private developer's project can
 * carry a large estimated value and a public spend of exactly $0. Never
 * presents a benchmark estimate as an official figure.
 */
export function EconomicIntelligenceCard({ lead }: { lead: Lead }) {
  const hasValue = lead.estimated_value_low !== null || lead.estimated_value_source_type !== null;
  const hasFunding = Boolean(lead.public_funding_status);

  if (!hasValue && !hasFunding) return null;

  return (
    <SectionCard
      title="Economic Intelligence"
      description="Estimated project value and government/public spend -- tracked as two distinct figures, never conflated."
      actions={
        hasFunding ? (
          <Badge variant={publicFundingVariant(lead.public_funding_status)}>{titleCase(lead.public_funding_status)}</Badge>
        ) : undefined
      }
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field
          label="Estimated Project Value"
          value={
            lead.estimated_value_low !== null
              ? formatCurrencyRange(lead.estimated_value_low, lead.estimated_value_high)
              : null
          }
        />
        <Field
          label="Public / Government Spend"
          value={
            lead.public_spend_low !== null
              ? formatCurrencyRange(lead.public_spend_low, lead.public_spend_high)
              : null
          }
        />
        <Field label="Project Scale" value={lead.project_scale_units ? `${lead.project_scale_units} × ${titleCase(lead.project_scale_type)}` : null} />
        <Field label="Value Confidence" value={lead.estimated_value_confidence ? titleCase(lead.estimated_value_confidence) : null} />
      </div>

      {lead.estimated_value_source_type && (
        <div className="mt-4 rounded-lg border border-border-subtle bg-surface p-3">
          <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">Value Basis</p>
          <p className="mt-1 text-xs text-foreground-faint">
            {VALUE_SOURCE_COPY[lead.estimated_value_source_type] ?? VALUE_SOURCE_COPY.insufficient_evidence}
          </p>
          {lead.estimated_value_basis && (
            <p className="mt-2 text-sm leading-relaxed text-foreground-muted">{lead.estimated_value_basis}</p>
          )}
        </div>
      )}

      {lead.public_funding_basis && (
        <div className="mt-3 rounded-lg border border-border-subtle bg-surface p-3">
          <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">Public Funding Basis</p>
          <p className="mt-2 text-sm leading-relaxed text-foreground-muted">{lead.public_funding_basis}</p>
        </div>
      )}
    </SectionCard>
  );
}
