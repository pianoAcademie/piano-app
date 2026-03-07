"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavItem = {
  href: string;
  label: string;
  icon: string;
};

type NavSection = {
  title: string;
  items: NavItem[];
};

const NAV_SECTIONS: NavSection[] = [
  {
    title: "Operations",
    items: [
      { href: "/admin", label: "Planning", icon: "📅" },
      { href: "/admin/clients", label: "Clients", icon: "👥" },
      { href: "/admin/professors", label: "Collaborateurs", icon: "🧑‍🏫" },
    ],
  },
  {
    title: "Finance",
    items: [
      { href: "/admin/salary-payments", label: "Paiement des salaires", icon: "💶" },
      { href: "/admin/teacher-invoicing", label: "Facturation professeurs", icon: "🧾" },
      { href: "/admin/subscriptions", label: "Abonnements", icon: "🔁" },
      { href: "/admin/quotes", label: "Devis", icon: "📑" },
      { href: "/admin/products", label: "Produits", icon: "📦" },
    ],
  },
  {
    title: "Communication",
    items: [
      { href: "/admin/communications", label: "Communications", icon: "✉️" },
      { href: "/admin/notifications/jobs", label: "Monitoring jobs", icon: "🧭" },
      { href: "/admin/notifications/incidents", label: "Incidents", icon: "🚨" },
    ],
  },
  {
    title: "Administration",
    items: [
      { href: "/admin/config", label: "Configuration", icon: "⚙️" },
      { href: "/admin/reporting", label: "Reporting", icon: "📊" },
    ],
  },
];

type AdminNavProps = {
  collapsed: boolean;
};

function isLinkActive(pathname: string, href: string): boolean {
  if (href === "/admin") {
    return pathname === "/admin";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function AdminNav({ collapsed }: AdminNavProps): JSX.Element {
  const pathname = usePathname() || "";

  return (
    <nav className={`admin-nav ${collapsed ? "collapsed" : ""}`}>
      {NAV_SECTIONS.map((section) => (
        <section className="admin-nav-section" key={section.title}>
          <h3 className="admin-nav-section-title">{section.title}</h3>
          <div className="admin-nav-section-items">
            {section.items.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`admin-nav-link ${isLinkActive(pathname, item.href) ? "active" : ""}`}
                title={item.label}
              >
                <span className="admin-nav-icon" aria-hidden="true">
                  {item.icon}
                </span>
                <span className="admin-nav-label">{item.label}</span>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </nav>
  );
}
