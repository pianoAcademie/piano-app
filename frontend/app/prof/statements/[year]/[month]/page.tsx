import Link from "next/link";
import { redirect } from "next/navigation";

import {
  logoutAction,
  teacherApproveStatementsOnlyAction,
  teacherDisputeSelectedLinesAction,
  teacherGenerateStatementsInvoiceAction,
  teacherReportMissingServiceAction,
} from "../../../../../lib/actions";
import { backendRequest } from "../../../../../lib/backend";
import { getPortalReturnTo, getPortalToken, readPortalImpersonationClaims } from "../../../../../lib/auth-cookies";
import AlertCard from "../../../../../components/teacher-ui/alert-card";
import BottomTabs from "../../../../../components/teacher-ui/bottom-tabs";
import PageHeaderMobile from "../../../../../components/teacher-ui/page-header-mobile";
import TeacherMissingServiceForm, { type MissingServiceActivityOption, type MissingServiceLocationOption } from "../../../../../components/teacher-missing-service-form";
import PortalImpersonationBanner from "../../../../../components/portal-impersonation-banner";
import type { CourseTypeOut, LocationOut, ProfessorContractGridOut, TeacherStatementOut } from "../../../../../lib/types";

type StatementServiceRow = {
  rowId: string;
  payorName: string;
  courseLabel: string;
  dateLabel: string;
  timeLabel: string;
  studentOrGroup: string;
  locationOrMode: string;
  durationMinutes: number;
  rateHt: string;
  amountHt: string;
  vat: string;
  totalTtc: string;
  currency: string;
};

const MONTH_LABELS = [
  "Janvier",
  "Fevrier",
  "Mars",
  "Avril",
  "Mai",
  "Juin",
  "Juillet",
  "Aout",
  "Septembre",
  "Octobre",
  "Novembre",
  "Decembre",
];

function profTabHref(tab: string): string {
  return `/prof?tab=${encodeURIComponent(tab)}`;
}

