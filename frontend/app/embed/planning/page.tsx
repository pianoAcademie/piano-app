import Link from "next/link";

import { reservePublicPlanningSessionAction } from "../../../lib/actions";
import PortalBrandLockup from "../../../components/portal-brand-lockup";
import { getPortalToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import { isChildOnlyBookingSession } from "../../../lib/client-session-selection";
import { localeForUiLanguage, normalizeUiLanguage, resolveAuthErrorMessage, resolveAuthOkMessage, type UiLanguage, uiText } from "../../../lib/ui-i18n";
import type { ClientBookingOut, ClientSessionFormulaOptionOut, CourseTypeOut, LocationOut, SessionOut } from "../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

type EmbedDay = {
  key: string;
  label: string;
  sessions: SessionOut[];
};

const PARIS_LOCATION_GROUP = "paris";
const PARIS_LOCATION_TOKENS = ["dulong", "scheffer", "assas", "richelieu", "pompe"];
const ACTIVE_CLIENT_BOOKING_STATUSES = new Set(["BOOKED", "WAITLISTED", "ATTENDED", "NO_SHOW", "EXCUSED_ABSENCE"]);
const DEFAULT_UPCOMING_SEARCH_DAYS = 400;
type PlanningParticipantKind = "ADULT" | "CHILD";

function readParam(params: SearchParams | undefined, key: string): string {
  const value = params?.[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function readParamValues(params: SearchParams | undefined, key: string): string[] {
  const value = params?.[key];
  if (Array.isArray(value)) {
    return value;
  }
  return value ? [value] : [];
}

function readStringListParam(params: SearchParams | undefined, key: string): string[] {
  return readParamValues(params, key)
    .flatMap((value) => value.split(","))
    .map((value) => value.trim())
    .filter(Boolean);
}

function uniqueValues(values: string[]): string[] {
  return Array.from(new Set(values));
}

function readCourseTypeIds(params: SearchParams | undefined): string[] {
  return uniqueValues([...readStringListParam(params, "course_type_id"), ...readStringListParam(params, "course_type_ids")]);
}

function readParticipantKind(params: SearchParams | undefined): PlanningParticipantKind | null {
  const value = readParam(params, "participant_kind").trim().toUpperCase();
  return value === "ADULT" || value === "CHILD" ? value : null;
}

function appendCourseTypeParams(params: URLSearchParams, courseTypeIds: string[]): void {
  for (const courseTypeId of courseTypeIds) {
    params.append("course_type_id", courseTypeId);
  }
}

function safeDate(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function resolveTimezone(value: string | null | undefined): string {
  const fallback = "Europe/Paris";
  const candidate = (value ?? "").trim();
  if (!candidate) {
    return fallback;
  }
  try {
    new Intl.DateTimeFormat("fr-FR", { timeZone: candidate }).format(new Date());
    return candidate;
  } catch {
    return fallback;
  }
}

function parseDateKey(raw: string, fallbackTimezone: string): string {
  const candidate = raw.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(candidate)) {
    return candidate;
  }
  return todayKeyInTimezone(fallbackTimezone);
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
  const weekday = (date.getUTCDay() + 6) % 7;
  return addUtcDays(date, -weekday);
}

function dateKeyInTimezone(value: string, timezone: string): string {
  const safeTimezone = resolveTimezone(timezone);
  const baseDate = safeDate(value) ?? new Date();
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: safeTimezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(baseDate);
  const year = parts.find((part) => part.type === "year")?.value ?? "";
  const month = parts.find((part) => part.type === "month")?.value ?? "";
  const day = parts.find((part) => part.type === "day")?.value ?? "";
  return `${year}-${month}-${day}`;
}

function todayKeyInTimezone(timezone: string): string {
  return dateKeyInTimezone(new Date().toISOString(), timezone);
}

function formatDayHeader(dayKey: string, timezone: string, language: UiLanguage): string {
  return new Intl.DateTimeFormat(localeForUiLanguage(language), {
    weekday: "short",
    day: "2-digit",
    month: "short",
    timeZone: timezone,
  }).format(keyToUtcDate(dayKey));
}

function formatTime(value: string, timezone: string, language: UiLanguage): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "--:--";
  }
  return new Intl.DateTimeFormat(localeForUiLanguage(language), {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone,
  }).format(parsed);
}

function formatDateTime(value: string, timezone: string, language: UiLanguage): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "-";
  }
  return new Intl.DateTimeFormat(localeForUiLanguage(language), {
    weekday: "long",
    day: "2-digit",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone,
  }).format(parsed);
}

