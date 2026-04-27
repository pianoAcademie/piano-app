import Link from "next/link";
import { redirect } from "next/navigation";

import {
  logoutAction,
  professorCreateCatalogRequestAction,
  professorDeliverCatalogRequestAction,
  professorMarkSessionAbsentAction,
  professorSendSessionMessageAction,
  professorUpdateAttendanceAction,
} from "../../lib/actions";
import { backendRequest } from "../../lib/backend";
import AutoSubmitSelect from "../../components/auto-submit-select";
import DayEventsDrawer from "../../components/planning/day-events-drawer";
import MonthDayCard from "../../components/planning/month-day-card";
import PortalImpersonationBanner from "../../components/portal-impersonation-banner";
import ActionCard from "../../components/teacher-ui/action-card";
import AlertCard from "../../components/teacher-ui/alert-card";
import BottomTabs from "../../components/teacher-ui/bottom-tabs";
import ListRow from "../../components/teacher-ui/list-row";
import PageHeaderMobile from "../../components/teacher-ui/page-header-mobile";
import PortalBrandLockup from "../../components/portal-brand-lockup";
import SectionAccordion from "../../components/teacher-ui/section-accordion";
import StatCard from "../../components/teacher-ui/stat-card";
import StatChip from "../../components/teacher-ui/stat-chip";
import StickyActionBar from "../../components/teacher-ui/sticky-action-bar";
import { getPortalReturnTo, getPortalToken, readPortalImpersonationClaims } from "../../lib/auth-cookies";
import type { PlanningEventChipData } from "../../components/planning/month-event-chip";
import type {
  ProfessorAttendancePendingOut,
  ProfessorBalanceOut,
  ProfessorContractGridOut,
  AdminCatalogProductOut,
  AdminCatalogRequestOut,
  LocationOut,
  ProfessorMeOut,
  ProfessorCatalogStudentOut,
  ProfessorPayoutOut,
  ProfessorSessionMessageOut,
  ProfessorSessionOut,
  UserOut,
} from "../../lib/types";
import { normalizeUiLanguage, type UiLanguage, uiText } from "../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;
type Tab = "overview" | "planning" | "finance" | "messages" | "catalog" | "profile";
type AgendaView = "week" | "day" | "agenda";

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

