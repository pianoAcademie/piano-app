import Link from "next/link";
import { redirect } from "next/navigation";

import {
  logoutAction,
  teacherApproveStatementsOnlyAction,
  teacherDisputeSelectedLinesAction,
  teacherGenerateStatementsInvoiceAction,
  teacherReportMissingServiceAction,
  teacherSendExternalInvoiceAction,
  teacherSendInvoiceToAccountingAction,
} from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import { getPortalReturnTo, getProfessorPortalToken, readPortalImpersonationClaims } from "../../../lib/auth-cookies";
import { buildProfessorHelpLabels } from "../../../lib/professor-help-labels";
import AlertCard from "../../../components/teacher-ui/alert-card";
import BottomTabs from "../../../components/teacher-ui/bottom-tabs";
import ProfessorHelpAssistant from "../../../components/teacher-ui/help-assistant";
import PageHeaderMobile from "../../../components/teacher-ui/page-header-mobile";
import TeacherMissingServiceForm, { type MissingServiceActivityOption, type MissingServiceLocationOption } from "../../../components/teacher-missing-service-form";
import PortalImpersonationBanner from "../../../components/portal-impersonation-banner";
import type { CourseTypeOut, LocationOut, ProfessorContractGridOut, TeacherInvoiceOut, TeacherStatementOut, UserOut } from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

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
  attendance: Array<{
    studentName: string;
    status: string;
  }>;
};

function profTabHref(tab: string): string {
  return `/prof?tab=${encodeURIComponent(tab)}`;
}

