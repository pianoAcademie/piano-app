"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { type UiLanguage, uiText } from "../lib/ui-i18n";

type NavItem = {
  href: string;
  label: string;
  icon: string;
};

type NavSection = {
  title: string;
  items: NavItem[];
};

function navSections(language: UiLanguage): NavSection[] {
  return [
    {
      title: uiText(language, "admin.nav.operations"),
      items: [
        { href: "/admin", label: uiText(language, "admin.nav.planning"), icon: "📅" },
        { href: "/admin/clients", label: uiText(language, "admin.nav.clients"), icon: "👥" },
        { href: "/admin/professors", label: uiText(language, "admin.nav.professors"), icon: "🧑‍🏫" },
      ],
    },
    {
      title: uiText(language, "admin.nav.finance"),
      items: [
        { href: "/admin/salary-payments", label: uiText(language, "admin.nav.salary_payments"), icon: "💶" },
        { href: "/admin/teacher-invoicing", label: uiText(language, "admin.nav.teacher_invoicing"), icon: "🧾" },
        { href: "/admin/subscriptions", label: uiText(language, "admin.nav.subscriptions"), icon: "🔁" },
        { href: "/admin/intakes", label: uiText(language, "admin.nav.intakes"), icon: "🧠" },
        { href: "/admin/quotes", label: uiText(language, "admin.nav.quotes"), icon: "📑" },
        { href: "/admin/prospects", label: uiText(language, "admin.nav.prospects"), icon: "🧲" },
        { href: "/admin/products", label: uiText(language, "admin.nav.products"), icon: "📦" },
      ],
    },
    {
      title: uiText(language, "admin.nav.communication"),
      items: [
        { href: "/admin/a-traiter", label: uiText(language, "admin.nav.todo"), icon: "📥" },
        { href: "/admin/communications", label: uiText(language, "admin.nav.communications"), icon: "✉️" },
        { href: "/admin/notifications/jobs", label: uiText(language, "admin.nav.jobs"), icon: "🧭" },
        { href: "/admin/notifications/incidents", label: uiText(language, "admin.nav.incidents"), icon: "🚨" },
      ],
    },
    {
      title: uiText(language, "admin.nav.administration"),
      items: [
        { href: "/admin/config", label: uiText(language, "admin.nav.config"), icon: "⚙️" },
        { href: "/admin/reporting", label: uiText(language, "admin.nav.reporting"), icon: "📊" },
      ],
    },
  ];
}

type AdminNavProps = {
  collapsed: boolean;
  language: UiLanguage;
};

function isLinkActive(pathname: string, href: string): boolean {
  if (href === "/admin") {
    return pathname === "/admin";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function AdminNav({ collapsed, language }: AdminNavProps): JSX.Element {
  const pathname = usePathname() || "";
  const sections = navSections(language);

  return (
    <nav className={`admin-nav ${collapsed ? "collapsed" : ""}`}>
      {sections.map((section) => (
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
