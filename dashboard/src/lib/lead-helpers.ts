// Pure helpers over already-fetched Lead data. Deliberately free of the
// "server-only" guard (unlike lib/leads.ts) so client components -- like
// the 3D intelligence graph, which highlights nodes from data already
// passed down as props -- can reuse the exact same logic used server-side
// instead of re-deriving it.

import type {
  DashboardStats,
  FrictionEvent,
  Lead,
  LeadFilters,
  Party,
  Priority,
  ProjectDateEntry,
} from "./types";

/**
 * Owner headline vs. owner contact person are distinct: the source record
 * may name a legal/commercial entity (owner_entity, e.g. an LLC or
 * partnership) separately from the individual who acts as owner contact
 * (owner_contact_name, often the same person as owner_name). The entity is
 * the primary, dominant identity when it exists and differs from the
 * contact person; the person is always surfaced as the contact line.
 * Never fabricates either -- both fall back to null, never a guess.
 */
export function getPrimaryOwnerDisplay(lead: Lead): {
  primary: string | null;
  contactName: string | null;
} {
  const primary = lead.owner_entity ?? lead.owner_name ?? null;
  const contactName =
    lead.owner_contact_name ?? (lead.owner_name && lead.owner_name !== primary ? lead.owner_name : null);
  return { primary, contactName };
}

/**
 * The primary commercially relevant party: the Property Owner when the
 * source document names one, otherwise the Applicant of Record/Agent, then
 * the Company on record. Never fabricates an owner -- when no owner is on
 * record, this is simply the next real identified party, clearly labeled
 * as such by getPrimaryPartyRole().
 */
export function getPrimaryPartyName(lead: Lead): string {
  return getPrimaryOwnerDisplay(lead).primary ?? lead.applicant_name ?? lead.company_name ?? "Unknown";
}

/**
 * Which role getPrimaryPartyName() actually resolved to. A missing owner is
 * not "this lead has no party" -- it's "the next real party is the
 * applicant/company" -- so the UI should label the headline with the role
 * that's actually backing it, not a blanket "Owner" (see CLAUDE.md section
 * 7/9 -- never call everything "owner", never present absence as failure).
 */
export function getPrimaryPartyRole(lead: Lead): "Owner" | "Applicant" | "Company" | "Unknown" {
  if (isOwnerKnown(lead)) return "Owner";
  if (lead.applicant_name) return "Applicant";
  if (lead.company_name) return "Company";
  return "Unknown";
}

export function isOwnerKnown(lead: Lead): boolean {
  return Boolean(lead.owner_name ?? lead.owner_entity);
}

export function getParties(lead: Lead): Party[] {
  return Array.isArray(lead.parties) ? lead.parties : [];
}

/**
 * Splits getParties() out by role -- Engineer and Architect get their own
 * slot in the Parties roster (see PartiesCard), everyone else (surveyors,
 * attorneys, etc.) is grouped as "Other Parties." Matched by substring on
 * party_role since the source documents don't use a fixed enum.
 */
export function getPartiesByRole(lead: Lead): { engineer: Party | null; architect: Party | null; others: Party[] } {
  const parties = getParties(lead);
  const engineer = parties.find((p) => (p.party_role ?? "").toLowerCase().includes("engineer")) ?? null;
  const architect = parties.find((p) => (p.party_role ?? "").toLowerCase().includes("architect")) ?? null;
  const others = parties.filter((p) => p !== engineer && p !== architect);
  return { engineer, architect, others };
}

export function isContactable(lead: Lead): boolean {
  return lead.is_contactable === true || lead.lead_status === "CONTACTABLE";
}

export function needsContactDiscovery(lead: Lead): boolean {
  return (
    !isContactable(lead) &&
    (lead.lead_status === "NO_CONTACT" ||
      lead.lead_status === "NOT_RUN" ||
      lead.lead_status === "FAILED" ||
      !lead.lead_status)
  );
}

export function hasUpcomingEvent(lead: Lead): boolean {
  return Boolean(lead.has_future_opportunity && lead.next_project_date);
}

export function hasFriction(lead: Lead): boolean {
  return (lead.friction_score ?? 0) > 0;
}

// Phase 6 commercial_readiness buckets -- see backend/app/services/
// commercial_lead_intelligence.py for the vocabulary these read.
export function isReadyForOutreach(lead: Lead): boolean {
  return lead.commercial_readiness === "READY_FOR_OUTREACH";
}

export function needsContactEnrichment(lead: Lead): boolean {
  return lead.commercial_readiness === "NEEDS_CONTACT_ENRICHMENT";
}

export function needsMoreEvidence(lead: Lead): boolean {
  return lead.commercial_readiness === "NEEDS_MORE_PROJECT_EVIDENCE";
}

// Phase 8 outreach_status buckets -- see backend/app/services/
// outreach_intelligence.py's OUTREACH_STATUS_* vocabulary/rank order.
const CONTACTED_OUTREACH_STATUSES = new Set(["CONTACTED", "REPLIED", "ENGAGED"]);

export function isContacted(lead: Lead): boolean {
  return CONTACTED_OUTREACH_STATUSES.has(lead.outreach_status ?? "");
}

