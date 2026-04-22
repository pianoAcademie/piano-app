"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import { type UiLanguage, uiText } from "../lib/ui-i18n";

type Crumb = {
  label: string;
  href?: string;
};

function configSectionLabels(language: UiLanguage): Record<string, string> {
  return {
    "params-account": uiText(language, "admin.breadcrumb.account_info"),
    "params-subscriptions": uiText(language, "admin.breadcrumb.subscription_settings"),
    "params-payments": uiText(language, "admin.breadcrumb.payment_methods"),
    formulas: uiText(language, "admin.breadcrumb.formulas"),
    quotes: uiText(language, "admin.breadcrumb.quotes"),
    calendars: uiText(language, "admin.breadcrumb.school_calendars"),
    activities: uiText(language, "admin.breadcrumb.activities"),
    promo: uiText(language, "admin.breadcrumb.promo"),
    products: uiText(language, "admin.breadcrumb.products"),
    "payment-rules": uiText(language, "admin.breadcrumb.payment_rules"),
    integrations: uiText(language, "admin.breadcrumb.integrations"),
    "purchase-link": uiText(language, "admin.breadcrumb.purchase_link"),
    "credit-types": uiText(language, "admin.breadcrumb.credit_types"),
  };
}

function looksLikeId(value: string): boolean {
  return value.length > 20 || value.includes("-");
}

function labelForSegment(segment: string, previous: string, language: UiLanguage): string | null {
  if (segment === "clients") {
    return uiText(language, "admin.breadcrumb.clients");
  }
  if (segment === "professors") {
    return uiText(language, "admin.breadcrumb.professors");
  }
  if (segment === "reporting") {
    return uiText(language, "admin.nav.reporting");
  }
  if (segment === "salary-payments") {
    return uiText(language, "admin.breadcrumb.salary_payments");
  }
  if (segment === "teacher-invoicing") {
    return uiText(language, "admin.breadcrumb.teacher_invoicing");
  }
  if (segment === "statements" && previous === "teacher-invoicing") {
    return uiText(language, "admin.breadcrumb.statements");
  }
  if (segment === "invoices" && previous === "teacher-invoicing") {
    return uiText(language, "admin.breadcrumb.invoices");
  }
  if (segment === "template" && previous === "teacher-invoicing") {
    return uiText(language, "admin.breadcrumb.invoice_template");
  }
  if (segment === "salary-grid" && previous === "teacher-invoicing") {
    return uiText(language, "admin.breadcrumb.salary_grid");
  }
  if (segment === "subscriptions") {
    return uiText(language, "admin.breadcrumb.subscriptions");
  }
  if (segment === "quotes") {
    return uiText(language, "admin.breadcrumb.quotes");
  }
  if (segment === "intakes") {
    return uiText(language, "admin.breadcrumb.intakes");
  }
  if (segment === "prospects") {
    return uiText(language, "admin.breadcrumb.prospects");
  }
  if (segment === "new" && previous === "quotes") {
    return uiText(language, "admin.breadcrumb.new_quote");
  }
  if (segment === "new" && previous === "prospects") {
    return uiText(language, "admin.breadcrumb.new_prospect");
  }
  if (segment === "communications") {
    return uiText(language, "admin.breadcrumb.communications");
  }
  if (segment === "a-traiter") {
    return uiText(language, "admin.breadcrumb.todo");
  }
  if (segment === "notifications") {
    return uiText(language, "admin.breadcrumb.notifications");
  }
  if (segment === "jobs" && previous === "notifications") {
    return uiText(language, "admin.breadcrumb.jobs");
  }
  if (segment === "incidents" && previous === "notifications") {
    return uiText(language, "admin.breadcrumb.incidents");
  }
  if (segment === "products") {
    return uiText(language, "admin.breadcrumb.products");
  }
  if (segment === "config") {
    return uiText(language, "admin.breadcrumb.config");
  }
  if (segment === "formulas") {
    return uiText(language, "admin.breadcrumb.formulas");
  }
  if (segment === "calendars" && previous === "config") {
    return uiText(language, "admin.breadcrumb.school_calendars");
  }
  if (segment === "new" && previous === "formulas") {
    return uiText(language, "admin.breadcrumb.new_formula");
  }
  if (segment === "plannings") {
    return uiText(language, "admin.breadcrumb.planning");
  }
  if (segment === "settings" && previous !== "config") {
    return uiText(language, "admin.breadcrumb.planning_settings");
  }

  if (previous === "clients" && looksLikeId(segment)) {
    return uiText(language, "admin.breadcrumb.client_record");
  }
  if (previous === "professors" && looksLikeId(segment)) {
    return uiText(language, "admin.breadcrumb.professor_record");
  }
  if (previous === "formulas" && looksLikeId(segment)) {
    return uiText(language, "admin.breadcrumb.edit_formula");
  }
  if (previous === "quotes" && looksLikeId(segment)) {
    return uiText(language, "admin.breadcrumb.quote_detail");
  }
  if (previous === "intakes" && looksLikeId(segment)) {
    return uiText(language, "admin.breadcrumb.intake_detail");
  }
  if (previous === "prospects" && looksLikeId(segment)) {
    return uiText(language, "admin.breadcrumb.prospect_detail");
  }

  if (looksLikeId(segment)) {
    return uiText(language, "admin.breadcrumb.detail");
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
  language?: UiLanguage;
};

export default function AdminBreadcrumb({ compact = false, language = "fr" }: AdminBreadcrumbProps): JSX.Element | null {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  if (!pathname) {
    return null;
  }
  let crumbs: Crumb[] = [];
  try {
    const segments = pathname.split("/").filter(Boolean);
    if (segments[0] !== "admin") {
      return null;
    }

    const sectionLabels = configSectionLabels(language);
    crumbs = [{ label: uiText(language, "admin.breadcrumb.admin"), href: "/admin" }];

    if (segments.length === 1) {
      crumbs.push({ label: uiText(language, "admin.breadcrumb.planning") });
    } else {
      for (let i = 1; i < segments.length; i += 1) {
        const segment = segments[i];
        const previous = segments[i - 1] ?? "";
        const label = labelForSegment(segment, previous, language);

        if (!label) {
          continue;
        }

        const href = i === segments.length - 1 ? undefined : hrefForSegment(segments, i);
        crumbs.push({ label, href });
      }
    }

    if (pathname === "/admin/config") {
      const section = searchParams?.get("section");
      const sectionLabel = section ? sectionLabels[section] : undefined;
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
      <nav className="admin-breadcrumb admin-breadcrumb-inline" aria-label={uiText(language, "admin.breadcrumb_title")}>
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
    <section className="admin-breadcrumb-wrap" aria-label={uiText(language, "admin.breadcrumb_title")}>
      <small className="admin-breadcrumb-title">{uiText(language, "admin.breadcrumb_title")}</small>
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
