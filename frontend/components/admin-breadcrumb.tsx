"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

type Crumb = {
  label: string;
  href?: string;
};

const CONFIG_SECTION_LABELS: Record<string, string> = {
  "params-account": "Informations du compte",
  "params-subscriptions": "Parametrage abonnements",
  "params-payments": "Moyens de paiement",
  formulas: "Formules",
  activities: "Activites",
  promo: "Code promo",
  products: "Produits",
  "payment-rules": "Regles de paiement",
  integrations: "Integrations",
  "purchase-link": "Lien d'achat",
  "credit-types": "Types de credit",
};

function looksLikeId(value: string): boolean {
  return value.length > 20 || value.includes("-");
}

function labelForSegment(segment: string, previous: string): string | null {
  if (segment === "clients") {
    return "Clients";
  }
  if (segment === "professors") {
    return "Collaborateurs";
  }
  if (segment === "reporting") {
    return "Reporting";
  }
  if (segment === "communications") {
    return "Communications";
  }
  if (segment === "products") {
    return "Produits";
  }
  if (segment === "config") {
    return "Configuration";
  }
  if (segment === "formulas") {
    return "Formules";
  }
  if (segment === "new" && previous === "formulas") {
    return "Nouvelle formule";
  }
  if (segment === "plannings") {
    return "Planning";
  }
  if (segment === "settings" && previous !== "config") {
    return "Parametres planning";
  }

  if (previous === "clients" && looksLikeId(segment)) {
    return "Fiche client";
  }
  if (previous === "professors" && looksLikeId(segment)) {
    return "Fiche collaborateur";
  }
  if (previous === "formulas" && looksLikeId(segment)) {
    return "Modifier formule";
  }

  if (looksLikeId(segment)) {
    return "Detail";
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
    return "/admin/config?section=formulas";
  }

  return `/${segments.slice(0, index + 1).join("/")}`;
}

export default function AdminBreadcrumb(): JSX.Element | null {
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

    crumbs = [{ label: "Administration", href: "/admin" }];

    if (segments.length === 1) {
      crumbs.push({ label: "Planning" });
    } else {
      for (let i = 1; i < segments.length; i += 1) {
        const segment = segments[i];
        const previous = segments[i - 1] ?? "";
        const label = labelForSegment(segment, previous);

        if (!label) {
          continue;
        }

        const href = i === segments.length - 1 ? undefined : hrefForSegment(segments, i);
        crumbs.push({ label, href });
      }
    }

    if (pathname === "/admin/config") {
      const section = searchParams?.get("section");
      const sectionLabel = section ? CONFIG_SECTION_LABELS[section] : undefined;
      if (sectionLabel && !crumbs.some((crumb) => crumb.label === sectionLabel)) {
        crumbs.push({ label: sectionLabel });
      }
    }
  } catch (_err) {
    return null;
  }

  return (
    <section className="admin-breadcrumb-wrap" aria-label="Fil d'Ariane">
      <small className="admin-breadcrumb-title">Fil d'Ariane</small>
      <nav className="admin-breadcrumb">
        {crumbs.map((crumb, index) => {
          const key = `${crumb.label}-${index}`;
          const isLast = index === crumbs.length - 1;
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
