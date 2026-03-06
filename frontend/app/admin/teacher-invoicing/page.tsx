import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import AdminTeacherInvoicingNav from "../../../components/admin-teacher-invoicing-nav";

const HUB_LINKS: Array<{ href: string; title: string; description: string }> = [
  {
    href: "/admin/teacher-invoicing/statements",
    title: "Releves",
    description: "Controle des releves, statuts, validation et suivi des litiges.",
  },
  {
    href: "/admin/teacher-invoicing/invoices",
    title: "Factures",
    description: "Liste des factures professeurs, statuts et historique des paiements.",
  },
  {
    href: "/admin/teacher-invoicing/template",
    title: "Template de facture",
    description: "Modele actif, variables et previsualisation PDF.",
  },
  {
    href: "/admin/teacher-invoicing/salary-grid",
    title: "Grille de salaire",
    description: "Periodes, regles par activite et gestion des tranches de remuneration.",
  },
];

export default async function AdminTeacherInvoicingHubPage(): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  return (
    <section className="admin-page-grid">
      <AdminTeacherInvoicingNav activeTab="hub" />

      <section className="grid cols-2 teacher-invoicing-hub-grid">
        {HUB_LINKS.map((entry) => (
          <article key={entry.href} className="card teacher-invoicing-hub-card">
            <h3>{entry.title}</h3>
            <p className="muted">{entry.description}</p>
            <div className="row top-gap-sm">
              <Link className="mode-link" href={entry.href}>
                Ouvrir
              </Link>
            </div>
          </article>
        ))}
      </section>
    </section>
  );
}
