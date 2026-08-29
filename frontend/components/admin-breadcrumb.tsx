"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import type { UiLanguage } from "../lib/ui-messages";

type Crumb = {
  label: string;
  href?: string;
};

function pickText(language: UiLanguage, fr: string, en: string): string {
  return language === "en" ? en : fr;
}

function withLanguage(href: string, language: UiLanguage): string {
  if (language !== "en") {
    return href;
  }
  const separator = href.includes("?") ? "&" : "?";
  return `${href}${separator}lang=en`;
}

function looksLikeId(value: string): boolean {
  return value.length > 20 || value.includes("-");
}

function configSectionLabel(section: string, language: UiLanguage): string | undefined {
  const labels: Record<string, string> = {
    "params-account": pickText(language, "Informations du compte", "Account information"),
    "params-subscriptions": pickText(language, "Parametrage abonnements", "Subscription settings"),
    "params-payments": pickText(language, "Moyens de paiement", "Payment methods"),
    formulas: pickText(language, "Formules", "Plans"),
    quotes: pickText(language, "Devis", "Quotes"),
    calendars: pickText(language, "Calendriers scolaires", "School calendars"),
    activities: pickText(language, "Activites", "Activities"),
    promo: pickText(language, "Code promo", "Promo code"),
    products: pickText(language, "Produits", "Products"),
    "payment-rules": pickText(language, "Regles de paiement", "Payment rules"),
    integrations: pickText(language, "Integrations", "Integrations"),
    "purchase-link": pickText(language, "Lien d'achat", "Purchase link"),
    "credit-types": pickText(language, "Types de credit", "Credit types"),
  };
  return labels[section];
}

function labelForSegment(segment: string, previous: string, language: UiLanguage): string | null {
  if (segment === "clients") {
    return pickText(language, "Clients", "Clients");
  }
  if (segment === "professors") {
    return pickText(language, "Collaborateurs", "Collaborators");
  }
  if (segment === "reporting") {
    return "Reporting";
  }
  if (segment === "realtime") {
    return pickText(language, "Temps réel", "Real-time");
  }
  if (segment === "salary-payments") {
    return pickText(language, "Paiement des salaires", "Salary payments");
  }
  if (segment === "accounting") {
    return pickText(language, "Espace comptable", "Accounting");
  }
  if (segment === "teacher-invoicing") {
    return pickText(language, "Facturation professeurs", "Teacher invoicing");
  }
  if (segment === "statements" && previous === "teacher-invoicing") {
    return pickText(language, "Releves", "Statements");
  }
  if (segment === "invoices" && previous === "teacher-invoicing") {
    return pickText(language, "Factures", "Invoices");
  }
  if (segment === "template" && previous === "teacher-invoicing") {
    return pickText(language, "Template de facture", "Invoice template");
  }
  if (segment === "salary-grid" && previous === "teacher-invoicing") {
    return pickText(language, "Grille de salaire", "Salary grid");
  }
  if (segment === "subscriptions") {
    return pickText(language, "Abonnements", "Subscriptions");
  }
  if (segment === "quotes") {
    return pickText(language, "Devis", "Quotes");
  }
  if (segment === "intakes") {
    return "Intakes";
  }
  if (segment === "tasks") {
    return pickText(language, "Tâches", "Tasks");
  }
  if (previous === "tasks" && looksLikeId(segment)) {
    return pickText(language, "Détail de la tâche", "Task details");
  }
  if (segment === "events") {
    return pickText(language, "Événements", "Events");
  }
  if (segment === "prospects") {
    return pickText(language, "Prospects", "Prospects");
  }
  if (segment === "new" && previous === "quotes") {
    return pickText(language, "Nouveau devis", "New quote");
  }
  if (segment === "new" && previous === "prospects") {
    return pickText(language, "Nouveau prospect", "New prospect");
  }
  if (segment === "communications") {
    return pickText(language, "Communications", "Communications");
  }
  if (segment === "triggers") {
    return "Triggers";
  }
  if (segment === "a-traiter") {
    return pickText(language, "A traiter", "To process");
  }
  if (segment === "notifications") {
    return pickText(language, "Notifications", "Notifications");
  }
  if (segment === "jobs" && previous === "notifications") {
    return pickText(language, "Monitoring jobs", "Job monitoring");
  }
  if (segment === "incidents" && previous === "notifications") {
    return pickText(language, "Incidents", "Incidents");
  }
  if (segment === "products") {
    return pickText(language, "Produits", "Products");
  }
  if (segment === "gift-cards") {
    return pickText(language, "Cartes cadeaux", "Gift cards");
  }
  if (segment === "config") {
    return pickText(language, "Configuration", "Settings");
  }
  if (segment === "quality-control") {
    return pickText(language, "Contrôle devis/planning", "Quote/schedule checks");
  }
  if (segment === "formulas") {
    return pickText(language, "Formules", "Plans");
  }
  if (segment === "calendars" && previous === "config") {
    return pickText(language, "Calendriers scolaires", "School calendars");
  }
  if (segment === "new" && previous === "formulas") {
    return pickText(language, "Nouvelle formule", "New plan");
  }
  if (segment === "plannings") {
    return pickText(language, "Planning", "Schedule");
  }
  if (segment === "settings" && previous !== "config") {
    return pickText(language, "Parametres planning", "Schedule settings");
  }

  if (previous === "clients" && looksLikeId(segment)) {
    return pickText(language, "Fiche client", "Client profile");
  }
  if (previous === "professors" && looksLikeId(segment)) {
    return pickText(language, "Fiche collaborateur", "Collaborator profile");
  }
  if (previous === "formulas" && looksLikeId(segment)) {
    return pickText(language, "Modifier formule", "Edit plan");
  }
  if (previous === "quotes" && looksLikeId(segment)) {
    return pickText(language, "Detail devis", "Quote details");
  }
  if (previous === "intakes" && looksLikeId(segment)) {
    return pickText(language, "Detail intake", "Intake details");
  }
  if (previous === "events" && looksLikeId(segment)) {
    return pickText(language, "Détail événement", "Event details");
  }
  if (previous === "prospects" && looksLikeId(segment)) {
    return pickText(language, "Detail prospect", "Prospect details");
  }

  if (looksLikeId(segment)) {
    return pickText(language, "Detail", "Details");
  }
  return null;
}

