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
 * source document names one, otherwise the Applicant of Record/Agent.
 * Never fabricates an owner -- when no owner is on record, this is simply
 * the applicant, clearly labeled as such by isOwnerKnown().
 */
export function getPrimaryPartyName(lead: Lead): string {
  return getPrimaryOwnerDisplay(lead).primary ?? lead.applicant_name ?? "Unknown";
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
    ownersIdentified: leads.filter(isOwnerKnown).length,
    ownersNotFound: leads.filter((lead) => !isOwnerKnown(lead)).length,
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
    return true;
  });
}
