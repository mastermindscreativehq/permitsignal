import Link from "next/link";
import type { Lead } from "@/lib/types";
import { getPrimaryPartyName, getPrimaryPartyRole, isContactable, isOwnerKnown, needsContactDiscovery } from "@/lib/lead-helpers";
import { Badge } from "@/components/ui/Badge";
import {
  approvalStatusVariant,
  commercialReadinessVariant,
  formatDate,
  formatDaysUntil,
  leadStatusVariant,
  priorityVariant,
  titleCase,
} from "@/lib/format";

export function LeadQueueTable({ leads }: { leads: Lead[] }) {
  if (leads.length === 0) {
    return (
      <div className="panel p-10 text-center">
        <p className="text-sm font-medium text-foreground">No opportunities match these filters</p>
        <p className="mt-1 text-xs text-foreground-faint">Adjust or clear filters to see more of the queue.</p>
      </div>
    );
  }

  return (
    <div className="panel overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1280px] text-left text-sm">
          <thead>
            <tr className="border-b border-border-subtle text-[11px] uppercase tracking-wide text-foreground-faint">
              <th className="px-4 py-3 font-medium">Who</th>
              <th className="px-4 py-3 font-medium">Property</th>
              <th className="px-4 py-3 font-medium">Project</th>
              <th className="px-4 py-3 font-medium">Friction</th>
              <th className="px-4 py-3 font-medium">Next Event</th>
              <th className="px-4 py-3 font-medium">Approval Action</th>
              <th className="px-4 py-3 font-medium">Priority</th>
              <th className="px-4 py-3 font-medium">Contact</th>
              <th className="px-4 py-3 font-medium">Next Action</th>
            </tr>
          </thead>
          <tbody>
            {leads.map((lead) => {
              const contactable = isContactable(lead);
              const needsDiscovery = needsContactDiscovery(lead);
              const ownerKnown = isOwnerKnown(lead);
              return (
                <tr
                  key={lead.application_number}
                  className="group border-b border-border-subtle/60 last:border-0 hover:bg-surface"
                >
                  <td className="px-4 py-3.5">
                    <Link
                      href={`/properties/${lead.application_number}`}
                      className={`font-medium group-hover:text-accent-strong ${ownerKnown ? "text-foreground" : "text-foreground-muted"}`}
                    >
                      {getPrimaryPartyName(lead)}
                    </Link>
                    <p className="text-[10px] uppercase tracking-wide text-foreground-faint">
                      {getPrimaryPartyRole(lead)}
                    </p>
                    {ownerKnown && lead.applicant_name && lead.applicant_name !== getPrimaryPartyName(lead) && (
                      <p className="truncate text-[11px] text-foreground-faint">Agent: {lead.applicant_name}</p>
                    )}
                  </td>
                  <td className="max-w-[220px] px-4 py-3.5">
                    <p className="truncate text-foreground-muted">{lead.project_address ?? "—"}</p>
                    <p className="truncate text-[11px] text-foreground-faint">{lead.neighborhood ?? lead.municipality ?? ""}</p>
                  </td>
                  <td className="max-w-[180px] px-4 py-3.5">
                    <p className="truncate text-foreground-muted">{lead.application_type ?? "—"}</p>
                    <p className="font-mono text-[11px] text-foreground-faint">{lead.application_number}</p>
                  </td>
                  <td className="px-4 py-3.5">
                    {lead.friction_score ? (
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-foreground">{lead.friction_score}</span>
                        <span className="truncate text-[11px] text-foreground-faint">
                          {lead.friction_signals?.slice(0, 2).map(titleCase).join(", ")}
                        </span>
                      </div>
                    ) : (
                      <span className="text-[11px] text-foreground-faint">None</span>
                    )}
                  </td>
                  <td className="px-4 py-3.5">
                    {lead.has_future_opportunity && lead.next_project_date ? (
                      <div>
                        <p className="text-foreground-muted">{formatDate(lead.next_project_date)}</p>
                        <p className="text-[11px] text-foreground-faint">
                          {titleCase(lead.next_project_event)} · {formatDaysUntil(lead.days_until_event)}
                        </p>
                      </div>
                    ) : (
                      <span className="text-[11px] text-foreground-faint">None scheduled</span>
                    )}
                  </td>
                  <td className="max-w-[190px] px-4 py-3.5">
                    {lead.approval_status ? (
                      <>
                        <Badge variant={approvalStatusVariant(lead.approval_status)}>{titleCase(lead.approval_status)}</Badge>
                        <p className="mt-1 truncate text-[11px] text-foreground-faint">{titleCase(lead.approval_action)}</p>
                      </>
                    ) : (
                      <span className="text-[11px] text-foreground-faint">Unknown</span>
                    )}
                  </td>
                  <td className="px-4 py-3.5">
                    <Badge variant={priorityVariant(lead.priority)}>{lead.priority ?? "—"}</Badge>
                    <p className="mt-1 font-mono text-[11px] text-foreground-faint">{lead.priority_score ?? "—"} pts</p>
                  </td>
                  <td className="px-4 py-3.5">
                    <Badge variant={leadStatusVariant(lead.lead_status)}>
                      {contactable ? "Contactable" : needsDiscovery ? titleCase(lead.lead_status ?? "No contact") : titleCase(lead.lead_status)}
                    </Badge>
                  </td>
                  <td className="max-w-[190px] px-4 py-3.5">
                    {lead.recommended_commercial_action ? (
                      <>
                        {lead.commercial_readiness && (
                          <Badge variant={commercialReadinessVariant(lead.commercial_readiness)}>
                            {lead.commercial_readiness.replaceAll("_", " ")}
                          </Badge>
                        )}
                        <p className="mt-1 truncate text-[11px] text-foreground-faint">
                          {titleCase(lead.recommended_commercial_action)}
                        </p>
                      </>
                    ) : (
                      <span className="text-[11px] text-foreground-faint">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