function parseTab(value: string): Tab {
  if (value === "planning" || value === "finance" || value === "messages" || value === "catalog" || value === "profile") {
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
  const token = getPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok) {
    redirect("/login?error_code=session_expired");
  }

  if (meResult.data.role === "admin") {
    redirect("/admin");
  }
  if (meResult.data.role !== "prof") {
    redirect("/client?tab=home");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
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

  const sessionsQuery = new URLSearchParams();
  sessionsQuery.set("from", agendaRange.from.toISOString());
  sessionsQuery.set("to", agendaRange.to.toISOString());
  sessionsQuery.set("include_students", "true");

  const [
    profileResult,
    pendingResult,
    sessionsResult,
    balanceResult,
    payoutsResult,
    messagesResult,
    contractGridsResult,
    catalogStudentsResult,
    catalogProductsResult,
    catalogLocationsResult,
    catalogRequestsResult,
  ] = await Promise.all([
    backendRequest<ProfessorMeOut>("/api/v1/professors/me", {}, token),
    backendRequest<ProfessorAttendancePendingOut[]>("/api/v1/professors/me/attendance/pending?limit=200", {}, token),
    backendRequest<ProfessorSessionOut[]>(`/api/v1/professors/me/sessions?${sessionsQuery.toString()}`, {}, token),
    backendRequest<ProfessorBalanceOut>("/api/v1/professors/me/balance", {}, token),
    backendRequest<ProfessorPayoutOut[]>("/api/v1/professors/me/payouts?limit=200", {}, token),
    backendRequest<ProfessorSessionMessageOut[]>("/api/v1/professors/me/messages?limit=100", {}, token),
    backendRequest<ProfessorContractGridOut[]>("/api/v1/professors/me/contract-grids", {}, token),
    backendRequest<ProfessorCatalogStudentOut[]>("/api/v1/professors/me/catalog/students", {}, token),
    backendRequest<AdminCatalogProductOut[]>("/api/v1/professors/me/catalog/products", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=true", {}, token),
    backendRequest<AdminCatalogRequestOut[]>("/api/v1/professors/me/catalog/requests", {}, token),
  ]);

  if (!profileResult.ok) {
    redirect(`/login?error=${encodeURIComponent(profileResult.message)}`);
  }

  const profile = profileResult.data;
  const fullName = `${profile.first_name} ${profile.last_name}`.trim();
  const impersonationDisplayName = impersonationNameHint || fullName || profile.email;
  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error");

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
        teacher_display_name: fullName || profile.email,
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
  const selectedMessageId = readParam(searchParams, "message_id");

  const pendingRows = pendingResult.ok ? pendingResult.data : [];
  const pendingCount = pendingRows.reduce((sum, row) => sum + row.pending_students_count, 0);
  const catalogStudents = catalogStudentsResult.ok ? catalogStudentsResult.data : [];
  const catalogProducts = catalogProductsResult.ok ? catalogProductsResult.data.filter((row) => row.active) : [];
  const catalogLocations = catalogLocationsResult.ok ? catalogLocationsResult.data.filter((row) => row.active) : [];
  const catalogRequests = catalogRequestsResult.ok ? catalogRequestsResult.data : [];
  const catalogToDeliver = catalogRequests.filter(
    (row) => row.status === "TO_DELIVER" || row.status === "INVOICE_TO_SEND",
  );

  const todaySessions = sessionsByDay.get(todayKeyUtc()) ?? [];
  const canEditPlanning = profile.permissions.can_edit_planning;
  const canMessageStudents = profile.permissions.can_message_clients;
  const maxVisibleSessionsByDay = agendaView === "day" ? 24 : agendaView === "week" ? 8 : 5;
  const previousAgendaDate = shiftAgendaDate(agendaView, agendaDate, -1);
  const nextAgendaDate = shiftAgendaDate(agendaView, agendaDate, 1);
  const previousAgendaHref = buildProfHref({ tab: "planning", agendaView, agendaDate: previousAgendaDate, dayDetails: "" });
  const nextAgendaHref = buildProfHref({ tab: "planning", agendaView, agendaDate: nextAgendaDate, dayDetails: "" });
  const todayAgendaHref = buildProfHref({ tab: "planning", agendaView, agendaDate: todayKeyUtc(), dayDetails: "" });
  const archivedMessages = messagesResult.ok ? messagesResult.data : [];
  const selectedMessage = selectedMessageId ? archivedMessages.find((message) => message.id === selectedMessageId) ?? null : null;

  const navTabs: Array<{ id: Tab; label: string; icon: string }> = [
    { id: "overview", label: uiText(language, "teacher.todo"), icon: "🗂" },
    { id: "planning", label: uiText(language, "teacher.planning"), icon: "📅" },
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
          <Link className="mode-link teacher-header-link" href="/prof/statements">
            {uiText(language, "teacher.statements")}
          </Link>
        }
        menu={
          <div className="teacher-header-menu-items">
            <Link className="teacher-header-menu-link" href={buildProfHref({ tab: "catalog", agendaView, agendaDate })}>
              {uiText(language, "teacher.products")}
            </Link>
            <Link className="teacher-header-menu-link" href={buildProfHref({ tab: "finance", agendaView, agendaDate })}>
              {uiText(language, "teacher.balance")}
            </Link>
            <form action={logoutAction}>
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
          { id: "statements", label: uiText(language, "teacher.statements"), icon: "🧾", href: "/prof/statements" },
          { id: "messages", label: uiText(language, "teacher.messages"), icon: "✉️", href: buildProfHref({ tab: "messages", agendaView, agendaDate }) },
          { id: "profile", label: uiText(language, "teacher.profile"), icon: "👤", href: buildProfHref({ tab: "profile", agendaView, agendaDate }) },
        ]}
      />

      {isImpersonating ? (
        <PortalImpersonationBanner displayName={impersonationDisplayName} returnTo={impersonationReturnTo} language={language} />
      ) : null}

      {okMessage ? <AlertCard tone="ok">{okMessage}</AlertCard> : null}
      {errorMessage ? <AlertCard tone="error">{errorMessage}</AlertCard> : null}
      {!sessionsResult.ok ? <AlertCard tone="error">{t("teacher.schedule_error")}: {sessionsResult.message}</AlertCard> : null}
      {!pendingResult.ok ? <AlertCard tone="error">{t("teacher.attendance_error")}: {pendingResult.message}</AlertCard> : null}
      {!balanceResult.ok ? <AlertCard tone="error">{t("teacher.balance_error")}: {balanceResult.message}</AlertCard> : null}
      {!messagesResult.ok ? <AlertCard tone="error">{t("teacher.messages_error")}: {messagesResult.message}</AlertCard> : null}
      {!contractGridsResult.ok ? <AlertCard tone="error">{t("teacher.statement_contract_grid_error")}: {contractGridsResult.message}</AlertCard> : null}
      {!catalogStudentsResult.ok ? <AlertCard tone="error">{t("teacher.catalog_students_error")}: {catalogStudentsResult.message}</AlertCard> : null}
      {!catalogProductsResult.ok ? <AlertCard tone="error">{t("teacher.catalog_products_error")}: {catalogProductsResult.message}</AlertCard> : null}
      {!catalogRequestsResult.ok ? <AlertCard tone="error">{t("teacher.catalog_requests_error")}: {catalogRequestsResult.message}</AlertCard> : null}

      {currentTab === "overview" ? (
        <section className="teacher-section-stack">
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

          <form method="get" className="grid cols-4 teacher-planning-controls">
            <input type="hidden" name="tab" value="planning" />
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
              <input type="date" name="agenda_date" defaultValue={agendaDate} />
            </label>
            <div className="row teacher-planning-controls-actions">
              <button type="submit" className="ghost">{t("teacher.go")}</button>
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
                dayDetailsHref={buildProfHref({ tab: "planning", agendaView, agendaDate, dayDetails: day.key })}
                openSessionHref={(sessionId) =>
                  buildProfHref({
                    tab: "planning",
                    agendaView,
                    agendaDate,
                    sessionId,
                    dayDetails: "",
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
            closeHref={buildProfHref({ tab: "planning", agendaView, agendaDate, dayDetails: "" })}
            openSessionHref={(sessionId) =>
              buildProfHref({
                tab: "planning",
                agendaView,
                agendaDate,
                sessionId,
                dayDetails: "",
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

      {currentTab === "messages" ? (
        <section className="teacher-section-stack">
          <ActionCard title={t("teacher.archived_messages")} subtitle={t("teacher.archived_messages_subtitle")}>
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
          <SectionAccordion title={t("teacher.my_profile")} subtitle={t("teacher.main_information")} defaultOpen={true}>
            <div className="list teacher-list-compact">
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
                </p>
              </div>
              <div className="teacher-attendance-header-meta">
                <span className={`occ-badge ${selectedSessionReservedCount >= selectedSession.capacity_max ? "occ-high" : "occ-low"}`}>
                  {selectedSessionReservedCount}/{selectedSession.capacity_max}
                </span>
                <span className="status-badge status-waitlist">{t("teacher.to_fill_count", { count: selectedSessionPendingCount })}</span>
                <Link
                  className="modal-close-x"
                  href={buildProfHref({ tab: "planning", agendaView, agendaDate })}
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
                      href={buildProfHref({ tab: "planning", agendaView, agendaDate, sessionId: selectedSession.id, attendanceFilter: "all" })}
                    >
                      {t("teacher.all_filter")}
                    </Link>
                    <Link
                      className={`mode-link ${attendanceFilter === "missing" ? "mode-active" : ""}`}
                      href={buildProfHref({ tab: "planning", agendaView, agendaDate, sessionId: selectedSession.id, attendanceFilter: "missing" })}
                    >
                      {t("teacher.missing_filter")}
                    </Link>
                  </div>
                  {canEditPlanning && editableAttendanceStudents.length > 0 ? (
                    <span className="status-badge status-scheduled">{t("teacher.one_tap_per_student")}</span>
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
                        ) : canEditPlanning ? (
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
                      </article>
                    ))}
                  </div>
                )}
              </section>

              <aside className="teacher-attendance-secondary">
                {canMessageStudents ? (
                  <details className="teacher-attendance-accordion">
                    <summary>{t("teacher.notes_optional")}</summary>
                    <div className="teacher-attendance-accordion-body">
                      <form action={professorSendSessionMessageAction} className="grid">
                        <input type="hidden" name="session_id" value={selectedSession.id} />
                        <input
                          type="hidden"
                          name="return_to"
                          value={buildProfHref({ tab: "planning", agendaView, agendaDate, sessionId: selectedSession.id, attendanceFilter })}
                        />
                        <input type="hidden" name="recipient_target" value="ADMIN" />
                        <label>
                          {t("teacher.subject")}
                          <input type="text" name="subject" required maxLength={255} defaultValue={t("teacher.lesson_note_subject", { title: selectedSession.title })} />
                        </label>
                        <label>
                          {t("teacher.internal_note")}
                          <input type="hidden" name="body_format" value="TEXT" />
                          <textarea name="body" rows={4} maxLength={12000} placeholder={t("teacher.note_admin_placeholder")} />
                        </label>
                        <div className="row">
                          <button type="submit" className="ghost">
                            {t("teacher.save_note")}
                          </button>
                        </div>
                      </form>
                    </div>
                  </details>
                ) : null}

                {canEditPlanning && selectedSession.status !== "CANCELLED" ? (
                  <details className="teacher-attendance-accordion teacher-attendance-accordion-danger">
                    <summary>{t("teacher.teacher_absence")}</summary>
                    <div className="teacher-attendance-accordion-body">
                      <form action={professorMarkSessionAbsentAction} className="grid">
                        <input type="hidden" name="session_id" value={selectedSession.id} />
                        <input
                          type="hidden"
                          name="return_to"
                          value={buildProfHref({ tab: "planning", agendaView, agendaDate, sessionId: selectedSession.id, attendanceFilter })}
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
                      <strong>{t("teacher.teacher_label")}:</strong> {fullName || profile.email}
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
              <Link className="reset-link" href={buildProfHref({ tab: "planning", agendaView, agendaDate })}>
                {uiText(language, "common.close")}
              </Link>
              <div className="row">
                {selectedSessionPendingCount > 0 ? (
                  <span className="status-badge status-waitlist">{t("teacher.to_fill_count", { count: selectedSessionPendingCount })}</span>
                ) : (
                  <span className="status-badge status-completed">{t("teacher.all_recorded")}</span>
                )}
                <Link className="mode-link" href={buildProfHref({ tab: "planning", agendaView, agendaDate })}>
                  {t("teacher.finish")}
                </Link>
              </div>
            </footer>
          </article>
        </section>
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
              <article className="item" dangerouslySetInnerHTML={{ __html: selectedMessage.body }} />
            ) : (
              <article className="item">
                <p style={{ whiteSpace: "pre-wrap" }}>{selectedMessage.body}</p>
              </article>
            )}
          </article>
        </section>
      ) : null}
    </main>
  );
}
