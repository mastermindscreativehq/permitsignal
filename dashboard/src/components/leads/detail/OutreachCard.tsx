import type { Lead } from "@/lib/types";
import { commercialReadinessVariant, outreachStatusVariant, titleCase } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { SectionCard } from "./SectionCard";
import { Field } from "./Field";

const READINESS_COPY: Record<string, string> = {
  READY_FOR_OUTREACH: "This lead qualifies as a real opportunity and has usable public contact evidence -- ready for outreach.",
  NEEDS_CONTACT_ENRICHMENT: "This lead qualifies as a real opportunity, but no public contact has been verified yet.",
  NEEDS_MORE_PROJECT_EVIDENCE: "A future project event exists, but this application has not yet met Provo Administrative Services Finance's bar for a qualified commercial lead.",
  NOT_READY: "No live project event is currently on record -- there is no active opportunity to act on yet.",
};

/**
 * Phase 6 commercial-readiness + Phase 8 outreach-lifecycle intelligence,
 * surfaced together since neither had a dashboard home yet. Both are
 * re-labelings of already-computed evidence (see backend/app/services/
 * commercial_lead_intelligence.py and outreach_intelligence.py) -- this
 * card never fabricates a contact, message, or lifecycle stage; it only
 * displays what those modules already computed.
 */
export function OutreachCard({ lead }: { lead: Lead }) {
  const readiness = lead.commercial_readiness;
  const outreachStatus = lead.outreach_status;

  return (
    <SectionCard
      title="Outreach & Commercial Readiness"
      description="Whether this lead is ready for commercial outreach, who to contact, and why."
      actions={
        <div className="flex items-center gap-2">
          {outreachStatus && (
            <Badge variant={outreachStatusVariant(outreachStatus)}>{outreachStatus.replaceAll("_", " ")}</Badge>
          )}
          {lead.outreach_qualification_status && (
            <Badge variant="status-neutral">{lead.outreach_qualification_status.replaceAll("_", " ")}</Badge>
          )}
          {readiness && (
            <Badge variant={commercialReadinessVariant(readiness)}>{readiness.replaceAll("_", " ")}</Badge>
          )}
        </div>
      }
    >
      <p className="text-sm leading-relaxed text-foreground-muted">
        {READINESS_COPY[readiness ?? ""] ?? "No commercial readiness evidence on record for this application."}
      </p>

      {lead.recommended_commercial_action && (
        <p className="mt-3 text-sm leading-relaxed text-foreground">
          <span className="font-medium">Recommended action: </span>
          {titleCase(lead.recommended_commercial_action)}
          {lead.commercial_action_reason && (
            <span className="text-foreground-muted"> -- {lead.commercial_action_reason}</span>
          )}
        </p>
      )}

      <div className="mt-4 grid grid-cols-2 gap-4">
        <Field
          label="Outreach Target"
          value={lead.outreach_contact_type && lead.outreach_contact_type !== "none" ? titleCase(lead.outreach_contact_type) : null}
        />
        <Field label="Channel" value={lead.outreach_channel && lead.outreach_channel !== "none" ? titleCase(lead.outreach_channel) : null} />
      </div>

      {lead.outreach_contact_reason && (
        <p className="mt-2 text-xs leading-relaxed text-foreground-faint">{lead.outreach_contact_reason}</p>
      )}

      {lead.outreach_message_subject && lead.outreach_message_body && (
        <div className="mt-4 rounded-lg border border-border-subtle bg-surface p-3">
          <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">Draft Outreach Message</p>
          <p className="mt-1 text-sm font-medium text-foreground">{lead.outreach_message_subject}</p>
          <p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-foreground-muted">{lead.outreach_message_body}</p>
        </div>
      )}

      {lead.follow_up_required && (
        <div className="mt-4 rounded-lg border border-status-caution/40 bg-status-caution-soft p-3">
          <p className="text-[11px] font-medium uppercase tracking-wide text-status-caution">Follow-Up Required</p>
          <p className="mt-1 text-sm text-foreground-muted">{lead.follow_up_reason ?? "No reason on record."}</p>
        </div>
      )}

      {lead.outreach_events?.length > 0 && (
        <div className="mt-4 border-t border-border-subtle pt-3">
          <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">Outreach History</p>
          <ul className="mt-2 space-y-1.5">
            {lead.outreach_events.map((event, index) => (
              <li key={index} className="text-xs text-foreground-muted">
                <span className="font-medium text-foreground">{titleCase(event.event)}</span>
                {event.occurred_at && ` -- ${event.occurred_at}`}
                {event.note && <span className="block text-foreground-faint">{event.note}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </SectionCard>
  );
}
