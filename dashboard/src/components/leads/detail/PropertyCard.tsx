import type { Lead } from "@/lib/types";
import { SectionCard } from "./SectionCard";
import { Field } from "./Field";

export function PropertyCard({ lead }: { lead: Lead }) {
  const hasCoords =
    lead.address_geocoded_lat != null && lead.address_geocoded_lng != null;

  return (
    <SectionCard title="Property">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Field label="Address" value={lead.project_address} />
        <Field label="Municipality" value={lead.municipality} />
        <Field label="State" value={lead.state} />
        <Field label="Neighborhood" value={lead.neighborhood} />
        <Field label="Parcel" value={lead.parcel_number} mono />
        <Field label="Acreage" value={lead.acreage} />
        <Field label="Zoning" value={lead.zoning} />
        {hasCoords && (
          <>
            <Field
              label="Latitude"
              value={
                lead.address_geocoded_lat != null
                  ? Number(lead.address_geocoded_lat).toFixed(6)
                  : null
              }
              mono
            />
            <Field
              label="Longitude"
              value={
                lead.address_geocoded_lng != null
                  ? Number(lead.address_geocoded_lng).toFixed(6)
                  : null
              }
              mono
            />
            <Field label="Verified County" value={lead.address_geocoded_county} />
          </>
        )}
      </div>
    </SectionCard>
  );
}
