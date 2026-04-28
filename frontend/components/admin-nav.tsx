"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type UiLanguage = "fr" | "en";

type LocalizedLabel = Record<UiLanguage, string>;

type NavItem = {
  href: string;
  label: LocalizedLabel;
  icon: string;
};

type NavSection = {
  key: string;
  title: LocalizedLabel;
  items: NavItem[];
};

const NAV_SECTIONS: NavSection[] = [
  {
    key: "operations",
    title: { fr: "Operations", en: "Operations" },
    items: [
      { href: "/admin", label: { fr: "Planning", en: "Schedule" }, icon: "📅" },
      { href: "/admin/simulation-planning", label: { fr: "Simulation planning", en: "Planning simulation" }, icon: "🧮" },
      { href: "/admin/clients", label: { fr: "Clients", en: "Clients" }, icon: "👥" },
      { href: "/admin/professors", label: { fr: "Collaborateurs", en: "Collaborators" }, icon: "🧑‍🏫" },
    ],
  },
  {
    key: "finance",
    title: { fr: "Finance", en: "Finance" },
    items: [
      { href: "/admin/salary-payments", label: { fr: "Paiement des salaires", en: "Salary payments" }, icon: "💶" },
      { href: "/admin/teacher-invoicing", label: { fr: "Facturation professeurs", en: "Teacher invoicing" }, icon: "🧾" },
      { href: "/admin/subscriptions", label: { fr: "Abonnements", en: "Subscriptions" }, icon: "🔁" },
      { href: "/admin/intakes", label: { fr: "Intakes", en: "Intakes" }, icon: "🧠" },
      { href: "/admin/quotes", label: { fr: "Devis", en: "Quotes" }, icon: "📑" },
      { href: "/admin/prospects", label: { fr: "Prospects", en: "Prospects" }, icon: "🧲" },
      { href: "/admin/products", label: { fr: "Produits", en: "Products" }, icon: "📦" },
    ],
  },
  {
    key: "communication",
    title: { fr: "Communication", en: "Communication" },
    items: [
      { href: "/admin/a-traiter", label: { fr: "A traiter", en: "To process" }, icon: "📥" },
      { href: "/admin/communications", label: { fr: "Communications", en: "Communications" }, icon: "✉️" },
      { href: "/admin/notifications/jobs", label: { fr: "Monitoring jobs", en: "Job monitoring" }, icon: "🧭" },
      { href: "/admin/notifications/incidents", label: { fr: "Incidents", en: "Incidents" }, icon: "🚨" },
    ],
  },
  {
    key: "administration",
    title: { fr: "Administration", en: "Administration" },
    items: [
      { href: "/admin/config", label: { fr: "Configuration", en: "Settings" }, icon: "⚙️" },
      { href: "/admin/reporting", label: { fr: "Reporting", en: "Reporting" }, icon: "📊" },
    ],
  },
];

type AdminNavProps = {
  collapsed: boolean;
  language?: UiLanguage;
};

function isLinkActive(pathname: string, href: string): boolean {
  if (href === "/admin") {
    return pathname === "/admin";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

function withUiLanguage(href: string, language: UiLanguage): string {
  if (language !== "en") {
    return href;
  }
  return `${href}${href.includes("?") ? "&" : "?"}lang=en`;
}

export default function AdminNav({ collapsed, language = "fr" }: AdminNavProps): JSX.Element {
  const pathname = usePathname() || "";

  return (
    <nav className={`admin-nav ${collapsed ? "collapsed" : ""}`}>
      {NAV_SECTIONS.map((section) => (
        <section className="admin-nav-section" key={section.key}>
          <h3 className="admin-nav-section-title">{section.title[language]}</h3>
          <div className="admin-nav-section-items">
            {section.items.map((item) => (
              <Link
                key={item.href}
                href={withUiLanguage(item.href, language)}
                className={`admin-nav-link ${isLinkActive(pathname, item.href) ? "active" : ""}`}
                title={item.label[language]}
              >
                <span className="admin-nav-icon" aria-hidden="true">
                  {item.icon}
                </span>
                <span className="admin-nav-label">{item.label[language]}</span>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </nav>
  );
}
