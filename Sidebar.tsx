"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { code: "01", label: "Overview", href: "/" },
  { code: "02", label: "Products", href: "/products" },
  { code: "03", label: "Documents", href: "/documents" },
  { code: "04", label: "Knowledge Graph", href: "/knowledge-graph" },
  { code: "05", label: "Analytics", href: "/analytics" },
  { code: "06", label: "Widget", href: "/widget" },
  { code: "07", label: "API Keys", href: "/api-keys" },
  { code: "08", label: "Settings", href: "/settings" },
];

export function Sidebar({ merchantName }: { merchantName: string }) {
  const pathname = usePathname();

  return (
    <aside className="flex w-56 flex-shrink-0 flex-col border-r border-line bg-white">
      <div className="flex items-center gap-2 px-5 py-5">
        <div className="h-5 w-5 bg-signal spec-corner" />
        <span className="font-display text-sm font-bold tracking-tight">MerchantAI</span>
      </div>
      <div className="rule-dashed mx-5 mb-2" />

      <nav className="flex-1 px-3">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`group mb-0.5 flex items-center gap-3 px-2 py-2 text-sm transition ${
                active ? "spec-corner bg-ink text-paper" : "text-ink-muted hover:bg-paper hover:text-ink"
              }`}
            >
              <span
                className={`font-mono text-[10px] ${active ? "text-brass" : "text-ink-muted/60 group-hover:text-signal"}`}
              >
                {item.code}
              </span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-line px-5 py-4">
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">Merchant</p>
        <p className="truncate text-sm font-medium">{merchantName}</p>
      </div>
    </aside>
  );
}
