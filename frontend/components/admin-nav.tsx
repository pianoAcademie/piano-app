"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type UiLanguage = "fr" | "en";

type LocalizedLabel = Record<UiLanguage, string>;

type NavItem = {
  href: string;
  label: LocalizedLabel;
  icon: string;
  permission?: string;
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
      { href: "/admin", label: { fr: "Planning", en: "Schedule" }, icon: "📅", permission: "can_view_planning" },
      { href: "/admin/planning-reorganization", label: { fr: "Reorganisation saison", en: "Season reorg" }, icon: "🧩", permission: "can_edit_planning" },
      { href: "/admin/simulation-planning", label: { fr: "Simulation planning", en: "Planning simulation" }, icon: "🧮", permission: "can_view_planning_simulation" },
      { href: "/admin/clients", label: { fr: "Clients", en: "Clients" }, icon: "👥", permission: "can_view_clients" },
      { href: "/admin/professors", label: { fr: "Collaborateurs", en: "Collaborators" }, icon: "🧑‍🏫", permission: "can_access_collaborators" },
    ],
  },
  {
    key: "finance",
    title: { fr: "Finance", en: "Finance" },
    items: [
      { href: "/admin/salary-payments", label: { fr: "Paiement des salaires", en: "Salary payments" }, icon: "💶" },
      { href: "/admin/teacher-invoicing", label: { fr: "Facturation professeurs", en: "Teacher invoicing" }, icon: "🧾" },
      { href: "/admin/billing-adjustments", label: { fr: "Regularisations a valider", en: "Billing review" }, icon: "✅", permission: "can_view_clients" },
      { href: "/admin/check-deposits", label: { fr: "Depots de cheques", en: "Check deposits" }, icon: "🏦" },
      { href: "/admin/referrals", label: { fr: "Parrainages", en: "Referrals" }, icon: "🤝" },
      { href: "/admin/subscriptions", label: { fr: "Abonnements", en: "Subscriptions" }, icon: "🔁" },
      { href: "/admin/intakes", label: { fr: "Intakes", en: "Intakes" }, icon: "🧠", permission: "can_view_intakes" },
      { href: "/admin/quotes", label: { fr: "Devis", en: "Quotes" }, icon: "📑", permission: "can_view_quotes" },
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
  isFullAdmin?: boolean;
  permissions?: Partial<Record<string, boolean | string | null>>;
  onNavigate?: () => void;
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

function hasVisiblePermission(permission: string, permissions: Partial<Record<string, boolean | string | null>>): boolean {
  if (permission === "can_view_planning" && permissions.can_edit_planning) {
    return true;
  }
  return Boolean(permissions[permission]);
}

export default function AdminNav({
  collapsed,
  language = "fr",
  isFullAdmin = true,
  permissions = {},
  onNavigate,
}: AdminNavProps): JSX.Element {
  const pathname = usePathname() || "";
  const visibleSections = NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => isFullAdmin || (item.permission ? hasVisiblePermission(item.permission, permissions) : false)),
  })).filter((section) => section.items.length > 0);

  return (
    <nav className={`admin-nav ${collapsed ? "collapsed" : ""}`}>
      {visibleSections.map((section) => (
        <section className="admin-nav-section" key={section.key}>
          <h3 className="admin-nav-section-title">{section.title[language]}</h3>
          <div className="admin-nav-section-items">
            {section.items.map((item) => (
              <Link
                key={item.href}
                href={withUiLanguage(item.href, language)}
                className={`admin-nav-link ${isLinkActive(pathname, item.href) ? "active" : ""}`}
                title={item.label[language]}
                onClick={onNavigate}
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
