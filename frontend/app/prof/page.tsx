import Link from "next/link";
import { redirect } from "next/navigation";

import {
  logoutAction,
  professorCreateCatalogRequestAction,
  professorDeliverCatalogRequestAction,
  professorMarkSessionAbsentAction,
  professorSendSessionMessageAction,
  professorUpdateAttendanceAction,
  professorUpdateBookingInternalNoteAction,
  professorUpdateSessionInternalNoteAction,
} from "../../lib/actions";
import { backendRequest } from "../../lib/backend";
import { portalFailurePath } from "../../lib/portal-auth-routing";
import { hasAnyAdminAccess } from "../../lib/admin-access";
import AutoSubmitInput from "../../components/auto-submit-input";
import AutoSubmitSelect from "../../components/auto-submit-select";
import DayEventsDrawer from "../../components/planning/day-events-drawer";
import MonthDayCard from "../../components/planning/month-day-card";
import PortalImpersonationBanner from "../../components/portal-impersonation-banner";
import ActionCard from "../../components/teacher-ui/action-card";
import AppInstallCard, { AppInstallMenuLink } from "../../components/teacher-ui/app-install-card";
import AlertCard from "../../components/teacher-ui/alert-card";
import BottomTabs from "../../components/teacher-ui/bottom-tabs";
import ProfessorHelpAssistant from "../../components/teacher-ui/help-assistant";
import ProfessorMobilePushRegistration from "../../components/teacher-ui/mobile-push-registration";
import PresenceHeartbeat from "../../components/presence-heartbeat";
import ListRow from "../../components/teacher-ui/list-row";
import ProfessorLocalIntakeRequestModal from "../../components/professor-local-intake-request-modal";
import PageHeaderMobile from "../../components/teacher-ui/page-header-mobile";
import PortalBrandLockup from "../../components/portal-brand-lockup";
import SectionAccordion from "../../components/teacher-ui/section-accordion";
import StatCard from "../../components/teacher-ui/stat-card";
import StatChip from "../../components/teacher-ui/stat-chip";
import StickyActionBar from "../../components/teacher-ui/sticky-action-bar";
import { getPortalReturnTo, getProfessorPortalToken, readPortalImpersonationClaims } from "../../lib/auth-cookies";
import { buildProfessorHelpLabels } from "../../lib/professor-help-labels";
import type { PlanningEventChipData } from "../../components/planning/month-event-chip";
import type {
  ProfessorAttendancePendingOut,
  ProfessorBalanceOut,
  ProfessorContractGridOut,
  ProfessorInternalNoteListOut,
  ProfessorLocalIntakeTaskOut,
  ProfessorLocalIntakeDetailOut,
  AdminCatalogProductOut,
  AdminCatalogRequestOut,
  LocationOut,
  ProfessorMeOut,
  ProfessorCatalogStudentOut,
  ProfessorPayoutOut,
  ProfessorSessionMessageOut,
  ProfessorInboxMessageOut,
  ProfessorSessionOut,
  ClientNewsOut,
  UserOut,
} from "../../lib/types";
import { normalizeUiLanguage, resolveAuthOkMessage, type UiLanguage, uiText } from "../../lib/ui-i18n";
import { sanitizeRichHtml } from "../../lib/sanitize-rich-html";

type SearchParams = Record<string, string | string[] | undefined>;

function emptyListResult<T>(): Promise<{ ok: true; status: 200; data: T[] }> {
  return Promise.resolve({ ok: true, status: 200, data: [] as T[] });
}
type Tab = "overview" | "planning" | "notes" | "finance" | "messages" | "catalog" | "profile";
type AgendaView = "week" | "day" | "agenda";
type PlanningScope = "mine" | "all";

type AgendaRange = {
  from: Date;
  to: Date;
  dayKeys: string[];
  title: string;
};

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function resolveProfessorErrorMessage(rawError: string, errorCode: string, errorStatus: string, language: UiLanguage): string {
  if (rawError) {
    return rawError;
  }
  const normalized = errorCode.trim().toLowerCase();
  if (normalized === "prof_statement_period_invalid") {
    return uiText(language, "teacher.statement_export_invalid_period");
  }
  if (normalized === "prof_statement_export_failed") {
    return uiText(language, "teacher.statement_export_failed", { status: errorStatus || "?" });
  }
  return "";
}

function parseTab(value: string): Tab {
  if (value === "planning" || value === "notes" || value === "finance" || value === "messages" || value === "catalog" || value === "profile") {
    return value;
  }
  return "overview";
}

function parseAgendaView(value: string): AgendaView {
  if (value === "day" || value === "agenda" || value === "week") {
    return value;
  }
  return "agenda";
}