function readQueryParam(searchParams: Record<string, string | string[] | undefined>, key: string): string {
  const value = searchParams[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function toDateFr(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString("fr-FR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

function modeLabel(rawMode: string): string {
  const normalized = rawMode.trim().toUpperCase();
  if (normalized === "EN_LIGNE" || normalized === "ONLINE") {
    return "En ligne";
  }
  if (normalized === "PRESENTIEL" || normalized === "ONSITE") {
    return "Presentiel";
  }
  return "Tous modes";
}

function toTimeFr(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function safeNumber(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function safeMoney(value: unknown): string {
  const parsed = safeNumber(value, 0);
  return parsed.toFixed(2);
}

function statusLabel(rawStatus: string): string {
  const normalized = rawStatus.trim().toLowerCase();
  if (normalized === "to_verify" || normalized === "ready" || normalized === "draft") {
    return "A verifier";
  }
  if (normalized === "in_dispute" || normalized === "disputed") {
    return "En litige";
  }
  if (normalized === "awaiting_admin_feedback") {
    return "En attente retour administration";
  }
  if (normalized === "validated" || normalized === "approved") {
    return "Valide";
  }
  if (normalized === "invoice_generated" || normalized === "closed") {
    return "Facture generee";
  }
  if (normalized === "exported") {
    return "Exporte";
  }
  if (normalized === "awaiting_attendance") {
    return "Presences a renseigner";
  }
  return rawStatus;
}

function statusTone(rawStatus: string): string {
  const normalized = rawStatus.trim().toLowerCase();
  if (normalized === "in_dispute" || normalized === "disputed" || normalized === "awaiting_admin_feedback") {
    return "status-warn";
  }
  if (normalized === "validated" || normalized === "approved" || normalized === "invoice_generated" || normalized === "closed" || normalized === "exported") {
    return "status-ok";
  }
  return "status-off";
}

function flattenServices(statements: TeacherStatementOut[]): StatementServiceRow[] {
  const out: StatementServiceRow[] = [];
  for (const statement of statements) {
    for (const line of statement.lines) {
      const sessionItemsRaw = (line.meta as Record<string, unknown> | null)?.session_items;
      const sessionItems = Array.isArray(sessionItemsRaw) ? sessionItemsRaw : [];
      if (sessionItems.length > 0) {
        sessionItems.forEach((item, index) => {
          const record = (item ?? {}) as Record<string, unknown>;
          const startAt = String(record.start_at_utc ?? "").trim();
          const endAt = String(record.end_at_utc ?? "").trim();
          const dateLabel = String(record.date ?? "").trim() || (startAt ? toDateFr(startAt) : "-");
          const timeLabel = startAt && endAt ? `${toTimeFr(startAt)} - ${toTimeFr(endAt)}` : "-";
          const amountHt = safeMoney(record.amount_ht ?? line.amount_ht);
          const totalTtc = safeMoney(record.amount_ttc ?? line.amount_ttc);
          const vat = (safeNumber(totalTtc) - safeNumber(amountHt)).toFixed(2);
          const rowId = `${statement.payor_legal_entity_id}:${String(record.session_id ?? "line")}:${index}`;
          out.push({
            rowId,
            payorName: statement.payor_legal_entity_name,
            courseLabel: String(record.title ?? line.course_type_label),
            dateLabel,
            timeLabel,
            studentOrGroup: String(record.student_or_group ?? "").trim() || "-",
            locationOrMode: `${String(record.location_name ?? "-")}` + (record.modality ? ` / ${String(record.modality)}` : ""),
            durationMinutes: Math.max(1, safeNumber(record.duration_minutes, Math.round(safeNumber(line.hours, 0) * 60))),
            rateHt: safeMoney(record.unit_rate_ht ?? line.unit_rate_ht),
            amountHt,
            vat,
            totalTtc,
            currency: statement.currency,
          });
        });
      } else {
        const amountHt = safeMoney(line.amount_ht);
        const totalTtc = safeMoney(line.amount_ttc);
        out.push({
          rowId: `${statement.payor_legal_entity_id}:${line.course_type_id ?? line.course_type_label}`,
          payorName: statement.payor_legal_entity_name,
          courseLabel: line.course_type_label,
          dateLabel: "-",
          timeLabel: "-",
          studentOrGroup: "-",
          locationOrMode: "-",
          durationMinutes: Math.max(1, Math.round(safeNumber(line.hours, 0) * 60)),
          rateHt: safeMoney(line.unit_rate_ht),
          amountHt,
          vat: (safeNumber(totalTtc) - safeNumber(amountHt)).toFixed(2),
          totalTtc,
          currency: statement.currency,
        });
      }
    }
  }
  return out;
}

function formatPeriodRange(year: number, month: number): { start: string; end: string } {
  const start = new Date(Date.UTC(year, month - 1, 1));
  const end = new Date(Date.UTC(year, month, 0));
  return {
    start: start.toLocaleDateString("fr-FR"),
    end: end.toLocaleDateString("fr-FR"),
  };
}

function isValidatedForBilling(statuses: string[]): boolean {
  if (statuses.length === 0) {
    return false;
  }
  return statuses.every((status) => {
    const normalized = status.trim().toLowerCase();
    return normalized === "validated" || normalized === "approved" || normalized === "invoice_generated" || normalized === "closed" || normalized === "exported";
  });
}

export default async function TeacherStatementMonthDetailPage({
  params,
  searchParams,
}: {
  params: { year: string; month: string };
  searchParams: Record<string, string | string[] | undefined>;
}): Promise<JSX.Element> {
  const token = getPortalToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  const impersonationClaims = readPortalImpersonationClaims();
  const isImpersonating = Boolean(impersonationClaims?.imp);
  const impersonationReturnTo = getPortalReturnTo() ?? "/admin";
  const year = Number.parseInt(params.year, 10);
  const month = Number.parseInt(params.month, 10);
  if (!Number.isFinite(year) || !Number.isFinite(month)) {
    redirect("/prof/statements?error=Periode%20invalide");
  }

  const ok = Array.isArray(searchParams.ok) ? searchParams.ok[0] : (searchParams.ok ?? "");
  const error = Array.isArray(searchParams.error) ? searchParams.error[0] : (searchParams.error ?? "");
  const impersonationNameHint = Array.isArray(searchParams.imp_name) ? searchParams.imp_name[0] ?? "" : searchParams.imp_name ?? "";
  const backToRaw = readQueryParam(searchParams, "from").trim();
  const [statementsResult, courseTypesResult, locationsResult, contractGridsResult] = await Promise.all([
    backendRequest<TeacherStatementOut[]>(`/api/v1/teacher/statements/${year}/${month}`, {}, token),
    backendRequest<CourseTypeOut[]>("/api/v1/course-types?active=true", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=true", {}, token),
    backendRequest<ProfessorContractGridOut[]>("/api/v1/professors/me/contract-grids", {}, token),
  ]);
  const statements = statementsResult.ok ? statementsResult.data : [];

  const monthLabel = MONTH_LABELS[Math.max(1, Math.min(12, month)) - 1] ?? String(month);
  const impersonationDisplayName = impersonationNameHint.trim() || "Portail professeur";
  const period = formatPeriodRange(year, month);
  const services = flattenServices(statements);

  const totalServices = services.length;
  const totalMinutes = services.reduce((sum, row) => sum + row.durationMinutes, 0);
  const totalHours = (totalMinutes / 60).toFixed(2);
  const totalHt = statements.reduce((sum, row) => sum + safeNumber(row.totals_ht), 0).toFixed(2);
  const totalVat = statements.reduce((sum, row) => sum + safeNumber(row.totals_vat), 0).toFixed(2);
  const totalTtc = statements.reduce((sum, row) => sum + safeNumber(row.totals_ttc), 0).toFixed(2);
  const statusValues = statements.map((row) => row.status);
  const globalStatus = statusValues[0] ? statusLabel(statusValues[0]) : "A verifier";
  const globalStatusTone = statusValues[0] ? statusTone(statusValues[0]) : "status-off";
  const billingUnlocked = isValidatedForBilling(statusValues);
  const statementsMonthHref = `/prof/statements?year=${year}&month=${month}`;
  const safeBackHref = backToRaw.startsWith("/prof/statements") ? backToRaw : statementsMonthHref;
  const monthPath = `/prof/statements/${year}/${month}`;
  const monthPathWithContext = `${monthPath}?from=${encodeURIComponent(safeBackHref)}`;
  const disputePanelHref = "#statement-dispute-modal";
  const missingPanelHref = "#statement-missing-modal";
  const fallbackCurrency = statements[0]?.currency || "EUR";

  const gridLineByCourseTypeId = new Map<string, ProfessorContractGridOut["lines"][number]>();
  if (contractGridsResult.ok) {
    for (const grid of contractGridsResult.data) {
      for (const line of grid.lines) {
        if (!line.course_type_id || gridLineByCourseTypeId.has(line.course_type_id)) {
          continue;
        }
        gridLineByCourseTypeId.set(line.course_type_id, line);
      }
    }
  }

  const activitiesMap = new Map<string, MissingServiceActivityOption>();
  if (courseTypesResult.ok && courseTypesResult.data.length > 0) {
    const restrictToProfessorActivities = gridLineByCourseTypeId.size > 0;
    for (const courseType of courseTypesResult.data) {
      if (restrictToProfessorActivities && !gridLineByCourseTypeId.has(courseType.id)) {
        continue;
      }
      const line = gridLineByCourseTypeId.get(courseType.id);
      activitiesMap.set(courseType.id, {
        id: courseType.id,
        label: (line?.course_type_name || courseType.name || "").trim() || "Prestation",
        duration_minutes: Number(line?.reference_duration_minutes ?? courseType.duration_minutes ?? 60) || 60,
        mode_label: modeLabel(line?.mode ?? courseType.mode),
        default_hourly_rate: line?.default_hourly_rate ?? courseType.default_hourly_rate,
        rules: line?.rules ?? [],
      });
    }
  }

  if (activitiesMap.size === 0 && contractGridsResult.ok) {
    for (const grid of contractGridsResult.data) {
      for (const line of grid.lines) {
        if (!line.course_type_id || activitiesMap.has(line.course_type_id)) {
          continue;
        }
        activitiesMap.set(line.course_type_id, {
          id: line.course_type_id,
          label: (line.course_type_name || line.service_type || "").trim() || "Prestation",
          duration_minutes: Number(line.reference_duration_minutes ?? 60) || 60,
          mode_label: modeLabel(line.mode),
          default_hourly_rate: line.default_hourly_rate,
          rules: line.rules,
        });
      }
    }
  }

  const missingServiceActivities = Array.from(activitiesMap.values()).sort((a, b) => a.label.localeCompare(b.label, "fr"));
  const missingServiceLocations: MissingServiceLocationOption[] = locationsResult.ok
    ? locationsResult.data.map((location) => ({ id: location.id, label: location.name }))
    : [];
  const defaultMissingServiceDate = new Date().toISOString().slice(0, 10);

  return (
    <section className="page teacher-shell teacher-subpage">
      <PageHeaderMobile
        title="Releve de prestations"
        subtitle={`${monthLabel} ${year}`}
        trailing={
          <Link className="mode-link teacher-header-link" href={safeBackHref}>
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
        <Link className="prof-nav-link active" href={safeBackHref}>
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

      {ok ? <AlertCard tone="ok">{ok}</AlertCard> : null}
      {error ? <AlertCard tone="error">{error}</AlertCard> : null}
      {!statementsResult.ok ? <AlertCard tone="error">Erreur releve detail: {statementsResult.message}</AlertCard> : null}
      {!courseTypesResult.ok ? <AlertCard tone="error">Erreur prestations: {courseTypesResult.message}</AlertCard> : null}
      {!locationsResult.ok ? <AlertCard tone="error">Erreur lieux: {locationsResult.message}</AlertCard> : null}
      {!contractGridsResult.ok ? <AlertCard tone="error">Erreur grille contractuelle: {contractGridsResult.message}</AlertCard> : null}

      <article className="card statement-period-hero">
        <p className="statement-title">Releve de prestations</p>
        <p className="statement-period-strong">Periode du {period.start} au {period.end}</p>
        <span className={`status-pill ${globalStatusTone}`}>{globalStatus}</span>
      </article>

      <article className="card statement-summary-card">
        <h3>Resume financier</h3>
        <div className="statement-summary-grid">
          <div>
            <small className="muted">Nombre de prestations</small>
            <strong>{totalServices}</strong>
          </div>
          <div>
            <small className="muted">Total heures</small>
            <strong>{totalHours} h</strong>
          </div>
          <div>
            <small className="muted">Total HT</small>
            <strong>{totalHt} EUR</strong>
          </div>
          <div>
            <small className="muted">TVA</small>
            <strong>{totalVat} EUR</strong>
          </div>
          <div>
            <small className="muted">Total TTC</small>
            <strong>{totalTtc} EUR</strong>
          </div>
        </div>
      </article>

      <article className="card">
        <div className="row spread statement-list-head">
          <h3>
            Prestations du releve
            <span className="badge statement-list-count">{services.length}</span>
          </h3>
          <small className="muted">Cochez les lignes a signaler.</small>
        </div>
        {services.length === 0 ? (
          <p className="muted">Aucune prestation detaillee sur cette periode.</p>
        ) : (
          <div className="statement-service-list">
            {services.map((row, index) => {
              const checkboxId = `statement-line-${index}`;
              const lineLabel = `${row.payorName} | ${row.courseLabel} | ${row.dateLabel} ${row.timeLabel}`;
              return (
                <article key={row.rowId} className="statement-service-card">
                  <div className="statement-service-head">
                    <label className="statement-line-check" htmlFor={checkboxId}>
                      <input id={checkboxId} type="checkbox" name="selected_lines" value={lineLabel} form="statement-dispute-form" />
                      <span className="statement-line-check-text">
                        <strong>{row.courseLabel}</strong>
                        <small>{row.dateLabel} · {row.timeLabel}</small>
                      </span>
                    </label>
                    <span className="badge statement-payor-badge">{row.payorName}</span>
                  </div>
                  <div className="statement-service-context">
                    {row.studentOrGroup !== "-" ? <span>{row.studentOrGroup}</span> : null}
                    {row.locationOrMode !== "-" ? <span>{row.locationOrMode}</span> : null}
                  </div>
                  <div className="statement-service-grid">
                    <small>Duree: <strong>{row.durationMinutes} min</strong></small>
                    <small>Taux HT: <strong>{row.rateHt} EUR</strong></small>
                    <small>HT: <strong>{row.amountHt} EUR</strong></small>
                    <small>TVA: <strong>{row.vat} EUR</strong></small>
                    <small>TTC: <strong>{row.totalTtc} EUR</strong></small>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </article>

      <article className="card statement-action-block">
        <h3>Signaler un probleme sur lignes existantes</h3>
        <p className="muted">Selectionnez une ou plusieurs lignes puis ouvrez le parcours dedie pour envoyer un commentaire a l administration.</p>
        <a className="mode-link" href={disputePanelHref}>
          Signaler un probleme sur les lignes selectionnees
        </a>
      </article>

      <article className="card statement-action-block">
        <h3>Ajouter une prestation manquante</h3>
        <p className="muted">Parcours distinct pour signaler une prestation effectuee mais absente du releve.</p>
        <a className="mode-link" href={missingPanelHref}>
          Ajouter une prestation manquante
        </a>
      </article>

      <article className="card statement-validation-block">
        <h3>Validation et facture</h3>
        <p className="muted">Validez d abord le releve, puis choisissez votre mode de facturation.</p>
        <div className="statement-validation-actions">
          <form action={teacherApproveStatementsOnlyAction}>
            <input type="hidden" name="year" value={year} />
            <input type="hidden" name="month" value={month} />
            <input type="hidden" name="return_to" value={monthPathWithContext} />
            <button type="submit">Approuver le releve</button>
          </form>

          {billingUnlocked ? (
            <div className="statement-billing-options">
              <form action={teacherGenerateStatementsInvoiceAction}>
                <input type="hidden" name="year" value={year} />
                <input type="hidden" name="month" value={month} />
                <input type="hidden" name="return_to" value={monthPathWithContext} />
                <button type="submit" className="ghost">Generer ma facture (modele Piano Academie)</button>
              </form>
              <a className="mode-link" href={`/prof/statements/${year}/${month}/export`}>
                Exporter les prestations (modele personnel)
              </a>
            </div>
          ) : (
            <p className="muted">Les options de facturation seront disponibles apres approbation du releve.</p>
          )}
        </div>
      </article>

      <section id="statement-dispute-modal" className="modal-overlay statement-target-modal">
        <article className="modal-panel modal-compact">
          <a className="close-link" href="#" aria-label="Fermer le signalement">
            ✕
          </a>
          <h3>Signaler un probleme sur les lignes selectionnees</h3>
          <p className="muted">Les lignes cochees dans le releve seront jointes a votre signalement.</p>
          <form id="statement-dispute-form" action={teacherDisputeSelectedLinesAction} className="grid top-gap-sm">
            <input type="hidden" name="year" value={year} />
            <input type="hidden" name="month" value={month} />
            <input type="hidden" name="return_to" value={monthPathWithContext} />
            <label>
              Commentaire (obligatoire)
              <textarea
                name="message"
                required
                minLength={5}
                maxLength={4000}
                rows={5}
                placeholder="Expliquez le probleme constate sur les prestations selectionnees"
              />
            </label>
            <button type="submit" className="ghost">Envoyer a l administration</button>
          </form>
        </article>
      </section>

      <section id="statement-missing-modal" className="modal-overlay statement-target-modal">
        <article className="modal-panel modal-compact">
          <a className="close-link" href="#" aria-label="Fermer la prestation manquante">
            ✕
          </a>
          <h3>Ajouter une prestation manquante</h3>
          <TeacherMissingServiceForm
            action={teacherReportMissingServiceAction}
            year={year}
            month={month}
            returnTo={monthPathWithContext}
            defaultDate={defaultMissingServiceDate}
            currency={fallbackCurrency}
            activities={missingServiceActivities}
            locations={missingServiceLocations}
          />
        </article>
      </section>
    </section>
  );
}
