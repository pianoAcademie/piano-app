import Link from "next/link";
import { redirect } from "next/navigation";

import AdminProfessorPayrollEditor from "../../../../components/admin-professor-payroll-editor";
import CollaboratorDailyScheduleForm from "../../../../components/collaborator-daily-schedule-form";
import {
  adminViewTeacherPortalAction,
  deleteAdminCollaboratorContractAction,
  sendAdminCollaboratorPasswordLinkAction,
  upsertAdminCollaboratorContractGridAction,
  uploadAdminCollaboratorContractAction,
  updateAdminCollaboratorRatesAction,
  updateAdminCollaboratorPermissionsAction,
  updateAdminCollaboratorProfileAction,
} from "../../../../lib/actions";
import { getAdminToken } from "../../../../lib/auth-cookies";
import { backendRequest } from "../../../../lib/backend";
import { hasAdminPermission } from "../../../../lib/admin-access";
import {
  buildAgendaRange,
  formatAgendaDayLabel,
  formatAgendaTime,
  isAgendaDateKey,
  parisDateKey,
  type AgendaView,
} from "../../../../lib/collaborator-agenda";
import CollaboratorClientChunkAnchor from "./_client-chunk-anchor";
import type {
  AdminConfigAccountOut,
  AdminProfessorDefaultGridOut,
  AdminProfessorContractGridOut,
  AdminProfessorContractLocationOptionOut,
  AdminProfessorDetailOut,
  AdminProfessorPayoutLedgerOut,
  AdminProfessorRateOut,
  AdminSessionOut,
  CourseTypeOut,
  LocationOut,
  UserOut,
} from "../../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;
type Tab = "profil" | "droits" | "tarifs" | "solde" | "planning";

const COLLABORATOR_LANGUAGE_OPTIONS: Array<{ value: string; labelKey: string }> = [
  { value: "Francais", labelKey: "common.french" },
  { value: "Anglais", labelKey: "common.english" },
  { value: "Espagnol", labelKey: "common.spanish" },
  { value: "Italien", labelKey: "common.italian" },
  { value: "Allemand", labelKey: "common.german" },
  { value: "Portugais", labelKey: "common.portuguese" },
  { value: "Russe", labelKey: "common.russian" },
  { value: "Chinois", labelKey: "common.chinese" },
  { value: "Japonais", labelKey: "common.japanese" },
];

type PageProps = {
  params: { id: string };
  searchParams: SearchParams;
};

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function parseTab(value: string): Tab {
  if (value === "droits" || value === "tarifs" || value === "solde" || value === "planning") {
    return value;
  }
  return "profil";
}

function parseAgendaView(value: string): AgendaView {
  if (value === "day" || value === "week") {
    return value;
  }
  return "month";
}

