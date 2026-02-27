"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest } from "./backend";
import type {
  AdminActivityOut,
  AdminInvoiceNumberingOut,
  AdminInvoiceTemplateOut,
  AdminClientPasswordEmailTemplateOut,
  AdminCreditTypeOut,
  AdminFormulaOut,
  AdminMessagingSettingsOut,
  AdminMessagingTemplateOut,
  AdminPlanningActivitiesOut,
  AdminProductCategoriesOut,
  AdminProfessorContractDeleteOut,
  AdminProfessorContractGridOut,
  AdminProfessorContractOut,
  AdminProfessorRateOut,
  AdminProfessorUpdateResult,
  AdminSubscriptionSettingsOut,
  AdminConfigAccountOut,
  AdminPaymentProviderOut,
  AdminPaymentMethodsOut,
  AdminProfessorDefaultGridOut,
  AuthLoginResponse,
  ClientPaymentCheckoutOut,
  ProfessorPermissionOut,
  UserOut,
} from "./types";

const ACCESS_TOKEN_COOKIE = "access_token";

type ApplyScope = "ONE" | "SERIES_FUTURE" | "SERIES_ALL";

function currentToken(): string | null {
  return cookies().get(ACCESS_TOKEN_COOKIE)?.value ?? null;
}

function setToken(token: string): void {
  cookies().set(ACCESS_TOKEN_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: false,
    path: "/",
    maxAge: 60 * 60 * 8,
  });
}

function clearToken(): void {
  cookies().delete(ACCESS_TOKEN_COOKIE);
}

function optionalField(formData: FormData, fieldName: string): string | null {
  const value = String(formData.get(fieldName) ?? "").trim();
  return value || null;
}

function checkboxField(formData: FormData, fieldName: string): boolean {
  return String(formData.get(fieldName) ?? "").toLowerCase() === "on";
}

function checkboxFieldWithDefault(formData: FormData, fieldName: string, defaultValue: boolean): boolean {
  const raw = formData.get(fieldName);
  if (raw === null) {
    return defaultValue;
  }
  const normalized = String(raw).trim().toLowerCase();
  if (!normalized) {
    return defaultValue;
  }
  return normalized === "on" || normalized === "true" || normalized === "1";
}

function parseApplyScope(raw: string): ApplyScope {
  const value = raw.trim().toUpperCase();
  if (value === "SERIES_FUTURE" || value === "SERIES_ALL") {
    return value;
  }
  return "ONE";
}

function parseUtcFromLocalInput(raw: string): string | null {
  const value = raw.trim();
  if (!value) {
    return null;
  }

  const candidate = value.length === 16 ? `${value}:00Z` : `${value}Z`;
  const parsed = new Date(candidate);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed.toISOString();
}

function parseUtcFromDateAndTime(dateRaw: string, timeRaw: string): string | null {
  const datePart = dateRaw.trim();
  const timePart = timeRaw.trim();
  if (!datePart || !timePart) {
    return null;
  }

  const normalizedTime = timePart.length === 5 ? `${timePart}:00` : timePart;
  const candidate = `${datePart}T${normalizedTime}Z`;
  const parsed = new Date(candidate);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }

  return parsed.toISOString();
}

function normalizeTimezone(raw: string, fallback = "UTC"): string {
  const value = raw.trim();
  if (!value) {
    return fallback;
  }
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: value }).format(new Date());
    return value;
  } catch {
    return fallback;
  }
}

type DateParts = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
};

function parseDateParts(dateRaw: string, timeRaw: string): DateParts | null {
  const dateMatch = dateRaw.trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!dateMatch) {
    return null;
  }
  const timeMatch = timeRaw.trim().match(/^(\d{2}):(\d{2})(?::(\d{2}))?$/);
  if (!timeMatch) {
    return null;
  }

  return {
    year: Number.parseInt(dateMatch[1], 10),
    month: Number.parseInt(dateMatch[2], 10),
    day: Number.parseInt(dateMatch[3], 10),
    hour: Number.parseInt(timeMatch[1], 10),
    minute: Number.parseInt(timeMatch[2], 10),
    second: Number.parseInt(timeMatch[3] ?? "0", 10),
  };
}

function getTimeZoneDateParts(instant: Date, timezone: string): DateParts {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(instant);

  const pick = (type: Intl.DateTimeFormatPartTypes): number => {
    const value = parts.find((part) => part.type === type)?.value ?? "0";
    return Number.parseInt(value, 10);
  };

  return {
    year: pick("year"),
    month: pick("month"),
    day: pick("day"),
    hour: pick("hour"),
    minute: pick("minute"),
    second: pick("second"),
  };
}

function parseUtcFromDateAndTimeInTimezone(dateRaw: string, timeRaw: string, timezoneRaw: string): string | null {
  const timezone = normalizeTimezone(timezoneRaw, "UTC");
  const requested = parseDateParts(dateRaw, timeRaw);
  if (!requested) {
    return null;
  }

  const requestedLocalMs = Date.UTC(
    requested.year,
    requested.month - 1,
    requested.day,
    requested.hour,
    requested.minute,
    requested.second,
    0,
  );

  let utcMs = requestedLocalMs;
  for (let i = 0; i < 3; i += 1) {
    const observed = getTimeZoneDateParts(new Date(utcMs), timezone);
    const observedLocalMs = Date.UTC(
      observed.year,
      observed.month - 1,
      observed.day,
      observed.hour,
      observed.minute,
      observed.second,
      0,
    );
    const delta = requestedLocalMs - observedLocalMs;
    utcMs += delta;
    if (delta === 0) {
      break;
    }
  }

  const parsed = new Date(utcMs);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed.toISOString();
}

function parseUtcStartOfDate(dateRaw: string): string | null {
  const datePart = dateRaw.trim();
  if (!datePart) {
    return null;
  }
  const parsed = new Date(`${datePart}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed.toISOString();
}

function safeAdminReturnPath(formData: FormData, fallback = "/admin"): string {
  const raw = String(formData.get("return_to") ?? "").trim();
  if (raw.startsWith("/admin")) {
    return raw;
  }
  return fallback;
}

function safeProfessorReturnPath(formData: FormData, fallback = "/prof"): string {
  const raw = String(formData.get("return_to") ?? "").trim();
  if (raw.startsWith("/prof")) {
    return raw;
  }
  return fallback;
}

function safeClientReturnPath(formData: FormData, fallback = "/dashboard"): string {
  const raw = String(formData.get("return_to") ?? "").trim();
  if (raw.startsWith("/dashboard")) {
    return raw;
  }
  return fallback;
}

function appendQueryMessage(path: string, key: string, message: string): string {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}${key}=${encodeURIComponent(message)}`;
}

function removeQueryParam(path: string, key: string): string {
  try {
    const url = new URL(path, "http://localhost");
    url.searchParams.delete(key);
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return path;
  }
}

function parsePositiveInt(raw: string): number | null {
  const value = raw.trim();
  if (!value) {
    return null;
  }
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

function parseNonNegativeInt(raw: string): number | null {
  const value = raw.trim();
  if (!value) {
    return null;
  }
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return null;
  }
  return parsed;
}

function parseNonNegativeDecimal(raw: string): number | null {
  const value = raw.trim();
  if (!value) {
    return null;
  }

  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return null;
  }

  return parsed;
}

function parsePaymentMethodCode(raw: string): string | null {
  const normalized = raw.trim().toUpperCase();
  if (!normalized) {
    return null;
  }
  if (
    normalized === "CHECK" ||
    normalized === "CASH" ||
    normalized === "BANK_TRANSFER" ||
    normalized === "CARD_ONLINE" ||
    normalized === "PAYPAL" ||
    normalized === "CARD_TERMINAL" ||
    normalized === "SEPA_DEBIT"
  ) {
    return normalized;
  }
  return null;
}

function parseProfessorContractLocationCode(raw: string): string | null {
  const normalized = raw.trim().toUpperCase();
  if (!normalized || normalized === "NONE") {
    return null;
  }
  return normalized;
}

function parseHeadcountRules(raw: string): Array<{ min_students: number; max_students: number | null; hourly_rate: number }> | null {
  const normalized = raw.trim();
  if (!normalized) {
    return [];
  }

  const rules: Array<{ min_students: number; max_students: number | null; hourly_rate: number }> = [];
  const chunks = normalized
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean);

  for (const chunk of chunks) {
    const parts = chunk.split(":");
    if (parts.length !== 2) {
      return null;
    }
    const rangeRaw = parts[0].trim();
    const rateRaw = parts[1].trim().replace(",", ".");
    const rate = parseNonNegativeDecimal(rateRaw);
    if (rate === null) {
      return null;
    }

    if (rangeRaw.endsWith("+")) {
      const min = parseNonNegativeInt(rangeRaw.slice(0, -1));
      if (min === null) {
        return null;
      }
      rules.push({ min_students: min, max_students: null, hourly_rate: rate });
      continue;
    }

    const [minRaw, maxRaw] = rangeRaw.split("-", 2).map((token) => token.trim());
    const min = parseNonNegativeInt(minRaw);
    if (min === null) {
      return null;
    }
    if (maxRaw === undefined || maxRaw === "") {
      rules.push({ min_students: min, max_students: null, hourly_rate: rate });
      continue;
    }
    const max = parseNonNegativeInt(maxRaw);
    if (max === null || max < min) {
      return null;
    }
    rules.push({ min_students: min, max_students: max, hourly_rate: rate });
  }

  return rules;
}

function parseLanguageList(raw: string): string[] {
  const tokens = raw
    .split(",")
    .map((token) => token.trim())
    .filter((token) => token.length > 0);

  const unique: string[] = [];
  const seen = new Set<string>();
  for (const token of tokens) {
    const key = token.toLocaleLowerCase("fr-FR");
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    unique.push(token);
  }

  return unique;
}

function parseStringList(rawValues: FormDataEntryValue[]): string[] {
  const unique: string[] = [];
  const seen = new Set<string>();

  for (const entry of rawValues) {
    const value = String(entry ?? "").trim();
    if (!value) {
      continue;
    }
    const key = value.toUpperCase();
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    unique.push(value);
  }

  return unique;
}

function isActiveFromClientStatus(status: string): boolean {
  const normalized = status.trim().toUpperCase();
  return normalized === "ACTIVE" || normalized === "TRIAL";
}

const PROFESSOR_PERMISSION_KEYS: Array<keyof ProfessorPermissionOut> = [
  "can_view_dashboard",
  "can_view_clients",
  "can_export_clients",
  "can_create_clients",
  "can_message_clients",
  "can_view_client_reminders",
  "can_create_subscriptions",
  "can_close_subscriptions",
  "can_edit_subscriptions",
  "can_downgrade_subscriptions",
  "can_cancel_subscriptions",
  "can_edit_payments",
  "can_refund_payments",
  "can_cancel_payments",
  "can_manage_mobile_news",
  "can_access_cash_menu",
  "can_view_planning",
  "can_view_all_school_sessions",
  "can_edit_planning",
  "can_force_booking",
  "can_view_admin_dashboard",
  "can_view_admin_reservations",
  "can_access_collaborators",
  "can_configure_app",
  "can_list_payments",
  "can_manage_events",
  "can_view_sportigo_info",
  "can_take_attendance",
  "can_record_payments_with_attendance",
  "can_edit_own_sessions",
  "can_view_pay_details",
  "can_manage_mileage_log",
  "can_view_other_teachers_contacts",
  "can_manage_other_teachers_students_and_sessions",
  "can_view_other_teachers_sessions",
  "can_view_student_parent_addresses_phones",
  "can_view_student_parent_emails",
  "can_view_student_attachments",
  "can_manage_invoices_and_accounts",
  "can_manage_expenses_and_other_income",
  "can_manage_shared_online_resources",
  "can_manage_website_and_news",
  "can_create_and_view_reports",
];

function parseProfessorPermissions(formData: FormData): ProfessorPermissionOut {
  const permissions = {} as ProfessorPermissionOut;

  for (const key of PROFESSOR_PERMISSION_KEYS) {
    permissions[key] = checkboxField(formData, key);
  }

  return permissions;
}

async function fetchCurrentUser(token: string): Promise<UserOut | null> {
  const result = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!result.ok) {
    return null;
  }
  return result.data;
}

async function ensureAdmin(token: string): Promise<void> {
  const me = await fetchCurrentUser(token);
  if (!me || me.role !== "admin") {
    redirect("/login?error=Acces%20admin%20requis");
  }
}

export async function loginAction(formData: FormData): Promise<void> {
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const password = String(formData.get("password") ?? "");

  const result = await backendRequest<AuthLoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

  if (!result.ok) {
    redirect(`/login?error=${encodeURIComponent(result.message)}`);
  }

  setToken(result.data.access_token);

  const me = await fetchCurrentUser(result.data.access_token);
  if (!me) {
    redirect("/login?error=Session%20invalide");
  }

  if (me.role === "admin") {
    redirect("/admin?ok=Connexion%20admin%20reussie");
  }

  if (me.role === "client") {
    redirect("/dashboard?ok=Connexion%20reussie");
  }

  redirect("/prof?ok=Connexion%20prof%20reussie");
}

export async function registerAction(formData: FormData): Promise<void> {
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const password = String(formData.get("password") ?? "");
  const first_name = optionalField(formData, "first_name");
  const last_name = optionalField(formData, "last_name");
  const address_line = optionalField(formData, "address_line");
  const phone = optionalField(formData, "phone");
  const residence_country = String(formData.get("residence_country") ?? "FR").trim().toUpperCase();
  const preferred_currency = String(formData.get("preferred_currency") ?? "EUR").trim().toUpperCase();
  const timezone = String(formData.get("timezone") ?? "Europe/Paris").trim();

  const registerResult = await backendRequest<{ id: string }>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({
      email,
      password,
      first_name,
      last_name,
      address_line,
      phone,
      residence_country,
      preferred_currency,
      timezone,
    }),
  });

  if (!registerResult.ok) {
    redirect(`/login?error=${encodeURIComponent(registerResult.message)}`);
  }

  const loginResult = await backendRequest<AuthLoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

  if (!loginResult.ok) {
    redirect(`/login?error=${encodeURIComponent(loginResult.message)}`);
  }

  setToken(loginResult.data.access_token);
  redirect("/dashboard?ok=Compte%20cree");
}

export async function forgotPasswordAction(formData: FormData): Promise<void> {
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  if (!email) {
    redirect("/login?error=Email%20obligatoire");
  }

  const result = await backendRequest<{ message: string }>("/api/v1/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email }),
  });

  if (!result.ok) {
    redirect(`/login?error=${encodeURIComponent(result.message)}`);
  }

  redirect(`/login?ok=${encodeURIComponent(result.data.message)}`);
}

export async function resetPasswordAction(formData: FormData): Promise<void> {
  const token = String(formData.get("token") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const passwordConfirm = String(formData.get("password_confirm") ?? "");

  if (!token) {
    redirect("/login?error=Lien%20de%20reinitialisation%20invalide");
  }
  if (password.length < 8) {
    redirect(`/login?reset_token=${encodeURIComponent(token)}&error=Mot%20de%20passe%20trop%20court`);
  }
  if (password !== passwordConfirm) {
    redirect(`/login?reset_token=${encodeURIComponent(token)}&error=Les%20mots%20de%20passe%20ne%20correspondent%20pas`);
  }

  const result = await backendRequest<{ message: string }>("/api/v1/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ token, password }),
  });

  if (!result.ok) {
    redirect(`/login?reset_token=${encodeURIComponent(token)}&error=${encodeURIComponent(result.message)}`);
  }

  redirect(`/login?ok=${encodeURIComponent(result.data.message)}`);
}

export async function logoutAction(): Promise<void> {
  clearToken();
  redirect("/login?ok=Deconnexion%20effectuee");
}

export async function updateProfileAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const residence_country = String(formData.get("residence_country") ?? "").trim().toUpperCase();
  const preferred_currency = String(formData.get("preferred_currency") ?? "").trim().toUpperCase();
  const timezone = String(formData.get("timezone") ?? "").trim();

  if (!residence_country || !preferred_currency || !timezone) {
    redirect("/dashboard?tab=account&edit_profile=1&error=Pays%2C%20devise%20et%20timezone%20sont%20obligatoires");
  }

  const payload = {
    first_name: optionalField(formData, "first_name"),
    last_name: optionalField(formData, "last_name"),
    address_line: optionalField(formData, "address_line"),
    postal_code: optionalField(formData, "postal_code"),
    city: optionalField(formData, "city"),
    address_country: String(formData.get("address_country") ?? "").trim().toUpperCase() || null,
    phone: optionalField(formData, "phone"),
    mobile_phone_1: optionalField(formData, "mobile_phone_1"),
    mobile_phone_2: optionalField(formData, "mobile_phone_2"),
    home_phone: optionalField(formData, "home_phone"),
    important_info: optionalField(formData, "important_info"),
    portal_contact_visible: checkboxField(formData, "portal_contact_visible"),
    email_opt_in: checkboxField(formData, "email_opt_in"),
    sms_opt_in: checkboxField(formData, "sms_opt_in"),
    lesson_reminder_email_opt_in: checkboxField(formData, "lesson_reminder_email_opt_in"),
    lesson_reminder_sms_opt_in: checkboxField(formData, "lesson_reminder_sms_opt_in"),
    residence_country,
    preferred_currency,
    timezone,
  };

  const result = await backendRequest<Record<string, never>>(
    "/api/v1/clients/me",
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/dashboard?tab=account&edit_profile=1&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/dashboard");
  redirect("/dashboard?tab=account&ok=Profil%20mis%20a%20jour");
}

