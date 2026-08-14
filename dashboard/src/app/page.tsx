import Link from "next/link";
import { getLeads } from "@/lib/leads";
import { computeDashboardStats } from "@/lib/lead-helpers";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatCard } from "@/components/ui/StatCard";
import { PriorityDistribution } from "@/components/leads/PriorityDistribution";
import { HighPriorityOpportunityCard } from "@/components/leads/HighPriorityOpportunityCard";
import { AttentionQueue } from "@/components/leads/AttentionQueue";

export const dynamic = "force-dynamic";
// The PermitSignal API's /leads call has been observed taking ~11s in
// production; Vercel's serverless default (10s) would otherwise cut this
// off before the fetch in getLeads() resolves.
export const maxDuration = 30;

export default async function OverviewPage() {
  const leads = await getLeads();
  const stats = computeDashboardStats(leads);

  const highPriorityQueue = leads
    .filter((lead) => lead.priority === "HIGH")
    .sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0));

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        eyebrow="Overview"
        title="Property Intelligence"
        description="Government planning packets, turned into owner-verified, evidence-backed property opportunities."
        actions={
          <Link
            href="/properties"
            className="rounded-md border border-border-subtle bg-surface px-3.5 py-2 text-sm font-medium text-foreground transition-colors hover:border-accent hover:text-accent-strong"
          >
            View Property Intelligence →
          </Link>
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Total Properties" value={stats.totalLeads} hint="Canonical opportunities" />
        <StatCard label="High Priority" value={stats.highPriority} hint="Score-ranked HIGH leads" accent="high" />
        <StatCard
          label="Owners Identified"
          value={stats.ownersIdentified}
          hint="Owner distinct from applicant on record"
          accent="positive"
        />
        <StatCard
          label="Owners Not Found"
          value={stats.ownersNotFound}
          hint="Ownership discovery incomplete"
          accent="caution"
        />
        <StatCard label="Contactable" value={stats.contactable} hint="Verified public contact found" accent="positive" />
        <StatCard label="Upcoming Events" value={stats.upcomingEvents} hint="Future hearings / meetings" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_280px]">
        <div className="panel p-5">
          <div className="mb-4">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-foreground-muted">
              Attention Queue
            </p>
            <p className="mt-1 text-xs text-foreground-faint">
              Top properties by opportunity score -- owner status, next event, friction, and contactability at a glance.
            </p>
          </div>
          <AttentionQueue leads={leads} />
        </div>
        <PriorityDistribution stats={stats} />
      </div>

      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">High-Priority Opportunities</h2>
          <Link href="/properties?priority=HIGH" className="text-sm text-accent-strong hover:underline">
            View all HIGH properties →
          </Link>
        </div>
        <div className="flex flex-col gap-3">
          {highPriorityQueue.length === 0 ? (
            <div className="panel p-8 text-center text-sm text-foreground-faint">No HIGH priority properties right now.</div>
          ) : (
            highPriorityQueue.map((lead) => (
              <HighPriorityOpportunityCard key={lead.application_number} lead={lead} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
