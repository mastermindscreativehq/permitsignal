"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Overview" },
  { href: "/properties", label: "Opportunities" },
  { href: "/ready-for-outreach", label: "Outreach" },
  { href: "/upcoming", label: "Events" },
  { href: "/contact-discovery", label: "Contacts" },
];

export function MobileNav() {
  const pathname = usePathname();

  return (
    <div className="flex flex-col gap-2 border-b border-border-subtle bg-background-elevated px-4 py-3 lg:hidden">
      <div className="flex items-center gap-2">
        <Image
          src="/assets/provo-logo.png"
          alt="Provo Administrative Services Finance logo"
          width={28}
          height={28}
          className="h-7 w-7 shrink-0 object-contain"
        />
        <span className="text-[11px] font-semibold text-foreground">
          PROVO ADMINISTRATIVE SERVICES FINANCE
        </span>
      </div>
      <nav className="flex items-center gap-4 overflow-x-auto">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`whitespace-nowrap text-xs font-medium ${isActive ? "text-foreground" : "text-foreground-muted"}`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
