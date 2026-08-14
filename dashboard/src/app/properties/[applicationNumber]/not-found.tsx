import Link from "next/link";

/**
 * Rendered when getLeadByApplicationNumber() (lib/leads.ts) resolves to
 * null -- either the Phase 4 API returned 404 for this application_number,
 * or it isn't configured/populated yet. Distinct from app/error.tsx: this
 * is an evidence-backed absence (no such lead), not an API failure.
 */
export default function LeadNotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
      <div className="panel flex max-w-lg flex-col items-center gap-3 p-8">
        <span className="h-2.5 w-2.5 rounded-full bg-status-neutral" />
        <h1 className="text-lg font-semibold text-foreground">No lead on record for this application number</h1>
        <p className="text-sm text-foreground-muted">
          PermitSignal has no canonical lead/opportunity record matching this application number. It may not have
          been ingested yet, or the number may be incorrect.
        </p>
        <Link
          href="/properties"
          className="mt-2 rounded-md border border-border-subtle bg-surface px-3.5 py-2 text-sm font-medium text-foreground transition-colors hover:border-accent hover:text-accent-strong"
        >
          ← Back to Opportunities
        </Link>
      </div>
    </div>
  );
}