export async function purchasePlanAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const planId = String(formData.get("plan_id") ?? "");
  const purchaseUserId = String(formData.get("purchase_user_id") ?? "").trim();
  const payload: Record<string, string> = {};
  if (purchaseUserId) {
    payload.user_id = purchaseUserId;
  }

  const result = await backendRequest<{ id: string; checkout_url?: string | null }>(
    `/api/v1/plans/${planId}/purchase`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/dashboard?tab=offers&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/dashboard");
  if (result.data.checkout_url) {
    redirect(result.data.checkout_url);
  }
  redirect("/dashboard?tab=offers&ok=Offre%20souscrite");
}

export async function openClientPaymentCheckoutAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const returnTo = safeClientReturnPath(formData, "/dashboard?tab=transactions");
  const paymentRaw = String(formData.get("payment_id") ?? "").trim();
  const paymentId = paymentRaw.startsWith("plan:") ? paymentRaw.slice("plan:".length) : paymentRaw;
  if (!paymentId) {
    redirect(appendQueryMessage(returnTo, "error", "Paiement introuvable"));
  }

  const result = await backendRequest<ClientPaymentCheckoutOut>(
    `/api/v1/clients/me/payments/${paymentId}/checkout`,
    {
      method: "POST",
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/dashboard");
  redirect(result.data.checkout_url);
}

export async function bookSessionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  const returnTo = safeClientReturnPath(formData, "/dashboard?tab=planning");
  const inSessionContext = returnTo.includes("session_id=");

  const sessionId = String(formData.get("session_id") ?? "");
  const bookingUserId = String(formData.get("booking_user_id") ?? "").trim();
  const subscriptionId = String(formData.get("client_plan_subscription_id") ?? "").trim();
  const payload: Record<string, string> = {};
  if (bookingUserId) {
    payload.user_id = bookingUserId;
  }
  if (subscriptionId) {
    payload.client_plan_subscription_id = subscriptionId;
  }
  const result = await backendRequest<{ id: string }>(
    `/api/v1/sessions/${sessionId}/book`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    const userMessage =
      result.status === 403 && result.message === "No eligible active plan for this session"
        ? "Aucune formule active compatible avec ce type de cours."
        : result.status === 403 && result.message === "No remaining credits on selected pack"
          ? "Plus de credits disponibles sur le carnet selectionne."
        : result.message;
    let failurePath = removeQueryParam(returnTo, "ok");
    failurePath = removeQueryParam(failurePath, "session_ok");
    if (inSessionContext) {
      failurePath = removeQueryParam(failurePath, "session_error");
      failurePath = appendQueryMessage(failurePath, "session_error", userMessage);
    }
    redirect(appendQueryMessage(failurePath, "error", userMessage));
  }

  revalidatePath("/dashboard");
  let successPath = removeQueryParam(returnTo, "error");
  successPath = removeQueryParam(successPath, "session_error");
  if (inSessionContext) {
    successPath = removeQueryParam(successPath, "session_ok");
    successPath = appendQueryMessage(successPath, "session_ok", "Reservation confirmee");
  }
  redirect(appendQueryMessage(successPath, "ok", "Reservation confirmee"));
}

export async function cancelBookingAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  const returnTo = safeClientReturnPath(formData, "/dashboard?tab=reservations");

  const bookingId = String(formData.get("booking_id") ?? "");
  const result = await backendRequest<Record<string, never>>(
    `/api/v1/bookings/${bookingId}`,
    {
      method: "DELETE",
    },
    token,
  );

  if (!result.ok && result.status != 204) {
    const failurePath = removeQueryParam(returnTo, "ok");
    redirect(appendQueryMessage(failurePath, "error", result.message));
  }

  revalidatePath("/dashboard");
  const successPath = removeQueryParam(returnTo, "error");
  redirect(appendQueryMessage(successPath, "ok", "Reservation annulee"));
}

