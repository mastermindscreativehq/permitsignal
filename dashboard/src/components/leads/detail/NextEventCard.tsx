import type { Lead } from "@/lib/types";
import { formatDate, formatDaysUntil, titleCase, urgencyVariant } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { SectionCard } from "./SectionCard";
import { Field } from "./Field";

export function NextEventCard({ lead }: { lead: Lead }) {
  const hasEvent = lead.has_future_opportunity && lead.next_project_date;

  return (
    <SectionCard title="Next Event" actions={hasEvent ? <Badge variant={urgencyVariant(lead.urgency)}>{lead.urgency ?? "Scheduled"}</Badge> : undefined}>
      {hasEvent ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Field label="Date" value={formatDate(lead.next_project_date)} mono />
          <Field label="Event" value={titleCase(lead.next_project_event)} />
          <Field label="Time" value={lead.next_project_time} mono />
          <Field label="Days Remaining" value={formatDaysUntil(lead.days_until_event)} />
        </div>
      ) : (
        <p className="text-sm text-foreground-faint">No verified upcoming project event.</p>
      )}
    </SectionCard>
  );
}