function readQueryParam(searchParams: SearchParams, key: string): string {
  const value = searchParams[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatDateLabel(value: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString(localeForUiLanguage(language), {
    timeZone: "Europe/Paris",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

function formatTimeLabel(value: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleTimeString(localeForUiLanguage(language), {
    timeZone: "Europe/Paris",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function attendanceLabel(rawStatus: string, language: UiLanguage): string {
  const normalized = rawStatus.trim().toUpperCase();
  if (normalized === "ATTENDED") return uiText(language, "teacher.attendance_attended");
  if (normalized === "NO_SHOW") return uiText(language, "teacher.attendance_no_show");
  if (normalized === "EXCUSED_ABSENCE") return uiText(language, "teacher.attendance_excused_absence");
  if (normalized === "BOOKED") return uiText(language, "teacher.attendance_booked");
  return rawStatus || "-";
}

function attendanceTone(rawStatus: string): string {
  const normalized = rawStatus.trim().toUpperCase();
  if (normalized === "ATTENDED") return "status-ok";
  if (normalized === "BOOKED") return "status-warn";
  if (normalized === "NO_SHOW") return "status-error";
  return "status-off";
}

function safeNumber(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function safeMoney(value: unknown): string {
  const parsed = safeNumber(value, 0);
  return parsed.toFixed(2);
}

function statusLabel(rawStatus: string, language: UiLanguage): string {
  const normalized = rawStatus.trim().toLowerCase();
  if (normalized === "to_verify" || normalized === "ready" || normalized === "draft") {
    return uiText(language, "teacher.statement_status_to_verify");
  }
  if (normalized === "in_dispute" || normalized === "disputed") {
    return uiText(language, "teacher.statement_status_in_dispute");
  }
  if (normalized === "awaiting_admin_feedback") {
    return uiText(language, "teacher.statement_status_awaiting_admin_feedback");
  }
  if (normalized === "validated" || normalized === "approved") {
    return uiText(language, "teacher.statement_status_validated");
  }
  if (normalized === "invoice_generated" || normalized === "closed") {
    return uiText(language, "teacher.statement_status_invoice_generated");
  }
  if (normalized === "exported") {
    return uiText(language, "teacher.statement_status_exported");
  }
  if (normalized === "awaiting_attendance") {
    return uiText(language, "teacher.statement_status_attendance_pending");
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

function modeLabel(rawMode: string, language: UiLanguage): string {
  const normalized = rawMode.trim().toUpperCase();
  if (normalized === "EN_LIGNE" || normalized === "ONLINE") {
    return uiText(language, "teacher.mode_online");
  }
  if (normalized === "PRESENTIEL" || normalized === "ONSITE") {
    return uiText(language, "teacher.mode_onsite");
  }
  return uiText(language, "teacher.mode_all");
}

function flattenServices(statements: TeacherStatementOut[], language: UiLanguage): StatementServiceRow[] {
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
          const dateLabel = String(record.date ?? "").trim() || (startAt ? formatDateLabel(startAt, language) : "-");
          const timeLabel = startAt && endAt ? `${formatTimeLabel(startAt, language)} - ${formatTimeLabel(endAt, language)}` : "-";
          const amountHt = safeMoney(record.amount_ht ?? line.amount_ht);
          const totalTtc = safeMoney(record.amount_ttc ?? line.amount_ttc);
          const vat = (safeNumber(totalTtc) - safeNumber(amountHt)).toFixed(2);
          const rowId = `${statement.payor_legal_entity_id}:${String(record.session_id ?? "line")}:${index}`;
          const rawModality = String(record.modality ?? "").trim();
          const localizedModality = rawModality ? modeLabel(rawModality, language) : "";
          const rawAttendance = Array.isArray(record.attendance) ? record.attendance : [];
          out.push({
            rowId,
            payorName: statement.payor_legal_entity_name,
            courseLabel: String(record.title ?? line.course_type_label),
            dateLabel,
            timeLabel,
            studentOrGroup: String(record.student_or_group ?? "").trim() || "-",
            locationOrMode: `${String(record.location_name ?? "-")}` + (localizedModality ? ` / ${localizedModality}` : ""),
            durationMinutes: Math.max(1, safeNumber(record.duration_minutes, Math.round(safeNumber(line.hours, 0) * 60))),
            rateHt: safeMoney(record.unit_rate_ht ?? line.unit_rate_ht),
            amountHt,
            vat,
            totalTtc,
            attendance: rawAttendance
              .map((rawRow) => {
                const attendanceRow = (rawRow ?? {}) as Record<string, unknown>;
                return {
                  studentName: String(attendanceRow.student_name ?? "-").trim() || "-",
                  status: String(attendanceRow.status ?? "").trim(),
                };
              })
              .sort((a, b) => a.studentName.localeCompare(b.studentName, localeForUiLanguage(language))),
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
          attendance: [],
        });
      }
    }
  }
  return out;
}

function formatPeriodRange(year: number, month: number, language: UiLanguage): { start: string; end: string } {
  const start = new Date(Date.UTC(year, month - 1, 1));
  const end = new Date(Date.UTC(year, month, 0));
  const locale = localeForUiLanguage(language);
  return {
    start: start.toLocaleDateString(locale),
    end: end.toLocaleDateString(locale),
  };
}

function formatMonthLabel(year: number, month: number, language: UiLanguage): string {
  const label = new Intl.DateTimeFormat(localeForUiLanguage(language), {
    month: "long",
  }).format(new Date(Date.UTC(year, month - 1, 1)));
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function invoiceStatusLabel(rawStatus: string, language: UiLanguage): string {
  const normalized = rawStatus.trim().toLowerCase();
  if (normalized === "sent_to_accounting") {
    return uiText(language, "teacher.invoice_status_sent_to_accounting");
  }
  if (normalized === "cancelled") {
    return uiText(language, "teacher.invoice_status_cancelled");
  }
  if (normalized === "generated") {
    return uiText(language, "teacher.invoice_status_generated");
  }
  return rawStatus;
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

function computeAdjacentMonths(year: number, month: number): {
  prevYear: number;
  prevMonth: number;
  nextYear: number;
  nextMonth: number;
} {
  const prevMonth = month === 1 ? 12 : month - 1;
  const prevYear = month === 1 ? year - 1 : year;
  const nextMonth = month === 12 ? 1 : month + 1;
  const nextYear = month === 12 ? year + 1 : year;
  return { prevYear, prevMonth, nextYear, nextMonth };
}

export default async function TeacherStatementsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}): Promise<JSX.Element> {
  const token = getProfessorPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const now = new Date();
  const year = Number.parseInt(readQueryParam(searchParams, "year"), 10) || now.getUTCFullYear();
  const parsedMonth = Number.parseInt(readQueryParam(searchParams, "month"), 10);
  const month = Number.isFinite(parsedMonth) && parsedMonth >= 1 && parsedMonth <= 12 ? parsedMonth : now.getUTCMonth() + 1;

  const ok = readQueryParam(searchParams, "ok");
  const error = readQueryParam(searchParams, "error");
  const notice = readQueryParam(searchParams, "notice").trim().toLowerCase();
  const impersonationNameHint = readQueryParam(searchParams, "imp_name").trim();

  const [
    meResult,
    statementsResult,
    courseTypesResult,
    locationsResult,
    contractGridsResult,
    invoicesResult,
  ] = await Promise.all([
    backendRequest<UserOut>("/api/v1/auth/me", {}, token),
    backendRequest<TeacherStatementOut[]>(`/api/v1/teacher/statements/${year}/${month}`, {}, token),
    backendRequest<CourseTypeOut[]>("/api/v1/course-types?active=true", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=true", {}, token),
    backendRequest<ProfessorContractGridOut[]>("/api/v1/professors/me/contract-grids", {}, token),
    backendRequest<TeacherInvoiceOut[]>(`/api/v1/teacher/invoices?year=${year}&month=${month}`, {}, token),
  ]);

  const language = normalizeUiLanguage(meResult.ok ? meResult.data.preferred_language : "fr");
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const locale = localeForUiLanguage(language);

  const statements = statementsResult.ok ? statementsResult.data : [];
  const monthLabel = formatMonthLabel(year, month, language);
  const period = formatPeriodRange(year, month, language);
  const services = flattenServices(statements, language);

  const totalServices = services.length;
  const totalMinutes = services.reduce((sum, row) => sum + row.durationMinutes, 0);
  const totalHours = (totalMinutes / 60).toFixed(2);
  const totalHt = statements.reduce((sum, row) => sum + safeNumber(row.totals_ht), 0).toFixed(2);
  const totalVat = statements.reduce((sum, row) => sum + safeNumber(row.totals_vat), 0).toFixed(2);
  const totalTtc = statements.reduce((sum, row) => sum + safeNumber(row.totals_ttc), 0).toFixed(2);
  const vatApplicable = statements.some((row) => row.vat_applicable);
  const totalPayable = vatApplicable ? totalTtc : totalHt;
  const statusValues = statements.map((row) => row.status);
  const globalStatus = statusValues[0] ? statusLabel(statusValues[0], language) : t("teacher.statement_status_to_verify");
  const globalStatusTone = statusValues[0] ? statusTone(statusValues[0]) : "status-off";
  const billingUnlocked = isValidatedForBilling(statusValues);
  const attendanceComplete = statements.length > 0 && statements.every((statement) => statement.attendance_complete);

  const impersonationClaims = readPortalImpersonationClaims();
  const isImpersonating = Boolean(impersonationClaims?.imp);
  const impersonationReturnTo = getPortalReturnTo() ?? "/admin";
  const impersonationDisplayName = impersonationNameHint || t("portal.teacher");

  const statementsMonthHref = `/prof/statements?year=${year}&month=${month}`;
  const { prevYear, prevMonth, nextYear, nextMonth } = computeAdjacentMonths(year, month);
  const previousMonthHref = `/prof/statements?year=${prevYear}&month=${prevMonth}`;
  const nextMonthHref = `/prof/statements?year=${nextYear}&month=${nextMonth}`;

  const disputePanelHref = "#statement-dispute-modal";
  const missingPanelHref = "#statement-missing-modal";
  const fallbackCurrency = statements[0]?.currency || "EUR";
  const successMessage = notice === "missing_service_sent"
    ? t("teacher.statement_missing_service_success")
    : notice === "dispute_sent"
      ? t("teacher.statement_dispute_success")
      : "";
  const showSuccessModal = successMessage.length > 0;
  const monthInvoices = invoicesResult.ok ? invoicesResult.data : [];
  const externalPayorOptions = statements.map((statement) => ({
    id: statement.payor_legal_entity_id,
    label: statement.payor_legal_entity_name,
  }));

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
          label: (line?.course_type_name || courseType.name || "").trim() || t("teacher.service_type"),
          duration_minutes: Number(line?.reference_duration_minutes ?? courseType.duration_minutes ?? 60) || 60,
          mode_label: modeLabel(line?.mode ?? courseType.mode, language),
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
          label: (line.course_type_name || line.service_type || "").trim() || t("teacher.service_type"),
          duration_minutes: Number(line.reference_duration_minutes ?? 60) || 60,
          mode_label: modeLabel(line.mode, language),
          default_hourly_rate: line.default_hourly_rate,
          rules: line.rules,
        });
      }
    }
  }

  const missingServiceActivities = Array.from(activitiesMap.values()).sort((a, b) => a.label.localeCompare(b.label, locale));
  const missingServiceLocations: MissingServiceLocationOption[] = locationsResult.ok
    ? locationsResult.data.map((location) => ({ id: location.id, label: location.name }))
    : [];
  const defaultMissingServiceDate = new Date().toISOString().slice(0, 10);

  return (
    <section className="page teacher-shell teacher-subpage">
      <PageHeaderMobile
        title={t("teacher.statements")}
        subtitle={`${monthLabel} ${year}`}
        trailing={
          <Link className="mode-link teacher-header-link" href="/prof">
            {t("teacher.return_home")}
          </Link>
        }
        menuLabel={t("portal.teacher_menu")}
        menu={
          <div className="teacher-header-menu-items">
            <Link className="teacher-header-menu-link" href="/prof">
              {t("common.home")}
            </Link>
            <form action={logoutAction}>
              <button className="ghost teacher-header-menu-btn" type="submit">
                {t("common.logout")}
              </button>
            </form>
          </div>
        }
      />

      <section className="card prof-nav teacher-desktop-nav" aria-label={t("teacher.navigation")}>
        <Link className="prof-nav-link" href={profTabHref("overview")}>
          <span aria-hidden>🗂</span>
          {t("teacher.todo")}
        </Link>
        <Link className="prof-nav-link" href={profTabHref("planning")}>
          <span aria-hidden>📅</span>
          {t("teacher.planning")}
        </Link>
        <Link className="prof-nav-link" href={profTabHref("catalog")}>
          <span aria-hidden>📦</span>
          {t("teacher.products")}
        </Link>
        <Link className="prof-nav-link" href={profTabHref("finance")}>
          <span aria-hidden>💶</span>
          {t("teacher.balance")}
        </Link>
        <Link className="prof-nav-link active" href={statementsMonthHref}>
          <span aria-hidden>🧾</span>
          {t("teacher.statements")}
        </Link>
      </section>

      <BottomTabs
        activeId="statements"
        ariaLabel={t("portal.mobile_teacher_nav")}
        items={[
          { id: "overview", label: t("teacher.todo"), icon: "📌", href: profTabHref("overview") },
          { id: "planning", label: t("teacher.planning"), icon: "📅", href: profTabHref("planning") },
          { id: "statements", label: t("teacher.statements"), icon: "🧾", href: statementsMonthHref },
          { id: "messages", label: t("teacher.messages"), icon: "✉️", href: profTabHref("messages") },
          { id: "profile", label: t("teacher.profile"), icon: "👤", href: profTabHref("profile") },
        ]}
      />

      {isImpersonating ? (
        <PortalImpersonationBanner displayName={impersonationDisplayName} returnTo={impersonationReturnTo} language={language} />
      ) : null}

      {ok && !successMessage ? <AlertCard tone="ok">{ok}</AlertCard> : null}
      {error ? <AlertCard tone="error">{error}</AlertCard> : null}
      {!statementsResult.ok ? <AlertCard tone="error">{t("teacher.statement_detail_error")}: {statementsResult.message}</AlertCard> : null}
      {!courseTypesResult.ok ? <AlertCard tone="error">{t("teacher.statement_services_error")}: {courseTypesResult.message}</AlertCard> : null}
      {!locationsResult.ok ? <AlertCard tone="error">{t("teacher.statement_locations_error")}: {locationsResult.message}</AlertCard> : null}
      {!contractGridsResult.ok ? <AlertCard tone="error">{t("teacher.statement_contract_grid_error")}: {contractGridsResult.message}</AlertCard> : null}
      {!invoicesResult.ok ? <AlertCard tone="error">{t("teacher.statement_invoices_error")}: {invoicesResult.message}</AlertCard> : null}

      <article className="card statement-month-switcher">
        <div className="row spread">
          <Link className="mode-link" href={previousMonthHref}>
            ← {t("teacher.previous_month")}
          </Link>
          <strong>{monthLabel} {year}</strong>
          <Link className="mode-link" href={nextMonthHref}>
            {t("teacher.next_month")} →
          </Link>
        </div>
      </article>

      <article className="card statement-period-hero">
        <p className="statement-title">{t("teacher.statement_title")}</p>
        <p className="statement-period-strong">{t("teacher.statement_period", period)}</p>
        <span className={`status-pill ${globalStatusTone}`}>{globalStatus}</span>
      </article>

      <article className="card statement-summary-card">
        <h3>{t("teacher.financial_summary")}</h3>
        <div className="statement-summary-grid">
          <div>
            <small className="muted">{t("teacher.services_count")}</small>
            <strong>{totalServices}</strong>
          </div>
          <div>
            <small className="muted">{t("teacher.total_hours")}</small>
            <strong>{totalHours} h</strong>
          </div>
          <div>
            <small className="muted">{t(vatApplicable ? "teacher.total_excl_tax" : "teacher.total_excl_tax_payable")}</small>
            <strong>{totalHt} EUR</strong>
          </div>
          <div>
            <small className="muted">{t("common.vat")}</small>
            <strong>{vatApplicable ? `${totalVat} EUR` : t("teacher.vat_not_applicable")}</strong>
          </div>
          {vatApplicable ? (
            <div>
              <small className="muted">{t("teacher.net_payable_incl_tax")}</small>
              <strong>{totalPayable} EUR</strong>
            </div>
          ) : null}
          <div>
            <small className="muted">{t("teacher.student_attendance")}</small>
            <strong className={`status-pill ${attendanceComplete ? "status-ok" : "status-warn"}`}>
              {attendanceComplete ? t("teacher.attendance_complete") : t("teacher.attendance_incomplete")}
            </strong>
          </div>
        </div>
      </article>

      <article className="card">
        <div className="row spread statement-list-head">
          <h3>
            {t("teacher.statement_services")}
            <span className="badge statement-list-count">{services.length}</span>
          </h3>
          <small className="muted">{t("teacher.statement_select_lines")}</small>
        </div>
        {services.length === 0 ? (
          <p className="muted">{t("teacher.statement_no_services")}</p>
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
                  <div className="statement-service-pricing">
                    <div className="statement-service-calculation" aria-label={t("teacher.calculation_details")}>
                      <div>
                        <small>{t("teacher.duration")}</small>
                        <strong>{row.durationMinutes} min</strong>
                      </div>
                      <div>
                        <small>{t("teacher.hourly_rate_excl_tax")}</small>
                        <strong>{row.rateHt} EUR / h</strong>
                      </div>
                    </div>
                    <div className={`statement-service-amounts ${vatApplicable ? "statement-service-amounts-vat" : ""}`}>
                      {vatApplicable ? (
                        <>
                          <div>
                            <small>{t("teacher.service_amount_excl_tax")}</small>
                            <strong>{row.amountHt} EUR</strong>
                          </div>
                          <div>
                            <small>{t("common.vat")}</small>
                            <strong>{row.vat} EUR</strong>
                          </div>
                          <div className="statement-service-payable">
                            <small>{t("teacher.net_payable_incl_tax")}</small>
                            <strong>{row.totalTtc} EUR</strong>
                          </div>
                        </>
                      ) : (
                        <div className="statement-service-payable statement-service-payable-only">
                          <small>{t("teacher.service_amount_excl_tax_payable")}</small>
                          <strong>{row.amountHt} EUR</strong>
                          <span>{t("teacher.vat_not_applicable")}</span>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="statement-attendance-block">
                    <small className="muted">{t("teacher.student_attendance")}</small>
                    {row.attendance.length === 0 ? (
                      <p className="muted statement-attendance-empty">{t("teacher.no_student_registered")}</p>
                    ) : (
                      <div className="row statement-attendance-list">
                        {row.attendance.map((attendanceRow, attendanceIndex) => (
                          <span
                            key={`${row.rowId}-${attendanceRow.studentName}-${attendanceIndex}`}
                            className={`status-pill ${attendanceTone(attendanceRow.status)}`}
                          >
                            {attendanceRow.studentName} · {attendanceLabel(attendanceRow.status, language)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </article>

      <article className="card statement-action-block">
        <h3>{t("teacher.report_issue_existing_lines")}</h3>
        <p className="muted">{t("teacher.report_issue_existing_lines_help")}</p>
        <a className="mode-link" href={disputePanelHref}>
          {t("teacher.report_issue_existing_lines_cta")}
        </a>
      </article>

      <article className="card statement-action-block">
        <h3>{t("teacher.add_missing_service")}</h3>
        <p className="muted">{t("teacher.add_missing_service_help")}</p>
        <a className="mode-link" href={missingPanelHref}>
          {t("teacher.add_missing_service_cta")}
        </a>
      </article>

      <article className="card statement-validation-block">
        <h3>{t("teacher.statement_validation")}</h3>
        <p className="muted">{t("teacher.statement_validation_help")}</p>
        <div className="statement-validation-actions">
          <form action={teacherApproveStatementsOnlyAction}>
            <input type="hidden" name="year" value={year} />
            <input type="hidden" name="month" value={month} />
            <input type="hidden" name="return_to" value={statementsMonthHref} />
            <button type="submit">{t("teacher.approve_statement")}</button>
          </form>
        </div>
      </article>

      <article className="card statement-validation-block">
        <h3>{t("teacher.billing")}</h3>
        {billingUnlocked ? (
          <div className="statement-billing-options">
            <form action={teacherGenerateStatementsInvoiceAction}>
              <input type="hidden" name="year" value={year} />
              <input type="hidden" name="month" value={month} />
              <input type="hidden" name="return_to" value={statementsMonthHref} />
              <button type="submit" className="ghost">
                {t("teacher.generate_invoice")}
              </button>
            </form>
            <details className="statement-external-billing">
              <summary>{t("teacher.external_billing")}</summary>
              <p className="muted">{t("teacher.external_billing_help")}</p>
              <a className="mode-link" href={`/prof/statements/${year}/${month}/export`}>
                {t("teacher.export_services")}
              </a>
              {externalPayorOptions.length > 0 ? (
                <form action={teacherSendExternalInvoiceAction} className="grid top-gap-sm teacher-form-stack statement-external-send-form">
                  <input type="hidden" name="year" value={year} />
                  <input type="hidden" name="month" value={month} />
                  <input type="hidden" name="return_to" value={statementsMonthHref} />
                  <label>
                    {t("teacher.payor_entity")}
                    <select name="payor_legal_entity_id" required>
                      {externalPayorOptions.map((payor) => (
                        <option key={payor.id} value={payor.id}>
                          {payor.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    {t("teacher.invoice_pdf")}
                    <input type="file" name="invoice_file" accept="application/pdf,.pdf" required />
                  </label>
                  <label>
                    {t("teacher.optional_note")}
                    <textarea name="note" rows={3} maxLength={1000} placeholder={t("teacher.accounting_note_placeholder")} />
                  </label>
                  <button type="submit">{t("teacher.send_external_invoice")}</button>
                </form>
              ) : null}
            </details>
            {monthInvoices.length > 0 ? (
              <section className="statement-generated-invoices">
                <h4>{t("teacher.generated_invoices_period")}</h4>
                <div className="statement-generated-list">
                  {monthInvoices.map((invoice) => (
                    <article key={invoice.id} className="statement-generated-card">
                      <div className="row spread statement-generated-head">
                        <strong>{invoice.invoice_number}</strong>
                        <span className={`status-pill ${invoice.status === "sent_to_accounting" ? "status-ok" : "status-off"}`}>
                          {invoiceStatusLabel(invoice.status, language)}
                        </span>
                      </div>
                      <small className="muted">
                        {t("common.date")}: {formatDateLabel(invoice.invoice_date, language)} • {t("teacher.amount_payable")}: {invoice.is_vat_applicable ? invoice.totals_ttc : invoice.totals_ht} EUR
                      </small>
                      <div className="statement-generated-actions">
                        <Link className="mode-link" href={`/prof/invoices/${invoice.id}`}>
                          {t("teacher.open")}
                        </Link>
                        <a className="mode-link" href={`/api/v1/teacher/invoices/${invoice.id}/pdf`}>
                          PDF
                        </a>
                        {invoice.status === "sent_to_accounting" ? (
                          <small className="muted">{t("teacher.already_sent_accounting")}</small>
                        ) : (
                          <form action={teacherSendInvoiceToAccountingAction}>
                            <input type="hidden" name="invoice_id" value={invoice.id} />
                            <input type="hidden" name="return_to" value={statementsMonthHref} />
                            <button type="submit">{t("teacher.send_to_accounting")}</button>
                          </form>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ) : null}
          </div>
        ) : (
          <p className="muted">{t("teacher.billing_locked")}</p>
        )}
      </article>

      <section id="statement-dispute-modal" className="modal-overlay statement-target-modal">
        <article className="modal-panel modal-compact">
          <a className="close-link" href="#" aria-label={t("teacher.close_issue_report")}>
            ✕
          </a>
          <h3>{t("teacher.selected_lines_report_title")}</h3>
          <p className="muted">{t("teacher.selected_lines_report_help")}</p>
          <form id="statement-dispute-form" action={teacherDisputeSelectedLinesAction} className="grid top-gap-sm">
            <input type="hidden" name="year" value={year} />
            <input type="hidden" name="month" value={month} />
            <input type="hidden" name="return_to" value={statementsMonthHref} />
            <label>
              {t("teacher.required_comment")}
              <textarea
                name="message"
                required
                minLength={5}
                maxLength={4000}
                rows={5}
                placeholder={t("teacher.selected_lines_report_placeholder")}
              />
            </label>
            <button type="submit" className="ghost">{t("teacher.send_to_admin")}</button>
          </form>
        </article>
      </section>

      <section id="statement-missing-modal" className="modal-overlay statement-target-modal">
        <article className="modal-panel modal-compact">
          <a className="close-link" href="#" aria-label={t("teacher.close_missing_service")}>
            ✕
          </a>
          <h3>{t("teacher.add_missing_service")}</h3>
          <TeacherMissingServiceForm
            action={teacherReportMissingServiceAction}
            year={year}
            month={month}
            returnTo={statementsMonthHref}
            defaultDate={defaultMissingServiceDate}
            currency={fallbackCurrency}
            language={language}
            activities={missingServiceActivities}
            locations={missingServiceLocations}
          />
        </article>
      </section>

      <section
        id="statement-success-modal"
        className={`modal-overlay statement-target-modal${showSuccessModal ? " is-open" : ""}`}
      >
        <article className="modal-panel modal-compact">
          <a className="close-link" href={statementsMonthHref} aria-label={t("teacher.close_confirmation")}>
            ✕
          </a>
          <h3>{t("teacher.report_sent")}</h3>
          <p className="muted">{successMessage || ok || t("teacher.statement_default_success")}</p>
          <a className="mode-link" href={statementsMonthHref}>
            {t("common.continue")}
          </a>
        </article>
      </section>
      <ProfessorHelpAssistant language={language} interfaceLabels={buildProfessorHelpLabels(language)} />
    </section>
  );
}
