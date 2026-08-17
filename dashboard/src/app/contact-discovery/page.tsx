import Link from "next/link";
import { getLeads } from "@/lib/leads";
import { needsContactDiscovery, needsContactEnrichment, getPrimaryPartyName, isOwnerKnown } from "@/lib/lead-helpers";
import { priorityVariant } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { PageHeader } from "@/components/layout/PageHeader";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

export default async function ContactDiscoveryPage() {
  const leads = await getLeads();
  const needsDiscovery = leads
    .filter(needsContactDiscovery)
    .sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0));

  const needsEnrichment = leads
    .filter(needsContactEnrichment)
    .sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0));

  const all = [...needsDiscovery, ...needsEnrichment];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Contact Discovery"
        title="Contact Intelligence"
        description={`${all.length} lead${all.length === 1 ? "" : "s"} need${all.length === 1 ? "s" : ""} contact discovery or enrichment before outreach is possible.`}
      />

      {all.length === 0 ? (
        <div className="panel p-10 text-center">
          <p className="text-sm font-medium text-foreground">All contacts discovered</p>
          <p className="mt-1 text-xs text-foreground-faint">
            Every opportunity has contact intelligence on record.
          </p>
          <Link href="/ready-for-outreach" className="mt-4 inline-block rounded-md border border-border-subtle bg-surface px-3.5 py-2 text-sm font-medium text-foreground transition-colors hover:border-accent hover:text-accent-strong">
            View Ready for Outreach →
          </Link>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {all.map((lead) => {
            const ownerKnown = isOwnerKnown(lead);
            const isDiscovery = needsContactDiscovery(lead);
            return (
              <Link
                key={lead.application_number}
                href={`/properties/${lead.application_number}`}
                className="panel panel-hover flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-sm font-semibold text-foreground">{getPrimaryPartyName(lead)}</p>
                    <Badge variant={priorityVariant(lead.priority)}>{lead.priority}</Badge>
                    <Badge variant={isDiscovery ? "status-caution" : "status-neutral"}>
                      {isDiscovery ? "Needs Discovery" : "Needs Enrichment"}
                    </Badge>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-foreground-muted">
                    <span>{lead.application_type} · {lead.application_number}</span>
                    <span>{lead.project_address ?? "—"}</span>
                    {lead.municipality && <span>{lead.municipality}</span>}
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-4">
                    <div>
                      <span className="text-foreground-faint">Applicant email: </span>
                      <span className={lead.applicant_email ? "text-foreground" : "italic text-foreground-faint"}>
                        {lead.applicant_email ?? "Not found"}
                      </span>
                    </div>
                    <div>
                      <span className="text-foreground-faint">Applicant phone: </span>
                      <span className={lead.applicant_phone ? "text-foreground" : "italic text-foreground-faint"}>
                        {lead.applicant_phone ?? "Not found"}
                      </span>
                    </div>
                    <div>
                      <span className="text-foreground-faint">Owner: </span>
                      <span className={ownerKnown ? "text-foreground" : "italic text-foreground-faint"}>
                        {ownerKnown ? getPrimaryPartyName(lead) : "Not identified"}
                      </span>
                    </div>
                    <div>
                      <span className="text-foreground-faint">Company: </span>
                      <span className={lead.company_name ? "text-foreground" : "italic text-foreground-faint"}>
                        {lead.company_name ?? "Not found"}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3 sm:shrink-0">
                  <span className="font-mono text-sm font-semibold text-foreground">{lead.priority_score ?? 0}</span>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
