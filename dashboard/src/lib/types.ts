// Canonical PermitSignal lead shape.
//
// This mirrors the flat canonical lead/opportunity dict produced by
// backend/app/services/pipeline_orchestrator.py and returned verbatim by
// the Phase 4 API (backend/app/main.py: GET /leads, GET /leads/{application_number}),
// whether that record was sourced from Supabase's "record" JSONB column
// (lead_repository.fetch_lead/fetch_leads) or the pipeline's JSON artifact
// fallback (case_report_generator.load_lead_queue) -- both return this same
// flat shape, so the dashboard never needs to special-case its source.

export type Priority = "HIGH" | "MEDIUM" | "LOW";

export type LeadStatus =
  | "CONTACTABLE"
  | "QUALIFIED"
  | "NO_CONTACT"
  | "NOT_RUN"
  | "FAILED";

// Phase 3 approval-action intelligence. approval_basis distinguishes how
// strong the evidence behind approval_action is -- see
// backend/app/services/approval_action_intelligence.py's module docstring.
export type ApprovalBasis =
  | "confirmed_requirement"
  | "evidence_backed_recommendation"
  | "inferred_next_step"
  | "unknown";

export interface FrictionEvent {
  event_type: string;
  event_date: string | null;
  severity: string | null;
  confidence: number | null;
  relevance: number | null;
  evidence: string | null;
  matched_text?: string | null;
  weight?: number | null;
  source_page?: number | null;
}

export interface ProjectDateEntry {
  label: string;
  value: string;
  time: string | null;
  date_type: string;
  is_future: boolean;
  confidence: number | null;
  context?: string | null;
}

export interface Party {
  party_name: string | null;
  party_role: string | null;
  party_company: string | null;
  party_contact_email: string | null;
  party_contact_phone: string | null;
  party_source: string | null;
  party_confidence: string | null;
}

export interface Lead {
  application_number: string;
  applicant_name: string | null;
  normalized_applicant_name: string | null;
  company_name: string | null;
  company_website: string | null;
  company_domain: string | null;

  application_type: string | null;
  project_address: string | null;
  neighborhood: string | null;
  status: unknown;
  description: string | null;
  project_description?: string | null;

  // Property (populated only when the source document labels them)
  parcel_number: string | null;
  acreage: string | null;
  zoning: string | null;

  // Property Owner / Principal -- the primary commercially relevant party,
  // distinct from the Applicant of Record/Agent below. Populated only when
  // the source document explicitly labels ownership; never inferred from
  // the applicant. See CLAUDE.md section 6.
  owner_name: string | null;
  owner_entity: string | null;
  owner_type: string | null;
  owner_contact_name: string | null;
  owner_contact_email: string | null;
  owner_contact_phone: string | null;
  owner_website: string | null;
  owner_source: string | null;
  owner_confidence: string | null;

  // Applicant of Record / Agent -- the entity submitting on the owner's
  // behalf (e.g. a design firm), distinct from applicant_name/email/phone
  // above (the individual the government record names as "requesting" the
  // application).
  applicant_entity: string | null;
  applicant_contact_name: string | null;
  applicant_contact_email: string | null;
  applicant_contact_phone: string | null;
  applicant_source: string | null;
  applicant_confidence: string | null;

  // Engineer / Architect / other licensed professionals.
  parties: Party[];

  friction_score: number | null;
  friction_signals: string[];
  friction_events: FrictionEvent[];
  // Raw friction-analyzer evidence. friction_events above is frequently []
  // for this pipeline version -- the actual evidence lives here.
  events?: FrictionEvent[];

  next_project_date: string | null;
  next_project_event: string | null;
  next_project_time: string | null;
  has_future_opportunity: boolean;
  days_until_event: number | null;
  urgency: string | null;
  future_project_dates?: ProjectDateEntry[];
  historical_project_dates?: ProjectDateEntry[];

  priority: Priority | null;
  priority_score: number | null;
  is_actionable: boolean;
  opportunity_reason: string | null;

  // Phase 3 -- Approval-Action Intelligence. Every field is either real
  // evidence-backed content or explicit null/"unknown" -- never fabricated.
  approval_status: string | null;
  approval_action: string | null;
  approval_action_type: string | null;
  approval_confidence: string | null;
  approval_basis: ApprovalBasis | null;
  approval_relevant_date: string | null;
  approval_source: string | null;
  approval_source_type: string | null;
  approval_evidence: string | null;
  approval_reason: string | null;

  contact_name: string | null;
  contact_role: string | null;
  applicant_email: string | null;
  applicant_phone: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  linkedin_url: string | null;

  email_source: string | null;
  phone_source: string | null;
  company_source: string | null;
  contact_source: string | null;
  email_confidence: string | null;
  phone_confidence: string | null;
  contact_confidence: string | null;
  contact_is_public: boolean | null;
  contact_is_verified: boolean | null;

  identity_status: string | null;
  identity_confidence?: string | null;
  enrichment_status: string | null;
  enrichment_method: string | null;

