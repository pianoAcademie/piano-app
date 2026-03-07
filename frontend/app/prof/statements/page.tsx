import Link from "next/link";
import { redirect } from "next/navigation";

import {
  logoutAction,
  teacherApproveStatementsAction,
  teacherCancelInvoiceAction,
  teacherDisputeStatementsAction,
  teacherSendInvoiceToAccountingAction,
  teacherUncancelInvoiceAction,
} from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import ActionCard from "../../../components/teacher-ui/action-card";
import AlertCard from "../../../components/teacher-ui/alert-card";
import BottomTabs from "../../../components/teacher-ui/bottom-tabs";
import ListRow from "../../../components/teacher-ui/list-row";
import PageHeaderMobile from "../../../components/teacher-ui/page-header-mobile";
import PortalImpersonationBanner from "../../../components/portal-impersonation-banner";
import SectionAccordion from "../../../components/teacher-ui/section-accordion";
import StatChip from "../../../components/teacher-ui/stat-chip";
import { getPortalReturnTo, getPortalToken, readPortalImpersonationClaims } from "../../../lib/auth-cookies";
import type { TeacherInvoiceOut, TeacherStatementOut } from "../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

const MONTH_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 1, label: "Janvier" },
  { value: 2, label: "Fevrier" },
  { value: 3, label: "Mars" },
  { value: 4, label: "Avril" },
  { value: 5, label: "Mai" },
  { value: 6, label: "Juin" },
  { value: 7, label: "Juillet" },
  { value: 8, label: "Aout" },
  { value: 9, label: "Septembre" },
  { value: 10, label: "Octobre" },
  { value: 11, label: "Novembre" },
  { value: 12, label: "Decembre" },
];

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function profTabHref(tab: string): string {
  return `/prof?tab=${encodeURIComponent(tab)}`;
}

function isPastOrStarted(isoValue: string): boolean {
  const parsed = new Date(isoValue);
  if (Number.isNaN(parsed.getTime())) {
    return false;
  }
  return parsed.getTime() <= Date.now();
}

