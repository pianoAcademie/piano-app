import Link from "next/link";
import { redirect } from "next/navigation";

import AdminProfessorPayrollEditor from "../../../../components/admin-professor-payroll-editor";
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
} from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;
type Tab = "profil" | "droits" | "tarifs" | "solde" | "planning";
type AgendaView = "month" | "week" | "day";

const COLLABORATOR_LANGUAGE_OPTIONS: string[] = [
  "Francais",
  "Anglais",
  "Espagnol",
  "Italien",
  "Allemand",
  "Portugais",
  "Russe",
  "Chinois",
  "Japonais",
];

type PageProps = {
  params: { id: string };
  searchParams: SearchParams;
};

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

function startOfMonthUtc(date: Date): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1));
}

function startOfWeekUtc(date: Date): Date {
  const day = date.getUTCDay();
  const offsetFromMonday = (day + 6) % 7;
  return addUtcDays(date, -offsetFromMonday);
}

function todayKeyUtc(): string {
  return utcDateToKey(new Date());
}

function buildAgendaRange(view: AgendaView, focusDayKey: string): AgendaRange {
  const focusDate = keyToUtcDate(focusDayKey);

  if (view === "day") {
    const from = focusDate;
    const toExclusive = addUtcDays(from, 1);
    const to = new Date(toExclusive.getTime() - 1);

    return {
      from,
      to,
      dayKeys: [focusDayKey],
      title: new Intl.DateTimeFormat("fr-FR", {
        weekday: "long",
        day: "2-digit",
        month: "long",
        year: "numeric",
        timeZone: "UTC",
      }).format(from),
    };
  }

  if (view === "week") {
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
      title: `${new Intl.DateTimeFormat("fr-FR", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      }).format(from)} - ${new Intl.DateTimeFormat("fr-FR", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      }).format(lastDay)}`,
    };
  }

  const from = startOfMonthUtc(focusDate);
  const nextMonth = new Date(Date.UTC(from.getUTCFullYear(), from.getUTCMonth() + 1, 1));
  const to = new Date(nextMonth.getTime() - 1);

  const dayKeys: string[] = [];
  let cursor = new Date(from.getTime());
  while (cursor < nextMonth) {
    dayKeys.push(utcDateToKey(cursor));
    cursor = addUtcDays(cursor, 1);
  }

  return {
    from,
    to,
    dayKeys,
    title: new Intl.DateTimeFormat("fr-FR", {
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    }).format(from),
  };
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString("fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function dayLabel(dayKey: string, view: AgendaView): string {
  const date = keyToUtcDate(dayKey);
  if (view === "day") {
    return new Intl.DateTimeFormat("fr-FR", {
      weekday: "long",
      day: "2-digit",
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    }).format(date);
  }

  return new Intl.DateTimeFormat("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  }).format(date);
}

function tabHref(professorId: string, tab: Tab): string {
  return `/admin/professors/${professorId}?tab=${tab}`;
}

function contractModeLabel(mode: string): string {
  const normalized = mode.trim().toUpperCase();
  if (normalized === "PRESENTIEL") {
    return "Presentiel";
  }
  if (normalized === "EN_LIGNE") {
    return "En ligne";
  }
  return "Autre";
}

function activityModeLabel(mode: string): string {
  const normalized = mode.trim().toUpperCase();
  if (normalized === "ONSITE") {
    return "Presentiel";
  }
  if (normalized === "ONLINE") {
    return "En ligne";
  }
  return "Tous";
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

function payoutStatusLabel(status: "PENDING" | "APPROVED" | "PAID" | null): string {
  if (status === "PENDING") {
    return "En attente";
  }
  if (status === "APPROVED") {
    return "Valide";
  }
  if (status === "PAID") {
    return "Paye";
  }
  return "Calcule";
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

const PERMISSION_SECTIONS: Array<{ title: string; keys: Array<{ key: string; label: string }> }> = [
  {
    title: "Gerer soi-meme",
    keys: [
      { key: "can_take_attendance", label: "Prendre les presences" },
      { key: "can_record_payments_with_attendance", label: "Enregistrer les paiements avec presence" },
      { key: "can_edit_own_sessions", label: "Modifier ses propres lecons/evenements" },
      { key: "can_view_pay_details", label: "Voir les details de la paie" },
      { key: "can_manage_mileage_log", label: "Ajouter/modifier le journal de kilometrage" },
    ],
  },
  {
    title: "Gerer d'autres enseignants",
    keys: [
      { key: "can_view_other_teachers_contacts", label: "Afficher les coordonnees des autres enseignants et utilisateurs" },
      { key: "can_manage_other_teachers_students_and_sessions", label: "Gerer les etudiants et les lecons/evenements des autres enseignants" },
      { key: "can_view_other_teachers_sessions", label: "Voir les lecons/evenements des autres enseignants" },
    ],
  },
  {
    title: "Gerer les etudiants et les parents",
    keys: [
      { key: "can_message_clients", label: "Envoyer des messages aux eleves (groupe et individuel)" },
      { key: "can_view_student_parent_addresses_phones", label: "Afficher les adresses et numeros de telephone d'etudiant/parent" },
      { key: "can_view_student_parent_emails", label: "Afficher les courriels d'etudiant/parent" },
      { key: "can_view_student_attachments", label: "Afficher/telecharger les pieces jointes du profil d'etudiant" },
    ],
  },
  {
    title: "Gerer d'autres fonctionnalites",
    keys: [
      { key: "can_manage_invoices_and_accounts", label: "Ajouter/voir les factures et les comptes" },
      { key: "can_manage_expenses_and_other_income", label: "Ajouter/modifier des depenses et autres revenus" },
      { key: "can_manage_shared_online_resources", label: "Ajouter/modifier/supprimer des ressources en ligne (espace partage)" },
      { key: "can_manage_website_and_news", label: "Modifier le site web et publier des nouvelles" },
      { key: "can_create_and_view_reports", label: "Creer/afficher des rapports" },
    ],
  },
];

export default async function AdminCollaboratorDetailPage({ params, searchParams }: PageProps): Promise<JSX.Element> {
  const token = getAdminToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const currentTab = parseTab(readParam(searchParams, "tab"));
  const isEditProfileOpen = readParam(searchParams, "edit_profile") === "1";
  const editGridId = readParam(searchParams, "edit_grid_id");
  const showLegacyContractGrid = readParam(searchParams, "legacy_contract") === "1";
  const agendaView = parseAgendaView(readParam(searchParams, "agenda_view"));
  const agendaDateInput = readParam(searchParams, "agenda_date");
  const agendaDate = isDateKey(agendaDateInput) ? agendaDateInput : todayKeyUtc();
  const payoutAsOfInput = readParam(searchParams, "payout_as_of");
  const payoutAsOf = isDateKey(payoutAsOfInput) ? payoutAsOfInput : todayKeyUtc();
  const agendaRange = buildAgendaRange(agendaView, agendaDate);

  const sessionsQuery = new URLSearchParams();
  sessionsQuery.set("professor_id", params.id);
  sessionsQuery.set("from", agendaRange.from.toISOString());
  sessionsQuery.set("to", agendaRange.to.toISOString());
  const payoutLedgerQuery = new URLSearchParams();
  payoutLedgerQuery.set("as_of", payoutAsOf);

  const contractGridsRequest = showLegacyContractGrid
    ? backendRequest<AdminProfessorContractGridOut[]>(`/api/v1/admin/collaborators/${params.id}/contract-grids`, {}, token)
    : Promise.resolve({ ok: true as const, status: 200, data: [] as AdminProfessorContractGridOut[] });
  const contractLocationsRequest = showLegacyContractGrid
    ? backendRequest<AdminProfessorContractLocationOptionOut[]>("/api/v1/admin/collaborators/contract-grid/locations", {}, token)
    : Promise.resolve({ ok: true as const, status: 200, data: [] as AdminProfessorContractLocationOptionOut[] });
  const payoutLedgerRequest =
    currentTab === "solde"
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
    backendRequest<AdminProfessorRateOut[]>(`/api/v1/admin/collaborators/${params.id}/rates`, {}, token),
    backendRequest<CourseTypeOut[]>("/api/v1/course-types", {}, token),
    backendRequest<AdminSessionOut[]>(`/api/v1/admin/sessions?${sessionsQuery.toString()}`, {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations", {}, token),
    backendRequest<AdminConfigAccountOut>("/api/v1/admin/config/account", {}, token),
    backendRequest<AdminProfessorDefaultGridOut>("/api/v1/admin/config/professor-default-grid", {}, token),
    contractGridsRequest,
    contractLocationsRequest,
    payoutLedgerRequest,
  ]);

  if (!profResult.ok) {
    if (profResult.status === 404) {
      redirect("/admin/professors?error=Collaborateur%20introuvable");
    }
    return <section className="flash-err">Erreur backend: {profResult.message}</section>;
  }

  const professor = profResult.data;
  const rates = ratesResult.ok ? ratesResult.data : [];
  const courseTypes = courseTypesResult.ok ? courseTypesResult.data : [];
  const sessions = sessionsResult.ok ? sessionsResult.data : [];
  const locations = locationsResult.ok ? locationsResult.data : [];
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
    .sort((a, b) => a.name.localeCompare(b.name, "fr"));
  const defaultGridByCourseTypeId = new Map(defaultProfessorGrid.lines.map((line) => [line.course_type_id, line]));
  const professorReferenceLine =
    defaultProfessorGrid.lines.find((line) => line.rules.length > 0)
    ?? defaultProfessorGrid.lines.find((line) => line.default_hourly_rate !== null)
    ?? null;
  const professorReferenceGrid = professorReferenceLine
    ? {
        default_hourly_rate: professorReferenceLine.default_hourly_rate,
        rules: professorReferenceLine.rules.map((rule) => ({
          min_students: rule.min_students,
          max_students: rule.max_students,
          hourly_rate: rule.hourly_rate,
        })),
      }
    : null;
  const professorHasHeadcountOverride = Boolean(activeBaseRate && activeBaseRate.rules.length > 0);
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
    const initialMode: "GENERAL" | "PROFESSOR" | "SPECIFIC" = hasSpecific
      ? "SPECIFIC"
      : (activeBaseRate ? "PROFESSOR" : "GENERAL");

    return {
      course_type_id: courseType.id,
      course_type_name: courseType.name,
      mode_label: activityModeLabel(courseType.mode),
      reference_duration_minutes: courseType.duration_minutes,
      initial_mode: initialMode,
      general_grid: generalGrid,
      specific_grid: specificGrid,
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
    label: dayLabel(dayKey, agendaView),
    sessions: sessionsByDay.get(dayKey) ?? [],
  }));

  const fullName = `${professor.first_name} ${professor.last_name}`.trim();
  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error");

  const tabs: Array<{ id: Tab; label: string }> = [
    { id: "profil", label: "Fiche" },
    { id: "droits", label: "Droits" },
    { id: "tarifs", label: "Configuration de la paie" },
    { id: "solde", label: "Solde du professeur" },
    { id: "planning", label: "Planning" },
  ];

  return (
    <section className="admin-page-grid">
      <CollaboratorClientChunkAnchor />
      <section className="client-hero card">
        <div className="row spread">
          <Link className="reset-link" href="/admin/professors">
            Retour collaborateurs
          </Link>
          <form action={adminViewTeacherPortalAction} target="_blank" rel="noopener noreferrer">
            <input type="hidden" name="teacher_id" value={professor.id} />
            <input type="hidden" name="return_to" value={`/admin/professors/${professor.id}?tab=${currentTab}`} />
            <button type="submit" className="mode-link">
              Vue professeur
            </button>
          </form>
          <span className={`status-pill ${professor.active ? "status-ok" : "status-off"}`}>{professor.active ? "Actif" : "Inactif"}</span>
        </div>
        <div className="client-hero-main">
          <div className="client-avatar">{(professor.first_name ?? "").slice(0, 1)}{(professor.last_name ?? "").slice(0, 1)}</div>
          <div>
            <h2>{fullName || professor.email}</h2>
            <p className="muted">
              {professor.email} | Tel: {professor.phone ?? "-"} | Role: {professor.role} | Coach: {professor.is_coach ? "Oui" : "Non"}
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
      {!ratesResult.ok ? <section className="flash-err">Erreur rates: {ratesResult.message}</section> : null}
      {!sessionsResult.ok ? <section className="flash-err">Erreur planning: {sessionsResult.message}</section> : null}
      {!accountResult.ok ? <section className="flash-err">Erreur devises: {accountResult.message}</section> : null}
      {!defaultProfessorGridResult.ok ? <section className="flash-err">Erreur grille generale: {defaultProfessorGridResult.message}</section> : null}
      {showLegacyContractGrid && !contractGridsResult.ok ? <section className="flash-err">Erreur grilles contractuelles: {contractGridsResult.message}</section> : null}
      {showLegacyContractGrid && !contractLocationsResult.ok ? <section className="flash-err">Erreur lieux contractuels: {contractLocationsResult.message}</section> : null}
      {currentTab === "solde" && !payoutLedgerResult.ok ? <section className="flash-err">Erreur solde paie: {payoutLedgerResult.message}</section> : null}

      {currentTab === "profil" ? (
        <section className="grid cols-2">
          <article className="card">
            <h3>Informations collaborateur</h3>
            <div className="list">
              <article className="item row spread">
                <span className="muted">Email</span>
                <strong>{professor.email}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Telephone</span>
                <strong>{professor.phone ?? "Non renseigne"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">SIRET</span>
                <strong>{professor.siret ?? "Non renseigne"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">IBAN</span>
                <strong>{professor.iban ?? "Non renseigne"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Adresse</span>
                <strong>{professor.address_line ?? "Non renseignee"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Compteur facture prof</span>
                <strong>{professor.teacher_invoice_counter}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">TVA applicable</span>
                <strong>{professor.teacher_is_vat_applicable ? "Oui" : "Non"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Taux TVA prof</span>
                <strong>{professor.teacher_vat_rate ?? "-"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">SIRET facturation prof</span>
                <strong>{professor.teacher_siret ?? "Non renseigne"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">IBAN facturation prof</span>
                <strong>{professor.teacher_iban ?? "Non renseigne"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Societe prof</span>
                <strong>{professor.teacher_company_name ?? "Non renseignee"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Adresse societe prof</span>
                <strong>{professor.teacher_company_address ?? "Non renseignee"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Lien Zoom</span>
                <strong>{professor.zoom_link ?? "Non renseigne"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Langues</span>
                <strong>{professor.spoken_languages.length > 0 ? professor.spoken_languages.join(", ") : "Non renseigne"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Email quotidien planning</span>
                <strong>{professor.daily_schedule_email_enabled ? "Actif" : "Inactif"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Heure d envoi (UTC)</span>
                <strong>{professor.daily_schedule_email_time}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Ignorer jours sans cours</span>
                <strong>{professor.daily_schedule_skip_if_no_course ? "Oui" : "Non"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Derniere activation</span>
                <strong>{professor.last_activation_email_sent_at ? formatDate(professor.last_activation_email_sent_at) : "Jamais"}</strong>
              </article>
            </div>
            <div className="row top-gap-sm">
              <Link className="mode-link" href={`/admin/professors/${professor.id}?tab=profil&edit_profile=1`}>
                Modifier la fiche
              </Link>
              <form action={sendAdminCollaboratorPasswordLinkAction}>
                <input type="hidden" name="professor_id" value={professor.id} />
                <input type="hidden" name="return_tab" value="profil" />
                <button type="submit">Generer acces et envoyer email</button>
              </form>
            </div>
          </article>

          {isEditProfileOpen ? (
            <section className="modal-overlay" role="dialog" aria-modal="true" aria-label="Modifier collaborateur">
              <section className="modal-card">
                <div className="row spread">
                  <h3>Modifier la fiche</h3>
                  <Link className="close-link" href={`/admin/professors/${professor.id}?tab=profil`}>
                    ×
                  </Link>
                </div>
                <form action={updateAdminCollaboratorProfileAction} className="grid cols-2">
              <input type="hidden" name="professor_id" value={professor.id} />
              <input type="hidden" name="return_tab" value="profil" />

              <label>
                Email
                <input type="email" name="email" defaultValue={professor.email} required />
              </label>

              <label>
                Statut
                <select name="active" defaultValue={professor.active ? "true" : "false"}>
                  <option value="true">Actif</option>
                  <option value="false">Inactif</option>
                </select>
              </label>

              <label>
                Prenom
                <input type="text" name="first_name" defaultValue={professor.first_name} required maxLength={100} />
              </label>

              <label>
                Nom
                <input type="text" name="last_name" defaultValue={professor.last_name} required maxLength={100} />
              </label>

              <label>
                Telephone
                <input type="text" name="phone" defaultValue={professor.phone ?? ""} maxLength={30} />
              </label>

              <label>
                SIRET
                <input type="text" name="siret" defaultValue={professor.siret ?? ""} maxLength={30} />
              </label>

              <label>
                IBAN
                <input type="text" name="iban" defaultValue={professor.iban ?? ""} maxLength={34} />
              </label>

              <label>
                Devise de paiement
                <select name="payout_currency" defaultValue={defaultRateCurrency}>
                  {availableCurrencies.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </select>
              </label>

              <label className="span-2">
                Lien Zoom
                <input type="url" name="zoom_link" defaultValue={professor.zoom_link ?? ""} />
              </label>

              <label className="span-2">
                Adresse
                <input type="text" name="address_line" defaultValue={professor.address_line ?? ""} maxLength={255} />
              </label>

              <label>
                Compteur facture prof
                <input type="number" name="teacher_invoice_counter" min={1} step={1} defaultValue={professor.teacher_invoice_counter} required />
              </label>

              <label className="checkline">
                <input type="checkbox" name="teacher_is_vat_applicable" defaultChecked={professor.teacher_is_vat_applicable} />
                TVA applicable
              </label>

              <label>
                Taux TVA (%)
                <input type="number" name="teacher_vat_rate" min="0" max="99.99" step="0.01" defaultValue={professor.teacher_vat_rate ?? ""} />
              </label>

              <label>
                SIRET facturation prof
                <input type="text" name="teacher_siret" defaultValue={professor.teacher_siret ?? ""} maxLength={64} />
              </label>

              <label>
                IBAN facturation prof
                <input type="text" name="teacher_iban" defaultValue={professor.teacher_iban ?? ""} maxLength={64} />
              </label>

              <label className="span-2">
                Societe prof
                <input type="text" name="teacher_company_name" defaultValue={professor.teacher_company_name ?? ""} maxLength={255} />
              </label>

              <label className="span-2">
                Adresse societe prof
                <textarea name="teacher_company_address" rows={3} defaultValue={professor.teacher_company_address ?? ""} maxLength={2000} />
              </label>

              <label className="span-2">
                Langues (selection multiple)
                <select name="spoken_languages" multiple size={6} defaultValue={professor.spoken_languages}>
                  {COLLABORATOR_LANGUAGE_OPTIONS.map((language) => (
                    <option key={language} value={language}>
                      {language}
                    </option>
                  ))}
                </select>
              </label>

              <label className="checkline">
                <input type="checkbox" name="is_coach" defaultChecked={professor.is_coach} />
                Mode coach
              </label>

              <label className="checkline">
                <input type="checkbox" name="is_admin" defaultChecked={professor.role === "admin"} />
                Droit administrateur
              </label>

              <label className="checkline">
                <input type="checkbox" name="daily_schedule_email_enabled" defaultChecked={professor.daily_schedule_email_enabled} />
                Activer email quotidien planning
              </label>

              <label>
                Heure email quotidien (UTC)
                <input type="time" name="daily_schedule_email_time" defaultValue={professor.daily_schedule_email_time || "07:00"} />
              </label>

              <label className="checkline">
                <input type="checkbox" name="daily_schedule_skip_if_no_course" defaultChecked={professor.daily_schedule_skip_if_no_course} />
                Ne pas envoyer si aucun cours
              </label>

              <div className="row span-2">
                <button type="submit">Enregistrer</button>
                <Link className="reset-link" href={`/admin/professors/${professor.id}?tab=profil`}>
                  Annuler
                </Link>
              </div>
                </form>
              </section>
            </section>
          ) : null}

          <article className="card span-2">
            <div className="row spread">
              <h3>Contrat de collaboration (PDF)</h3>
              <span className="badge">{professor.contract ? "Contrat charge" : "Aucun contrat"}</span>
            </div>

            {professor.contract ? (
              <div className="list">
                <article className="item row spread">
                  <span className="muted">Nom du fichier</span>
                  <strong>{professor.contract.file_name}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">Taille</span>
                  <strong>{Math.max(1, Math.round(professor.contract.size_bytes / 1024))} KB</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">Importe le</span>
                  <strong>{formatDate(professor.contract.uploaded_at)}</strong>
                </article>
              </div>
            ) : (
              <p className="muted">Aucun contrat rattache a ce collaborateur.</p>
            )}

            <div className="row">
              {professor.contract ? (
                <a className="reset-link" href={`/admin/professors/${professor.id}/contract`}>
                  Telecharger le contrat
                </a>
              ) : null}
            </div>

            <form action={uploadAdminCollaboratorContractAction} className="grid cols-3" encType="multipart/form-data">
              <input type="hidden" name="professor_id" value={professor.id} />
              <input type="hidden" name="return_tab" value="profil" />
              <label className="span-2">
                Fichier PDF
                <input type="file" name="contract_file" accept="application/pdf" required />
              </label>
              <div className="row">
                <button type="submit">Importer / remplacer le contrat</button>
              </div>
            </form>

            {professor.contract ? (
              <form action={deleteAdminCollaboratorContractAction} className="row">
                <input type="hidden" name="professor_id" value={professor.id} />
                <input type="hidden" name="return_tab" value="profil" />
                <button type="submit" className="danger">
                  Supprimer le contrat
                </button>
              </form>
            ) : null}
          </article>
        </section>
      ) : null}

      {currentTab === "droits" ? (
        <section className="card">
          <h3>Privileges utilisateur</h3>
          <p className="muted">Configuration des droits du professeur depuis le BackOffice administrateur.</p>
          <form action={updateAdminCollaboratorPermissionsAction} className="grid cols-2">
            <input type="hidden" name="professor_id" value={professor.id} />
            <article className="item span-2">
              <label className="checkline">
                <input type="checkbox" name="is_admin" defaultChecked={professor.role === "admin"} />
                Administrateur (tous privileges)
              </label>
              <p className="muted">Les administrateurs peuvent acceder a toutes les parties du BackOffice.</p>
            </article>

            {PERMISSION_SECTIONS.map((section) => (
              <article key={section.title} className="item">
                <strong>{section.title}</strong>
                <div className="grid">
                  {section.keys.map(({ key, label }) => (
                    <label key={key} className="checkline">
                      <input type="checkbox" name={key} defaultChecked={Boolean((professor.permissions as Record<string, boolean>)[key])} />
                      {label}
                    </label>
                  ))}
                </div>
              </article>
            ))}

            <div className="row span-2">
              <button type="submit">Valider les droits</button>
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
                professorHasOverride={professorHasHeadcountOverride}
                professorGrid={
                  activeBaseRate
                    ? {
                        default_hourly_rate: activeBaseRate.hourly_rate,
                        rules: activeBaseRate.rules.map((rule) => ({
                          min_students: rule.min_students,
                          max_students: rule.max_students,
                          hourly_rate: rule.hourly_rate,
                        })),
                      }
                    : null
                }
                professorReferenceGrid={professorReferenceGrid}
                activities={payrollActivities}
              />
            </form>
          </article>

          {showLegacyContractGrid ? (
            <>
              <article className="card">
                <div className="row spread">
                  <h3>Grilles contractuelles (legacy)</h3>
                  <Link className="mode-link" href={tabHref(professor.id, "tarifs")}>
                    Nouvelle grille
                  </Link>
                </div>
                {contractGrids.length === 0 ? (
                  <p className="muted">Aucune grille contractuelle definie.</p>
                ) : (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Lieu</th>
                          <th>Debut</th>
                          <th>Fin</th>
                          <th>Lignes</th>
                          <th>Statut</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {contractGrids.map((row) => (
                          <tr key={row.id}>
                            <td>{row.location_label}</td>
                            <td>{row.valid_from}</td>
                            <td>{row.valid_to ?? "-"}</td>
                            <td>{row.lines.length}</td>
                            <td>{row.is_active_today ? "Active" : "Historique/Future"}</td>
                            <td>
                              <Link className="mode-link" href={`/admin/professors/${professor.id}?tab=tarifs&legacy_contract=1&edit_grid_id=${row.id}`}>
                                Modifier
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <article className="item top-gap-sm">
                  <strong>Fallback legacy</strong>
                  <p className="muted">
                    Utilise uniquement en secours si aucune surcharge professeur et aucune grille generale ne matchent l activite.
                  </p>
                  <p className="muted">Taux legacy en base: {rates.length}</p>
                </article>
              </article>

              <article className="card">
                <h3>{selectedContractGrid ? "Modifier une grille existante" : "Creer une grille contractuelle"}</h3>
                <form action={upsertAdminCollaboratorContractGridAction} className="grid">
                  <input type="hidden" name="professor_id" value={professor.id} />
                  {selectedContractGrid ? <input type="hidden" name="grid_id" value={selectedContractGrid.id} /> : null}

                  <label>
                    Date de prise d effet
                    <input type="date" name="valid_from" defaultValue={selectedContractGrid?.valid_from ?? effectiveDateDefault} required />
                  </label>

                  <label>
                    Date de fin (optionnel)
                    <input type="date" name="valid_to" defaultValue={selectedContractGrid?.valid_to ?? ""} />
                  </label>

                  <label>
                    Lieu
                    <select name="location_code" defaultValue={selectedContractGrid?.location_code ?? "NONE"}>
                      <option value="NONE">Tous lieux / non specifie</option>
                      {contractLocationOptions.map((option) => (
                        <option key={option.code} value={option.code}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Dupliquer depuis (optionnel)
                    <select name="clone_from_grid_id" defaultValue="">
                      <option value="">Ne pas dupliquer</option>
                      {contractGrids.map((row) => (
                        <option key={`clone-${row.id}`} value={row.id}>
                          {row.location_label} | {row.valid_from}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="span-2">
                    Notes
                    <textarea name="notes" rows={2} defaultValue={selectedContractGrid?.notes ?? ""} />
                  </label>

                  <article className="item span-2">
                    <strong>Lignes de grille</strong>
                    <p className="muted">Regles effectif: format `0-3:35; 4-8:42; 9+:50`.</p>
                    <div className="table-wrap top-gap-sm">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Activite (BackOffice)</th>
                            <th>Mode (derive)</th>
                            <th>Duree ref (min, derive)</th>
                            <th>Taux default</th>
                            <th>Regles effectif</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Array.from({ length: contractLineSlots }).map((_, index) => {
                            const line = selectedGridLines[index];
                            const defaultCourseTypeId =
                              line?.course_type_id ?? (line ? (courseTypeIdByNormalizedName.get(normalizeLookupKey(line.service_type)) ?? "") : "");
                            const derivedCourseType = defaultCourseTypeId ? courseTypeById.get(defaultCourseTypeId) : undefined;
                            const derivedMode = derivedCourseType
                              ? contractModeLabel(derivedCourseType.mode === "ONLINE" ? "EN_LIGNE" : derivedCourseType.mode === "ONSITE" ? "PRESENTIEL" : "AUTRE")
                              : (line ? contractModeLabel(line.mode) : "-");
                            const derivedDuration = derivedCourseType?.duration_minutes ?? line?.reference_duration_minutes ?? null;
                            return (
                              <tr key={`grid-line-${index}`}>
                                <td>
                                  <select name={`line_course_type_id_${index}`} defaultValue={defaultCourseTypeId}>
                                    <option value="">Selectionner une activite</option>
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
                                    placeholder="0-3:35; 4-8:42; 9+:50"
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
                    <button type="submit">{selectedContractGrid ? "Mettre a jour la grille" : "Creer la grille"}</button>
                    {selectedContractGrid ? (
                      <Link className="reset-link" href={`${tabHref(professor.id, "tarifs")}&legacy_contract=1`}>
                        Annuler edition
                      </Link>
                    ) : null}
                  </div>
                </form>
              </article>

              <article className="card span-2">
                <h3>Apercu coach/professeur (lecture seule)</h3>
                {contractGrids.filter((row) => row.is_active_today).length === 0 ? (
                  <p className="muted">Aucune grille active aujourd hui.</p>
                ) : (
                  <div className="list">
                    {contractGrids
                      .filter((row) => row.is_active_today)
                      .map((grid) => (
                        <article key={`active-grid-${grid.id}`} className="item">
                          <div className="row spread">
                            <strong>{grid.location_label}</strong>
                            <span className="badge">
                              {grid.valid_from} - {grid.valid_to ?? "non definie"}
                            </span>
                          </div>
                          <div className="table-wrap top-gap-sm">
                            <table className="data-table">
                              <thead>
                                <tr>
                                  <th>Activite</th>
                                  <th>Mode</th>
                                  <th>Duree ref</th>
                                  <th>Taux default</th>
                                  <th>Regles effectif</th>
                                </tr>
                              </thead>
                              <tbody>
                                {grid.lines.map((line) => (
                                  <tr key={`preview-line-${line.id}`}>
                                    <td>{line.course_type_name || line.service_type}</td>
                                    <td>{contractModeLabel(line.mode)}</td>
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
              <h3>Grilles contractuelles</h3>
              <p className="muted">
                Masquees par defaut pour eviter le double emploi avec la grille generale + surcharges professeur.
              </p>
              <Link className="mode-link" href={`${tabHref(professor.id, "tarifs")}&legacy_contract=1`}>
                Afficher les grilles contractuelles (mode legacy)
              </Link>
            </article>
          )}
        </section>
      ) : null}

      {currentTab === "solde" ? (
        <section className="card">
          <div className="row spread">
            <h3>Solde du professeur</h3>
            <span className="badge">
              {payoutLedger?.total_due ?? "0.00"} {payoutLedger?.currency ?? professor.payout_currency}
            </span>
          </div>
          <form method="get" className="row top-gap-sm">
            <input type="hidden" name="tab" value="solde" />
            <label style={{ minWidth: "220px" }}>
              Date d arrete
              <input type="date" name="payout_as_of" defaultValue={payoutAsOf} />
            </label>
            <button type="submit">Actualiser</button>
          </form>
          {payoutLedger && payoutLedger.rows.length > 0 ? (
            <div className="table-wrap top-gap-sm">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Date & heure</th>
                    <th>Description</th>
                    <th>Revenu</th>
                    <th>Paiement</th>
                    <th>Solde cumule</th>
                  </tr>
                </thead>
                <tbody>
                  {payoutLedger.rows.map((row) => (
                    <tr key={`payout-ledger-${row.session_id}`}>
                      <td>
                        {formatDate(row.start_at_utc)}
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
                        <small className="muted">{row.hourly_rate !== null ? `${row.hourly_rate} / h` : "taux non defini"}</small>
                      </td>
                      <td>
                        <span className={`status-pill ${payoutStatusToneClass(row.payout_status)}`}>
                          {payoutStatusLabel(row.payout_status)}
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
            <p className="muted top-gap-sm">Aucun cours comptabilise jusqu a cette date.</p>
          )}
        </section>
      ) : null}

      {currentTab === "planning" ? (
        <section className="card">
          <div className="row spread">
            <h3>Planning du professeur</h3>
            <span className="badge">{agendaRange.title}</span>
          </div>

          <form method="get" className="grid cols-4">
            <input type="hidden" name="tab" value="planning" />

            <label>
              Vue
              <select name="agenda_view" defaultValue={agendaView}>
                <option value="month">Mois</option>
                <option value="week">Semaine</option>
                <option value="day">Jour</option>
              </select>
            </label>

            <label>
              Date de reference (UTC)
              <input type="date" name="agenda_date" defaultValue={agendaDate} />
            </label>

            <div className="row">
              <button type="submit">Appliquer</button>
              <a className="reset-link" href={tabHref(professor.id, "planning")}>
                Reinitialiser
              </a>
            </div>
          </form>

          <div className="agenda-columns">
            {agendaDays.map((day) => (
              <article key={day.key} className="agenda-day-card">
                <h4>{day.label}</h4>
                {day.sessions.length === 0 ? (
                  <p className="muted">Aucun cours.</p>
                ) : (
                  <div className="list">
                    {day.sessions.map((session) => (
                      <article key={session.id} className="item">
                        <div className="row spread">
                          <strong>{formatTime(session.start_at_utc)} - {formatTime(session.end_at_utc)}</strong>
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
                        <p className="muted">Statut: {session.status}</p>
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
