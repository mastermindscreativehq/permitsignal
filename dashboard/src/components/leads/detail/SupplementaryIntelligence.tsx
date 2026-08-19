"use client";

import { useState } from "react";
import type { Lead } from "@/lib/types";
import { formatCurrencyRange, formatDate, titleCase } from "@/lib/format";
import { getFutureProjectDates, getHistoricalProjectDates, getContactSearchQueries } from "@/lib/lead-helpers";
import { SectionCard } from "./SectionCard";
import { Field, ContactField } from "./Field";
import { PartiesCard } from "./PartiesCard";
import { FrictionCard } from "./FrictionCard";
import { NextEventCard } from "./NextEventCard";
import { FollowUpCard } from "./FollowUpCard";

/**
 * Supplementary intelligence sections displayed below the canonical
 * DeepIntelligenceCard. Contains ALL remaining intelligence that does
 * NOT duplicate the approval intelligence package:
 *
 *   - Why This Matters
 *   - Property Intelligence (parcel, acreage, zoning)
 *   - Parties
 *   - Friction
 *   - Complete Timeline (historical + future dates)
 *   - Contact Intelligence
 *   - Commercial Readiness
 *   - Follow-Up Intelligence
 *   - Outreach Intelligence
 *   - Economic Intelligence
 *   - Source & Evidence
 *   - Enrichment Intelligence
 */