export default async function TeacherStatementsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}): Promise<JSX.Element> {
  const token = getPortalToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  const impersonationClaims = readPortalImpersonationClaims();
  const isImpersonating = Boolean(impersonationClaims?.imp);
  const impersonationReturnTo = getPortalReturnTo() ?? "/admin";
  const impersonationNameHint = readParam(searchParams, "imp_name").trim();
  const now = new Date();
  const year = Number.parseInt(readParam(searchParams, "year"), 10) || now.getUTCFullYear();
  const parsedMonth = Number.parseInt(readParam(searchParams, "month"), 10);
  const month = Number.isFinite(parsedMonth) && parsedMonth >= 1 && parsedMonth <= 12 ? parsedMonth : now.getUTCMonth() + 1;
  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");
  const monthLabel = MONTH_OPTIONS.find((option) => option.value === month)?.label ?? String(month);
  const statementsMonthHref = `/prof/statements?year=${year}&month=${month}`;

  const [statementsResult, invoicesResult] = await Promise.all([
    backendRequest<TeacherStatementOut[]>(`/api/v1/teacher/statements?year=${year}&month=${month}`, {}, token),
    backendRequest<TeacherInvoiceOut[]>(`/api/v1/teacher/invoices?year=${year}&month=${month}`, {}, token),
  ]);
  const statements = statementsResult.ok ? statementsResult.data : [];
  const invoices = invoicesResult.ok ? invoicesResult.data : [];
  const impersonationDisplayName =
    impersonationNameHint
    || "Portail professeur";
  const invoicesByPayor = new Map<string, TeacherInvoiceOut[]>();
  for (const invoice of invoices) {
    const bucket = invoicesByPayor.get(invoice.payor_legal_entity_id) ?? [];
    bucket.push(invoice);
    invoicesByPayor.set(invoice.payor_legal_entity_id, bucket);
  }

  return (
    <section className="page teacher-shell teacher-subpage">
      <PageHeaderMobile
        title="Releves mensuels"
        subtitle={`${monthLabel} ${year}`}
        trailing={
          <Link className="mode-link teacher-header-link" href="/prof">
            Retour accueil
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

      <section className="card prof-nav teacher-desktop-nav" aria-label="Navigation professeur">
        <Link className="prof-nav-link" href={profTabHref("overview")}>
          <span aria-hidden>🗂</span>
          A traiter
        </Link>
        <Link className="prof-nav-link" href={profTabHref("planning")}>
          <span aria-hidden>📅</span>
          Planning
        </Link>
        <Link className="prof-nav-link" href={profTabHref("catalog")}>
          <span aria-hidden>📦</span>
          Produits
        </Link>
        <Link className="prof-nav-link" href={profTabHref("finance")}>
          <span aria-hidden>💶</span>
          Solde
        </Link>
        <Link className="prof-nav-link active" href={statementsMonthHref}>
          <span aria-hidden>🧾</span>
          Releves
        </Link>
      </section>

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

      {isImpersonating ? (
        <PortalImpersonationBanner displayName={impersonationDisplayName} returnTo={impersonationReturnTo} />
      ) : null}

      <article className="card teacher-filter-card">
        <form method="get" className="grid teacher-filter-form">
          <label>
            Annee
            <input type="number" name="year" min={2000} max={2100} defaultValue={year} />
          </label>
          <label>
            Mois
            <select name="month" defaultValue={month}>
              {MONTH_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <div className="teacher-filter-submit">
            <button type="submit">Afficher</button>
          </div>
        </form>
      </article>

      {ok ? <AlertCard tone="ok">{ok}</AlertCard> : null}
      {error ? <AlertCard tone="error">{error}</AlertCard> : null}
      {!statementsResult.ok ? <AlertCard tone="error">Erreur releves: {statementsResult.message}</AlertCard> : null}
      {!invoicesResult.ok ? <AlertCard tone="error">Erreur factures prof: {invoicesResult.message}</AlertCard> : null}

      <ActionCard title="Actions" subtitle="Validation ou litige pour la periode selectionnee.">
        <div className="row teacher-actions-wrap">
          <form action={teacherApproveStatementsAction}>
            <input type="hidden" name="year" value={year} />
            <input type="hidden" name="month" value={month} />
            <input type="hidden" name="return_to" value={statementsMonthHref} />
            <button type="submit">Approuver et generer</button>
          </form>
          <form action={teacherDisputeStatementsAction} className="teacher-dispute-form">
            <input type="hidden" name="year" value={year} />
            <input type="hidden" name="month" value={month} />
            <input type="hidden" name="return_to" value={statementsMonthHref} />
            <input type="text" name="message" placeholder="Motif de litige" required />
            <button type="submit" className="ghost">
              Signaler litige
            </button>
          </form>
        </div>
      </ActionCard>

      {statements.length === 0 ? (
        <AlertCard tone="warn">Aucun releve trouve pour cette periode.</AlertCard>
      ) : (
        <div className="grid teacher-entity-grid">
          {statements.map((statement) => {
            const pendingMissingSessions = statement.missing_sessions.filter((row) => isPastOrStarted(row.start_at_utc));
            const hasPendingPastAttendance = pendingMissingSessions.length > 0;
            return (
            <article key={`${statement.payor_legal_entity_id}-${statement.year}-${statement.month}`} className="card">
              <div className="row spread">
                <strong>{statement.payor_legal_entity_name}</strong>
                <span className={`status-pill ${hasPendingPastAttendance ? "status-warn" : "status-ok"}`}>
                  {hasPendingPastAttendance ? "Presences a renseigner" : statement.status}
                </span>
              </div>

              <div className="teacher-chip-row">
                <StatChip label="HT" value={`${statement.totals_ht} ${statement.currency}`} />
                <StatChip label="TVA" value={`${statement.totals_vat} ${statement.currency}`} />
                <StatChip label="TTC" value={`${statement.totals_ttc} ${statement.currency}`} tone="ok" />
              </div>

              {hasPendingPastAttendance ? (
                <SectionAccordion
                  title="Presences a renseigner"
                  subtitle="Seances a completer avant approbation"
                  badge={<span className="status-pill status-warn">{pendingMissingSessions.length}</span>}
                >
                  <div className="list teacher-list-compact">
                    {pendingMissingSessions.map((missing) => (
                      <ListRow
                        key={missing.session_id}
                        left={missing.title}
                        subtitle={`${new Date(missing.start_at_utc).toLocaleString("fr-FR")} | ${missing.pending_students_count}/${missing.total_students_count}`}
                      />
                    ))}
                  </div>
                </SectionAccordion>
              ) : null}

              <div className="row top-gap-sm">
                <Link className="mode-link" href={`/prof/statements/${year}/${month}?from=${encodeURIComponent(statementsMonthHref)}`}>
                  Voir detail
                </Link>
              </div>

              {(invoicesByPayor.get(statement.payor_legal_entity_id) ?? []).map((invoice) => (
                <article key={invoice.id} className="item teacher-invoice-card">
                  <div className="row spread">
                    <strong>{invoice.invoice_number}</strong>
                    <span className={`status-pill ${invoice.status === "cancelled" ? "status-off" : "status-ok"}`}>
                      {invoice.status}
                    </span>
                  </div>
                  <p className="muted">
                    {invoice.totals_ttc} EUR | echeance {invoice.due_date}
                  </p>
                  <div className="row teacher-actions-wrap">
                    <Link className="reset-link" href={`/api/v1/teacher/invoices/${invoice.id}/pdf`}>
                      PDF
                    </Link>
                    <Link className="reset-link" href={`/prof/invoices/${invoice.id}`}>
                      Ouvrir
                    </Link>
                    <form action={teacherSendInvoiceToAccountingAction}>
                      <input type="hidden" name="invoice_id" value={invoice.id} />
                      <input type="hidden" name="return_to" value={statementsMonthHref} />
                      <button type="submit" className="ghost">
                        Envoyer compta
                      </button>
                    </form>
                    {invoice.status === "cancelled" ? (
                      <form action={teacherUncancelInvoiceAction}>
                        <input type="hidden" name="invoice_id" value={invoice.id} />
                        <input type="hidden" name="return_to" value={statementsMonthHref} />
                        <button type="submit">Reactiver</button>
                      </form>
                    ) : (
                      <form action={teacherCancelInvoiceAction}>
                        <input type="hidden" name="invoice_id" value={invoice.id} />
                        <input type="hidden" name="return_to" value={statementsMonthHref} />
                        <button type="submit" className="danger">
                          Annuler
                        </button>
                      </form>
                    )}
                  </div>
                </article>
              ))}
            </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
