import Link from "next/link";
import { notFound } from "next/navigation";
import { getLeadByApplicationNumber } from "@/lib/leads";
import { CaseHeader } from "@/components/leads/detail/CaseHeader";
import { PropertyCard } from "@/components/leads/detail/PropertyCard";
import { ProjectCard } from "@/components/leads/detail/ProjectCard";
import { PartiesCard } from "@/components/leads/detail/PartiesCard";
import { FrictionCard } from "@/components/leads/detail/FrictionCard";
import { NextEventCard } from "@/components/leads/detail/NextEventCard";
import { ApprovalActionCard } from "@/components/leads/detail/ApprovalActionCard";
import { OpportunityCard } from "@/components/leads/detail/OpportunityCard";
import { FollowUpCard } from "@/components/leads/detail/FollowUpCard";
import { ContactIntelligenceCard } from "@/components/leads/detail/ContactIntelligenceCard";
import { OutreachCard } from "@/components/leads/detail/OutreachCard";
import { EvidenceView } from "@/components/leads/detail/EvidenceView";

export const dynamic = "force-dynamic";

export default async function PropertyDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ applicationNumber: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const { applicationNumber } = await params;
  const { tab } = await searchParams;
  const lead = await getLeadByApplicationNumber(applicationNumber);

  if (!lead) notFound();

  const activeTab = tab === "evidence" ? "evidence" : "profile";

  return (
    <div className="flex flex-col gap-6">
      <CaseHeader lead={lead} />

      <div className="flex gap-1 border-b border-border-subtle">
        <Link
          href={`/properties/${lead.application_number}`}
          className={`px-3 py-2 text-sm font-medium ${
            activeTab === "profile"
              ? "border-b-2 border-accent text-foreground"
              : "text-foreground-muted hover:text-foreground"
          }`}
        >
          Profile
        </Link>
        <Link
          href={`/properties/${lead.application_number}?tab=evidence`}
          className={`px-3 py-2 text-sm font-medium ${
            activeTab === "evidence"
              ? "border-b-2 border-accent text-foreground"
              : "text-foreground-muted hover:text-foreground"
          }`}
        >
          Evidence
        </Link>
      </div>

      {activeTab === "profile" ? (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_380px]">
          <div className="flex min-w-0 flex-col gap-5">
            <PropertyCard lead={lead} />
            <ProjectCard lead={lead} />
            <PartiesCard lead={lead} />
            <FrictionCard lead={lead} />
            <NextEventCard lead={lead} />
            <ApprovalActionCard lead={lead} />
          </div>
          <div className="flex min-w-0 flex-col gap-5">
            <OpportunityCard lead={lead} />
            <ContactIntelligenceCard lead={lead} />
            <OutreachCard lead={lead} />
            <FollowUpCard lead={lead} />
          </div>
        </div>
      ) : (
        <EvidenceView lead={lead} />
      )}
    </div>
  );
}
