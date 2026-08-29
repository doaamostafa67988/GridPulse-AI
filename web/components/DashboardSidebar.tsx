"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Map, Wallet, ArrowLeft } from "lucide-react";

const NAV_ITEMS = [
  { href: "/dashboard/overview", label: "Risk Overview", icon: LayoutDashboard },
  { href: "/dashboard/map", label: "Map View", icon: Map },
  { href: "/dashboard/plan", label: "Critical Zones & Plan", icon: Wallet },
];

export function DashboardSidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-panel-border bg-panel">
      <div className="flex items-center gap-2 border-b border-panel-border px-5 py-5">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo-icon.png" alt="GridPulse AI" className="h-8 w-8 rounded-lg object-cover" />
        <span className="text-sm font-semibold text-foreground">GridPulse AI</span>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                active
                  ? "bg-brand-light text-brand-dark"
                  : "text-muted hover:bg-gray-50 hover:text-foreground"
              }`}
            >
              <Icon size={18} />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-panel-border p-3">
        <Link
          href="/"
          className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-muted transition-colors hover:bg-gray-50 hover:text-foreground"
        >
          <ArrowLeft size={18} />
          Back to site
        </Link>
      </div>
    </aside>
  );
}
