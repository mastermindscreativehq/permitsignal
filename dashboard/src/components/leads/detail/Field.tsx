import type { ReactNode } from "react";

export function Field({
  label,
  value,
  mono = false,
  fallback = "—",
}: {
  label: string;
  value: ReactNode | null | undefined;
  mono?: boolean;
  fallback?: string;
}) {
  const isEmpty = value === null || value === undefined || value === "";
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">{label}</p>
      {isEmpty ? (
        <p className="mt-0.5 text-sm text-foreground-faint/70 italic">{fallback}</p>
      ) : (
        <p className={`mt-0.5 text-sm text-foreground ${mono ? "font-mono break-all" : "break-words"}`}>{value}</p>
      )}
    </div>
  );
}

/** For contact-intelligence fields specifically: CLAUDE.md requires "NOT FOUND" rather than a blank or a fake-looking placeholder. */
export function ContactField({
  label,
  value,
  href,
  mono = true,
}: {
  label: string;
  value: string | null | undefined;
  href?: (value: string) => string;
  mono?: boolean;
}) {
  const isEmpty = !value;
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-medium uppercase tracking-wide text-foreground-faint">{label}</p>
      {isEmpty ? (
        <p className="mt-0.5 inline-flex items-center gap-1.5 text-sm italic text-foreground-faint/70">
          <span className="h-1.5 w-1.5 rounded-full bg-status-neutral" />
          NOT FOUND
        </p>
      ) : href ? (
        <a
          href={href(value)}
          target="_blank"
          rel="noreferrer"
          className={`mt-0.5 block text-sm text-accent-strong hover:underline ${mono ? "font-mono break-all" : "break-words"}`}
        >
          {value}
        </a>
      ) : (
        <p className={`mt-0.5 text-sm text-foreground ${mono ? "font-mono break-all" : "break-words"}`}>{value}</p>
      )}
    </div>
  );
}
