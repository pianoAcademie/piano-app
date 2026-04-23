import Link from "next/link";

import { reservePublicPlanningSessionAction } from "../../../lib/actions";
import PortalBrandLockup from "../../../components/portal-brand-lockup";
import { getPortalToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../lib/ui-i18n";
import type { ClientBookingOut, CourseTypeOut, LocationOut, SessionOut } from "../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

type EmbedDay = {
  key: string;
  label: string;
  sessions: SessionOut[];
};

function readParam(params: SearchParams | undefined, key: string): string {
  const value = params?.[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
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

function buildPlanningHref({
  courseTypeId,
  locationId,
  date,
  sessionId,
  language,
}: {
  courseTypeId: string;
  locationId?: string | null;
  date: string;
  sessionId?: string | null;
  language: UiLanguage;
}): string {
  const params = new URLSearchParams();
  params.set("course_type_id", courseTypeId);
  if (locationId) {
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

export default async function EmbedPlanningPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const language = normalizeUiLanguage(readParam(searchParams, "lang"));
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const courseTypeId = readParam(searchParams, "course_type_id").trim();
  const locationId = readParam(searchParams, "location_id").trim();
  const selectedSessionId = readParam(searchParams, "session_id").trim();
  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error");
  const sessionOkMessage = readParam(searchParams, "session_ok");
  const sessionErrorMessage = readParam(searchParams, "session_error");

  if (!courseTypeId) {
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

  const [courseTypesResult, locationsResult] = await Promise.all([
    backendRequest<CourseTypeOut[]>(
      `/api/v1/course-types?active=true${locationId ? `&location_id=${encodeURIComponent(locationId)}` : ""}`,
    ),
    backendRequest<LocationOut[]>("/api/v1/locations?active=true"),
  ]);

  const courseTypes = courseTypesResult.ok ? courseTypesResult.data : [];
  const locations = locationsResult.ok ? locationsResult.data : [];
  const selectedCourseType = courseTypes.find((row) => row.id === courseTypeId) ?? null;
  const selectedLocation = locations.find((row) => row.id === locationId) ?? null;
  const timezone = resolveTimezone(selectedLocation?.timezone || "Europe/Paris");

  if (!selectedCourseType || (locationId && !selectedLocation)) {
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

  const anchorDateKey = parseDateKey(readParam(searchParams, "date"), timezone);
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
  const [sessionsResult, bookingsResult] = await Promise.all([
    backendRequest<SessionOut[]>(
      `/api/v1/sessions?course_type_id=${encodeURIComponent(courseTypeId)}${locationId ? `&location_id=${encodeURIComponent(locationId)}` : ""}&timezone=${encodeURIComponent(timezone)}&from=${encodeURIComponent(queryFrom)}&to=${encodeURIComponent(queryTo)}`,
    ),
    portalToken ? backendRequest<ClientBookingOut[]>("/api/v1/clients/me/bookings", {}, portalToken) : Promise.resolve(null),
  ]);

  const sessionsRaw = sessionsResult.ok ? sessionsResult.data : [];
  const sessions = sessionsRaw
    .filter((session) => session.online_booking_enabled)
    .filter((session) => session.booking_scopes.includes("EXTERNAL"))
    .filter((session) => session.external_booking_price_ttc !== null)
    .sort((left, right) => left.start_at_utc.localeCompare(right.start_at_utc));

  const sessionIds = new Set(sessions.map((session) => session.id));
  const ownBookings = bookingsResult && bookingsResult.ok ? bookingsResult.data : [];
  const bookingsBySessionId = new Map(
    ownBookings
      .filter((booking) => sessionIds.has(booking.session.id))
      .map((booking) => [booking.session.id, booking]),
  );

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
  const selectedBooking = selectedSession ? bookingsBySessionId.get(selectedSession.id) ?? null : null;
  const selectedSessionStart = selectedSession ? safeDate(selectedSession.start_at_utc) : null;
  const selectedSessionStarted = selectedSessionStart ? selectedSessionStart.getTime() <= Date.now() : false;
  const selectedSessionIsFull = selectedSession ? selectedSession.seats_remaining <= 0 : false;
  const selectedSessionReturnTo = buildPlanningHref({
    courseTypeId,
    locationId,
    date: weekStartKey,
    sessionId: selectedSession?.id ?? null,
    language,
  });
  const previousHref = buildPlanningHref({
    courseTypeId,
    locationId,
    date: utcDateToKey(addUtcDays(weekStart, -7)),
    language,
  });
  const nextHref = buildPlanningHref({
    courseTypeId,
    locationId,
    date: utcDateToKey(addUtcDays(weekStart, 7)),
    language,
  });
  const todayHref = buildPlanningHref({
    courseTypeId,
    locationId,
    date: todayKeyInTimezone(timezone),
    language,
  });
  const closeSessionHref = buildPlanningHref({
    courseTypeId,
    locationId,
    date: weekStartKey,
    language,
  });
  const loginHref = `/login?mode=login&return_to=${encodeURIComponent(selectedSessionReturnTo)}${language === "en" ? "&lang=en" : ""}`;
  const sessionCheckoutHref = selectedSession ? buildSessionCheckoutHref(selectedSession.id, selectedSessionReturnTo, language) : `/buy/session/checkout${language === "en" ? "?lang=en" : ""}`;
  const sessionCheckoutLoginHref = `/login?mode=login&return_to=${encodeURIComponent(sessionCheckoutHref)}${language === "en" ? "&lang=en" : ""}`;
  const selectedSessionRequiresCheckout =
    selectedSession !== null && Number(selectedSession.external_booking_price_ttc ?? "0") > 0 && !selectedSessionIsFull;

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
              <h1>{selectedCourseType.name}</h1>
              <p className="muted">
                {selectedLocation
                  ? t("embed_planning.week_view_location", { location: selectedLocation.name })
                  : t("embed_planning.week_view_all_locations")}
              </p>
            </div>
            <div className="embed-planning-nav">
              <Link className="mode-link" href={previousHref}>←</Link>
              <Link className="mode-link" href={todayHref}>{uiText(language, "client.today")}</Link>
              <Link className="mode-link" href={nextHref}>→</Link>
            </div>
          </header>

          {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
          {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
          {sessionOkMessage ? <section className="flash-ok">{sessionOkMessage}</section> : null}
          {sessionErrorMessage ? <section className="flash-err">{sessionErrorMessage}</section> : null}

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
                      const isReserved = booking !== null && ["BOOKED", "WAITLISTED", "ATTENDED", "NO_SHOW", "EXCUSED_ABSENCE"].includes(booking.status);
                      const detailHref = buildPlanningHref({
                        courseTypeId,
                        locationId,
                        date: weekStartKey,
                        sessionId: session.id,
                        language,
                      });
                      return (
                        <Link key={session.id} className={`embed-slot-card${selectedSession?.id === session.id ? " is-selected" : ""}`} href={detailHref}>
                          <div className="embed-slot-card-top">
                            <strong>{formatTime(session.start_at_utc, timezone, language)} - {formatTime(session.end_at_utc, timezone, language)}</strong>
                            {isReserved ? <span className="badge">{t("embed_planning.reserved_badge")}</span> : null}
                          </div>
                          <p>{session.title}</p>
                          {!selectedLocation ? <small>{session.location?.name || t("embed_planning.location_to_confirm")}</small> : null}
                          <small>{formatMoney(session.external_booking_price_ttc, session.external_booking_currency, language)}</small>
                          <small>{externalAvailabilityLabel(session, language)}</small>
                        </Link>
                      );
                    })
                  )}
                </div>
              </section>
            ))}
          </div>
        </article>

        {selectedSession ? (
          <section className="card embed-planning-detail">
            <div className="row spread">
              <h2>{selectedSession.title}</h2>
              <Link className="reset-link" href={closeSessionHref}>{uiText(language, "common.close")}</Link>
            </div>

            <p className="muted">
              {formatDateTime(selectedSession.start_at_utc, timezone, language)} · {selectedLocation?.name || selectedSession.location?.name || t("embed_planning.location_to_confirm")}
            </p>

            <div className="embed-planning-detail-grid">
              <article className="item">
                <small className="muted">{t("embed_planning.external_rate")}</small>
                <p>{formatMoney(selectedSession.external_booking_price_ttc, selectedSession.external_booking_currency, language)}</p>
              </article>
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
                <p className="muted">{t("embed_planning.unauthenticated_help")}</p>
                <Link className="mode-link embed-planning-primary-link" href={selectedSessionRequiresCheckout ? sessionCheckoutLoginHref : loginHref}>
                  {t("embed_planning.reserve_cta")}
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
        ) : null}
      </section>
    </main>
  );
}
