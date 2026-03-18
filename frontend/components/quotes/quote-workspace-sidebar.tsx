import React from "react";
import Link from "next/link";

export type SidebarItem = {
  id: string;
  label: string;
  href: string;
  active?: boolean;
  badge?: string;
  badgeTone?: "default" | "alert";
};

export default function QuoteWorkspaceSidebar({ items }: { items: SidebarItem[] }): JSX.Element {
  return (
    <section className="card quote-workspace-sidebar-card">
      <h3>Navigation devis</h3>
      <nav className="quote-workspace-sidebar-nav top-gap-sm" aria-label="Navigation fiche devis">
        {items.map((item) => (
          <Link
            key={item.id}
            href={item.href}
            className={`quote-workspace-sidebar-link ${item.active ? "active" : ""}`.trim()}
          >
            <span>{item.label}</span>
            {item.badge ? (
              <span className={`badge ${item.badgeTone === "alert" ? "quote-workspace-sidebar-badge-alert" : ""}`.trim()}>
                {item.badge}
              </span>
            ) : null}
          </Link>
        ))}
      </nav>
    </section>
  );
}
