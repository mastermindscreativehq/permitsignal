import type { Lead, PropertyAddressComponents } from "@/lib/types";
import { SectionCard } from "./SectionCard";
import { Field } from "./Field";

const MISSING_IN_SOURCE = "Not stated in source record";

/**
 * Case Information -- the two core case facts as they exist in the
 * official government source document:
 *
 * 1. Case ID / Application Number: application_number is the
 *    government-issued identifier read from the record itself
 *    (never an internal PermitSignal id). The application_id_* fields
 *    record how the source identifies it.
 * 2. Full Property Address: property_address_full is the most complete
 *    address form actually stated in the source; components are parsed
 *    from it. Anything the source does not state is displayed honestly
 *    as missing rather than inferred (CLAUDE.md contact-integrity rules).
 */
export function CaseInformationCard({ lead }: { lead: Lead }) {
  const components: PropertyAddressComponents | null =
    (lead.property_address_components as PropertyAddressComponents | null | undefined) ?? null;

  const fullAddress = lead.property_address_full ?? lead.project_address;

  const city = components?.city ?? null;
  const state = components?.state ?? null;
  const postalCode = components?.postal_code ?? null;
  const unit = components?.unit ?? null;

  // Honest-missing explanation: when the source states only a street,
  // say so explicitly instead of leaving blank fields.
  const addressIncomplete =
    Boolean(fullAddress) &&
    (!city || !state || !postalCode);

  const identifierType = lead.application_id_type ?? null;
  const identifierLabel = lead.application_id_label ?? null;

  const identifierCaption = [
    identifierLabel ? `source label "${identifierLabel}"` : null,
    identifierType ? `identified as ${identifierType}` : null,
    lead.application_id_confidence ? `${lead.application_id_confidence} confidence` : null,
    lead.application_id_source === "government_record" ? "read directly from the government record" : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <SectionCard
      title="Case Information"
      description="Core case facts exactly as stated in the official government planning record."
    >
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Field label="Case ID / Application Number" value={lead.application_number} mono />
        <Field
          label="Identifier Type"
          value={identifierCaption || identifierType}
          fallback={MISSING_IN_SOURCE}
        />
        <div className="col-span-2 sm:col-span-1">
          <Field
            label="Full Property Address"
            value={fullAddress}
            fallback={MISSING_IN_SOURCE}
          />
        </div>
        <Field label="City" value={city} fallback={MISSING_IN_SOURCE} />
        <Field label="State" value={state} fallback={MISSING_IN_SOURCE} />
        <Field label="ZIP Code" value={postalCode} fallback={MISSING_IN_SOURCE} mono />
        <Field label="Unit" value={unit} fallback="—" mono />
        <div className="col-span-2 sm:col-span-2">
          <Field label="Parcel" value={lead.parcel_number} mono />
        </div>
      </div>

      {addressIncomplete && (
        <p className="mt-4 text-xs italic text-foreground-faint">
          The official source document states this location as a partial address
          {lead.property_address_completeness === "street_only" ? " (street only)" : ""}; the missing
          city/state/ZIP details are not written anywhere in the record and are therefore not shown.
        </p>
      )}

      {!fullAddress && (
        <p className="mt-4 text-xs italic text-foreground-faint">
          This government record does not state a property address for this item.
        </p>
      )}
    </SectionCard>
  );
}
