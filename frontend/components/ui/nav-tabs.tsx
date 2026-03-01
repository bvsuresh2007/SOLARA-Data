"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { label: "Sales",     href: "/dashboard/sales" },
  { label: "Inventory", href: "/dashboard/inventory" },
  { label: "Upload",    href: "/dashboard/upload" },
  { label: "Actions",   href: "/dashboard/actions" },
];

export function NavTabs() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-4 text-sm font-medium">
      {NAV_ITEMS.map(({ label, href }) => {
        const isActive = pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "transition-colors",
              isActive
                ? "text-orange-400 border-b border-orange-400 pb-0.5"
                : "text-zinc-500 hover:text-zinc-200"
            )}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
