import React from "react";
import Link from "next/link";

import { type UiLanguage, uiText } from "../../lib/ui-i18n";

export type SidebarItem = {
  id: string;
  label: string;
  href: string;
  active?: boolean;
  badge?: string;
  badgeTone?: "default" | "alert";
};

export default function QuoteWorkspaceSidebar({
  items,
  language = "fr",
}: {
  items: SidebarItem[];
  language?: UiLanguage;
}): JSX.Element {
  return (
    <section className="card quote-workspace-sidebar-card" aria-label={uiText(language, "admin.quote_detail.sidebar_title")}>
      <h3>{uiText(language, "admin.quote_detail.sidebar_title")}</h3>
      <nav className="quote-workspace-sidebar-nav top-gap-sm" aria-label={uiText(language, "admin.quote_detail.sidebar_aria")}>
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