export function isOpportunityStage(lead: Lead): boolean {
  return lead.outreach_status === "OPPORTUNITY";
}

// approval_status buckets -- see backend/app/services/
// approval_action_intelligence.py's SIGNAL_PRIORITY/STATUS vocabulary.
// "Pending" is awaiting a scheduled government decision; "denied/delayed"
// is a negative or stalled outcome already on record.
const PENDING_APPROVAL_STATUSES = new Set(["scheduled", "pending", "under_review"]);
const DENIED_OR_DELAYED_STATUSES = new Set([
  "denied",
  "withdrawn",
  "recommended_denial",
  "tabled",
  "continued",
]);

export function isPendingApproval(lead: Lead): boolean {
  return PENDING_APPROVAL_STATUSES.has((lead.approval_status ?? "").toLowerCase());
}

export function isDeniedOrDelayed(lead: Lead): boolean {
  return DENIED_OR_DELAYED_STATUSES.has((lead.approval_status ?? "").toLowerCase());
}

/**
 * "Recently submitted" reads created_at -- the record's own creation
 * timestamp, the only submission-adjacent evidence the pipeline persists
 * (see docs/DATA_MODEL.md). Not a fabricated field; just a plain recency
 * window over an existing one.
 */
export function isRecentlySubmitted(lead: Lead, withinDays = 30): boolean {
  if (!lead.created_at) return false;
  const created = new Date(lead.created_at).getTime();
  if (Number.isNaN(created)) return false;
  return Date.now() - created <= withinDays * 24 * 60 * 60 * 1000;
}

/**
 * Friction evidence lives in the raw "events" field for this pipeline (the
 * promoted friction_events field is currently always []) -- fall back to
 * the promoted field first in case a future pipeline version populates it
 * directly, per docs/DATA_MODEL.md section 6.
 */
export function getFrictionEvidence(lead: Lead): FrictionEvent[] {
  if (lead.friction_events?.length) return lead.friction_events;
  return Array.isArray(lead.events) ? lead.events : [];
}

export function getFutureProjectDates(lead: Lead): ProjectDateEntry[] {
  return Array.isArray(lead.future_project_dates) ? lead.future_project_dates : [];
}

export function getHistoricalProjectDates(lead: Lead): ProjectDateEntry[] {
  return Array.isArray(lead.historical_project_dates) ? lead.historical_project_dates : [];
}

export function getContactSearchQueries(lead: Lead): string[] {
  return Array.isArray(lead.search_queries) ? lead.search_queries : [];
}

export function computeDashboardStats(leads: Lead[]): DashboardStats {
  const priorities: Priority[] = ["HIGH", "MEDIUM", "LOW"];
  const priorityDistribution = priorities.map((priority) => ({
    priority,
    count: leads.filter((lead) => lead.priority === priority).length,
  }));

  return {
    totalLeads: leads.length,
    highPriority: leads.filter((lead) => lead.priority === "HIGH").length,
    readyForOutreach: leads.filter(isReadyForOutreach).length,
    needsContactEnrichment: leads.filter(needsContactEnrichment).length,
    ownersIdentified: leads.filter(isOwnerKnown).length,
    contactable: leads.filter(isContactable).length,
    needingDiscovery: leads.filter(needsContactDiscovery).length,
    upcomingEvents: leads.filter(hasUpcomingEvent).length,
    priorityDistribution,
  };
}

export function getApplicationTypes(leads: Lead[]): string[] {
  const types = new Set<string>();
  for (const lead of leads) {
    if (lead.application_type) types.add(lead.application_type);
  }
  return Array.from(types).sort();
}

export function filterLeads(leads: Lead[], filters: LeadFilters): Lead[] {
  return leads.filter((lead) => {
    if (filters.priority && lead.priority !== filters.priority) return false;
    if (filters.leadStatus && lead.lead_status !== filters.leadStatus) return false;
    if (
      filters.applicationType &&
      lead.application_type !== filters.applicationType
    )
      return false;
    if (filters.contactability === "contactable" && !isContactable(lead))
      return false;
    if (
      filters.contactability === "needs_discovery" &&
      !needsContactDiscovery(lead)
    )
      return false;
    if (filters.upcomingEvent === "yes" && !hasUpcomingEvent(lead)) return false;
    if (filters.upcomingEvent === "no" && hasUpcomingEvent(lead)) return false;
    if (filters.friction === "yes" && !hasFriction(lead)) return false;
    if (filters.friction === "no" && hasFriction(lead)) return false;
    if (filters.readiness && lead.commercial_readiness !== filters.readiness) return false;
    if (filters.outreachStage === "contacted" && !isContacted(lead)) return false;
    if (filters.outreachStage === "opportunity" && !isOpportunityStage(lead)) return false;
    if (filters.approvalBucket === "pending" && !isPendingApproval(lead)) return false;
    if (filters.approvalBucket === "denied_delayed" && !isDeniedOrDelayed(lead)) return false;
    if (filters.recentlySubmitted === "yes" && !isRecentlySubmitted(lead)) return false;
    return true;
  });
}
