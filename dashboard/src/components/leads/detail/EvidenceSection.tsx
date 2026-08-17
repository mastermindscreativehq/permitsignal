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
  if (!url) return <span className="text-xs text-foreground-faint">No source URL</span>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="text-xs text-accent-strong hover:underline"
    >
      View source →
    </a>
  );
}

export function EvidenceSection({ lead }: { lead: Lead }) {
  const frictionEvidence = getFrictionEvidence(lead);
  const futureDates = getFutureProjectDates(lead);
  const historicalDates = getHistoricalProjectDates(lead);
  const searchQueries = getContactSearchQueries(lead);

  return (
    <SectionCard title="Evidence" description="Source documents and intelligence evidence behind this opportunity.">
      <div className="flex flex-col gap-5">
        {/* Friction evidence */}
        <div>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-foreground-faint">
            Friction Evidence ({frictionEvidence.length})
          </p>
          {frictionEvidence.length === 0 ? (
            <p className="text-sm text-foreground-faint">No friction evidence on record.</p>
          ) : (
            <div className="flex flex-col gap-2">
              {frictionEvidence.map((event, index) => (
                <div key={index} className="rounded-lg border border-border-subtle bg-surface p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={severityVariant(event.severity)}>{titleCase(event.event_type)}</Badge>
                    <span className="text-xs text-foreground-faint">{formatDate(event.event_date)}</span>
                    {event.confidence != null && (
                      <span className="text-xs text-foreground-faint">Conf {(event.confidence * 100).toFixed(0)}%</span>
                    )}
                  </div>
                  {event.matched_text && (
                    <p className="mt-1.5 text-xs font-medium text-foreground-muted">&ldquo;{event.matched_text}&rdquo;</p>
                  )}
                  {event.evidence && (
                    <p className="mt-1 text-xs leading-relaxed text-foreground-faint line-clamp-3">{event.evidence}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Future project dates */}
        <div>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-status-positive">
            Future Events ({futureDates.length})
          </p>
          {futureDates.length === 0 ? (
            <p className="text-sm text-foreground-faint">None found.</p>
          ) : (
            <div className="flex flex-col gap-1.5">
              {futureDates.map((date, index) => (
                <div key={index} className="flex items-center justify-between rounded-md bg-surface px-3 py-2">
                  <span className="text-xs font-medium text-foreground">{titleCase(date.label)}</span>
                  <span className="font-mono text-xs text-foreground-faint">
                    {formatDate(date.value)} {date.time ?? ""}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Historical/administrative dates */}
        {historicalDates.length > 0 && (
          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-foreground-faint">
              Historical / Administrative ({historicalDates.length})
            </p>
            <div className="flex max-h-48 flex-col gap-1 overflow-y-auto pr-1">
              {historicalDates.map((date, index) => (
                <div key={index} className="flex items-center justify-between rounded-md bg-surface/60 px-3 py-1.5">
                  <span className="text-xs text-foreground-muted">{titleCase(date.label)}</span>
                  <span className="font-mono text-[11px] text-foreground-faint">{formatDate(date.value)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Approval-action evidence */}
        {lead.approval_status && (
          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-foreground-faint">
              Approval-Action Evidence
            </p>
            <div className="rounded-lg border border-border-subtle bg-surface p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={approvalBasisVariant(lead.approval_basis)}>{titleCase(lead.approval_basis)}</Badge>
                {lead.approval_relevant_date && (
                  <span className="text-xs text-foreground-faint">{formatDate(lead.approval_relevant_date)}</span>
                )}
              </div>
              {lead.approval_evidence && (
                <p className="mt-2 text-xs leading-relaxed text-foreground-muted">{lead.approval_evidence}</p>
              )}
              <SourceLink url={lead.approval_source} />
            </div>
          </div>
        )}

        {/* Contact discovery evidence */}
        <div>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-foreground-faint">
            Contact Discovery ({searchQueries.length} queries)
          </p>
          {searchQueries.length === 0 ? (
            <p className="text-sm text-foreground-faint">No contact discovery run yet.</p>
          ) : (
            <div className="flex flex-col gap-1">
              {searchQueries.slice(0, 5).map((query, index) => (
                <code key={index} className="rounded bg-surface px-2 py-1 text-[11px] text-foreground-muted">
                  {query}
                </code>
              ))}
              {searchQueries.length > 5 && (
                <p className="text-[11px] text-foreground-faint">+{searchQueries.length - 5} more</p>
              )}
            </div>
          )}
        </div>

        {/* Source document link */}
        <div className="border-t border-border-subtle pt-3">
          <SourceLink url={lead.source_url} />
        </div>
      </div>
    </SectionCard>
  );
}
