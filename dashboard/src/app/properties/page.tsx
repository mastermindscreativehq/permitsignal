import { getLeads } from "@/lib/leads";
import { filterLeads, getApplicationTypes } from "@/lib/lead-helpers";
import type { LeadFilters, LeadStatus, Priority } from "@/lib/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { LeadFilterBar } from "@/components/leads/LeadFilterBar";
import { LeadQueueTable } from "@/components/leads/LeadQueueTable";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  priority?: string;
  status?: string;
  type?: string;
  contactability?: string;
  event?: string;
  friction?: string;
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
  };

  const filtered = filterLeads(leads, filters);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Property Intelligence"
        title="Property Intelligence"
        description={`${filtered.length} of ${leads.length} properties shown, ranked by opportunity score. Owner, applicant, and government staff are tracked as distinct parties.`}
      />

      {leads.length === 0 ? (
        <div className="panel p-10 text-center">
          <p className="text-sm font-medium text-foreground">No leads on record yet</p>
          <p className="mt-1 text-xs text-foreground-faint">
            The PermitSignal API returned zero leads. Run the pipeline against a government packet to populate the
            queue.
          </p>
        </div>
      ) : (
        <>
          <LeadFilterBar applicationTypes={applicationTypes} />

          <LeadQueueTable
            leads={[...filtered].sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0))}
          />
        </>
      )}
    </div>
  );
}
