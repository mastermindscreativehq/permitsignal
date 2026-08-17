"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

type Tab = { label: string; params: Record<string, string> };

const PRIMARY_TABS: Tab[] = [
  { label: "All", params: {} },
  { label: "High Priority", params: { priority: "HIGH" } },
  { label: "Ready for Outreach", params: { readiness: "READY_FOR_OUTREACH" } },
  { label: "Needs Contact", params: { readiness: "NEEDS_CONTACT_ENRICHMENT" } },
];

function getActiveTab(searchParams: URLSearchParams): number {
  const p = searchParams.toString();
  if (!p) return 0;
  if (searchParams.get("priority") === "HIGH" && !searchParams.get("readiness")) return 1;
  if (searchParams.get("readiness") === "READY_FOR_OUTREACH") return 2;
  if (searchParams.get("readiness") === "NEEDS_CONTACT_ENRICHMENT") return 3;
  return -1;
}

export function OpportunityFilters({ applicationTypes }: { applicationTypes: string[] }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [showAdvanced, setShowAdvanced] = useState(false);

  const activeTab = getActiveTab(searchParams);

  const setTab = (tab: Tab) => {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(tab.params)) {
      params.set(k, v);
    }
    router.push(`/properties${params.toString() ? `?${params.toString()}` : ""}`);
  };

  const setFilter = (key: string, value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value) params.set(key, value);
    else params.delete(key);
    router.push(`/properties${params.toString() ? `?${params.toString()}` : ""}`);
  };

  const hasAdvancedFilters = ["status", "type", "contactability", "event", "friction", "stage", "approval", "recent"].some(
    (key) => searchParams.get(key)
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {PRIMARY_TABS.map((tab, i) => (
          <button
            key={tab.label}
            onClick={() => setTab(tab)}
            className={`rounded-md px-3.5 py-2 text-sm font-medium transition-colors ${
              activeTab === i
                ? "bg-surface-strong text-foreground border border-border-strong"
                : "border border-transparent text-foreground-muted hover:bg-surface hover:text-foreground"
            }`}
          >
            {tab.label}
          </button>
        ))}
        <button
          onClick={() => setShowAdvanced(!showAdvanced)}
          className={`rounded-md px-3.5 py-2 text-sm font-medium transition-colors ${
            showAdvanced || hasAdvancedFilters
              ? "bg-surface-strong text-foreground border border-border-strong"
              : "border border-transparent text-foreground-muted hover:bg-surface hover:text-foreground"
          }`}
        >
          Advanced {hasAdvancedFilters ? "·" : ""} {showAdvanced ? "▾" : "▸"}
        </button>
      </div>

      {showAdvanced && (
        <div className="panel flex flex-wrap items-end gap-4 p-4">
          <SelectFilter
            label="Status"
            paramKey="status"
            value={searchParams.get("status") ?? ""}
            onChange={setFilter}
            options={[
              { value: "CONTACTABLE", label: "Contactable" },
              { value: "QUALIFIED", label: "Qualified" },
              { value: "NO_CONTACT", label: "No Contact" },
              { value: "NOT_RUN", label: "Not Run" },
              { value: "FAILED", label: "Failed" },
            ]}
          />
          <SelectFilter
            label="Type"
            paramKey="type"
            value={searchParams.get("type") ?? ""}
            onChange={setFilter}
            options={applicationTypes.map((t) => ({ value: t, label: t }))}
          />
          <SelectFilter
            label="Contactability"
            paramKey="contactability"
            value={searchParams.get("contactability") ?? ""}
            onChange={setFilter}
            options={[
              { value: "contactable", label: "Contactable" },
              { value: "needs_discovery", label: "Needs Discovery" },
            ]}
          />
          <SelectFilter
            label="Event"
            paramKey="event"
            value={searchParams.get("event") ?? ""}
            onChange={setFilter}
            options={[
              { value: "yes", label: "Has Event" },
              { value: "no", label: "No Event" },
            ]}
          />
          <SelectFilter
            label="Friction"
            paramKey="friction"
            value={searchParams.get("friction") ?? ""}
            onChange={setFilter}
            options={[
              { value: "yes", label: "Has Friction" },
              { value: "no", label: "No Friction" },
            ]}
          />
          <SelectFilter
            label="Outreach"
            paramKey="stage"
            value={searchParams.get("stage") ?? ""}
            onChange={setFilter}
            options={[
              { value: "contacted", label: "Contacted" },
              { value: "opportunity", label: "Opportunity" },
            ]}
          />
          <SelectFilter
            label="Approval"
            paramKey="approval"
            value={searchParams.get("approval") ?? ""}
            onChange={setFilter}
            options={[
              { value: "pending", label: "Pending" },
              { value: "denied_delayed", label: "Denied / Delayed" },
            ]}
          />
          <SelectFilter
            label="Submitted"
            paramKey="recent"
            value={searchParams.get("recent") ?? ""}
            onChange={setFilter}
            options={[{ value: "yes", label: "Recently" }]}
          />
          {hasAdvancedFilters && (
            <button
              onClick={() => {
                const params = new URLSearchParams();
                router.push("/properties");
              }}
              className="rounded-md border border-border-subtle px-3 py-2 text-xs font-medium text-foreground-muted transition-colors hover:border-border-strong hover:text-foreground"
            >
              Clear filters
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function SelectFilter({
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
