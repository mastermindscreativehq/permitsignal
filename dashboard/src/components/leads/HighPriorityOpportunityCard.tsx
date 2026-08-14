import Link from "next/link";
import type { Lead } from "@/lib/types";
import { getPrimaryPartyName, isContactable, isOwnerKnown, needsContactDiscovery } from "@/lib/lead-helpers";
import { approvalStatusVariant, formatDate, formatDaysUntil, leadStatusVariant, priorityVariant, titleCase } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";

export function HighPriorityOpportunityCard({ lead }: { lead: Lead }) {
  const ownerKnown = isOwnerKnown(lead);
  const contactable = isContactable(lead);
  const needsDiscovery = needsContactDiscovery(lead);
  const hasEvent = lead.has_future_opportunity && lead.next_project_date;

  return (
    <Link
      href={`/properties/${lead.application_number}`}
      className="panel panel-hover flex flex-col gap-4 border-l-2 border-l-priority-high p-4 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex min-w-0 flex-1 flex-col gap-3 sm:flex-row sm:items-center sm:gap-6">
        <div className="min-w-0 sm:w-[220px]">
          <p className="text-[10px] font-medium uppercase tracking-wide text-foreground-faint">
            {ownerKnown ? "Owner" : "Applicant — owner not found"}
          </p>
          <p className={`truncate text-sm font-semibold ${ownerKnown ? "text-foreground" : "text-foreground-muted"}`}>
            {getPrimaryPartyName(lead)}
          </p>
        </div>
        <div className="min-w-0 sm:w-[200px]">
          <p className="text-[10px] font-medium uppercase tracking-wide text-foreground-faint">Property</p>
          <p className="truncate text-sm text-foreground-muted">{lead.project_address ?? "No address on record"}</p>
        </div>
        <div className="min-w-0 sm:w-[170px]">
          <p className="text-[10px] font-medium uppercase tracking-wide text-foreground-faint">Project</p>
          <p className="truncate text-sm text-foreground-muted">{lead.application_type ?? "—"}</p>
          <p className="font-mono text-[11px] text-foreground-faint">{lead.application_number}</p>
        </div>
        <div className="min-w-0 sm:w-[130px]">
          <p className="text-[10px] font-medium uppercase tracking-wide text-foreground-faint">Friction</p>
          <p className="text-sm text-foreground-muted">
            {lead.friction_score ? `${lead.friction_score} · ${lead.friction_signals?.[0] ? titleCase(lead.friction_signals[0]) : "Signal"}` : "None"}
          </p>
        </div>
        <div className="min-w-0 sm:w-[150px]">
          <p className="text-[10px] font-medium uppercase tracking-wide text-foreground-faint">Next Event</p>
          <p className="text-sm text-foreground-muted">
            {hasEvent ? `${formatDate(lead.next_project_date)} · ${formatDaysUntil(lead.days_until_event)}` : "None scheduled"}
          </p>
        </div>
        <div className="min-w-0 sm:w-[170px]">
          <p className="text-[10px] font-medium uppercase tracking-wide text-foreground-faint">Approval Action</p>
          <p className="truncate text-sm text-foreground-muted">
            {lead.approval_action ? titleCase(lead.approval_action) : "Unknown"}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3 sm:shrink-0">
        <Badge variant={leadStatusVariant(lead.lead_status)}>
          {contactable ? "Contactable" : needsDiscovery ? "Needs Discovery" : titleCase(lead.lead_status)}
        </Badge>
        {lead.approval_status && (
          <Badge variant={approvalStatusVariant(lead.approval_status)}>{titleCase(lead.approval_status)}</Badge>
        )}
        <Badge variant={priorityVariant(lead.priority)}>{lead.priority ?? "—"}</Badge>
      </div>
    </Link>
  );
}
