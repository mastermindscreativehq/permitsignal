import Link from "next/link";
import { getLeads } from "@/lib/leads";
import { hasUpcomingEvent, getPrimaryPartyName, getPrimaryPartyRole } from "@/lib/lead-helpers";
import { formatDate, formatDaysUntil, priorityVariant, titleCase, urgencyVariant } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { PageHeader } from "@/components/layout/PageHeader";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

export default async function UpcomingEventsPage() {
  const leads = await getLeads();
  const upcoming = leads
    .filter(hasUpcomingEvent)
    .sort((a, b) => (a.next_project_date ?? "").localeCompare(b.next_project_date ?? ""));

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Upcoming Events"
        title="Project Events"
        description={`${upcoming.length} opportunit${upcoming.length === 1 ? "y has" : "ies have"} a future project event scheduled — hearings, meetings, and decision dates.`}
      />

      {upcoming.length === 0 ? (
        <div className="panel p-10 text-center">
          <p className="text-sm font-medium text-foreground">No upcoming events</p>
          <p className="mt-1 text-xs text-foreground-faint">
            No opportunities currently have a future project event on record.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {upcoming.map((lead) => (
            <Link
              key={lead.application_number}
              href={`/properties/${lead.application_number}`}
              className="panel panel-hover flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="truncate text-sm font-semibold text-foreground">{getPrimaryPartyName(lead)}</p>
                  <Badge variant={priorityVariant(lead.priority)}>{lead.priority}</Badge>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-foreground-muted">
                  <span>{lead.application_type} · {lead.application_number}</span>
                  <span>{lead.project_address ?? "—"}</span>
                </div>
              </div>
              <div className="flex items-center gap-4 sm:shrink-0">
                <div className="text-right">
                  <p className="text-sm font-medium text-foreground">{formatDate(lead.next_project_date)}</p>
                  <p className="text-xs text-foreground-muted">
                    {titleCase(lead.next_project_event)}
                    {lead.next_project_time ? ` · ${lead.next_project_time}` : ""}
                  </p>
                </div>
                <Badge variant={urgencyVariant(lead.urgency)}>
                  {formatDaysUntil(lead.days_until_event)}
                </Badge>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
