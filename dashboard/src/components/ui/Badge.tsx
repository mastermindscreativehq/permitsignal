import type { ReactNode } from "react";

type Variant =
  | "priority-high"
  | "priority-medium"
  | "priority-low"
  | "status-positive"
  | "status-caution"
  | "status-negative"
  | "status-neutral"
  | "accent";

const VARIANT_STYLES: Record<Variant, { fg: string; bg: string; dot: string }> = {
  "priority-high": {
    fg: "text-priority-high",
    bg: "bg-priority-high-soft",
    dot: "bg-priority-high",
  },
  "priority-medium": {
    fg: "text-priority-medium",
    bg: "bg-priority-medium-soft",
    dot: "bg-priority-medium",
  },
  "priority-low": {
    fg: "text-priority-low",
    bg: "bg-priority-low-soft",
    dot: "bg-priority-low",
  },
  "status-positive": {
    fg: "text-status-positive",
    bg: "bg-status-positive-soft",
    dot: "bg-status-positive",
  },
  "status-caution": {
    fg: "text-status-caution",
    bg: "bg-status-caution-soft",
    dot: "bg-status-caution",
  },
  "status-negative": {
    fg: "text-status-negative",
    bg: "bg-status-negative-soft",
    dot: "bg-status-negative",
  },
  "status-neutral": {
    fg: "text-status-neutral",
    bg: "bg-status-neutral-soft",
    dot: "bg-status-neutral",
  },
  accent: {
    fg: "text-accent-strong",
    bg: "bg-accent-soft",
    dot: "bg-accent",
  },
};

export function Badge({
  variant = "status-neutral",
  children,
  dot = true,
  className = "",
}: {
  variant?: Variant;
  children: ReactNode;
  dot?: boolean;
  className?: string;
}) {
  const styles = VARIANT_STYLES[variant];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide ${styles.fg} ${styles.bg} ${className}`}
    >
      {dot && <span className={`h-1.5 w-1.5 rounded-full ${styles.dot}`} />}
      {children}
    </span>
  );
}
