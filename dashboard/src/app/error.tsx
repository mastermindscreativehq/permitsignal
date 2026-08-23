"use client";

import { useEffect } from "react";

/**
 * Catches PermitSignalApiError (lib/leads.ts) -- an unreachable API,
 * non-2xx response, or malformed JSON -- and any other rendering error
 * under this layout. Never shows a raw stack trace or a misleading
 * "no leads" empty state when the real problem is the API being down;
 * see docs/PHASE_5_FRONTEND_LIVE_INTELLIGENCE.md Step 6 ("API unavailable"
 * / "malformed API response").
 */
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error("PermitSignal dashboard error:", error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
      <div className="panel flex max-w-lg flex-col items-center gap-3 p-8">
        <span className="h-2.5 w-2.5 rounded-full bg-status-negative" />
        <h1 className="text-lg font-semibold text-foreground">Unable to load intelligence</h1>
        <p className="text-sm text-foreground-muted">
          {error.message || "The Provo Administrative Services Finance API did not return a usable response."}
        </p>
        <p className="text-xs text-foreground-faint">
          This is a connectivity/response problem, not missing data -- no intelligence has been fabricated to fill
          the gap.
        </p>
        <button
          onClick={() => reset()}
          className="mt-2 rounded-md border border-border-subtle bg-surface px-3.5 py-2 text-sm font-medium text-foreground transition-colors hover:border-accent hover:text-accent-strong"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
