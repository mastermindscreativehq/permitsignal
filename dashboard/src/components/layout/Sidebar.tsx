"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  {
    href: "/",
    label: "Overview",
    icon: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M3.5 10.5 12 3.5l8.5 7M5.5 9v10a1 1 0 0 0 1 1H10v-5.5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1V20h3.5a1 1 0 0 0 1-1V9"
      />
    ),
  },
  {
    href: "/properties",
    label: "Opportunities",
    icon: (
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h10" />
    ),
  },
  {
    href: "/ready-for-outreach",
    label: "Ready for Outreach",
    icon: <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />,
  },
  {
    href: "/upcoming",
    label: "Upcoming Events",
    icon: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M7 3v3M17 3v3M4 9h16M5 6h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1Z"
      />
    ),
  },
  {
    href: "/contact-discovery",
    label: "Contact Discovery",
    icon: <path strokeLinecap="round" strokeLinejoin="round" d="M4 5h16v11H8l-4 4V5Z" />,
  },
];

function isActive(href: string, pathname: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href);
}

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden w-[236px] shrink-0 flex-col border-r border-border-subtle bg-background-elevated px-4 py-6 lg:flex">
      <div className="mb-8 flex items-center gap-2.5 px-2">
        <Image
          src="/assets/provo-logo.png"
          alt="Provo Administrative Services Finance logo"
          width={32}
          height={32}
          className="h-8 w-8 shrink-0 object-contain"
        />
        <div>
          <p className="text-[11px] font-semibold leading-tight text-foreground">
            PROVO ADMINISTRATIVE SERVICES FINANCE
          </p>
          <p className="text-[11px] leading-tight text-foreground-faint">Commercial Intelligence</p>
        </div>
      </div>

      <nav className="flex flex-col gap-1">
        {NAV_ITEMS.map((item) => {
          const active = isActive(item.href, pathname);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`group flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors ${
                active
                  ? "bg-surface-strong text-foreground"
                  : "text-foreground-muted hover:bg-surface hover:text-foreground"
              }`}
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                className={`h-[17px] w-[17px] shrink-0 ${active ? "text-accent-strong" : "text-foreground-faint group-hover:text-foreground-muted"}`}
              >
                {item.icon}
              </svg>
              <span className="truncate">{item.label}</span>
              {active && <span className="ml-auto h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto">
        <div className="panel px-3 py-3">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-pulse-dot rounded-full bg-status-positive" />
            </span>
            <p className="text-xs font-medium text-foreground">Live data</p>
          </div>
          <p className="mt-1 text-[11px] leading-snug text-foreground-faint">
            Live via Provo Administrative Services Finance API
          </p>
        </div>
      </div>
    </aside>
  );
}
