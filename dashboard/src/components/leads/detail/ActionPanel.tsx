import type { Lead } from "@/lib/types";
import { priorityVariant, formatCurrencyRange, titleCase } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { SectionCard } from "./SectionCard";
import { Field, ContactField } from "./Field";
import { FollowUpCard } from "./FollowUpCard";

const PERMITSIGNAL_API_URL = process.env.PERMITSIGNAL_API_URL ?? "http://localhost:8000";

const STATUS_COPY: Record<string, string> = {
  CONTACTABLE: "Verified public contact on file — ready for direct outreach.",
  QUALIFIED: "Identity resolved with confidence — pending final contact verification.",
  NO_CONTACT: "No public contact found — evidence-backed absence, not a failure.",
  NOT_RUN: "Contact discovery has not been attempted yet.",
  FAILED: "Contact discovery ran but could not verify a public source.",
};

const READINESS_COPY: Record<string, string> = {
  READY_FOR_OUTREACH: "Qualified with usable contact evidence — ready for outreach.",
  NEEDS_CONTACT_ENRICHMENT: "Qualified, but no public contact verified yet.",
  NEEDS_MORE_PROJECT_EVIDENCE: "Future event exists but not yet meeting qualification bar.",
  NOT_READY: "No active opportunity to act on yet.",
};

/**
 * The right-column action panel on the detail page.
 * Focuses on: score, contactability, recommended action, and commercial readiness.
 */
export function ActionPanel({ lead }: { lead: Lead }) {
  const status = (lead.lead_status ?? "NOT_RUN") as string;

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <SectionCard
        title="Opportunity"
        actions={<Badge variant={priorityVariant(lead.priority)}>{lead.priority ?? "UNSCORED"}</Badge>}
      >
        <div className="grid grid-cols-2 gap-4">
          <Field label="Priority Score" value={lead.priority_score ?? 0} mono />
          <Field label="Actionable" value={lead.is_actionable ? "Yes" : "No"} />
        </div>
        {lead.recommended_commercial_action && (
          <div className="mt-3 rounded-lg border border-border-subtle bg-surface p-3">
            <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">Recommended Action</p>
            <p className="mt-1 text-sm font-medium text-foreground">{titleCase(lead.recommended_commercial_action)}</p>
            {lead.commercial_action_reason && (
              <p className="mt-1 text-xs text-foreground-muted">{lead.commercial_action_reason}</p>
            )}
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="Contact Intelligence"
        actions={<Badge variant={status === "CONTACTABLE" ? "status-positive" : status === "NO_CONTACT" || status === "NOT_RUN" ? "status-caution" : "status-neutral"}>
          {status.replaceAll("_", " ")}
        </Badge>}
      >
        <p className="text-xs leading-relaxed text-foreground-muted">
          {STATUS_COPY[status] ?? STATUS_COPY.NOT_RUN}
        </p>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <ContactField label="Applicant Email" value={lead.applicant_email} href={(v) => `mailto:${v}`} />
          <ContactField label="Applicant Phone" value={lead.applicant_phone} />
          <ContactField label="Contact Name" value={lead.contact_name} mono={false} />
          <ContactField label="Contact Role" value={lead.contact_role} mono={false} />
          <ContactField label="Company" value={lead.company_name} mono={false} />
          <ContactField label="LinkedIn" value={lead.linkedin_url} href={(v) => v} />
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3 border-t border-border-subtle pt-3">
          <Field label="Email Confidence" value={lead.email_confidence ? titleCase(lead.email_confidence) : null} />
          <Field label="Phone Confidence" value={lead.phone_confidence ? titleCase(lead.phone_confidence) : null} />
        </div>
      </SectionCard>

      {lead.commercial_readiness && (
        <SectionCard title="Commercial Readiness">
          <p className="text-xs leading-relaxed text-foreground-muted">
            {READINESS_COPY[lead.commercial_readiness] ?? "No readiness evidence on record."}
          </p>
          {lead.outreach_contact_type && lead.outreach_contact_type !== "none" && (
            <div className="mt-3 grid grid-cols-2 gap-3">
              <Field label="Outreach Target" value={titleCase(lead.outreach_contact_type)} />
              <Field label="Channel" value={lead.outreach_channel && lead.outreach_channel !== "none" ? titleCase(lead.outreach_channel) : null} />
            </div>
          )}
          {lead.outreach_message_subject && lead.outreach_message_body && (
            <div className="mt-3 rounded-lg border border-border-subtle bg-surface p-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">Draft Message</p>
              <p className="mt-1 text-sm font-medium text-foreground">{lead.outreach_message_subject}</p>
              <p className="mt-1 whitespace-pre-line text-xs leading-relaxed text-foreground-muted">{lead.outreach_message_body}</p>
            </div>
          )}
        </SectionCard>
      )}

      <FollowUpCard lead={lead} />

      <EconomicIntelligence lead={lead} />

      {lead.outreach_events?.length > 0 && (
        <SectionCard title="Outreach History">
          <ul className="space-y-1.5">
            {lead.outreach_events.map((event, index) => (
              <li key={index} className="text-xs text-foreground-muted">
                <span className="font-medium text-foreground">{titleCase(event.event)}</span>
                {event.occurred_at && <span className="text-foreground-faint"> · {event.occurred_at}</span>}
                {event.note && <span className="block text-foreground-faint">{event.note}</span>}
              </li>
            ))}
          </ul>
        </SectionCard>
      )}
    </div>
  );
}

function EconomicIntelligence({ lead }: { lead: Lead }) {
  const hasValue = lead.estimated_value_low !== null || lead.estimated_value_source_type !== null;
  const hasFunding = Boolean(lead.public_funding_status);
  if (!hasValue && !hasFunding) return null;

  return (
    <SectionCard title="Economic Intelligence">
      <div className="grid grid-cols-2 gap-3">
        <Field
          label="Est. Project Value"
          value={
            lead.estimated_value_low !== null
              ? formatCurrencyRange(lead.estimated_value_low, lead.estimated_value_high)
              : null
          }
        />
        <Field
          label="Public Spend"
          value={
            lead.public_spend_low !== null
              ? formatCurrencyRange(lead.public_spend_low, lead.public_spend_high)
              : null
          }
        />
        <Field
          label="Scale"
          value={lead.project_scale_units ? `${lead.project_scale_units} × ${titleCase(lead.project_scale_type)}` : null}
        />
        <Field label="Confidence" value={lead.estimated_value_confidence ? titleCase(lead.estimated_value_confidence) : null} />
      </div>
      {lead.estimated_value_source_type && (
        <p className="mt-3 text-[11px] text-foreground-faint">
          {lead.estimated_value_source_type === "disclosed_document_value"
            ? "Disclosed in government record"
            : lead.estimated_value_source_type === "construction_benchmark_estimate"
              ? "Estimate from construction benchmarks — not an official figure"
              : "Insufficient evidence for estimate"}
        </p>
      )}
    </SectionCard>
  );
}
