import type { Lead } from "@/lib/types";
import {
  getContactSearchQueries,
  getFrictionEvidence,
  getFutureProjectDates,
  getHistoricalProjectDates,
} from "@/lib/lead-helpers";
import { approvalBasisVariant, formatDate, severityVariant, titleCase } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { SectionCard } from "./SectionCard";
import { Field } from "./Field";

function SourceLink({ url }: { url: string | null | undefined }) {
  if (!url) return <span className="text-xs text-foreground-faint">No source URL on record</span>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="text-xs text-accent-strong hover:underline"
    >
      View source document →
    </a>
  );
}

export function EvidenceView({ lead }: { lead: Lead }) {
  const frictionEvidence = getFrictionEvidence(lead);
  const futureDates = getFutureProjectDates(lead);
  const historicalDates = getHistoricalProjectDates(lead);
  const searchQueries = getContactSearchQueries(lead);
  const emailCandidates = Array.isArray(lead.email_candidates) ? lead.email_candidates : [];
  const phoneCandidates = Array.isArray(lead.phone_candidates) ? lead.phone_candidates : [];

  return (
    <div className="flex flex-col gap-5">
      <SectionCard
        title="Friction Evidence"
        description="Raw text spans the friction analyzer matched against, with the source packet."
        actions={<SourceLink url={lead.source_url} />}
      >
        {frictionEvidence.length === 0 ? (
          <p className="text-sm text-foreground-faint">No friction evidence recorded for this application.</p>
        ) : (
          <div className="flex flex-col gap-3">
            {frictionEvidence.map((event, index) => (
              <div key={index} className="rounded-lg border border-border-subtle bg-surface p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={severityVariant(event.severity)}>{titleCase(event.event_type)}</Badge>
                  <span className="text-xs text-foreground-faint">{formatDate(event.event_date)}</span>
                  {event.confidence != null && (
                    <span className="text-xs text-foreground-faint">Confidence {(event.confidence * 100).toFixed(0)}%</span>
                  )}
                  {event.relevance != null && (
                    <span className="text-xs text-foreground-faint">Relevance {(event.relevance * 100).toFixed(0)}%</span>
                  )}
                </div>
                {event.matched_text && (
                  <p className="mt-2 text-xs font-medium text-foreground-muted">Matched: “{event.matched_text}”</p>
                )}
                {event.evidence && (
                  <p className="mt-1 text-sm leading-relaxed text-foreground-muted">{event.evidence}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="Project Event Evidence"
        description="Every date the extractor found in the packet, classified as future project events vs. administrative/historical dates."
      >
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-status-positive">
              Future Events ({futureDates.length})
            </p>
            <div className="flex flex-col gap-2">
              {futureDates.length === 0 && <p className="text-sm text-foreground-faint">None found.</p>}
              {futureDates.map((date, index) => (
                <div key={index} className="rounded-lg border border-border-subtle bg-surface p-2.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-foreground">{titleCase(date.label)}</span>
                    <span className="font-mono text-foreground-faint">
                      {formatDate(date.value)} {date.time ?? ""}
                    </span>
                  </div>
                  {date.confidence != null && (
                    <p className="mt-1 text-[11px] text-foreground-faint">
                      Confidence {(date.confidence * 100).toFixed(0)}%
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-foreground-faint">
              Historical / Administrative ({historicalDates.length})
            </p>
            <div className="flex max-h-72 flex-col gap-2 overflow-y-auto pr-1">
              {historicalDates.length === 0 && <p className="text-sm text-foreground-faint">None found.</p>}
              {historicalDates.map((date, index) => (
                <div key={index} className="rounded-lg border border-border-subtle/60 bg-surface/60 p-2.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-foreground-muted">{titleCase(date.label)}</span>
                    <span className="font-mono text-foreground-faint">{formatDate(date.value)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Approval-Action Evidence"
        description="The government-record or scheduling evidence PermitSignal's approval-action recommendation is derived from."
      >
        {lead.approval_status ? (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={approvalBasisVariant(lead.approval_basis)}>{titleCase(lead.approval_basis)}</Badge>
              <span className="text-xs text-foreground-faint">Source type: {titleCase(lead.approval_source_type)}</span>
              {lead.approval_relevant_date && (
                <span className="text-xs text-foreground-faint">{formatDate(lead.approval_relevant_date)}</span>
              )}
            </div>
            {lead.approval_evidence && (
              <p className="rounded-lg border border-border-subtle bg-surface p-3 text-sm leading-relaxed text-foreground-muted">
                {lead.approval_evidence}
              </p>
            )}
            {lead.approval_source && (
              <SourceLink url={lead.approval_source} />
            )}
          </div>
        ) : (
          <p className="text-sm text-foreground-faint">No approval-action evidence recorded for this application.</p>
        )}
      </SectionCard>

      <SectionCard
        title="Company Identification Evidence"
        description="How (or whether) this applicant was resolved to a company."
      >
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Field label="Company" value={lead.company_name} />
          <Field label="Domain" value={lead.company_domain} mono />
          <Field label="Source" value={lead.company_source ? titleCase(lead.company_source) : null} />
        </div>
      </SectionCard>

      <SectionCard
        title="Contact Discovery Evidence"
        description="Search queries and candidates evaluated for this applicant. Empty candidate lists mean discovery hasn't surfaced a public source -- not that data was hidden."
      >
        <Field
          label="Identity Status"
          value={lead.identity_status ? titleCase(lead.identity_status) : null}
        />
        <div className="mt-4">
          <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-foreground-faint">
            Search Queries Used ({searchQueries.length})
          </p>
          {searchQueries.length === 0 ? (
            <p className="text-sm text-foreground-faint">No contact discovery has been run yet.</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {searchQueries.map((query, index) => (
                <li key={index} className="rounded-md bg-surface px-2.5 py-1.5 font-mono text-xs text-foreground-muted">
                  {query}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-foreground-faint">
              Email Candidates ({emailCandidates.length})
            </p>
            <p className="text-sm text-foreground-faint">
              {emailCandidates.length === 0 ? "None found." : `${emailCandidates.length} candidate(s) evaluated.`}
            </p>
          </div>
          <div>
            <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-foreground-faint">
              Phone Candidates ({phoneCandidates.length})
            </p>
            <p className="text-sm text-foreground-faint">
              {phoneCandidates.length === 0 ? "None found." : `${phoneCandidates.length} candidate(s) evaluated.`}
            </p>
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
