import Link from "next/link";
import { notFound } from "next/navigation";
import { getLeadByApplicationNumber } from "@/lib/leads";
import { CaseHeader } from "@/components/leads/detail/CaseHeader";
import { ProfileIntelligence } from "@/components/leads/detail/ProfileIntelligence";
import { ActionPanel } from "@/components/leads/detail/ActionPanel";

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
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_380px]">
        <ProfileIntelligence lead={lead} />
        <ActionPanel lead={lead} />
      </div>
    </div>
  );
}
