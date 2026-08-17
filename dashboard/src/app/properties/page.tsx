import { getLeads } from "@/lib/leads";
import { filterLeads, getApplicationTypes } from "@/lib/lead-helpers";
import type { LeadFilters, LeadStatus, Priority } from "@/lib/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { OpportunityFilters } from "@/components/leads/OpportunityFilters";
import { LeadQueueTable } from "@/components/leads/LeadQueueTable";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

type SearchParams = Promise<{
  priority?: string;
  status?: string;
  type?: string;
  contactability?: string;
  event?: string;
  friction?: string;
  readiness?: string;
  stage?: string;
  approval?: string;
  recent?: string;
  tab?: string;
}>;

export default async function PropertyIntelligencePage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const params = await searchParams;
  const leads = await getLeads();
  const applicationTypes = getApplicationTypes(leads);

  const filters: LeadFilters = {
    priority: params.priority as Priority | undefined,
    leadStatus: params.status as LeadStatus | undefined,
    applicationType: params.type,
    contactability: params.contactability as LeadFilters["contactability"],
    upcomingEvent: params.event as LeadFilters["upcomingEvent"],
    friction: params.friction as LeadFilters["friction"],
    readiness: params.readiness as LeadFilters["readiness"],
    outreachStage: params.stage as LeadFilters["outreachStage"],
    approvalBucket: params.approval as LeadFilters["approvalBucket"],
    recentlySubmitted: params.recent as LeadFilters["recentlySubmitted"],
  };

  const filtered = filterLeads(leads, filters);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Opportunities"
        title="Opportunity Queue"
        description={`${filtered.length} of ${leads.length} opportunities, ranked by commercial potential.`}
      />

      {leads.length === 0 ? (
        <div className="panel p-10 text-center">
          <p className="text-sm font-medium text-foreground">No opportunities on record</p>
          <p className="mt-1 text-xs text-foreground-faint">
            The PermitSignal API returned zero leads. Run the pipeline against a government packet to populate the queue.
          </p>
        </div>
      ) : (
        <>
          <OpportunityFilters applicationTypes={applicationTypes} />

          <LeadQueueTable
            leads={[...filtered].sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0))}
          />
        </>
      )}
    </div>
  );
}