function isDateKey(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function keyToUtcDate(key: string): Date {
  return new Date(`${key}T00:00:00.000Z`);
}

function utcDateToKey(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function addUtcDays(date: Date, days: number): Date {
  const out = new Date(date.getTime());
  out.setUTCDate(out.getUTCDate() + days);
  return out;
}

function startOfWeekUtc(date: Date): Date {
  const day = date.getUTCDay();
  const offsetFromMonday = (day + 6) % 7;
  return addUtcDays(date, -offsetFromMonday);
}

function todayKeyUtc(): string {
  return utcDateToKey(new Date());
}

function localeForLanguage(language: UiLanguage): string {
  return language === "en" ? "en-US" : "fr-FR";
}

function buildAgendaRange(view: AgendaView, focusDayKey: string, language: UiLanguage = "fr"): AgendaRange {
  const focusDate = keyToUtcDate(focusDayKey);
  const locale = localeForLanguage(language);

  if (view === "day") {
    const from = focusDate;
    const toExclusive = addUtcDays(from, 1);
    const to = new Date(toExclusive.getTime() - 1);
    return {
      from,
      to,
      dayKeys: [focusDayKey],
      title: new Intl.DateTimeFormat(locale, {
        weekday: "long",
        day: "2-digit",
        month: "long",
        year: "numeric",
        timeZone: "UTC",
      }).format(from),
    };
  }

  if (view === "agenda") {
    const from = focusDate;
    const dayKeys: string[] = [];
    for (let i = 0; i < 14; i += 1) {
      dayKeys.push(utcDateToKey(addUtcDays(from, i)));
    }
    const lastDay = addUtcDays(from, 13);
    const toExclusive = addUtcDays(lastDay, 1);
    const to = new Date(toExclusive.getTime() - 1);
    return {
      from,
      to,
      dayKeys,
      title: `${new Intl.DateTimeFormat(locale, {
        day: "2-digit",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      }).format(from)} - ${new Intl.DateTimeFormat(locale, {
        day: "2-digit",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      }).format(lastDay)}`,
    };
  }

  const from = startOfWeekUtc(focusDate);
  const dayKeys: string[] = [];
  for (let i = 0; i < 7; i += 1) {
    dayKeys.push(utcDateToKey(addUtcDays(from, i)));
  }
  const lastDay = addUtcDays(from, 6);
  const toExclusive = addUtcDays(lastDay, 1);
  const to = new Date(toExclusive.getTime() - 1);
  return {
    from,
    to,
    dayKeys,
    title: `${new Intl.DateTimeFormat(locale, {
      day: "2-digit",
      month: "short",
      year: "numeric",
      timeZone: "UTC",
    }).format(from)} - ${new Intl.DateTimeFormat(locale, {
      day: "2-digit",
      month: "short",
      year: "numeric",
      timeZone: "UTC",
    }).format(lastDay)}`,
  };
}

function formatDayLabel(dayKey: string, view: AgendaView, language: UiLanguage = "fr"): string {
  const date = keyToUtcDate(dayKey);
  const locale = localeForLanguage(language);
  if (view === "day") {
    return new Intl.DateTimeFormat(locale, {
      weekday: "long",
      day: "2-digit",
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    }).format(date);
  }
  return new Intl.DateTimeFormat(locale, {
    weekday: "short",
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  }).format(date);
}

function formatDateTime(value: string, language: UiLanguage = "fr"): string {
  return new Date(value).toLocaleString(localeForLanguage(language), {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatTime(value: string, language: UiLanguage = "fr"): string {
  return new Date(value).toLocaleTimeString(localeForLanguage(language), {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDateOnly(value: string, language: UiLanguage = "fr"): string {
  return new Date(`${value}T00:00:00Z`).toLocaleDateString(localeForLanguage(language), {
    day: "2-digit",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

function professorModeLabel(mode: string, language: UiLanguage = "fr"): string {
  const normalized = mode.trim().toUpperCase();
  if (normalized === "EN_LIGNE") {
    return uiText(language, "teacher.mode_online");
  }
  if (normalized === "PRESENTIEL") {
    return uiText(language, "teacher.mode_onsite");
  }
  return uiText(language, "teacher.mode_other");
}

function formatMoneyEurLike(amountRaw: string, currency: string, language: UiLanguage = "fr"): string {
  const amount = Number(amountRaw);
  if (!Number.isFinite(amount)) {
    return `${amountRaw} ${currency}`;
  }
  return `${amount.toLocaleString(localeForLanguage(language), {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} ${currency}`;
}

function formatRuleLabel(
  rule: { min_students: number; max_students: number | null; hourly_rate: string },
  currency: string,
  language: UiLanguage = "fr",
): string {
  const amount = formatMoneyEurLike(rule.hourly_rate, currency, language);
  if (rule.max_students === null) {
    return uiText(language, "teacher.students_and_more_rate", { min: rule.min_students, amount });
  }
  return uiText(language, "teacher.students_range_rate", { min: rule.min_students, max: rule.max_students, amount });
}

function statusBadgeClass(status: string): string {
  const normalized = status.toUpperCase();
  if (normalized === "ATTENDANCE_PENDING") {
    return "status-waitlist";
  }
  if (normalized === "COMPLETED") {
    return "status-completed";
  }
  if (normalized === "CANCELLED") {
    return "status-cancelled";
  }
  return "status-scheduled";
}

function statusLabel(status: string, language: UiLanguage = "fr"): string {
  const normalized = status.toUpperCase();
  if (normalized === "ATTENDANCE_PENDING") {
    return uiText(language, "teacher.statement_status_attendance_pending");
  }
  if (normalized === "SCHEDULED") {
    return uiText(language, "teacher.session_status_scheduled");
  }
  if (normalized === "COMPLETED") {
    return uiText(language, "teacher.session_status_completed");
  }
  if (normalized === "CANCELLED") {
    return uiText(language, "teacher.session_status_cancelled");
  }
  return normalized;
}

function professorTypeLabel(session: ProfessorSessionOut, language: UiLanguage = "fr"): string {
  const locationCode = (session.location.code || "").toUpperCase();
  const locationName = (session.location.name || "").toLowerCase();
  const courseName = (session.course_type.name || "").toLowerCase();
  if (session.location.is_online || locationCode === "ONLINE") {
    return uiText(language, "teacher.session_type_online");
  }
  if (locationCode.includes("DOMICILE") || locationName.includes("domicile")) {
    return uiText(language, "teacher.session_type_home");
  }
  if (courseName.includes("prive") || courseName.includes("particulier")) {
    return uiText(language, "teacher.session_type_private");
  }
  return uiText(language, "teacher.session_type_group");
}

function shortLocationLabel(value: string, language: UiLanguage = "fr"): string {
  const trimmed = (value || "").trim();
  if (!trimmed) {
    return uiText(language, "teacher.location_fallback");
  }
  for (const separator of [" - ", ",", "|"]) {
    if (trimmed.includes(separator)) {
      return trimmed.split(separator, 1)[0].trim() || uiText(language, "teacher.location_fallback");
    }
  }
  return trimmed;
}

function attendanceLabel(status: string, language: UiLanguage = "fr"): string {
  const normalized = status.toUpperCase();
  if (normalized === "BOOKED") {
    return uiText(language, "teacher.attendance_booked");
  }
  if (normalized === "ATTENDED") {
    return uiText(language, "teacher.attendance_attended");
  }
  if (normalized === "NO_SHOW") {
    return uiText(language, "teacher.attendance_no_show");
  }
  if (normalized === "EXCUSED_ABSENCE") {
    return uiText(language, "teacher.attendance_excused_absence");
  }
  if (normalized === "WAITLISTED") {
    return uiText(language, "teacher.attendance_waitlisted");
  }
  return normalized;
}

function attendanceRowTone(status: string): "warn" | "ok" | "neutral" | "danger" {
  const normalized = status.toUpperCase();
  if (normalized === "ATTENDED") {
    return "ok";
  }
  if (normalized === "NO_SHOW") {
    return "danger";
  }
  if (normalized === "EXCUSED_ABSENCE") {
    return "neutral";
  }
  return "warn";
}

function buildProfHref(params: {
  tab: Tab;
  agendaView: AgendaView;
  agendaDate: string;
  sessionId?: string | null;
  messageId?: string | null;
  dayDetails?: string | null;
  attendanceFilter?: string | null;
  planningScope?: PlanningScope;
  intakeDetail?: string | null;
}): string {
  const query = new URLSearchParams();
  query.set("tab", params.tab);
  query.set("agenda_view", params.agendaView);
  query.set("agenda_date", params.agendaDate);
  if (params.sessionId) {
    query.set("session_id", params.sessionId);
  }
  if (params.messageId) {
    query.set("message_id", params.messageId);
  }
  if (params.dayDetails) {
    query.set("day_details", params.dayDetails);
  }
  if (params.attendanceFilter && params.attendanceFilter !== "all") {
    query.set("attendance_filter", params.attendanceFilter);
  }
  if (params.planningScope === "all") {
    query.set("planning_scope", "all");
  }
  if (params.intakeDetail) {
    query.set("intake_detail", params.intakeDetail);
  }
  return `/prof?${query.toString()}`;
}

function shiftAgendaDate(view: AgendaView, agendaDate: string, direction: -1 | 1): string {
  const focusDate = keyToUtcDate(agendaDate);
  if (view === "week") {
    return utcDateToKey(addUtcDays(focusDate, direction * 7));
  }
  if (view === "day") {
    return utcDateToKey(addUtcDays(focusDate, direction));
  }
  return utcDateToKey(addUtcDays(focusDate, direction * 14));
}

function parseMessageSubject(subject: string): { cleanedSubject: string; targetLabel: string | null } {
  const studentMatch = subject.match(/\s*\(eleve:\s*(.+)\)\s*$/i);
  if (studentMatch) {
    const cleanedSubject = subject.replace(/\s*\(eleve:\s*(.+)\)\s*$/i, "").trim();
    return {
      cleanedSubject: cleanedSubject || subject,
      targetLabel: studentMatch[1]?.trim() || null,
    };
  }
  const adminMatch = subject.match(/\s*\(administration\)\s*$/i);
  if (adminMatch) {
    const cleanedSubject = subject.replace(/\s*\(administration\)\s*$/i, "").trim();
    return {
      cleanedSubject: cleanedSubject || subject,
      targetLabel: "Administration",
    };
  }
  return { cleanedSubject: subject, targetLabel: null };
}

function plainMessagePreview(raw: string, format: string): string {
  const plainText =
    format === "HTML"
      ? raw
          .replace(/<\s*br\s*\/?>/gi, "\n")
          .replace(/<\s*\/\s*p\s*>/gi, "\n")
          .replace(/<\s*\/\s*div\s*>/gi, "\n")
          .replace(/<\s*li\b[^>]*>/gi, "- ")
          .replace(/<[^>]+>/g, "")
      : raw;
  return plainText.replace(/\n{3,}/g, "\n\n").trim();
}

function pendingAttendanceCount(session: ProfessorSessionOut): number {
  return session.students.filter((student) => student.attendance_status === "BOOKED").length;
}

function reservedStudentsCountFromRoster(session: ProfessorSessionOut): number {
  return session.students.filter((student) => {
    return (
      student.attendance_status === "BOOKED" ||
      student.attendance_status === "ATTENDED" ||
      student.attendance_status === "NO_SHOW" ||
      student.attendance_status === "EXCUSED_ABSENCE"
    );
  }).length;
}

function sessionDisplayStatus(session: ProfessorSessionOut): string {
  const normalized = session.status.toUpperCase();
  if (normalized !== "SCHEDULED") {
    return normalized;
  }
  const sessionEnded = new Date(session.end_at_utc).getTime() <= Date.now();
  if (!sessionEnded) {
    return normalized;
  }
  return pendingAttendanceCount(session) > 0 ? "ATTENDANCE_PENDING" : "COMPLETED";
}

function productRequestStatusLabel(status: string, language: UiLanguage = "fr"): string {
  const normalized = status.toUpperCase();
  if (normalized === "PROCESSING") {
    return uiText(language, "teacher.request_processing");
  }
  if (normalized === "INVOICE_TO_SEND") {
    return uiText(language, "teacher.request_invoice_to_send");
  }
  if (normalized === "TO_DELIVER") {
    return uiText(language, "teacher.request_to_deliver");
  }
  if (normalized === "DELIVERED") {
    return uiText(language, "teacher.request_delivered");
  }
  if (normalized === "REJECTED") {
    return uiText(language, "teacher.request_rejected");
  }
  return normalized;
}

function productRequestSourceLabel(source: string, language: UiLanguage = "fr"): string {
  const normalized = source.toUpperCase();
  if (normalized === "PROFESSOR") {
    return uiText(language, "teacher.default_name");
  }
  if (normalized === "ADMIN") {
    return uiText(language, "teacher.admin_target");
  }
  return normalized;
}

function payoutStatusLabel(status: string | null, language: UiLanguage = "fr"): string {
  const normalized = (status || "").toUpperCase();
  if (normalized === "PENDING") {
    return uiText(language, "teacher.payout_status_pending");
  }
  if (normalized === "APPROVED") {
    return uiText(language, "teacher.payout_status_approved");
  }
  if (normalized === "PAID") {
    return uiText(language, "teacher.payout_status_paid");
  }
  return status || "-";
}

function payoutStatusBadgeClass(status: string | null): string {
  const normalized = (status || "").toUpperCase();
  if (normalized === "PAID") {
    return "status-ok";
  }
  if (normalized === "APPROVED") {
    return "status-scheduled";
  }
  return "status-warn";
}

export default async function ProfessorPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = getProfessorPortalToken();
  const professorLoginPath = "/login?portal=prof&return_to=%2Fprof&error_code=session_expired";
  if (!token) {
    redirect(professorLoginPath);
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok) {
    redirect(portalFailurePath({ status: meResult.status, returnTo: "/prof", loginPath: professorLoginPath }));
  }

  if (meResult.data.role === "admin") {
    redirect("/admin");
  }
  if (meResult.data.role !== "prof") {
    redirect("/client?tab=home");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const canAccessAdminPortal = hasAnyAdminAccess(meResult.data);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const currentTab = parseTab(readParam(searchParams, "tab"));
  const impersonationClaims = readPortalImpersonationClaims();
  const isImpersonating = Boolean(impersonationClaims?.imp);
  const impersonationReturnTo = getPortalReturnTo() ?? "/admin";
  const impersonationNameHint = readParam(searchParams, "imp_name").trim();
  const agendaView = parseAgendaView(readParam(searchParams, "agenda_view"));
  const agendaDateRaw = readParam(searchParams, "agenda_date");
  const agendaDate = isDateKey(agendaDateRaw) ? agendaDateRaw : todayKeyUtc();
  const agendaRange = buildAgendaRange(agendaView, agendaDate, language);
  const requestedPlanningScope: PlanningScope =
    currentTab === "planning" && readParam(searchParams, "planning_scope") === "all" ? "all" : "mine";
  const selectedLocalIntakeId = currentTab === "overview" ? readParam(searchParams, "intake_detail").trim() : "";
  const needsPlanning = currentTab === "overview" || currentTab === "planning";
  const needsCatalog = currentTab === "catalog";
  const needsFinance = currentTab === "finance";
  const needsMessages = currentTab === "messages" || currentTab === "planning";

  const sessionsQuery = new URLSearchParams();
  sessionsQuery.set("from", agendaRange.from.toISOString());
  sessionsQuery.set("to", agendaRange.to.toISOString());
  sessionsQuery.set("include_students", "true");
  sessionsQuery.set("scope", requestedPlanningScope);

  const [
    profileResult,
    pendingResult,
    sessionsResult,
    notesResult,
    balanceResult,
    payoutsResult,
    messagesResult,
    inboxResult,
    contractGridsResult,
    catalogStudentsResult,
    catalogProductsResult,
    catalogLocationsResult,
    catalogRequestsResult,
    localIntakesResult,
    selectedLocalIntakeResult,
    newsResult,
  ] = await Promise.all([
    backendRequest<ProfessorMeOut>("/api/v1/professors/me", {}, token),
    currentTab === "overview"
      ? backendRequest<ProfessorAttendancePendingOut[]>("/api/v1/professors/me/attendance/pending?limit=200", {}, token)
      : emptyListResult<ProfessorAttendancePendingOut>(),
    needsPlanning
      ? backendRequest<ProfessorSessionOut[]>(`/api/v1/professors/me/sessions?${sessionsQuery.toString()}`, {}, token)
      : emptyListResult<ProfessorSessionOut>(),
    currentTab === "notes"
      ? backendRequest<ProfessorInternalNoteListOut[]>("/api/v1/professors/me/notes?limit=1000", {}, token)
      : Promise.resolve({ ok: true as const, status: 200, data: [] as ProfessorInternalNoteListOut[] }),
    needsFinance
      ? backendRequest<ProfessorBalanceOut>("/api/v1/professors/me/balance", {}, token)
      : Promise.resolve({
          ok: true as const,
          status: 200 as const,
          data: {
            currency: "EUR",
            pending_amount: "0",
            approved_amount: "0",
            paid_amount: "0",
            total_amount: "0",
            pending_sessions: 0,
            approved_sessions: 0,
            paid_sessions: 0,
          } satisfies ProfessorBalanceOut,
        }),
    needsFinance
      ? backendRequest<ProfessorPayoutOut[]>("/api/v1/professors/me/payouts?limit=200", {}, token)
      : emptyListResult<ProfessorPayoutOut>(),
    needsMessages
      ? backendRequest<ProfessorSessionMessageOut[]>("/api/v1/professors/me/messages?limit=100", {}, token)
      : emptyListResult<ProfessorSessionMessageOut>(),
    currentTab === "messages"
      ? backendRequest<ProfessorInboxMessageOut[]>("/api/v1/professors/me/inbox?limit=200", {}, token)
      : Promise.resolve({ ok: true as const, status: 200, data: [] as ProfessorInboxMessageOut[] }),
    needsFinance
      ? backendRequest<ProfessorContractGridOut[]>("/api/v1/professors/me/contract-grids", {}, token)
      : emptyListResult<ProfessorContractGridOut>(),
    needsCatalog
      ? backendRequest<ProfessorCatalogStudentOut[]>("/api/v1/professors/me/catalog/students", {}, token)
      : emptyListResult<ProfessorCatalogStudentOut>(),
    needsCatalog
      ? backendRequest<AdminCatalogProductOut[]>("/api/v1/professors/me/catalog/products", {}, token)
      : emptyListResult<AdminCatalogProductOut>(),
    needsCatalog
      ? backendRequest<LocationOut[]>("/api/v1/locations?active=true", {}, token)
      : emptyListResult<LocationOut>(),
    needsCatalog
      ? backendRequest<AdminCatalogRequestOut[]>("/api/v1/professors/me/catalog/requests", {}, token)
      : emptyListResult<AdminCatalogRequestOut>(),
    currentTab === "overview"
      ? backendRequest<ProfessorLocalIntakeTaskOut[]>(
          "/api/v1/professors/me/intakes/local-confirmations?status=PENDING&limit=100",
          {},
          token,
        )
      : emptyListResult<ProfessorLocalIntakeTaskOut>(),
    selectedLocalIntakeId
      ? backendRequest<ProfessorLocalIntakeDetailOut>(
          `/api/v1/professors/me/intakes/local-confirmations/${encodeURIComponent(selectedLocalIntakeId)}`,
          {},
          token,
        )
      : Promise.resolve({ ok: true as const, status: 200, data: null as ProfessorLocalIntakeDetailOut | null }),
    backendRequest<ClientNewsOut[]>("/api/v1/professors/me/news", {}, token),
  ]);

  if (!profileResult.ok) {
    redirect(portalFailurePath({ status: profileResult.status, returnTo: "/prof", loginPath: professorLoginPath }));
  }

  const profile = profileResult.data;
  const professorNews = newsResult.ok ? newsResult.data : [];
  const fullName = `${profile.first_name} ${profile.last_name}`.trim();
  const canViewAllSchoolSessions = Boolean(
    profile.permissions.can_view_all_school_sessions
      || profile.permissions.can_view_other_teachers_sessions
      || profile.permissions.can_manage_other_teachers_students_and_sessions,
  );
  const planningScope: PlanningScope = canViewAllSchoolSessions && requestedPlanningScope === "all" ? "all" : "mine";
  const impersonationDisplayName = impersonationNameHint || fullName || profile.email;
  const okMessage = resolveAuthOkMessage(readParam(searchParams, "ok"), readParam(searchParams, "ok_code"), language);
  const errorMessage = resolveProfessorErrorMessage(
    readParam(searchParams, "error"),
    readParam(searchParams, "error_code"),
    readParam(searchParams, "error_status"),
    language,
  );

  const sessions = sessionsResult.ok ? sessionsResult.data : [];
  const sessionsByDay = new Map<string, ProfessorSessionOut[]>();
  for (const session of sessions) {
    const dayKey = session.start_at_utc.slice(0, 10);
    const bucket = sessionsByDay.get(dayKey) ?? [];
    bucket.push(session);
    sessionsByDay.set(dayKey, bucket);
  }
  for (const rows of sessionsByDay.values()) {
    rows.sort((a, b) => a.start_at_utc.localeCompare(b.start_at_utc));
  }
  const agendaDays = agendaRange.dayKeys.map((dayKey) => ({
    key: dayKey,
    label: formatDayLabel(dayKey, agendaView, language),
    sessions: sessionsByDay.get(dayKey) ?? [],
  }));
  const dayDetailsRaw = readParam(searchParams, "day_details");
  const dayDetails = isDateKey(dayDetailsRaw) ? dayDetailsRaw : "";
  const agendaCardDays = agendaDays.map((day) => ({
    key: day.key,
    label: day.label,
    events: day.sessions.map((session) => {
      const displayStatus = sessionDisplayStatus(session);
      return {
        id: session.id,
        title: session.title,
        start_at_utc: session.start_at_utc,
        end_at_utc: session.end_at_utc,
        capacity_max: session.capacity_max,
        booked_count: Math.max(session.booked_count, reservedStudentsCountFromRoster(session)),
        teacher_display_name: session.effective_teacher_display_name || fullName || profile.email,
        habitual_teacher_display_name: session.habitual_teacher_display_name || undefined,
        substitute_teacher_display_name: session.substitute_teacher_display_name,
        effective_teacher_display_name: session.effective_teacher_display_name || undefined,
        location_label: shortLocationLabel(session.location.name, language),
        type_label: professorTypeLabel(session, language),
        status_label: statusLabel(displayStatus, language),
        status: displayStatus,
      } satisfies PlanningEventChipData;
    }),
  }));
  const selectedDayDetails = dayDetails ? agendaCardDays.find((day) => day.key === dayDetails) ?? null : null;

  const selectedSessionId = readParam(searchParams, "session_id");
  const selectedSession = selectedSessionId ? sessions.find((session) => session.id === selectedSessionId) ?? null : null;
  const selectedSessionDisplayStatus = selectedSession ? sessionDisplayStatus(selectedSession) : null;
  const selectedSessionReservedCount = selectedSession
    ? Math.max(selectedSession.booked_count, reservedStudentsCountFromRoster(selectedSession))
    : 0;
  const selectedSessionPendingCount = selectedSession ? pendingAttendanceCount(selectedSession) : 0;
  const attendanceFilter = readParam(searchParams, "attendance_filter") === "missing" ? "missing" : "all";
  const selectedSessionStudents = selectedSession?.students ?? [];
  const visibleAttendanceStudents =
    attendanceFilter === "missing"
      ? selectedSessionStudents.filter((student) => student.attendance_status === "BOOKED")
      : selectedSessionStudents;
  const editableAttendanceStudents = selectedSessionStudents.filter((student) => student.attendance_status !== "WAITLISTED");
  const selectedSessionBelongsToProfessor = selectedSession
    ? (selectedSession.effective_teacher_id ?? selectedSession.habitual_teacher_id) === profile.id
    : false;
  const selectedMessageId = readParam(searchParams, "message_id");
  const sentMessageId = readParam(searchParams, "sent_message_id");

  const pendingRows = pendingResult.ok ? pendingResult.data : [];
  const pendingCount = pendingRows.reduce((sum, row) => sum + row.pending_students_count, 0);
  const pendingLocalIntakes = localIntakesResult.ok ? localIntakesResult.data : [];
  const catalogStudents = catalogStudentsResult.ok ? catalogStudentsResult.data : [];
  const catalogProducts = catalogProductsResult.ok ? catalogProductsResult.data.filter((row) => row.active) : [];
  const catalogLocations = catalogLocationsResult.ok ? catalogLocationsResult.data.filter((row) => row.active) : [];
  const catalogRequests = catalogRequestsResult.ok ? catalogRequestsResult.data : [];
  const catalogToDeliver = catalogRequests.filter(
    (row) => row.status === "TO_DELIVER" || row.status === "INVOICE_TO_SEND",
  );

  const todaySessions = sessionsByDay.get(todayKeyUtc()) ?? [];
  const canEditPlanning = profile.permissions.can_edit_planning;
  const canTakeAttendance = profile.permissions.can_take_attendance || profile.permissions.can_edit_planning;
  const canMessageStudents = profile.permissions.can_message_clients;
  const canTakeAttendanceForSelectedSession = canTakeAttendance && selectedSessionBelongsToProfessor;
  const canMessageSelectedSession = canMessageStudents && selectedSessionBelongsToProfessor;
  const canEditSelectedSession = canEditPlanning && selectedSessionBelongsToProfessor;
  const maxVisibleSessionsByDay = agendaView === "day" ? 24 : agendaView === "week" ? 8 : 5;
  const previousAgendaDate = shiftAgendaDate(agendaView, agendaDate, -1);
  const nextAgendaDate = shiftAgendaDate(agendaView, agendaDate, 1);
  const previousAgendaHref = buildProfHref({ tab: "planning", agendaView, agendaDate: previousAgendaDate, dayDetails: "", planningScope });
  const nextAgendaHref = buildProfHref({ tab: "planning", agendaView, agendaDate: nextAgendaDate, dayDetails: "", planningScope });
  const todayAgendaHref = buildProfHref({ tab: "planning", agendaView, agendaDate: todayKeyUtc(), dayDetails: "", planningScope });
  const archivedMessages = messagesResult.ok ? messagesResult.data : [];
  const inboxMessages = inboxResult.ok ? inboxResult.data : [];
  const internalNotes = notesResult.ok ? notesResult.data : [];
  const noteSearch = readParam(searchParams, "note_q").trim().toLocaleLowerCase();
  const noteTypeRaw = readParam(searchParams, "note_type").toUpperCase();
  const noteType = noteTypeRaw === "SESSION" || noteTypeRaw === "STUDENT" ? noteTypeRaw : "ALL";
  const notePeriodRaw = readParam(searchParams, "note_period").toUpperCase();
  const notePeriod = notePeriodRaw === "30" || notePeriodRaw === "90" || notePeriodRaw === "365" || notePeriodRaw === "ALL"
    ? notePeriodRaw
    : "ALL";
  const noteLocation = readParam(searchParams, "note_location");
  const notePeriodCutoff = notePeriod === "ALL" ? null : Date.now() - Number(notePeriod) * 24 * 60 * 60 * 1000;
  const noteLocationOptions = Array.from(
    new Map(internalNotes.map((note) => [note.location_id, note.location_name])).entries(),
  )
    .map(([id, name]) => ({ id, name }))
    .sort((a, b) => a.name.localeCompare(b.name, language));
  const filteredInternalNotes = internalNotes.filter((note) => {
    if (noteType !== "ALL" && note.note_type !== noteType) {
      return false;
    }
    if (noteLocation && note.location_id !== noteLocation) {
      return false;
    }
    if (notePeriodCutoff !== null && new Date(note.session_start_at_utc).getTime() < notePeriodCutoff) {
      return false;
    }
    if (!noteSearch) {
      return true;
    }
    return [
      note.body,
      note.student_display_name ?? "",
      note.session_title,
      note.course_type_name,
      note.location_name,
    ].join(" ").toLocaleLowerCase().includes(noteSearch);
  });
  const selectedMessage = selectedMessageId ? archivedMessages.find((message) => message.id === selectedMessageId) ?? null : null;
  const sentMessage = sentMessageId ? archivedMessages.find((message) => message.id === sentMessageId) ?? null : null;
  const selectedSessionMessages = selectedSession
    ? archivedMessages.filter((message) => message.session_id === selectedSession.id)
    : [];

  const navTabs: Array<{ id: Tab; label: string; icon: string }> = [
    { id: "overview", label: uiText(language, "teacher.todo"), icon: "🗂" },
    { id: "planning", label: uiText(language, "teacher.planning"), icon: "📅" },
    { id: "notes", label: uiText(language, "teacher.notes"), icon: "📝" },
    { id: "catalog", label: uiText(language, "teacher.products"), icon: "📦" },
    { id: "finance", label: uiText(language, "teacher.balance"), icon: "💶" },
    { id: "messages", label: uiText(language, "teacher.messages"), icon: "✉️" },
    { id: "profile", label: uiText(language, "teacher.profile"), icon: "👤" },
  ];

  return (
    <main className="page prof-page teacher-shell">
      <PageHeaderMobile
        title={fullName || uiText(language, "teacher.default_name")}
        subtitle={profile.email}
        statusLabel={profile.active ? uiText(language, "common.active") : uiText(language, "common.inactive")}
        menuLabel={uiText(language, "portal.teacher_menu")}
        trailing={
          <div className="row gap-sm">
            {canAccessAdminPortal ? (
              <Link
                className="mode-link teacher-header-link teacher-admin-switch-link"
                href="/admin"
                aria-label={language === "en" ? "Switch to administration" : "Passer en mode administration"}
              >
                {language === "en" ? "Admin mode" : "Mode admin"}
              </Link>
            ) : null}
            <Link className="mode-link teacher-header-link" href="/prof/statements">
              {uiText(language, "teacher.statements")}
            </Link>
          </div>
        }
        menu={
          <div className="teacher-header-menu-items">
            {canAccessAdminPortal ? (
              <Link className="teacher-header-menu-link teacher-header-menu-link-primary" href="/admin">
                {language === "en" ? "Switch to administration" : "Passer en mode administration"}
              </Link>
            ) : null}
            <Link className="teacher-header-menu-link" href={buildProfHref({ tab: "catalog", agendaView, agendaDate })}>
              {uiText(language, "teacher.products")}
            </Link>
            <Link className="teacher-header-menu-link" href={buildProfHref({ tab: "finance", agendaView, agendaDate })}>
              {uiText(language, "teacher.balance")}
            </Link>
            <Link className="teacher-header-menu-link" href={buildProfHref({ tab: "notes", agendaView, agendaDate })}>
              {uiText(language, "teacher.notes")}
            </Link>
            <AppInstallMenuLink
              language={language}
              href={`${buildProfHref({ tab: "profile", agendaView, agendaDate })}#prof-mobile-app`}
            />
            <form action={logoutAction} data-mobile-push-logout="true">
              <button className="ghost teacher-header-menu-btn" type="submit">
                {uiText(language, "common.logout")}
              </button>
            </form>
          </div>
        }
      />

      <section className="teacher-brand-banner card">
        <PortalBrandLockup
          title={uiText(language, "common.app_name")}
          subtitle={uiText(language, "teacher.portal_subtitle")}
          eyebrow="Mi-Young Lee"
          tone="dark"
          compact
        />
        <div className="teacher-brand-banner-copy">
          <strong>{fullName || uiText(language, "teacher.default_name")}</strong>
          <small>{profile.email}</small>
        </div>
      </section>

      <section className="card prof-nav teacher-desktop-nav">
        {navTabs.map((tab) => (
          <Link
            key={tab.id}
            className={`prof-nav-link ${currentTab === tab.id ? "active" : ""}`}
            href={buildProfHref({ tab: tab.id, agendaView, agendaDate })}
          >
            <span aria-hidden>{tab.icon}</span>
            {tab.label}
          </Link>
        ))}
        <Link className="prof-nav-link" href="/prof/statements">
          <span aria-hidden>🧾</span>
          {uiText(language, "teacher.statements")}
        </Link>
      </section>

      <BottomTabs
        activeId={currentTab}
        ariaLabel={uiText(language, "portal.mobile_teacher_nav")}
        items={[
          { id: "overview", label: uiText(language, "teacher.todo"), icon: "📌", href: buildProfHref({ tab: "overview", agendaView, agendaDate }) },
          { id: "planning", label: uiText(language, "teacher.planning"), icon: "📅", href: buildProfHref({ tab: "planning", agendaView, agendaDate }) },
          { id: "notes", label: uiText(language, "teacher.notes"), icon: "📝", href: buildProfHref({ tab: "notes", agendaView, agendaDate }) },
          { id: "messages", label: uiText(language, "teacher.messages"), icon: "✉️", href: buildProfHref({ tab: "messages", agendaView, agendaDate }) },
          { id: "profile", label: uiText(language, "teacher.profile"), icon: "👤", href: buildProfHref({ tab: "profile", agendaView, agendaDate }) },
        ]}
      />

      <ProfessorMobilePushRegistration language={language} />
      <PresenceHeartbeat />

      {isImpersonating ? (
        <PortalImpersonationBanner displayName={impersonationDisplayName} returnTo={impersonationReturnTo} language={language} />
      ) : null}

      {okMessage ? <AlertCard tone="ok">{okMessage}</AlertCard> : null}
      {errorMessage ? <AlertCard tone="error">{errorMessage}</AlertCard> : null}
      {!sessionsResult.ok ? <AlertCard tone="error">{t("teacher.schedule_error")}: {sessionsResult.message}</AlertCard> : null}
      {!pendingResult.ok ? <AlertCard tone="error">{t("teacher.attendance_error")}: {pendingResult.message}</AlertCard> : null}
      {!balanceResult.ok ? <AlertCard tone="error">{t("teacher.balance_error")}: {balanceResult.message}</AlertCard> : null}
      {!messagesResult.ok ? <AlertCard tone="error">{t("teacher.messages_error")}: {messagesResult.message}</AlertCard> : null}
      {currentTab === "messages" && !inboxResult.ok ? <AlertCard tone="error">{t("teacher.inbox_error")}: {inboxResult.message}</AlertCard> : null}
      {currentTab === "notes" && !notesResult.ok ? <AlertCard tone="error">{t("teacher.notes_error")}: {notesResult.message}</AlertCard> : null}
      {!contractGridsResult.ok ? <AlertCard tone="error">{t("teacher.statement_contract_grid_error")}: {contractGridsResult.message}</AlertCard> : null}
      {!catalogStudentsResult.ok ? <AlertCard tone="error">{t("teacher.catalog_students_error")}: {catalogStudentsResult.message}</AlertCard> : null}
      {!catalogProductsResult.ok ? <AlertCard tone="error">{t("teacher.catalog_products_error")}: {catalogProductsResult.message}</AlertCard> : null}
      {!catalogRequestsResult.ok ? <AlertCard tone="error">{t("teacher.catalog_requests_error")}: {catalogRequestsResult.message}</AlertCard> : null}
      {!localIntakesResult.ok ? <AlertCard tone="error">Confirmations Bar-le-Duc : {localIntakesResult.message}</AlertCard> : null}

      {currentTab === "overview" ? (
        <section className="teacher-section-stack">
          {professorNews.length > 0 ? (
            <ActionCard title={language === "en" ? "School news" : "Actualités de l’école"} subtitle={language === "en" ? "Information for professors" : "Informations destinées aux professeurs"}>
              <div className="client-news-list">
                {professorNews.map((article) => (
                  <article className={`client-news-card ${article.is_pinned ? "is-pinned" : ""}`} key={article.id}>
                    <h2>{article.title}</h2>
                    {article.summary ? <p className="client-news-summary">{article.summary}</p> : null}
                    <div className="client-news-body">{article.body}</div>
                    {article.link_url ? <a className="mode-link client-news-link" href={article.link_url} target="_blank" rel="noreferrer">{article.link_label || (language === "en" ? "Learn more" : "En savoir plus")}</a> : null}
                  </article>
                ))}
              </div>
            </ActionCard>
          ) : null}
          {pendingLocalIntakes.length > 0 ? (
            <ActionCard
              title="Confirmations Bar-le-Duc"
              subtitle="Choisissez le créneau et la partition à prévoir pour chaque nouvel intake."
              chips={<StatChip label="À confirmer" value={pendingLocalIntakes.length} tone="warn" />}
            >
              <div className="list teacher-list-compact">
                {pendingLocalIntakes.map((intake) => (
                  <ListRow
                    key={intake.id}
                    left={(
                      <Link href={`/prof/intakes/${intake.id}`}>
                        {intake.child_label || intake.prospect_label}
                      </Link>
                    )}
                    subtitle={[intake.requested_summary, intake.prospect_label].filter(Boolean).join(" · ")}
                    right={(
                      <div className="teacher-intake-list-actions">
                        <span className="status-pill status-warn">À confirmer</span>
                        <Link
                          className="mode-link"
                          href={buildProfHref({
                            tab: "overview",
                            agendaView,
                            agendaDate,
                            intakeDetail: intake.id,
                          })}
                        >
                          Voir la demande
                        </Link>
                      </div>
                    )}
                  />
                ))}
              </div>
            </ActionCard>
          ) : null}
          <ActionCard
            title={t("teacher.today_title")}
            subtitle={t("teacher.today_subtitle")}
            chips={
              <>
                <StatChip label={t("teacher.attendance_chip")} value={pendingCount} tone={pendingCount > 0 ? "warn" : "ok"} />
                <StatChip label={t("teacher.todays_lessons_chip")} value={todaySessions.length} />
                <StatChip label={t("teacher.access_rights_chip")} value={canEditPlanning ? t("teacher.edit_mode") : t("teacher.read_mode")} />
              </>
            }
            action={
              <Link className="mode-link teacher-cta-full" href={buildProfHref({ tab: "planning", agendaView: "day", agendaDate: todayKeyUtc() })}>
                {t("teacher.open_schedule")}
              </Link>
            }
          >
            {pendingRows.length === 0 ? (
              <p className="muted">{t("teacher.no_pending_entry")}</p>
            ) : (
              <div className="list teacher-list-compact">
                {pendingRows.map((row) => {
                  const dayKey = row.start_at_utc.slice(0, 10);
                  const href = buildProfHref({
                    tab: "planning",
                    agendaView: "day",
                    agendaDate: dayKey,
                    sessionId: row.session_id,
                  });
                  return (
                    <ListRow
                      key={row.session_id}
                      href={href}
                      left={row.title}
                      subtitle={`${formatDateTime(row.start_at_utc, language)} - ${formatTime(row.end_at_utc, language)} | ${row.course_type_name} | ${row.location_name}`}
                      right={
                        <span className="status-pill status-warn">
                          {t("teacher.to_fill_progress", {
                            pending: row.pending_students_count,
                            total: row.total_students_count,
                          })}
                        </span>
                      }
                    />
                  );
                })}
              </div>
            )}
          </ActionCard>
        </section>
      ) : null}

      {currentTab === "planning" ? (
        <section className="card teacher-planning-card">
          <div className="row spread teacher-planning-head">
            <h2>{t("teacher.upcoming_lessons")}</h2>
            <span className="badge">{agendaRange.title}</span>
          </div>

          {canViewAllSchoolSessions ? (
            <nav className="teacher-planning-scope-toggle" aria-label={t("teacher.planning_scope_label")}>
              <Link
                className={`mode-link ${planningScope === "mine" ? "mode-active" : ""}`}
                href={buildProfHref({ tab: "planning", agendaView, agendaDate, planningScope: "mine" })}
              >
                {t("teacher.planning_scope_mine")}
              </Link>
              <Link
                className={`mode-link ${planningScope === "all" ? "mode-active" : ""}`}
                href={buildProfHref({ tab: "planning", agendaView, agendaDate, planningScope: "all" })}
              >
                {t("teacher.planning_scope_all")}
              </Link>
            </nav>
          ) : null}

          <form method="get" className="grid cols-4 teacher-planning-controls">
            <input type="hidden" name="tab" value="planning" />
            <input type="hidden" name="planning_scope" value={planningScope} />
            <label>
              {t("teacher.view_label")}
              <AutoSubmitSelect
                name="agenda_view"
                defaultValue={agendaView}
                options={[
                  { value: "agenda", label: t("teacher.upcoming_lessons_14_days") },
                  { value: "week", label: t("teacher.week") },
                  { value: "day", label: t("teacher.day") },
                ]}
              />
            </label>
            <label>
              {t("teacher.reference_date_utc")}
              <AutoSubmitInput
                type="date"
                name="agenda_date"
                defaultValue={agendaDate}
                ariaLabel={t("teacher.reference_date_utc")}
              />
            </label>
            <div className="row teacher-planning-controls-actions">
              <Link className="reset-link" href={todayAgendaHref}>
                {uiText(language, "client.today")}
              </Link>
            </div>
            <div className="row teacher-planning-controls-arrows">
              <Link className="mode-link" href={previousAgendaHref}>
                ←
              </Link>
              <Link className="mode-link" href={nextAgendaHref}>
                →
              </Link>
            </div>
          </form>
          <p className="muted">{t("teacher.planning_help")}</p>

          <div className={`agenda-grid coach-agenda-grid agenda-grid-${agendaView === "agenda" ? "month" : agendaView}`}>
            {agendaCardDays.map((day) => (
              <MonthDayCard
                key={day.key}
                language={language}
                dayLabel={day.label}
                events={day.events}
                isToday={day.key === todayKeyUtc()}
                maxVisibleEvents={maxVisibleSessionsByDay}
                expanded={agendaView !== "agenda"}
                dayDetailsHref={buildProfHref({ tab: "planning", agendaView, agendaDate, dayDetails: day.key, planningScope })}
                openSessionHref={(sessionId) =>
                  buildProfHref({
                    tab: "planning",
                    agendaView,
                    agendaDate,
                    sessionId,
                    dayDetails: "",
                    planningScope,
                  })
                }
              />
            ))}
          </div>

          <DayEventsDrawer
            language={language}
            isOpen={Boolean(selectedDayDetails && !selectedSession)}
            dayLabel={selectedDayDetails ? selectedDayDetails.label : ""}
            events={selectedDayDetails ? selectedDayDetails.events : []}
            closeHref={buildProfHref({ tab: "planning", agendaView, agendaDate, dayDetails: "", planningScope })}
            openSessionHref={(sessionId) =>
              buildProfHref({
                tab: "planning",
                agendaView,
                agendaDate,
                sessionId,
                dayDetails: "",
                planningScope,
              })
            }
          />
        </section>
      ) : null}

      {currentTab === "catalog" ? (
        <section className="grid cols-2 teacher-catalog-layout">
          <ActionCard
            title={t("teacher.catalog_request_title")}
            subtitle={t("teacher.catalog_request_subtitle")}
            action={
              <StickyActionBar>
                <button type="submit" form="teacher-catalog-request-form">
                  {t("teacher.send_request")}
                </button>
              </StickyActionBar>
            }
          >
            <form id="teacher-catalog-request-form" action={professorCreateCatalogRequestAction} className="grid teacher-form-stack">
              <input type="hidden" name="return_to" value={buildProfHref({ tab: "catalog", agendaView, agendaDate })} />
              <label>
                {t("teacher.student_label")}
                <select name="student_user_id" required defaultValue="">
                  <option value="">{t("teacher.select_student")}</option>
                  {catalogStudents.map((row) => (
                    <option key={row.user_id} value={row.user_id}>
                      {row.display_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("teacher.product_label")}
                <select name="product_id" required defaultValue="">
                  <option value="">{t("teacher.select_product")}</option>
                  {catalogProducts.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.title}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("teacher.delivery_location")}
                <select name="location_id" required defaultValue="">
                  <option value="">{t("teacher.select_location")}</option>
                  {catalogLocations.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("teacher.quantity")}
                <input type="number" name="quantity" min={1} step={1} defaultValue={1} required />
              </label>
              <label>
                {t("teacher.optional_note")}
                <textarea name="note" rows={3} maxLength={2000} />
              </label>
            </form>
          </ActionCard>

          <ActionCard title={t("teacher.products_to_deliver")} subtitle={t("teacher.products_to_deliver_subtitle")}>
            {catalogToDeliver.length === 0 ? (
              <p className="muted">{t("teacher.no_product_to_deliver")}</p>
            ) : (
              <>
                <div className="table-wrap teacher-desktop-table">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>{uiText(language, "common.date")}</th>
                        <th>{t("teacher.student_label")}</th>
                        <th>{t("teacher.product_label")}</th>
                        <th>{t("teacher.location")}</th>
                        <th>{t("teacher.quantity")}</th>
                        <th>{t("teacher.stock")}</th>
                        <th>{uiText(language, "common.status")}</th>
                        <th>{uiText(language, "client.action")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {catalogToDeliver.map((row) => {
                        const lowOrNegative = (row.stock_estimated_quantity ?? 0) < 0;
                        return (
                          <tr key={row.id} className={lowOrNegative ? "catalog-stock-negative" : ""}>
                            <td>{formatDateTime(row.requested_at, language)}</td>
                            <td>{row.student_name}</td>
                            <td>{row.product_title}</td>
                            <td>{row.location_name}</td>
                            <td>{row.quantity}</td>
                            <td>
                              {row.stock_estimated_quantity ?? "-"}
                              {lowOrNegative ? <div className="catalog-stock-alert">{t("teacher.negative_stock")}</div> : null}
                            </td>
                            <td>{productRequestStatusLabel(row.status, language)}</td>
                            <td>
                              <form action={professorDeliverCatalogRequestAction} className="grid">
                                <input type="hidden" name="request_id" value={row.id} />
                                <input
                                  type="hidden"
                                  name="return_to"
                                  value={buildProfHref({ tab: "catalog", agendaView, agendaDate })}
                                />
                                <input type="text" name="note" maxLength={2000} placeholder={t("teacher.delivery_note_placeholder")} />
                                <button type="submit">{t("teacher.mark_delivered")}</button>
                              </form>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="teacher-mobile-card-list">
                  {catalogToDeliver.map((row) => {
                    const lowOrNegative = (row.stock_estimated_quantity ?? 0) < 0;
                    return (
                      <article key={`${row.id}-mobile`} className="item">
                        <p className="muted">{formatDateTime(row.requested_at, language)}</p>
                        <strong>{row.product_title}</strong>
                        <p className="muted">
                          {row.student_name} | {row.location_name} | {t("teacher.quantity_short", { quantity: row.quantity })}
                        </p>
                        <p className="muted">
                          {uiText(language, "common.status")}: {productRequestStatusLabel(row.status, language)} | {t("teacher.stock")}: {row.stock_estimated_quantity ?? "-"}
                        </p>
                        {lowOrNegative ? <p className="catalog-stock-alert">{t("teacher.negative_stock")}</p> : null}
                        <form action={professorDeliverCatalogRequestAction} className="grid top-gap-sm">
                          <input type="hidden" name="request_id" value={row.id} />
                          <input type="hidden" name="return_to" value={buildProfHref({ tab: "catalog", agendaView, agendaDate })} />
                          <input type="text" name="note" maxLength={2000} placeholder={t("teacher.delivery_note_placeholder")} />
                          <button type="submit">{t("teacher.mark_delivered")}</button>
                        </form>
                      </article>
                    );
                  })}
                </div>
              </>
            )}
          </ActionCard>

          <div className="span-2">
            <ActionCard title={t("teacher.catalog_history_title")} subtitle={t("teacher.catalog_history_subtitle")}>
              {catalogRequests.length === 0 ? (
                <p className="muted">{t("teacher.no_catalog_request")}</p>
              ) : (
                <>
                  <div className="table-wrap teacher-desktop-table">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>{uiText(language, "common.date")}</th>
                          <th>{t("teacher.source")}</th>
                          <th>{t("teacher.student_label")}</th>
                          <th>{t("teacher.product_label")}</th>
                          <th>{t("teacher.location")}</th>
                          <th>{t("teacher.quantity")}</th>
                          <th>{uiText(language, "common.status")}</th>
                          <th>{t("teacher.billing_label")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {catalogRequests.map((row) => (
                          <tr key={`${row.id}-history`}>
                            <td>{formatDateTime(row.requested_at, language)}</td>
                            <td>{productRequestSourceLabel(row.request_source, language)}</td>
                            <td>{row.student_name}</td>
                            <td>{row.product_title}</td>
                            <td>{row.location_name}</td>
                            <td>{row.quantity}</td>
                            <td>{productRequestStatusLabel(row.status, language)}</td>
                            <td>{row.should_bill === null ? "-" : row.should_bill ? t("teacher.yes") : t("teacher.no")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="list teacher-mobile-card-list">
                    {catalogRequests.map((row) => (
                      <ListRow
                        key={`${row.id}-list`}
                        left={row.product_title}
                        subtitle={`${formatDateTime(row.requested_at, language)} | ${row.student_name} | ${row.location_name}`}
                        right={
                          <span className="status-pill status-warn">
                            {productRequestStatusLabel(row.status, language)}
                          </span>
                        }
                      />
                    ))}
                  </div>
                </>
              )}
            </ActionCard>
          </div>
        </section>
      ) : null}

      {currentTab === "finance" ? (
        <section className="grid teacher-finance-layout">
          <ActionCard title={t("teacher.balance_title")} subtitle={t("teacher.balance_subtitle")}>
            {balanceResult.ok ? (
              <>
                <div className="teacher-stat-grid">
                  <StatCard
                    label={t("teacher.pending")}
                    value={formatMoneyEurLike(balanceResult.data.pending_amount, balanceResult.data.currency, language)}
                    hint={t("teacher.lessons_count", { count: balanceResult.data.pending_sessions })}
                  />
                  <StatCard
                    label={t("teacher.approved")}
                    value={formatMoneyEurLike(balanceResult.data.approved_amount, balanceResult.data.currency, language)}
                    hint={t("teacher.lessons_count", { count: balanceResult.data.approved_sessions })}
                  />
                  <StatCard
                    label={t("teacher.paid")}
                    value={formatMoneyEurLike(balanceResult.data.paid_amount, balanceResult.data.currency, language)}
                    hint={t("teacher.lessons_count", { count: balanceResult.data.paid_sessions })}
                  />
                  <StatCard
                    label={t("teacher.total")}
                    value={formatMoneyEurLike(balanceResult.data.total_amount, balanceResult.data.currency, language)}
                    hint={t("teacher.currency_hint", { currency: balanceResult.data.currency })}
                  />
                </div>
              </>
            ) : (
              <p className="muted">{t("teacher.balance_unavailable")}</p>
            )}
          </ActionCard>

          <ActionCard title={t("teacher.payout_tracking_title")} subtitle={t("teacher.payout_tracking_subtitle")}>
            {payoutsResult.ok && payoutsResult.data.length > 0 ? (
              <div className="list teacher-list-compact">
                {payoutsResult.data.map((row) => (
                  <ListRow
                    key={row.payout_id}
                    left={formatMoneyEurLike(row.amount_snapshot, row.currency_snapshot, language)}
                    subtitle={`${row.course_type_name} - ${row.location_name} | ${formatDateTime(row.session_start_at_utc, language)}`}
                    right={
                      <span className={`status-pill ${payoutStatusBadgeClass(row.payout_status)}`}>
                        {payoutStatusLabel(row.payout_status, language)}
                      </span>
                    }
                  />
                ))}
              </div>
            ) : (
              <p className="muted">{t("teacher.no_payout")}</p>
            )}
          </ActionCard>

          <ActionCard title={t("teacher.compensation_grid_title")} subtitle={t("teacher.compensation_grid_subtitle")}>
            {contractGridsResult.ok && contractGridsResult.data.length > 0 ? (
              (() => {
                const grids = contractGridsResult.data;
                const firstGrid = grids[0];
                const periodLabel = firstGrid.valid_to
                  ? t("teacher.period_from_to", {
                      start: formatDateOnly(firstGrid.valid_from, language),
                      end: formatDateOnly(firstGrid.valid_to, language),
                    })
                  : t("teacher.period_from", {
                      start: formatDateOnly(firstGrid.valid_from, language),
                    });

                const seen = new Set<string>();
                const lines = grids.flatMap((grid) => grid.lines).filter((line) => {
                  const key = `${line.course_type_id ?? line.service_type}:${line.mode}:${line.reference_duration_minutes ?? "-"}`;
                  if (seen.has(key)) {
                    return false;
                  }
                  seen.add(key);
                  return true;
                });

                return (
                  <>
                    <article className="item">
                      <strong>{t("teacher.applicable_period")}</strong>
                      <p className="muted top-gap-sm">{periodLabel}</p>
                    </article>

                    <div className="list top-gap-sm">
                      {lines.map((line, index) => {
                        const title = line.course_type_name || line.service_type;
                        const modeLabel = professorModeLabel(line.mode, language);
                        const durationLabel = line.reference_duration_minutes ? `${line.reference_duration_minutes} min` : "-";
                        const gridRows =
                          line.rules.length > 0
                            ? line.rules.map((rule) => formatRuleLabel(rule, profile.payout_currency, language))
                            : line.default_hourly_rate
                              ? [t("teacher.hourly_rate_label", { amount: formatMoneyEurLike(line.default_hourly_rate, profile.payout_currency, language) })]
                              : [t("teacher.no_rate_available")];

                        return (
                          <article key={`prof-rate-line-${index}-${title}`} className="item">
                            <strong>{title}</strong>
                            <p className="muted top-gap-sm">
                              {modeLabel} • {durationLabel}
                            </p>
                            <p className="muted top-gap-sm">
                              <strong>{t("teacher.active_grid")}</strong>
                            </p>
                            <ul className="top-gap-sm">
                              {gridRows.map((row) => (
                                <li key={`${title}-${row}`}>{row}</li>
                              ))}
                            </ul>
                          </article>
                        );
                      })}
                    </div>
                  </>
                );
              })()
            ) : (
              <p className="muted">{t("teacher.no_active_compensation_grid")}</p>
            )}
          </ActionCard>
        </section>
      ) : null}

      {currentTab === "notes" ? (
        <section className="teacher-section-stack">
          <ActionCard title={t("teacher.notes_title")} subtitle={t("teacher.notes_subtitle")}>
            <form method="get" className="teacher-notes-filter-form">
              <input type="hidden" name="tab" value="notes" />
              <input type="hidden" name="agenda_view" value={agendaView} />
              <input type="hidden" name="agenda_date" value={agendaDate} />
              <label className="teacher-notes-search-field">
                {t("teacher.notes_search")}
                <input
                  type="search"
                  name="note_q"
                  defaultValue={readParam(searchParams, "note_q")}
                  placeholder={t("teacher.notes_search_placeholder")}
                />
              </label>
              <div className="teacher-notes-filter-grid">
                <label>
                  {t("teacher.notes_type")}
                  <select name="note_type" defaultValue={noteType}>
                    <option value="ALL">{t("teacher.notes_type_all")}</option>
                    <option value="SESSION">{t("teacher.notes_type_session")}</option>
                    <option value="STUDENT">{t("teacher.notes_type_student")}</option>
                  </select>
                </label>
                <label>
                  {t("teacher.notes_period")}
                  <select name="note_period" defaultValue={notePeriod}>
                    <option value="ALL">{t("teacher.notes_period_all")}</option>
                    <option value="30">{t("teacher.notes_period_30")}</option>
                    <option value="90">{t("teacher.notes_period_90")}</option>
                    <option value="365">{t("teacher.notes_period_365")}</option>
                  </select>
                </label>
                <label>
                  {t("teacher.notes_location")}
                  <select name="note_location" defaultValue={noteLocation}>
                    <option value="">{t("teacher.notes_location_all")}</option>
                    {noteLocationOptions.map((location) => (
                      <option key={location.id} value={location.id}>{location.name}</option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="teacher-notes-filter-actions">
                <button type="submit">{t("teacher.notes_apply")}</button>
                <Link className="mode-link" href={buildProfHref({ tab: "notes", agendaView, agendaDate })}>
                  {t("teacher.notes_reset")}
                </Link>
              </div>
            </form>
          </ActionCard>

          <ActionCard
            title={t("teacher.notes_results", { count: filteredInternalNotes.length })}
            subtitle={t("teacher.notes_results_subtitle")}
          >
            {filteredInternalNotes.length > 0 ? (
              <div className="teacher-note-history-list">
                {filteredInternalNotes.map((note) => {
                  const isStudentNote = note.note_type === "STUDENT";
                  const lessonDay = note.session_start_at_utc.slice(0, 10);
                  return (
                    <article key={note.id} className="teacher-note-history-card">
                      <header className="teacher-note-history-head">
                        <span className={`status-pill ${isStudentNote ? "status-info" : "status-warn"}`}>
                          {isStudentNote ? t("teacher.notes_type_student") : t("teacher.notes_type_session")}
                        </span>
                        <time dateTime={note.session_start_at_utc}>{formatDateTime(note.session_start_at_utc, language)}</time>
                      </header>
                      <div className="teacher-note-history-title">
                        <strong>{isStudentNote ? note.student_display_name ?? t("teacher.student_label") : t("teacher.notes_group_label")}</strong>
                        <span className="muted">{note.session_title} · {note.course_type_name} · {note.location_name}</span>
                      </div>
                      <p className="teacher-note-history-body">{note.body}</p>
                      <Link
                        className="mode-link teacher-note-history-link"
                        href={buildProfHref({
                          tab: "planning",
                          agendaView: "day",
                          agendaDate: lessonDay,
                          sessionId: note.session_id,
                        })}
                      >
                        {t("teacher.notes_open_course")}
                      </Link>
                    </article>
                  );
                })}
              </div>
            ) : (
              <p className="muted">{t("teacher.notes_no_result")}</p>
            )}
          </ActionCard>
        </section>
      ) : null}

      {currentTab === "messages" ? (
        <section className="teacher-section-stack">
          <ActionCard title={t("teacher.inbox_messages")} subtitle={t("teacher.inbox_messages_subtitle")}>
            {inboxMessages.length > 0 ? (
              <div className="list teacher-list-compact">
                {inboxMessages.map((message) => (
                  <details className="teacher-inbox-message item" key={`${message.channel}-${message.id}`}>
                    <summary>
                      <span>
                        <strong>{message.subject}</strong>
                        <small className="muted">{formatDateTime(message.sent_at, language)}</small>
                      </span>
                      <span className="badge">{message.channel === "PUSH" ? t("teacher.push_channel") : message.channel}</span>
                    </summary>
                    {message.body_format === "HTML" ? (
                      <article className="teacher-inbox-message-body" dangerouslySetInnerHTML={{ __html: sanitizeRichHtml(message.body) }} />
                    ) : (
                      <p className="teacher-inbox-message-body">{message.body}</p>
                    )}
                  </details>
                ))}
              </div>
            ) : (
              <p className="muted">{t("teacher.no_inbox_message")}</p>
            )}
          </ActionCard>

          <ActionCard title={t("teacher.sent_messages")} subtitle={t("teacher.archived_messages_subtitle")}>
          {messagesResult.ok && archivedMessages.length > 0 ? (
            <div className="list teacher-list-compact">
              {archivedMessages.map((message) => {
                const parsedSubject = parseMessageSubject(message.subject);
                return (
                  <ListRow
                    key={message.id}
                    href={buildProfHref({ tab: "messages", agendaView, agendaDate, messageId: message.id })}
                    left={parsedSubject.cleanedSubject}
                    subtitle={`${t("teacher.sent_on", { date: formatDateTime(message.sent_at, language) })} | ${t("teacher.format_label", { format: message.body_format })}`}
                    right={
                      <div className="row">
                        <span className="badge">
                          {parsedSubject.targetLabel === "Administration"
                            ? t("teacher.admin_target")
                            : parsedSubject.targetLabel
                              ? t("teacher.student_target", { name: parsedSubject.targetLabel })
                              : t("teacher.group_target")}
                        </span>
                        <span className="badge">{t("teacher.recipient_count", { count: message.recipient_count })}</span>
                      </div>
                    }
                  />
                );
              })}
            </div>
          ) : (
            <p className="muted">{t("teacher.no_archived_message")}</p>
          )}
          </ActionCard>
        </section>
      ) : null}

      {currentTab === "profile" ? (
        <section className="teacher-section-stack">
          <AppInstallCard language={language} />

          <SectionAccordion title={t("teacher.my_profile")} subtitle={t("teacher.main_information")} defaultOpen={true}>
            <div className="list teacher-list-compact teacher-profile-list">
              <ListRow left={t("teacher.name")} right={fullName || "-"} />
              <ListRow left={uiText(language, "common.email")} right={profile.email} />
              <ListRow left={t("teacher.phone")} right={profile.phone ?? t("teacher.not_provided")} />
              <ListRow left={t("teacher.zoom_link")} right={profile.zoom_link ?? t("teacher.not_provided")} />
              <ListRow left={t("teacher.languages")} right={profile.spoken_languages.length > 0 ? profile.spoken_languages.join(", ") : t("teacher.not_provided")} />
              <ListRow left={t("teacher.contract_currency")} right={profile.payout_currency} />
            </div>
          </SectionAccordion>

          <SectionAccordion title={t("teacher.daily_schedule_email")} subtitle={t("teacher.admin_setting")} defaultOpen={false}>
            <div className="list teacher-list-compact">
              <ListRow left={t("teacher.activation")} right={profile.daily_schedule_email_enabled ? t("teacher.enabled") : t("teacher.disabled")} />
              <ListRow left={t("teacher.utc_time")} right={profile.daily_schedule_email_time} />
              <ListRow left={t("teacher.skip_days_without_course")} right={profile.daily_schedule_skip_if_no_course ? t("teacher.yes") : t("teacher.no")} />
            </div>
            <p className="muted top-gap-sm">
              {t("teacher.digest_help")}
            </p>
          </SectionAccordion>
        </section>
      ) : null}

      {currentTab === "planning" && selectedSession ? (
        <section className="modal-overlay modal-overlay-front teacher-attendance-overlay">
          <article className="modal-panel session-attendance-modal-v2 teacher-attendance-modal">
            <header className="teacher-attendance-header">
              <div className="teacher-attendance-header-main">
                <h2 className="modal-title">{t("teacher.attendance_title")}</h2>
                <p className="muted">
                  {formatDateTime(selectedSession.start_at_utc, language)} - {formatTime(selectedSession.end_at_utc, language)} · {selectedSession.location.name}
                  {planningScope === "all" && selectedSession.effective_teacher_display_name
                    ? ` · ${t("teacher.teacher_short")} ${selectedSession.effective_teacher_display_name}`
                    : ""}
                </p>
              </div>
              <div className="teacher-attendance-header-meta">
                <span className={`occ-badge ${selectedSessionReservedCount >= selectedSession.capacity_max ? "occ-high" : "occ-low"}`}>
                  {selectedSessionReservedCount}/{selectedSession.capacity_max}
                </span>
                <span className="status-badge status-waitlist">{t("teacher.to_fill_count", { count: selectedSessionPendingCount })}</span>
                <Link
                  className="modal-close-x"
                  href={buildProfHref({ tab: "planning", agendaView, agendaDate, planningScope })}
                  aria-label={uiText(language, "common.close")}
                >
                  ×
                </Link>
              </div>
            </header>

            <div className="teacher-attendance-body">
              <section className="teacher-attendance-primary">
                <div className="teacher-attendance-toolbar">
                  <div className="teacher-attendance-filters">
                    <Link
                      className={`mode-link ${attendanceFilter === "all" ? "mode-active" : ""}`}
                      href={buildProfHref({ tab: "planning", agendaView, agendaDate, sessionId: selectedSession.id, attendanceFilter: "all", planningScope })}
                    >
                      {t("teacher.all_filter")}
                    </Link>
                    <Link
                      className={`mode-link ${attendanceFilter === "missing" ? "mode-active" : ""}`}
                      href={buildProfHref({ tab: "planning", agendaView, agendaDate, sessionId: selectedSession.id, attendanceFilter: "missing", planningScope })}
                    >
                      {t("teacher.missing_filter")}
                    </Link>
                  </div>
                  {canTakeAttendanceForSelectedSession && editableAttendanceStudents.length > 0 ? (
                    <span className="status-badge status-scheduled">{t("teacher.one_tap_per_student")}</span>
                  ) : planningScope === "all" && !selectedSessionBelongsToProfessor ? (
                    <span className="status-badge status-scheduled">{t("teacher.planning_read_only_course")}</span>
                  ) : null}
                </div>

                {visibleAttendanceStudents.length === 0 ? (
                  <div className="teacher-attendance-empty">
                    <p className="muted">
                      {attendanceFilter === "missing" ? t("teacher.no_missing_attendance") : t("teacher.no_student_registered")}
                    </p>
                  </div>
                ) : (
                  <div className="teacher-attendance-rows">
                    {visibleAttendanceStudents.map((student) => (
                      <article key={student.booking_id} className="teacher-attendance-row-card">
                        <div className="teacher-attendance-row-head">
                          <div className="teacher-attendance-row-identity">
                            <strong>{student.display_name}</strong>
                            <small className="muted">{t("teacher.student_id_short", { id: student.user_id.slice(0, 8) })}</small>
                          </div>
                          <div className="teacher-attendance-row-tags">
                            <span className={`status-pill attendance-pill-${attendanceRowTone(student.attendance_status)}`}>
                              {attendanceLabel(student.attendance_status, language)}
                            </span>
                            {student.is_first_course ? <span className="status-pill status-ok">{t("teacher.first_lesson")}</span> : null}
                            {student.is_trial_course ? <span className="status-pill status-warn">{t("teacher.trial")}</span> : null}
                          </div>
                        </div>

                        {student.attendance_status === "WAITLISTED" ? (
                          <p className="muted">{t("teacher.waitlist_student_readonly")}</p>
                        ) : canTakeAttendanceForSelectedSession ? (
                          <div className="teacher-attendance-segment-grid">
                            {[
                              { value: "ATTENDED", label: t("teacher.present"), tone: "ok" },
                              { value: "EXCUSED_ABSENCE", label: t("teacher.excused"), tone: "neutral" },
                              { value: "NO_SHOW", label: t("teacher.unexcused"), tone: "danger" },
                            ].map((choice) => (
                              <form key={`${student.booking_id}-${choice.value}`} action={professorUpdateAttendanceAction}>
                                <input type="hidden" name="booking_id" value={student.booking_id} />
                                <input type="hidden" name="attendance_status" value={choice.value} />
                                <input
                                  type="hidden"
                                  name="return_to"
                                  value={buildProfHref({
                                    tab: "planning",
                                    agendaView,
                                    agendaDate,
                                    sessionId: selectedSession.id,
                                    attendanceFilter,
                                    planningScope,
                                  })}
                                />
                                <button
                                  type="submit"
                                  className={`teacher-attendance-btn tone-${choice.tone} ${
                                    student.attendance_status === choice.value ? "active" : ""
                                  }`}
                                >
                                  {choice.label}
                                </button>
                              </form>
                            ))}
                          </div>
                        ) : (
                          <p className="muted">{t("teacher.read_only")}</p>
                        )}

                        {student.attendance_status !== "WAITLISTED" && canTakeAttendanceForSelectedSession ? (
                          <details className="teacher-student-note">
                            <summary>
                              <span>{t("teacher.student_internal_note")}</span>
                              <span className={`status-pill ${student.internal_note ? "status-ok" : "status-scheduled"}`}>
                                {student.internal_note ? t("teacher.note_entered") : t("teacher.add_note")}
                              </span>
                            </summary>
                            <form action={professorUpdateBookingInternalNoteAction} className="teacher-student-note-form">
                              <input type="hidden" name="session_id" value={selectedSession.id} />
                              <input type="hidden" name="booking_id" value={student.booking_id} />
                              <input
                                type="hidden"
                                name="return_to"
                                value={buildProfHref({
                                  tab: "planning",
                                  agendaView,
                                  agendaDate,
                                  sessionId: selectedSession.id,
                                  attendanceFilter,
                                  planningScope,
                                })}
                              />
                              <p className="teacher-note-safety-text teacher-note-safety-internal">
                                {t("teacher.student_internal_note_help")}
                              </p>
                              <textarea
                                name="internal_note"
                                rows={3}
                                maxLength={12000}
                                defaultValue={student.internal_note ?? ""}
                                placeholder={t("teacher.student_internal_note_placeholder")}
                              />
                              <button type="submit" className="ghost">{t("teacher.save")}</button>
                            </form>
                          </details>
                        ) : null}
                      </article>
                    ))}
                  </div>
                )}
              </section>

              <aside className="teacher-attendance-secondary">
                <details className="teacher-attendance-accordion" open={selectedSessionMessages.length > 0}>
                  <summary>{t("teacher.session_messages_section")}</summary>
                  <div className="teacher-attendance-accordion-body">
                    <p className="teacher-session-message-help">{t("teacher.session_messages_help")}</p>
                    {sentMessage && selectedSession && sentMessage.session_id === selectedSession.id ? (
                      <p className="teacher-message-sent-confirmation">
                        {t("teacher.sent_message_archived")}
                        {" "}
                        <Link
                          className="reset-link"
                          href={buildProfHref({ tab: "messages", agendaView, agendaDate, messageId: sentMessage.id })}
                        >
                          {t("teacher.open_message")}
                        </Link>
                      </p>
                    ) : null}
                    {selectedSessionMessages.length > 0 ? (
                      <div className="teacher-session-message-list">
                        {selectedSessionMessages.slice(0, 5).map((message) => {
                          const parsedSubject = parseMessageSubject(message.subject);
                          const targetLabel =
                            parsedSubject.targetLabel === "Administration"
                              ? t("teacher.admin_target")
                              : parsedSubject.targetLabel
                                ? t("teacher.student_target", { name: parsedSubject.targetLabel })
                                : t("teacher.group_target");
                          const preview = plainMessagePreview(message.body, message.body_format);
                          return (
                            <article
                              key={message.id}
                              className={`teacher-session-message-card ${message.id === sentMessageId ? "teacher-session-message-card-highlight" : ""}`}
                            >
                              <div className="teacher-session-message-card-head">
                                <strong>{parsedSubject.cleanedSubject}</strong>
                                <span className="badge">{targetLabel}</span>
                              </div>
                              <p className="muted">
                                {t("teacher.sent_on", { date: formatDateTime(message.sent_at, language) })} ·{" "}
                                {t("teacher.recipient_count", { count: message.recipient_count })}
                              </p>
                              <p className="teacher-session-message-preview">{preview || "-"}</p>
                              <Link
                                className="reset-link"
                                href={buildProfHref({ tab: "messages", agendaView, agendaDate, messageId: message.id })}
                              >
                                {t("teacher.open_message")}
                              </Link>
                            </article>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="muted">{t("teacher.no_session_message")}</p>
                    )}
                  </div>
                </details>

                {canTakeAttendanceForSelectedSession ? (
                  <details className="teacher-attendance-accordion" open>
                    <summary>{t("teacher.session_internal_note_section")}</summary>
                    <div className="teacher-attendance-accordion-body">
                      <p className="teacher-note-safety-text teacher-note-safety-internal">{t("teacher.session_internal_note_help")}</p>
                      <form action={professorUpdateSessionInternalNoteAction} className="grid">
                        <input type="hidden" name="session_id" value={selectedSession.id} />
                        <input
                          type="hidden"
                          name="return_to"
                          value={buildProfHref({ tab: "planning", agendaView, agendaDate, sessionId: selectedSession.id, attendanceFilter, planningScope })}
                        />
                        <label>
                          {t("teacher.session_internal_note")}
                          <textarea
                            name="internal_note"
                            rows={4}
                            maxLength={12000}
                            defaultValue={selectedSession.internal_note ?? ""}
                            placeholder={t("teacher.session_internal_note_placeholder")}
                          />
                        </label>
                        <div className="row">
                          <button type="submit" className="ghost">
                            {t("teacher.save")}
                          </button>
                        </div>
                      </form>
                    </div>
                  </details>
                ) : null}

                {canMessageSelectedSession ? (
                  <details className="teacher-attendance-accordion">
                    <summary>{t("teacher.notify_students_section")}</summary>
                    <div className="teacher-attendance-accordion-body">
                      <p className="teacher-note-safety-text teacher-note-safety-family">{t("teacher.notify_students_help")}</p>
                      <form action={professorSendSessionMessageAction} className="grid">
                        <input type="hidden" name="session_id" value={selectedSession.id} />
                        <input
                          type="hidden"
                          name="return_to"
                          value={buildProfHref({ tab: "planning", agendaView, agendaDate, sessionId: selectedSession.id, attendanceFilter, planningScope })}
                        />
                        <input type="hidden" name="recipient_target" value="GROUP" />
                        <label>
                          {t("teacher.subject")}
                          <input
                            type="text"
                            name="subject"
                            required
                            maxLength={255}
                            defaultValue={t("teacher.message_students_subject", { title: selectedSession.title })}
                          />
                        </label>
                        <label>
                          {t("teacher.message_students")}
                          <input type="hidden" name="body_format" value="TEXT" />
                          <textarea name="body" rows={4} maxLength={12000} placeholder={t("teacher.message_students_placeholder")} required />
                        </label>
                        <div className="row">
                          <button type="submit" className="primary">
                            {t("teacher.send_students_message")}
                          </button>
                        </div>
                      </form>
                    </div>
                  </details>
                ) : null}

                {canEditSelectedSession && selectedSession.status !== "CANCELLED" ? (
                  <details className="teacher-attendance-accordion teacher-attendance-accordion-danger">
                    <summary>{t("teacher.teacher_absence")}</summary>
                    <div className="teacher-attendance-accordion-body">
                      <form action={professorMarkSessionAbsentAction} className="grid">
                        <input type="hidden" name="session_id" value={selectedSession.id} />
                        <input
                          type="hidden"
                          name="return_to"
                          value={buildProfHref({ tab: "planning", agendaView, agendaDate, sessionId: selectedSession.id, attendanceFilter, planningScope })}
                        />
                        <label className="checkline">
                          <input type="checkbox" name="notify_students" />
                          {t("teacher.notify_students")}
                        </label>
                        <label>
                          {t("teacher.subject_optional")}
                          <input type="text" name="students_subject" maxLength={255} />
                        </label>
                        <label>
                          {t("teacher.message_optional")}
                          <input type="hidden" name="students_format" value="TEXT" />
                          <textarea name="students_message" rows={4} maxLength={12000} placeholder={t("teacher.message_students_placeholder")} />
                        </label>
                        <details className="teacher-attendance-confirm">
                          <summary className="danger-link">{t("teacher.declare_teacher_absence")}</summary>
                          <div className="teacher-attendance-confirm-body">
                            <p className="muted">{t("teacher.session_will_be_cancelled")}</p>
                            <button type="submit" className="danger">
                              {t("teacher.confirm_teacher_absence")}
                            </button>
                          </div>
                        </details>
                      </form>
                    </div>
                  </details>
                ) : null}

                <details className="teacher-attendance-accordion">
                  <summary>{t("teacher.slot_details")}</summary>
                  <div className="teacher-attendance-accordion-body teacher-attendance-details-list">
                    <p>
                      <strong>{t("teacher.activity")}:</strong> {selectedSession.course_type.name}
                    </p>
                    <p>
                      <strong>{uiText(language, "common.status")}:</strong> {statusLabel(selectedSessionDisplayStatus ?? selectedSession.status, language)}
                    </p>
                    <p>
                      <strong>{t("teacher.location")}:</strong> {selectedSession.location.name}
                    </p>
                    <p>
                      <strong>{t("teacher.teacher_label")}:</strong>{" "}
                      {selectedSession.effective_teacher_display_name || fullName || profile.email}
                    </p>
                    {selectedSession.zoom_link ? (
                      <p className="teacher-attendance-zoom-row">
                        <strong>{t("teacher.zoom_link")}:</strong>{" "}
                        <a href={selectedSession.zoom_link} target="_blank" rel="noreferrer">
                          {t("teacher.open_link")}
                        </a>
                      </p>
                    ) : null}
                  </div>
                </details>
              </aside>
            </div>

            <footer className="teacher-attendance-footer">
              <Link className="reset-link" href={buildProfHref({ tab: "planning", agendaView, agendaDate, planningScope })}>
                {uiText(language, "common.close")}
              </Link>
              <div className="row">
                {!selectedSessionBelongsToProfessor ? (
                  <span className="status-badge status-scheduled">{t("teacher.planning_read_only_course")}</span>
                ) : selectedSessionPendingCount > 0 ? (
                  <span className="status-badge status-waitlist">{t("teacher.to_fill_count", { count: selectedSessionPendingCount })}</span>
                ) : (
                  <span className="status-badge status-completed">{t("teacher.all_recorded")}</span>
                )}
                <Link className="mode-link" href={buildProfHref({ tab: "planning", agendaView, agendaDate, planningScope })}>
                  {t("teacher.finish")}
                </Link>
              </div>
            </footer>
          </article>
        </section>
      ) : null}

      {selectedLocalIntakeId && !selectedLocalIntakeResult.ok ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel modal-compact" role="dialog" aria-modal="true" aria-label="Demande indisponible">
            <Link
              className="modal-close-x"
              href={buildProfHref({ tab: "overview", agendaView, agendaDate })}
              aria-label="Fermer"
            >
              ×
            </Link>
            <h2 className="modal-title">Demande indisponible</h2>
            <AlertCard tone="error">Cette demande n’est plus disponible ou ne vous est pas affectée.</AlertCard>
          </article>
        </section>
      ) : null}

      {selectedLocalIntakeResult.ok && selectedLocalIntakeResult.data ? (
        <ProfessorLocalIntakeRequestModal
          intake={selectedLocalIntakeResult.data}
          closeHref={buildProfHref({ tab: "overview", agendaView, agendaDate })}
        />
      ) : null}

      {currentTab === "messages" && selectedMessage ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel modal-compact">
            <Link
              className="modal-close-x"
              href={buildProfHref({ tab: "messages", agendaView, agendaDate })}
              aria-label={uiText(language, "common.close")}
            >
              ×
            </Link>
            {(() => {
              const parsedSubject = parseMessageSubject(selectedMessage.subject);
              return (
                <>
                  <h3 className="modal-title">{parsedSubject.cleanedSubject}</h3>
                  <p className="muted">
                    {t("teacher.sent_on", { date: formatDateTime(selectedMessage.sent_at, language) })} |{" "}
                    {parsedSubject.targetLabel === "Administration"
                      ? t("teacher.admin_target")
                      : parsedSubject.targetLabel
                        ? t("teacher.student_target", { name: parsedSubject.targetLabel })
                        : t("teacher.group_target")}
                  </p>
                </>
              );
            })()}
            {selectedMessage.body_format === "HTML" ? (
              <article className="item" dangerouslySetInnerHTML={{ __html: sanitizeRichHtml(selectedMessage.body) }} />
            ) : (
              <article className="item">
                <p style={{ whiteSpace: "pre-wrap" }}>{selectedMessage.body}</p>
              </article>
            )}
          </article>
        </section>
      ) : null}
      <ProfessorHelpAssistant language={language} interfaceLabels={buildProfessorHelpLabels(language)} />
    </main>
  );
}
