import type { ReactNode } from "react";

export function StatCard({
  label,
  value,
  hint,
  accent = "neutral",
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  accent?: "neutral" | "high" | "positive" | "caution";
  icon?: ReactNode;
}) {
  const accentColor =
    accent === "high"
      ? "text-priority-high"
      : accent === "positive"
        ? "text-status-positive"
        : accent === "caution"
          ? "text-status-caution"
          : "text-foreground";

  return (
    <div className="panel panel-hover p-5">
      <div className="flex items-start justify-between">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-foreground-muted">
          {label}
        </p>
        {icon && <div className="text-foreground-faint">{icon}</div>}
      </div>
      <p className={`mt-3 font-mono text-2xl font-semibold tracking-tight ${accentColor}`}>
        {value}
      </p>
      {hint && <p className="mt-1.5 text-xs text-foreground-faint">{hint}</p>}
    </div>
  );
}