  lead_status: LeadStatus | null;
  is_contactable: boolean;

  // Phase 6 -- Commercial Lead Intelligence. A deterministic re-labeling of
  // lead_status/is_contactable (+ approval_action) for a commercial
  // audience -- never a second scoring model. See
  // backend/app/services/commercial_lead_intelligence.py.
  contactability_level: string | null;
  commercial_readiness: string | null;
  recommended_commercial_action: string | null;
  commercial_action_reason: string | null;

  // Phase 8 -- Outreach & Monetization Intelligence. outreach_status is the
  // controlled lead lifecycle (also the commercial/revenue status --
  // READY_FOR_OUTREACH is the point a lead becomes sellable; OPPORTUNITY/
  // WON/LOST track the resulting deal). NEW/QUALIFIED/READY_FOR_OUTREACH
  // are recomputed from commercial_readiness every pipeline run; CONTACTED
  // and beyond only change via a controlled outreach event (POST /leads/
  // {application_number}/outreach/events) -- never reset by a pipeline
  // rerun. outreach_contact_type never duplicates the underlying contact
  // fields above -- it only records WHICH party was selected as the
  // outreach target. See backend/app/services/outreach_intelligence.py.
  outreach_status: string | null;
  outreach_qualification_status: string | null;
  outreach_channel: string | null;
  outreach_contact_type: string | null;
  outreach_contact_reason: string | null;
  outreach_message_subject: string | null;
  outreach_message_body: string | null;
  follow_up_required: boolean;
  follow_up_reason: string | null;
  last_outreach_at: string | null;
  outreach_events: {
    event: string;
    note: string | null;
    occurred_at: string | null;
    previous_status: string | null;
    resulting_status: string | null;
  }[];

  // Phase 9 -- Economic Intelligence. estimated_value_* is the project's
  // own economic scale (an ESTIMATE unless source_type is
  // disclosed_document_value); public_spend_* is a SEPARATE figure for
  // whether government money is actually expected to be spent -- a
  // private developer's project can carry a large estimated value and a
  // public_spend of exactly 0. See backend/app/services/
  // economic_intelligence.py.
  project_scale_units: number | null;
  project_scale_type: string | null;
  project_scale_basis: string | null;

  estimated_value_low: number | null;
  estimated_value_high: number | null;
  estimated_value_mid: number | null;
  estimated_value_currency: string | null;
  estimated_value_confidence: string | null;
  estimated_value_source_type: string | null;
  estimated_value_basis: string | null;

  public_funding_status: string | null;
  public_funding_confidence: string | null;
  public_funding_basis: string | null;

  public_spend_low: number | null;
  public_spend_high: number | null;
  public_spend_mid: number | null;
  public_spend_confidence: string | null;

  source: string | null;
  source_url: string | null;
  municipality: string | null;
  state: string | null;

  staff_contact_name: string | null;
  staff_contact_email: string | null;
  staff_contact_phone: string | null;

  search_queries?: string[];
  search_results?: unknown[];
  email_candidates?: unknown[];
  phone_candidates?: unknown[];

  builder_version?: string | null;
  created_at: string | null;

  // Not yet populated by any pipeline stage -- reserved for the n8n
  // automation layer described in CLAUDE.md section 10 (scheduled
  // collection/enrichment/follow-up jobs). No fields exist for these yet,
  // so no UI should render a value for them; enrichment_status and
  // created_at above are the current, real stand-ins for "sync state."
  // last_enriched_at, next_enrichment_at, source_status,
  // owner_discovery_status, follow_up_status

  [key: string]: unknown;
}

export interface DashboardStats {
  totalLeads: number;
  highPriority: number;
  readyForOutreach: number;
  needsContactEnrichment: number;
  ownersIdentified: number;
  contactable: number;
  needingDiscovery: number;
  upcomingEvents: number;
  // Phase 9 -- sums of estimated_value_mid / public_spend_mid across leads
  // that carry evidence for each (never fabricated for leads with none).
  totalEstimatedValue: number;
  totalPublicSpend: number;
  priorityDistribution: { priority: Priority; count: number }[];
}

export type CommercialReadiness =
  | "READY_FOR_OUTREACH"
  | "NEEDS_CONTACT_ENRICHMENT"
  | "NEEDS_MORE_PROJECT_EVIDENCE"
  | "NOT_READY";

export interface LeadFilters {
  priority?: Priority;
  leadStatus?: LeadStatus;
  applicationType?: string;
  contactability?: "contactable" | "needs_discovery";
  upcomingEvent?: "yes" | "no";
  friction?: "yes" | "no";
  // Phase 6 commercial_readiness -- "who should I contact and why" queue filters.
  readiness?: CommercialReadiness;
  // Phase 8 outreach_status buckets -- "already contacted" / "became a real deal".
  outreachStage?: "contacted" | "opportunity";
  // approval_status buckets -- awaiting a government decision vs. a negative/stalled one.
  approvalBucket?: "pending" | "denied_delayed";
  recentlySubmitted?: "yes";
}
