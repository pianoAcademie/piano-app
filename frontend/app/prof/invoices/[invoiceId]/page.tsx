import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import {
  logoutAction,
  teacherCancelInvoiceAction,
  teacherSendInvoiceToAccountingAction,
  teacherUncancelInvoiceAction,
} from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import ActionCard from "../../../../components/teacher-ui/action-card";
import AlertCard from "../../../../components/teacher-ui/alert-card";
import BottomTabs from "../../../../components/teacher-ui/bottom-tabs";
import ListRow from "../../../../components/teacher-ui/list-row";
import PageHeaderMobile from "../../../../components/teacher-ui/page-header-mobile";
import SectionAccordion from "../../../../components/teacher-ui/section-accordion";
import StatChip from "../../../../components/teacher-ui/stat-chip";
import type { TeacherInvoiceOut } from "../../../../lib/types";

function profTabHref(tab: string): string {
  return `/prof?tab=${encodeURIComponent(tab)}`;
}

export default async function TeacherInvoiceDetailPage({
  params,
  searchParams,
}: {
  params: { invoiceId: string };
  searchParams: Record<string, string | string[] | undefined>;
}): Promise<JSX.Element> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  const invoiceId = params.invoiceId;
  const ok = Array.isArray(searchParams.ok) ? searchParams.ok[0] : (searchParams.ok ?? "");
  const error = Array.isArray(searchParams.error) ? searchParams.error[0] : (searchParams.error ?? "");

  const result = await backendRequest<TeacherInvoiceOut>(`/api/v1/teacher/invoices/${invoiceId}`, {}, token);
  if (!result.ok) {
    return <section className="flash-err">Erreur facture professeur: {result.message}</section>;
  }
  const invoice = result.data;

  return (
    <section className="page teacher-shell teacher-subpage">
      <PageHeaderMobile
        title={`Facture ${invoice.invoice_number}`}
        subtitle={`${invoice.payor_legal_entity_name} | ${invoice.invoice_date}`}
        trailing={
          <Link
            className="mode-link teacher-header-link"
            href={`/prof/statements?year=${invoice.invoice_date.slice(0, 4)}&month=${invoice.invoice_date.slice(5, 7)}`}
          >
            Retour releves
          </Link>
        }
        menu={
          <div className="teacher-header-menu-items">
            <Link className="teacher-header-menu-link" href="/prof">
              Accueil
            </Link>
            <form action={logoutAction}>
              <button className="ghost teacher-header-menu-btn" type="submit">
                Se deconnecter
              </button>
            </form>
          </div>
        }
      />

      <BottomTabs
        activeId="statements"
        items={[
          { id: "overview", label: "A traiter", icon: "📌", href: profTabHref("overview") },
          { id: "planning", label: "Planning", icon: "📅", href: profTabHref("planning") },
          { id: "statements", label: "Releves", icon: "🧾", href: "/prof/statements" },
          { id: "messages", label: "Messages", icon: "✉️", href: profTabHref("messages") },
          { id: "profile", label: "Profil", icon: "👤", href: profTabHref("profile") },
        ]}
      />

      {ok ? <AlertCard tone="ok">{ok}</AlertCard> : null}
      {error ? <AlertCard tone="error">{error}</AlertCard> : null}

      <ActionCard title="Actions facture" subtitle={`Echeance: ${invoice.due_date}`}>
        <div className="row teacher-actions-wrap">
          <a className="mode-link" href={`/api/v1/teacher/invoices/${invoice.id}/pdf`}>
            Telecharger PDF
          </a>
          <form action={teacherSendInvoiceToAccountingAction}>
            <input type="hidden" name="invoice_id" value={invoice.id} />
            <input type="hidden" name="return_to" value={`/prof/invoices/${invoice.id}`} />
            <button type="submit">Envoyer a la comptabilite</button>
          </form>
          {invoice.status === "cancelled" ? (
            <form action={teacherUncancelInvoiceAction}>
              <input type="hidden" name="invoice_id" value={invoice.id} />
              <input type="hidden" name="return_to" value={`/prof/invoices/${invoice.id}`} />
              <button type="submit">Reactiver</button>
            </form>
          ) : (
            <form action={teacherCancelInvoiceAction}>
              <input type="hidden" name="invoice_id" value={invoice.id} />
              <input type="hidden" name="return_to" value={`/prof/invoices/${invoice.id}`} />
              <button type="submit" className="danger">
                Annuler
              </button>
            </form>
          )}
        </div>
      </ActionCard>

      <ActionCard title="Synthese facture" subtitle="Informations legales et montants.">
        <div className="teacher-chip-row">
          <StatChip label="Statut" value={invoice.status} tone={invoice.status === "cancelled" ? "warn" : "ok"} />
          <StatChip label="HT" value={invoice.totals_ht} />
          <StatChip label="TVA" value={invoice.totals_vat} />
          <StatChip label="TTC" value={invoice.totals_ttc} tone="ok" />
        </div>
        <div className="list teacher-list-compact">
          <ListRow left="SIRET prof" right={invoice.teacher_siret_display} />
          <ListRow left="IBAN" right={invoice.teacher_iban} />
          <ListRow left="Date facture" right={invoice.invoice_date} />
          <ListRow left="Date echeance" right={invoice.due_date} />
        </div>
      </ActionCard>

      <SectionAccordion title="Lignes facture" defaultOpen={true}>
        <div className="list teacher-list-compact">
          {invoice.lines.map((line) => (
            <ListRow
              key={line.id}
              left={line.course_type_label}
              subtitle={`${line.hours} h | Taux HT ${line.unit_rate_ht} | HT ${line.amount_ht}`}
              right={line.amount_ttc}
            />
          ))}
        </div>
      </SectionAccordion>
    </section>
  );
}