function isDateKey(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function todayKeyUtc(): string {
  return new Date().toISOString().slice(0, 10);
}

function formatDate(value: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString(localeForUiLanguage(language), {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Paris",
  });
}

function tabHref(professorId: string, tab: Tab): string {
  return `/admin/professors/${professorId}?tab=${tab}`;
}

function contractModeLabel(mode: string, language: UiLanguage): string {
  const normalized = mode.trim().toUpperCase();
  if (normalized === "PRESENTIEL") {
    return uiText(language, "admin.professor_detail.mode_onsite");
  }
  if (normalized === "EN_LIGNE") {
    return uiText(language, "admin.professor_detail.mode_online");
  }
  return uiText(language, "admin.professor_detail.mode_other");
}

function activityModeLabel(mode: string, language: UiLanguage): string {
  const normalized = mode.trim().toUpperCase();
  if (normalized === "ONSITE") {
    return uiText(language, "admin.professor_detail.mode_onsite");
  }
  if (normalized === "ONLINE") {
    return uiText(language, "admin.professor_detail.mode_online");
  }
  return uiText(language, "admin.professor_detail.mode_all");
}

function normalizeLookupKey(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

function isRateActiveOn(rate: AdminProfessorRateOut, onDate: string): boolean {
  if (rate.valid_from > onDate) {
    return false;
  }
  if (rate.valid_to && rate.valid_to < onDate) {
    return false;
  }
  return true;
}

function payoutStatusLabel(status: "PENDING" | "APPROVED" | "PAID" | null, language: UiLanguage): string {
  if (status === "PENDING") {
    return uiText(language, "admin.professor_detail.payout_pending");
  }
  if (status === "APPROVED") {
    return uiText(language, "admin.professor_detail.payout_approved");
  }
  if (status === "PAID") {
    return uiText(language, "admin.professor_detail.payout_paid");
  }
  return uiText(language, "admin.professor_detail.payout_calculated");
}

function payoutStatusToneClass(status: "PENDING" | "APPROVED" | "PAID" | null): string {
  if (status === "PAID") {
    return "status-off";
  }
  if (status === "APPROVED") {
    return "status-ok";
  }
  return "status-warn";
}

function encodeHeadcountRules(
  rules: Array<{ min_students: number; max_students: number | null; hourly_rate: string }>,
): string {
  return rules
    .map((rule) => {
      const range = rule.max_students === null ? `${rule.min_students}+` : `${rule.min_students}-${rule.max_students}`;
      return `${range}:${rule.hourly_rate}`;
    })
    .join("; ");
}

function collaboratorRoleLabel(role: string, language: UiLanguage): string {
  const normalized = role.trim().toLowerCase();
  if (normalized === "admin") {
    return uiText(language, "admin.professor_detail.role_admin");
  }
  if (normalized === "prof") {
    return uiText(language, "admin.professor_detail.role_teacher");
  }
  return role;
}

function spokenLanguageLabel(value: string, language: UiLanguage): string {
  const option = COLLABORATOR_LANGUAGE_OPTIONS.find((candidate) => candidate.value === value);
  return option ? uiText(language, option.labelKey) : value;
}

function spokenLanguagesLabel(values: string[], language: UiLanguage): string {
  if (values.length === 0) {
    return uiText(language, "admin.professor_detail.not_provided");
  }
  return values.map((value) => spokenLanguageLabel(value, language)).join(", ");
}

const PERMISSION_SECTIONS: Array<{ titleKey: string; keys: Array<{ key: string; labelKey: string }> }> = [
  {
    titleKey: "admin.professor_detail.permissions.manager_title",
    keys: [
      { key: "can_view_planning", labelKey: "admin.professor_detail.permissions.view_planning" },
      { key: "can_edit_planning", labelKey: "admin.professor_detail.permissions.edit_planning" },
      { key: "can_view_planning_simulation", labelKey: "admin.professor_detail.permissions.view_planning_simulation" },
      { key: "can_manage_check_deposits", labelKey: "admin.professor_detail.permissions.manage_check_deposits" },
      { key: "can_view_clients", labelKey: "admin.professor_detail.permissions.view_clients_readonly" },
      { key: "can_access_collaborators", labelKey: "admin.professor_detail.permissions.access_collaborators" },
      { key: "can_view_intakes", labelKey: "admin.professor_detail.permissions.view_intakes_readonly" },
      { key: "can_view_quotes", labelKey: "admin.professor_detail.permissions.view_quotes_readonly" },
      { key: "can_view_upcoming_trials", labelKey: "admin.professor_detail.permissions.view_upcoming_trials" },
    ],
  },
  {
    titleKey: "admin.professor_detail.permissions.self_title",
    keys: [
      { key: "can_take_attendance", labelKey: "admin.professor_detail.permissions.take_attendance" },
      { key: "can_record_payments_with_attendance", labelKey: "admin.professor_detail.permissions.record_payments_with_attendance" },
      { key: "can_edit_own_sessions", labelKey: "admin.professor_detail.permissions.edit_own_sessions" },
      { key: "can_view_pay_details", labelKey: "admin.professor_detail.permissions.view_pay_details" },
      { key: "can_manage_mileage_log", labelKey: "admin.professor_detail.permissions.manage_mileage_log" },
    ],
  },
  {
    titleKey: "admin.professor_detail.permissions.other_teachers_title",
    keys: [
      { key: "can_view_other_teachers_contacts", labelKey: "admin.professor_detail.permissions.view_other_teachers_contacts" },
      { key: "can_manage_other_teachers_students_and_sessions", labelKey: "admin.professor_detail.permissions.manage_other_teachers_students_and_sessions" },
      { key: "can_view_other_teachers_sessions", labelKey: "admin.professor_detail.permissions.view_other_teachers_sessions" },
    ],
  },
  {
    titleKey: "admin.professor_detail.permissions.students_title",
    keys: [
      { key: "can_message_clients", labelKey: "admin.professor_detail.permissions.message_clients" },
      { key: "can_view_student_parent_addresses_phones", labelKey: "admin.professor_detail.permissions.view_student_parent_addresses_phones" },
      { key: "can_view_student_parent_emails", labelKey: "admin.professor_detail.permissions.view_student_parent_emails" },
      { key: "can_view_student_attachments", labelKey: "admin.professor_detail.permissions.view_student_attachments" },
    ],
  },
  {
    titleKey: "admin.professor_detail.permissions.other_features_title",
    keys: [
      { key: "can_manage_invoices_and_accounts", labelKey: "admin.professor_detail.permissions.manage_invoices_and_accounts" },
      { key: "can_manage_expenses_and_other_income", labelKey: "admin.professor_detail.permissions.manage_expenses_and_other_income" },
      { key: "can_manage_shared_online_resources", labelKey: "admin.professor_detail.permissions.manage_shared_online_resources" },
      { key: "can_manage_website_and_news", labelKey: "admin.professor_detail.permissions.manage_website_and_news" },
      { key: "can_create_and_view_reports", labelKey: "admin.professor_detail.permissions.create_and_view_reports" },
    ],
  },
];

export default async function AdminCollaboratorDetailPage({ params, searchParams }: PageProps): Promise<JSX.Element> {
  const token = getAdminToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || !hasAdminPermission(meResult.data, "can_access_collaborators")) {
    redirect("/login?error_code=admin_access_required");
  }
  const canManageCollaborators = meResult.data.role === "admin";
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const sortLocale = localeForUiLanguage(language);

  const requestedTab = parseTab(readParam(searchParams, "tab"));
  const currentTab = canManageCollaborators || requestedTab === "planning" ? requestedTab : "profil";
  const isEditProfileOpen = readParam(searchParams, "edit_profile") === "1";
  const editGridId = readParam(searchParams, "edit_grid_id");
  const showLegacyContractGrid = readParam(searchParams, "legacy_contract") === "1";
  const agendaView = parseAgendaView(readParam(searchParams, "agenda_view"));
  const agendaDateInput = readParam(searchParams, "agenda_date");
  const agendaDate = isAgendaDateKey(agendaDateInput) ? agendaDateInput : parisDateKey(new Date());
  const payoutAsOfInput = readParam(searchParams, "payout_as_of");
  const payoutAsOf = isDateKey(payoutAsOfInput) ? payoutAsOfInput : todayKeyUtc();
  const agendaRange = buildAgendaRange(agendaView, agendaDate, sortLocale);

  const sessionsQuery = new URLSearchParams();
  sessionsQuery.set("professor_id", params.id);
  sessionsQuery.set("from", agendaRange.from.toISOString());
  sessionsQuery.set("to", agendaRange.to.toISOString());
  const payoutLedgerQuery = new URLSearchParams();
  payoutLedgerQuery.set("as_of", payoutAsOf);

  const contractGridsRequest = canManageCollaborators && showLegacyContractGrid
    ? backendRequest<AdminProfessorContractGridOut[]>(`/api/v1/admin/collaborators/${params.id}/contract-grids`, {}, token)
    : Promise.resolve({ ok: true as const, status: 200, data: [] as AdminProfessorContractGridOut[] });
  const contractLocationsRequest = canManageCollaborators && showLegacyContractGrid
    ? backendRequest<AdminProfessorContractLocationOptionOut[]>("/api/v1/admin/collaborators/contract-grid/locations", {}, token)
    : Promise.resolve({ ok: true as const, status: 200, data: [] as AdminProfessorContractLocationOptionOut[] });
  const payoutLedgerRequest =
    canManageCollaborators && currentTab === "solde"
      ? backendRequest<AdminProfessorPayoutLedgerOut>(`/api/v1/admin/collaborators/${params.id}/payout-ledger?${payoutLedgerQuery.toString()}`, {}, token)
      : Promise.resolve({ ok: true as const, status: 200, data: null as AdminProfessorPayoutLedgerOut | null });

  const [
    profResult,
    ratesResult,
    courseTypesResult,
    sessionsResult,
    locationsResult,
    accountResult,
    defaultProfessorGridResult,
    contractGridsResult,
    contractLocationsResult,
    payoutLedgerResult,
  ] =
    await Promise.all([
    backendRequest<AdminProfessorDetailOut>(`/api/v1/admin/collaborators/${params.id}`, {}, token),
    canManageCollaborators
      ? backendRequest<AdminProfessorRateOut[]>(`/api/v1/admin/collaborators/${params.id}/rates`, {}, token)
      : Promise.resolve({ ok: true as const, status: 200, data: [] as AdminProfessorRateOut[] }),
    backendRequest<CourseTypeOut[]>("/api/v1/course-types", {}, token),
    backendRequest<AdminSessionOut[]>(`/api/v1/admin/sessions?${sessionsQuery.toString()}`, {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations", {}, token),
    canManageCollaborators
      ? backendRequest<AdminConfigAccountOut>("/api/v1/admin/config/account", {}, token)
      : Promise.resolve({ ok: true as const, status: 200, data: null as AdminConfigAccountOut | null }),
    canManageCollaborators
      ? backendRequest<AdminProfessorDefaultGridOut>("/api/v1/admin/config/professor-default-grid", {}, token)
      : Promise.resolve({ ok: true as const, status: 200, data: { lines: [], updated_at: null } as AdminProfessorDefaultGridOut }),
    contractGridsRequest,
    contractLocationsRequest,
    payoutLedgerRequest,
  ]);

  if (!profResult.ok) {
    if (profResult.status === 404) {
      redirect(`/admin/professors?error=${encodeURIComponent(t("admin.professor_detail.not_found"))}`);
    }
    return <section className="flash-err">{t("admin.professor_detail.backend_error")}: {profResult.message}</section>;
  }

  const professor = profResult.data;
  const permissionState = professor.permissions as Record<string, boolean | string | null>;
  const isTeacherProfile =
    professor.role !== "admin" &&
    Boolean(permissionState.can_view_planning) &&
    Boolean(permissionState.can_take_attendance) &&
    Boolean(permissionState.can_message_clients) &&
    Boolean(permissionState.can_view_pay_details) &&
    !Boolean(permissionState.can_edit_planning) &&
    !Boolean(permissionState.can_view_all_school_sessions) &&
    !Boolean(permissionState.can_access_collaborators) &&
    !Boolean(permissionState.can_view_clients) &&
    !Boolean(permissionState.can_view_student_parent_addresses_phones) &&
    !Boolean(permissionState.can_view_student_parent_emails) &&
    !Boolean(permissionState.can_view_other_teachers_contacts) &&
    !Boolean(permissionState.can_view_other_teachers_sessions) &&
    !Boolean(permissionState.can_manage_other_teachers_students_and_sessions);
  const isManagerProfile =
    professor.role !== "admin" &&
    Boolean(permissionState.can_edit_planning) &&
    Boolean(permissionState.can_view_planning_simulation) &&
    Boolean(permissionState.can_view_clients) &&
    Boolean(permissionState.can_access_collaborators) &&
    Boolean(permissionState.can_view_intakes) &&
    Boolean(permissionState.can_view_quotes) &&
    Boolean(permissionState.can_view_upcoming_trials);
  const isAccountantProfile =
    professor.role !== "admin" &&
    Boolean(permissionState.can_manage_invoices_and_accounts) &&
    Boolean(permissionState.can_create_and_view_reports) &&
    Boolean(permissionState.can_manage_check_deposits) &&
    !Boolean(permissionState.can_edit_planning) &&
    !Boolean(permissionState.can_view_clients) &&
    !Boolean(permissionState.can_access_collaborators);
  const rates = ratesResult.ok ? ratesResult.data : [];
  const courseTypes = courseTypesResult.ok ? courseTypesResult.data : [];
  const sessions = sessionsResult.ok ? sessionsResult.data : [];
  const locations = locationsResult.ok ? locationsResult.data : [];
  const selectedSimulationLocationId = String(permissionState.planning_simulation_location_id ?? "");
  const selectedCheckDepositsLocationId = String(permissionState.check_deposits_location_id ?? "");
  const simulationLocationOptions = selectedSimulationLocationId && !locations.some((location) => location.id === selectedSimulationLocationId)
    ? [
        ...locations,
        {
          id: selectedSimulationLocationId,
          code: "",
          name: t("admin.professor_detail.permissions.simulation_location_configured"),
          address_line: null,
          city: null,
          country_code: "FR",
          is_online: false,
          timezone: "Europe/Paris",
          active: true,
        },
      ]
    : locations;
  const accountConfig = accountResult.ok ? accountResult.data : null;
  const defaultProfessorGrid = defaultProfessorGridResult.ok ? defaultProfessorGridResult.data : { lines: [], updated_at: null };
  const contractGrids = contractGridsResult.ok ? contractGridsResult.data : [];
  const contractLocationOptions = contractLocationsResult.ok ? contractLocationsResult.data : [];
  const payoutLedger = payoutLedgerResult.ok ? payoutLedgerResult.data : null;
  const availableCurrencies =
    accountConfig && accountConfig.allowed_currencies.length > 0 ? accountConfig.allowed_currencies : ["EUR", "USD"];
  const defaultRateCurrency =
    availableCurrencies.includes(professor.payout_currency)
      ? professor.payout_currency
      : availableCurrencies.includes(accountConfig?.default_currency ?? "")
        ? (accountConfig?.default_currency ?? availableCurrencies[0])
        : (availableCurrencies[0] ?? "EUR");
  const effectiveDateDefault = new Date().toISOString().slice(0, 10);
  const selectedContractGrid = editGridId ? contractGrids.find((row) => row.id === editGridId) ?? null : null;
  const contractLineSlots = 16;
  const selectedGridLines = selectedContractGrid?.lines ?? [];
  const activeRatesByKey = new Map<string, AdminProfessorRateOut>();
  for (const rate of rates) {
    if (!isRateActiveOn(rate, payoutAsOf)) {
      continue;
    }
    const key = rate.course_type_id ?? "__GLOBAL__";
    if (!activeRatesByKey.has(key)) {
      activeRatesByKey.set(key, rate);
    }
  }
  const activeBaseRate = activeRatesByKey.get("__GLOBAL__") ?? null;
  const editableCourseTypes = [...courseTypes]
    .filter((courseType) => courseType.active)
    .sort((a, b) => a.name.localeCompare(b.name, sortLocale));
  const defaultGridByCourseTypeId = new Map(defaultProfessorGrid.lines.map((line) => [line.course_type_id, line]));
  const activeGeneralPeriodLabel =
    defaultProfessorGrid.active_period_start_date
      ? `${defaultProfessorGrid.active_period_start_date} -> ${defaultProfessorGrid.active_period_end_date ?? t("admin.professor_detail.ongoing")}`
      : null;
  const payrollActivities = editableCourseTypes.map((courseType) => {
    const activeRate = activeRatesByKey.get(courseType.id) ?? null;
    const defaultGridLine = defaultGridByCourseTypeId.get(courseType.id) ?? null;
    const generalGrid = defaultGridLine
      ? {
          default_hourly_rate: defaultGridLine.default_hourly_rate,
          rules: defaultGridLine.rules.map((rule) => ({
            min_students: rule.min_students,
            max_students: rule.max_students,
            hourly_rate: rule.hourly_rate,
          })),
        }
      : {
          default_hourly_rate: courseType.default_hourly_rate,
          rules: [],
        };
    const specificGrid = activeRate
      ? {
          default_hourly_rate: activeRate.hourly_rate,
          rules: activeRate.rules.map((rule) => ({
            min_students: rule.min_students,
            max_students: rule.max_students,
            hourly_rate: rule.hourly_rate,
          })),
        }
      : null;
    const hasSpecific = Boolean(activeRate && (activeRate.hourly_rate !== null || activeRate.rules.length > 0));
    const initialMode: "GENERAL" | "SPECIFIC" = hasSpecific ? "SPECIFIC" : "GENERAL";

    return {
      course_type_id: courseType.id,
      course_type_name: courseType.name,
      mode_label: activityModeLabel(courseType.mode, language),
      reference_duration_minutes: courseType.duration_minutes,
      initial_mode: initialMode,
      general_grid: generalGrid,
      specific_grid: specificGrid,
      specific_valid_from: activeRate?.valid_from ?? null,
      specific_valid_to: activeRate?.valid_to ?? null,
    };
  });

  const locationNameById = new Map(locations.map((loc) => [loc.id, loc.name]));
  const courseTypeNameById = new Map(courseTypes.map((ct) => [ct.id, ct.name]));
  const courseTypeById = new Map(courseTypes.map((ct) => [ct.id, ct]));
  const courseTypeIdByNormalizedName = new Map<string, string>();
  for (const courseType of courseTypes) {
    const key = normalizeLookupKey(courseType.name);
    if (!courseTypeIdByNormalizedName.has(key)) {
      courseTypeIdByNormalizedName.set(key, courseType.id);
    }
  }

  const sessionsByDay = new Map<string, AdminSessionOut[]>();
  for (const session of sessions) {
    const dayKey = parisDateKey(session.start_at_utc);
    const bucket = sessionsByDay.get(dayKey) ?? [];
    bucket.push(session);
    sessionsByDay.set(dayKey, bucket);
  }
  for (const rows of sessionsByDay.values()) {
    rows.sort((a, b) => a.start_at_utc.localeCompare(b.start_at_utc));
  }

  const agendaDays = agendaRange.dayKeys.map((dayKey) => ({
    key: dayKey,
    label: formatAgendaDayLabel(dayKey, agendaView, sortLocale),
    sessions: sessionsByDay.get(dayKey) ?? [],
  }));

  const fullName = `${professor.first_name} ${professor.last_name}`.trim();
  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error");

  const tabs: Array<{ id: Tab; label: string }> = [
    { id: "profil", label: t("admin.professor_detail.tab_profile") },
    ...(canManageCollaborators
      ? [
          { id: "droits" as const, label: t("admin.professor_detail.tab_permissions") },
          { id: "tarifs" as const, label: t("admin.professor_detail.tab_payroll") },
          { id: "solde" as const, label: t("admin.professor_detail.tab_balance") },
        ]
      : []),
    { id: "planning", label: t("admin.professor_detail.tab_schedule") },
  ];

  return (
    <section className="admin-page-grid">
      <CollaboratorClientChunkAnchor />
      <section className="client-hero card">
        <div className="row spread">
          <Link className="reset-link" href="/admin/professors">
            {t("admin.professor_detail.back_list")}
          </Link>
          {canManageCollaborators ? (
            <div className="row teacher-actions-wrap">
              <form action={adminViewTeacherPortalAction} target="_blank" rel="noopener noreferrer">
                <input type="hidden" name="teacher_id" value={professor.id} />
                <input type="hidden" name="view_mode" value="teacher" />
                <input type="hidden" name="return_to" value={`/admin/professors/${professor.id}?tab=${currentTab}`} />
                <button type="submit" className="mode-link">
                  {t("admin.professor_detail.view_teacher_portal")}
                </button>
              </form>
              {isManagerProfile ? (
                <form action={adminViewTeacherPortalAction} target="_blank" rel="noopener noreferrer">
                  <input type="hidden" name="teacher_id" value={professor.id} />
                  <input type="hidden" name="view_mode" value="manager" />
                  <input type="hidden" name="return_to" value={`/admin/professors/${professor.id}?tab=${currentTab}`} />
                  <button type="submit" className="ghost">
                    {language === "en" ? "Manager view" : "Vue gestionnaire"}
                  </button>
                </form>
              ) : null}
            </div>
          ) : null}
          <span className={`status-pill ${professor.active ? "status-ok" : "status-off"}`}>
            {professor.active ? t("common.active") : t("common.inactive")}
          </span>
        </div>
        <div className="client-hero-main">
          <div className="client-avatar">{(professor.first_name ?? "").slice(0, 1)}{(professor.last_name ?? "").slice(0, 1)}</div>
          <div>
            <h2>{fullName || professor.email}</h2>
            <p className="muted">
              {t("admin.professor_detail.hero_summary", {
                email: professor.email,
                phone: professor.phone ?? "-",
                role: collaboratorRoleLabel(professor.role, language),
                coach: professor.is_coach ? t("common.yes") : t("common.no"),
              })}
            </p>
          </div>
        </div>
        <nav className="client-tabs">
          {tabs.map((tab) => (
            <Link key={tab.id} href={tabHref(professor.id, tab.id)} className={`client-tab ${currentTab === tab.id ? "active" : ""}`}>
              {tab.label}
            </Link>
          ))}
        </nav>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {!ratesResult.ok ? <section className="flash-err">{t("admin.professor_detail.error_rates")}: {ratesResult.message}</section> : null}
      {!sessionsResult.ok ? <section className="flash-err">{t("admin.professor_detail.error_schedule")}: {sessionsResult.message}</section> : null}
      {canManageCollaborators && !accountResult.ok ? <section className="flash-err">{t("admin.professor_detail.error_currencies")}: {accountResult.message}</section> : null}
      {canManageCollaborators && !defaultProfessorGridResult.ok ? (
        <section className="flash-err">{t("admin.professor_detail.error_general_grid")}: {defaultProfessorGridResult.message}</section>
      ) : null}
      {showLegacyContractGrid && !contractGridsResult.ok ? (
        <section className="flash-err">{t("admin.professor_detail.error_contract_grids")}: {contractGridsResult.message}</section>
      ) : null}
      {showLegacyContractGrid && !contractLocationsResult.ok ? (
        <section className="flash-err">{t("admin.professor_detail.error_contract_locations")}: {contractLocationsResult.message}</section>
      ) : null}
      {currentTab === "solde" && !payoutLedgerResult.ok ? (
        <section className="flash-err">{t("admin.professor_detail.error_payout_balance")}: {payoutLedgerResult.message}</section>
      ) : null}

      {currentTab === "profil" ? (
        <section className="grid cols-2">
          <article className="card">
            <h3>{t("admin.professor_detail.section_information")}</h3>
            <div className="list">
              <article className="item row spread">
                <span className="muted">{t("common.email")}</span>
                <strong>{professor.email}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">{t("admin.professor_detail.field_phone")}</span>
                <strong>{professor.phone ?? t("admin.professor_detail.not_provided")}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">{t("admin.professors.siret_label")}</span>
                <strong>{professor.siret ?? t("admin.professor_detail.not_provided")}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">{t("admin.professors.iban_label")}</span>
                <strong>{professor.iban ?? t("admin.professor_detail.not_provided")}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">{t("admin.professor_detail.field_address")}</span>
                <strong>{professor.address_line ?? t("admin.professor_detail.not_provided")}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">{t("admin.professor_detail.field_teacher_invoice_counter")}</span>
                <strong>{professor.teacher_invoice_counter}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">{t("admin.professor_detail.field_teacher_vat_applicable")}</span>
                <strong>{professor.teacher_is_vat_applicable ? t("common.yes") : t("common.no")}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">{t("admin.professor_detail.field_teacher_vat_rate")}</span>
                <strong>{professor.teacher_vat_rate ?? "-"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">{t("admin.professor_detail.field_teacher_siret")}</span>
                <strong>{professor.teacher_siret ?? t("admin.professor_detail.not_provided")}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">{t("admin.professor_detail.field_teacher_iban")}</span>
                <strong>{professor.teacher_iban ?? t("admin.professor_detail.not_provided")}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">{t("admin.professor_detail.field_teacher_company_name")}</span>
                <strong>{professor.teacher_company_name ?? t("admin.professor_detail.not_provided")}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">{t("admin.professor_detail.field_teacher_company_address")}</span>
                <strong>{professor.teacher_company_address ?? t("admin.professor_detail.not_provided")}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">{t("admin.professor_detail.field_zoom_link")}</span>
                <strong>{professor.zoom_link ?? t("admin.professor_detail.not_provided")}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">{t("admin.professor_detail.field_languages")}</span>
                <strong>{spokenLanguagesLabel(professor.spoken_languages, language)}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">{t("admin.professor_detail.field_daily_schedule_email")}</span>
                <strong>{professor.daily_schedule_email_enabled ? t("common.active") : t("common.inactive")}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">{t("admin.professor_detail.field_daily_schedule_time")}</span>
                <strong>{professor.daily_schedule_email_time}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">{t("admin.professor_detail.field_skip_if_no_course")}</span>
                <strong>{professor.daily_schedule_skip_if_no_course ? t("common.yes") : t("common.no")}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">{t("admin.professor_detail.field_last_activation")}</span>
                <strong>{professor.last_activation_email_sent_at ? formatDate(professor.last_activation_email_sent_at, language) : t("admin.professor_detail.never")}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">{t("admin.professor_detail.field_last_login")}</span>
                <strong>{professor.last_login_at ? formatDate(professor.last_login_at, language) : t("admin.professor_detail.no_login_recorded")}</strong>
              </article>
            </div>
            {canManageCollaborators ? (
              <div className="row top-gap-sm">
                <Link className="mode-link" href={`/admin/professors/${professor.id}?tab=profil&edit_profile=1`}>
                  {t("common.edit")}
                </Link>
                <form action={sendAdminCollaboratorPasswordLinkAction}>
                  <input type="hidden" name="professor_id" value={professor.id} />
                  <input type="hidden" name="return_tab" value="profil" />
                  <button type="submit">{t("admin.professor_detail.send_access_link")}</button>
                </form>
              </div>
            ) : null}
          </article>

          {canManageCollaborators ? (
            <CollaboratorDailyScheduleForm
              professorId={professor.id}
              email={professor.email}
              active={professor.active}
              returnTo={tabHref(professor.id, "profil")}
              language={language}
            />
          ) : null}

          {isEditProfileOpen && canManageCollaborators ? (
            <section className="modal-overlay" role="dialog" aria-modal="true" aria-label={t("admin.professor_detail.edit_dialog_aria")}>
              <section className="modal-panel professor-profile-modal">
                <Link className="modal-close-x" href={`/admin/professors/${professor.id}?tab=profil`} aria-label={t("common.close")}>
                  ×
                </Link>
                <h3 className="modal-title">{t("admin.professor_detail.edit_title")}</h3>
                <form action={updateAdminCollaboratorProfileAction} className="grid cols-2 professor-profile-modal-form">
              <input type="hidden" name="professor_id" value={professor.id} />
              <input type="hidden" name="return_tab" value="profil" />

              <label>
                {t("common.email")}
                <input type="email" name="email" defaultValue={professor.email} required />
              </label>

              <label>
                {t("admin.professor_detail.field_status")}
                <select name="active" defaultValue={professor.active ? "true" : "false"}>
                  <option value="true">{t("common.active")}</option>
                  <option value="false">{t("common.inactive")}</option>
                </select>
              </label>

              <label>
                {t("admin.professor_detail.field_first_name")}
                <input type="text" name="first_name" defaultValue={professor.first_name} required maxLength={100} />
              </label>

              <label>
                {t("admin.professor_detail.field_last_name")}
                <input type="text" name="last_name" defaultValue={professor.last_name} required maxLength={100} />
              </label>

              <label>
                {t("admin.professor_detail.field_phone")}
                <input type="text" name="phone" defaultValue={professor.phone ?? ""} maxLength={30} />
              </label>

              <label>
                {t("admin.professors.siret_label")}
                <input type="text" name="siret" defaultValue={professor.siret ?? ""} maxLength={30} />
              </label>

              <label>
                {t("admin.professors.iban_label")}
                <input type="text" name="iban" defaultValue={professor.iban ?? ""} maxLength={34} />
              </label>

              <label>
                {t("admin.professor_detail.field_payout_currency")}
                <select name="payout_currency" defaultValue={defaultRateCurrency}>
                  {availableCurrencies.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </select>
              </label>

              <label className="span-2">
                {t("admin.professor_detail.field_zoom_link")}
                <input type="url" name="zoom_link" defaultValue={professor.zoom_link ?? ""} />
              </label>

              <label className="span-2">
                {t("admin.professor_detail.field_address")}
                <input type="text" name="address_line" defaultValue={professor.address_line ?? ""} maxLength={255} />
              </label>

              <label>
                {t("admin.professor_detail.field_teacher_invoice_counter")}
                <input type="number" name="teacher_invoice_counter" min={1} step={1} defaultValue={professor.teacher_invoice_counter} required />
              </label>

              <label className="checkline">
                <input type="checkbox" name="teacher_is_vat_applicable" defaultChecked={professor.teacher_is_vat_applicable} />
                {t("admin.professor_detail.field_teacher_vat_applicable")}
              </label>

              <label>
                {t("admin.professor_detail.field_teacher_vat_rate_percent")}
                <input type="number" name="teacher_vat_rate" min="0" max="99.99" step="0.01" defaultValue={professor.teacher_vat_rate ?? ""} />
              </label>

              <label>
                {t("admin.professor_detail.field_teacher_siret")}
                <input type="text" name="teacher_siret" defaultValue={professor.teacher_siret ?? ""} maxLength={64} />
              </label>

              <label>
                {t("admin.professor_detail.field_teacher_iban")}
                <input type="text" name="teacher_iban" defaultValue={professor.teacher_iban ?? ""} maxLength={64} />
              </label>

              <label className="span-2">
                {t("admin.professor_detail.field_teacher_company_name")}
                <input type="text" name="teacher_company_name" defaultValue={professor.teacher_company_name ?? ""} maxLength={255} />
              </label>

              <label className="span-2">
                {t("admin.professor_detail.field_teacher_company_address")}
                <textarea name="teacher_company_address" rows={3} defaultValue={professor.teacher_company_address ?? ""} maxLength={2000} />
              </label>

              <label className="span-2">
                {t("admin.professor_detail.field_spoken_languages")}
                <select name="spoken_languages" multiple size={6} defaultValue={professor.spoken_languages}>
                  {COLLABORATOR_LANGUAGE_OPTIONS.map((language) => (
                    <option key={language.value} value={language.value}>
                      {t(language.labelKey)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="checkline">
                <input type="checkbox" name="is_coach" defaultChecked={professor.is_coach} />
                {t("admin.professor_detail.field_coach_mode")}
              </label>

              <label className="checkline">
                <input type="checkbox" name="is_admin" defaultChecked={professor.role === "admin"} />
                {t("admin.professor_detail.field_administrator_right")}
              </label>

              <label className="checkline">
                <input type="checkbox" name="daily_schedule_email_enabled" defaultChecked={professor.daily_schedule_email_enabled} />
                {t("admin.professor_detail.field_daily_schedule_email")}
              </label>

              <label>
                {t("admin.professor_detail.field_daily_schedule_time")}
                <input type="time" name="daily_schedule_email_time" defaultValue={professor.daily_schedule_email_time || "07:00"} />
              </label>

              <label className="checkline">
                <input type="checkbox" name="daily_schedule_skip_if_no_course" defaultChecked={professor.daily_schedule_skip_if_no_course} />
                {t("admin.professor_detail.field_skip_if_no_course")}
              </label>

              <div className="row span-2 modal-actions-end professor-profile-modal-actions">
                <button type="submit">{t("common.save")}</button>
                <Link className="reset-link" href={`/admin/professors/${professor.id}?tab=profil`}>
                  {t("common.cancel")}
                </Link>
              </div>
                </form>
              </section>
            </section>
          ) : null}

          <article className="card span-2">
            <div className="row spread">
              <h3>{t("admin.professor_detail.contract_title")}</h3>
              <span className="badge">{professor.contract ? t("admin.professor_detail.contract_uploaded") : t("admin.professor_detail.contract_none")}</span>
            </div>

            {professor.contract ? (
              <div className="list">
                <article className="item row spread">
                  <span className="muted">{t("admin.professor_detail.contract_file_name")}</span>
                  <strong>{professor.contract.file_name}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.professor_detail.contract_size")}</span>
                  <strong>{Math.max(1, Math.round(professor.contract.size_bytes / 1024))} KB</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.professor_detail.contract_uploaded_at")}</span>
                  <strong>{formatDate(professor.contract.uploaded_at, language)}</strong>
                </article>
              </div>
            ) : (
              <p className="muted">{t("admin.professor_detail.contract_no_file")}</p>
            )}

            <div className="row">
              {professor.contract && canManageCollaborators ? (
                <a className="reset-link" href={`/admin/professors/${professor.id}/contract`}>
                  {t("admin.professor_detail.contract_download")}
                </a>
              ) : null}
            </div>

            {canManageCollaborators ? (
              <form action={uploadAdminCollaboratorContractAction} className="grid cols-3" encType="multipart/form-data">
                <input type="hidden" name="professor_id" value={professor.id} />
                <input type="hidden" name="return_tab" value="profil" />
                <label className="span-2">
                  {t("admin.professor_detail.contract_pdf_file")}
                  <input type="file" name="contract_file" accept="application/pdf" required />
                </label>
                <div className="row">
                  <button type="submit">{t("admin.professor_detail.contract_upload_replace")}</button>
                </div>
              </form>
            ) : null}

            {professor.contract && canManageCollaborators ? (
              <form action={deleteAdminCollaboratorContractAction} className="row">
                <input type="hidden" name="professor_id" value={professor.id} />
                <input type="hidden" name="return_tab" value="profil" />
                <button type="submit" className="danger">
                  {t("admin.professor_detail.contract_delete")}
                </button>
              </form>
            ) : null}
          </article>
        </section>
      ) : null}

      {currentTab === "droits" ? (
        <section className="card">
          <h3>{t("admin.professor_detail.permissions_title")}</h3>
          <p className="muted">{t("admin.professor_detail.permissions_subtitle")}</p>
          <form action={updateAdminCollaboratorPermissionsAction} className="grid cols-2">
            <input type="hidden" name="professor_id" value={professor.id} />
            <article className="item span-2">
              <label className="checkline">
                <input type="checkbox" name="teacher_profile" defaultChecked={isTeacherProfile} />
                {t("admin.professor_detail.permissions_teacher_profile")}
              </label>
              <p className="muted">{t("admin.professor_detail.permissions_teacher_profile_help")}</p>
            </article>
            <article className="item span-2">
              <label className="checkline">
                <input
                  type="checkbox"
                  name="manager_profile"
                  defaultChecked={isManagerProfile}
                />
                {t("admin.professor_detail.permissions_manager_profile")}
              </label>
              <p className="muted">{t("admin.professor_detail.permissions_manager_profile_help")}</p>
            </article>
            <article className="item span-2">
              <label className="checkline">
                <input type="checkbox" name="accountant_profile" defaultChecked={isAccountantProfile} />
                {t("admin.professor_detail.permissions_accountant_profile")}
              </label>
              <p className="muted">{t("admin.professor_detail.permissions_accountant_profile_help")}</p>
            </article>
            <article className="item span-2">
              <label className="checkline">
                <input type="checkbox" name="is_admin" defaultChecked={professor.role === "admin"} />
                {t("admin.professor_detail.permissions_admin_all")}
              </label>
              <p className="muted">{t("admin.professor_detail.permissions_admin_all_help")}</p>
            </article>
            <article className="item span-2">
              <label>
                {t("admin.professor_detail.permissions.simulation_location_scope")}
                <select
                  name="planning_simulation_location_id"
                  defaultValue={selectedSimulationLocationId}
                >
                  <option value="">{t("admin.professor_detail.permissions.simulation_location_all")}</option>
                  {simulationLocationOptions
                    .slice()
                    .sort((a, b) => a.name.localeCompare(b.name, "fr"))
                    .map((location) => (
                      <option key={location.id} value={location.id}>
                        {location.name}
                      </option>
                    ))}
                </select>
              </label>
              <p className="muted">{t("admin.professor_detail.permissions.simulation_location_scope_help")}</p>
            </article>
            <article className="item span-2">
              <label>
                {t("admin.professor_detail.permissions.check_deposits_location_scope")}
                <select
                  name="check_deposits_location_id"
                  defaultValue={selectedCheckDepositsLocationId}
                >
                  <option value="">{t("admin.professor_detail.permissions.check_deposits_location_required")}</option>
                  {locations
                    .filter((location) => !location.is_online)
                    .slice()
                    .sort((a, b) => a.name.localeCompare(b.name, "fr"))
                    .map((location) => (
                      <option key={location.id} value={location.id}>
                        {location.name}
                      </option>
                    ))}
                </select>
              </label>
              <p className="muted">{t("admin.professor_detail.permissions.check_deposits_location_scope_help")}</p>
            </article>

            {PERMISSION_SECTIONS.map((section) => (
              <article key={section.titleKey} className="item">
                <strong>{t(section.titleKey)}</strong>
                <div className="grid">
                  {section.keys.map(({ key, labelKey }) => (
                    <label key={key} className="checkline">
                      <input type="checkbox" name={key} defaultChecked={Boolean(permissionState[key])} />
                      {t(labelKey)}
                    </label>
                  ))}
                </div>
              </article>
            ))}

            <div className="row span-2">
              <button type="submit">{t("admin.professor_detail.permissions_save")}</button>
            </div>
          </form>
        </section>
      ) : null}

      {currentTab === "tarifs" ? (
        <section className="grid cols-2">
          <article className="card span-2">
            <form action={updateAdminCollaboratorRatesAction} className="grid">
              <AdminProfessorPayrollEditor
                professorId={professor.id}
                effectiveFrom={payoutAsOf}
                currencyCode={activeBaseRate?.currency_code ?? defaultRateCurrency}
                availableCurrencies={availableCurrencies}
                baseHourlyRate={activeBaseRate?.hourly_rate ?? ""}
                activities={payrollActivities}
                activeGeneralPeriodLabel={activeGeneralPeriodLabel}
                language={language}
              />
            </form>
          </article>

          {showLegacyContractGrid ? (
            <>
              <article className="card">
                <div className="row spread">
                  <h3>{t("admin.professor_detail.legacy_grids_title")}</h3>
                  <Link className="mode-link" href={tabHref(professor.id, "tarifs")}>
                    {t("admin.professor_detail.new_grid")}
                  </Link>
                </div>
                {contractGrids.length === 0 ? (
                  <p className="muted">{t("admin.professor_detail.no_contract_grid")}</p>
                ) : (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>{t("common.location")}</th>
                          <th>{t("common.start")}</th>
                          <th>{t("admin.professor_detail.end")}</th>
                          <th>{t("admin.professor_detail.lines")}</th>
                          <th>{t("common.status")}</th>
                          <th>{t("common.actions")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {contractGrids.map((row) => (
                          <tr key={row.id}>
                            <td>{row.location_label}</td>
                            <td>{row.valid_from}</td>
                            <td>{row.valid_to ?? "-"}</td>
                            <td>{row.lines.length}</td>
                            <td>{row.is_active_today ? t("admin.professor_detail.grid_status_active") : t("admin.professor_detail.grid_status_history_future")}</td>
                            <td>
                              <Link className="mode-link" href={`/admin/professors/${professor.id}?tab=tarifs&legacy_contract=1&edit_grid_id=${row.id}`}>
                                {t("common.edit")}
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <article className="item top-gap-sm">
                  <strong>{t("admin.professor_detail.legacy_fallback_title")}</strong>
                  <p className="muted">
                    {t("admin.professor_detail.legacy_fallback_help")}
                  </p>
                  <p className="muted">{t("admin.professor_detail.legacy_rates_count", { count: rates.length })}</p>
                </article>
              </article>

              <article className="card">
                <h3>{selectedContractGrid ? t("admin.professor_detail.edit_contract_grid") : t("admin.professor_detail.create_contract_grid")}</h3>
                <form action={upsertAdminCollaboratorContractGridAction} className="grid">
                  <input type="hidden" name="professor_id" value={professor.id} />
                  {selectedContractGrid ? <input type="hidden" name="grid_id" value={selectedContractGrid.id} /> : null}

                  <label>
                    {t("admin.professor_detail.effective_date")}
                    <input type="date" name="valid_from" defaultValue={selectedContractGrid?.valid_from ?? effectiveDateDefault} required />
                  </label>

                  <label>
                    {t("admin.professor_detail.end_date_optional")}
                    <input type="date" name="valid_to" defaultValue={selectedContractGrid?.valid_to ?? ""} />
                  </label>

                  <label>
                    {t("common.location")}
                    <select name="location_code" defaultValue={selectedContractGrid?.location_code ?? "NONE"}>
                      <option value="NONE">{t("admin.professor_detail.all_locations_unspecified")}</option>
                      {contractLocationOptions.map((option) => (
                        <option key={option.code} value={option.code}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    {t("admin.professor_detail.clone_from_optional")}
                    <select name="clone_from_grid_id" defaultValue="">
                      <option value="">{t("admin.professor_detail.do_not_clone")}</option>
                      {contractGrids.map((row) => (
                        <option key={`clone-${row.id}`} value={row.id}>
                          {row.location_label} | {row.valid_from}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="span-2">
                    {t("common.notes")}
                    <textarea name="notes" rows={2} defaultValue={selectedContractGrid?.notes ?? ""} />
                  </label>

                  <article className="item span-2">
                    <strong>{t("admin.professor_detail.grid_lines")}</strong>
                    <p className="muted">{t("admin.professor_detail.headcount_rules_help")}</p>
                    <div className="table-wrap top-gap-sm">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>{t("admin.professor_detail.activity_backoffice")}</th>
                            <th>{t("admin.professor_detail.derived_mode")}</th>
                            <th>{t("admin.professor_detail.derived_duration")}</th>
                            <th>{t("admin.professor_detail.default_rate")}</th>
                            <th>{t("admin.professor_detail.headcount_rules")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Array.from({ length: contractLineSlots }).map((_, index) => {
                            const line = selectedGridLines[index];
                            const defaultCourseTypeId =
                              line?.course_type_id ?? (line ? (courseTypeIdByNormalizedName.get(normalizeLookupKey(line.service_type)) ?? "") : "");
                            const derivedCourseType = defaultCourseTypeId ? courseTypeById.get(defaultCourseTypeId) : undefined;
                            const derivedMode = derivedCourseType
                              ? contractModeLabel(
                                  derivedCourseType.mode === "ONLINE" ? "EN_LIGNE" : derivedCourseType.mode === "ONSITE" ? "PRESENTIEL" : "AUTRE",
                                  language,
                                )
                              : (line ? contractModeLabel(line.mode, language) : "-");
                            const derivedDuration = derivedCourseType?.duration_minutes ?? line?.reference_duration_minutes ?? null;
                            return (
                              <tr key={`grid-line-${index}`}>
                                <td>
                                  <select name={`line_course_type_id_${index}`} defaultValue={defaultCourseTypeId}>
                                    <option value="">{t("admin.professor_detail.select_activity")}</option>
                                    {courseTypes.map((courseType) => (
                                      <option key={`grid-line-course-type-${index}-${courseType.id}`} value={courseType.id}>
                                        {courseType.name}
                                      </option>
                                    ))}
                                  </select>
                                </td>
                                <td>
                                  <span className="muted">{derivedMode}</span>
                                </td>
                                <td>
                                  <span className="muted">{derivedDuration ?? "-"}</span>
                                </td>
                                <td>
                                  <input type="number" name={`line_default_rate_${index}`} min="0" step="0.01" defaultValue={line?.default_hourly_rate ?? ""} />
                                </td>
                                <td>
                                  <input
                                    type="text"
                                    name={`line_rules_${index}`}
                                    defaultValue={line ? encodeHeadcountRules(line.rules) : ""}
                                    placeholder={t("admin.professor_detail.headcount_rules_placeholder")}
                                  />
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </article>

                  <div className="row">
                    <button type="submit">{selectedContractGrid ? t("admin.professor_detail.update_grid") : t("admin.professor_detail.create_grid")}</button>
                    {selectedContractGrid ? (
                      <Link className="reset-link" href={`${tabHref(professor.id, "tarifs")}&legacy_contract=1`}>
                        {t("admin.professor_detail.cancel_edit")}
                      </Link>
                    ) : null}
                  </div>
                </form>
              </article>

              <article className="card span-2">
                <h3>{t("admin.professor_detail.coach_preview_readonly")}</h3>
                {contractGrids.filter((row) => row.is_active_today).length === 0 ? (
                  <p className="muted">{t("admin.professor_detail.no_active_grid_today")}</p>
                ) : (
                  <div className="list">
                    {contractGrids
                      .filter((row) => row.is_active_today)
                      .map((grid) => (
                        <article key={`active-grid-${grid.id}`} className="item">
                          <div className="row spread">
                            <strong>{grid.location_label}</strong>
                            <span className="badge">
                              {grid.valid_from} - {grid.valid_to ?? t("admin.professor_detail.not_defined")}
                            </span>
                          </div>
                          <div className="table-wrap top-gap-sm">
                            <table className="data-table">
                              <thead>
                                <tr>
                                  <th>{t("admin.professor_detail.activity")}</th>
                                  <th>{t("admin.professor_detail.mode")}</th>
                                  <th>{t("admin.professor_detail.reference_duration")}</th>
                                  <th>{t("admin.professor_detail.default_rate")}</th>
                                  <th>{t("admin.professor_detail.headcount_rules")}</th>
                                </tr>
                              </thead>
                              <tbody>
                                {grid.lines.map((line) => (
                                  <tr key={`preview-line-${line.id}`}>
                                    <td>{line.course_type_name || line.service_type}</td>
                                    <td>{contractModeLabel(line.mode, language)}</td>
                                    <td>{line.reference_duration_minutes ?? "-"}</td>
                                    <td>{line.default_hourly_rate ?? "-"}</td>
                                    <td>{line.rules.length > 0 ? encodeHeadcountRules(line.rules) : "-"}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </article>
                      ))}
                  </div>
                )}
              </article>
            </>
          ) : (
            <article className="card span-2">
              <h3>{t("admin.professor_detail.contract_grids_title")}</h3>
              <p className="muted">
                {t("admin.professor_detail.contract_grids_hidden_help")}
              </p>
              <Link className="mode-link" href={`${tabHref(professor.id, "tarifs")}&legacy_contract=1`}>
                {t("admin.professor_detail.show_legacy_grids")}
              </Link>
            </article>
          )}
        </section>
      ) : null}

      {currentTab === "solde" ? (
        <section className="card">
          <div className="row spread">
            <h3>{t("admin.professor_detail.balance_title")}</h3>
            <span className="badge">
              {payoutLedger?.total_due ?? "0.00"} {payoutLedger?.currency ?? professor.payout_currency}
            </span>
          </div>
          <form method="get" className="row top-gap-sm">
            <input type="hidden" name="tab" value="solde" />
            <label style={{ minWidth: "220px" }}>
              {t("admin.professor_detail.as_of_date")}
              <input type="date" name="payout_as_of" defaultValue={payoutAsOf} />
            </label>
            <button type="submit">{t("admin.professor_detail.refresh")}</button>
          </form>
          {payoutLedger && payoutLedger.rows.length > 0 ? (
            <div className="table-wrap top-gap-sm">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t("admin.professor_detail.column_date_time")}</th>
                    <th>{t("admin.professor_detail.column_description")}</th>
                    <th>{t("admin.professor_detail.column_income")}</th>
                    <th>{t("admin.professor_detail.column_payment")}</th>
                    <th>{t("admin.professor_detail.column_cumulative_balance")}</th>
                  </tr>
                </thead>
                <tbody>
                  {payoutLedger.rows.map((row) => (
                    <tr key={`payout-ledger-${row.session_id}`}>
                      <td>
                        {formatDate(row.start_at_utc, language)}
                        <br />
                        <small className="muted">{row.duration_hours} h</small>
                      </td>
                      <td>
                        {row.course_type_name}
                        <br />
                        <small className="muted">{row.location_name}</small>
                      </td>
                      <td>
                        {row.amount !== null ? `${row.amount} ${row.currency ?? payoutLedger.currency}` : "-"}
                        <br />
                        <small className="muted">
                          {row.hourly_rate !== null ? `${row.hourly_rate} / h` : t("admin.professor_detail.rate_undefined")}
                        </small>
                      </td>
                      <td>
                        <span className={`status-pill ${payoutStatusToneClass(row.payout_status)}`}>
                          {payoutStatusLabel(row.payout_status, language)}
                        </span>
                      </td>
                      <td>
                        {row.cumulative_due} {payoutLedger.currency}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted top-gap-sm">{t("admin.professor_detail.no_recorded_course")}</p>
          )}
        </section>
      ) : null}

      {currentTab === "planning" ? (
        <section className="card">
          <div className="row spread">
            <h3>{t("admin.professor_detail.schedule_title")}</h3>
            <span className="badge">{agendaRange.title}</span>
          </div>

          {canManageCollaborators ? (
            <CollaboratorDailyScheduleForm
              professorId={professor.id}
              email={professor.email}
              active={professor.active}
              returnTo={`${tabHref(professor.id, "planning")}&agenda_view=${agendaView}&agenda_date=${agendaDate}`}
              language={language}
            />
          ) : null}

          <form method="get" className="grid cols-4">
            <input type="hidden" name="tab" value="planning" />

            <label>
              {t("admin.professor_detail.schedule_view")}
              <select name="agenda_view" defaultValue={agendaView}>
                <option value="month">{t("admin.professor_detail.schedule_month")}</option>
                <option value="week">{t("admin.professor_detail.schedule_week")}</option>
                <option value="day">{t("admin.professor_detail.schedule_day")}</option>
              </select>
            </label>

            <label>
              {t("admin.professor_detail.schedule_reference_date")}
              <input type="date" name="agenda_date" defaultValue={agendaDate} />
            </label>

            <div className="row">
              <button type="submit">{t("common.apply")}</button>
              <a className="reset-link" href={tabHref(professor.id, "planning")}>
                {t("common.reset")}
              </a>
            </div>
          </form>

          <div className="agenda-columns">
            {agendaDays.map((day) => (
              <article key={day.key} className="agenda-day-card">
                <h4>{day.label}</h4>
                {day.sessions.length === 0 ? (
                  <p className="muted">{t("admin.professor_detail.no_course")}</p>
                ) : (
                  <div className="list">
                    {day.sessions.map((session) => (
                      <article key={session.id} className="item">
                        <div className="row spread">
                          <strong>{formatAgendaTime(session.start_at_utc, sortLocale)} - {formatAgendaTime(session.end_at_utc, sortLocale)}</strong>
                          <span className="badge">
                            {session.booked_count}/{session.capacity_max}
                          </span>
                        </div>
                        <p>
                          {session.title}
                          <br />
                          <small className="muted">
                            {courseTypeNameById.get(session.course_type_id) ?? session.course_type_id} / {locationNameById.get(session.location_id) ?? session.location_id}
                          </small>
                        </p>
                        <p className="muted">{t("admin.professor_detail.status_prefix", { status: session.status })}</p>
                      </article>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </section>
  );
}
