import type { Lead, LeadStatus } from "@/lib/types";
import { leadStatusVariant, titleCase } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { SectionCard } from "./SectionCard";
import { ContactField, Field } from "./Field";

const STATUS_COPY: Record<LeadStatus, string> = {
  CONTACTABLE: "A verified, public contact method was found for this applicant. Ready for outreach.",
  QUALIFIED: "Identity and company were resolved with enough confidence to qualify this lead, pending final contact verification.",
  NO_CONTACT: "No public contact information has been found yet. This is a valid state -- evidence-backed absence, not a failure.",
  NOT_RUN: "Contact discovery has not been attempted for this lead yet.",
  FAILED: "Contact discovery ran but could not verify a public source.",
};

export function ContactIntelligenceCard({ lead }: { lead: Lead }) {
  const status = (lead.lead_status ?? "NOT_RUN") as LeadStatus;

  return (
    <SectionCard
      title="Contact Intelligence"
      actions={<Badge variant={leadStatusVariant(status)}>{status.replaceAll("_", " ")}</Badge>}
    >
      <p className="text-sm leading-relaxed text-foreground-muted">{STATUS_COPY[status] ?? STATUS_COPY.NOT_RUN}</p>

      <div className="mt-4 grid grid-cols-2 gap-4">
        <ContactField label="Applicant Email" value={lead.applicant_email} href={(v) => `mailto:${v}`} />
        <ContactField label="Applicant Phone" value={lead.applicant_phone} />
        <ContactField label="Contact Name" value={lead.contact_name} mono={false} />
        <ContactField label="Contact Role" value={lead.contact_role} mono={false} />
        <ContactField label="Contact Email" value={lead.contact_email} href={(v) => `mailto:${v}`} />
        <ContactField label="Contact Phone" value={lead.contact_phone} />
        <ContactField label="LinkedIn" value={lead.linkedin_url} href={(v) => v} />
        <ContactField label="Company" value={lead.company_name} mono={false} />
        <ContactField
          label="Company Website"
          value={lead.company_website}
          href={(v) => (v.startsWith("http") ? v : `https://${v}`)}
        />
        <ContactField label="Company Domain" value={lead.company_domain} />
      </div>

      <div className="mt-5 grid grid-cols-2 gap-4 border-t border-border-subtle pt-4">
        <Field label="Email Confidence" value={lead.email_confidence ? titleCase(lead.email_confidence) : null} />
        <Field label="Phone Confidence" value={lead.phone_confidence ? titleCase(lead.phone_confidence) : null} />
        <Field label="Public" value={lead.contact_is_public === null ? null : lead.contact_is_public ? "Yes" : "No"} />
        <Field label="Verified" value={lead.contact_is_verified === null ? null : lead.contact_is_verified ? "Yes" : "No"} />
        <Field label="Contactability" value={lead.contactability_level ? titleCase(lead.contactability_level) : null} />
      </div>
    </SectionCard>
  );
}
