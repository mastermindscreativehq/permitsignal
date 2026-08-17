import Link from "next/link";
import { getLeads } from "@/lib/leads";
import { isReadyForOutreach, needsContactEnrichment, isContactable, getPrimaryPartyName, hasUpcomingEvent } from "@/lib/lead-helpers";
import { formatDate, formatDaysUntil, priorityVariant, titleCase, leadStatusVariant } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { PageHeader } from "@/components/layout/PageHeader";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

export default async function OverviewPage() {
  const leads = await getLeads();

  const total = leads.length;
  const highPriority = leads.filter((l) => l.priority === "HIGH").length;
  const readyCount = leads.filter(isReadyForOutreach).length;
  const needsContact = leads.filter(needsContactEnrichment).length;

  const topOpportunities = [...leads]
    .filter((l) => l.priority === "HIGH" || (l.priority_score ?? 0) >= 60)
    .sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0))
    .slice(0, 8);

  const upcomingEvents = leads
    .filter((l) => hasUpcomingEvent(l))
    .sort((a, b) => {
      const da = a.next_project_date ?? "";
      const db = b.next_project_date ?? "";
      return da.localeCompare(db);
    })
    .slice(0, 8);

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        eyebrow="Overview"
        title="Commercial Intelligence"
        description="Government planning packets, turned into evidence-backed opportunities."
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Link href="/properties" className="panel panel-hover p-5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-foreground-muted">Total Opportunities</p>
          <p className="mt-3 font-mono text-2xl font-semibold tracking-tight text-foreground">{total}</p>
        </Link>
        <Link href="/properties?priority=HIGH" className="panel panel-hover p-5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-foreground-muted">High Priority</p>
          <p className="mt-3 font-mono text-2xl font-semibold tracking-tight text-priority-high">{highPriority}</p>
        </Link>
        <Link href="/ready-for-outreach" className="panel panel-hover p-5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-foreground-muted">Ready for Outreach</p>
          <p className="mt-3 font-mono text-2xl font-semibold tracking-tight text-status-positive">{readyCount}</p>
        </Link>
        <Link href="/contact-discovery" className="panel panel-hover p-5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-foreground-muted">Needs Contact</p>
          <p className="mt-3 font-mono text-2xl font-semibold tracking-tight text-status-caution">{needsContact}</p>
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_380px]">
        <div className="flex min-w-0 flex-col gap-4">
          <div>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-foreground">Top Opportunities</h2>
              <Link href="/properties" className="text-xs text-accent-strong hover:underline">View all →</Link>
            </div>
            {topOpportunities.length === 0 ? (
              <div className="panel p-8 text-center text-sm text-foreground-faint">No opportunities on record.</div>
            ) : (
              <div className="flex flex-col gap-2">
                {topOpportunities.map((lead) => (
                  <Link
                    key={lead.application_number}
                    href={`/properties/${lead.application_number}`}
                    className="panel panel-hover flex items-center gap-4 p-4"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="truncate text-sm font-medium text-foreground">{getPrimaryPartyName(lead)}</p>
                        <Badge variant={priorityVariant(lead.priority)}>{lead.priority}</Badge>
                      </div>
                      <p className="mt-0.5 text-xs text-foreground-muted">
                        {lead.application_type} · {lead.project_address ?? "—"}
                      </p>
                    </div>
                    <div className="hidden text-right sm:block">
                      <p className="text-xs text-foreground-muted">
                        {hasUpcomingEvent(lead)
                          ? `${formatDate(lead.next_project_date)} · ${formatDaysUntil(lead.days_until_event)}`
                          : "No event"}
                      </p>
                      <Badge variant={leadStatusVariant(lead.lead_status)}>
                        {isContactable(lead) ? "Contactable" : titleCase(lead.lead_status ?? "NO_CONTACT")}
                      </Badge>
                    </div>
                    <Badge variant={priorityVariant(lead.priority)} className="sm:hidden">{lead.priority_score ?? 0}</Badge>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <div>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-foreground">Upcoming Events</h2>
              <Link href="/upcoming" className="text-xs text-accent-strong hover:underline">View all →</Link>
            </div>
            {upcomingEvents.length === 0 ? (
              <div className="panel p-8 text-center text-sm text-foreground-faint">No upcoming events.</div>
            ) : (
              <div className="flex flex-col gap-2">
                {upcomingEvents.map((lead) => (
                  <Link
                    key={lead.application_number}
                    href={`/properties/${lead.application_number}`}
                    className="panel panel-hover p-4"
                  >
                    <div className="flex items-center justify-between">
                      <p className="truncate text-sm font-medium text-foreground">{getPrimaryPartyName(lead)}</p>
                      <span className="ml-2 shrink-0 font-mono text-xs text-foreground-faint">
                        {formatDate(lead.next_project_date)}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center justify-between">
                      <p className="truncate text-xs text-foreground-muted">{lead.application_type}</p>
                      <span className="ml-2 shrink-0 text-xs text-foreground-faint">
                        {formatDaysUntil(lead.days_until_event)}
                      </span>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
