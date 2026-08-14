import type { Lead } from "@/lib/types";
import { titleCase } from "@/lib/format";
import { getPartiesByRole, getPrimaryOwnerDisplay, isOwnerKnown } from "@/lib/lead-helpers";
import { Badge } from "@/components/ui/Badge";
import { SectionCard } from "./SectionCard";
import { ContactField, Field } from "./Field";

function RoleRow({
  role,
  name,
  detail,
  confidence,
  source,
}: {
  role: string;
  name: string | null;
  detail?: string | null;
  confidence?: string | null;
  source?: string | null;
}) {
  const isEmpty = !name;
  return (
    <div className="grid grid-cols-[140px_1fr_auto] items-baseline gap-3 py-2.5">
      <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">{role}</p>
      <div className="min-w-0">
        {isEmpty ? (
          <p className="inline-flex items-center gap-1.5 text-sm italic text-foreground-faint/70">
            <span className="h-1.5 w-1.5 rounded-full bg-status-neutral" />
            NOT FOUND
          </p>
        ) : (
          <>
            <p className="truncate text-sm text-foreground">{name}</p>
            {detail && <p className="truncate text-xs text-foreground-faint">{detail}</p>}
          </>
        )}
      </div>
      <p className="whitespace-nowrap text-right text-[11px] text-foreground-faint">
        {confidence ? titleCase(confidence) : ""}
        {confidence && source ? " · " : ""}
        {source ? titleCase(source) : ""}
      </p>
    </div>
  );
}

/**
 * The full Parties roster for a property -- deliberately tiered, not a
 * flat list. Owner is visually dominant (own slot, larger type), the
 * commercial/professional parties are peers of each other below it, and
 * Government Staff sits below a divider in a distinct, muted treatment so
 * it reads as an official reference contact rather than a lead.
 */
export function PartiesCard({ lead }: { lead: Lead }) {
  const ownerKnown = isOwnerKnown(lead);
  const { primary: ownerPrimary, contactName: ownerContactName } = getPrimaryOwnerDisplay(lead);
  const { engineer, architect, others } = getPartiesByRole(lead);
  const hasStaff = Boolean(lead.staff_contact_name || lead.staff_contact_email || lead.staff_contact_phone);

  return (
    <SectionCard
      title="Parties"
      description="Every party on record for this property, ranked by commercial relevance -- not flattened to equal importance."
    >
      {/* Tier 1: Owner -- the dominant identity. */}
      <div className={`rounded-md border p-4 ${ownerKnown ? "border-accent/35 bg-accent-soft/25" : "border-border-subtle bg-surface"}`}>
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent-strong">Property Owner</p>
        {ownerPrimary ? (
          <p className="mt-1 flex flex-wrap items-center gap-2 text-lg font-semibold leading-tight text-foreground">
            {ownerPrimary}
            {lead.owner_type && (
              <Badge variant="accent" dot={false}>
                {titleCase(lead.owner_type)}
              </Badge>
            )}
          </p>
        ) : (
          <p className="mt-1 inline-flex items-center gap-1.5 text-lg italic text-foreground-faint/70">
            <span className="h-2 w-2 rounded-full bg-status-neutral" />
            NOT FOUND
          </p>
        )}
        {!ownerKnown && (
          <p className="mt-1 text-xs text-foreground-faint">
            The source document does not label an owner distinct from the applicant -- evidence-backed absence, not a guess.
          </p>
        )}
        <div className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1 border-t border-border-subtle/70 pt-2">
          <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">Owner Contact</p>
          {ownerContactName ? (
            <p className="text-sm text-foreground">{ownerContactName}</p>
          ) : (
            <p className="text-sm italic text-foreground-faint/70">NOT FOUND</p>
          )}
          {(lead.owner_confidence || lead.owner_source) && (
            <p className="ml-auto text-[11px] text-foreground-faint">
              {lead.owner_confidence ? titleCase(lead.owner_confidence) : ""}
              {lead.owner_confidence && lead.owner_source ? " · " : ""}
              {lead.owner_source ? titleCase(lead.owner_source) : ""}
            </p>
          )}
        </div>
        {(lead.owner_contact_email || lead.owner_contact_phone || lead.owner_website) && (
          <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <ContactField label="Email" value={lead.owner_contact_email} href={(v) => `mailto:${v}`} />
            <ContactField label="Phone" value={lead.owner_contact_phone} />
            <ContactField label="Website" value={lead.owner_website} href={(v) => (v.startsWith("http") ? v : `https://${v}`)} />
          </div>
        )}
      </div>

      {/* Tier 2: commercial / professional parties -- peers of each other, secondary to the owner. */}
      <div className="mt-3 divide-y divide-border-subtle/70 rounded-md border border-border-subtle px-4">
        <RoleRow
          role="Applicant / Agent"
          name={lead.applicant_name}
          detail={lead.company_name ?? lead.applicant_entity}
          confidence={lead.applicant_confidence}
          source={lead.applicant_source}
        />
        <RoleRow
          role="Engineer"
          name={engineer?.party_name ?? null}
          detail={engineer?.party_company}
          confidence={engineer?.party_confidence}
        />
        <RoleRow
          role="Architect"
          name={architect?.party_name ?? null}
          detail={architect?.party_company}
          confidence={architect?.party_confidence}
        />
        <RoleRow
          role="Other Parties"
          name={others.length ? others.map((p) => p.party_name).filter(Boolean).join(", ") : null}
          detail={others.length ? others.map((p) => titleCase(p.party_role)).filter(Boolean).join(", ") : null}
        />
      </div>

      {/* Tier 3: Government Staff -- an official record, never a commercial party. */}
      <div className="mt-3 rounded-md border border-border-subtle bg-background-elevated px-4 py-3">
        <p className="text-[10px] font-medium uppercase tracking-wide text-foreground-faint">
          Government Staff · Official Record — Not a Commercial Party
        </p>
        {hasStaff ? (
          <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Field label="Name" value={lead.staff_contact_name} />
            <ContactField label="Email" value={lead.staff_contact_email} href={(v) => `mailto:${v}`} />
            <ContactField label="Phone" value={lead.staff_contact_phone} />
          </div>
        ) : (
          <p className="mt-1 text-sm italic text-foreground-faint/70">No government staff contact on record.</p>
        )}
      </div>
    </SectionCard>
  );
}
