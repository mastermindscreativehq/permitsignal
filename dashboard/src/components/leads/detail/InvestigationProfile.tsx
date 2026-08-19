"use client";

import { useState, useCallback } from "react";
import type {
  Lead,
  InvestigationProfile,
  InvestigationStatus,
  InvestigationEvent,
  InvestigationEvidence,
  InvestigationSource,
} from "@/lib/types";
import {
  getInvestigation,
  investigateWeb,
  investigateWebsite,
  investigateDirectories,
  investigateLinkedin,
  investigatePublicRecords,
  investigateProject,
  investigateContact,
  investigateAll,
} from "@/lib/investigation-api";
import { SectionCard } from "./SectionCard";
import { Field, ContactField } from "./Field";
import { Badge } from "@/components/ui/Badge";
import { titleCase } from "@/lib/format";

const SOURCE_LABELS: Record<InvestigationSource, string> = {
  web: "Web Search",
  website: "Official Website",
  directories: "Business Directories",
  linkedin: "LinkedIn",
  public_records: "Public Records",
  project: "Project Relationships",
  contact: "Contact Discovery",
};

const SOURCE_ICONS: Record<InvestigationSource, string> = {
  web: "M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z",
  website: "M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5a17.92 17.92 0 01-8.716-2.247m0 0A8.966 8.966 0 013 12c0-1.264.26-2.467.727-3.57",
  directories: "M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 010 3.75H5.625a1.875 1.875 0 010-3.75z",
  linkedin: "M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z",
  public_records: "M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z",
  project: "M13.5 21v-7.5a.75.75 0 01.75-.75h3a.75.75 0 01.75.75V21m-4.5 0H2.36m11.14 0H18m0 0h3.64m-1.39 0V9.349m-16.5 11.65V9.35m0 0a3.001 3.001 0 003.75-.615A2.993 2.993 0 009.75 9.75c.896 0 1.7-.393 2.25-1.016a2.993 2.993 0 002.25 1.016c.896 0 1.7-.393 2.25-1.016A3.001 3.001 0 0021 9.349",
  contact: "M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75",
};

function statusVariant(s: InvestigationStatus): "status-positive" | "status-caution" | "status-negative" | "status-neutral" | "priority-high" {
  switch (s) {
    case "ENRICHED":
      return "status-positive";
    case "PARTIAL":
      return "status-caution";
    case "IN_PROGRESS":
      return "priority-high";
    case "NOT_FOUND":
      return "status-neutral";
    case "ERROR":
      return "status-negative";
    default:
      return "status-neutral";
  }
}

function SourceStatusDot({ status }: { status: InvestigationStatus }) {
  const color =
    status === "ENRICHED"
      ? "bg-status-positive"
      : status === "PARTIAL"
        ? "bg-status-caution"
        : status === "IN_PROGRESS"
          ? "bg-priority-high animate-pulse"
          : status === "ERROR"
            ? "bg-status-negative"
            : "bg-status-neutral/50";

  return <span className={`h-2 w-2 rounded-full ${color}`} />;
}

