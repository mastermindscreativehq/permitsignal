import Link from "next/link";
import { getLeads } from "@/lib/leads";
import { isReadyForOutreach, needsContactEnrichment, needsContactDiscovery, getPrimaryPartyName, hasUpcomingEvent } from "@/lib/lead-helpers";
import { formatDate, formatDaysUntil, priorityVariant, titleCase, commercialReadinessVariant, leadStatusVariant } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { PageHeader } from "@/components/layout/PageHeader";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

export default async function ReadyForOutreachPage() {
  const leads = await getLeads();
  const ready = leads
    .filter(isReadyForOutreach)
    .sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0));

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Ready for Outreach"
        title="Qualified Opportunities"
        description={`${ready.length} lead${ready.length === 1 ? "" : "s"} qualified with verified contact evidence, ready for commercial action.`}
      />

      {ready.length === 0 ? (
        <div className="panel p-10 text-center">
          <p className="text-sm font-medium text-foreground">No leads ready for outreach</p>
          <p className="mt-1 text-xs text-foreground-faint">
            No opportunities currently have verified contact evidence and commercial readiness. Run contact enrichment to qualify more leads.
          </p>
          <Link href="/contact-discovery" className="mt-4 inline-block rounded-md border border-border-subtle bg-surface px-3.5 py-2 text-sm font-medium text-foreground transition-colors hover:border-accent hover:text-accent-strong">
            View Contact Discovery →
          </Link>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {ready.map((lead) => (
            <Link
              key={lead.application_number}
              href={`/properties/${lead.application_number}`}
              className="panel panel-hover flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="truncate text-sm font-semibold text-foreground">{getPrimaryPartyName(lead)}</p>
                  <Badge variant={priorityVariant(lead.priority)}>{lead.priority}</Badge>
                  <Badge variant={commercialReadinessVariant(lead.commercial_readiness)}>
                    {lead.commercial_readiness?.replaceAll("_", " ")}
                  </Badge>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-foreground-muted">
                  <span>{lead.application_type}</span>
                  <span>{lead.project_address ?? "—"}</span>
                  <span>{lead.municipality}</span>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                  {lead.recommended_commercial_action && (
                    <span className="text-xs text-foreground-muted">
                      Action: {titleCase(lead.recommended_commercial_action)}
                    </span>
                  )}
                  {hasUpcomingEvent(lead) && (
                    <span className="text-xs text-foreground-faint">
                      Event: {formatDate(lead.next_project_date)} · {formatDaysUntil(lead.days_until_event)}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-3 sm:shrink-0">
                <Badge variant={leadStatusVariant(lead.lead_status)}>
                  {lead.lead_status?.replaceAll("_", " ")}
                </Badge>
                <span className="font-mono text-sm font-semibold text-foreground">{lead.priority_score ?? 0}</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
