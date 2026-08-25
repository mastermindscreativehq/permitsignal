import type { Lead, PropertyAddressComponents } from "@/lib/types";
import { SectionCard } from "./SectionCard";
import { Field } from "./Field";

const MISSING_IN_SOURCE = "Not stated in source record";

const CONFIDENCE_COLORS: Record<string, string> = {
  HIGH: "text-green-600 dark:text-green-400",
  MEDIUM: "text-yellow-600 dark:text-yellow-400",
  LOW: "text-orange-600 dark:text-orange-400",
  UNRESOLVED: "text-red-600 dark:text-red-400",
};

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
 * 3. Address Intelligence: geocoded, verified real-world location data
 *    is displayed separately and never overwrites the source address.
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

  // Address Intelligence fields
  const aiStatus = lead.address_enrichment_status ?? null;
  const aiConfidence = lead.address_geocoding_confidence ?? null;
  const aiLat = lead.address_geocoded_lat ?? null;
  const aiLng = lead.address_geocoded_lng ?? null;
  const aiCity = lead.address_geocoded_city ?? null;
  const aiState = lead.address_geocoded_state ?? null;
  const aiPostal = lead.address_geocoded_postal ?? null;
  const aiCounty = lead.address_geocoded_county ?? null;
  const aiFull = lead.address_geocoded_full ?? null;
  const aiSource = lead.address_geocoding_source ?? null;
  const aiMethod = lead.address_geocoding_method ?? null;
  const aiParcel = lead.address_parcel_id_verified ?? null;
  const aiAt = lead.address_geocoded_at ?? null;

  const hasAddressIntelligence =
    aiStatus === "enriched" &&
    (aiLat != null || aiLng != null || aiCity != null);

  return (
    <SectionCard
      title="Case Information"
      description="Core case facts exactly as stated in the official government planning record."
    >
      {/* --- Official Source Address --- */}
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

      {/* --- Address Intelligence (Verified Location) --- */}
      {hasAddressIntelligence && (
        <div className="mt-5 border-t border-border pt-4">
          <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-foreground-faint mb-3">
            Address Intelligence — Verified Location
          </h4>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <div className="col-span-2 sm:col-span-3">
              <Field label="Geocoded Address" value={aiFull} fallback="Not resolved" />
            </div>
            <Field
              label="Confidence"
              value={
                aiConfidence ? (
                  <span className={CONFIDENCE_COLORS[aiConfidence] ?? ""}>
                    {aiConfidence}
                  </span>
                ) : null
              }
              fallback="—"
            />
            <Field label="City" value={aiCity} fallback="—" />
            <Field label="State" value={aiState} fallback="—" />
            <Field label="ZIP Code" value={aiPostal} fallback="—" mono />
            <Field label="County" value={aiCounty} fallback="—" />
            <Field
              label="Coordinates"
              value={
                aiLat != null && aiLng != null
                  ? `${Number(aiLat).toFixed(6)}, ${Number(aiLng).toFixed(6)}`
                  : null
              }
              fallback="—"
              mono
            />
            <Field label="Provider" value={aiSource} fallback="—" />
            <Field label="Method" value={aiMethod} fallback="—" />
            <Field label="Parcel Verified" value={aiParcel} fallback="—" mono />
            <div className="col-span-2 sm:col-span-2">
              <Field
                label="Enriched At"
                value={
                  aiAt
                    ? new Date(aiAt).toLocaleString()
                    : null
                }
                fallback="—"
              />
            </div>
          </div>
        </div>
      )}

      {aiStatus === "enriched" && !hasAddressIntelligence && (
        <div className="mt-5 border-t border-border pt-4">
          <p className="text-xs italic text-foreground-faint">
            Address intelligence was processed but no geocoded location data was resolved.
          </p>
        </div>
      )}

      {aiStatus === "not_resolved" && (
        <div className="mt-5 border-t border-border pt-4">
          <p className="text-xs italic text-foreground-faint">
            Address intelligence could not resolve this location to a verified address.
          </p>
        </div>
      )}
    </SectionCard>
  );
}
