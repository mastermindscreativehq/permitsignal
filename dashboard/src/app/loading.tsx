function SkeletonBlock({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-surface-strong ${className}`} />;
}

/**
 * Loading skeleton shown while any page under this layout fetches data.
 * Generic enough to work for overview, list, and detail pages.
 */
export default function Loading() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 border-b border-border-subtle pb-6">
        <SkeletonBlock className="h-3 w-24" />
        <SkeletonBlock className="h-7 w-72" />
        <SkeletonBlock className="h-4 w-96" />
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <SkeletonBlock key={index} className="h-24" />
        ))}
      </div>
      <SkeletonBlock className="h-64 w-full" />
      <SkeletonBlock className="h-48 w-full" />
    </div>
  );
}