export function SupplementaryIntelligence({ lead }: { lead: Lead }) {
  const [open, setOpen] = useState(false);
  const status = (lead.lead_status ?? "NOT_RUN") as string;
  const historicalDates = getHistoricalProjectDates(lead);
  const futureDates = getFutureProjectDates(lead);
  const searchQueries = getContactSearchQueries(lead);
  const hasPropertyDetails = lead.parcel_number || lead.acreage || lead.zoning;
  const hasTimeline = historicalDates.length > 0 || futureDates.length > 0;
  const hasOutreach = (lead.outreach_events?.length ?? 0) > 0 || lead.outreach_message_subject;
  const hasEnrichment = lead.enrichment_status || lead.identity_confidence || searchQueries.length > 0;

  return (
    <details open={open} className="group rounded-lg border border-border-subtle bg-card">
      <summary
        className="flex cursor-pointer items-center justify-between px-5 py-4 select-none"
        onClick={(e) => {
          e.preventDefault();
          setOpen(!open);
        }}
      >
        <div className="flex items-center gap-3">
          <svg
            className={`h-4 w-4 shrink-0 text-foreground-faint transition-transform ${open ? "rotate-90" : ""}`}
            viewBox="0 0 12 12"
            fill="currentColor"
          >
            <path d="M4.5 2l4 4-4 4" />
          </svg>
          <h3 className="text-[13px] font-semibold uppercase tracking-[0.1em] text-foreground">
            Supporting Intelligence
          </h3>
          <span className="text-[11px] text-foreground-faint">
            Property, parties, timeline, contacts, economics, sources
          </span>
        </div>
      </summary>

      {open && (
        <div className="flex flex-col gap-5 px-5 pb-5">
          {/* Why This Matters */}
          {lead.opportunity_reason && (
            <SectionCard title="Why This Matters">
              <p className="text-sm leading-relaxed text-foreground">{lead.opportunity_reason}</p>
            </SectionCard>
          )}

          {/* Property Intelligence */}
          {hasPropertyDetails && (
            <SectionCard title="Property Intelligence" description="Physical property details from the government record.">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <Field label="Parcel Number" value={lead.parcel_number} mono />
                <Field label="Acreage" value={lead.acreage} />
                <Field label="Zoning" value={lead.zoning ? titleCase(lead.zoning) : null} />
              </div>
            </SectionCard>
          )}

          {/* Parties */}
          <PartiesCard lead={lead} />

          {/* Friction */}
          <FrictionCard lead={lead} />

          {/* Next Event */}
          <NextEventCard lead={lead} />

          {/* Complete Timeline */}
          {hasTimeline && (
            <SectionCard title="Complete Timeline" description="Historical and future project dates from the government record.">
              {historicalDates.length > 0 && (
                <div className="mb-4">
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-foreground-faint">
                    Historical Events ({historicalDates.length})
                  </p>
                  <div className="flex max-h-48 flex-col gap-1 overflow-y-auto pr-1">
                    {historicalDates.map((date, index) => (
                      <div key={`hist-${index}`} className="flex items-center justify-between rounded-md bg-surface/60 px-3 py-1.5">
                        <span className="text-xs text-foreground-muted">{titleCase(date.label)}</span>
                        <span className="font-mono text-[11px] text-foreground-faint">{formatDate(date.value)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {futureDates.length > 0 && (
                <div>
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-status-positive">
                    Future Events ({futureDates.length})
                  </p>
                  <div className="flex flex-col gap-1.5">
                    {futureDates.map((date, index) => (
                      <div key={`fut-${index}`} className="flex items-center justify-between rounded-md bg-surface px-3 py-2">
                        <span className="text-xs font-medium text-foreground">{titleCase(date.label)}</span>
                        <span className="font-mono text-xs text-foreground-faint">
                          {formatDate(date.value)} {date.time ?? ""}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </SectionCard>
          )}

          {/* Contact Intelligence */}
          <SectionCard
            title="Contact Intelligence"
            actions={
              <span className="rounded-full border border-border-subtle px-2 py-0.5 text-[10px] font-medium text-foreground-faint">
                {status.replaceAll("_", " ")}
              </span>
            }
          >
            <div className="grid grid-cols-2 gap-3">
              <ContactField label="Applicant Email" value={lead.applicant_email} href={(v) => `mailto:${v}`} />
              <ContactField label="Applicant Phone" value={lead.applicant_phone} />
              <ContactField label="Contact Name" value={lead.contact_name} mono={false} />
              <ContactField label="Contact Role" value={lead.contact_role} mono={false} />
              <ContactField label="Company" value={lead.company_name} mono={false} />
              <ContactField label="LinkedIn" value={lead.linkedin_url} href={(v) => v} />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3 border-t border-border-subtle pt-3">
              <Field label="Email Confidence" value={lead.email_confidence ? titleCase(lead.email_confidence) : null} />
              <Field label="Phone Confidence" value={lead.phone_confidence ? titleCase(lead.phone_confidence) : null} />
              <Field label="Contact Source" value={lead.contact_source ? titleCase(lead.contact_source) : null} />
              <Field label="Contact Verified" value={lead.contact_is_verified === true ? "Yes" : lead.contact_is_verified === false ? "No" : null} />
            </div>
          </SectionCard>

          {/* Commercial Readiness */}
          {lead.commercial_readiness && (
            <SectionCard title="Commercial Readiness">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Readiness" value={lead.commercial_readiness?.replace(/_/g, " ")} />
                <Field label="Contactability" value={lead.contactability_level?.replace(/_/g, " ")} />
                {lead.outreach_contact_type && lead.outreach_contact_type !== "none" && (
                  <Field label="Outreach Target" value={titleCase(lead.outreach_contact_type)} />
                )}
                {lead.outreach_channel && lead.outreach_channel !== "none" && (
                  <Field label="Channel" value={titleCase(lead.outreach_channel)} />
                )}
              </div>
              {lead.recommended_commercial_action && (
                <div className="mt-3 rounded-lg border border-border-subtle bg-surface p-3">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">Recommended Action</p>
                  <p className="mt-1 text-sm font-medium text-foreground">{titleCase(lead.recommended_commercial_action)}</p>
                  {lead.commercial_action_reason && (
                    <p className="mt-1 text-xs text-foreground-muted">{lead.commercial_action_reason}</p>
                  )}
                </div>
              )}
            </SectionCard>
          )}

          {/* Follow-Up Intelligence */}
          <FollowUpCard lead={lead} />

          {/* Outreach Intelligence */}
          {hasOutreach && (
            <SectionCard title="Outreach Intelligence" description="Outreach history and messaging.">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Outreach Status" value={lead.outreach_status?.replace(/_/g, " ")} />
                <Field label="Qualification" value={lead.outreach_qualification_status?.replace(/_/g, " ")} />
                <Field label="Last Outreach" value={lead.last_outreach_at ? formatDate(lead.last_outreach_at.split("T")[0]) : null} />
                <Field label="Follow-Up Required" value={lead.follow_up_required ? "Yes" : "No"} />
              </div>
              {lead.follow_up_reason && (
                <p className="mt-2 text-xs text-foreground-muted">{lead.follow_up_reason}</p>
              )}
              {lead.outreach_message_subject && (
                <div className="mt-3 rounded-lg border border-border-subtle bg-surface p-3">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">Draft Message</p>
                  <p className="mt-1 text-sm font-medium text-foreground">{lead.outreach_message_subject}</p>
                  {lead.outreach_message_body && (
                    <p className="mt-1 whitespace-pre-line text-xs leading-relaxed text-foreground-muted">{lead.outreach_message_body}</p>
                  )}
                </div>
              )}
              {lead.outreach_events && lead.outreach_events.length > 0 && (
                <div className="mt-3">
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-foreground-faint">
                    Outreach Events ({lead.outreach_events.length})
                  </p>
                  <ul className="space-y-1.5">
                    {lead.outreach_events.map((event, index) => (
                      <li key={index} className="flex items-start gap-2 rounded bg-surface/60 px-3 py-2 text-xs">
                        <span className="font-medium text-foreground">{titleCase(event.event)}</span>
                        {event.occurred_at && <span className="text-foreground-faint"> · {formatDate(event.occurred_at.split("T")[0])}</span>}
                        {event.note && <span className="block text-foreground-faint">{event.note}</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </SectionCard>
          )}

          {/* Economic Intelligence */}
          {(lead.estimated_value_low !== null || lead.public_funding_status) && (
            <SectionCard title="Economic Intelligence" description="Project value and public spending estimates.">
              <div className="grid grid-cols-2 gap-3">
                <Field
                  label="Est. Project Value"
                  value={
                    lead.estimated_value_low !== null
                      ? formatCurrencyRange(lead.estimated_value_low, lead.estimated_value_high)
                      : null
                  }
                />
                <Field
                  label="Public Spend"
                  value={
                    lead.public_spend_low !== null
                      ? formatCurrencyRange(lead.public_spend_low, lead.public_spend_high)
                      : null
                  }
                />
                <Field
                  label="Scale"
                  value={lead.project_scale_units ? `${lead.project_scale_units} × ${titleCase(lead.project_scale_type)}` : null}
                />
                <Field label="Confidence" value={lead.estimated_value_confidence ? titleCase(lead.estimated_value_confidence) : null} />
                <Field label="Value Source" value={lead.estimated_value_source_type?.replace(/_/g, " ")} />
                <Field label="Public Funding" value={lead.public_funding_status?.replace(/_/g, " ")} />
              </div>
              {lead.estimated_value_basis && (
                <p className="mt-3 text-[11px] text-foreground-faint">{lead.estimated_value_basis}</p>
              )}
              {lead.public_funding_basis && (
                <p className="mt-1 text-[11px] text-foreground-faint">{lead.public_funding_basis}</p>
              )}
            </SectionCard>
          )}

          {/* Source & Evidence */}
          <SectionCard title="Source & Evidence" description="Government document origin and retrieval information.">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Source" value={lead.source} />
              <Field label="Source URL" value={lead.source_url ? (
                <a href={lead.source_url} target="_blank" rel="noreferrer" className="text-accent-strong hover:underline">
                  View source document
                </a>
              ) : null} />
              <Field label="Municipality" value={lead.municipality} />
              <Field label="State" value={lead.state} />
              <Field label="Created" value={lead.created_at ? formatDate(lead.created_at.split("T")[0]) : null} />
              <Field label="Builder Version" value={lead.builder_version} />
            </div>
          </SectionCard>

          {/* Enrichment Intelligence */}
          {hasEnrichment && (
            <SectionCard title="Enrichment Intelligence" description="Contact discovery and enrichment process status.">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Enrichment Status" value={lead.enrichment_status ? titleCase(lead.enrichment_status) : null} />
                <Field label="Identity Confidence" value={lead.identity_confidence ? titleCase(lead.identity_confidence) : null} />
                <Field label="Enrichment Method" value={lead.enrichment_method ? titleCase(lead.enrichment_method) : null} />
                <Field label="Identity Status" value={lead.identity_status ? titleCase(lead.identity_status) : null} />
              </div>
              {searchQueries.length > 0 && (
                <div className="mt-3">
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-foreground-faint">
                    Search Queries Performed ({searchQueries.length})
                  </p>
                  <div className="flex flex-col gap-1">
                    {searchQueries.map((query, index) => (
                      <code key={index} className="rounded bg-surface px-2 py-1 text-[11px] text-foreground-muted">
                        {query}
                      </code>
                    ))}
                  </div>
                </div>
              )}
            </SectionCard>
          )}
        </div>
      )}
    </details>
  );
}