function hrefForSegment(segments: string[], index: number): string {
  const segment = segments[index];
  const previous = segments[index - 1] ?? "";

  if (segment === "plannings") {
    return "/admin";
  }
  if (segment === "formulas" && previous === "config") {
    return "/admin/config/formulas";
  }

  return `/${segments.slice(0, index + 1).join("/")}`;
}

type AdminBreadcrumbProps = {
  compact?: boolean;
};

export default function AdminBreadcrumb({ compact = false }: AdminBreadcrumbProps): JSX.Element | null {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const language: UiLanguage = searchParams?.get("lang") === "en" ? "en" : "fr";
  if (!pathname) {
    return null;
  }
  let crumbs: Crumb[] = [];
  try {
    const segments = pathname.split("/").filter(Boolean);
    if (segments[0] !== "admin") {
      return null;
    }

    crumbs = [{ label: pickText(language, "Administration", "Administration"), href: withLanguage("/admin", language) }];

    if (segments.length === 1) {
      crumbs.push({ label: pickText(language, "Planning", "Schedule") });
    } else {
      for (let i = 1; i < segments.length; i += 1) {
        const segment = segments[i];
        const previous = segments[i - 1] ?? "";
        const label = labelForSegment(segment, previous, language);

        if (!label) {
          continue;
        }

        const href = i === segments.length - 1 ? undefined : withLanguage(hrefForSegment(segments, i), language);
        crumbs.push({ label, href });
      }
    }

    if (pathname === "/admin/config") {
      const section = searchParams?.get("section");
      const sectionLabel = section ? configSectionLabel(section, language) : undefined;
      if (sectionLabel && !crumbs.some((crumb) => crumb.label === sectionLabel)) {
        crumbs.push({ label: sectionLabel });
      }
    }
  } catch (_err) {
    return null;
  }

  const compactCrumbs = crumbs.length > 1 ? crumbs.slice(1) : crumbs;
  const crumbsToRender = compact ? compactCrumbs : crumbs;

  if (compact) {
    return (
      <nav className="admin-breadcrumb admin-breadcrumb-inline" aria-label={pickText(language, "Fil d'Ariane", "Breadcrumb")}>
        {crumbsToRender.map((crumb, index) => {
          const key = `${crumb.label}-${index}`;
          const isLast = index === crumbsToRender.length - 1;
          return (
            <span className="admin-breadcrumb-item" key={key}>
              {crumb.href && !isLast ? (
                <Link href={crumb.href} className="admin-breadcrumb-link">
                  {crumb.label}
                </Link>
              ) : (
                <span className="admin-breadcrumb-current">{crumb.label}</span>
              )}
              {!isLast ? <span className="admin-breadcrumb-sep">/</span> : null}
            </span>
          );
        })}
      </nav>
    );
  }

  return (
    <section className="admin-breadcrumb-wrap" aria-label={pickText(language, "Fil d'Ariane", "Breadcrumb")}>
      <small className="admin-breadcrumb-title">{pickText(language, "Fil d'Ariane", "Breadcrumb")}</small>
      <nav className="admin-breadcrumb">
        {crumbsToRender.map((crumb, index) => {
          const key = `${crumb.label}-${index}`;
          const isLast = index === crumbsToRender.length - 1;
          return (
            <span className="admin-breadcrumb-item" key={key}>
              {crumb.href && !isLast ? (
                <Link href={crumb.href} className="admin-breadcrumb-link">
                  {crumb.label}
                </Link>
              ) : (
                <span className="admin-breadcrumb-current">{crumb.label}</span>
              )}
              {!isLast ? <span className="admin-breadcrumb-sep">/</span> : null}
            </span>
          );
        })}
      </nav>
    </section>
  );
}