function formatMoney(amountRaw: string | null, currencyRaw: string | null, language: UiLanguage): string {
  if (!amountRaw) {
    return uiText(language, "public_booking.price_to_confirm");
  }
  const amount = Number(amountRaw);
  const currency = (currencyRaw || "EUR").trim().toUpperCase() || "EUR";
  if (!Number.isFinite(amount)) {
    return `${amountRaw} ${currency}`;
  }
  try {
    return new Intl.NumberFormat(localeForUiLanguage(language), {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

function publicPlanningRateLabel(
  session: SessionOut,
  participantKind: PlanningParticipantKind | null,
  language: UiLanguage,
): string {
  if (participantKind && session.external_booking_price_ttc === null) {
    return uiText(language, "embed_planning.formula_access_rate");
  }
  return formatMoney(session.external_booking_price_ttc, session.external_booking_currency, language);
}

function normalizeLocationName(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/[^a-zA-Z0-9]+/g, " ")
    .trim()
    .toLowerCase();
}

function resolveParisLocationIds(locations: LocationOut[]): string[] {
  return locations
    .filter((location) => {
      const normalized = normalizeLocationName(location.name);
      return PARIS_LOCATION_TOKENS.some((token) => normalized.includes(token));
    })
    .map((location) => location.id);
}

function resolveLocationColorClass(locationName: string | null | undefined): string {
  const normalized = normalizeLocationName(locationName ?? "");
  const token = PARIS_LOCATION_TOKENS.find((candidate) => normalized.includes(candidate));
  return token ? `location-color-${token}` : "location-color-default";
}

function buildPlanningHref({
  courseTypeIds,
  participantKind,
  locationId,
  locationGroup,
  date,
  sessionId,
  language,
}: {
  courseTypeIds: string[];
  participantKind?: PlanningParticipantKind | null;
  locationId?: string | null;
  locationGroup?: string | null;
  date: string;
  sessionId?: string | null;
  language: UiLanguage;
}): string {
  const params = new URLSearchParams();
  appendCourseTypeParams(params, courseTypeIds);
  if (participantKind) {
    params.set("participant_kind", participantKind);
  }
  if (locationGroup) {
    params.set("location_group", locationGroup);
    if (locationId) {
      params.set("location_id", locationId);
    }
  } else if (locationId) {
    params.set("location_id", locationId);
  }
  params.set("date", date);
  if (sessionId) {
    params.set("session_id", sessionId);
  }
  if (language === "en") {
    params.set("lang", "en");
  }
  return `/embed/planning?${params.toString()}`;
}

function buildSessionCheckoutHref(sessionId: string, planningReturnTo: string, language: UiLanguage): string {
  const params = new URLSearchParams();
  params.set("session_id", sessionId);
  if (planningReturnTo) {
    params.set("planning_return_to", planningReturnTo);
  }
  if (language === "en") {
    params.set("lang", "en");
  }
  return `/buy/session/checkout?${params.toString()}`;
}

function bookingStatusLabel(status: string, language: UiLanguage): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "BOOKED") return uiText(language, "embed_planning.booking_status_booked");
  if (normalized === "WAITLISTED") return uiText(language, "embed_planning.booking_status_waitlisted");
  if (normalized === "ATTENDED") return uiText(language, "embed_planning.booking_status_completed");
  if (normalized === "EXCUSED_ABSENCE") return uiText(language, "embed_planning.booking_status_excused");
  if (normalized === "NO_SHOW") return uiText(language, "embed_planning.booking_status_absent");
  return normalized || "-";
}

function externalAvailabilityLabel(session: SessionOut, language: UiLanguage): string {
  if (!session.show_external_remaining_seats) {
    return session.seats_remaining > 0 ? uiText(language, "embed_planning.availability_available") : uiText(language, "embed_planning.availability_full");
  }
  return session.seats_remaining > 0
    ? uiText(language, "embed_planning.availability_remaining", { count: session.seats_remaining })
    : uiText(language, "embed_planning.availability_waitlist");
}

function isPublicPlanningSession(session: SessionOut, participantKind: PlanningParticipantKind | null): boolean {
  const participantAllowed = participantKind === "ADULT"
    ? session.adult_bookings_enabled
    : participantKind === "CHILD"
      ? session.child_bookings_enabled
      : true;
  return (
    participantAllowed &&
    session.online_booking_enabled &&
    session.booking_scopes.includes("EXTERNAL") &&
    (participantKind !== null || session.external_booking_price_ttc !== null)
  );
}

function sortPublicPlanningSessions(left: SessionOut, right: SessionOut): number {
  const byStart = left.start_at_utc.localeCompare(right.start_at_utc);
  if (byStart !== 0) {
    return byStart;
  }
  return left.location.name.localeCompare(right.location.name, "fr");
}

export default async function EmbedPlanningPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const language = normalizeUiLanguage(readParam(searchParams, "lang"));
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const courseTypeIds = readCourseTypeIds(searchParams);
  const participantKind = readParticipantKind(searchParams);
  const locationId = readParam(searchParams, "location_id").trim();
  const locationGroup = readParam(searchParams, "location_group").trim().toLowerCase();
  const selectedSessionId = readParam(searchParams, "session_id").trim();
  const okMessage = resolveAuthOkMessage(readParam(searchParams, "ok"), readParam(searchParams, "ok_code"), language);
  const errorMessage = resolveAuthErrorMessage(readParam(searchParams, "error"), readParam(searchParams, "error_code"), language);
  const sessionOkMessage = resolveAuthOkMessage(readParam(searchParams, "session_ok"), readParam(searchParams, "session_ok_code"), language);
  const sessionErrorMessage = resolveAuthErrorMessage(
    readParam(searchParams, "session_error"),
    readParam(searchParams, "session_error_code"),
    language,
  );

  const locationsParams = new URLSearchParams({ active: "true" });
  if (courseTypeIds.length === 1 && participantKind === null) {
    locationsParams.set("course_type_id", courseTypeIds[0]);
  }
  const locationsResult = await backendRequest<LocationOut[]>(`/api/v1/locations?${locationsParams.toString()}`);
  const locations = locationsResult.ok ? locationsResult.data : [];
  const parisLocationIds = resolveParisLocationIds(locations);
  const usesParisLocationGroup = locationGroup === PARIS_LOCATION_GROUP && parisLocationIds.length > 0;
  const selectedParisLocationId = usesParisLocationGroup && parisLocationIds.includes(locationId) ? locationId : "";
  const effectiveLocationIds = usesParisLocationGroup
    ? selectedParisLocationId
      ? [selectedParisLocationId]
      : parisLocationIds
    : locationId
      ? [locationId]
      : [];

  if ((courseTypeIds.length === 0 && participantKind === null) || effectiveLocationIds.length === 0) {
    return (
      <main className="embed-planning-page">
        <section className="embed-planning-shell">
          <article className="card embed-planning-card">
            <h1>{t("embed_planning.invalid_params_title")}</h1>
            <p className="flash-err">{t("embed_planning.invalid_params_body")}</p>
          </article>
        </section>
      </main>
    );
  }

  const courseTypesResults = participantKind
    ? []
    : await Promise.all(
        effectiveLocationIds.map((currentLocationId) =>
          backendRequest<CourseTypeOut[]>(`/api/v1/course-types?active=true&location_id=${encodeURIComponent(currentLocationId)}`),
        ),
      );
  const courseTypeById = new Map<string, CourseTypeOut>();
  for (const result of courseTypesResults) {
    if (!result.ok) {
      continue;
    }
    for (const row of result.data) {
      courseTypeById.set(row.id, row);
    }
  }
  const selectedCourseTypes = courseTypeIds.map((courseTypeId) => courseTypeById.get(courseTypeId)).filter((courseType): courseType is CourseTypeOut => Boolean(courseType));
  const selectedCourseTypeIds = selectedCourseTypes.map((courseType) => courseType.id);
  const selectedCourseTypeLabel = participantKind === "ADULT"
    ? t("embed_planning.all_adult_booking_slots")
    : participantKind === "CHILD"
      ? t("embed_planning.all_child_booking_slots")
      : selectedCourseTypes.map((courseType) => courseType.name).join(" + ");
  const selectedLocation = locations.find((row) => row.id === (usesParisLocationGroup ? selectedParisLocationId : locationId)) ?? null;
  const selectedLocationName = usesParisLocationGroup
    ? selectedLocation?.name ?? (language === "en" ? "Paris - all locations" : "Paris - tous les lieux")
    : (selectedLocation?.name ?? "");
  const timezone = resolveTimezone(selectedLocation?.timezone || "Europe/Paris");

  if ((selectedCourseTypes.length === 0 && participantKind === null) || (!usesParisLocationGroup && !selectedLocation)) {
    return (
      <main className="embed-planning-page">
        <section className="embed-planning-shell">
          <article className="card embed-planning-card">
            <h1>{t("embed_planning.unavailable_title")}</h1>
            <p className="flash-err">{t("embed_planning.unavailable_body")}</p>
          </article>
        </section>
      </main>
    );
  }

  const loadPublicPlanningSessions = async (from: string, to: string): Promise<SessionOut[]> => {
    const loadSessions = (currentLocationId: string, courseTypeId?: string) => {
      const params = new URLSearchParams();
      if (courseTypeId) {
        params.set("course_type_id", courseTypeId);
      }
      params.set("location_id", currentLocationId);
      params.set("timezone", timezone);
      params.set("from", from);
      params.set("to", to);
      if (participantKind) {
        params.set("participant_kind", participantKind);
      }
      return backendRequest<SessionOut[]>(`/api/v1/sessions?${params.toString()}`);
    };
    const results = await Promise.all(
      participantKind
        ? effectiveLocationIds.map((currentLocationId) => loadSessions(currentLocationId))
        : effectiveLocationIds.flatMap((currentLocationId) =>
            selectedCourseTypeIds.map((courseTypeId) => loadSessions(currentLocationId, courseTypeId)),
          ),
    );
    const sessionById = new Map<string, SessionOut>();
    for (const result of results) {
      if (!result.ok) {
        continue;
      }
      for (const session of result.data) {
        sessionById.set(session.id, session);
      }
    }
    return [...sessionById.values()]
      .filter((session) => isPublicPlanningSession(session, participantKind))
      .sort(sortPublicPlanningSessions);
  };

  const requestedDate = readParam(searchParams, "date").trim();
  let anchorDateKey = parseDateKey(requestedDate, timezone);
  if (!requestedDate) {
    const now = new Date();
    const upcomingSearchEnd = addUtcDays(now, DEFAULT_UPCOMING_SEARCH_DAYS);
    const upcomingSessions = await loadPublicPlanningSessions(now.toISOString(), upcomingSearchEnd.toISOString());
    const firstAvailableSession = upcomingSessions.find((session) => session.seats_remaining > 0);
    if (firstAvailableSession) {
      anchorDateKey = dateKeyInTimezone(firstAvailableSession.start_at_utc, timezone);
    }
  }

  const weekStart = startOfWeekUtc(keyToUtcDate(anchorDateKey));
  const weekStartKey = utcDateToKey(weekStart);
  const weekDays = Array.from({ length: 7 }, (_, index) => {
    const dayValue = addUtcDays(weekStart, index);
    const key = utcDateToKey(dayValue);
    return {
      key,
      label: formatDayHeader(key, timezone, language),
    };
  });
  const queryFrom = addUtcDays(weekStart, -1).toISOString();
  const queryTo = addUtcDays(weekStart, 8).toISOString();

  const portalToken = getPortalToken();
  const [sessions, bookingsResult] = await Promise.all([
    loadPublicPlanningSessions(queryFrom, queryTo),
    portalToken ? backendRequest<ClientBookingOut[]>("/api/v1/clients/me/bookings", {}, portalToken) : Promise.resolve(null),
  ]);

  const sessionIds = new Set(sessions.map((session) => session.id));
  const ownBookings = bookingsResult && bookingsResult.ok ? bookingsResult.data : [];
  const bookingsBySessionId = new Map(
    ownBookings
      .filter((booking) => sessionIds.has(booking.session.id))
      .filter((booking) => ACTIVE_CLIENT_BOOKING_STATUSES.has(booking.status))
      .map((booking) => [booking.session.id, booking]),
  );
  const locationOptions = locations
    .filter((location) => location.active)
    .sort((left, right) => left.name.localeCompare(right.name, localeForUiLanguage(language)));
  const parisLocationOptions = locationOptions.filter((location) => parisLocationIds.includes(location.id));
  const showParisLocationLegend = usesParisLocationGroup && !selectedParisLocationId && parisLocationOptions.length > 1;

  const sessionsByDay = new Map<string, SessionOut[]>();
  for (const session of sessions) {
    const dayKey = dateKeyInTimezone(session.start_at_utc, timezone);
    if (!sessionsByDay.has(dayKey)) {
      sessionsByDay.set(dayKey, []);
    }
    sessionsByDay.get(dayKey)?.push(session);
  }

  const embedDays: EmbedDay[] = weekDays.map((dayValue) => ({
    key: dayValue.key,
    label: dayValue.label,
    sessions: sessionsByDay.get(dayValue.key) ?? [],
  }));

  const selectedSession = sessions.find((session) => session.id === selectedSessionId) ?? null;
  const selectedSessionTrialOffersResult = selectedSession
    ? await backendRequest<ClientSessionFormulaOptionOut[]>(
        `/api/v1/public/sessions/${encodeURIComponent(selectedSession.id)}/trial-offers${participantKind ? `?participant_kind=${encodeURIComponent(participantKind)}` : ""}`,
      )
    : null;
  const selectedSessionTrialOffers =
    selectedSessionTrialOffersResult?.ok ? selectedSessionTrialOffersResult.data : [];
  const featuredTrialOffer = selectedSessionTrialOffers[0] ?? null;
  const selectedBooking = selectedSession ? bookingsBySessionId.get(selectedSession.id) ?? null : null;
  const selectedSessionStart = selectedSession ? safeDate(selectedSession.start_at_utc) : null;
  const selectedSessionStarted = selectedSessionStart ? selectedSessionStart.getTime() <= Date.now() : false;
  const selectedSessionIsFull = selectedSession ? selectedSession.seats_remaining <= 0 : false;
  const selectedSessionReturnTo = buildPlanningHref({
    courseTypeIds,
    participantKind,
    locationId: usesParisLocationGroup ? selectedParisLocationId : locationId,
    locationGroup: usesParisLocationGroup ? PARIS_LOCATION_GROUP : null,
    date: weekStartKey,
    sessionId: selectedSession?.id ?? null,
    language,
  });
  const previousHref = buildPlanningHref({
    courseTypeIds,
    participantKind,
    locationId: usesParisLocationGroup ? selectedParisLocationId : locationId,
    locationGroup: usesParisLocationGroup ? PARIS_LOCATION_GROUP : null,
    date: utcDateToKey(addUtcDays(weekStart, -7)),
    language,
  });
  const nextHref = buildPlanningHref({
    courseTypeIds,
    participantKind,
    locationId: usesParisLocationGroup ? selectedParisLocationId : locationId,
    locationGroup: usesParisLocationGroup ? PARIS_LOCATION_GROUP : null,
    date: utcDateToKey(addUtcDays(weekStart, 7)),
    language,
  });
  const todayHref = buildPlanningHref({
    courseTypeIds,
    participantKind,
    locationId: usesParisLocationGroup ? selectedParisLocationId : locationId,
    locationGroup: usesParisLocationGroup ? PARIS_LOCATION_GROUP : null,
    date: todayKeyInTimezone(timezone),
    language,
  });
  const closeSessionHref = buildPlanningHref({
    courseTypeIds,
    participantKind,
    locationId: usesParisLocationGroup ? selectedParisLocationId : locationId,
    locationGroup: usesParisLocationGroup ? PARIS_LOCATION_GROUP : null,
    date: weekStartKey,
    language,
  });
  const childRegistrationQuery = isChildOnlyBookingSession(selectedSession) ? "&registration_subject_type=child" : "";
  const loginHref = `/login?mode=login&return_to=${encodeURIComponent(selectedSessionReturnTo)}${childRegistrationQuery}${language === "en" ? "&lang=en" : ""}`;
  const sessionCheckoutHref = selectedSession ? buildSessionCheckoutHref(selectedSession.id, selectedSessionReturnTo, language) : `/buy/session/checkout${language === "en" ? "?lang=en" : ""}`;
  const sessionCheckoutLoginHref = `/login?mode=login&return_to=${encodeURIComponent(sessionCheckoutHref)}${childRegistrationQuery}${language === "en" ? "&lang=en" : ""}`;
  const selectedSessionRequiresCheckout =
    selectedSession !== null
    && !selectedSessionIsFull
    && (
      participantKind !== null
      || Number(selectedSession.external_booking_price_ttc ?? "0") > 0
      || featuredTrialOffer !== null
    );
  const selectedSessionDetail = selectedSession ? (
    <section className="embed-planning-detail embed-planning-detail-priority">
      <div className="row spread">
        <div>
          <small className="embed-planning-step-label">{t("embed_planning.selected_slot_label")}</small>
          <h2>{selectedSession.title}</h2>
        </div>
        <Link className="reset-link" href={closeSessionHref}>{uiText(language, "common.close")}</Link>
      </div>

      <p className="muted">
        {formatDateTime(selectedSession.start_at_utc, timezone, language)} · {usesParisLocationGroup ? selectedSession.location.name : selectedLocationName || t("embed_planning.location_to_confirm")}
      </p>

      <div className="embed-planning-detail-grid">
        <article className="item">
          <small className="muted">
            {t(selectedSession.external_booking_price_ttc === null ? "embed_planning.formula_access_label" : "embed_planning.external_rate")}
          </small>
          <p>{publicPlanningRateLabel(selectedSession, participantKind, language)}</p>
        </article>
        {selectedSessionTrialOffers.map((trialOffer) => (
          <article className="item embed-planning-trial-offer" key={trialOffer.formula_id}>
            <small className="muted">{t("embed_planning.trial_rate")}</small>
            <p>{formatMoney(trialOffer.price_ttc, trialOffer.currency, language)}</p>
            <small className="muted">{t("embed_planning.trial_eligibility_notice")}</small>
          </article>
        ))}
        <article className="item">
          <small className="muted">{t("embed_planning.availability_label")}</small>
          <p>{externalAvailabilityLabel(selectedSession, language)}</p>
        </article>
        <article className="item">
          <small className="muted">{t("embed_planning.coach_label")}</small>
          <p>{selectedSession.effective_teacher_display_name || t("embed_planning.to_confirm")}</p>
        </article>
      </div>

      {selectedSession.description ? <p>{selectedSession.description}</p> : null}

      {!portalToken ? (
        <div className="embed-planning-cta-stack">
          {featuredTrialOffer ? (
            <div className="embed-planning-rate-choice-callout">
              <span className="embed-planning-rate-choice-icon" aria-hidden="true">€</span>
              <div>
                <strong>{t("embed_planning.rate_choice_title")}</strong>
                <p>
                  {selectedSession.external_booking_price_ttc === null
                    ? t("embed_planning.rate_choice_body_formula_only", {
                        trialPrice: formatMoney(featuredTrialOffer.price_ttc, featuredTrialOffer.currency, language),
                      })
                    : t("embed_planning.rate_choice_body", {
                        unitPrice: formatMoney(
                          selectedSession.external_booking_price_ttc,
                          selectedSession.external_booking_currency,
                          language,
                        ),
                        trialPrice: formatMoney(featuredTrialOffer.price_ttc, featuredTrialOffer.currency, language),
                      })}
                </p>
                <small>{t("embed_planning.rate_choice_login_note")}</small>
              </div>
            </div>
          ) : (
            <p className="muted">{t("embed_planning.unauthenticated_help")}</p>
          )}
          <Link className="mode-link embed-planning-primary-link" href={selectedSessionRequiresCheckout ? sessionCheckoutLoginHref : loginHref}>
            {t(featuredTrialOffer ? "embed_planning.choose_rate_cta" : "embed_planning.reserve_cta")}
          </Link>
        </div>
      ) : selectedBooking ? (
        <div className="embed-planning-cta-stack">
          <p className="flash-ok">{t("embed_planning.current_status", { status: bookingStatusLabel(selectedBooking.status, language) })}</p>
        </div>
      ) : selectedSessionStarted ? (
        <p className="flash-err">{t("embed_planning.already_started")}</p>
      ) : selectedSessionRequiresCheckout ? (
        <div className="embed-planning-cta-stack">
          <p className="muted">{t("embed_planning.secure_payment_help")}</p>
          <Link className="mode-link embed-planning-primary-link" href={sessionCheckoutHref}>{t("embed_planning.continue_to_payment")}</Link>
        </div>
      ) : (
        <form action={reservePublicPlanningSessionAction} className="embed-planning-book-form">
          <input type="hidden" name="session_id" value={selectedSession.id} />
          <input type="hidden" name="return_to" value={selectedSessionReturnTo} />
          <button type="submit">{selectedSessionIsFull ? t("embed_planning.join_waitlist") : t("embed_planning.reserve_slot")}</button>
        </form>
      )}
    </section>
  ) : null;

  return (
    <main className="embed-planning-page">
      <section className="embed-planning-shell">
        <article className="card embed-planning-card">
          <header className="embed-planning-header">
            <div>
              <PortalBrandLockup
                title="Piano Academie"
                subtitle={t("embed_planning.brand_subtitle")}
                eyebrow="Mi-Young Lee"
                className="embed-brand-lockup"
              />
              <h1>{selectedCourseTypeLabel}</h1>
              <p className="muted">
                {selectedLocationName
                  ? t("embed_planning.week_view_location", { location: selectedLocationName })
                  : t("embed_planning.week_view_all_locations")}
              </p>
            </div>
            <div className="embed-planning-nav">
              <Link className="mode-link" href={previousHref}>←</Link>
              <Link className="mode-link" href={todayHref}>{uiText(language, "client.today")}</Link>
              <Link className="mode-link" href={nextHref}>→</Link>
            </div>
          </header>

          <form method="get" className="grid cols-2 top-gap-sm">
            {courseTypeIds.map((courseTypeId) => (
              <input key={courseTypeId} type="hidden" name="course_type_id" value={courseTypeId} />
            ))}
            {language === "en" ? <input type="hidden" name="lang" value="en" /> : null}
            {participantKind ? <input type="hidden" name="participant_kind" value={participantKind} /> : null}

            {usesParisLocationGroup ? (
              <>
                <input type="hidden" name="location_group" value={PARIS_LOCATION_GROUP} />
                <label>
                  {uiText(language, "common.location")}
                  <select name="location_id" defaultValue={selectedParisLocationId}>
                    <option value="">{language === "en" ? "All Paris locations" : "Tous les lieux parisiens"}</option>
                    {parisLocationOptions.map((location) => (
                      <option key={location.id} value={location.id}>
                        {location.name}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            ) : (
              <label>
                {uiText(language, "common.location")}
                <select name="location_id" defaultValue={locationId}>
                  <option value="">{t("embed_planning.all_locations_option")}</option>
                  {locationOptions.map((location) => (
                    <option key={location.id} value={location.id}>
                      {location.name}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <label>
              {uiText(language, "common.date")}
              <input type="date" name="date" defaultValue={anchorDateKey} />
            </label>

            <div className="row">
              <button type="submit">{uiText(language, "common.apply")}</button>
              {(selectedParisLocationId || (!usesParisLocationGroup && locationId) || readParam(searchParams, "date").trim()) ? (
                <Link
                  className="ghost small-btn"
                  href={buildPlanningHref({
                    courseTypeIds,
                    participantKind,
                    locationId: usesParisLocationGroup ? null : locationId,
                    locationGroup: usesParisLocationGroup ? PARIS_LOCATION_GROUP : null,
                    date: todayKeyInTimezone(timezone),
                    language,
                  })}
                >
                  {uiText(language, "common.reset")}
                </Link>
              ) : null}
            </div>
          </form>

          {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
          {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
          {sessionOkMessage ? <section className="flash-ok">{sessionOkMessage}</section> : null}
          {sessionErrorMessage ? <section className="flash-err">{sessionErrorMessage}</section> : null}

          {selectedSessionDetail ?? (
            <section className="embed-planning-guide" aria-label={t("embed_planning.booking_steps_title")}>
              <strong>{t("embed_planning.booking_steps_title")}</strong>
              <span>{t("embed_planning.booking_steps_body")}</span>
            </section>
          )}

          {showParisLocationLegend ? (
            <section className="embed-location-legend" aria-label={language === "en" ? "Paris location colours" : "Couleurs des lieux parisiens"}>
              {parisLocationOptions.map((location) => (
                <span key={location.id} className={`embed-location-legend-chip ${resolveLocationColorClass(location.name)}`}>
                  <span aria-hidden="true" />
                  {location.name}
                </span>
              ))}
            </section>
          ) : null}

          <div className="embed-planning-week-grid">
            {embedDays.map((dayValue) => (
              <section key={dayValue.key} className="embed-planning-day">
                <header className="embed-planning-day-head">
                  <strong>{dayValue.label}</strong>
                </header>
                <div className="embed-planning-day-body">
                  {dayValue.sessions.length === 0 ? (
                    <p className="muted">{t("embed_planning.no_slots")}</p>
                  ) : (
                    dayValue.sessions.map((session) => {
                      const booking = bookingsBySessionId.get(session.id) ?? null;
                      const isReserved = booking !== null && ACTIVE_CLIENT_BOOKING_STATUSES.has(booking.status);
                      const detailHref = buildPlanningHref({
                        courseTypeIds,
                        participantKind,
                        locationId: usesParisLocationGroup ? selectedParisLocationId : locationId,
                        locationGroup: usesParisLocationGroup ? PARIS_LOCATION_GROUP : null,
                        date: weekStartKey,
                        sessionId: session.id,
                        language,
                      });
                      return (
                        <Link
                          key={session.id}
                          className={`embed-slot-card ${resolveLocationColorClass(session.location?.name)}${selectedSession?.id === session.id ? " is-selected" : ""}`}
                          href={detailHref}
                          scroll
                        >
                          <div className="embed-slot-card-top">
                            <strong>{formatTime(session.start_at_utc, timezone, language)} - {formatTime(session.end_at_utc, timezone, language)}</strong>
                            {isReserved ? <span className="badge">{t("embed_planning.reserved_badge")}</span> : null}
                          </div>
                          <p>{session.title}</p>
                          {usesParisLocationGroup ? <small className="embed-slot-location">{session.location.name}</small> : null}
                          {!usesParisLocationGroup && !selectedLocation ? (
                            <small className="embed-slot-location">{session.location?.name || t("embed_planning.location_to_confirm")}</small>
                          ) : null}
                          <small>{publicPlanningRateLabel(session, participantKind, language)}</small>
                          <small>{externalAvailabilityLabel(session, language)}</small>
                          <span className="embed-slot-card-action">{isReserved ? t("embed_planning.reserved_badge") : t("embed_planning.select_slot_cta")}</span>
                        </Link>
                      );
                    })
                  )}
                </div>
              </section>
            ))}
          </div>
        </article>
      </section>
    </main>
  );
}
