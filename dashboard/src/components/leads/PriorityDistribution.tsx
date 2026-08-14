import type { DashboardStats } from "@/lib/types";

const COLOR: Record<string, string> = {
  HIGH: "var(--priority-high)",
  MEDIUM: "var(--priority-medium)",
  LOW: "var(--priority-low)",
};

export function PriorityDistribution({ stats }: { stats: DashboardStats }) {
  const total = stats.totalLeads || 1;

  return (
    <div className="panel p-5">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-foreground-muted">
        Priority Distribution
      </p>

      <div className="mt-4 flex h-2.5 w-full overflow-hidden rounded-full bg-surface">
        {stats.priorityDistribution.map(({ priority, count }) => (
          <div
            key={priority}
            style={{
              width: `${(count / total) * 100}%`,
              backgroundColor: COLOR[priority],
            }}
            className="h-full transition-all first:rounded-l-full last:rounded-r-full"
          />
        ))}
      </div>

      <div className="mt-4 flex flex-col gap-2.5">
        {stats.priorityDistribution.map(({ priority, count }) => (
          <div key={priority} className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: COLOR[priority] }}
              />
              <span className="text-foreground-muted">{priority}</span>
            </div>
            <span className="font-mono text-foreground">{count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