export async function professorUpdateAttendanceAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const returnTo = safeProfessorReturnPath(formData, "/prof?tab=planning");
  const bookingId = String(formData.get("booking_id") ?? "").trim();
  const attendanceStatus = String(formData.get("attendance_status") ?? "").trim().toUpperCase();

  if (!bookingId || !["ATTENDED", "NO_SHOW", "EXCUSED_ABSENCE"].includes(attendanceStatus)) {
    redirect(appendQueryMessage(returnTo, "error", "Saisie de presence invalide"));
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/bookings/${bookingId}/attendance`,
    {
      method: "POST",
      body: JSON.stringify({ attendance_status: attendanceStatus }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/prof");
  redirect(appendQueryMessage(returnTo, "ok", "Presence mise a jour"));
}

export async function professorSendSessionMessageAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const returnTo = safeProfessorReturnPath(formData, "/prof?tab=planning");
  const sessionId = String(formData.get("session_id") ?? "").trim();
  const subject = String(formData.get("subject") ?? "").trim();
  const body = String(formData.get("body") ?? "").trim();
  const bodyFormat = String(formData.get("body_format") ?? "TEXT").trim().toUpperCase() === "HTML" ? "HTML" : "TEXT";

  if (!sessionId || !subject || !body) {
    redirect(appendQueryMessage(returnTo, "error", "Sujet et message obligatoires"));
  }

  const result = await backendRequest<{ message_id: string; recipient_count: number }>(
    `/api/v1/professors/me/sessions/${sessionId}/messages`,
    {
      method: "POST",
      body: JSON.stringify({
        subject,
        body,
        body_format: bodyFormat,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/prof");
  redirect(appendQueryMessage(returnTo, "ok", `Message envoye (${result.data.recipient_count} destinataire(s))`));
}

export async function professorMarkSessionAbsentAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const returnTo = safeProfessorReturnPath(formData, "/prof?tab=planning");
  const sessionId = String(formData.get("session_id") ?? "").trim();
  const notifyStudents = checkboxField(formData, "notify_students");
  const studentsSubject = optionalField(formData, "students_subject");
  const studentsMessage = optionalField(formData, "students_message");
  const studentsFormat = String(formData.get("students_format") ?? "TEXT").trim().toUpperCase() === "HTML" ? "HTML" : "TEXT";

  if (!sessionId) {
    redirect(appendQueryMessage(returnTo, "error", "Creneau invalide"));
  }

  const payload: Record<string, unknown> = {
    notify_students: notifyStudents,
    students_format: studentsFormat,
  };
  if (notifyStudents) {
    payload.students_subject = studentsSubject;
    payload.students_message = studentsMessage;
  }

  const result = await backendRequest<{ session_id: string; notified_students: number }>(
    `/api/v1/professors/me/sessions/${sessionId}/absence`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/prof");
  redirect(appendQueryMessage(returnTo, "ok", `Creneau annule (notif: ${result.data.notified_students})`));
}

export async function createAdminSessionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);
  const returnTo = safeAdminReturnPath(formData, "/admin?create=1");

  const course_type_id = String(formData.get("course_type_id") ?? "").trim();
  const location_id = String(formData.get("location_id") ?? "").trim();
  const professor_id = String(formData.get("professor_id") ?? "").trim();
  const title = String(formData.get("title") ?? "").trim();
  const public_description = optionalField(formData, "public_description");
  const private_description = optionalField(formData, "private_description");
  const zoom_link = optionalField(formData, "zoom_link");
  const is_private = checkboxField(formData, "is_private");
  const allow_online_booking = !is_private && checkboxFieldWithDefault(formData, "allow_online_booking", true);
  const is_all_day = checkboxField(formData, "is_all_day");
  const session_timezone = normalizeTimezone(String(formData.get("session_timezone") ?? "Europe/Paris"), "Europe/Paris");
  const recurrence_mode = String(formData.get("recurrence_mode") ?? "NONE").trim().toUpperCase();

  const recurrence_frequency = String(formData.get("recurrence_frequency") ?? "WEEKLY").trim().toUpperCase();
  const recurrence_interval_raw = String(formData.get("recurrence_interval") ?? "1").trim();
  const recurrence_interval = parsePositiveInt(recurrence_interval_raw);
  const recurrence_until_date = String(formData.get("recurrence_until_date") ?? "").trim();

  const start_date = String(formData.get("start_date") ?? "");
  const start_time = String(formData.get("start_time") ?? (is_all_day ? "00:00" : ""));
  const end_time = String(formData.get("end_time") ?? "");
  const start_at_utc = parseUtcFromDateAndTimeInTimezone(start_date, is_all_day ? "00:00" : start_time, session_timezone);
  const end_at_utc = is_all_day
    ? null
    : end_time.trim()
      ? parseUtcFromDateAndTimeInTimezone(start_date, end_time, session_timezone)
      : null;

  const capacity_raw = String(formData.get("capacity_max") ?? "");
  const parsed_capacity_max = parseNonNegativeInt(capacity_raw);
  const capacity_max = parsed_capacity_max ?? 1;

  if (!course_type_id || !location_id || !professor_id || !title || !start_at_utc) {
    redirect(appendQueryMessage(returnTo, "error", "Champs obligatoires manquants"));
  }

  if (!is_all_day && !start_time.trim()) {
    redirect(appendQueryMessage(returnTo, "error", "Heure de debut obligatoire"));
  }

  if (!is_all_day && end_time.trim() && !end_at_utc) {
    redirect(appendQueryMessage(returnTo, "error", "Heure de fin invalide"));
  }

  if (!capacity_raw.trim() || parsed_capacity_max === null || capacity_max < 0) {
    redirect(appendQueryMessage(returnTo, "error", "Capacite max obligatoire (>= 0; vacances = 0)"));
  }

  const recurrenceEnabled = recurrence_mode === "RECURRING";
  if (recurrenceEnabled) {
    if (!(recurrence_frequency === "DAILY" || recurrence_frequency === "WEEKLY" || recurrence_frequency === "MONTHLY")) {
      redirect(appendQueryMessage(returnTo, "error", "Frequence de recurrence invalide"));
    }
    if (recurrence_interval === null || recurrence_interval < 1) {
      redirect(appendQueryMessage(returnTo, "error", "Intervalle de recurrence invalide"));
    }
    if (recurrence_interval !== 1) {
      redirect(appendQueryMessage(returnTo, "error", "Intervalle de recurrence > 1 pas encore supporte"));
    }
    if (!recurrence_until_date) {
      redirect(appendQueryMessage(returnTo, "error", "Choisir une date de fin de recurrence"));
    }
  }

  const payload: Record<string, unknown> = {
    course_type_id,
    location_id,
    professor_id,
    title,
    start_at_utc,
    is_all_day,
    capacity_max,
    is_private,
    allow_online_booking,
    timezone: session_timezone,
  };

  if (public_description !== null) {
    payload.public_description = public_description;
  }
  if (private_description !== null) {
    payload.private_description = private_description;
  }
  if (zoom_link !== null) {
    payload.zoom_link = zoom_link;
  }
  if (end_at_utc !== null) {
    payload.end_at_utc = end_at_utc;
  }
  if (recurrenceEnabled) {
    const recurrence: Record<string, unknown> = { frequency: recurrence_frequency };
    recurrence.until_date = recurrence_until_date;
    payload.recurrence = recurrence;
  }

  const result = await backendRequest<{ id: string }>(
    "/api/v1/admin/sessions",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin");
  const successPath = removeQueryParam(returnTo, "create");
  redirect(appendQueryMessage(successPath, "ok", "Creneau cree"));
}

export async function updateAdminSessionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);
  const returnTo = safeAdminReturnPath(formData, "/admin");

  const session_id = String(formData.get("session_id") ?? "").trim();
  const title = String(formData.get("title") ?? "").trim();
  const public_description = optionalField(formData, "public_description");
  const private_description = optionalField(formData, "private_description");
  const course_type_id = String(formData.get("course_type_id") ?? "").trim();
  const location_id = String(formData.get("location_id") ?? "").trim();
  const professor_id = String(formData.get("professor_id") ?? "").trim();
  const zoom_link = optionalField(formData, "zoom_link");
  const status = String(formData.get("status") ?? "").trim();
  const is_private = checkboxField(formData, "is_private");
  const allow_online_booking = !is_private && checkboxFieldWithDefault(formData, "allow_online_booking", true);
  const is_all_day = checkboxField(formData, "is_all_day");
  const session_timezone = normalizeTimezone(String(formData.get("session_timezone") ?? "Europe/Paris"), "Europe/Paris");
  const apply_scope = parseApplyScope(String(formData.get("apply_scope") ?? "ONE"));

  const start_date = String(formData.get("start_date") ?? "");
  const start_time = String(formData.get("start_time") ?? (is_all_day ? "00:00" : ""));
  const end_time = String(formData.get("end_time") ?? "");
  const start_at_utc = parseUtcFromDateAndTimeInTimezone(start_date, is_all_day ? "00:00" : start_time, session_timezone);
  const end_at_utc = is_all_day ? null : parseUtcFromDateAndTimeInTimezone(start_date, end_time, session_timezone);
  const capacity_raw = String(formData.get("capacity_max") ?? "");
  const capacity_max = parseNonNegativeInt(capacity_raw);

  if (!session_id || !title || !start_at_utc || !course_type_id || !location_id || !professor_id) {
    redirect(appendQueryMessage(returnTo, "error", "Champs de modification invalides"));
  }
  if (!is_all_day && !end_at_utc) {
    redirect(appendQueryMessage(returnTo, "error", "Heure de fin invalide"));
  }

  if (capacity_raw.trim() && capacity_max === null) {
    redirect(appendQueryMessage(returnTo, "error", "Capacite max invalide"));
  }

  const payload: Record<string, unknown> = {
    title,
    public_description,
    private_description,
    course_type_id,
    location_id,
    professor_id,
    start_at_utc,
    is_all_day,
    is_private,
    allow_online_booking,
    timezone: session_timezone,
  };

  if (end_at_utc !== null) {
    payload.end_at_utc = end_at_utc;
  }
  if (capacity_max !== null) {
    payload.capacity_max = capacity_max;
  }
  if (zoom_link !== null) {
    payload.zoom_link = zoom_link;
  } else {
    payload.zoom_link = null;
  }
  if (status && status !== "UNCHANGED") {
    payload.status = status;
    if (status === "CANCELLED") {
      payload.cancel_reason = "ADMIN_CANCELLED";
    }
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/sessions/${session_id}?apply_scope=${apply_scope}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin");
  const successPath = removeQueryParam(returnTo, "session_id");
  redirect(appendQueryMessage(successPath, "ok", "Creneau modifie"));
}

export async function shiftAdminSessionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);
  const returnTo = safeAdminReturnPath(formData, "/admin?edit=1");

  const session_id = String(formData.get("session_id") ?? "").trim();
  const apply_scope = parseApplyScope(String(formData.get("apply_scope") ?? "ONE"));
  const minutes_delta_raw = String(formData.get("minutes_delta") ?? "").trim();
  const current_start_raw = String(formData.get("current_start_at_utc") ?? "");
  const current_end_raw = String(formData.get("current_end_at_utc") ?? "");

  const minutes_delta = Number.parseInt(minutes_delta_raw, 10);
  if (!session_id || !Number.isFinite(minutes_delta)) {
    redirect(appendQueryMessage(returnTo, "error", "Deplacement rapide invalide"));
  }

  const start_at_utc = parseUtcFromLocalInput(current_start_raw);
  const end_at_utc = parseUtcFromLocalInput(current_end_raw);
  if (!start_at_utc || !end_at_utc) {
    redirect(appendQueryMessage(returnTo, "error", "Date de deplacement invalide"));
  }

  const start_ms = Date.parse(start_at_utc);
  const end_ms = Date.parse(end_at_utc);
  if (!Number.isFinite(start_ms) || !Number.isFinite(end_ms)) {
    redirect(appendQueryMessage(returnTo, "error", "Date de deplacement invalide"));
  }

  const shifted_start = new Date(start_ms + minutes_delta * 60_000).toISOString();
  const shifted_end = new Date(end_ms + minutes_delta * 60_000).toISOString();

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/sessions/${session_id}?apply_scope=${apply_scope}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        start_at_utc: shifted_start,
        end_at_utc: shifted_end,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin");
  redirect(appendQueryMessage(returnTo, "ok", "Creneau decale"));
}

export async function cancelAdminSessionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);
  const returnTo = safeAdminReturnPath(formData, "/admin?edit=1");

  const session_id = String(formData.get("session_id") ?? "").trim();
  const apply_scope = parseApplyScope(String(formData.get("apply_scope") ?? "ONE"));
  const notify_students = checkboxField(formData, "notify_students");
  const notify_professor = checkboxField(formData, "notify_professor");
  const professor_same_as_students = checkboxField(formData, "professor_same_as_students");
  const students_subject = optionalField(formData, "students_subject");
  const students_message = optionalField(formData, "students_message");
  const students_format = String(formData.get("students_format") ?? "TEXT").trim().toUpperCase() === "HTML" ? "HTML" : "TEXT";
  const professor_subject = optionalField(formData, "professor_subject");
  const professor_message = optionalField(formData, "professor_message");
  const professor_format = String(formData.get("professor_format") ?? "TEXT").trim().toUpperCase() === "HTML" ? "HTML" : "TEXT";
  if (!session_id) {
    redirect(appendQueryMessage(returnTo, "error", "Session invalide"));
  }

  const payload: Record<string, unknown> = {
    cancel_reason: "ADMIN_CANCELLED",
  };
  if (notify_students || notify_professor) {
    payload.notifications = {
      notify_students,
      students_subject,
      students_message,
      students_format,
      notify_professor,
      professor_same_as_students,
      professor_subject,
      professor_message,
      professor_format,
    };
  }

  const result = await backendRequest<{
    processed_sessions: number;
    notified_students: number;
    notified_professors: number;
  }>(
    `/api/v1/admin/sessions/${session_id}/cancel?apply_scope=${apply_scope}`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin");
  const successPath = removeQueryParam(returnTo, "confirm_action");
  const details =
    result.data.notified_students > 0 || result.data.notified_professors > 0
      ? ` (${result.data.notified_students} eleve(s), ${result.data.notified_professors} professeur(s) notifie(s))`
      : "";
  redirect(appendQueryMessage(successPath, "ok", `Cours annule${details}`));
}

export async function deleteAdminSessionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);
  const returnTo = safeAdminReturnPath(formData, "/admin?edit=1");

  const session_id = String(formData.get("session_id") ?? "").trim();
  const delete_following = String(formData.get("delete_following") ?? "").trim().toLowerCase();
  let apply_scope = parseApplyScope(String(formData.get("apply_scope") ?? "ONE"));
  if (delete_following === "yes") {
    apply_scope = "SERIES_FUTURE";
  } else if (delete_following === "no") {
    apply_scope = "ONE";
  }
  const notify_students = checkboxField(formData, "notify_students");
  const notify_professor = checkboxField(formData, "notify_professor");
  const professor_same_as_students = checkboxField(formData, "professor_same_as_students");
  const students_subject = optionalField(formData, "students_subject");
  const students_message = optionalField(formData, "students_message");
  const students_format = String(formData.get("students_format") ?? "TEXT").trim().toUpperCase() === "HTML" ? "HTML" : "TEXT";
  const professor_subject = optionalField(formData, "professor_subject");
  const professor_message = optionalField(formData, "professor_message");
  const professor_format = String(formData.get("professor_format") ?? "TEXT").trim().toUpperCase() === "HTML" ? "HTML" : "TEXT";
  if (!session_id) {
    redirect(appendQueryMessage(returnTo, "error", "Session invalide"));
  }

  const payload: Record<string, unknown> = {};
  if (notify_students || notify_professor) {
    payload.notifications = {
      notify_students,
      students_subject,
      students_message,
      students_format,
      notify_professor,
      professor_same_as_students,
      professor_subject,
      professor_message,
      professor_format,
    };
  }

  const result = await backendRequest<{
    processed_sessions: number;
    notified_students: number;
    notified_professors: number;
  }>(
    `/api/v1/admin/sessions/${session_id}/delete?apply_scope=${apply_scope}`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin");
  let successPath = removeQueryParam(returnTo, "session_id");
  successPath = removeQueryParam(successPath, "confirm_action");
  const details =
    result.data.notified_students > 0 || result.data.notified_professors > 0
      ? ` (${result.data.notified_students} eleve(s), ${result.data.notified_professors} professeur(s) notifie(s))`
      : "";
  redirect(appendQueryMessage(successPath, "ok", `Creneau supprime${details}`));
}

export async function adminAddClientToSessionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);
  const returnTo = safeAdminReturnPath(formData, "/admin?edit=1");

  const sessionId = String(formData.get("session_id") ?? "").trim();
  const clientId = String(formData.get("client_id") ?? "").trim();
  const clientPlanSubscriptionIdRaw = String(formData.get("client_plan_subscription_id") ?? "").trim();
  const recurrenceChecked = checkboxField(formData, "apply_recurrence");
  const recurrenceEndDate = String(formData.get("recurrence_end_date") ?? "").trim();
  const apply_scope = recurrenceChecked ? "SERIES_FUTURE" : "ONE";

  if (!sessionId || !clientId) {
    redirect(appendQueryMessage(returnTo, "error", "Session ou client invalide"));
  }
  if (recurrenceChecked && !recurrenceEndDate) {
    redirect(appendQueryMessage(returnTo, "error", "Date de fin de recurrence requise"));
  }

  const payload: Record<string, unknown> = {
    client_id: clientId,
  };
  if (clientPlanSubscriptionIdRaw) {
    payload.client_plan_subscription_id = clientPlanSubscriptionIdRaw;
  }
  if (recurrenceChecked && recurrenceEndDate) {
    payload.recurrence_end_date = recurrenceEndDate;
  }

  const result = await backendRequest<{
    processed_count: number;
    booked_count: number;
    waitlisted_count: number;
    skipped_count: number;
    details: string[];
  }>(
    `/api/v1/admin/sessions/${sessionId}/bookings?apply_scope=${apply_scope}`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin");
  if (result.data.processed_count === 0) {
    const detail = result.data.details?.[0] ?? "Inscription impossible pour ce creneau";
    redirect(appendQueryMessage(returnTo, "error", detail));
  }
  const summary = `Inscription: ${result.data.booked_count} reserve(s), ${result.data.waitlisted_count} en attente, ${result.data.skipped_count} ignore(s)`;
  redirect(appendQueryMessage(returnTo, "ok", summary));
}

export async function adminRemoveClientFromSessionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);
  const returnTo = safeAdminReturnPath(formData, "/admin?edit=1");

  const sessionId = String(formData.get("session_id") ?? "").trim();
  const bookingId = String(formData.get("booking_id") ?? "").trim();
  if (!sessionId || !bookingId) {
    redirect(appendQueryMessage(returnTo, "error", "Reservation invalide"));
  }

  const result = await backendRequest<Record<string, never>>(
    `/api/v1/admin/sessions/${sessionId}/bookings/${bookingId}`,
    {
      method: "DELETE",
    },
    token,
  );

  if (!result.ok && result.status !== 204) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin");
  redirect(appendQueryMessage(returnTo, "ok", "Eleve retire du creneau"));
}

export async function adminUpdateSessionAttendanceAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);
  const returnTo = safeAdminReturnPath(formData, "/admin?edit=1");

  const sessionId = String(formData.get("session_id") ?? "").trim();
  const bookingId = String(formData.get("booking_id") ?? "").trim();
  const attendanceStatus = String(formData.get("attendance_status") ?? "").trim().toUpperCase();

  if (!sessionId || !bookingId || !["BOOKED", "ATTENDED", "NO_SHOW", "EXCUSED_ABSENCE"].includes(attendanceStatus)) {
    redirect(appendQueryMessage(returnTo, "error", "Saisie de presence invalide"));
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/sessions/${sessionId}/bookings/${bookingId}/attendance`,
    {
      method: "POST",
      body: JSON.stringify({ attendance_status: attendanceStatus }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin");
  redirect(appendQueryMessage(returnTo, "ok", "Presence mise a jour"));
}

export async function adminUpdateSessionGroupNoteAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);
  const returnTo = safeAdminReturnPath(formData, "/admin?edit=1");

  const sessionId = String(formData.get("session_id") ?? "").trim();
  if (!sessionId) {
    redirect(appendQueryMessage(returnTo, "error", "Session invalide"));
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/sessions/${sessionId}/group-note`,
    {
      method: "PATCH",
      body: JSON.stringify({ group_note: optionalField(formData, "group_note") }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin");
  redirect(appendQueryMessage(returnTo, "ok", "Note de groupe enregistree"));
}

export async function adminUpdateSessionBookingNoteAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);
  const returnTo = safeAdminReturnPath(formData, "/admin?edit=1");

  const sessionId = String(formData.get("session_id") ?? "").trim();
  const bookingId = String(formData.get("booking_id") ?? "").trim();
  if (!sessionId || !bookingId) {
    redirect(appendQueryMessage(returnTo, "error", "Reservation invalide"));
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/sessions/${sessionId}/bookings/${bookingId}/note`,
    {
      method: "PATCH",
      body: JSON.stringify({ student_note: optionalField(formData, "student_note") }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin");
  redirect(appendQueryMessage(returnTo, "ok", "Note eleve enregistree"));
}

export async function updatePlanningSettingsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const locationId = String(formData.get("location_id") ?? "").trim();
  if (!locationId) {
    redirect("/admin?error=Planning%20invalide");
  }

  const min_booking_notice_hours_raw = String(formData.get("min_booking_notice_hours") ?? "").trim();
  const max_booking_horizon_months_raw = String(formData.get("max_booking_horizon_months") ?? "").trim();
  const cancellation_deadline_hours_raw = String(formData.get("cancellation_deadline_hours") ?? "").trim();
  const max_bookings_per_client_raw = String(formData.get("max_bookings_per_client") ?? "").trim();
  const waitlist_capacity_raw = String(formData.get("waitlist_capacity") ?? "").trim();
  const auto_cancel_if_booked_less_than_raw = String(formData.get("auto_cancel_if_booked_less_than") ?? "").trim();
  const auto_cancel_hours_before_start_raw = String(formData.get("auto_cancel_hours_before_start") ?? "").trim();

  const min_booking_notice_hours = parseNonNegativeInt(min_booking_notice_hours_raw);
  const max_booking_horizon_months = parsePositiveInt(max_booking_horizon_months_raw);
  const cancellation_deadline_hours = parseNonNegativeInt(cancellation_deadline_hours_raw);
  const max_bookings_per_client = parsePositiveInt(max_bookings_per_client_raw);
  const waitlist_capacity = parseNonNegativeInt(waitlist_capacity_raw);
  const auto_cancel_if_booked_less_than = parseNonNegativeInt(auto_cancel_if_booked_less_than_raw);
  const auto_cancel_hours_before_start = parseNonNegativeInt(auto_cancel_hours_before_start_raw);

  if (min_booking_notice_hours === null || max_booking_horizon_months === null || cancellation_deadline_hours === null) {
    redirect(`/admin/plannings/${locationId}/settings?error=Delais%20planning%20invalides`);
  }
  if (waitlist_capacity === null || auto_cancel_if_booked_less_than === null || auto_cancel_hours_before_start === null) {
    redirect(`/admin/plannings/${locationId}/settings?error=Parametres%20de%20capacite%20invalides`);
  }
  if (max_bookings_per_client_raw && max_bookings_per_client === null) {
    redirect(`/admin/plannings/${locationId}/settings?error=Nombre%20max%20de%20reservations%20invalide`);
  }

  const payload: Record<string, unknown> = {
    description: optionalField(formData, "description"),
    min_booking_notice_hours,
    max_booking_horizon_months,
    cancellation_deadline_hours,
    max_bookings_per_client: max_bookings_per_client_raw ? max_bookings_per_client : null,
    allow_negative_credits: checkboxField(formData, "allow_negative_credits"),
    waitlist_capacity,
    auto_cancel_if_booked_less_than,
    auto_cancel_hours_before_start,
    is_private: checkboxField(formData, "is_private"),
    allow_force_booking: checkboxField(formData, "allow_force_booking"),
    allow_multi_booking: checkboxField(formData, "allow_multi_booking"),
    notify_coach: checkboxField(formData, "notify_coach"),
    notify_admins: checkboxField(formData, "notify_admins"),
    hide_booking_count: checkboxField(formData, "hide_booking_count"),
    block_client_cancellation: checkboxField(formData, "block_client_cancellation"),
  };

  const result = await backendRequest<{ location_id: string }>(
    `/api/v1/admin/plannings/${locationId}/settings`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/plannings/${locationId}/settings?error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin");
  revalidatePath(`/admin/plannings/${locationId}/settings`);
  redirect(`/admin/plannings/${locationId}/settings?ok=Parametres%20planning%20mis%20a%20jour`);
}

export async function updateAdminClientAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const returnTab = String(formData.get("return_tab") ?? "infos").trim() || "infos";
  if (!clientId) {
    redirect("/admin/clients?error=Client%20invalide");
  }

  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const firstName = String(formData.get("first_name") ?? "").trim();
  const lastName = String(formData.get("last_name") ?? "").trim();
  const residence_country = String(formData.get("residence_country") ?? "").trim().toUpperCase();
  const preferred_currency = String(formData.get("preferred_currency") ?? "").trim().toUpperCase();
  const timezone = String(formData.get("timezone") ?? "").trim();
  const address_country = String(formData.get("address_country") ?? "").trim().toUpperCase();
  const client_status = String(formData.get("client_status") ?? "").trim().toUpperCase() || "ACTIVE";
  const client_kind_raw = String(formData.get("client_kind") ?? "").trim().toUpperCase();
  const client_kind = client_kind_raw === "CHILD" ? "CHILD" : "ADULT";
  const birthDateRaw = String(formData.get("birth_date") ?? "").trim();

  if (!firstName || !lastName || !address_country) {
    redirect(
      `/admin/clients/${clientId}?tab=${returnTab}&error=Prenom%2C%20nom%20et%20pays%20de%20taxation%20sont%20obligatoires`,
    );
  }

  const payload = {
    ...(email ? { email } : {}),
    first_name: firstName,
    last_name: lastName,
    address_line: optionalField(formData, "address_line"),
    postal_code: optionalField(formData, "postal_code"),
    city: optionalField(formData, "city"),
    address_country,
    mobile_phone_1: optionalField(formData, "mobile_phone_1"),
    mobile_phone_2: optionalField(formData, "mobile_phone_2"),
    home_phone: optionalField(formData, "home_phone"),
    phone: optionalField(formData, "mobile_phone_1"),
    birth_date: birthDateRaw || null,
    important_info: optionalField(formData, "important_info"),
    private_note: optionalField(formData, "private_note"),
    residence_country,
    preferred_currency,
    timezone,
    portal_contact_visible: checkboxFieldWithDefault(formData, "portal_contact_visible", true),
    email_opt_in: checkboxFieldWithDefault(formData, "email_opt_in", true),
    sms_opt_in: checkboxFieldWithDefault(formData, "sms_opt_in", true),
    lesson_reminder_email_opt_in: checkboxFieldWithDefault(formData, "lesson_reminder_email_opt_in", true),
    lesson_reminder_sms_opt_in: checkboxFieldWithDefault(formData, "lesson_reminder_sms_opt_in", false),
    client_kind,
    client_status,
    is_active: isActiveFromClientStatus(client_status),
  };

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/clients/${clientId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/clients");
  revalidatePath(`/admin/clients/${clientId}`);
  redirect(`/admin/clients/${clientId}?tab=${returnTab}&ok=Client%20mis%20a%20jour`);
}

export async function updateAdminClientGroupsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const returnTab = String(formData.get("return_tab") ?? "infos").trim() || "infos";
  if (!clientId) {
    redirect("/admin/clients?error=Client%20invalide");
  }

  const groupIds = parseStringList(formData.getAll("group_ids"));

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/clients/${clientId}/groups`,
    {
      method: "PUT",
      body: JSON.stringify({
        group_ids: groupIds,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/clients");
  revalidatePath(`/admin/clients/${clientId}`);
  redirect(`/admin/clients/${clientId}?tab=${returnTab}&ok=Groupes%20mis%20a%20jour`);
}

export async function adminClientActionPlaceholder(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const actionName = String(formData.get("action_name") ?? "Action").trim();

  if (!clientId) {
    redirect("/admin/clients?error=Client%20invalide");
  }

  redirect(`/admin/clients/${clientId}?ok=${encodeURIComponent(actionName + " en preparation")}`);
}

export async function sendAdminClientPasswordAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const returnTab = String(formData.get("return_tab") ?? "infos").trim() || "infos";
  if (!clientId) {
    redirect("/admin/clients?error=Client%20invalide");
  }

  const result = await backendRequest<{ message_id: string; sent_at: string }>(
    `/api/v1/admin/clients/${clientId}/send-password-email`,
    {
      method: "POST",
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(
    `/admin/clients/${clientId}?tab=${returnTab}&ok=${encodeURIComponent(
      `Mot de passe genere et envoye (${result.data.message_id})`,
    )}`,
  );
}

export async function adminPurchasePlanForClientAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const planId = String(formData.get("plan_id") ?? "").trim();
  const returnTabRaw = String(formData.get("return_tab") ?? "fiche").trim().toLowerCase();
  const returnTab =
    returnTabRaw === "paiements" || returnTabRaw === "messages" || returnTabRaw === "infos" || returnTabRaw === "famille" || returnTabRaw === "reservations"
      ? returnTabRaw
      : "fiche";

  if (!clientId || !planId) {
    redirect("/admin/clients?error=Client%20ou%20plan%20invalide");
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/clients/${clientId}/plans/${planId}/purchase`,
    {
      method: "POST",
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/clients");
  revalidatePath(`/admin/clients/${clientId}`);
  redirect(`/admin/clients/${clientId}?tab=${returnTab}&ok=Produit%20ajoute`);
}

export async function adminOpenClientPurchaseTermsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const planId = String(formData.get("plan_id") ?? "").trim();
  const returnTabRaw = String(formData.get("return_tab") ?? "fiche").trim().toLowerCase();
  const returnTab =
    returnTabRaw === "paiements" || returnTabRaw === "messages" || returnTabRaw === "infos" || returnTabRaw === "famille" || returnTabRaw === "reservations"
      ? returnTabRaw
      : "fiche";
  const purchaseType = String(formData.get("purchase_type") ?? "FORMULA").trim().toUpperCase() || "FORMULA";
  const paymentMethodCode = parsePaymentMethodCode(String(formData.get("payment_method_code") ?? ""));
  const discountedTotalRaw = String(formData.get("discounted_total_incl_vat") ?? "").trim();
  const discountedTotal = discountedTotalRaw ? parseNonNegativeDecimal(discountedTotalRaw.replace(",", ".")) : null;

  if (!clientId || !planId) {
    redirect("/admin/clients?error=Client%20ou%20plan%20invalide");
  }
  if (!paymentMethodCode) {
    redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=Veuillez%20selectionner%20un%20moyen%20de%20reglement`);
  }
  if (discountedTotalRaw && discountedTotal === null) {
    redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=Prix%20remise%20invalide`);
  }

  const params = new URLSearchParams({
    tab: returnTab,
    purchase_modal: "terms",
    purchase_plan_id: planId,
    purchase_type: purchaseType,
    purchase_payment_method: paymentMethodCode,
  });
  if (discountedTotal !== null) {
    params.set("purchase_discounted_total", discountedTotal.toFixed(2));
  }

  redirect(`/admin/clients/${clientId}?${params.toString()}`);
}

export async function adminFinalizeClientPurchaseAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const planId = String(formData.get("plan_id") ?? "").trim();
  const planKind = String(formData.get("plan_kind") ?? "").trim().toUpperCase();
  const planName = String(formData.get("plan_name") ?? "").trim() || "Formule";
  const purchaseType = String(formData.get("purchase_type") ?? "FORMULA").trim().toUpperCase() || "FORMULA";
  const returnTabRaw = String(formData.get("return_tab") ?? "fiche").trim().toLowerCase();
  const returnTab =
    returnTabRaw === "paiements" || returnTabRaw === "messages" || returnTabRaw === "infos" || returnTabRaw === "famille" || returnTabRaw === "reservations"
      ? returnTabRaw
      : "fiche";
  const paymentMethodCode = parsePaymentMethodCode(String(formData.get("payment_method_code") ?? ""));
  const discountedTotalRaw = String(formData.get("discounted_total_incl_vat") ?? "").trim();
  const discountedTotal = discountedTotalRaw ? parseNonNegativeDecimal(discountedTotalRaw.replace(",", ".")) : null;
  const signatureChannelRaw = String(formData.get("signature_channel") ?? "NONE").trim().toUpperCase();
  const isCardOnlinePayment = paymentMethodCode === "CARD_ONLINE";
  const signatureChannel =
    isCardOnlinePayment && (signatureChannelRaw === "EMAIL" || signatureChannelRaw === "SMS") ? signatureChannelRaw : "NONE";
  const acceptedCgv = checkboxField(formData, "cgv_accepted");

  if (!clientId || !planId) {
    redirect("/admin/clients?error=Client%20ou%20plan%20invalide");
  }
  if (!paymentMethodCode) {
    redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=Moyen%20de%20paiement%20invalide`);
  }
  if (isCardOnlinePayment && signatureChannel === "NONE") {
    redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=Choisir%20un%20canal%20email%20ou%20SMS`);
  }
  if (!acceptedCgv) {
    redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=Vous%20devez%20accepter%20les%20CGV`);
  }
  if (discountedTotalRaw && discountedTotal === null) {
    redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=Prix%20remise%20invalide`);
  }

  const purchaseResult = await backendRequest<{ id: string }>(
    `/api/v1/admin/clients/${clientId}/plans/${planId}/purchase`,
    {
      method: "POST",
      body: JSON.stringify({
        payment_method_code: paymentMethodCode,
      }),
    },
    token,
  );
  if (!purchaseResult.ok) {
    redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(purchaseResult.message)}`);
  }

  const subscriptionId = purchaseResult.data.id;
  if (planKind === "SUBSCRIPTION") {
    const setupResult = await backendRequest<{ id: string }>(
      `/api/v1/admin/clients/${clientId}/subscriptions/${subscriptionId}/billing-setup`,
      {
        method: "POST",
        body: JSON.stringify({
          billing_method_code: paymentMethodCode,
        }),
      },
      token,
    );
    if (!setupResult.ok) {
      redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(setupResult.message)}`);
    }
  }

  if (isCardOnlinePayment && signatureChannel === "EMAIL") {
    const emailResult = await backendRequest<{ message_id: string }>(
      `/api/v1/admin/clients/${clientId}/subscriptions/${subscriptionId}/send-payment-email`,
      {
        method: "POST",
        body: JSON.stringify({
          payment_method_code: paymentMethodCode,
          discounted_total_incl_vat: discountedTotal !== null ? discountedTotal.toFixed(2) : null,
        }),
      },
      token,
    );
    if (!emailResult.ok) {
      redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(emailResult.message)}`);
    }
  }

  const notes: string[] = [];
  notes.push(`Nouvel achat (${purchaseType === "PRODUCT" ? "produit catalogue" : "formule de cours"}): ${planName}.`);
  notes.push(`Reglement: ${paymentMethodCode}.`);
  if (discountedTotal !== null) {
    notes.push(`Prix remise saisi: ${discountedTotal.toFixed(2)} EUR TTC.`);
  }
  notes.push("CGV acceptees sur la fiche client.");
  if (!isCardOnlinePayment) {
    notes.push("Lien de paiement: non envoye (reglement hors carte).");
  } else if (signatureChannel === "EMAIL") {
    notes.push("Lien de paiement: email envoye.");
  } else if (signatureChannel === "SMS") {
    notes.push("Lien de paiement: SMS (envoi manuel requis).");
  } else {
    notes.push("Lien de paiement: non envoye.");
  }

  await backendRequest<{ id: string }>(
    `/api/v1/admin/clients/${clientId}/notes`,
    {
      method: "POST",
      body: JSON.stringify({
        message: notes.join(" "),
      }),
    },
    token,
  );

  revalidatePath("/admin/clients");
  revalidatePath(`/admin/clients/${clientId}`);
  const channelMessage = !isCardOnlinePayment ? "paiement enregistre" : signatureChannel === "EMAIL" ? "lien email envoye" : "SMS a envoyer";
  redirect(`/admin/clients/${clientId}?tab=${returnTab}&ok=${encodeURIComponent(`Produit ajoute (${channelMessage})`)}`);
}

export async function suspendAdminClientSubscriptionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const subscriptionId = String(formData.get("subscription_id") ?? "").trim();
  const startRaw = String(formData.get("suspension_starts_at") ?? "").trim();
  const durationUnit = String(formData.get("duration_unit") ?? "DAY").trim().toUpperCase();
  const durationValue = parsePositiveInt(String(formData.get("duration_value") ?? ""));
  if (!clientId || !subscriptionId) {
    redirect("/admin/clients?error=Abonnement%20invalide");
  }
  const startsAt = parseUtcStartOfDate(startRaw);
  if (!startsAt) {
    redirect(`/admin/clients/${clientId}?tab=fiche&error=Date%20de%20debut%20de%20suspension%20invalide`);
  }
  if (!durationValue) {
    redirect(`/admin/clients/${clientId}?tab=fiche&error=Duree%20de%20suspension%20invalide`);
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/clients/${clientId}/subscriptions/${subscriptionId}/suspend`,
    {
      method: "POST",
      body: JSON.stringify({
        suspension_starts_at: startsAt,
        duration_unit: durationUnit === "MONTH" ? "MONTH" : "DAY",
        duration_value: durationValue,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/clients/${clientId}?tab=fiche&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(`/admin/clients/${clientId}?tab=fiche&ok=Suspension%20enregistree`);
}

export async function updateAdminClientSubscriptionExpiryAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const subscriptionId = String(formData.get("subscription_id") ?? "").trim();
  const endsAtRaw = String(formData.get("ends_at") ?? "").trim();
  if (!clientId || !subscriptionId) {
    redirect("/admin/clients?error=Produit%20invalide");
  }
  const endsAt = parseUtcStartOfDate(endsAtRaw);
  if (!endsAt) {
    redirect(`/admin/clients/${clientId}?tab=fiche&error=Date%20d%27expiration%20invalide`);
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/clients/${clientId}/subscriptions/${subscriptionId}/expiry`,
    {
      method: "POST",
      body: JSON.stringify({
        ends_at: endsAt,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/clients/${clientId}?tab=fiche&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(`/admin/clients/${clientId}?tab=fiche&ok=Date%20d%27expiration%20mise%20a%20jour`);
}

export async function cancelAdminClientSubscriptionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const subscriptionId = String(formData.get("subscription_id") ?? "").trim();
  const requestedRaw = String(formData.get("cancellation_requested_at") ?? "").trim();
  const immediateCancel = checkboxField(formData, "immediate_cancel");
  const confirmImmediate = checkboxField(formData, "confirm_immediate");
  if (!clientId || !subscriptionId) {
    redirect("/admin/clients?error=Abonnement%20invalide");
  }
  const requestedAt = parseUtcStartOfDate(requestedRaw);
  if (!requestedAt) {
    redirect(`/admin/clients/${clientId}?tab=fiche&error=Date%20de%20resiliation%20invalide`);
  }
  if (immediateCancel && !confirmImmediate) {
    redirect(`/admin/clients/${clientId}?tab=fiche&error=Confirmation%20obligatoire%20pour%20une%20resiliation%20immediate`);
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/clients/${clientId}/subscriptions/${subscriptionId}/cancel`,
    {
      method: "POST",
      body: JSON.stringify({
        cancellation_requested_at: requestedAt,
        immediate: immediateCancel,
        confirm_immediate: confirmImmediate,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/clients/${clientId}?tab=fiche&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(
    `/admin/clients/${clientId}?tab=fiche&ok=${
      immediateCancel ? "Resiliation%20immediate%20enregistree" : "Resiliation%20enregistree"
    }`,
  );
}

export async function setupAdminClientSubscriptionBillingAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const subscriptionId = String(formData.get("subscription_id") ?? "").trim();
  if (!clientId || !subscriptionId) {
    redirect("/admin/clients?error=Abonnement%20invalide");
  }

  const billingMethodCode = optionalField(formData, "billing_method_code");
  const paymentProviderSubscriptionRef = optionalField(formData, "payment_provider_subscription_ref");
  const paymentProviderCustomerRef = optionalField(formData, "payment_provider_customer_ref");
  const paymentProviderMandateRef = optionalField(formData, "payment_provider_mandate_ref");

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/clients/${clientId}/subscriptions/${subscriptionId}/billing-setup`,
    {
      method: "POST",
      body: JSON.stringify({
        billing_method_code: billingMethodCode,
        payment_provider_subscription_ref: paymentProviderSubscriptionRef,
        payment_provider_customer_ref: paymentProviderCustomerRef,
        payment_provider_mandate_ref: paymentProviderMandateRef,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/clients/${clientId}?tab=fiche&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(`/admin/clients/${clientId}?tab=fiche&ok=Parametres%20de%20prelevement%20mis%20a%20jour`);
}

export async function updateAdminClientManualCreditAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const creditTypeId = String(formData.get("credit_type_id") ?? "").trim();
  const creditsCountRaw = String(formData.get("credits_count") ?? "").trim();
  const creditsCount = parseNonNegativeInt(creditsCountRaw);

  if (!clientId || !creditTypeId) {
    redirect("/admin/clients?error=Type%20de%20credit%20invalide");
  }
  if (creditsCount === null) {
    redirect(`/admin/clients/${clientId}?tab=fiche&error=Nombre%20de%20credits%20invalide`);
  }

  const result = await backendRequest<{ credit_type_id: string; credits_count: number }>(
    `/api/v1/admin/clients/${clientId}/manual-credits/${creditTypeId}`,
    {
      method: "POST",
      body: JSON.stringify({
        credits_count: creditsCount,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/clients/${clientId}?tab=fiche&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(`/admin/clients/${clientId}?tab=fiche&ok=Credits%20manuels%20mis%20a%20jour`);
}

export async function createAdminClientNoteAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const message = String(formData.get("message") ?? "").trim();
  if (!clientId) {
    redirect("/admin/clients?error=Client%20invalide");
  }
  if (!message) {
    redirect(`/admin/clients/${clientId}?tab=fiche&error=Note%20vide`);
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/clients/${clientId}/notes`,
    {
      method: "POST",
      body: JSON.stringify({
        message,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/clients/${clientId}?tab=fiche&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(`/admin/clients/${clientId}?tab=fiche&ok=Note%20ajoutee`);
}

export async function refundAdminClientPaymentAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const paymentSource = String(formData.get("payment_source") ?? "").trim().toUpperCase();
  const paymentId = String(formData.get("payment_id") ?? "").trim();
  const reason = optionalField(formData, "reason");
  const returnTabRaw = String(formData.get("return_tab") ?? "").trim().toLowerCase();
  const returnTab = returnTabRaw === "factures" ? "factures" : "paiements";

  if (!clientId || !paymentSource || !paymentId) {
    redirect("/admin/clients?error=Paiement%20invalide");
  }

  const result = await backendRequest<{ source: string; payment_id: string }>(
    `/api/v1/admin/clients/${clientId}/payments/${paymentSource}/${paymentId}/refund`,
    {
      method: "POST",
      body: JSON.stringify({
        reason,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(`/admin/clients/${clientId}?tab=${returnTab}&ok=Avoir%20enregistre`);
}

export async function cancelAdminClientInvoiceAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const paymentSource = String(formData.get("payment_source") ?? "").trim().toUpperCase();
  const paymentId = String(formData.get("payment_id") ?? "").trim();
  const returnTabRaw = String(formData.get("return_tab") ?? "").trim().toLowerCase();
  const returnTab = returnTabRaw === "factures" ? "factures" : "paiements";

  if (!clientId || !paymentSource || !paymentId) {
    redirect("/admin/clients?error=Facture%20invalide");
  }

  const result = await backendRequest<{ source: string; payment_id: string }>(
    `/api/v1/admin/clients/${clientId}/payments/${paymentSource}/${paymentId}/refund`,
    {
      method: "POST",
      body: JSON.stringify({
        reason: "FACTURE_ANNULEE_PAR_ADMIN",
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(`/admin/clients/${clientId}?tab=${returnTab}&ok=Facture%20annulee`);
}

export async function createAdminClientManualTransactionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const transactionType = String(formData.get("transaction_type") ?? "").trim().toUpperCase();
  const amountRaw = String(formData.get("amount_incl_vat") ?? "").trim().replace(",", ".");
  const vatRateRaw = String(formData.get("vat_rate") ?? "20").trim().replace(",", ".");
  const occurredAtRaw = String(formData.get("occurred_at") ?? "").trim();
  const occurredAt = occurredAtRaw ? parseUtcStartOfDate(occurredAtRaw) : null;
  const amountInclVat = parseNonNegativeDecimal(amountRaw);
  const vatRate = parseNonNegativeDecimal(vatRateRaw);
  const paymentMethodCode = parsePaymentMethodCode(String(formData.get("payment_method_code") ?? ""));
  const customReference = optionalField(formData, "reference");
  const resolvedReference = customReference ?? (paymentMethodCode ? `MODE:${paymentMethodCode}` : null);

  if (!clientId) {
    redirect("/admin/clients?error=Client%20invalide");
  }
  if (!["PAYMENT", "REFUND", "CHARGE", "DISCOUNT"].includes(transactionType)) {
    redirect(`/admin/clients/${clientId}?tab=paiements&error=Type%20de%20transaction%20invalide`);
  }
  if (amountInclVat === null || amountInclVat <= 0) {
    redirect(`/admin/clients/${clientId}?tab=paiements&error=Montant%20invalide`);
  }
  if (vatRate === null || vatRate < 0 || vatRate > 100) {
    redirect(`/admin/clients/${clientId}?tab=paiements&error=Taux%20de%20TVA%20invalide`);
  }
  if (occurredAtRaw && !occurredAt) {
    redirect(`/admin/clients/${clientId}?tab=paiements&error=Date%20invalide`);
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/clients/${clientId}/manual-transactions`,
    {
      method: "POST",
      body: JSON.stringify({
        transaction_type: transactionType,
        occurred_at: occurredAt,
        label: optionalField(formData, "label"),
        description: optionalField(formData, "description"),
        category: optionalField(formData, "category"),
        reference: resolvedReference,
        student_id: optionalField(formData, "student_id"),
        amount_incl_vat: amountInclVat,
        vat_rate: vatRate,
        currency: optionalField(formData, "currency"),
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/clients/${clientId}?tab=paiements&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(`/admin/clients/${clientId}?tab=paiements&ok=Transaction%20manuelle%20ajoutee`);
}

export async function createAdminClientAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const returnTo = safeAdminReturnPath(formData, "/admin/clients");
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const firstName = String(formData.get("first_name") ?? "").trim();
  const lastName = String(formData.get("last_name") ?? "").trim();
  const residence_country = String(formData.get("residence_country") ?? "FR").trim().toUpperCase();
  const preferred_currency = String(formData.get("preferred_currency") ?? "EUR").trim().toUpperCase();
  const timezone = String(formData.get("timezone") ?? "Europe/Paris").trim();
  const address_country = String(formData.get("address_country") ?? "FR").trim().toUpperCase();
  const client_kind_raw = String(formData.get("client_kind") ?? "ADULT").trim().toUpperCase();
  const client_kind = client_kind_raw === "CHILD" ? "CHILD" : "ADULT";
  const client_status = String(formData.get("client_status") ?? "").trim().toUpperCase() || "ACTIVE";
  const birthDateRaw = String(formData.get("birth_date") ?? "").trim();
  const addressLine = optionalField(formData, "address_line");
  const city = optionalField(formData, "city");

  if (!firstName || !lastName || !address_country) {
    redirect(
      appendQueryMessage(
        returnTo,
        "error",
        "Prenom, nom et pays de taxation sont obligatoires",
      ),
    );
  }

  const payload = {
    email: email || null,
    client_kind,
    first_name: firstName,
    last_name: lastName,
    address_line: addressLine,
    postal_code: optionalField(formData, "postal_code"),
    city,
    address_country,
    mobile_phone_1: optionalField(formData, "mobile_phone_1"),
    mobile_phone_2: optionalField(formData, "mobile_phone_2"),
    home_phone: optionalField(formData, "home_phone"),
    phone: optionalField(formData, "mobile_phone_1"),
    birth_date: birthDateRaw || null,
    important_info: optionalField(formData, "important_info"),
    private_note: optionalField(formData, "private_note"),
    residence_country,
    preferred_currency,
    timezone,
    portal_contact_visible: checkboxFieldWithDefault(formData, "portal_contact_visible", true),
    email_opt_in: checkboxFieldWithDefault(formData, "email_opt_in", true),
    sms_opt_in: checkboxFieldWithDefault(formData, "sms_opt_in", true),
    lesson_reminder_email_opt_in: checkboxFieldWithDefault(formData, "lesson_reminder_email_opt_in", true),
    lesson_reminder_sms_opt_in: checkboxFieldWithDefault(formData, "lesson_reminder_sms_opt_in", false),
    client_status,
    is_active: isActiveFromClientStatus(client_status),
  };

  const result = await backendRequest<{ id: string }>(
    "/api/v1/admin/clients",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  const createdClientId = result.data.id;

  if (client_kind === "CHILD") {
    const relationshipLabel = optionalField(formData, "relationship_label");
    const existingAdultId = String(formData.get("existing_adult_id") ?? "").trim();
    const billingForExistingAdult = checkboxField(formData, "existing_adult_billing_recipient");
    const newAdultEmail = String(formData.get("adult_email") ?? "").trim().toLowerCase();
    const newAdultFirstName = String(formData.get("adult_first_name") ?? "").trim();
    const newAdultLastName = String(formData.get("adult_last_name") ?? "").trim();
    const newAdultCountry = String(formData.get("adult_residence_country") ?? "FR").trim().toUpperCase();
    const newAdultCurrency = String(formData.get("adult_preferred_currency") ?? "EUR").trim().toUpperCase();
    const newAdultTimezone = String(formData.get("adult_timezone") ?? "Europe/Paris").trim();
    const newAdultAddressCountry = String(formData.get("adult_address_country") ?? "FR").trim().toUpperCase();
    const newAdultStatus = String(formData.get("adult_client_status") ?? "").trim().toUpperCase() || "ACTIVE";
    const newAdultBillingRecipient = checkboxField(formData, "new_adult_billing_recipient");

    const adultsToLink: Array<{ adultId: string; isBillingRecipient: boolean }> = [];

    if (existingAdultId) {
      adultsToLink.push({ adultId: existingAdultId, isBillingRecipient: billingForExistingAdult });
    }

    if (newAdultEmail || newAdultFirstName || newAdultLastName) {
      if (!newAdultFirstName || !newAdultLastName) {
        redirect(`/admin/clients/${createdClientId}?tab=famille&error=Prenom%20et%20nom%20adulte%20obligatoires`);
      }
      const newAdultAddressLine = optionalField(formData, "adult_address_line");
      const newAdultCity = optionalField(formData, "adult_city");

      const createAdultResult = await backendRequest<{ id: string }>(
        "/api/v1/admin/clients",
        {
          method: "POST",
          body: JSON.stringify({
            email: newAdultEmail || null,
            client_kind: "ADULT",
            first_name: newAdultFirstName,
            last_name: newAdultLastName,
            address_line: newAdultAddressLine,
            postal_code: optionalField(formData, "adult_postal_code"),
            city: newAdultCity,
            address_country: newAdultAddressCountry,
            mobile_phone_1: optionalField(formData, "adult_mobile_phone_1"),
            mobile_phone_2: optionalField(formData, "adult_mobile_phone_2"),
            home_phone: optionalField(formData, "adult_home_phone"),
            phone: optionalField(formData, "adult_mobile_phone_1"),
            residence_country: newAdultCountry,
            preferred_currency: newAdultCurrency,
            timezone: newAdultTimezone,
            client_status: newAdultStatus,
            is_active: isActiveFromClientStatus(newAdultStatus),
          }),
        },
        token,
      );

      if (!createAdultResult.ok) {
        redirect(`/admin/clients/${createdClientId}?tab=famille&error=${encodeURIComponent(createAdultResult.message)}`);
      }

      adultsToLink.push({ adultId: createAdultResult.data.id, isBillingRecipient: newAdultBillingRecipient });
    }

    for (let index = 0; index < adultsToLink.length; index += 1) {
      const item = adultsToLink[index];
      const linkResult = await backendRequest<{ id: string }>(
        "/api/v1/admin/clients/family/links",
        {
          method: "POST",
          body: JSON.stringify({
            adult_client_id: item.adultId,
            child_client_id: createdClientId,
            relationship_label: relationshipLabel,
            is_billing_recipient: item.isBillingRecipient || (index === 0 && !adultsToLink.some((row) => row.isBillingRecipient)),
          }),
        },
        token,
      );
      if (!linkResult.ok) {
        redirect(`/admin/clients/${createdClientId}?tab=famille&error=${encodeURIComponent(linkResult.message)}`);
      }
    }
  }

  revalidatePath("/admin/clients");
  revalidatePath(`/admin/clients/${createdClientId}`);
  redirect(`/admin/clients/${createdClientId}?tab=famille&ok=Compte%20client%20cree%20%28mot%20de%20passe%20a%20envoyer%20depuis%20la%20fiche%29`);
}

export async function createChildForAdultAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const adultClientId = String(formData.get("adult_client_id") ?? "").trim();
  if (!adultClientId) {
    redirect("/admin/clients?error=Adulte%20invalide");
  }

  const email = String(formData.get("child_email") ?? "").trim().toLowerCase();
  const firstName = String(formData.get("child_first_name") ?? "").trim();
  const lastName = String(formData.get("child_last_name") ?? "").trim();
  const residence_country = String(formData.get("child_residence_country") ?? "FR").trim().toUpperCase();
  const preferred_currency = String(formData.get("child_preferred_currency") ?? "EUR").trim().toUpperCase();
  const timezone = String(formData.get("child_timezone") ?? "Europe/Paris").trim();
  const address_country = String(formData.get("child_address_country") ?? "FR").trim().toUpperCase();
  const birthDateRaw = String(formData.get("child_birth_date") ?? "").trim();
  const relationship_label = optionalField(formData, "relationship_label");
  const billingRecipient = checkboxField(formData, "is_billing_recipient");
  const childStatus = String(formData.get("child_client_status") ?? "").trim().toUpperCase() || "ACTIVE";

  if (!firstName || !lastName || !residence_country || !preferred_currency || !timezone || !address_country) {
    redirect(`/admin/clients/${adultClientId}?tab=famille&error=Informations%20enfant%20incompletes`);
  }

  const createResult = await backendRequest<{ id: string }>(
    "/api/v1/admin/clients",
    {
      method: "POST",
      body: JSON.stringify({
        email: email || null,
        client_kind: "CHILD",
        first_name: firstName,
        last_name: lastName,
        address_line: optionalField(formData, "child_address_line"),
        postal_code: optionalField(formData, "child_postal_code"),
        city: optionalField(formData, "child_city"),
        address_country,
        mobile_phone_1: optionalField(formData, "child_mobile_phone_1"),
        mobile_phone_2: optionalField(formData, "child_mobile_phone_2"),
        home_phone: optionalField(formData, "child_home_phone"),
        phone: optionalField(formData, "child_mobile_phone_1"),
        birth_date: birthDateRaw || null,
        important_info: optionalField(formData, "child_important_info"),
        residence_country,
        preferred_currency,
        timezone,
        client_status: childStatus,
        is_active: isActiveFromClientStatus(childStatus),
      }),
    },
    token,
  );

  if (!createResult.ok) {
    redirect(`/admin/clients/${adultClientId}?tab=famille&error=${encodeURIComponent(createResult.message)}`);
  }

  const childClientId = createResult.data.id;
  const linkResult = await backendRequest<{ id: string }>(
    "/api/v1/admin/clients/family/links",
    {
      method: "POST",
      body: JSON.stringify({
        adult_client_id: adultClientId,
        child_client_id: childClientId,
        relationship_label,
        is_billing_recipient: billingRecipient,
      }),
    },
    token,
  );

  if (!linkResult.ok) {
    redirect(
      `/admin/clients/${adultClientId}?tab=famille&error=${encodeURIComponent(
        `Enfant cree mais rattachement impossible: ${linkResult.message}`,
      )}`,
    );
  }

  revalidatePath("/admin/clients");
  revalidatePath(`/admin/clients/${adultClientId}`);
  revalidatePath(`/admin/clients/${childClientId}`);
  redirect(
    `/admin/clients/${adultClientId}?tab=famille&ok=Enfant%20cree%20et%20rattache%20%28mot%20de%20passe%20a%20envoyer%20depuis%20la%20fiche%29`,
  );
}

export async function createAdultForChildAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const childClientId = String(formData.get("child_client_id") ?? "").trim();
  if (!childClientId) {
    redirect("/admin/clients?error=Enfant%20invalide");
  }

  const email = String(formData.get("adult_email") ?? "").trim().toLowerCase();
  const firstName = String(formData.get("adult_first_name") ?? "").trim();
  const lastName = String(formData.get("adult_last_name") ?? "").trim();
  const residence_country = String(formData.get("adult_residence_country") ?? "FR").trim().toUpperCase();
  const preferred_currency = String(formData.get("adult_preferred_currency") ?? "EUR").trim().toUpperCase();
  const timezone = String(formData.get("adult_timezone") ?? "Europe/Paris").trim();
  const address_country = String(formData.get("adult_address_country") ?? "FR").trim().toUpperCase();
  const adultStatus = String(formData.get("adult_client_status") ?? "").trim().toUpperCase() || "ACTIVE";
  const relationship_label = optionalField(formData, "relationship_label");
  const adultAddressLine = optionalField(formData, "adult_address_line");
  const adultCity = optionalField(formData, "adult_city");

  if (!firstName || !lastName || !address_country) {
    redirect(`/admin/clients/${childClientId}?tab=famille&error=Informations%20adulte%20incompletes`);
  }

  const createResult = await backendRequest<{ id: string }>(
    "/api/v1/admin/clients",
    {
      method: "POST",
      body: JSON.stringify({
        email: email || null,
        client_kind: "ADULT",
        first_name: firstName,
        last_name: lastName,
        address_line: adultAddressLine,
        postal_code: optionalField(formData, "adult_postal_code"),
        city: adultCity,
        address_country,
        mobile_phone_1: optionalField(formData, "adult_mobile_phone_1"),
        mobile_phone_2: optionalField(formData, "adult_mobile_phone_2"),
        home_phone: optionalField(formData, "adult_home_phone"),
        phone: optionalField(formData, "adult_mobile_phone_1"),
        residence_country,
        preferred_currency,
        timezone,
        client_status: adultStatus,
        is_active: isActiveFromClientStatus(adultStatus),
      }),
    },
    token,
  );

  if (!createResult.ok) {
    redirect(`/admin/clients/${childClientId}?tab=famille&error=${encodeURIComponent(createResult.message)}`);
  }

  const adultClientId = createResult.data.id;
  const linkResult = await backendRequest<{ id: string }>(
    "/api/v1/admin/clients/family/links",
    {
      method: "POST",
      body: JSON.stringify({
        adult_client_id: adultClientId,
        child_client_id: childClientId,
        relationship_label,
        is_billing_recipient: checkboxField(formData, "is_billing_recipient"),
      }),
    },
    token,
  );

  if (!linkResult.ok) {
    redirect(
      `/admin/clients/${childClientId}?tab=famille&error=${encodeURIComponent(
        `Adulte cree mais rattachement impossible: ${linkResult.message}`,
      )}`,
    );
  }

  revalidatePath("/admin/clients");
  revalidatePath(`/admin/clients/${childClientId}`);
  revalidatePath(`/admin/clients/${adultClientId}`);
  redirect(
    `/admin/clients/${childClientId}?tab=famille&ok=Adulte%20cree%20et%20rattache%20%28mot%20de%20passe%20a%20envoyer%20depuis%20la%20fiche%29`,
  );
}

export async function linkExistingFamilyMembersAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const adultClientId = String(formData.get("adult_client_id") ?? "").trim();
  const childClientId = String(formData.get("child_client_id") ?? "").trim();
  const returnClientId = String(formData.get("return_client_id") ?? "").trim() || adultClientId || childClientId;
  const relationship_label = optionalField(formData, "relationship_label");
  const isBillingRecipient = checkboxField(formData, "is_billing_recipient");

  if (!adultClientId || !childClientId || !returnClientId) {
    redirect("/admin/clients?error=Rattachement%20familial%20invalide");
  }

  const result = await backendRequest<{ id: string }>(
    "/api/v1/admin/clients/family/links",
    {
      method: "POST",
      body: JSON.stringify({
        adult_client_id: adultClientId,
        child_client_id: childClientId,
        relationship_label,
        is_billing_recipient: isBillingRecipient,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/clients/${returnClientId}?tab=famille&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath(`/admin/clients/${returnClientId}`);
  revalidatePath(`/admin/clients/${adultClientId}`);
  revalidatePath(`/admin/clients/${childClientId}`);
  redirect(`/admin/clients/${returnClientId}?tab=famille&ok=Membres%20famille%20rattaches`);
}

export async function setFamilyBillingRecipientAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const linkId = String(formData.get("link_id") ?? "").trim();
  const returnClientId = String(formData.get("return_client_id") ?? "").trim();
  if (!linkId || !returnClientId) {
    redirect("/admin/clients?error=Destinataire%20facture%20invalide");
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/clients/family/links/${linkId}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        is_billing_recipient: true,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/clients/${returnClientId}?tab=famille&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath(`/admin/clients/${returnClientId}`);
  redirect(`/admin/clients/${returnClientId}?tab=famille&ok=Destinataire%20facture%20mis%20a%20jour`);
}

export async function unlinkFamilyMembersAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const linkId = String(formData.get("link_id") ?? "").trim();
  const returnClientId = String(formData.get("return_client_id") ?? "").trim();
  if (!linkId || !returnClientId) {
    redirect("/admin/clients?error=Lien%20familial%20invalide");
  }

  const result = await backendRequest<Record<string, never>>(
    `/api/v1/admin/clients/family/links/${linkId}`,
    {
      method: "DELETE",
    },
    token,
  );

  if (!result.ok && result.status !== 204) {
    redirect(`/admin/clients/${returnClientId}?tab=famille&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath(`/admin/clients/${returnClientId}`);
  redirect(`/admin/clients/${returnClientId}?tab=famille&ok=Lien%20familial%20supprime`);
}

export async function bulkAdminClientsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const returnTo = safeAdminReturnPath(formData, "/admin/clients");
  const action = String(formData.get("bulk_action") ?? "").trim().toUpperCase();
  const selectionScopeRaw = String(formData.get("selection_scope") ?? "PAGE").trim().toUpperCase();
  const selectionScope = selectionScopeRaw === "FILTERED" ? "FILTERED" : "PAGE";
  const clientIds = parseStringList(formData.getAll("client_ids"));
  const filteredClientIds = parseStringList(formData.getAll("filtered_client_ids"));
  const targetStatus = String(formData.get("target_status") ?? "").trim().toUpperCase();
  const groupId = String(formData.get("group_id") ?? "").trim();
  const filterSearch = optionalField(formData, "filter_search");
  const filterStatusRaw = String(formData.get("filter_status") ?? "").trim().toUpperCase();
  const filterStatus = filterStatusRaw && filterStatusRaw !== "ALL" ? filterStatusRaw : null;
  const filterGroupId = String(formData.get("filter_group_id") ?? "").trim();
  const filterIncludeArchived = String(formData.get("filter_include_archived") ?? "").trim().toLowerCase() === "true";
  const filterActiveOnly = String(formData.get("filter_active_only") ?? "").trim().toLowerCase() === "true";

  if (selectionScope === "PAGE" && clientIds.length === 0) {
    redirect(appendQueryMessage(returnTo, "error", "Aucun adherent selectionne"));
  }

  if (action === "EXPORT") {
    const exportIds = selectionScope === "FILTERED" ? filteredClientIds : clientIds;
    if (exportIds.length === 0) {
      redirect(appendQueryMessage(returnTo, "error", "Aucun adherent selectionne pour export"));
    }
    const query = new URLSearchParams();
    for (const clientId of exportIds) {
      query.append("client_ids", clientId);
    }
    redirect(`/admin/clients/export?${query.toString()}`);
  }

  const payload: Record<string, unknown> = {
    action,
    client_ids: selectionScope === "PAGE" ? clientIds : [],
    selection_scope: selectionScope,
    filter_search: filterSearch,
    filter_status: filterStatus,
    filter_group_id: filterGroupId || null,
    filter_include_archived: filterIncludeArchived,
    filter_active_only: filterActiveOnly,
  };

  if (action === "UPDATE_STATUS") {
    if (!targetStatus) {
      redirect(appendQueryMessage(returnTo, "error", "Statut cible obligatoire"));
    }
    payload.target_status = targetStatus;
  }

  if (action === "ASSIGN_GROUP") {
    if (!groupId) {
      redirect(appendQueryMessage(returnTo, "error", "Groupe obligatoire"));
    }
    payload.group_id = groupId;
  }

  const result = await backendRequest<{ processed_count: number; skipped_count: number; message: string }>(
    "/api/v1/admin/clients/bulk",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/clients");
  redirect(appendQueryMessage(returnTo, "ok", result.data.message));
}

export async function createAdminClientGroupAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const returnTo = safeAdminReturnPath(formData, "/admin/clients?view=groups");
  const name = String(formData.get("name") ?? "").trim();
  const code = String(formData.get("code") ?? "").trim();
  const active = checkboxField(formData, "active");

  if (!name) {
    redirect(appendQueryMessage(returnTo, "error", "Nom de groupe obligatoire"));
  }

  const result = await backendRequest<{ id: string }>(
    "/api/v1/admin/clients/groups",
    {
      method: "POST",
      body: JSON.stringify({
        name,
        code: code || null,
        active,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/clients");
  redirect(appendQueryMessage(returnTo, "ok", "Groupe cree"));
}

export async function createAdminCollaboratorAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const first_name = String(formData.get("first_name") ?? "").trim();
  const last_name = String(formData.get("last_name") ?? "").trim();
  const payout_currency = String(formData.get("payout_currency") ?? "EUR").trim().toUpperCase();

  if (!email || !first_name || !last_name) {
    redirect("/admin/professors?error=Email%2C%20prenom%20et%20nom%20sont%20obligatoires");
  }

  const permissions = parseProfessorPermissions(formData);
  permissions.can_view_planning = true;
  permissions.can_edit_planning = true;

  const payload = {
    email,
    first_name,
    last_name,
    phone: optionalField(formData, "phone"),
    siret: optionalField(formData, "siret"),
    iban: optionalField(formData, "iban"),
    address_line: optionalField(formData, "address_line"),
    zoom_link: optionalField(formData, "zoom_link"),
    spoken_languages: parseStringList(formData.getAll("spoken_languages")),
    payout_currency,
    is_coach: checkboxField(formData, "is_coach"),
    is_admin: checkboxField(formData, "is_admin"),
    daily_schedule_email_enabled: checkboxField(formData, "daily_schedule_email_enabled"),
    daily_schedule_email_time: String(formData.get("daily_schedule_email_time") ?? "07:00").trim() || "07:00",
    daily_schedule_skip_if_no_course: checkboxFieldWithDefault(formData, "daily_schedule_skip_if_no_course", true),
    permissions,
  };

  const result = await backendRequest<AdminProfessorUpdateResult>(
    "/api/v1/admin/collaborators",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/professors?error=${encodeURIComponent(result.message)}`);
  }

  const created = result.data.professor;
  revalidatePath("/admin/professors");
  revalidatePath(`/admin/professors/${created.id}`);
  redirect("/admin/professors?ok=Collaborateur%20cree%20et%20email%20identifiants%20envoye");
}

export async function uploadAdminCollaboratorContractAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const professorId = String(formData.get("professor_id") ?? "").trim();
  const returnTabRaw = String(formData.get("return_tab") ?? "profil").trim();
  const returnTab = returnTabRaw === "droits" || returnTabRaw === "tarifs" || returnTabRaw === "planning" ? returnTabRaw : "profil";

  if (!professorId) {
    redirect("/admin/professors?error=Collaborateur%20invalide");
  }

  const returnTo = `/admin/professors/${professorId}?tab=${returnTab}`;
  const rawFile = formData.get("contract_file");
  if (!(rawFile instanceof File) || rawFile.size <= 0) {
    redirect(appendQueryMessage(returnTo, "error", "Selectionnez un PDF a importer"));
  }
  if (!rawFile.name.toLowerCase().endsWith(".pdf")) {
    redirect(appendQueryMessage(returnTo, "error", "Le contrat doit etre un fichier PDF"));
  }

  const uploadPayload = new FormData();
  uploadPayload.set("file", rawFile, rawFile.name);

  const result = await backendRequest<AdminProfessorContractOut>(
    `/api/v1/admin/collaborators/${professorId}/contract`,
    {
      method: "POST",
      body: uploadPayload,
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/professors");
  revalidatePath(`/admin/professors/${professorId}`);
  redirect(appendQueryMessage(returnTo, "ok", "Contrat collaborateur importe"));
}

export async function deleteAdminCollaboratorContractAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const professorId = String(formData.get("professor_id") ?? "").trim();
  const returnTabRaw = String(formData.get("return_tab") ?? "profil").trim();
  const returnTab = returnTabRaw === "droits" || returnTabRaw === "tarifs" || returnTabRaw === "planning" ? returnTabRaw : "profil";

  if (!professorId) {
    redirect("/admin/professors?error=Collaborateur%20invalide");
  }

  const returnTo = `/admin/professors/${professorId}?tab=${returnTab}`;
  const result = await backendRequest<AdminProfessorContractDeleteOut>(
    `/api/v1/admin/collaborators/${professorId}/contract`,
    {
      method: "DELETE",
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/professors");
  revalidatePath(`/admin/professors/${professorId}`);
  redirect(appendQueryMessage(returnTo, "ok", "Contrat collaborateur supprime"));
}

export async function sendAdminCollaboratorsMessageAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const returnTo = safeAdminReturnPath(formData, "/admin/professors");
  const collaboratorIds = parseStringList(formData.getAll("collaborator_ids"));
  const subject = String(formData.get("subject") ?? "").trim();
  const body = String(formData.get("body") ?? "").trim();
  const bodyFormatRaw = String(formData.get("body_format") ?? "TEXT").trim().toUpperCase();
  const bodyFormat = bodyFormatRaw === "HTML" ? "HTML" : "TEXT";

  if (collaboratorIds.length === 0) {
    redirect(appendQueryMessage(returnTo, "error", "Selectionnez au moins un collaborateur"));
  }
  if (!subject || !body) {
    redirect(appendQueryMessage(returnTo, "error", "Sujet et message obligatoires"));
  }

  const result = await backendRequest<{ requested_count: number; sent_count: number; skipped_count: number }>(
    "/api/v1/admin/collaborators/messages",
    {
      method: "POST",
      body: JSON.stringify({
        collaborator_ids: collaboratorIds,
        subject,
        body,
        body_format: bodyFormat,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/professors");
  redirect(
    appendQueryMessage(
      returnTo,
      "ok",
      `Message envoye: ${result.data.sent_count}/${result.data.requested_count} collaborateurs`,
    ),
  );
}

export async function updateAdminCollaboratorProfileAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const professorId = String(formData.get("professor_id") ?? "").trim();
  const returnTab = String(formData.get("return_tab") ?? "profil").trim() || "profil";
  if (!professorId) {
    redirect("/admin/professors?error=Collaborateur%20invalide");
  }

  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const first_name = String(formData.get("first_name") ?? "").trim();
  const last_name = String(formData.get("last_name") ?? "").trim();

  if (!email || !first_name || !last_name) {
    redirect(`/admin/professors/${professorId}?tab=${returnTab}&error=Email%2C%20prenom%20et%20nom%20sont%20obligatoires`);
  }

  const activeRaw = String(formData.get("active") ?? "").trim();
  const payload: Record<string, unknown> = {
    email,
    first_name,
    last_name,
    phone: optionalField(formData, "phone"),
    siret: optionalField(formData, "siret"),
    iban: optionalField(formData, "iban"),
    address_line: optionalField(formData, "address_line"),
    zoom_link: optionalField(formData, "zoom_link"),
    spoken_languages: parseStringList(formData.getAll("spoken_languages")),
    payout_currency: String(formData.get("payout_currency") ?? "EUR").trim().toUpperCase(),
    is_coach: checkboxField(formData, "is_coach"),
    is_admin: checkboxField(formData, "is_admin"),
    daily_schedule_email_enabled: checkboxField(formData, "daily_schedule_email_enabled"),
    daily_schedule_email_time: String(formData.get("daily_schedule_email_time") ?? "07:00").trim() || "07:00",
    daily_schedule_skip_if_no_course: checkboxField(formData, "daily_schedule_skip_if_no_course"),
  };

  if (activeRaw === "true" || activeRaw === "false") {
    payload.active = activeRaw === "true";
  }

  const password = String(formData.get("password") ?? "");
  if (password.trim()) {
    payload.password = password;
  }

  const result = await backendRequest<AdminProfessorUpdateResult>(
    `/api/v1/admin/collaborators/${professorId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/professors/${professorId}?tab=${returnTab}&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/professors");
  revalidatePath(`/admin/professors/${professorId}`);

  if (result.data.activation_email_sent) {
    redirect(
      `/admin/professors/${professorId}?tab=${returnTab}&ok=${encodeURIComponent(
        `Collaborateur active. Email d'activation envoye (${result.data.activation_email_message_id ?? "id n/a"})`,
      )}`,
    );
  }

  redirect(`/admin/professors/${professorId}?tab=${returnTab}&ok=Fiche%20collaborateur%20mise%20a%20jour`);
}

export async function updateAdminCollaboratorPermissionsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const professorId = String(formData.get("professor_id") ?? "").trim();
  if (!professorId) {
    redirect("/admin/professors?error=Collaborateur%20invalide");
  }

  const payload = parseProfessorPermissions(formData);
  const isAdmin = checkboxField(formData, "is_admin");

  const result = await backendRequest<ProfessorPermissionOut>(
    `/api/v1/admin/collaborators/${professorId}/permissions`,
    {
      method: "PUT",
      body: JSON.stringify({ ...payload, is_admin: isAdmin }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/professors/${professorId}?tab=droits&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/professors");
  revalidatePath(`/admin/professors/${professorId}`);
  redirect(`/admin/professors/${professorId}?tab=droits&ok=Droits%20mis%20a%20jour`);
}

export async function updateAdminCollaboratorRatesAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const professorId = String(formData.get("professor_id") ?? "").trim();
  if (!professorId) {
    redirect("/admin/professors?error=Collaborateur%20invalide");
  }

  const currency = String(formData.get("currency_code") ?? "").trim().toUpperCase() || null;
  const effectiveFrom = String(formData.get("effective_from") ?? "").trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(effectiveFrom)) {
    redirect(`/admin/professors/${professorId}?tab=tarifs&error=Date%20d%27effet%20invalide`);
  }

  const rates: Array<{
    course_type_id: string | null;
    hourly_rate: number | null;
    rules: Array<{ min_students: number; max_students: number | null; hourly_rate: number }>;
    currency_code: string | null;
  }> = [];

  for (const [key, value] of formData.entries()) {
    if (!key.startsWith("rate_")) {
      continue;
    }

    const courseTypeToken = key.slice("rate_".length).trim();
    const rateRaw = String(value ?? "").trim();
    if (!courseTypeToken || !rateRaw) {
      continue;
    }

    let hourlyRate: number | null = null;
    let rules: Array<{ min_students: number; max_students: number | null; hourly_rate: number }> = [];
    if (rateRaw.includes(":")) {
      const parsedRules = parseHeadcountRules(rateRaw);
      if (parsedRules === null) {
        redirect(
          `/admin/professors/${professorId}?tab=tarifs&error=Regle%20de%20taux%20invalide%20pour%20${encodeURIComponent(courseTypeToken)}`,
        );
      }
      rules = parsedRules;
    } else {
      hourlyRate = parseNonNegativeDecimal(rateRaw.replace(",", "."));
      if (hourlyRate === null) {
        redirect(
          `/admin/professors/${professorId}?tab=tarifs&error=Taux%20horaire%20invalide%20pour%20${encodeURIComponent(courseTypeToken)}`,
        );
      }
    }

    const courseTypeId = courseTypeToken === "GLOBAL" ? null : courseTypeToken;
    rates.push({
      course_type_id: courseTypeId,
      hourly_rate: hourlyRate,
      rules,
      currency_code: currency,
    });
  }

  const result = await backendRequest<AdminProfessorRateOut[]>(
    `/api/v1/admin/collaborators/${professorId}/rates`,
    {
      method: "PUT",
      body: JSON.stringify({ rates, effective_from: effectiveFrom }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/professors/${professorId}?tab=tarifs&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/professors");
  revalidatePath(`/admin/professors/${professorId}`);
  redirect(`/admin/professors/${professorId}?tab=tarifs&ok=Taux%20horaires%20mis%20a%20jour`);
}

export async function upsertAdminCollaboratorContractGridAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const professorId = String(formData.get("professor_id") ?? "").trim();
  if (!professorId) {
    redirect("/admin/professors?error=Collaborateur%20invalide");
  }

  const gridId = String(formData.get("grid_id") ?? "").trim();
  const validFrom = String(formData.get("valid_from") ?? "").trim();
  const validTo = String(formData.get("valid_to") ?? "").trim();
  const locationCode = parseProfessorContractLocationCode(String(formData.get("location_code") ?? ""));
  const notes = optionalField(formData, "notes");
  const cloneFromGridIdRaw = String(formData.get("clone_from_grid_id") ?? "").trim();

  if (!/^\d{4}-\d{2}-\d{2}$/.test(validFrom)) {
    redirect(`/admin/professors/${professorId}?tab=tarifs&error=Date%20de%20prise%20d%27effet%20invalide`);
  }
  if (validTo && !/^\d{4}-\d{2}-\d{2}$/.test(validTo)) {
    redirect(`/admin/professors/${professorId}?tab=tarifs&error=Date%20de%20fin%20invalide`);
  }

  const lines: Array<{
    course_type_id: string;
    default_hourly_rate: number | null;
    rules: Array<{ min_students: number; max_students: number | null; hourly_rate: number }>;
  }> = [];

  for (let index = 0; index < 16; index += 1) {
    const courseTypeId = String(formData.get(`line_course_type_id_${index}`) ?? "").trim();
    const defaultRateRaw = String(formData.get(`line_default_rate_${index}`) ?? "").trim().replace(",", ".");
    const rulesRaw = String(formData.get(`line_rules_${index}`) ?? "").trim();

    if (!courseTypeId && !defaultRateRaw && !rulesRaw) {
      continue;
    }
    if (!courseTypeId) {
      redirect(`/admin/professors/${professorId}?tab=tarifs&error=Ligne%20${index + 1}%20sans%20activite`);
    }

    const defaultRate = defaultRateRaw ? parseNonNegativeDecimal(defaultRateRaw) : null;
    if (defaultRateRaw && defaultRate === null) {
      redirect(`/admin/professors/${professorId}?tab=tarifs&error=Taux%20default%20invalide%20sur%20ligne%20${index + 1}`);
    }

    const rules = parseHeadcountRules(rulesRaw);
    if (rules === null) {
      redirect(`/admin/professors/${professorId}?tab=tarifs&error=Format%20regles%20effectif%20invalide%20sur%20ligne%20${index + 1}`);
    }

    lines.push({
      course_type_id: courseTypeId,
      default_hourly_rate: defaultRate,
      rules,
    });
  }

  if (lines.length === 0 && !cloneFromGridIdRaw) {
    redirect(`/admin/professors/${professorId}?tab=tarifs&error=Ajoutez%20au%20moins%20une%20ligne%20de%20grille`);
  }

  const payload = {
    valid_from: validFrom,
    valid_to: validTo || null,
    location_code: locationCode,
    notes,
    clone_from_grid_id: cloneFromGridIdRaw || null,
    lines,
  };

  const endpoint = gridId
    ? `/api/v1/admin/collaborators/${professorId}/contract-grids/${gridId}`
    : `/api/v1/admin/collaborators/${professorId}/contract-grids`;
  const method = gridId ? "PUT" : "POST";

  const result = await backendRequest<AdminProfessorContractGridOut>(
    endpoint,
    {
      method,
      body: JSON.stringify(payload),
    },
    token,
  );
  if (!result.ok) {
    redirect(`/admin/professors/${professorId}?tab=tarifs&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/professors");
  revalidatePath(`/admin/professors/${professorId}`);
  const message = gridId ? "Grille contractuelle mise a jour" : "Nouvelle grille contractuelle creee";
  redirect(`/admin/professors/${professorId}?tab=tarifs&ok=${encodeURIComponent(message)}`);
}

type FormulaRestrictionPeriod = "DAY" | "WEEK" | "MONTH" | "ROLLING_MONTH" | "SEMESTER";

function parseFormulaRestrictionPeriod(raw: string): FormulaRestrictionPeriod | null {
  const normalized = raw.trim().toUpperCase();
  if (normalized === "DAY" || normalized === "WEEK" || normalized === "MONTH" || normalized === "ROLLING_MONTH" || normalized === "SEMESTER") {
    return normalized;
  }
  return null;
}

function parseFormulaRestrictions(formData: FormData): Array<{
  period: FormulaRestrictionPeriod;
  max_bookings: number;
  course_type_ids: string[];
}> {
  const restrictions: Array<{
    period: FormulaRestrictionPeriod;
    max_bookings: number;
    course_type_ids: string[];
  }> = [];

  const rowKeys = parseStringList(formData.getAll("restriction_row_key"));
  for (const rowKey of rowKeys) {
    const period = parseFormulaRestrictionPeriod(String(formData.get(`restriction_period_${rowKey}`) ?? ""));
    const maxBookings = parsePositiveInt(String(formData.get(`restriction_max_${rowKey}`) ?? ""));
    if (!period || maxBookings === null) {
      continue;
    }

    const courseTypeIds = parseStringList(formData.getAll(`restriction_course_type_ids_${rowKey}`));
    restrictions.push({
      period,
      max_bookings: maxBookings,
      course_type_ids: courseTypeIds,
    });
  }

  return restrictions;
}

function parseFormulaCreditGrants(formData: FormData): Array<{ credit_type_id: string; credits_count: number }> {
  const grants: Array<{ credit_type_id: string; credits_count: number }> = [];
  const rowKeys = parseStringList(formData.getAll("credit_grant_row_key"));

  for (const rowKey of rowKeys) {
    const creditTypeId = String(formData.get(`credit_grant_credit_type_id_${rowKey}`) ?? "").trim();
    const creditsCountRaw = String(formData.get(`credit_grant_credits_count_${rowKey}`) ?? "").trim();
    const creditsCount = parsePositiveInt(creditsCountRaw);

    if (!creditTypeId && creditsCount === null) {
      continue;
    }
    if (!creditTypeId) {
      throw new Error("Chaque ligne de credit doit avoir un type de credit");
    }
    if (creditsCount === null) {
      throw new Error("Chaque ligne de credit doit avoir un nombre de credits positif");
    }

    grants.push({
      credit_type_id: creditTypeId,
      credits_count: creditsCount,
    });
  }

  return grants;
}

function parseFormulaPayload(formData: FormData): Record<string, unknown> {
  const name = String(formData.get("name") ?? "").trim();
  const kindRaw = String(formData.get("kind") ?? "PACK").trim().toUpperCase();
  const kind = kindRaw === "SUBSCRIPTION" ? "SUBSCRIPTION" : kindRaw === "FORFAIT" ? "FORFAIT" : "PACK";
  const priceTaxModeRaw = String(formData.get("price_tax_mode") ?? "HT").trim().toUpperCase();
  const priceTaxMode = priceTaxModeRaw === "TTC" ? "TTC" : "HT";
  const creditGrantsRelationRaw = String(formData.get("credit_grants_relation") ?? "OR").trim().toUpperCase();
  const creditGrantsRelation = creditGrantsRelationRaw === "AND" ? "AND" : "OR";
  const price = parseNonNegativeDecimal(
    String(formData.get("monthly_price_value") ?? formData.get("monthly_price_excl_vat") ?? ""),
  );
  const currency = String(formData.get("currency_code") ?? "EUR").trim().toUpperCase();
  const signupFee = parseNonNegativeDecimal(
    String(formData.get("signup_fee_value") ?? formData.get("signup_fee_excl_vat") ?? ""),
  );
  const packValidityMonthsRaw = String(formData.get("pack_validity_months") ?? "").trim();
  const packValidityMonths = packValidityMonthsRaw ? parsePositiveInt(packValidityMonthsRaw) : null;
  const creditGrants = parseFormulaCreditGrants(formData);
  const creditsCount = creditGrants.reduce((sum, grant) => sum + grant.credits_count, 0);
  const entitlementIds = parseStringList(formData.getAll("entitlement_course_type_ids"));
  const paymentMethods = parseStringList(formData.getAll("payment_methods")).map((value) => value.toUpperCase());
  const options = parseStringList(String(formData.get("options_csv") ?? "").split(","));
  const restrictions = parseFormulaRestrictions(formData);

  if (!name) {
    throw new Error("Nom de formule obligatoire");
  }
  if (price === null && kind !== "FORFAIT") {
    throw new Error("Tarif formule obligatoire (TTC ou HT)");
  }
  if (!currency) {
    throw new Error("Devise obligatoire");
  }
  if (kind === "PACK" && creditGrants.length === 0) {
    throw new Error("Ajoutez au moins un type de credit et son nombre de credits");
  }
  if (kind === "PACK" && creditsCount <= 0) {
    throw new Error("Nombre de credits total invalide pour un carnet");
  }
  if (kind === "PACK" && (packValidityMonths === null || packValidityMonths < 1 || packValidityMonths > 12)) {
    throw new Error("La duree de validite du carnet doit etre comprise entre 1 et 12 mois");
  }
  if (entitlementIds.length === 0) {
    throw new Error("Selectionnez au moins un type de cours");
  }

  return {
    name,
    kind,
    active: checkboxField(formData, "active"),
    is_private: checkboxField(formData, "is_private"),
    description: optionalField(formData, "description"),
    credits_count: kind === "PACK" ? creditsCount : null,
    pack_validity_months: kind === "PACK" ? packValidityMonths : null,
    credit_grants: kind === "PACK" ? creditGrants : [],
    credit_grants_relation: kind === "PACK" ? creditGrantsRelation : "OR",
    price_tax_mode: priceTaxMode,
    monthly_price_value: price,
    monthly_price_excl_vat: price,
    currency_code: currency,
    signup_fee_value: signupFee,
    signup_fee_excl_vat: signupFee,
    options,
    payment_methods: paymentMethods,
    entitlement_course_type_ids: entitlementIds,
    restrictions,
  };
}

export async function createAdminActivityAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const name = String(formData.get("name") ?? "").trim();
  const code = String(formData.get("code") ?? "").trim();
  const description = optionalField(formData, "description");
  const serviceCode = String(formData.get("service_code") ?? "ACTIVITY").trim().toUpperCase();
  const creditTypeId = String(formData.get("credit_type_id") ?? "").trim();
  const durationMinutes = parsePositiveInt(String(formData.get("duration_minutes") ?? ""));
  const defaultCapacity = parsePositiveInt(String(formData.get("default_capacity") ?? ""));
  const defaultHourlyRateRaw = String(formData.get("default_hourly_rate") ?? "").trim();
  const defaultHourlyRate = parseNonNegativeDecimal(defaultHourlyRateRaw);
  const colorHex = String(formData.get("color_hex") ?? "#94C973").trim();
  const modeRaw = String(formData.get("mode") ?? "ANY").trim().toUpperCase();
  const mode = modeRaw === "ONLINE" || modeRaw === "ONSITE" ? modeRaw : "ANY";

  if (!name) {
    redirect("/admin/config?section=activities&error=Nom%20activite%20obligatoire");
  }
  if (!durationMinutes || durationMinutes < 5) {
    redirect("/admin/config?section=activities&error=Duree%20activite%20invalide");
  }
  if (!defaultCapacity || defaultCapacity < 1) {
    redirect("/admin/config?section=activities&error=Capacite%20par%20defaut%20invalide");
  }
  if (!creditTypeId) {
    redirect("/admin/config?section=activities&error=Type%20de%20credit%20obligatoire");
  }
  if (defaultHourlyRateRaw && defaultHourlyRate === null) {
    redirect("/admin/config?section=activities&error=Taux%20horaire%20par%20defaut%20invalide");
  }

  const payload: Record<string, unknown> = {
    name,
    description,
    service_code: serviceCode || "ACTIVITY",
    credit_type_id: creditTypeId,
    duration_minutes: durationMinutes,
    color_hex: colorHex,
    mode,
    default_capacity: defaultCapacity,
    default_hourly_rate: defaultHourlyRateRaw ? defaultHourlyRate : null,
    active: checkboxField(formData, "active"),
  };
  if (code) {
    payload.code = code;
  }

  const result = await backendRequest<AdminActivityOut>(
    "/api/v1/admin/activities",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=activities&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin");
  redirect("/admin/config?section=activities&ok=Activite%20cree");
}

export async function updateAdminActivityAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const activityId = String(formData.get("activity_id") ?? "").trim();
  if (!activityId) {
    redirect("/admin/config?section=activities&error=Activite%20invalide");
  }

  const name = String(formData.get("name") ?? "").trim();
  const code = String(formData.get("code") ?? "").trim();
  const description = optionalField(formData, "description");
  const serviceCode = String(formData.get("service_code") ?? "ACTIVITY").trim().toUpperCase();
  const creditTypeId = String(formData.get("credit_type_id") ?? "").trim();
  const durationMinutes = parsePositiveInt(String(formData.get("duration_minutes") ?? ""));
  const defaultCapacity = parsePositiveInt(String(formData.get("default_capacity") ?? ""));
  const defaultHourlyRateRaw = String(formData.get("default_hourly_rate") ?? "").trim();
  const defaultHourlyRate = parseNonNegativeDecimal(defaultHourlyRateRaw);
  const colorHex = String(formData.get("color_hex") ?? "#94C973").trim();
  const modeRaw = String(formData.get("mode") ?? "ANY").trim().toUpperCase();
  const mode = modeRaw === "ONLINE" || modeRaw === "ONSITE" ? modeRaw : "ANY";

  if (!name) {
    redirect("/admin/config?section=activities&error=Nom%20activite%20obligatoire");
  }
  if (!durationMinutes || durationMinutes < 5) {
    redirect("/admin/config?section=activities&error=Duree%20activite%20invalide");
  }
  if (!defaultCapacity || defaultCapacity < 1) {
    redirect("/admin/config?section=activities&error=Capacite%20par%20defaut%20invalide");
  }
  if (!creditTypeId) {
    redirect("/admin/config?section=activities&error=Type%20de%20credit%20obligatoire");
  }
  if (defaultHourlyRateRaw && defaultHourlyRate === null) {
    redirect("/admin/config?section=activities&error=Taux%20horaire%20par%20defaut%20invalide");
  }

  const payload: Record<string, unknown> = {
    name,
    code: code || undefined,
    description,
    service_code: serviceCode || "ACTIVITY",
    credit_type_id: creditTypeId,
    duration_minutes: durationMinutes,
    color_hex: colorHex,
    mode,
    default_capacity: defaultCapacity,
    default_hourly_rate: defaultHourlyRateRaw ? defaultHourlyRate : null,
    active: checkboxField(formData, "active"),
  };

  const result = await backendRequest<AdminActivityOut>(
    `/api/v1/admin/activities/${activityId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=activities&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin");
  redirect("/admin/config?section=activities&ok=Activite%20mise%20a%20jour");
}

export async function createAdminCreditTypeAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const name = String(formData.get("name") ?? "").trim();
  const code = String(formData.get("code") ?? "").trim();
  const description = optionalField(formData, "description");
  const active = checkboxField(formData, "active");

  if (!name) {
    redirect("/admin/config?section=credit-types&error=Nom%20type%20de%20credit%20obligatoire");
  }

  const payload: Record<string, unknown> = {
    name,
    description,
    active,
  };
  if (code) {
    payload.code = code;
  }

  const result = await backendRequest<AdminCreditTypeOut>(
    "/api/v1/admin/credit-types",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=credit-types&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin");
  redirect("/admin/config?section=credit-types&ok=Type%20de%20credit%20cree");
}

export async function updateAdminCreditTypeAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const creditTypeId = String(formData.get("credit_type_id") ?? "").trim();
  if (!creditTypeId) {
    redirect("/admin/config?section=credit-types&error=Type%20de%20credit%20invalide");
  }

  const name = String(formData.get("name") ?? "").trim();
  const code = String(formData.get("code") ?? "").trim();
  const description = optionalField(formData, "description");
  const active = checkboxField(formData, "active");

  if (!name) {
    redirect("/admin/config?section=credit-types&error=Nom%20type%20de%20credit%20obligatoire");
  }

  const payload: Record<string, unknown> = {
    name,
    description,
    active,
  };
  if (code) {
    payload.code = code;
  }

  const result = await backendRequest<AdminCreditTypeOut>(
    `/api/v1/admin/credit-types/${creditTypeId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=credit-types&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin");
  redirect("/admin/config?section=credit-types&ok=Type%20de%20credit%20mis%20a%20jour");
}

export async function deleteAdminCreditTypeAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const creditTypeId = String(formData.get("credit_type_id") ?? "").trim();
  if (!creditTypeId) {
    redirect("/admin/config?section=credit-types&error=Type%20de%20credit%20invalide");
  }

  const result = await backendRequest<Record<string, never>>(
    `/api/v1/admin/credit-types/${creditTypeId}`,
    {
      method: "DELETE",
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=credit-types&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin");
  redirect("/admin/config?section=credit-types&ok=Type%20de%20credit%20supprime");
}

export async function updateAdminConfigAccountAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const payload = {
    contact_first_name: String(formData.get("contact_first_name") ?? "").trim(),
    contact_last_name: String(formData.get("contact_last_name") ?? "").trim(),
    contact_email: String(formData.get("contact_email") ?? "").trim(),
    contact_phone: String(formData.get("contact_phone") ?? "").trim(),
    company_name: String(formData.get("company_name") ?? "").trim(),
    club_name: String(formData.get("club_name") ?? "").trim(),
    siret: String(formData.get("siret") ?? "").trim(),
    vat_number: String(formData.get("vat_number") ?? "").trim(),
    vat_default_rate: String(formData.get("vat_default_rate") ?? "").trim(),
    website: String(formData.get("website") ?? "").trim(),
    address_line: String(formData.get("address_line") ?? "").trim(),
    postal_code: String(formData.get("postal_code") ?? "").trim(),
    city: String(formData.get("city") ?? "").trim(),
    country: String(formData.get("country") ?? "").trim(),
    allowed_currencies: parseStringList(formData.getAll("allowed_currencies")).map((code) => code.toUpperCase()),
    default_currency: String(formData.get("default_currency") ?? "EUR").trim().toUpperCase(),
    legal_terms: String(formData.get("legal_terms") ?? "").trim(),
  };

  const result = await backendRequest<AdminConfigAccountOut>(
    "/api/v1/admin/config/account",
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=params-account&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  redirect("/admin/config?section=params-account&ok=Informations%20compte%20mises%20a%20jour");
}

export async function updateAdminConfigSubscriptionsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const directDebitDay = parsePositiveInt(String(formData.get("direct_debit_day") ?? ""));
  if (directDebitDay !== null && (directDebitDay < 1 || directDebitDay > 28)) {
    redirect("/admin/config?section=params-subscriptions&error=Jour%20de%20prelevement%20invalide");
  }

  const payload = {
    direct_debit_day: directDebitDay,
    allow_card_subscriptions: checkboxField(formData, "allow_card_subscriptions"),
    add_contract_signature: checkboxField(formData, "add_contract_signature"),
    close_expired_subscriptions: checkboxField(formData, "close_expired_subscriptions"),
    allow_promotional_start_period: checkboxField(formData, "allow_promotional_start_period"),
    allow_prorata_card: checkboxField(formData, "allow_prorata_card"),
    allow_prorata_sepa: checkboxField(formData, "allow_prorata_sepa"),
    online_resiliation_enabled: checkboxField(formData, "online_resiliation_enabled"),
  };

  const result = await backendRequest<AdminSubscriptionSettingsOut>(
    "/api/v1/admin/config/subscriptions",
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=params-subscriptions&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  redirect("/admin/config?section=params-subscriptions&ok=Parametres%20abonnements%20mis%20a%20jour");
}

export async function updateAdminConfigProfessorDefaultGridAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const lines: Array<{
    course_type_id: string;
    default_hourly_rate: number | null;
    rules: Array<{ min_students: number; max_students: number | null; hourly_rate: number }>;
  }> = [];

  for (let index = 0; index < 16; index += 1) {
    const courseTypeId = String(formData.get(`line_course_type_id_${index}`) ?? "").trim();
    const defaultRateRaw = String(formData.get(`line_default_rate_${index}`) ?? "").trim().replace(",", ".");
    const rulesRaw = String(formData.get(`line_rules_${index}`) ?? "").trim();

    if (!courseTypeId && !defaultRateRaw && !rulesRaw) {
      continue;
    }
    if (!courseTypeId) {
      redirect(`/admin/config?section=params-professor-default-grid&error=Ligne%20${index + 1}%20sans%20activite`);
    }

    const defaultRate = defaultRateRaw ? parseNonNegativeDecimal(defaultRateRaw) : null;
    if (defaultRateRaw && defaultRate === null) {
      redirect(`/admin/config?section=params-professor-default-grid&error=Taux%20default%20invalide%20sur%20ligne%20${index + 1}`);
    }

    const rules = parseHeadcountRules(rulesRaw);
    if (rules === null) {
      redirect(`/admin/config?section=params-professor-default-grid&error=Format%20regles%20effectif%20invalide%20sur%20ligne%20${index + 1}`);
    }

    lines.push({
      course_type_id: courseTypeId,
      default_hourly_rate: defaultRate,
      rules,
    });
  }

  const result = await backendRequest<AdminProfessorDefaultGridOut>(
    "/api/v1/admin/config/professor-default-grid",
    {
      method: "PUT",
      body: JSON.stringify({ lines }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=params-professor-default-grid&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin/professors");
  redirect("/admin/config?section=params-professor-default-grid&ok=Grille%20salariale%20par%20defaut%20mise%20a%20jour");
}

export async function updateAdminConfigPaymentMethodsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);
  const enabledCodes = parseStringList(formData.getAll("enabled_codes")).map((code) => code.toUpperCase());

  const result = await backendRequest<AdminPaymentMethodsOut>(
    "/api/v1/admin/config/payment-methods",
    {
      method: "PUT",
      body: JSON.stringify({ enabled_codes: enabledCodes }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=params-payments&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  redirect("/admin/config?section=params-payments&ok=Moyens%20de%20paiement%20mis%20a%20jour");
}

export async function updateAdminConfigProductCategoriesAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const raw = String(formData.get("categories") ?? "");
  const categories = raw
    .split(/[\n,;]+/)
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);

  const deduplicated: string[] = [];
  const seen = new Set<string>();
  for (const category of categories) {
    const key = category.toLocaleLowerCase("fr-FR");
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    deduplicated.push(category);
  }

  const result = await backendRequest<AdminProductCategoriesOut>(
    "/api/v1/admin/config/product-categories",
    {
      method: "PUT",
      body: JSON.stringify({ categories: deduplicated }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=products&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin/clients");
  redirect("/admin/config?section=products&ok=Categories%20produits%20mises%20a%20jour");
}

export async function updateAdminConfigPaymentProviderAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const payload = {
    provider: String(formData.get("provider") ?? "PAYPLUG").trim().toUpperCase(),
    mode: String(formData.get("mode") ?? "TEST").trim().toUpperCase(),
    payplug_test_secret: optionalField(formData, "payplug_test_secret"),
    payplug_live_secret: optionalField(formData, "payplug_live_secret"),
    mollie_test_api_key: optionalField(formData, "mollie_test_api_key"),
    mollie_live_api_key: optionalField(formData, "mollie_live_api_key"),
    webhook_secret: optionalField(formData, "webhook_secret"),
  };

  const result = await backendRequest<AdminPaymentProviderOut>(
    "/api/v1/admin/config/payment-provider",
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=params-payments&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  redirect("/admin/config?section=params-payments&ok=Configuration%20PSP%20mise%20a%20jour");
}

export async function updateAdminConfigMessagingSettingsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const payload = {
    studio_email: String(formData.get("studio_email") ?? "").trim(),
    studio_sender_name: String(formData.get("studio_sender_name") ?? "").trim(),
    teacher_sender_name: String(formData.get("teacher_sender_name") ?? "").trim(),
    use_studio_name_as_default_sender: checkboxField(formData, "use_studio_name_as_default_sender"),
    use_studio_email_for_reminders: checkboxField(formData, "use_studio_email_for_reminders"),
    use_studio_email_for_lesson_notes: checkboxField(formData, "use_studio_email_for_lesson_notes"),
    send_birthday_emails: checkboxField(formData, "send_birthday_emails"),
  };

  const result = await backendRequest<AdminMessagingSettingsOut>(
    "/api/v1/admin/config/messaging-settings",
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=params-messaging&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  redirect("/admin/config?section=params-messaging&ok=Parametres%20messagerie%20mis%20a%20jour");
}

export async function updateAdminConfigInvoiceTemplateAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const body = String(formData.get("body") ?? "").trim();
  if (!body) {
    redirect("/admin/config?section=params-messaging&error=Modele%20de%20facture%20obligatoire");
  }

  const result = await backendRequest<AdminInvoiceTemplateOut>(
    "/api/v1/admin/config/invoice-template",
    {
      method: "PUT",
      body: JSON.stringify({ body }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=params-messaging&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin/clients");
  redirect("/admin/config?section=params-messaging&ok=Modele%20de%20facture%20mis%20a%20jour");
}

export async function updateAdminConfigInvoiceNumberingAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const formatPattern = String(formData.get("format_pattern") ?? "").trim();
  const nextNumberRaw = String(formData.get("next_number") ?? "").trim();
  const nextNumber = Number.parseInt(nextNumberRaw, 10);

  if (!formatPattern) {
    redirect("/admin/config?section=params-messaging&error=Format%20numero%20de%20facture%20obligatoire");
  }
  if (!Number.isFinite(nextNumber) || nextNumber < 1) {
    redirect("/admin/config?section=params-messaging&error=Prochain%20numero%20de%20facture%20invalide");
  }

  const result = await backendRequest<AdminInvoiceNumberingOut>(
    "/api/v1/admin/config/invoice-numbering",
    {
      method: "PUT",
      body: JSON.stringify({
        format_pattern: formatPattern,
        next_number: nextNumber,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=params-messaging&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin/clients");
  redirect("/admin/config?section=params-messaging&ok=Numero%20de%20facture%20mis%20a%20jour");
}

export async function saveAdminConfigMessagingTemplateAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const templateKind = String(formData.get("template_kind") ?? "").trim().toUpperCase();
  const templateChannel = String(formData.get("template_channel") ?? "").trim().toUpperCase();
  const templateCode = String(formData.get("template_code") ?? "").trim().toUpperCase();
  const templateId = String(formData.get("template_id") ?? "").trim();
  const name = String(formData.get("name") ?? "").trim();
  const subject = optionalField(formData, "subject");
  const body = String(formData.get("body") ?? "").trim();
  const active = checkboxField(formData, "active");

  if (!body) {
    redirect("/admin/config?section=params-messaging&error=Corps%20du%20modele%20obligatoire");
  }

  if (templateKind === "PREDEFINED") {
    if (!templateCode) {
      redirect("/admin/config?section=params-messaging&error=Template%20predefini%20introuvable");
    }

    const result = await backendRequest<AdminMessagingTemplateOut>(
      `/api/v1/admin/config/messaging-templates/predefined/${encodeURIComponent(templateCode)}`,
      {
        method: "PUT",
        body: JSON.stringify({ subject, body, active }),
      },
      token,
    );

    if (!result.ok) {
      redirect(`/admin/config?section=params-messaging&error=${encodeURIComponent(result.message)}`);
    }

    revalidatePath("/admin/config");
    redirect("/admin/config?section=params-messaging&ok=Modele%20predefini%20mis%20a%20jour");
  }

  if (templateKind !== "CUSTOM") {
    redirect("/admin/config?section=params-messaging&error=Type%20de%20modele%20invalide");
  }

  if (!name) {
    redirect("/admin/config?section=params-messaging&error=Nom%20du%20modele%20obligatoire");
  }
  if (templateChannel !== "EMAIL" && templateChannel !== "SMS") {
    redirect("/admin/config?section=params-messaging&error=Canal%20invalide");
  }
  if (templateChannel === "EMAIL" && !subject) {
    redirect("/admin/config?section=params-messaging&error=Objet%20obligatoire%20pour%20un%20email");
  }

  const payload = {
    channel: templateChannel,
    name,
    subject,
    body,
    active,
  };

  const endpoint = templateId
    ? `/api/v1/admin/config/messaging-templates/custom/${encodeURIComponent(templateId)}`
    : "/api/v1/admin/config/messaging-templates/custom";
  const method = templateId ? "PATCH" : "POST";
  const result = await backendRequest<AdminMessagingTemplateOut>(
    endpoint,
    {
      method,
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=params-messaging&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  redirect(
    `/admin/config?section=params-messaging&ok=${encodeURIComponent(
      templateId ? "Modele personnalise mis a jour" : "Modele personnalise cree",
    )}`,
  );
}

export async function resetAdminConfigPredefinedMessagingTemplateAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const templateCode = String(formData.get("template_code") ?? "").trim().toUpperCase();
  if (!templateCode) {
    redirect("/admin/config?section=params-messaging&error=Template%20predefini%20introuvable");
  }

  const result = await backendRequest<AdminMessagingTemplateOut>(
    `/api/v1/admin/config/messaging-templates/predefined/${encodeURIComponent(templateCode)}`,
    {
      method: "DELETE",
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=params-messaging&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  redirect("/admin/config?section=params-messaging&ok=Modele%20predefini%20retabli");
}

export async function deleteAdminConfigMessagingTemplateAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const templateId = String(formData.get("template_id") ?? "").trim();
  if (!templateId) {
    redirect("/admin/config?section=params-messaging&error=Template%20introuvable");
  }

  const result = await backendRequest<Record<string, never>>(
    `/api/v1/admin/config/messaging-templates/custom/${encodeURIComponent(templateId)}`,
    { method: "DELETE" },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=params-messaging&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  redirect("/admin/config?section=params-messaging&ok=Modele%20personnalise%20supprime");
}

export async function updateAdminClientPasswordEmailTemplateAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const subject = String(formData.get("subject") ?? "").trim();
  const body = String(formData.get("body") ?? "").trim();
  if (!subject || !body) {
    redirect("/admin/config?section=params-messaging&error=Objet%20et%20corps%20sont%20obligatoires");
  }

  const result = await backendRequest<AdminClientPasswordEmailTemplateOut>(
    "/api/v1/admin/clients/password-email-template",
    {
      method: "PUT",
      body: JSON.stringify({ subject, body }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=params-messaging&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin/clients");
  redirect("/admin/config?section=params-messaging&ok=Template%20email%20client%20mis%20a%20jour");
}

export async function createAdminFormulaAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);
  const returnTo = safeAdminReturnPath(formData, "/admin/config/formulas/new");

  let payload: Record<string, unknown>;
  try {
    payload = parseFormulaPayload(formData);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Formulaire formule invalide";
    redirect(appendQueryMessage(returnTo, "error", message));
  }

  const result = await backendRequest<AdminFormulaOut>(
    "/api/v1/admin/formulas",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin/config/formulas/new");
  revalidatePath(`/admin/config/formulas/${result.data.id}`);

  if (returnTo.startsWith("/admin/config/formulas/new")) {
    redirect(appendQueryMessage(`/admin/config/formulas/${result.data.id}`, "ok", "Formule cree"));
  }

  redirect(appendQueryMessage(`/admin/config?section=formulas&formula_id=${result.data.id}`, "ok", "Formule cree"));
}

export async function updateAdminFormulaAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const formulaId = String(formData.get("formula_id") ?? "").trim();
  if (!formulaId) {
    redirect("/admin/config?section=formulas&error=Formule%20invalide");
  }
  const returnTo = safeAdminReturnPath(formData, `/admin/config/formulas/${formulaId}`);

  let payload: Record<string, unknown>;
  try {
    payload = parseFormulaPayload(formData);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Formulaire formule invalide";
    redirect(appendQueryMessage(returnTo, "error", message));
  }

  const result = await backendRequest<AdminFormulaOut>(
    `/api/v1/admin/formulas/${formulaId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config");
  revalidatePath(`/admin/config/formulas/${formulaId}`);
  redirect(appendQueryMessage(returnTo, "ok", "Formule mise a jour"));
}

export async function duplicateAdminFormulaAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const formulaId = String(formData.get("formula_id") ?? "").trim();
  if (!formulaId) {
    redirect("/admin/config?section=formulas&error=Formule%20invalide");
  }
  const returnTo = safeAdminReturnPath(formData, "/admin/config?section=formulas");

  const result = await backendRequest<AdminFormulaOut>(
    `/api/v1/admin/formulas/${formulaId}/duplicate`,
    {
      method: "POST",
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config");
  revalidatePath(`/admin/config/formulas/${formulaId}`);
  revalidatePath(`/admin/config/formulas/${result.data.id}`);

  if (returnTo.startsWith("/admin/config/formulas/")) {
    redirect(appendQueryMessage(`/admin/config/formulas/${result.data.id}`, "ok", "Formule dupliquee"));
  }

  redirect(appendQueryMessage(`/admin/config?section=formulas&formula_id=${result.data.id}`, "ok", "Formule dupliquee"));
}

export async function disableAdminFormulaAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  await ensureAdmin(token);

  const formulaId = String(formData.get("formula_id") ?? "").trim();
  if (!formulaId) {
    redirect("/admin/config?section=formulas&error=Formule%20invalide");
  }
  const returnTo = safeAdminReturnPath(formData, "/admin/config?section=formulas");

  const result = await backendRequest<AdminFormulaOut>(
    `/api/v1/admin/formulas/${formulaId}/disable`,
    {
      method: "POST",
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config");
  revalidatePath(`/admin/config/formulas/${formulaId}`);
  redirect(appendQueryMessage(returnTo, "ok", "Formule desactivee"));
}

export async function updatePlanningActivitiesAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  await ensureAdmin(token);

  const locationId = String(formData.get("location_id") ?? "").trim();
  if (!locationId) {
    redirect("/admin?error=Planning%20invalide");
  }

  const activityIds = parseStringList(formData.getAll("activity_ids"));
  if (activityIds.length === 0) {
    redirect(`/admin/plannings/${locationId}/settings?error=Selectionnez%20au%20moins%20une%20activite`);
  }

  const result = await backendRequest<AdminPlanningActivitiesOut>(
    `/api/v1/admin/plannings/${locationId}/activities`,
    {
      method: "PUT",
      body: JSON.stringify({ activity_ids: activityIds }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/plannings/${locationId}/settings?error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin");
  revalidatePath(`/admin/plannings/${locationId}/settings`);
  redirect(`/admin/plannings/${locationId}/settings?ok=Activites%20du%20planning%20mises%20a%20jour`);
}
