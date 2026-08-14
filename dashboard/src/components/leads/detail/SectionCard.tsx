import type { ReactNode } from "react";

export function SectionCard({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="panel min-w-0 p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-[13px] font-semibold uppercase tracking-[0.1em] text-foreground">{title}</h3>
          {description && <p className="mt-1 text-xs text-foreground-faint">{description}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}
