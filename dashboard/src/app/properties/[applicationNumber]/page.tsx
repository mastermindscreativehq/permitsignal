import { notFound } from "next/navigation";
import { getLeadByApplicationNumber } from "@/lib/leads";
import { CaseHeader } from "@/components/leads/detail/CaseHeader";
import { CaseInformationCard } from "@/components/leads/detail/CaseInformationCard";
import { CaseReportHistory } from "@/components/leads/detail/CaseReportHistory";
import { DeepIntelligenceCard } from "@/components/leads/detail/DeepIntelligenceCard";
import { PredictionsCard } from "@/components/leads/detail/PredictionsCard";
import { SupplementaryIntelligence } from "@/components/leads/detail/SupplementaryIntelligence";
import { InvestigationProfile } from "@/components/leads/detail/InvestigationProfile";
import { MatrixCenter } from "@/components/leads/detail/MatrixCenter";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

export default async function PropertyDetailPage({
  params,
}: {
  params: Promise<{ applicationNumber: string }>;
}) {
  const { applicationNumber } = await params;
  const lead = await getLeadByApplicationNumber(applicationNumber);

  if (!lead) notFound();

  return (
    <div className="flex flex-col gap-6">
      <CaseHeader lead={lead} />
      <CaseInformationCard lead={lead} />
      <div id="case-report-history">
        <CaseReportHistory applicationNumber={applicationNumber} />
      </div>
      <InvestigationProfile lead={lead} />
      <DeepIntelligenceCard lead={lead} />
      <PredictionsCard lead={lead} />
      <SupplementaryIntelligence lead={lead} />
      <MatrixCenter lead={lead} />
    </div>
  );
}
