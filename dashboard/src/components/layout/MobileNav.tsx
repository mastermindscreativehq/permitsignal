"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Overview" },
  { href: "/properties", label: "Property Intelligence" },
  { href: "/properties?event=yes", label: "Upcoming Events" },
  { href: "/properties?friction=yes", label: "Friction" },
  { href: "/properties?contactability=needs_discovery", label: "Contact Intel." },
];

export function MobileNav() {
  const pathname = usePathname();

  return (
    <div className="flex flex-col gap-2 border-b border-border-subtle bg-background-elevated px-4 py-3 lg:hidden">
      <div className="flex items-center gap-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-md border border-accent/40 bg-accent-soft">
          <span className="font-mono text-[10px] font-semibold text-accent-strong">PS</span>
        </div>
        <span className="text-sm font-semibold text-foreground">PermitSignal</span>
      </div>
      <nav className="flex items-center gap-4 overflow-x-auto">
        {NAV_ITEMS.map((item) => {
          const path = item.href.split("?")[0];
          const active = pathname === path;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`whitespace-nowrap text-xs font-medium ${active ? "text-foreground" : "text-foreground-muted"}`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
