"use client";

import { useRouter, useSearchParams } from "next/navigation";
import type { LeadStatus, Priority } from "@/lib/types";

const PRIORITIES: Priority[] = ["HIGH", "MEDIUM", "LOW"];
const LEAD_STATUSES: LeadStatus[] = ["CONTACTABLE", "QUALIFIED", "NO_CONTACT", "NOT_RUN", "FAILED"];

function Select({
  label,
  paramKey,
  options,
  value,
  onChange,
}: {
  label: string;
  paramKey: string;
  options: { value: string; label: string }[];
  value: string;
  onChange: (paramKey: string, value: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[11px] font-semibold uppercase tracking-wide text-foreground-faint">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(paramKey, event.target.value)}
        className="rounded-md border border-border-subtle bg-background-elevated px-3 py-2 text-sm text-foreground outline-none transition-colors focus:border-accent"
      >
        <option value="">All</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function LeadFilterBar({ applicationTypes }: { applicationTypes: string[] }) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const update = (key: string, value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value) params.set(key, value);
    else params.delete(key);
    router.push(`/properties${params.toString() ? `?${params.toString()}` : ""}`);
  };

  const hasFilters = [
    "priority",
    "status",
    "type",
    "contactability",
    "event",
    "friction",
    "readiness",
    "stage",
    "approval",
    "recent",
  ].some((key) => searchParams.get(key));

  return (
    <div className="panel flex flex-wrap items-end gap-4 p-4">
      <Select
        label="Priority"
        paramKey="priority"
        value={searchParams.get("priority") ?? ""}
        onChange={update}
        options={PRIORITIES.map((p) => ({ value: p, label: p }))}
      />
      <Select
        label="Lead Status"
        paramKey="status"
        value={searchParams.get("status") ?? ""}
        onChange={update}
        options={LEAD_STATUSES.map((s) => ({ value: s, label: s.replaceAll("_", " ") }))}
      />
      <Select
        label="Application Type"
        paramKey="type"
        value={searchParams.get("type") ?? ""}
        onChange={update}
        options={applicationTypes.map((t) => ({ value: t, label: t }))}
      />
      <Select
        label="Contactability"
        paramKey="contactability"
        value={searchParams.get("contactability") ?? ""}
        onChange={update}
        options={[
          { value: "contactable", label: "Contactable" },
          { value: "needs_discovery", label: "Needs Discovery" },
        ]}
      />
      <Select
        label="Friction"
        paramKey="friction"
        value={searchParams.get("friction") ?? ""}
        onChange={update}
        options={[
          { value: "yes", label: "Has Friction" },
          { value: "no", label: "No Friction" },
        ]}
      />
      <Select
        label="Upcoming Event"
        paramKey="event"
        value={searchParams.get("event") ?? ""}
        onChange={update}
        options={[
          { value: "yes", label: "Has Event" },
          { value: "no", label: "No Event" },
        ]}
      />
      <Select
        label="Readiness"
        paramKey="readiness"
        value={searchParams.get("readiness") ?? ""}
        onChange={update}
        options={[
          { value: "READY_FOR_OUTREACH", label: "Ready for Outreach" },
          { value: "NEEDS_CONTACT_ENRICHMENT", label: "Needs Enrichment" },
          { value: "NEEDS_MORE_PROJECT_EVIDENCE", label: "Needs Evidence" },
          { value: "NOT_READY", label: "Not Ready" },
        ]}
      />
      <Select
        label="Outreach"
        paramKey="stage"
        value={searchParams.get("stage") ?? ""}
        onChange={update}
        options={[
          { value: "contacted", label: "Contacted" },
          { value: "opportunity", label: "Opportunity" },
        ]}
      />
      <Select
        label="Approval"
        paramKey="approval"
        value={searchParams.get("approval") ?? ""}
        onChange={update}
        options={[
          { value: "pending", label: "Pending" },
          { value: "denied_delayed", label: "Denied / Delayed" },
        ]}
      />
      <Select
        label="Submitted"
        paramKey="recent"
        value={searchParams.get("recent") ?? ""}
        onChange={update}
        options={[{ value: "yes", label: "Recently Submitted" }]}
      />
      {hasFilters && (
        <button
          onClick={() => router.push("/properties")}
          className="rounded-md border border-border-subtle px-3 py-2 text-xs font-medium text-foreground-muted transition-colors hover:border-border-strong hover:text-foreground"
        >
          Clear filters
        </button>
      )}
    </div>
  );
}
