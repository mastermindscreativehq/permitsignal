import type { Lead } from "@/lib/types";
import { isContactable, needsContactDiscovery } from "@/lib/lead-helpers";
import { formatDaysUntil, titleCase } from "@/lib/format";
import { SectionCard } from "./SectionCard";

function buildFollowUpNote(lead: Lead): string {
  if (isContactable(lead)) {
    return `A verified public contact is on file (${lead.contact_source ? titleCase(lead.contact_source) : "public source"}) -- this lead is ready for direct outreach.`;
  }
  if (needsContactDiscovery(lead)) {
    return "No public contact has been verified yet. Recommend running contact discovery before outreach -- do not guess an email or phone number.";
  }
  return "Contact discovery previously failed to verify a public source for this applicant.";
}

export function FollowUpCard({ lead }: { lead: Lead }) {
  const hasEvent = lead.has_future_opportunity && lead.next_project_date;

  return (
    <SectionCard title="Follow-Up Intelligence" description="Evidence-based summary of why this lead deserves attention.">
      <p className="text-sm leading-relaxed text-foreground">
        {lead.opportunity_reason ?? `${lead.applicant_name ?? "This applicant"} has an open ${lead.application_type ?? "application"}.`}
        {hasEvent && ` Next milestone in ${formatDaysUntil(lead.days_until_event).toLowerCase()}.`}
      </p>
      <p className="mt-3 text-sm leading-relaxed text-foreground-muted">{buildFollowUpNote(lead)}</p>
    </SectionCard>
  );
}
