import type { LeadStatus, Priority } from "./types";

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatDaysUntil(days: number | null | undefined): string {
  if (days === null || days === undefined) return "—";
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days < 0) return `${Math.abs(days)}d ago`;
  return `In ${days}d`;
}

export function titleCase(value: string | null | undefined): string {
  if (!value) return "—";
  return value
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

type Variant =
  | "priority-high"
  | "priority-medium"
  | "priority-low"
  | "status-positive"
  | "status-caution"
  | "status-negative"
  | "status-neutral";

export function priorityVariant(priority: Priority | null | undefined): Variant {
  switch (priority) {
    case "HIGH":
      return "priority-high";
    case "MEDIUM":
      return "priority-medium";
    default:
      return "priority-low";
  }
}

export function leadStatusVariant(status: LeadStatus | null | undefined): Variant {
  switch (status) {
    case "CONTACTABLE":
    case "QUALIFIED":
      return "status-positive";
    case "FAILED":
      return "status-negative";
    case "NOT_RUN":
      return "status-caution";
    case "NO_CONTACT":
    default:
      return "status-neutral";
  }
}

export function urgencyVariant(urgency: string | null | undefined): Variant {
  switch ((urgency ?? "").toUpperCase()) {
    case "IMMEDIATE":
    case "SOON":
      return "priority-high";
    case "UPCOMING":
      return "priority-medium";
    default:
      return "priority-low";
  }
}

export function severityVariant(severity: string | null | undefined): Variant {
  switch ((severity ?? "").toLowerCase()) {
    case "critical":
      return "status-negative";
    case "high":
      return "priority-high";
    case "medium":
      return "status-caution";
    default:
      return "status-neutral";
  }
}

export function approvalStatusVariant(status: string | null | undefined): Variant {
  switch ((status ?? "").toLowerCase()) {
    case "denied":
      return "status-negative";
    case "withdrawn":
    case "recommended_denial":
    case "tabled":
      return "status-caution";
    case "continued":
    case "under_review":
    case "pending":
      return "status-caution";
    case "scheduled":
      return "status-positive";
    default:
      return "status-neutral";
  }
}

export function commercialReadinessVariant(readiness: string | null | undefined): Variant {
  switch (readiness) {
    case "READY_FOR_OUTREACH":
      return "status-positive";
    case "NEEDS_CONTACT_ENRICHMENT":
    case "NEEDS_MORE_PROJECT_EVIDENCE":
      return "status-caution";
    default:
      return "status-neutral";
  }
}

export function outreachStatusVariant(status: string | null | undefined): Variant {
  switch (status) {
    case "WON":
    case "OPPORTUNITY":
      return "status-positive";
    case "READY_FOR_OUTREACH":
    case "CONTACTED":
    case "REPLIED":
    case "ENGAGED":
      return "status-caution";
    case "LOST":
      return "status-negative";
    default:
      return "status-neutral";
  }
}

export function approvalBasisVariant(basis: string | null | undefined): Variant {
  switch (basis) {
    case "confirmed_requirement":
      return "status-positive";
    case "evidence_backed_recommendation":
      return "status-caution";
    case "inferred_next_step":
      return "status-neutral";
    default:
      return "status-neutral";
  }
}
