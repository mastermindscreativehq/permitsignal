import type { Lead } from "@/lib/types";
import { priorityVariant } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { SectionCard } from "./SectionCard";
import { Field } from "./Field";

export function OpportunityCard({ lead }: { lead: Lead }) {
  return (
    <SectionCard title="Opportunity" actions={<Badge variant={priorityVariant(lead.priority)}>{lead.priority ?? "UNSCORED"}</Badge>}>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Field label="Priority Score" value={lead.priority_score ?? 0} mono />
        <Field label="Actionable" value={lead.is_actionable ? "Yes" : "No"} />
      </div>
      <p className="mt-4 text-sm leading-relaxed text-foreground-muted">
        {lead.opportunity_reason ?? "No opportunity reasoning recorded."}
      </p>
    </SectionCard>
  );
}