function InvestigationButton({
  label,
  icon,
  onClick,
  loading,
  status,
}: {
  label: string;
  icon: string;
  onClick: () => void;
  loading: boolean;
  status: InvestigationStatus;
}) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-all ${
        loading
          ? "cursor-wait border-priority-high/30 bg-priority-high-soft text-priority-high"
          : status === "ENRICHED"
            ? "border-status-positive/30 bg-status-positive-soft text-status-positive hover:border-status-positive/50"
            : "border-border-subtle bg-surface text-foreground-muted hover:border-border-strong hover:text-foreground"
      }`}
    >
      <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d={icon} />
      </svg>
      {loading ? "Running..." : label}
      <SourceStatusDot status={status} />
    </button>
  );
}

function EvidenceItem({ evidence }: { evidence: InvestigationEvidence }) {
  const [expanded, setExpanded] = useState(false);
  const fieldLabel = evidence.field === "linkedin_profile" ? "LinkedIn" : titleCase(evidence.field);

  return (
    <div className="rounded-lg border border-border-subtle bg-surface/60 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-foreground-faint">
              {fieldLabel}
            </span>
            {evidence.confidence && (
              <Badge variant={evidence.confidence === "HIGH" ? "status-positive" : evidence.confidence === "MEDIUM" ? "status-caution" : "status-neutral"}>
                {evidence.confidence}
              </Badge>
            )}
          </div>
          <p className="mt-1 font-mono text-xs break-all text-foreground">{evidence.value}</p>
          {evidence.source_type && (
            <p className="mt-0.5 text-[10px] text-foreground-faint">
              {titleCase(evidence.source_type.replace(/_/g, " "))}
              {evidence.source_domain ? ` · ${evidence.source_domain}` : ""}
            </p>
          )}
        </div>
        {evidence.source_url && (
          <a
            href={evidence.source_url}
            target="_blank"
            rel="noreferrer"
            className="shrink-0 text-[10px] text-accent-strong hover:underline"
          >
            View
          </a>
        )}
      </div>
      {evidence.match_reason && (
        <p className="mt-1.5 text-[10px] text-foreground-muted">{evidence.match_reason}</p>
      )}
      {evidence.evidence_text && (
        <>
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-1.5 text-[10px] text-accent-strong hover:underline"
          >
            {expanded ? "Hide evidence" : "Show evidence"}
          </button>
          {expanded && (
            <p className="mt-1 whitespace-pre-line rounded bg-background p-2 text-[10px] leading-relaxed text-foreground-muted">
              {evidence.evidence_text}
            </p>
          )}
        </>
      )}
    </div>
  );
}

function EventLog({ events }: { events: InvestigationEvent[] }) {
  if (!events.length) return null;

  return (
    <div className="mt-3">
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-foreground-faint">
        Investigation Events ({events.length})
      </p>
      <div className="flex max-h-48 flex-col gap-1 overflow-y-auto pr-1">
        {[...events].reverse().map((event, i) => (
          <div key={i} className="flex items-start gap-2 rounded bg-surface/60 px-3 py-1.5 text-[11px]">
            <span className={`mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full ${
              event.result === "error" ? "bg-status-negative" :
              event.result === "partial" ? "bg-status-caution" :
              "bg-status-positive"
            }`} />
            <div className="min-w-0">
              <span className="font-medium text-foreground">{titleCase((event.action || "").replace(/_/g, " "))}</span>
              {event.source && <span className="ml-1 text-foreground-faint">· {event.source}</span>}
              {event.error && <span className="ml-1 text-status-negative">· {event.error}</span>}
              {event.note && <span className="ml-1 text-foreground-faint">· {event.note}</span>}
              {event.emails_discovered ? <span className="ml-1 text-status-positive">· {event.emails_discovered} emails</span> : null}
              {event.phones_discovered ? <span className="ml-1 text-status-positive">· {event.phones_discovered} phones</span> : null}
              {event.profiles_discovered ? <span className="ml-1 text-status-positive">· {event.profiles_discovered} profiles</span> : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function InvestigationProfile({ lead }: { lead: Lead }) {
  const [loading, setLoading] = useState<string | null>(null);
  const [profile, setProfile] = useState<InvestigationProfile | null>(
    lead.investigation ?? null
  );
  const [expanded, setExpanded] = useState(false);
  const [eventLogExpanded, setEventLogExpanded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const applicationNumber = lead.application_number;

  const refreshProfile = useCallback(async () => {
    try {
      const resp = await getInvestigation(applicationNumber);
      if (resp.investigation) {
        setProfile(resp.investigation);
      }
    } catch {
      // Non-fatal — keep existing profile state
    }
  }, [applicationNumber]);

  const runSource = useCallback(
    async (source: string, fn: (appNum: string, opts?: { force?: boolean }) => Promise<unknown>) => {
      setLoading(source);
      setError(null);
      try {
        await fn(applicationNumber, { force: true });
        await refreshProfile();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Investigation failed");
      } finally {
        setLoading(null);
      }
    },
    [applicationNumber, refreshProfile]
  );

  const runInvestigateAll = useCallback(async () => {
    setLoading("all");
    setError(null);
    try {
      await investigateAll(applicationNumber, { force: true });
      await refreshProfile();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Investigation failed");
    } finally {
      setLoading(null);
    }
  }, [applicationNumber, refreshProfile]);

  const investigation = profile ?? (lead.investigation as InvestigationProfile | undefined);

  const sources = investigation?.sources ?? ({} as Record<string, string>);
  const contacts = investigation?.contacts;
  const summary = investigation?.summary;
  const identityMatches = investigation?.identity_matches ?? [];
  const events = investigation?.events ?? [];
  const allEvidence = investigation?.evidence ?? [];
  const invStatus = (investigation?.status ?? "NOT_STARTED") as InvestigationStatus;

  const hasEvidence = allEvidence.length > 0;
  const hasContacts = (contacts?.email_candidates?.length ?? 0) > 0 || (contacts?.phone_candidates?.length ?? 0) > 0;
  const hasIdentity = identityMatches.length > 0;

  return (
    <details open={expanded} className="group rounded-lg border border-border-subtle bg-card">
      <summary
        className="flex cursor-pointer items-center justify-between px-5 py-4 select-none"
        onClick={(e) => {
          e.preventDefault();
          setExpanded(!expanded);
        }}
      >
        <div className="flex items-center gap-3">
          <svg
            className={`h-4 w-4 shrink-0 text-foreground-faint transition-transform ${expanded ? "rotate-90" : ""}`}
            viewBox="0 0 12 12"
            fill="currentColor"
          >
            <path d="M4.5 2l4 4-4 4" />
          </svg>
          <h3 className="text-[13px] font-semibold uppercase tracking-[0.1em] text-foreground">
            Investigation Profile
          </h3>
          <Badge variant={statusVariant(invStatus)}>
            {invStatus.replace(/_/g, " ")}
          </Badge>
          {summary && (summary.emails_found + summary.phones_found + summary.websites_found > 0) && (
            <span className="text-[11px] text-foreground-faint">
              {summary.emails_found} emails · {summary.phones_found} phones · {summary.websites_found} websites
            </span>
          )}
        </div>
      </summary>

      {expanded && (
        <div className="flex flex-col gap-5 px-5 pb-5">
          {/* Owner / Entity Identity */}
          <SectionCard title="Owner / Entity" description="Government-record identity for the property owner.">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Owner Name" value={lead.owner_name} />
              <Field label="Owner Entity" value={lead.owner_entity} />
              <Field label="Owner Type" value={lead.owner_type ? titleCase(lead.owner_type) : null} />
              <Field label="Source" value={lead.owner_source ? titleCase(lead.owner_source.replace(/_/g, " ")) : null} />
              <Field label="Confidence" value={lead.owner_confidence ? titleCase(lead.owner_confidence) : null} />
              <Field label="Applicant" value={lead.applicant_name} />
            </div>
          </SectionCard>

          {/* Investigation Buttons */}
          <SectionCard
            title="Investigation Pipelines"
            description="Run source-specific investigation pipelines. Each pipeline searches a different public data source."
          >
            <div className="flex flex-wrap gap-2">
              <InvestigationButton
                label="Investigate Everything"
                icon="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z"
                onClick={runInvestigateAll}
                loading={loading === "all"}
                status={invStatus}
              />
              {(
                [
                  ["web", "Search Web", investigateWeb],
                  ["website", "Find Website", investigateWebsite],
                  ["directories", "Search Directories", investigateDirectories],
                  ["linkedin", "Find LinkedIn", investigateLinkedin],
                  ["public_records", "Search Records", investigatePublicRecords],
                  ["project", "Find Connections", investigateProject],
                  ["contact", "Find Contacts", investigateContact],
                ] as const
              ).map(([key, label, fn]) => (
                <InvestigationButton
                  key={key}
                  label={label}
                  icon={SOURCE_ICONS[key]}
                  onClick={() => runSource(key, fn)}
                  loading={loading === key}
                  status={(sources[key] ?? "NOT_STARTED") as InvestigationStatus}
                />
              ))}
            </div>

            {error && (
              <div className="mt-3 rounded-lg border border-status-negative/30 bg-status-negative-soft p-3 text-xs text-status-negative">
                {error}
              </div>
            )}

            {/* Source Status Grid */}
            <div className="mt-4 grid grid-cols-2 gap-2 border-t border-border-subtle pt-4 sm:grid-cols-4">
              {(Object.entries(SOURCE_LABELS) as [InvestigationSource, string][]).map(([key, label]) => (
                <div key={key} className="flex items-center gap-2 text-xs">
                  <SourceStatusDot status={(sources[key] ?? "NOT_STARTED") as InvestigationStatus} />
                  <span className="text-foreground-muted">{label}</span>
                  <span className="ml-auto text-[10px] text-foreground-faint">
                    {(sources[key] ?? "NOT_STARTED").replace(/_/g, " ")}
                  </span>
                </div>
              ))}
            </div>
          </SectionCard>

          {/* Discovered Contacts */}
          <SectionCard
            title="Discovered Contacts"
            description="Publicly discovered contact information ranked by source quality."
          >
            <div className="grid grid-cols-2 gap-3">
              <ContactField label="Preferred Email" value={contacts?.preferred_email ?? null} href={(v) => `mailto:${v}`} />
              <ContactField label="Preferred Phone" value={contacts?.preferred_phone ?? null} />
              <ContactField
                label="Preferred Website"
                value={contacts?.preferred_website ?? null}
                href={(v) => (v.startsWith("http") ? v : `https://${v}`)}
              />
              <Field
                label="Email Candidates"
                value={contacts?.email_candidates?.length ? `${contacts.email_candidates.length} found` : null}
              />
              <Field
                label="Phone Candidates"
                value={contacts?.phone_candidates?.length ? `${contacts.phone_candidates.length} found` : null}
              />
              <Field
                label="Website Candidates"
                value={contacts?.website_candidates?.length ? `${contacts.website_candidates.length} found` : null}
              />
            </div>

            {!hasContacts && invStatus !== "NOT_STARTED" && (
              <p className="mt-3 text-xs italic text-foreground-faint">
                No public contact information discovered yet. Run an investigation pipeline to search.
              </p>
            )}
          </SectionCard>

          {/* Evidence */}
          {hasEvidence && (
            <SectionCard
              title="Investigation Evidence"
              description={`All evidence collected across investigation pipelines. ${allEvidence.length} total evidence items.`}
              actions={
                <button
                  onClick={() => setEventLogExpanded(!eventLogExpanded)}
                  className="text-[10px] text-accent-strong hover:underline"
                >
                  {eventLogExpanded ? "Hide events" : "Show events"}
                </button>
              }
            >
              <div className="flex max-h-64 flex-col gap-2 overflow-y-auto pr-1">
                {allEvidence.map((ev, i) => (
                  <EvidenceItem key={i} evidence={ev} />
                ))}
              </div>

              {eventLogExpanded && <EventLog events={events} />}
            </SectionCard>
          )}

          {/* Identity Matches */}
          {hasIdentity && (
            <SectionCard title="Identity Resolution" description="How discovered information relates to the known owner/entity.">
              <div className="flex max-h-48 flex-col gap-2 overflow-y-auto pr-1">
                {identityMatches.slice(0, 5).map((match, i) => (
                  <div key={i} className="rounded-lg border border-border-subtle bg-surface/60 p-3">
                    <div className="flex items-center gap-2">
                      <Badge variant={match.confidence_label === "HIGH" ? "status-positive" : match.confidence_label === "MEDIUM" ? "status-caution" : "status-neutral"}>
                        {match.confidence_label}
                      </Badge>
                      <span className="text-xs text-foreground-muted">
                        Score: {(match.match_score * 100).toFixed(0)}%
                      </span>
                      {match.source_url && (
                        <a
                          href={match.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="ml-auto text-[10px] text-accent-strong hover:underline"
                        >
                          Source
                        </a>
                      )}
                    </div>
                    {match.reasoning && (
                      <p className="mt-1.5 text-[11px] text-foreground-muted">{match.reasoning}</p>
                    )}
                    {match.matched_signals.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {match.matched_signals.map((signal, j) => (
                          <span key={j} className="rounded bg-status-positive-soft px-1.5 py-0.5 text-[9px] text-status-positive">
                            {signal}
                          </span>
                        ))}
                      </div>
                    )}
                    {match.conflicting_signals.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {match.conflicting_signals.map((signal, j) => (
                          <span key={j} className="rounded bg-status-negative-soft px-1.5 py-0.5 text-[9px] text-status-negative">
                            {signal}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </SectionCard>
          )}

          {/* Investigation History */}
          {events.length > 0 && (
            <EventLog events={events} />
          )}
        </div>
      )}
    </details>
  );
}
