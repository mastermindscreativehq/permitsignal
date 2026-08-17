import type { Lead } from "@/lib/types";
import { formatDate, formatDaysUntil, titleCase } from "@/lib/format";
import { hasUpcomingEvent } from "@/lib/lead-helpers";
import { SectionCard } from "./SectionCard";
import { Field } from "./Field";
import { PartiesCard } from "./PartiesCard";
import { FrictionCard } from "./FrictionCard";
import { NextEventCard } from "./NextEventCard";
import { ApprovalActionCard } from "./ApprovalActionCard";
import { EvidenceSection } from "./EvidenceSection";

/**
 * The main left-column intelligence display on the detail page.
 * Organized by hierarchy: Why → Who → What happened → What's next → Evidence.
 */
export function ProfileIntelligence({ lead }: { lead: Lead }) {
  return (
    <div className="flex min-w-0 flex-col gap-5">
      {lead.opportunity_reason && (
        <SectionCard title="Why This Matters">
          <p className="text-sm leading-relaxed text-foreground">{lead.opportunity_reason}</p>
        </SectionCard>
      )}

      <PartiesCard lead={lead} />

      <FrictionCard lead={lead} />

      <NextEventCard lead={lead} />

      <ApprovalActionCard lead={lead} />

      <EvidenceSection lead={lead} />
    </div>
  );
}
