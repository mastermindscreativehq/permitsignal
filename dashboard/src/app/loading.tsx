function SkeletonBlock({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-surface-strong ${className}`} />;
}

/**
 * Shown by Next.js while any page under this layout awaits its data fetch
 * (getLeads() / getLeadByApplicationNumber() in lib/leads.ts, both plain
 * fetch() calls against the Phase 4 API with no client-side cache) --
 * covers the "loading lead queue" and "loading lead detail" states from
 * docs/PHASE_5_FRONTEND_LIVE_INTELLIGENCE.md Step 6.
 */
export default function Loading() {
  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-3 border-b border-border-subtle pb-6">
        <SkeletonBlock className="h-3 w-24" />
        <SkeletonBlock className="h-7 w-72" />
        <SkeletonBlock className="h-4 w-96" />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }).map((_, index) => (
          <SkeletonBlock key={index} className="h-20" />
        ))}
      </div>
      <SkeletonBlock className="h-64 w-full" />
      <SkeletonBlock className="h-48 w-full" />
    </div>
  );
}
