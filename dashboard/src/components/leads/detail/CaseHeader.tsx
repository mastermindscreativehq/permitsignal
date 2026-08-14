import Link from "next/link";
import type { Lead } from "@/lib/types";
import { commercialReadinessVariant, formatDate, formatDateTime, leadStatusVariant, priorityVariant, titleCase } from "@/lib/format";
import { getPrimaryOwnerDisplay, getPrimaryPartyRole, hasUpcomingEvent } from "@/lib/lead-helpers";
import { Badge } from "@/components/ui/Badge";

// The backend FastAPI service (see lib/leads.ts) that serves generated
// case-report PDFs. Not a secret -- just a hostname, safe to read directly
// in a server component.
const PERMITSIGNAL_API_URL = process.env.PERMITSIGNAL_API_URL ?? "http://localhost:8000";

/**
 * The case identity strip at the top of a property detail page --
 * application number/type/address/municipality, priority/lead-status, the
 * owner-primary identity (never fabricated -- see getPrimaryOwnerDisplay),
 * and the next live project event, if any. Replaces the removed 3D
 * "Property Intelligence Map" panel: the cards below already cover this
 * data in depth, so the header's job is a single-glance case summary, not
 * another visualization.
 */
export function CaseHeader({ lead }: { lead: Lead }) {
  const { primary: ownerPrimary, contactName: ownerContactName } = getPrimaryOwnerDisplay(lead);
  const showApplicantLine = Boolean(lead.applicant_name) && lead.applicant_name !== ownerPrimary;
  const upcoming = hasUpcomingEvent(lead);

  return (
    <div>
      <Link href="/properties" className="text-xs font-medium text-foreground-muted hover:text-foreground">
        ← Back to Opportunities
      </Link>
      <div className="mt-3 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent-strong">
            {getPrimaryPartyRole(lead)}
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-foreground sm:text-[28px]">
            {ownerPrimary ?? lead.applicant_name ?? lead.company_name ?? "Unknown"}
          </h1>
          <p className="mt-1 text-sm text-foreground-muted">
            {lead.application_type} · {lead.application_number} · {lead.project_address ?? "No address on record"}
            {lead.municipality ? ` · ${lead.municipality}` : ""}
          </p>
          {ownerContactName && (
            <p className="mt-1 text-xs text-foreground-faint">Owner Contact: {ownerContactName}</p>
          )}
          {showApplicantLine && (
            <p className="mt-0.5 text-xs text-foreground-faint">Applicant / Agent: {lead.applicant_name}</p>
          )}
          <p className="mt-1 text-xs text-foreground-faint">
            {upcoming
              ? `Next Event: ${titleCase(lead.next_project_event)} · ${formatDate(lead.next_project_date)}${lead.next_project_time ? ` · ${lead.next_project_time}` : ""}`
              : "Next Event: None scheduled"}
          </p>
          <p className="mt-2 text-[11px] text-foreground-faint">
            Enrichment: {titleCase(lead.enrichment_status ?? "disabled")} · Report generated {formatDateTime(lead.created_at)}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex items-center gap-2">
            <Badge variant={priorityVariant(lead.priority)}>{lead.priority ?? "UNSCORED"}</Badge>
            <Badge variant={leadStatusVariant(lead.lead_status)}>
              {(lead.lead_status ?? "NOT_RUN").replaceAll("_", " ")}
            </Badge>
            {lead.commercial_readiness && (
              <Badge variant={commercialReadinessVariant(lead.commercial_readiness)}>
                {lead.commercial_readiness.replaceAll("_", " ")}
              </Badge>
            )}
          </div>
          {lead.recommended_commercial_action && (
            <p className="max-w-[260px] text-right text-xs text-foreground-faint">
              Next: {titleCase(lead.recommended_commercial_action)}
            </p>
          )}
          <a
            href={`${PERMITSIGNAL_API_URL}/leads/${lead.application_number}/report.pdf`}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs font-medium text-foreground-muted transition-colors hover:border-accent hover:text-accent-strong"
          >
            Download Case Report (PDF)
          </a>
        </div>
      </div>
    </div>
  );
}
