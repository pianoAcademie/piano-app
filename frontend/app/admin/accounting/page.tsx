import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { hasAccountantAccess } from "../../../lib/admin-access";
import { backendRequest } from "../../../lib/backend";
import type { UserOut } from "../../../lib/types";
import { normalizeUiLanguage } from "../../../lib/ui-i18n";

const ACCOUNTING_LINKS = [
  {
    href: "/admin/teacher-invoicing/statements",
    icon: "🧾",
    title: { fr: "Relevés mensuels", en: "Monthly statements" },
    description: {
      fr: "Consulter les prestations, présences, heures et montants de chaque professeur, puis exporter le relevé.",
      en: "Review each teacher's services, attendance, hours and amounts, then export the statement.",
    },
  },
  {
    href: "/admin/salary-payments",
    icon: "💶",
    title: { fr: "Paiements collaborateurs", en: "Collaborator payments" },
    description: {
      fr: "Voir les montants dus, saisir le règlement et retrouver l'historique des paiements.",
      en: "Review amounts due, record settlements and access payment history.",
    },
  },
  {
    href: "/admin/teacher-invoicing/invoices",
    icon: "📄",
    title: { fr: "Factures collaborateurs", en: "Collaborator invoices" },
    description: {
      fr: "Retrouver les factures reçues et les paiements enregistrés par période.",
      en: "Find received invoices and recorded payments by period.",
    },
  },
  {
    href: "/admin/reporting",
    icon: "📊",
    title: { fr: "Reportings et exports", en: "Reports and exports" },
    description: {
      fr: "Générer, télécharger et historiser les états financiers et opérationnels autorisés.",
      en: "Generate, download and retain authorized financial and operational reports.",
    },
  },
  {
    href: "/admin/check-deposits",
    icon: "🏦",
    title: { fr: "Suivi des chèques", en: "Check tracking" },
    description: {
      fr: "Suivre les chèques reçus, en transit, prêts au dépôt, déposés ou refusés, tous sites confondus.",
      en: "Track received, in-transit, ready, deposited or refused checks across all sites.",
    },
  },
] as const;

export default async function AdminAccountingPage(): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) redirect("/login?error_code=session_expired");

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || !hasAccountantAccess(meResult.data)) {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);

  return (
    <section className="admin-page-grid">
      <section className="card">
        <span className="status-pill status-info">{language === "en" ? "ACCOUNTING" : "COMPTABILITÉ"}</span>
        <h2>{language === "en" ? "Accounting workspace" : "Espace comptable"}</h2>
        <p className="muted">
          {language === "en"
            ? "A dedicated workspace for teacher statements, collaborator payments, reporting and check tracking."
            : "Un espace dédié aux relevés professeurs, aux paiements collaborateurs, aux reportings et au suivi des chèques."}
        </p>
      </section>

      <section className="grid cols-2 teacher-invoicing-hub-grid">
        {ACCOUNTING_LINKS.map((entry) => (
          <article className="card teacher-invoicing-hub-card" key={entry.href}>
            <div className="row gap-sm">
              <span aria-hidden="true">{entry.icon}</span>
              <h3>{entry.title[language]}</h3>
            </div>
            <p className="muted">{entry.description[language]}</p>
            <div className="row top-gap-sm">
              <Link className="mode-link" href={entry.href}>
                {language === "en" ? "Open" : "Ouvrir"}
              </Link>
            </div>
          </article>
        ))}
      </section>

      <section className="card">
        <h3>{language === "en" ? "Security scope" : "Périmètre de sécurité"}</h3>
        <p className="muted">
          {language === "en"
            ? "This profile has no access to schedule editing, client messages, teaching notes or general settings. Every payment entry remains linked to the user who recorded it."
            : "Ce profil n'accède ni à la modification du planning, ni aux messages clients, ni aux notes pédagogiques, ni à la configuration générale. Chaque paiement saisi reste rattaché à son auteur."}
        </p>
      </section>
    </section>
  );
}
