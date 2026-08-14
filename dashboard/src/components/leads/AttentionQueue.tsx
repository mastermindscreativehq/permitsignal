import Link from "next/link";
import type { Lead } from "@/lib/types";
import { getPrimaryPartyName, hasFriction, isContactable, isOwnerKnown } from "@/lib/lead-helpers";
import { formatDate, leadStatusVariant, priorityVariant, titleCase, urgencyVariant } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";

/**
 * Functional replacement for the removed 3D "skyline" panel on the
 * overview page. Same underlying data as LeadQueueTable/HighPriorityOpportunityCard
 * (already used elsewhere on this page) but condensed to the properties
 * that most need attention right now -- ranked by priority score, every
 * column a direct field, no invented status.
 */
export function AttentionQueue({ leads, limit = 8 }: { leads: Lead[]; limit?: number }) {
  const queue = [...leads]
    .sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0))
    .slice(0, limit);

  if (queue.length === 0) {
    return (
      <div className="panel p-8 text-center text-sm text-foreground-faint">No properties on record yet.</div>
    );
  }

  return (
    <div className="panel overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] text-left text-sm">
          <thead>
            <tr className="border-b border-border-subtle text-[11px] uppercase tracking-wide text-foreground-faint">
              <th className="px-4 py-3 font-medium">Owner</th>
              <th className="px-4 py-3 font-medium">Property</th>
              <th className="px-4 py-3 font-medium">Next Event</th>
              <th className="px-4 py-3 font-medium">Friction</th>
              <th className="px-4 py-3 font-medium">Contact</th>
              <th className="px-4 py-3 font-medium">Priority</th>
            </tr>
          </thead>
          <tbody>
            {queue.map((lead) => {
              const ownerKnown = isOwnerKnown(lead);
              const contactable = isContactable(lead);
              return (
                <tr
                  key={lead.application_number}
                  className="group border-b border-border-subtle/60 last:border-0 hover:bg-surface"
                >
                  <td className="px-4 py-3">
                    <Link
                      href={`/properties/${lead.application_number}`}
                      className={`font-medium group-hover:text-accent-strong ${ownerKnown ? "text-foreground" : "text-foreground-muted"}`}
                    >
                      {getPrimaryPartyName(lead)}
                    </Link>
                    <p className="text-[10px] uppercase tracking-wide text-foreground-faint">
                      {ownerKnown ? "Owner" : "Owner not found"}
                    </p>
                  </td>
                  <td className="max-w-[200px] px-4 py-3">
                    <p className="truncate text-foreground-muted">{lead.project_address ?? lead.application_type ?? "—"}</p>
                    <p className="font-mono text-[11px] text-foreground-faint">{lead.application_number}</p>
                  </td>
                  <td className="px-4 py-3">
                    {lead.has_future_opportunity && lead.next_project_date ? (
                      <div>
                        <p className="text-foreground-muted">{formatDate(lead.next_project_date)}</p>
                        <Badge variant={urgencyVariant(lead.urgency)}>{titleCase(lead.next_project_event)}</Badge>
                      </div>
                    ) : (
                      <span className="text-[11px] text-foreground-faint">None scheduled</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {hasFriction(lead) ? (
                      <span className="font-mono text-xs text-foreground">{lead.friction_score}</span>
                    ) : (
                      <span className="text-[11px] text-foreground-faint">None</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={leadStatusVariant(lead.lead_status)}>
                      {contactable ? "Contactable" : titleCase(lead.lead_status ?? "No contact")}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={priorityVariant(lead.priority)}>{lead.priority ?? "—"}</Badge>
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
