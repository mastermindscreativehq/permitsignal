import type { Lead } from "@/lib/types";
import { getFrictionEvidence } from "@/lib/lead-helpers";
import { formatDate, severityVariant, titleCase } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { SectionCard } from "./SectionCard";
import { Field } from "./Field";

export function FrictionCard({ lead }: { lead: Lead }) {
  const evidence = getFrictionEvidence(lead);

  return (
    <SectionCard
      title="Friction"
      description="Historical signals that this application has faced resistance before."
    >
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Field label="Friction Score" value={lead.friction_score ?? 0} mono />
        <Field
          label="Signals"
          value={lead.friction_signals?.length ? lead.friction_signals.map(titleCase).join(", ") : null}
          fallback="No signals detected"
        />
      </div>

      {evidence.length > 0 ? (
        <div className="mt-4 flex flex-col gap-3">
          {evidence.map((event, index) => (
            <div key={index} className="rounded-lg border border-border-subtle bg-surface p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={severityVariant(event.severity)}>{titleCase(event.event_type)}</Badge>
                <span className="text-xs text-foreground-faint">{formatDate(event.event_date)}</span>
                {event.confidence != null && (
                  <span className="text-xs text-foreground-faint">
                    Confidence {(event.confidence * 100).toFixed(0)}%
                  </span>
                )}
              </div>
              {event.evidence && (
                <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-foreground-muted">
                  {event.evidence}
                </p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm text-foreground-faint">No historical friction evidence on record.</p>
      )}
    </SectionCard>
  );
}
