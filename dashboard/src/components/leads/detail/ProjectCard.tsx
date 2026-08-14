import type { Lead } from "@/lib/types";
import { SectionCard } from "./SectionCard";
import { Field } from "./Field";

export function ProjectCard({ lead }: { lead: Lead }) {
  return (
    <SectionCard title="Project" description="The application itself -- see the Property card for the underlying land.">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Field label="Application Number" value={lead.application_number} mono />
        <Field label="Application Type" value={lead.application_type} />
        <Field label="Status" value={Array.isArray(lead.status) && lead.status.length ? lead.status.join(", ") : null} />
      </div>
      {lead.description && (
        <p className="mt-4 rounded-lg border border-border-subtle bg-surface p-3 text-sm leading-relaxed text-foreground-muted">
          {lead.description}
        </p>
      )}
    </SectionCard>
  );
}
