"use server";

import { Buffer } from "node:buffer";
import { revalidatePath } from "next/cache";
import { headers } from "next/headers";
import { redirect } from "next/navigation";

import {
  clearAdminImpersonationReturnToken,
  clearAdminToken,
  clearAllAuthTokens,
  clearPortalReturnTo,
  clearPortalToken,
  getAdminImpersonationReturnToken,
  getAnyToken,
  getPortalToken,
  getTokenForPathname,
  getPortalReturnTo,
  setAdminImpersonationReturnToken,
  setAdminToken,
  setPortalReturnTo,
  setPortalToken,
} from "./auth-cookies";
import { backendRequest, backendUrl } from "./backend";
import { hasAnyAdminAccess } from "./admin-access";
import { loadLivePlanningMatchForBlock, type LivePlanningBlockInput } from "./quote-planning-live";
import {
  analyzeQuoteQuickTransformStatus,
  quoteTransformFinancialAdjustmentFromMeta,
  type QuoteQuickTransformAnalysis,
  type QuoteTransformActivityCatalog,
  type QuoteTransformClient,
  type QuoteTransformLine,
  type QuoteTransformPlan,
  type QuoteTransformProspect,
  type QuoteTransformQuote,
  type QuoteTransformSession,
} from "./quote-transformation";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "./ui-i18n";
import { withUiLanguage, withUiMessageCode } from "./ui-messages";
import type {
  AdminActivityOut,
  AdminActivityContentMappingOut,
  AdminClientOut,
  AdminLegalEntityOut,
  AdminInvoiceNumberingOut,
  AdminInvoiceTemplateOut,
  AdminTeacherInvoiceTemplateOut,
  AdminClientPasswordEmailTemplateOut,
  AdminClientAutoInvoiceRuleOut,
  AdminRangeInvoiceEmailOut,
  AdminRangeInvoiceOut,
  AdminCheckDepositBulkUpdateOut,
  AdminClientPaymentOut,
  AdminCreditTypeOut,
  AdminFormulaOut,
  AdminMessagingSettingsOut,
  AdminMessagingTemplateOut,
  AdminPlanningActivitiesOut,
  AdminCatalogCategoryOut,
  AdminCatalogProductOut,
  AdminCatalogProductImageUploadOut,
  AdminCatalogReorderProductOut,
  AdminCatalogStockTransferOut,
  AdminCatalogKitOut,
  AdminCatalogRequestOut,
  AdminCatalogStockOut,
  AdminStockEntryCreateOut,
  AdminProductCategoriesOut,
  AdminReferralProgramSettingsOut,
  AdminImpersonationStartOut,
  AdminProfessorContractDeleteOut,
  AdminCollaboratorSendPasswordOut,
  AdminProfessorContractGridOut,
  AdminProfessorContractOut,
  AdminProfessorRateOut,
  AdminProfessorSalaryPaymentOut,
  AdminProfessorUpdateResult,
  AdminSubscriptionSettingsOut,
  AdminConfigAccountOut,
  AdminExternalContentCourseOut,
  AdminExternalContentSettingsOut,
  AdminExternalContentSyncOut,
  AdminPaymentProviderOut,
  AdminPaymentMethodsOut,
  AdminProfessorDefaultGridOut,
  AdminProfessorPayGridPeriodDetailOut,
  AdminProfessorPayGridPeriodOut,
  AuthLoginResponse,
  ClientPaymentCheckoutOut,
  PublicFormulaPurchaseContextOut,
  PublicFormulaPurchaseStartOut,
  ProfessorPermissionOut,
  ProfessorCatalogStudentOut,
  TeacherApproveStatementsOut,
  TeacherInvoiceOut,
  TeacherStatementOut,
  UserOut,
  PlanOut,
  LocationOut,
  AdminSessionOut,
} from "./types";

type ApplyScope = "ONE" | "SERIES_FUTURE" | "SERIES_ALL";
type BookingScope = "OCCURRENCE" | "SERIES_FUTURE";
type SessionAudienceScope = "EXTERNAL" | "SUBSCRIPTION" | "FORFAIT" | "PRIVATE";
type UiTextResolver = (key: string, values?: Record<string, string | number>) => string;

function currentToken(): string | null {
  const referer = headers().get("referer") ?? "";
  if (referer) {
    try {
      const pathname = new URL(referer).pathname;
      const scoped = getTokenForPathname(pathname);
      if (scoped) {
        return scoped;
      }
    } catch {
      // Ignore malformed referer and fallback to legacy behavior.
    }
  }
  return getAnyToken();
}

function currentPortalToken(): string | null {
  return getPortalToken() ?? currentToken();
}

function setAdminSessionToken(token: string, maxAgeSeconds?: number): void {
  setAdminToken(token, { maxAge: maxAgeSeconds });
}

function setPortalSessionToken(token: string, maxAgeSeconds?: number): void {
  setPortalToken(token, { maxAge: maxAgeSeconds });
}

function clearToken(): void {
  clearAllAuthTokens();
  clearPortalReturnTo();
}

function optionalField(formData: FormData, fieldName: string): string | null {
  const value = String(formData.get(fieldName) ?? "").trim();
  return value || null;
}

function localizedBaseField(formData: FormData, fieldName: string): string | null {
  return optionalField(formData, `${fieldName}_fr`) ?? optionalField(formData, fieldName);
}

function localizedTranslationsField(formData: FormData, fieldName: string): Record<string, string> {
  const translations: Record<string, string> = {};
  const frenchValue = optionalField(formData, `${fieldName}_fr`) ?? optionalField(formData, fieldName);
  const englishValue = optionalField(formData, `${fieldName}_en`);

  if (frenchValue) {
    translations.fr = frenchValue;
  }
  if (englishValue) {
    translations.en = englishValue;
  }

  return translations;
}

function supportedLanguageField(formData: FormData, fieldName: string, fallback = "fr"): string {
  const value = String(formData.get(fieldName) ?? fallback).trim().toLowerCase();
  return value === "en" ? "en" : "fr";
}

function emailListField(formData: FormData, fieldName: string): string[] | null {
  const value = String(formData.get(fieldName) ?? "").trim();
  if (!value) {
    return null;
  }
  const parsed = value
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
  return parsed.length > 0 ? parsed : null;
}

function multiValueField(formData: FormData, fieldName: string): string[] | null {
  const value = String(formData.get(fieldName) ?? "").replace(/\r/g, "").trim();
  if (!value) {
    return null;
  }
  const parsed = value
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
  return parsed.length > 0 ? parsed : null;
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

function multiCheckboxField(formData: FormData, fieldName: string, defaultValue: boolean): boolean {
  const values = formData.getAll(fieldName);
  if (values.length === 0) {
    return defaultValue;
  }
  const normalized = String(values[values.length - 1] ?? "")
    .trim()
    .toLowerCase();
  if (!normalized) {
    return defaultValue;
  }
  return normalized === "on" || normalized === "true" || normalized === "1";
}

function normalizeSessionAudienceScope(raw: string, fallback: SessionAudienceScope = "EXTERNAL"): SessionAudienceScope {
  const value = raw.trim().toUpperCase();
  if (value === "SUBSCRIPTION" || value === "FORFAIT" || value === "PRIVATE" || value === "EXTERNAL") {
    return value;
  }
  return fallback;
}

function normalizeSessionAudienceScopes(
  rawValues: Iterable<unknown>,
  fallback: SessionAudienceScope[] = ["EXTERNAL"],
): SessionAudienceScope[] {
  const seen = new Set<SessionAudienceScope>();
  const values: SessionAudienceScope[] = [];
  for (const raw of rawValues) {
    const scope = normalizeSessionAudienceScope(String(raw ?? ""), "__INVALID__" as SessionAudienceScope);
    if (scope === ("__INVALID__" as SessionAudienceScope) || seen.has(scope)) {
      continue;
    }
    seen.add(scope);
    values.push(scope);
  }
  if (seen.has("PRIVATE")) {
    return ["PRIVATE"];
  }
  const ordered = (["EXTERNAL", "SUBSCRIPTION", "FORFAIT"] as const).filter((scope) => seen.has(scope));
  if (ordered.length > 0) {
    return [...ordered];
  }
  return [...fallback];
}

function parseSessionAudience(formData: FormData): {
  visibilityScopes: SessionAudienceScope[];
  bookingScopes: SessionAudienceScope[];
  isPrivate: boolean;
  allowOnlineBooking: boolean;
  showExternalRemainingSeats: boolean;
} {
  const visibilityScopes: SessionAudienceScope[] = normalizeSessionAudienceScopes(
    formData.getAll("visibility_scopes"),
    checkboxField(formData, "is_private") ? ["PRIVATE"] : ["EXTERNAL"],
  );
  const bookingScopes: SessionAudienceScope[] = visibilityScopes.includes("PRIVATE")
    ? ["PRIVATE"]
    : normalizeSessionAudienceScopes(
        formData.getAll("booking_scopes"),
        checkboxFieldWithDefault(formData, "allow_online_booking", true) ? ["EXTERNAL"] : ["PRIVATE"],
      );
  return {
    visibilityScopes,
    bookingScopes,
    isPrivate: visibilityScopes.length === 1 && visibilityScopes[0] === "PRIVATE",
    allowOnlineBooking: !(bookingScopes.length === 1 && bookingScopes[0] === "PRIVATE"),
    showExternalRemainingSeats: multiCheckboxField(formData, "show_external_remaining_seats", true),
  };
}

function parseApplyScope(raw: string): ApplyScope {
  const value = raw.trim().toUpperCase();
  if (value === "SERIES_FUTURE" || value === "SERIES_ALL") {
    return value;
  }
  return "ONE";
}

function parseBookingScope(raw: string): BookingScope {
  const value = raw.trim().toUpperCase();
  if (value === "SERIES_FUTURE") {
    return "SERIES_FUTURE";
  }
  return "OCCURRENCE";
}

function appendQueryParam(path: string, key: string, value: string): string {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}${encodeURIComponent(key)}=${encodeURIComponent(value)}`;
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

function formatAdminDateTime(value: string, language: UiLanguage, timezone = "Europe/Paris"): string {
  return new Intl.DateTimeFormat(localeForUiLanguage(language), {
    timeZone: normalizeTimezone(timezone, "Europe/Paris"),
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
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

function safeClientReturnPath(formData: FormData, fallback = "/client"): string {
  const raw = String(formData.get("return_to") ?? "").trim();
  if (raw.startsWith("/dashboard") || raw.startsWith("/client")) {
    return raw;
  }
  return fallback;
}

function safePublicBuyPath(raw: string, fallback: string): string {
  const value = raw.trim();
  if (value.startsWith("/buy/") || value.startsWith("/login")) {
    return value;
  }
  return fallback;
}

function safePublicReturnPath(raw: string, fallback: string): string {
  const value = raw.trim();
  if (
    value.startsWith("/buy/")
    || value.startsWith("/login")
    || value.startsWith("/embed/")
    || value.startsWith("/client")
    || value.startsWith("/dashboard")
  ) {
    return value;
  }
  return fallback;
}

function appendQueryMessage(path: string, key: string, message: string): string {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}${key}=${encodeURIComponent(message)}`;
}

type CreateSessionDraftPayload = {
  title: string;
  course_type_id: string;
  professor_id: string;
  location_id: string;
  session_timezone: string;
  start_date: string;
  start_time: string;
  end_time: string;
  duration_minutes: string;
  capacity_max: string;
  is_all_day: "1" | "0";
  zoom_link: string;
  recurrence_mode: string;
  recurrence_frequency: string;
  recurrence_interval: string;
  recurrence_until_date: string;
  recurrence_time_basis: string;
  visibility_scopes: SessionAudienceScope[];
  booking_scopes: SessionAudienceScope[];
  external_booking_price_ttc: string;
  show_external_remaining_seats: "1" | "0";
  public_description: string;
  private_description: string;
  professor_reminder_note: string;
};

function encodeCreateSessionDraft(draft: CreateSessionDraftPayload): string {
  try {
    return Buffer.from(JSON.stringify(draft), "utf-8").toString("base64url");
  } catch {
    return "";
  }
}

function withCreateSessionDraft(path: string, draft: CreateSessionDraftPayload): string {
  const encoded = encodeCreateSessionDraft(draft);
  if (!encoded) {
    return path;
  }
  return setQueryParam(path, "create_draft", encoded);
}

function createSessionErrorPath(path: string, draft: CreateSessionDraftPayload, message: string): string {
  return appendQueryMessage(withCreateSessionDraft(path, draft), "error", message);
}

function clampDraftValue(value: string, maxLength = 600): string {
  if (value.length <= maxLength) {
    return value;
  }
  return value.slice(0, maxLength);
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

function setQueryParam(path: string, key: string, value: string | null): string {
  try {
    const url = new URL(path, "http://localhost");
    if (value === null || value === "") {
      url.searchParams.delete(key);
    } else {
      url.searchParams.set(key, value);
    }
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return path;
  }
}

function sessionCheckoutContext(path: string): { isSessionCheckout: boolean; sessionId: string; bookingUserId: string } {
  try {
    const url = new URL(path, "http://localhost");
    return {
      isSessionCheckout: url.pathname === "/buy/session/checkout",
      sessionId: String(url.searchParams.get("session_id") ?? "").trim(),
      bookingUserId: String(url.searchParams.get("booking_user_id") ?? "").trim(),
    };
  } catch {
    return { isSessionCheckout: false, sessionId: "", bookingUserId: "" };
  }
}

async function resolveChildBookingReturnTo(
  token: string,
  returnTo: string,
  registrationSubjectType: "self" | "child",
): Promise<string> {
  if (registrationSubjectType !== "child") {
    return returnTo;
  }
  const context = sessionCheckoutContext(returnTo);
  if (!context.isSessionCheckout || !context.sessionId || context.bookingUserId) {
    return returnTo;
  }

  const familyResult = await backendRequest<{
    links_as_adult: Array<{ child: { id: string } }>;
  }>("/api/v1/clients/me/family", {}, token);
  if (!familyResult.ok) {
    return returnTo;
  }

  const childIds = [
    ...new Set(
      (familyResult.data.links_as_adult || [])
        .map((link) => String(link.child?.id ?? "").trim())
        .filter((value) => value.length > 0),
    ),
  ];
  if (childIds.length !== 1) {
    return returnTo;
  }
  return setQueryParam(returnTo, "booking_user_id", childIds[0]);
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

function isVacationServiceCode(serviceCode: string): boolean {
  return serviceCode.trim().toUpperCase().startsWith("VACATION");
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

function parseReminderHoursOverride(raw: string): number | null | "INVALID" {
  const value = raw.trim();
  if (!value || value.toLowerCase() === "global") {
    return null;
  }
  const parsed = parseNonNegativeInt(value);
  if (parsed === null) {
    return "INVALID";
  }
  return parsed;
}

function parseOptionalPlanningRuleOverride(raw: string): number | null | "INVALID" {
  const value = raw.trim();
  if (!value || value.toLowerCase() === "global") {
    return null;
  }
  const parsed = parseNonNegativeInt(value);
  if (parsed === null) {
    return "INVALID";
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

function parseSignedDecimal(raw: string): number | null {
  const value = raw.trim();
  if (!value) {
    return null;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return parsed;
}

function parseUuid(raw: string): string | null {
  const value = raw.trim();
  if (!value) {
    return null;
  }
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value) ? value : null;
}

function parseDelimitedRows(text: string): string[][] {
  const delimiter = text.includes("\t") ? "\t" : ";";
  const fallbackDelimiter = delimiter === ";" && !text.includes(";") && text.includes(",") ? "," : delimiter;
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let inQuotes = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];
    if (char === '"' && inQuotes && next === '"') {
      cell += '"';
      index += 1;
      continue;
    }
    if (char === '"') {
      inQuotes = !inQuotes;
      continue;
    }
    if (!inQuotes && char === fallbackDelimiter) {
      row.push(cell.trim());
      cell = "";
      continue;
    }
    if (!inQuotes && (char === "\n" || char === "\r")) {
      if (char === "\r" && next === "\n") {
        index += 1;
      }
      row.push(cell.trim());
      if (row.some((value) => value.length > 0)) {
        rows.push(row);
      }
      row = [];
      cell = "";
      continue;
    }
    cell += char;
  }
  row.push(cell.trim());
  if (row.some((value) => value.length > 0)) {
    rows.push(row);
  }
  return rows;
}

function normalizeCheckDepositHeader(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function checkDepositRowsFromDelimitedText(text: string): Array<Record<string, string | number | null>> {
  const rows = parseDelimitedRows(text);
  if (rows.length === 0) {
    return [];
  }
  const headers = rows[0].map(normalizeCheckDepositHeader);
  const out: Array<Record<string, string | number | null>> = [];
  rows.slice(1).forEach((row, rowIndex) => {
    const record: Record<string, string | number | null> = { row_number: rowIndex + 2 };
    row.forEach((value, index) => {
      const header = headers[index] || "";
      if (!header) {
        return;
      }
      record[header] = value;
    });
    const transactionId = String(record.transaction_id ?? record.id ?? record.identifiant ?? "").trim();
    const reference = String(record.reference ?? record.ref ?? record.numero ?? record.numero_cheque ?? record.cheque ?? "").trim();
    const amountRaw = String(record.amount_incl_vat ?? record.amount ?? record.montant ?? record.montant_ttc ?? "").trim().replace(",", ".");
    const amount = parseNonNegativeDecimal(amountRaw);
    const payerName = String(
      record.payer_name ??
        record.payeur ??
        record.tireur ??
        record.emetteur ??
        record.emetteur_cheque ??
        record.nom_emetteur ??
        record.titulaire ??
        record.titulaire_compte ??
        record.nom_sur_cheque ??
        record.nom_sur_le_cheque ??
        record.nom_cheque ??
        record.nom ??
        "",
    ).trim();
    out.push({
      row_number: rowIndex + 2,
      transaction_id: parseUuid(transactionId),
      reference: reference || null,
      amount_incl_vat: amount && amount > 0 ? amount : null,
      client_name: String(record.client_name ?? record.client ?? record.famille ?? "").trim() || null,
      payer_name: payerName || null,
    });
  });
  return out;
}

async function checkDepositRowsFromSpreadsheet(file: File): Promise<Array<Record<string, string | number | null>>> {
  const { default: readXlsxFile } = await import("read-excel-file");
  const rows = await readXlsxFile(file);
  return checkDepositRowsFromDelimitedText(rows.map((row) => row.join(";")).join("\n"));
}

function parseDateOnly(raw: string): string | null {
  const value = raw.trim();
  if (!value) {
    return null;
  }
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null;
}

type QuoteFinancialAdjustmentType = "none" | "credit" | "debt";

type QuoteFinancialAdjustmentPayload = {
  type: QuoteFinancialAdjustmentType;
  amount_ttc: string;
  effective_date: string | null;
  label: string | null;
};

type QuotePreRegistrationDepositPayload = {
  enabled: boolean;
  amount_ttc: string;
};

function parseQuoteFinancialAdjustment(formData: FormData): { value: QuoteFinancialAdjustmentPayload; error: string | null } {
  const rawType = String(formData.get("financial_adjustment_type") ?? "none").trim().toLowerCase();
  let type: QuoteFinancialAdjustmentType = "none";
  if (rawType === "credit" || rawType === "debt") {
    type = rawType;
  } else if (rawType && rawType !== "none") {
    return {
      value: { type: "none", amount_ttc: "0.00", effective_date: null, label: null },
      error: "Type d ajustement financier invalide",
    };
  }

  const amountRaw = String(formData.get("financial_adjustment_amount_ttc") ?? "").trim().replace(",", ".");
  const dateRaw = String(formData.get("financial_adjustment_effective_date") ?? "").trim();
  const labelRaw = String(formData.get("financial_adjustment_label") ?? "").trim();

  if (dateRaw && !parseDateOnly(dateRaw)) {
    return {
      value: { type: "none", amount_ttc: "0.00", effective_date: null, label: null },
      error: "Date d ajustement invalide",
    };
  }

  let amount = 0;
  if (type !== "none") {
    if (!amountRaw) {
      return {
        value: { type: "none", amount_ttc: "0.00", effective_date: null, label: null },
        error: "Montant obligatoire pour un avoir ou une dette",
      };
    }
    const parsedAmount = parseNonNegativeDecimal(amountRaw);
    if (parsedAmount === null || parsedAmount <= 0) {
      return {
        value: { type: "none", amount_ttc: "0.00", effective_date: null, label: null },
        error: "Montant d ajustement invalide",
      };
    }
    amount = parsedAmount;
  }

  const defaultLabel = type === "credit" ? "Avoir" : type === "debt" ? "Dette" : "";
  return {
    value: {
      type,
      amount_ttc: amount.toFixed(2),
      effective_date: dateRaw || null,
      label: (labelRaw || defaultLabel || "").slice(0, 200) || null,
    },
    error: null,
  };
}

function parseQuotePreRegistrationDeposit(
  formData: FormData,
): { value: QuotePreRegistrationDepositPayload; error: string | null } {
  const enabledRaw = String(formData.get("pre_registration_deposit_enabled") ?? "").trim().toLowerCase();
  const enabled = enabledRaw === "yes" || enabledRaw === "true" || enabledRaw === "on" || enabledRaw === "1";
  if (!enabled) {
    return {
      value: {
        enabled: false,
        amount_ttc: "0.00",
      },
      error: null,
    };
  }

  const amountRaw = String(formData.get("pre_registration_deposit_amount_ttc") ?? "").trim().replace(",", ".");
  const normalizedAmountRaw = amountRaw || "200.00";
  const parsedAmount = parseNonNegativeDecimal(normalizedAmountRaw);
  if (parsedAmount === null || parsedAmount <= 0) {
    return {
      value: {
        enabled: false,
        amount_ttc: "0.00",
      },
      error: "Montant d acompte invalide",
    };
  }

  return {
    value: {
      enabled: true,
      amount_ttc: parsedAmount.toFixed(2),
    },
    error: null,
  };
}

type CatalogKitItemPayload = {
  product_id: string;
  quantity: number;
  display_order: number;
};

type CatalogKitPriceMode = "calculated" | "forced";

function parseCatalogKitItemsFromFormData(formData: FormData, maxRows = 50): CatalogKitItemPayload[] | null {
  const out: CatalogKitItemPayload[] = [];
  const seen = new Set<string>();
  const requestedCount = parseNonNegativeInt(String(formData.get("item_count") ?? ""));
  const totalRows = requestedCount === null ? maxRows : Math.min(maxRows, requestedCount);
  for (let i = 0; i < totalRows; i += 1) {
    const productIdRaw = String(formData.get(`item_product_id_${i}`) ?? "");
    const productId = parseUuid(productIdRaw);
    if (!productId) {
      continue;
    }
    if (seen.has(productId)) {
      return null;
    }
    const quantity = parsePositiveInt(String(formData.get(`item_quantity_${i}`) ?? "1")) ?? 1;
    const displayOrder = parseNonNegativeInt(String(formData.get(`item_order_${i}`) ?? String(i))) ?? i;
    seen.add(productId);
    out.push({
      product_id: productId,
      quantity,
      display_order: displayOrder,
    });
  }
  return out;
}

function parseCatalogKitPriceMode(raw: string): CatalogKitPriceMode {
  return raw.trim().toLowerCase() === "forced" ? "forced" : "calculated";
}

function parseCurrencyCode(raw: string, fallback = "EUR"): string {
  const value = raw.trim().toUpperCase();
  if (!value) {
    return fallback;
  }
  return /^[A-Z]{3}$/.test(value) ? value : fallback;
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
    normalized === "SEPA_DEBIT" ||
    normalized === "FACTURATION_AUTO"
  ) {
    return normalized;
  }
  return null;
}

function parsePurchaseType(raw: string): "FORMULA" | "PRODUCT" {
  return raw.trim().toUpperCase() === "PRODUCT" ? "PRODUCT" : "FORMULA";
}

function parseCheckboxFlag(formData: FormData, key: string, defaultValue = false): boolean {
  const values = formData.getAll(key).map((entry) => String(entry).trim().toLowerCase());
  if (values.length === 0) {
    return defaultValue;
  }
  if (values.includes("on") || values.includes("true") || values.includes("1") || values.includes("yes")) {
    return true;
  }
  if (values.includes("off") || values.includes("false") || values.includes("0") || values.includes("no")) {
    return false;
  }
  return defaultValue;
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
  return normalized === "ACTIVE" || normalized === "RESPONSABLE" || normalized === "TRIAL";
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
  "can_view_planning_simulation",
  "can_view_intakes",
  "can_view_quotes",
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
  if (!me || !hasAnyAdminAccess(me)) {
    redirect("/login?error_code=admin_access_required");
  }
}

async function ensureAdminAndGetLanguage(token: string): Promise<UiLanguage> {
  const me = await fetchCurrentUser(token);
  if (!me || !hasAnyAdminAccess(me)) {
    redirect("/login?error_code=admin_access_required");
  }
  return normalizeUiLanguage(me.preferred_language);
}

const ADMIN_REFERRAL_ACTION_TEXT: Record<UiLanguage, Record<string, string>> = {
  fr: {
    invalid_payment_status: "Statut de paiement invalide",
    payment_status_updated: "Statut du paiement mis a jour",
    invalid_target_status: "Statut cible invalide",
    xls_unsupported: "Enregistrez le fichier Excel en .xlsx ou en CSV avant import",
    select_checks_or_file: "Selectionnez des cheques ou importez un fichier CSV/XLSX",
    check_rows_unmatched: "{count} ligne(s) non rapprochee(s): {details}{extra}",
    check_rows_updated: "{count} cheque(s) mis a jour{warning}",
    referral_incomplete: "Parrainage incomplet",
    referral_validated: "Parrainage valide",
    referral_not_found: "Parrainage introuvable",
    referral_recomputed: "Parrainage recalcule",
    referrals_recomputed: "{updated} parrainage(s) recalcules, {credits} avoir(s) genere(s)",
    referral_settings_saved: "Parametres de parrainage enregistres",
  },
  en: {
    invalid_payment_status: "Invalid payment status",
    payment_status_updated: "Payment status updated",
    invalid_target_status: "Invalid target status",
    xls_unsupported: "Save the Excel file as .xlsx or CSV before importing",
    select_checks_or_file: "Select checks or import a CSV/XLSX file",
    check_rows_unmatched: "{count} unmatched row(s): {details}{extra}",
    check_rows_updated: "{count} check(s) updated{warning}",
    referral_incomplete: "Incomplete referral",
    referral_validated: "Referral validated",
    referral_not_found: "Referral not found",
    referral_recomputed: "Referral recomputed",
    referrals_recomputed: "{updated} referral(s) recomputed, {credits} credit(s) granted",
    referral_settings_saved: "Referral settings saved",
  },
};

function adminReferralActionText(language: UiLanguage, key: string, values?: Record<string, string | number>): string {
  const template = ADMIN_REFERRAL_ACTION_TEXT[language][key] || ADMIN_REFERRAL_ACTION_TEXT.fr[key] || key;
  if (!values) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (_match, token) => String(values[token] ?? ""));
}

async function ensureProfessorAndGetLanguage(token: string): Promise<UiLanguage> {
  const me = await fetchCurrentUser(token);
  if (!me || me.role !== "prof") {
    redirect("/login?error_code=invalid_session");
  }
  return normalizeUiLanguage(me.preferred_language);
}

function publicActionLanguage(...paths: string[]): UiLanguage {
  for (const path of paths) {
    const value = String(path ?? "").trim();
    if (!value) {
      continue;
    }
    const queryIndex = value.indexOf("?");
    const search = queryIndex >= 0 ? value.slice(queryIndex + 1) : "";
    const params = new URLSearchParams(search);
    const lang = params.get("lang");
    if (lang) {
      return normalizeUiLanguage(lang);
    }
  }
  return "fr";
}

function isDeleteConfirmationValue(value: string): boolean {
  const normalized = value.trim().toUpperCase();
  return normalized === "SUPPRIMER" || normalized === "DELETE";
}

export async function loginAction(formData: FormData): Promise<void> {
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const password = String(formData.get("password") ?? "");
  const mode = String(formData.get("auth_mode") ?? "login").trim().toLowerCase() || "login";
  const purchaseContext = String(formData.get("purchase_context") ?? "").trim();
  const publicReturnTo = safePublicReturnPath(String(formData.get("return_to") ?? "").trim(), "");
  const language = normalizeUiLanguage(String(formData.get("lang") ?? ""));
  const registrationSubjectTypeRaw = String(formData.get("registration_subject_type") ?? "self").trim().toLowerCase();
  const registrationSubjectType = registrationSubjectTypeRaw === "child" ? "child" : "self";
  const loginPathBase = `/login?mode=${encodeURIComponent(mode)}${email ? `&email=${encodeURIComponent(email)}` : ""}${
    purchaseContext ? `&purchase_context=${encodeURIComponent(purchaseContext)}` : ""
  }${publicReturnTo ? `&return_to=${encodeURIComponent(publicReturnTo)}` : ""}&registration_subject_type=${encodeURIComponent(
    registrationSubjectType,
  )}${language === "en" ? "&lang=en" : ""}`;

  const result = await backendRequest<AuthLoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

  if (!result.ok) {
    redirect(`${loginPathBase}&error=${encodeURIComponent(result.message)}`);
  }

  const me = await fetchCurrentUser(result.data.access_token);
  if (!me) {
    redirect("/login?error_code=invalid_session");
  }

  if (hasAnyAdminAccess(me)) {
    clearAllAuthTokens();
    setAdminSessionToken(result.data.access_token);
  } else {
    clearAllAuthTokens();
    setPortalSessionToken(result.data.access_token);
  }

  if (hasAnyAdminAccess(me)) {
    redirect("/admin?ok_code=login_admin_success");
  }

  if (me.role === "client") {
    if (purchaseContext) {
      redirect(
        appendQueryMessage(
          setQueryParam(`/buy/checkout?purchase_context=${encodeURIComponent(purchaseContext)}`, "lang", language === "en" ? "en" : null),
          "ok_code",
          "login_success",
        ),
      );
    }
    if (publicReturnTo) {
      const resolvedReturnTo = await resolveChildBookingReturnTo(result.data.access_token, publicReturnTo, registrationSubjectType);
      redirect(appendQueryMessage(resolvedReturnTo, "ok_code", "login_success"));
    }
    redirect("/client?tab=home&ok_code=login_success");
  }

  redirect("/prof?ok_code=login_teacher_success");
}

export async function registerAction(formData: FormData): Promise<void> {
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const password = String(formData.get("password") ?? "");
  const purchaseContext = String(formData.get("purchase_context") ?? "").trim();
  const publicReturnTo = safePublicReturnPath(String(formData.get("return_to") ?? "").trim(), "");
  const language = normalizeUiLanguage(String(formData.get("lang") ?? ""));
  const first_name = String(formData.get("first_name") ?? "").trim();
  const last_name = String(formData.get("last_name") ?? "").trim();
  const phone = String(formData.get("phone") ?? "").trim();
  const address_line = String(formData.get("address_line") ?? "").trim();
  const postal_code = String(formData.get("postal_code") ?? "").trim();
  const city = String(formData.get("city") ?? "").trim();
  const address_country = String(formData.get("address_country") ?? "FR").trim().toUpperCase();
  const registrationSubjectTypeRaw = String(formData.get("registration_subject_type") ?? "self").trim().toLowerCase();
  const registration_subject_type = registrationSubjectTypeRaw === "child" ? "child" : "self";
  const child_first_name = String(formData.get("child_first_name") ?? "").trim();
  const child_last_name = String(formData.get("child_last_name") ?? "").trim();
  const child_birth_date = String(formData.get("child_birth_date") ?? "").trim();
  const studentPhoto = formData.get("student_photo");
  const studentPhotoFile =
    typeof File !== "undefined" && studentPhoto instanceof File && studentPhoto.size > 0
      ? studentPhoto
      : null;
  const confirmAccuracy = parseCheckboxFlag(formData, "confirm_accuracy", false);
  const acceptAccountTerms = parseCheckboxFlag(formData, "accept_account_terms", false);
  const marketingEmail = parseCheckboxFlag(formData, "marketing_email_opt_in", false);
  const marketingSms = parseCheckboxFlag(formData, "marketing_sms_opt_in", false);
  const residence_country = String(formData.get("residence_country") ?? "FR").trim().toUpperCase();
  const preferred_currency = "EUR";
  const timezone = "Europe/Paris";
  const signupPathBase = `/login?mode=signup${email ? `&email=${encodeURIComponent(email)}` : ""}${
    purchaseContext ? `&purchase_context=${encodeURIComponent(purchaseContext)}` : ""
  }${publicReturnTo ? `&return_to=${encodeURIComponent(publicReturnTo)}` : ""}&registration_subject_type=${encodeURIComponent(
    registration_subject_type,
  )}${language === "en" ? "&lang=en" : ""}`;
  const trialSessionContext = sessionCheckoutContext(publicReturnTo);
  const trialSessionId = trialSessionContext.isSessionCheckout ? trialSessionContext.sessionId : "";

  if (!first_name) {
    redirect(`${signupPathBase}&error_code=signup_first_name_required`);
  }
  if (!last_name) {
    redirect(`${signupPathBase}&error_code=signup_last_name_required`);
  }
  if (registration_subject_type === "child" && !child_first_name) {
    redirect(`${signupPathBase}&error_code=signup_child_first_name_required`);
  }
  if (registration_subject_type === "child" && !child_last_name) {
    redirect(`${signupPathBase}&error_code=signup_child_last_name_required`);
  }
  if (registration_subject_type === "child" && !child_birth_date) {
    redirect(`${signupPathBase}&error_code=signup_child_birth_date_required`);
  }
  if (!email.includes("@")) {
    redirect(`${signupPathBase}&error_code=signup_valid_email_required`);
  }
  if (!phone) {
    redirect(`${signupPathBase}&error_code=signup_phone_required`);
  }
  if (!address_line) {
    redirect(`${signupPathBase}&error_code=signup_address_required`);
  }
  if (!postal_code) {
    redirect(`${signupPathBase}&error_code=signup_postal_code_required`);
  }
  if (!city) {
    redirect(`${signupPathBase}&error_code=signup_city_required`);
  }
  if (!address_country || address_country.length !== 2) {
    redirect(`${signupPathBase}&error_code=signup_address_country_required`);
  }
  if (!residence_country || residence_country.length !== 2) {
    redirect(`${signupPathBase}&error_code=signup_residence_country_required`);
  }
  if (password.length < 8) {
    redirect(`${signupPathBase}&error_code=signup_password_too_short`);
  }
  if (!confirmAccuracy) {
    redirect(`${signupPathBase}&error_code=signup_confirm_accuracy_required`);
  }
  if (!acceptAccountTerms) {
    redirect(`${signupPathBase}&error_code=signup_accept_terms_required`);
  }

  const registerResult = await backendRequest<{ id: string }>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({
      email,
      password,
      first_name,
      last_name,
      phone,
      registration_subject_type,
      child_first_name: registration_subject_type === "child" ? child_first_name : null,
      child_last_name: registration_subject_type === "child" ? child_last_name : null,
      child_birth_date: registration_subject_type === "child" ? child_birth_date || null : null,
      trial_session_id: trialSessionId || null,
      transactional_email_opt_in: true,
      transactional_sms_opt_in: true,
      marketing_email_opt_in: marketingEmail,
      marketing_sms_opt_in: marketingSms,
      student_photo_filename: studentPhotoFile?.name || null,
      student_photo_mime_type: studentPhotoFile?.type || null,
      address_line,
      postal_code,
      city,
      address_country,
      residence_country,
      preferred_currency,
      timezone,
    }),
  });

  if (!registerResult.ok) {
    redirect(`${signupPathBase}&error=${encodeURIComponent(registerResult.message)}`);
  }

  const loginResult = await backendRequest<AuthLoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

  if (!loginResult.ok) {
    redirect(
      `/login?mode=login${email ? `&email=${encodeURIComponent(email)}` : ""}${
        purchaseContext ? `&purchase_context=${encodeURIComponent(purchaseContext)}` : ""
      }${publicReturnTo ? `&return_to=${encodeURIComponent(publicReturnTo)}` : ""}${language === "en" ? "&lang=en" : ""}&error=${encodeURIComponent(loginResult.message)}`,
    );
  }

  clearAllAuthTokens();
  setPortalSessionToken(loginResult.data.access_token);
  if (purchaseContext) {
    redirect(
      appendQueryMessage(
        setQueryParam(`/buy/checkout?purchase_context=${encodeURIComponent(purchaseContext)}`, "lang", language === "en" ? "en" : null),
        "ok_code",
        "signup_success",
      ),
    );
  }
  if (publicReturnTo) {
    const resolvedReturnTo = await resolveChildBookingReturnTo(
      loginResult.data.access_token,
      publicReturnTo,
      registration_subject_type,
    );
    redirect(appendQueryMessage(resolvedReturnTo, "ok_code", "signup_success"));
  }
  redirect("/client?tab=home&ok_code=signup_success");
}

export async function forgotPasswordAction(formData: FormData): Promise<void> {
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const purchaseContext = String(formData.get("purchase_context") ?? "").trim();
  const publicReturnTo = safePublicReturnPath(String(formData.get("return_to") ?? "").trim(), "");
  const language = normalizeUiLanguage(String(formData.get("lang") ?? ""));
  const forgotPathBase = `/login?mode=forgot${email ? `&email=${encodeURIComponent(email)}` : ""}${
    purchaseContext ? `&purchase_context=${encodeURIComponent(purchaseContext)}` : ""
  }${publicReturnTo ? `&return_to=${encodeURIComponent(publicReturnTo)}` : ""}${language === "en" ? "&lang=en" : ""}`;
  if (!email) {
    redirect(`${forgotPathBase}&error_code=forgot_email_required`);
  }

  const result = await backendRequest<{ message: string }>("/api/v1/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email }),
  });

  if (!result.ok) {
    redirect(`${forgotPathBase}&error=${encodeURIComponent(result.message)}`);
  }

  redirect(`${forgotPathBase}&ok=${encodeURIComponent(result.data.message)}`);
}

export async function resetPasswordAction(formData: FormData): Promise<void> {
  const token = String(formData.get("token") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const passwordConfirm = String(formData.get("password_confirm") ?? "");

  if (!token) {
    redirect("/login?error_code=reset_link_invalid");
  }
  if (password.length < 8) {
    redirect(`/login?mode=forgot&reset_token=${encodeURIComponent(token)}&error_code=reset_password_too_short`);
  }
  if (password !== passwordConfirm) {
    redirect(`/login?mode=forgot&reset_token=${encodeURIComponent(token)}&error_code=reset_password_mismatch`);
  }

  const result = await backendRequest<{ message: string }>("/api/v1/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ token, password }),
  });

  if (!result.ok) {
    redirect(`/login?mode=forgot&reset_token=${encodeURIComponent(token)}&error=${encodeURIComponent(result.message)}`);
  }

  redirect(`/login?mode=login&ok=${encodeURIComponent(result.data.message)}`);
}

export async function logoutAction(): Promise<void> {
  clearToken();
  redirect("/login?ok_code=logged_out");
}

export async function updateProfileAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const residence_country = String(formData.get("residence_country") ?? "").trim().toUpperCase();
  const preferred_language = supportedLanguageField(formData, "preferred_language");
  const preferred_currency = String(formData.get("preferred_currency") ?? "").trim().toUpperCase();
  const timezone = String(formData.get("timezone") ?? "").trim();

  if (!residence_country || !preferred_currency || !timezone) {
    redirect("/client?tab=account&edit_profile=1&error_code=profile_preferences_required");
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
    preferred_language,
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
    redirect(`/client?tab=account&edit_profile=1&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/client");
  revalidatePath("/dashboard");
  redirect("/client?tab=account&ok_code=profile_updated");
}

export async function purchasePlanAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const planId = String(formData.get("plan_id") ?? "");
  const purchaseUserId = String(formData.get("purchase_user_id") ?? "").trim();
  const startDateRaw = String(formData.get("start_date") ?? "").trim();
  const confirmExistingPackPurchase = String(formData.get("confirm_existing_pack_purchase") ?? "").trim() === "1";
  const payload: Record<string, string> = {};
  if (purchaseUserId) {
    payload.user_id = purchaseUserId;
  }
  if (startDateRaw) {
    if (!parseUtcStartOfDate(startDateRaw)) {
      redirect("/client?tab=offers&error_code=offer_start_date_invalid");
    }
    payload.start_date = startDateRaw;
  }
  if (confirmExistingPackPurchase) {
    payload.confirm_existing_pack_purchase = "true";
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
    if (result.status === 409 && result.message === "An active pack with remaining credits already exists") {
      let confirmPath = "/client?tab=offers";
      confirmPath = setQueryParam(confirmPath, "purchase_user_id", purchaseUserId || null);
      confirmPath = setQueryParam(confirmPath, "purchase_start_date", startDateRaw || null);
      confirmPath = setQueryParam(confirmPath, "confirm_plan_id", planId || null);
      confirmPath = setQueryParam(confirmPath, "confirm_existing_pack_purchase", "1");
      confirmPath = setQueryParam(confirmPath, "warning_code", "active_pack_warning");
      redirect(confirmPath);
    }
    redirect(`/client?tab=offers&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/client");
  revalidatePath("/dashboard");
  if (result.data.checkout_url) {
    redirect(result.data.checkout_url);
  }
  let successPath = "/client?tab=offers&ok_code=offer_subscribed";
  successPath = setQueryParam(successPath, "purchase_user_id", purchaseUserId || null);
  successPath = setQueryParam(successPath, "purchase_start_date", startDateRaw || null);
  redirect(successPath);
}

export async function startFormulaPurchaseLinkAction(formData: FormData): Promise<void> {
  const formulaIdRaw = String(formData.get("formula_id") ?? "").trim();
  const formulaId = parseUuid(formulaIdRaw);
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const sessionId = String(formData.get("session_id") ?? "").trim();
  const bookingUserId = String(formData.get("booking_user_id") ?? "").trim();
  const planningReturnTo = safePublicReturnPath(String(formData.get("planning_return_to") ?? "").trim(), "/embed/planning");
  const fallbackReturnTo = formulaId ? `/buy/formula/${formulaId}` : "/buy/formula";
  const returnTo = safePublicBuyPath(String(formData.get("return_to") ?? ""), fallbackReturnTo);
  const language = publicActionLanguage(returnTo, planningReturnTo);

  if (!formulaId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "public_booking.invalid_formula")));
  }
  if (!email || !email.includes("@")) {
    const pathWithEmail = setQueryParam(returnTo, "email", email);
    redirect(appendQueryMessage(pathWithEmail, "error", uiText(language, "public_booking.valid_email_required")));
  }

  const result = await backendRequest<PublicFormulaPurchaseStartOut>(
    `/api/v1/public/formulas/${formulaId}/purchase-start`,
    {
      method: "POST",
      body: JSON.stringify({
        email,
        session_id: sessionId || null,
        booking_user_id: bookingUserId || null,
        planning_return_to: planningReturnTo || null,
      }),
    },
  );
  if (!result.ok) {
    const pathWithEmail = setQueryParam(returnTo, "email", email);
    redirect(appendQueryMessage(pathWithEmail, "error", result.message));
  }

  if (getPortalToken()) {
    redirect(setQueryParam(`/buy/checkout?purchase_context=${encodeURIComponent(result.data.purchase_context)}`, "lang", language === "en" ? "en" : null));
  }

  const mode = result.data.existing_user ? "login" : "signup";
  redirect(setQueryParam(
    `/login?mode=${mode}&email=${encodeURIComponent(email)}&purchase_context=${encodeURIComponent(result.data.purchase_context)}`,
    "lang",
    language === "en" ? "en" : null,
  ));
}

export async function submitFormulaCheckoutAction(formData: FormData): Promise<void> {
  const purchaseContext = String(formData.get("purchase_context") ?? "").trim();
  const returnTo = safePublicBuyPath(String(formData.get("return_to") ?? ""), "/buy/checkout");
  const language = publicActionLanguage(returnTo);
  const confirmExistingPackPurchase = String(formData.get("confirm_existing_pack_purchase") ?? "").trim() === "1";

  if (!purchaseContext) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "public_formula_checkout.invalid_context_error")));
  }

  const token = currentPortalToken();
  if (!token) {
    redirect(setQueryParam(
      `/login?mode=login&purchase_context=${encodeURIComponent(purchaseContext)}&error=${encodeURIComponent(
        uiText(language, "public_formula_checkout.login_required"),
      )}`,
      "lang",
      language === "en" ? "en" : null,
    ));
  }

  const contextResult = await backendRequest<PublicFormulaPurchaseContextOut>(
    `/api/v1/public/formulas/purchase-context/${encodeURIComponent(purchaseContext)}`,
  );
  if (!contextResult.ok) {
    redirect(appendQueryMessage(returnTo, "error", contextResult.message));
  }

  const purchaseResult = await backendRequest<{ id: string; checkout_url?: string | null }>(
    `/api/v1/plans/${contextResult.data.formula_id}/purchase`,
    {
      method: "POST",
      body: JSON.stringify({
        purchase_context: purchaseContext,
        confirm_existing_pack_purchase: confirmExistingPackPurchase,
      }),
    },
    token,
  );
  if (!purchaseResult.ok) {
    if (purchaseResult.status === 401) {
      clearToken();
      redirect(setQueryParam(
        `/login?mode=login&purchase_context=${encodeURIComponent(purchaseContext)}&error=${encodeURIComponent(
          uiText(language, "public_formula_checkout.session_expired"),
        )}`,
        "lang",
        language === "en" ? "en" : null,
      ));
    }
    const withContext = setQueryParam(returnTo, "purchase_context", purchaseContext);
    if (purchaseResult.status === 409 && purchaseResult.message === "An active pack with remaining credits already exists") {
      const warningPath = setQueryParam(withContext, "confirm_existing_pack_purchase", "1");
      redirect(
        setQueryParam(
          warningPath,
          "warning",
          uiText(language, "public_formula_checkout.active_pack_warning"),
        ),
      );
    }
    redirect(appendQueryMessage(withContext, "error", purchaseResult.message));
  }

  revalidatePath("/client");
  revalidatePath("/dashboard");
  if (purchaseResult.data.checkout_url) {
    redirect(purchaseResult.data.checkout_url);
  }
  redirect(`/client?tab=finance&ok=${encodeURIComponent(uiText(language, "public_formula_checkout.purchase_confirmed"))}`);
}

export async function submitPublicSessionCheckoutAction(formData: FormData): Promise<void> {
  const sessionId = String(formData.get("session_id") ?? "").trim();
  const bookingUserId = String(formData.get("booking_user_id") ?? "").trim();
  const checkoutReturnTo = safePublicBuyPath(
    String(formData.get("checkout_return_to") ?? "").trim(),
    sessionId ? `/buy/session/checkout?session_id=${encodeURIComponent(sessionId)}` : "/buy/session/checkout",
  );
  const planningReturnTo = safePublicReturnPath(
    String(formData.get("planning_return_to") ?? "").trim(),
    "/embed/planning",
  );
  const language = publicActionLanguage(checkoutReturnTo, planningReturnTo);

  if (!sessionId) {
    redirect(appendQueryMessage(checkoutReturnTo, "error_code", "invalid_slot"));
  }

  const token = currentPortalToken();
  if (!token) {
    redirect(setQueryParam(
      `/login?mode=login&return_to=${encodeURIComponent(checkoutReturnTo)}&error_code=booking_login_required`,
      "lang",
      language === "en" ? "en" : null,
    ));
  }

  const result = await backendRequest<{
    booking_id: string;
    booking_status: string;
    checkout_url: string | null;
    invoice_status: string | null;
  }>(
    `/api/v1/clients/me/sessions/${sessionId}/checkout`,
    {
      method: "POST",
      body: JSON.stringify(bookingUserId ? { user_id: bookingUserId } : {}),
    },
    token,
  );
  if (!result.ok) {
    if (result.status === 401) {
      clearToken();
      redirect(setQueryParam(
        `/login?mode=login&return_to=${encodeURIComponent(checkoutReturnTo)}&error_code=session_expired`,
        "lang",
        language === "en" ? "en" : null,
      ));
    }
    redirect(appendQueryMessage(checkoutReturnTo, "error", result.message));
  }

  if (result.data.checkout_url) {
    redirect(result.data.checkout_url);
  }

  const bookingStatus = String(result.data.booking_status ?? "").trim().toUpperCase();
  const invoiceStatus = String(result.data.invoice_status ?? "").trim().toUpperCase();
  let successPlanningPath = removeQueryParam(planningReturnTo, "session_id");
  successPlanningPath = removeQueryParam(successPlanningPath, "session_member_id");
  successPlanningPath = removeQueryParam(successPlanningPath, "session_ok");
  successPlanningPath = removeQueryParam(successPlanningPath, "session_error");
  successPlanningPath = removeQueryParam(successPlanningPath, "session_ok_code");
  successPlanningPath = removeQueryParam(successPlanningPath, "session_error_code");
  successPlanningPath = removeQueryParam(successPlanningPath, "ok");
  successPlanningPath = removeQueryParam(successPlanningPath, "error");
  successPlanningPath = removeQueryParam(successPlanningPath, "ok_code");
  successPlanningPath = removeQueryParam(successPlanningPath, "error_code");
  if (bookingStatus === "WAITLISTED") {
    redirect(appendQueryMessage(successPlanningPath, "ok_code", "waitlist_joined"));
  }
  if (invoiceStatus === "PAID") {
    redirect(appendQueryMessage(successPlanningPath, "ok_code", "already_paid"));
  }
  if (invoiceStatus === "COVERED") {
    redirect(appendQueryMessage(successPlanningPath, "ok_code", "booking_confirmed"));
  }

  redirect(appendQueryMessage(successPlanningPath, "ok_code", "booking_confirmed"));
}

export async function openClientPaymentCheckoutAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const returnTo = safeClientReturnPath(formData, "/client?tab=finance&finance_view=transactions");
  const directPaymentUrl = String(formData.get("payment_url") ?? "").trim();
  if (directPaymentUrl) {
    if (directPaymentUrl.startsWith("/") || directPaymentUrl.startsWith("http://") || directPaymentUrl.startsWith("https://")) {
      redirect(directPaymentUrl);
    }
    redirect(appendQueryMessage(returnTo, "error_code", "invalid_payment_link"));
  }

  const paymentRaw = String(formData.get("payment_id") ?? "").trim();
  const paymentId = paymentRaw.startsWith("plan:") ? paymentRaw.slice("plan:".length) : paymentRaw;
  if (!paymentId) {
    redirect(appendQueryMessage(returnTo, "error_code", "payment_not_found"));
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

  revalidatePath("/client");
  revalidatePath("/dashboard");
  redirect(result.data.checkout_url);
}

export async function bookSessionAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const returnTo = safeClientReturnPath(formData, "/client?tab=planning");
  const inSessionContext = returnTo.includes("session_id=");
  let successPlanningPath = removeQueryParam(returnTo, "session_id");
  successPlanningPath = removeQueryParam(successPlanningPath, "session_member_id");
  successPlanningPath = removeQueryParam(successPlanningPath, "session_ok");
  successPlanningPath = removeQueryParam(successPlanningPath, "session_error");
  successPlanningPath = removeQueryParam(successPlanningPath, "session_ok_code");
  successPlanningPath = removeQueryParam(successPlanningPath, "session_error_code");
  successPlanningPath = removeQueryParam(successPlanningPath, "ok");
  successPlanningPath = removeQueryParam(successPlanningPath, "error");
  successPlanningPath = removeQueryParam(successPlanningPath, "ok_code");
  successPlanningPath = removeQueryParam(successPlanningPath, "error_code");

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
    const userErrorCode =
      result.status === 403 && result.message === "No eligible active plan for this session"
        ? "no_eligible_plan"
        : result.status === 403 && result.message === "No remaining credits on selected pack"
          ? "no_pack_credits"
          : "";
    const userMessage = result.message;
    let failurePath = removeQueryParam(returnTo, "ok");
    failurePath = removeQueryParam(failurePath, "ok_code");
    failurePath = removeQueryParam(failurePath, "error");
    failurePath = removeQueryParam(failurePath, "error_code");
    failurePath = removeQueryParam(failurePath, "session_ok");
    failurePath = removeQueryParam(failurePath, "session_ok_code");
    if (inSessionContext) {
      failurePath = removeQueryParam(failurePath, "session_error");
      failurePath = removeQueryParam(failurePath, "session_error_code");
      failurePath = userErrorCode
        ? appendQueryMessage(failurePath, "session_error_code", userErrorCode)
        : appendQueryMessage(failurePath, "session_error", userMessage);
    }
    redirect(userErrorCode ? appendQueryMessage(failurePath, "error_code", userErrorCode) : appendQueryMessage(failurePath, "error", userMessage));
  }

  revalidatePath("/client");
  revalidatePath("/dashboard");
  if (inSessionContext) {
    redirect(appendQueryMessage(successPlanningPath, "ok_code", "booking_confirmed"));
  }
  let successPath = removeQueryParam(returnTo, "error");
  successPath = removeQueryParam(successPath, "session_error");
  successPath = removeQueryParam(successPath, "error_code");
  successPath = removeQueryParam(successPath, "session_error_code");
  redirect(appendQueryMessage(successPath, "ok_code", "booking_confirmed"));
}

export async function reservePublicPlanningSessionAction(formData: FormData): Promise<void> {
  const fallbackReturnTo = "/embed/planning";
  const returnTo = safePublicReturnPath(String(formData.get("return_to") ?? "").trim(), fallbackReturnTo);
  const language = publicActionLanguage(returnTo);
  const token = currentPortalToken();
  if (!token) {
    redirect(setQueryParam(
      `/login?mode=login&return_to=${encodeURIComponent(returnTo)}&error_code=booking_login_required`,
      "lang",
      language === "en" ? "en" : null,
    ));
  }
  let successPlanningPath = removeQueryParam(returnTo, "session_id");
  successPlanningPath = removeQueryParam(successPlanningPath, "session_member_id");
  successPlanningPath = removeQueryParam(successPlanningPath, "session_ok");
  successPlanningPath = removeQueryParam(successPlanningPath, "session_error");
  successPlanningPath = removeQueryParam(successPlanningPath, "session_ok_code");
  successPlanningPath = removeQueryParam(successPlanningPath, "session_error_code");
  successPlanningPath = removeQueryParam(successPlanningPath, "ok");
  successPlanningPath = removeQueryParam(successPlanningPath, "error");
  successPlanningPath = removeQueryParam(successPlanningPath, "ok_code");
  successPlanningPath = removeQueryParam(successPlanningPath, "error_code");

  const sessionId = String(formData.get("session_id") ?? "").trim();
  if (!sessionId) {
    redirect(appendQueryMessage(returnTo, "session_error_code", "invalid_slot"));
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/sessions/${sessionId}/book`,
    {
      method: "POST",
      body: JSON.stringify({}),
    },
    token,
  );

  if (!result.ok) {
    const userErrorCode =
      result.status === 403 && result.message === "No eligible active plan for this session"
        ? "no_eligible_plan"
        : result.status === 403 && result.message === "No remaining credits on selected pack"
          ? "no_pack_credits"
          : "";
    const userMessage = result.message;
    let failurePath = removeQueryParam(returnTo, "ok");
    failurePath = removeQueryParam(failurePath, "error");
    failurePath = removeQueryParam(failurePath, "ok_code");
    failurePath = removeQueryParam(failurePath, "error_code");
    failurePath = removeQueryParam(failurePath, "session_ok");
    failurePath = removeQueryParam(failurePath, "session_error");
    failurePath = removeQueryParam(failurePath, "session_ok_code");
    failurePath = removeQueryParam(failurePath, "session_error_code");
    failurePath = userErrorCode
      ? appendQueryMessage(failurePath, "session_error_code", userErrorCode)
      : appendQueryMessage(failurePath, "session_error", userMessage);
    redirect(userErrorCode ? appendQueryMessage(failurePath, "error_code", userErrorCode) : appendQueryMessage(failurePath, "error", userMessage));
  }

  revalidatePath("/embed/planning");
  redirect(appendQueryMessage(successPlanningPath, "ok_code", "booking_confirmed"));
}

export async function cancelBookingAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const returnTo = safeClientReturnPath(formData, "/client?tab=reservations");

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

  revalidatePath("/client");
  revalidatePath("/dashboard");
  let successPath = removeQueryParam(returnTo, "error");
  successPath = removeQueryParam(successPath, "error_code");
  successPath = removeQueryParam(successPath, "ok");
  successPath = removeQueryParam(successPath, "ok_code");
  redirect(appendQueryMessage(successPath, "ok_code", "booking_cancelled"));
}

export async function professorUpdateAttendanceAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureProfessorAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const returnTo = safeProfessorReturnPath(formData, "/prof?tab=planning");
  const bookingId = String(formData.get("booking_id") ?? "").trim();
  const attendanceStatus = String(formData.get("attendance_status") ?? "").trim().toUpperCase();

  if (!bookingId || !["ATTENDED", "NO_SHOW", "EXCUSED_ABSENCE"].includes(attendanceStatus)) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.action.invalid_attendance_entry")));
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
  redirect(appendQueryMessage(returnTo, "ok", t("teacher.action.attendance_updated")));
}

export async function professorSendSessionMessageAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureProfessorAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const returnTo = safeProfessorReturnPath(formData, "/prof?tab=planning");
  const sessionId = String(formData.get("session_id") ?? "").trim();
  const subject = String(formData.get("subject") ?? "").trim();
  const body = String(formData.get("body") ?? "").trim();
  const bodyFormat = String(formData.get("body_format") ?? "TEXT").trim().toUpperCase() === "HTML" ? "HTML" : "TEXT";
  const recipientTarget = String(formData.get("recipient_target") ?? "GROUP").trim().toUpperCase();
  const targetUserId = recipientTarget.startsWith("STUDENT:") ? parseUuid(recipientTarget.slice("STUDENT:".length)) : null;
  const recipientScope = targetUserId ? "STUDENT" : recipientTarget === "ADMIN" ? "ADMIN" : "GROUP";

  if (!sessionId || !subject || !body) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.action.subject_message_required")));
  }

  const result = await backendRequest<{ message_id: string; recipient_count: number }>(
    `/api/v1/professors/me/sessions/${sessionId}/messages`,
    {
      method: "POST",
      body: JSON.stringify({
        subject,
        body,
        body_format: bodyFormat,
        recipient_scope: recipientScope,
        target_user_id: targetUserId,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/prof");
  redirect(appendQueryMessage(returnTo, "ok", t("teacher.action.message_sent_summary", { count: result.data.recipient_count })));
}

export async function professorMarkSessionAbsentAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureProfessorAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const returnTo = safeProfessorReturnPath(formData, "/prof?tab=planning");
  const sessionId = String(formData.get("session_id") ?? "").trim();
  const notifyStudents = checkboxField(formData, "notify_students");
  const studentsSubject = optionalField(formData, "students_subject");
  const studentsMessage = optionalField(formData, "students_message");
  const studentsFormat = String(formData.get("students_format") ?? "TEXT").trim().toUpperCase() === "HTML" ? "HTML" : "TEXT";

  if (!sessionId) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.action.invalid_session_slot")));
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
  redirect(appendQueryMessage(returnTo, "ok", t("teacher.action.session_cancelled_summary", { count: result.data.notified_students })));
}

export async function teacherApproveStatementsAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureProfessorAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeProfessorReturnPath(formData, "/prof/statements");
  const year = Number.parseInt(String(formData.get("year") ?? "").trim(), 10);
  const month = Number.parseInt(String(formData.get("month") ?? "").trim(), 10);
  if (!Number.isFinite(year) || !Number.isFinite(month)) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.action.invalid_period")));
  }

  const result = await backendRequest<TeacherApproveStatementsOut>(
    `/api/v1/teacher/statements/${year}/${month}/approve`,
    {
      method: "POST",
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/prof/statements");
  revalidatePath(`/prof/statements/${year}/${month}`);
  revalidatePath("/prof");
  redirect(appendQueryMessage(returnTo, "ok", t("teacher.action.generated_invoices_summary", { count: result.data.generated_invoices.length })));
}

export async function teacherApproveStatementsOnlyAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureProfessorAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeProfessorReturnPath(formData, "/prof/statements");
  const year = Number.parseInt(String(formData.get("year") ?? "").trim(), 10);
  const month = Number.parseInt(String(formData.get("month") ?? "").trim(), 10);
  if (!Number.isFinite(year) || !Number.isFinite(month)) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.action.invalid_period")));
  }

  const result = await backendRequest<TeacherStatementOut[]>(
    `/api/v1/teacher/statements/${year}/${month}/approve-only`,
    {
      method: "POST",
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/prof/statements");
  revalidatePath(`/prof/statements/${year}/${month}`);
  revalidatePath("/prof");
  redirect(appendQueryMessage(returnTo, "ok", t("teacher.action.statement_approved_choose_billing")));
}

export async function teacherGenerateStatementsInvoiceAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureProfessorAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeProfessorReturnPath(formData, "/prof/statements");
  const year = Number.parseInt(String(formData.get("year") ?? "").trim(), 10);
  const month = Number.parseInt(String(formData.get("month") ?? "").trim(), 10);
  if (!Number.isFinite(year) || !Number.isFinite(month)) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.action.invalid_period")));
  }

  const result = await backendRequest<TeacherApproveStatementsOut>(
    `/api/v1/teacher/statements/${year}/${month}/generate-invoices`,
    {
      method: "POST",
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/prof/statements");
  revalidatePath(`/prof/statements/${year}/${month}`);
  revalidatePath("/prof");
  redirect(appendQueryMessage(returnTo, "ok", t("teacher.action.generated_invoices_summary", { count: result.data.generated_invoices.length })));
}

export async function teacherDisputeStatementsAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureProfessorAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeProfessorReturnPath(formData, "/prof/statements");
  const year = Number.parseInt(String(formData.get("year") ?? "").trim(), 10);
  const month = Number.parseInt(String(formData.get("month") ?? "").trim(), 10);
  const message = String(formData.get("message") ?? "").trim();
  if (!Number.isFinite(year) || !Number.isFinite(month)) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.action.invalid_period")));
  }
  if (!message) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.action.dispute_message_required")));
  }
  const result = await backendRequest<TeacherStatementOut[]>(
    `/api/v1/teacher/statements/${year}/${month}/dispute`,
    {
      method: "POST",
      body: JSON.stringify({ message }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/prof/statements");
  revalidatePath(`/prof/statements/${year}/${month}`);
  redirect(appendQueryMessage(returnTo, "ok", t("teacher.action.dispute_sent_admin")));
}

export async function teacherDisputeSelectedLinesAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureProfessorAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeProfessorReturnPath(formData, "/prof/statements");
  const year = Number.parseInt(String(formData.get("year") ?? "").trim(), 10);
  const month = Number.parseInt(String(formData.get("month") ?? "").trim(), 10);
  const message = String(formData.get("message") ?? "").trim();
  const selectedLines = formData
    .getAll("selected_lines")
    .map((value) => String(value).trim())
    .filter((value) => value.length > 0);
  if (!Number.isFinite(year) || !Number.isFinite(month)) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.action.invalid_period")));
  }
  if (!message) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.action.comment_required")));
  }
  if (selectedLines.length === 0) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.action.select_at_least_one_line")));
  }
  const result = await backendRequest<TeacherStatementOut[]>(
    `/api/v1/teacher/statements/${year}/${month}/dispute-lines`,
    {
      method: "POST",
      body: JSON.stringify({ message, selected_lines: selectedLines }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/prof/statements");
  revalidatePath(`/prof/statements/${year}/${month}`);
  const successPath = setQueryParam(
    appendQueryMessage(returnTo, "ok", t("teacher.action.issue_sent_admin")),
    "notice",
    "dispute_sent",
  );
  redirect(successPath);
}

export async function teacherReportMissingServiceAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureProfessorAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeProfessorReturnPath(formData, "/prof/statements");
  const year = Number.parseInt(String(formData.get("year") ?? "").trim(), 10);
  const month = Number.parseInt(String(formData.get("month") ?? "").trim(), 10);
  const serviceDate = String(formData.get("service_date") ?? "").trim();
  const courseTypeId = String(formData.get("course_type_id") ?? "").trim();
  const locationId = String(formData.get("location_id") ?? "").trim();
  const studentOrGroup = optionalField(formData, "student_or_group");
  const attendeeCountRaw = String(formData.get("attendee_count") ?? "").trim();
  const comment = String(formData.get("comment") ?? "").trim();

  if (!Number.isFinite(year) || !Number.isFinite(month) || !serviceDate || !courseTypeId || !locationId || !comment) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.action.missing_service_required_fields")));
  }
  let attendeeCount: number | null = null;
  if (attendeeCountRaw) {
    attendeeCount = Number.parseInt(attendeeCountRaw, 10);
    if (!Number.isFinite(attendeeCount) || attendeeCount < 0) {
      redirect(appendQueryMessage(returnTo, "error", t("teacher.action.invalid_attendee_count")));
    }
  }

  const result = await backendRequest<TeacherStatementOut[]>(
    `/api/v1/teacher/statements/${year}/${month}/report-missing-service`,
    {
      method: "POST",
      body: JSON.stringify({
        service_date: serviceDate,
        course_type_id: courseTypeId,
        location_id: locationId,
        student_or_group: studentOrGroup,
        attendee_count: attendeeCount,
        comment,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/prof/statements");
  revalidatePath(`/prof/statements/${year}/${month}`);
  const successPath = setQueryParam(
    appendQueryMessage(returnTo, "ok", t("teacher.action.missing_service_sent_admin")),
    "notice",
    "missing_service_sent",
  );
  redirect(successPath);
}

export async function teacherCancelInvoiceAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureProfessorAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeProfessorReturnPath(formData, "/prof/statements");
  const invoiceId = String(formData.get("invoice_id") ?? "").trim();
  if (!invoiceId) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.action.invalid_invoice")));
  }
  const result = await backendRequest<TeacherInvoiceOut>(
    `/api/v1/teacher/invoices/${invoiceId}/cancel`,
    {
      method: "POST",
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/prof/statements");
  revalidatePath(`/prof/invoices/${invoiceId}`);
  redirect(appendQueryMessage(returnTo, "ok", t("teacher.action.invoice_cancelled")));
}

export async function teacherUncancelInvoiceAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureProfessorAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeProfessorReturnPath(formData, "/prof/statements");
  const invoiceId = String(formData.get("invoice_id") ?? "").trim();
  if (!invoiceId) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.action.invalid_invoice")));
  }
  const result = await backendRequest<TeacherInvoiceOut>(
    `/api/v1/teacher/invoices/${invoiceId}/uncancel`,
    {
      method: "POST",
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/prof/statements");
  revalidatePath(`/prof/invoices/${invoiceId}`);
  redirect(appendQueryMessage(returnTo, "ok", t("teacher.action.invoice_reactivated")));
}

export async function teacherSendInvoiceToAccountingAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureProfessorAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeProfessorReturnPath(formData, "/prof/statements");
  const invoiceId = String(formData.get("invoice_id") ?? "").trim();
  if (!invoiceId) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.action.invalid_invoice")));
  }
  const result = await backendRequest<TeacherInvoiceOut>(
    `/api/v1/teacher/invoices/${invoiceId}/send-to-accounting`,
    {
      method: "POST",
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/prof/statements");
  revalidatePath(`/prof/invoices/${invoiceId}`);
  redirect(appendQueryMessage(returnTo, "ok", t("teacher.action.invoice_sent_to_accounting")));
}

export async function teacherSendExternalInvoiceAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureProfessorAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeProfessorReturnPath(formData, "/prof/statements");
  const year = Number.parseInt(String(formData.get("year") ?? "").trim(), 10);
  const month = Number.parseInt(String(formData.get("month") ?? "").trim(), 10);
  const payorLegalEntityId = String(formData.get("payor_legal_entity_id") ?? "").trim();
  const note = optionalField(formData, "note");
  const invoiceFile = formData.get("invoice_file");
  if (!Number.isFinite(year) || !Number.isFinite(month) || !payorLegalEntityId) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.action.invalid_period_or_payor")));
  }
  if (!(invoiceFile instanceof File) || invoiceFile.size <= 0) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.action.select_invoice_pdf")));
  }

  const payload = new FormData();
  payload.set("payor_legal_entity_id", payorLegalEntityId);
  payload.set("invoice_file", invoiceFile);
  if (note) {
    payload.set("note", note);
  }

  const result = await backendRequest<TeacherStatementOut[]>(
    `/api/v1/teacher/statements/${year}/${month}/send-external-invoice`,
    {
      method: "POST",
      body: payload,
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/prof/statements");
  revalidatePath(`/prof/statements/${year}/${month}`);
  redirect(appendQueryMessage(returnTo, "ok", t("teacher.action.external_invoice_sent_to_accounting")));
}

export async function createAdminSessionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin?create=1");

  const course_type_id = String(formData.get("course_type_id") ?? "").trim();
  const location_id = String(formData.get("location_id") ?? "").trim();
  const professor_id = String(formData.get("professor_id") ?? "").trim();
  const title = String(formData.get("title") ?? "").trim();
  const public_description = optionalField(formData, "public_description");
  const private_description = optionalField(formData, "private_description");
  const professor_reminder_note = optionalField(formData, "professor_reminder_note");
  const externalBookingPriceRaw = String(formData.get("external_booking_price_ttc") ?? "").trim();
  const externalBookingPrice = externalBookingPriceRaw ? parseNonNegativeDecimal(externalBookingPriceRaw.replace(",", ".")) : null;
  const zoom_link = optionalField(formData, "zoom_link");
  const sessionAudience = parseSessionAudience(formData);
  const visibility_scopes = sessionAudience.visibilityScopes;
  const booking_scopes = sessionAudience.bookingScopes;
  const is_private = sessionAudience.isPrivate;
  const allow_online_booking = sessionAudience.allowOnlineBooking;
  const show_external_remaining_seats = sessionAudience.showExternalRemainingSeats;
  const is_all_day = checkboxField(formData, "is_all_day");
  const session_timezone = normalizeTimezone(String(formData.get("session_timezone") ?? "Europe/Paris"), "Europe/Paris");
  const recurrence_mode = String(formData.get("recurrence_mode") ?? "NONE").trim().toUpperCase();

  const recurrence_frequency = String(formData.get("recurrence_frequency") ?? "WEEKLY").trim().toUpperCase();
  const recurrence_interval_raw = String(formData.get("recurrence_interval") ?? "1").trim();
  const recurrence_interval = parsePositiveInt(recurrence_interval_raw);
  const recurrence_until_date = String(formData.get("recurrence_until_date") ?? "").trim();
  const recurrence_time_basis = "LOCAL";

  const start_date = String(formData.get("start_date") ?? "");
  const start_time = String(formData.get("start_time") ?? (is_all_day ? "00:00" : ""));
  const end_time = String(formData.get("end_time") ?? "");
  const duration_minutes_raw = String(formData.get("duration_minutes") ?? "").trim();
  const duration_minutes = duration_minutes_raw ? parsePositiveInt(duration_minutes_raw) : null;
  const start_at_utc = parseUtcFromDateAndTimeInTimezone(start_date, is_all_day ? "00:00" : start_time, session_timezone);
  const parsed_end_at_utc = is_all_day
    ? null
    : end_time.trim()
      ? parseUtcFromDateAndTimeInTimezone(start_date, end_time, session_timezone)
      : null;
  let end_at_utc = parsed_end_at_utc;
  if (!is_all_day && !end_at_utc && start_at_utc && duration_minutes !== null) {
    const startMs = Date.parse(start_at_utc);
    if (Number.isFinite(startMs)) {
      end_at_utc = new Date(startMs + duration_minutes * 60000).toISOString();
    }
  }

  const capacity_raw = String(formData.get("capacity_max") ?? "");
  const parsed_capacity_max = parseNonNegativeInt(capacity_raw);
  const capacity_max = parsed_capacity_max ?? 1;

  const createDraftPayload: CreateSessionDraftPayload = {
    title: clampDraftValue(title, 255),
    course_type_id,
    professor_id,
    location_id,
    session_timezone,
    start_date: String(start_date || "").trim(),
    start_time: String(start_time || "").trim(),
    end_time: String(end_time || "").trim(),
    duration_minutes: duration_minutes_raw,
    capacity_max: String(capacity_raw || "").trim(),
    is_all_day: is_all_day ? "1" : "0",
    zoom_link: clampDraftValue(zoom_link ?? "", 1200),
    recurrence_mode: recurrence_mode || "NONE",
    recurrence_frequency: recurrence_frequency || "WEEKLY",
    recurrence_interval: recurrence_interval_raw || "1",
    recurrence_until_date: recurrence_until_date || "",
    recurrence_time_basis,
    visibility_scopes,
    booking_scopes,
    external_booking_price_ttc: externalBookingPriceRaw,
    show_external_remaining_seats: show_external_remaining_seats ? "1" : "0",
    public_description: clampDraftValue(public_description ?? "", 1200),
    private_description: clampDraftValue(private_description ?? "", 1200),
    professor_reminder_note: clampDraftValue(professor_reminder_note ?? "", 1200),
  };

  if (!course_type_id || !location_id || !title || !start_at_utc) {
    redirect(createSessionErrorPath(returnTo, createDraftPayload, t("admin.planning_action.required_fields_missing")));
  }

  if (!is_all_day && !start_time.trim()) {
    redirect(createSessionErrorPath(returnTo, createDraftPayload, t("admin.planning_action.start_time_required")));
  }

  if (!is_all_day && end_time.trim() && !parsed_end_at_utc) {
    redirect(createSessionErrorPath(returnTo, createDraftPayload, t("admin.planning_action.end_time_invalid")));
  }

  if (!is_all_day && duration_minutes_raw && duration_minutes === null) {
    redirect(createSessionErrorPath(returnTo, createDraftPayload, t("admin.planning_action.duration_invalid")));
  }

  if (!is_all_day && !parsed_end_at_utc && duration_minutes === null) {
    redirect(createSessionErrorPath(returnTo, createDraftPayload, t("admin.planning_action.end_time_or_duration_required")));
  }

  if (!is_all_day && start_at_utc && end_at_utc) {
    const startMs = Date.parse(start_at_utc);
    const endMs = Date.parse(end_at_utc);
    if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) {
      redirect(createSessionErrorPath(returnTo, createDraftPayload, t("admin.planning_action.end_time_invalid")));
    }
  }

  if (!capacity_raw.trim() || parsed_capacity_max === null || capacity_max < 0) {
    redirect(createSessionErrorPath(returnTo, createDraftPayload, t("admin.planning_action.capacity_required")));
  }
  if (externalBookingPriceRaw && externalBookingPrice === null) {
    redirect(createSessionErrorPath(returnTo, createDraftPayload, t("admin.planning_action.external_price_invalid")));
  }

  const recurrenceEnabled = recurrence_mode === "RECURRING";
  if (recurrenceEnabled) {
    if (!(recurrence_frequency === "DAILY" || recurrence_frequency === "WEEKLY" || recurrence_frequency === "MONTHLY")) {
      redirect(createSessionErrorPath(returnTo, createDraftPayload, t("admin.planning_action.recurrence_frequency_invalid")));
    }
    if (recurrence_interval === null || recurrence_interval < 1) {
      redirect(createSessionErrorPath(returnTo, createDraftPayload, t("admin.planning_action.recurrence_interval_invalid")));
    }
    if (!recurrence_until_date) {
      redirect(createSessionErrorPath(returnTo, createDraftPayload, t("admin.planning_action.recurrence_until_required")));
    }
  }

  const payload: Record<string, unknown> = {
    course_type_id,
    location_id,
    title,
    start_at_utc,
    is_all_day,
    capacity_max,
    visibility_scopes,
    booking_scopes,
    is_private,
    allow_online_booking,
    show_external_remaining_seats,
    timezone: session_timezone,
  };
  payload.professor_id = professor_id || null;

  if (public_description !== null) {
    payload.public_description = public_description;
  }
  if (private_description !== null) {
    payload.private_description = private_description;
  }
  if (professor_reminder_note !== null) {
    payload.professor_reminder_note = professor_reminder_note;
  }
  if (zoom_link !== null) {
    payload.zoom_link = zoom_link;
  }
  if (externalBookingPriceRaw) {
    payload.external_booking_price_ttc = externalBookingPrice;
  }
  if (end_at_utc !== null) {
    payload.end_at_utc = end_at_utc;
  }
  if (recurrenceEnabled) {
    const recurrence: Record<string, unknown> = {
      frequency: recurrence_frequency,
      interval: recurrence_interval ?? 1,
      time_basis: recurrence_time_basis,
    };
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
    redirect(createSessionErrorPath(returnTo, createDraftPayload, result.message));
  }

  revalidatePath("/admin");
  const successPath = removeQueryParam(returnTo, "create_draft");
  redirect(appendQueryMessage(successPath, "ok", t("admin.planning_action.slot_created")));
}

export async function updateAdminSessionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin");

  const session_id = String(formData.get("session_id") ?? "").trim();
  const title = String(formData.get("title") ?? "").trim();
  const public_description = optionalField(formData, "public_description");
  const private_description = optionalField(formData, "private_description");
  const professor_reminder_note = optionalField(formData, "professor_reminder_note");
  const externalBookingPriceRaw = String(formData.get("external_booking_price_ttc") ?? "").trim();
  const externalBookingPrice = externalBookingPriceRaw ? parseNonNegativeDecimal(externalBookingPriceRaw.replace(",", ".")) : null;
  const course_type_id = String(formData.get("course_type_id") ?? "").trim();
  const location_id = String(formData.get("location_id") ?? "").trim();
  const professor_id = String(formData.get("professor_id") ?? "").trim();
  const substitute_teacher_id = String(formData.get("substitute_teacher_id") ?? "").trim();
  const substitute_note = optionalField(formData, "substitute_note");
  const zoom_link = optionalField(formData, "zoom_link");
  const status = String(formData.get("status") ?? "").trim();
  const sessionAudience = parseSessionAudience(formData);
  const visibility_scopes = sessionAudience.visibilityScopes;
  const booking_scopes = sessionAudience.bookingScopes;
  const is_private = sessionAudience.isPrivate;
  const allow_online_booking = sessionAudience.allowOnlineBooking;
  const show_external_remaining_seats = sessionAudience.showExternalRemainingSeats;
  const is_all_day = checkboxField(formData, "is_all_day");
  const session_timezone = normalizeTimezone(String(formData.get("session_timezone") ?? "Europe/Paris"), "Europe/Paris");
  const apply_scope = parseApplyScope(String(formData.get("apply_scope") ?? "ONE"));
  const has_recurrence_group = String(formData.get("has_recurrence_group") ?? "").trim() === "1";
  const recurrence_mode = String(formData.get("recurrence_mode") ?? "NONE").trim().toUpperCase();
  const recurrence_frequency = String(formData.get("recurrence_frequency") ?? "WEEKLY").trim().toUpperCase();
  const recurrence_interval_raw = String(formData.get("recurrence_interval") ?? "1").trim();
  const recurrence_interval = parsePositiveInt(recurrence_interval_raw);
  const recurrence_until_date = String(formData.get("recurrence_until_date") ?? "").trim();
  const recurrence_time_basis = "LOCAL";

  const start_date = String(formData.get("start_date") ?? "");
  const start_time = String(formData.get("start_time") ?? (is_all_day ? "00:00" : ""));
  const end_time = String(formData.get("end_time") ?? "");
  const duration_minutes_raw = String(formData.get("duration_minutes") ?? "").trim();
  const duration_minutes = duration_minutes_raw ? parsePositiveInt(duration_minutes_raw) : null;
  const start_at_utc = parseUtcFromDateAndTimeInTimezone(start_date, is_all_day ? "00:00" : start_time, session_timezone);
  const parsed_end_at_utc = is_all_day ? null : parseUtcFromDateAndTimeInTimezone(start_date, end_time, session_timezone);
  let end_at_utc = parsed_end_at_utc;
  if (!is_all_day && !end_at_utc && start_at_utc && duration_minutes !== null) {
    const startMs = Date.parse(start_at_utc);
    if (Number.isFinite(startMs)) {
      end_at_utc = new Date(startMs + duration_minutes * 60000).toISOString();
    }
  }
  const capacity_raw = String(formData.get("capacity_max") ?? "");
  const capacity_max = parseNonNegativeInt(capacity_raw);

  if (!session_id || !title || !start_at_utc || !course_type_id || !location_id) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.update_fields_invalid")));
  }
  if (!is_all_day && !start_time.trim()) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.start_time_required")));
  }

  if (!is_all_day && end_time.trim() && !parsed_end_at_utc) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.end_time_invalid")));
  }

  if (!is_all_day && duration_minutes_raw && duration_minutes === null) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.duration_invalid")));
  }

  if (!is_all_day && !parsed_end_at_utc && duration_minutes === null) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.end_time_or_duration_required")));
  }

  if (!is_all_day && start_at_utc && end_at_utc) {
    const startMs = Date.parse(start_at_utc);
    const endMs = Date.parse(end_at_utc);
    if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) {
      redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.end_time_invalid")));
    }
  }

  if (capacity_raw.trim() && capacity_max === null) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.capacity_invalid")));
  }
  if (externalBookingPriceRaw && externalBookingPrice === null) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.external_price_invalid")));
  }

  const recurrenceEnabled = recurrence_mode === "RECURRING";
  if (recurrenceEnabled) {
    if (has_recurrence_group && apply_scope === "ONE") {
      redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.recurrence_scope_future_or_all_required")));
    }
    if (!has_recurrence_group && apply_scope !== "ONE") {
      redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.recurrence_conversion_scope_one_required")));
    }
    if (!(recurrence_frequency === "DAILY" || recurrence_frequency === "WEEKLY" || recurrence_frequency === "MONTHLY")) {
      redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.recurrence_frequency_invalid")));
    }
    if (recurrence_interval === null || recurrence_interval < 1) {
      redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.recurrence_interval_invalid")));
    }
    if (!recurrence_until_date) {
      redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.recurrence_until_required")));
    }
  }

  const payload: Record<string, unknown> = {
    title,
    public_description,
    private_description,
    professor_reminder_note,
    course_type_id,
    location_id,
    start_at_utc,
    is_all_day,
    visibility_scopes,
    booking_scopes,
    is_private,
    allow_online_booking,
    show_external_remaining_seats,
    external_booking_price_ttc: externalBookingPriceRaw ? externalBookingPrice : null,
    timezone: session_timezone,
  };
  payload.professor_id = professor_id || null;
  if (apply_scope === "ONE") {
    payload.substitute_teacher_id = substitute_teacher_id || null;
    payload.substitute_note = substitute_note;
  }

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
  if (recurrenceEnabled) {
    payload.recurrence = {
      frequency: recurrence_frequency,
      interval: recurrence_interval ?? 1,
      until_date: recurrence_until_date,
      time_basis: recurrence_time_basis,
    };
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
  redirect(appendQueryMessage(successPath, "ok", t("admin.planning_action.slot_updated")));
}

export async function shiftAdminSessionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin?edit=1");

  const session_id = String(formData.get("session_id") ?? "").trim();
  const apply_scope = parseApplyScope(String(formData.get("apply_scope") ?? "ONE"));
  const minutes_delta_raw = String(formData.get("minutes_delta") ?? "").trim();
  const current_start_raw = String(formData.get("current_start_at_utc") ?? "");
  const current_end_raw = String(formData.get("current_end_at_utc") ?? "");

  const minutes_delta = Number.parseInt(minutes_delta_raw, 10);
  if (!session_id || !Number.isFinite(minutes_delta)) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.quick_shift_invalid")));
  }

  const start_at_utc = parseUtcFromLocalInput(current_start_raw);
  const end_at_utc = parseUtcFromLocalInput(current_end_raw);
  if (!start_at_utc || !end_at_utc) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.shift_date_invalid")));
  }

  const start_ms = Date.parse(start_at_utc);
  const end_ms = Date.parse(end_at_utc);
  if (!Number.isFinite(start_ms) || !Number.isFinite(end_ms)) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.shift_date_invalid")));
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
  redirect(appendQueryMessage(returnTo, "ok", t("admin.planning_action.slot_shifted")));
}

export async function duplicateAdminSessionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin");

  const session_id = String(formData.get("session_id") ?? "").trim();
  const target_date = String(formData.get("target_date") ?? "").trim();
  const target_time = String(formData.get("target_time") ?? "").trim();
  const session_timezone = normalizeTimezone(String(formData.get("session_timezone") ?? "Europe/Paris"), "Europe/Paris");
  const parsedScope = parseApplyScope(String(formData.get("apply_scope") ?? "ONE"));
  const apply_scope: "ONE" | "SERIES_FUTURE" = parsedScope === "SERIES_FUTURE" ? "SERIES_FUTURE" : "ONE";
  const target_start_at_utc = parseUtcFromDateAndTimeInTimezone(target_date, target_time, session_timezone);

  if (!session_id || !target_start_at_utc) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.duplicate_invalid_target")));
  }

  const result = await backendRequest<{
    processed_sessions: number;
    duplicated_bookings: number;
  }>(
    `/api/v1/admin/sessions/${session_id}/duplicate?apply_scope=${apply_scope}`,
    {
      method: "POST",
      body: JSON.stringify({
        target_start_at_utc,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin");
  const successPath = removeQueryParam(returnTo, "duplicate");
  redirect(
    appendQueryMessage(
      successPath,
      "ok",
      t("admin.planning_action.slot_duplicated_summary", {
        session_count: result.data.processed_sessions,
        student_count: result.data.duplicated_bookings,
      }),
    ),
  );
}

export async function cancelAdminSessionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
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
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.invalid_session")));
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
      ? t("admin.planning_action.notification_details", {
          student_count: result.data.notified_students,
          professor_count: result.data.notified_professors,
        })
      : "";
  redirect(appendQueryMessage(successPath, "ok", `${t("admin.planning_action.slot_cancelled")}${details}`));
}

export async function deleteAdminSessionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
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
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.invalid_session")));
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
      ? t("admin.planning_action.notification_details", {
          student_count: result.data.notified_students,
          professor_count: result.data.notified_professors,
        })
      : "";
  redirect(appendQueryMessage(successPath, "ok", `${t("admin.planning_action.slot_deleted")}${details}`));
}

export async function adminAddClientToSessionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin?edit=1");

  const sessionId = String(formData.get("session_id") ?? "").trim();
  const clientId = String(formData.get("client_id") ?? "").trim();
  const clientPlanSubscriptionIdRaw = String(formData.get("client_plan_subscription_id") ?? "").trim();
  const scopeRaw = String(formData.get("scope") ?? "").trim();
  const scope = parseBookingScope(scopeRaw);
  const recurrenceChecked = checkboxField(formData, "apply_recurrence");
  const recurrenceEndDate = String(formData.get("recurrence_end_date") ?? "").trim();
  const shouldApplyFuture = scope === "SERIES_FUTURE" || recurrenceChecked;

  if (!sessionId || !clientId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.invalid_session_or_client")));
  }
  if (shouldApplyFuture && recurrenceChecked && !recurrenceEndDate) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.recurrence_end_required")));
  }

  const payload: Record<string, unknown> = {
    client_id: clientId,
  };
  if (clientPlanSubscriptionIdRaw) {
    payload.client_plan_subscription_id = clientPlanSubscriptionIdRaw;
  }
  if (shouldApplyFuture && recurrenceEndDate) {
    payload.recurrence_end_date = recurrenceEndDate;
  }

  const result = await backendRequest<{
    processed_count: number;
    booked_count: number;
    waitlisted_count: number;
    skipped_count: number;
    details: string[];
  }>(
    `/api/v1/admin/sessions/${sessionId}/bookings?scope=${shouldApplyFuture ? "SERIES_FUTURE" : "OCCURRENCE"}`,
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
    const detail = result.data.details?.[0] ?? t("admin.planning_action.enrollment_impossible_slot");
    redirect(appendQueryMessage(returnTo, "error", detail));
  }
  const scopeLabel = shouldApplyFuture ? t("admin.planning.future_series") : t("admin.planning.this_session");
  const summary = t("admin.planning_action.enrollment_summary", {
    scope: scopeLabel,
    booked_count: result.data.booked_count,
    waitlisted_count: result.data.waitlisted_count,
    skipped_count: result.data.skipped_count,
  });
  redirect(appendQueryMessage(returnTo, "ok", summary));
}

export async function adminRemoveClientFromSessionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin?edit=1");

  const sessionId = String(formData.get("session_id") ?? "").trim();
  const bookingId = String(formData.get("booking_id") ?? "").trim();
  const scope = parseBookingScope(String(formData.get("scope") ?? "").trim());
  if (!sessionId || !bookingId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.invalid_booking")));
  }

  const result = await backendRequest<Record<string, never>>(
    `/api/v1/admin/sessions/${sessionId}/bookings/${bookingId}?scope=${scope}`,
    {
      method: "DELETE",
    },
    token,
  );

  if (!result.ok && result.status !== 204) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin");
  redirect(appendQueryMessage(returnTo, "ok", t("admin.planning_action.student_removed_from_slot")));
}

export async function movePlanningReorganizationBookingAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const returnTo = safeAdminReturnPath(formData, "/admin/planning-reorganization");
  const bookingId = String(formData.get("booking_id") ?? "").trim();
  const targetSessionId = String(formData.get("target_session_id") ?? "").trim();
  const scopeRaw = String(formData.get("scope") ?? "single").trim();
  const scope = scopeRaw === "series_future" ? "series_future" : "single";

  if (!bookingId || !targetSessionId) {
    redirect(appendQueryMessage(returnTo, "error", "Deplacement impossible : eleve ou creneau manquant."));
  }

  const result = await backendRequest<{
    moved_count: number;
    skipped_count: number;
    details: string[];
  }>(
    "/api/v1/admin/planning-reorganization/move-booking",
    {
      method: "POST",
      body: JSON.stringify({
        booking_id: bookingId,
        target_session_id: targetSessionId,
        scope,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/planning-reorganization");
  revalidatePath("/admin");
  const details = result.data.details.length ? ` (${result.data.details.join(" ; ")})` : "";
  const message = `${result.data.moved_count} deplacement(s), ${result.data.skipped_count} ignore(s)${details}`;
  redirect(appendQueryMessage(returnTo, result.data.moved_count > 0 ? "ok" : "error", message));
}

export async function adminUpdateSessionAttendanceAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin?edit=1");

  const sessionId = String(formData.get("session_id") ?? "").trim();
  const bookingId = String(formData.get("booking_id") ?? "").trim();
  const attendanceStatus = String(formData.get("attendance_status") ?? "").trim().toUpperCase();

  if (!sessionId || !bookingId || !["BOOKED", "ATTENDED", "NO_SHOW", "EXCUSED_ABSENCE"].includes(attendanceStatus)) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.invalid_attendance_entry")));
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
  redirect(appendQueryMessage(returnTo, "ok", t("admin.planning_action.attendance_updated")));
}

export async function adminUpdateSessionGroupNoteAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin?edit=1");

  const sessionId = String(formData.get("session_id") ?? "").trim();
  const sessionTitle = String(formData.get("session_title") ?? "").trim();
  const noteAction = String(formData.get("note_action") ?? "SAVE_ONLY").trim().toUpperCase();
  const destinationRaw = String(formData.get("note_destination") ?? "PRIVATE").trim().toUpperCase();
  const noteDestination =
    destinationRaw === "STUDENTS" ||
    destinationRaw === "PARENTS" ||
    destinationRaw === "STUDENTS_AND_PARENTS" ||
    destinationRaw === "PROFESSOR" ||
    destinationRaw === "ADMINS" ||
    destinationRaw === "SELF" ||
    destinationRaw === "PRIVATE"
      ? destinationRaw
      : "PRIVATE";
  const groupNote = optionalField(formData, "group_note");
  const groupNoteFormat = String(formData.get("group_note_format") ?? "TEXT").trim().toUpperCase() === "HTML" ? "HTML" : "TEXT";
  const includedStudentIds = parseStringList(formData.getAll("included_student_ids"));
  const sendToSelf = checkboxField(formData, "send_to_self");
  const subject = optionalField(formData, "subject") ?? t("admin.planning_action.group_note_subject", { title: sessionTitle || t("admin.planning_action.slot_fallback") });
  if (!sessionId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.invalid_session")));
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/sessions/${sessionId}/group-note`,
    {
      method: "PATCH",
      body: JSON.stringify({ group_note: groupNote }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  if (noteAction === "SEND_EMAIL" && noteDestination !== "PRIVATE") {
    if (!groupNote) {
      redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.group_note_required_for_send")));
    }
    if (
      (noteDestination === "STUDENTS" || noteDestination === "PARENTS" || noteDestination === "STUDENTS_AND_PARENTS") &&
      includedStudentIds.length === 0
    ) {
      redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.select_at_least_one_student")));
    }

    const broadcastResult = await backendRequest<{
      channel: "EMAIL";
      recipient_count: number;
      cc_count: number;
      skipped_count: number;
      details: string[];
    }>(
      `/api/v1/admin/sessions/${sessionId}/broadcast`,
      {
        method: "POST",
        body: JSON.stringify({
          channel: "EMAIL",
          audience: noteDestination,
          included_student_ids: includedStudentIds,
          send_to_self: sendToSelf,
          subject,
          body: groupNote,
          body_format: groupNoteFormat,
          cc_emails: [],
          cc_phone_numbers: [],
        }),
      },
      token,
    );

    if (!broadcastResult.ok) {
      redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.group_note_saved_send_failed", { message: broadcastResult.message })));
    }

    revalidatePath("/admin");
    redirect(appendQueryMessage(returnTo, "ok", t("admin.planning_action.group_note_saved_sent", { count: broadcastResult.data.recipient_count })));
  }

  revalidatePath("/admin");
  redirect(appendQueryMessage(returnTo, "ok", t("admin.planning_action.group_note_saved")));
}

export async function adminUpdateSessionBookingNoteAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin?edit=1");

  const sessionId = String(formData.get("session_id") ?? "").trim();
  const bookingId = String(formData.get("booking_id") ?? "").trim();
  const studentId = String(formData.get("student_id") ?? "").trim();
  const studentDisplayName = String(formData.get("student_display_name") ?? "").trim();
  const sessionTitle = String(formData.get("session_title") ?? "").trim();
  const noteAction = String(formData.get("note_action") ?? "SAVE_INTERNAL").trim().toUpperCase();
  const studentNote = optionalField(formData, "student_note");
  const studentNoteFormat = String(formData.get("student_note_format") ?? "TEXT").trim().toUpperCase() === "HTML" ? "HTML" : "TEXT";
  if (!sessionId || !bookingId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.invalid_booking")));
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/sessions/${sessionId}/bookings/${bookingId}/note`,
    {
      method: "PATCH",
      body: JSON.stringify({ student_note: studentNote }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  if (noteAction === "SEND_PARENTS") {
    if (!studentId || !studentNote) {
      redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.student_note_parent_required")));
    }
    const subject = t("admin.planning_action.student_note_subject", {
      student: studentDisplayName || t("admin.planning_action.student_fallback"),
      title: sessionTitle || t("admin.planning_action.slot_fallback"),
    });
    const broadcastResult = await backendRequest<{
      channel: "EMAIL";
      recipient_count: number;
      cc_count: number;
      skipped_count: number;
      details: string[];
    }>(
      `/api/v1/admin/sessions/${sessionId}/broadcast`,
      {
        method: "POST",
        body: JSON.stringify({
          channel: "EMAIL",
          audience: "PARENTS",
          included_student_ids: [studentId],
          subject,
          body: studentNote,
          body_format: studentNoteFormat,
          cc_emails: [],
          cc_phone_numbers: [],
        }),
      },
      token,
    );
    if (!broadcastResult.ok) {
      redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.student_note_saved_send_failed", { message: broadcastResult.message })));
    }
    revalidatePath("/admin");
    redirect(appendQueryMessage(returnTo, "ok", t("admin.planning_action.student_note_sent_to_parents", { count: broadcastResult.data.recipient_count })));
  }

  revalidatePath("/admin");
  redirect(appendQueryMessage(returnTo, "ok", t("admin.planning_action.internal_note_saved")));
}

export async function adminSendSessionBroadcastAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin");

  const sessionId = String(formData.get("session_id") ?? "").trim();
  const channelRaw = String(formData.get("channel") ?? "EMAIL").trim().toUpperCase();
  const channel = channelRaw === "SMS" ? "SMS" : "EMAIL";
  const audienceRaw = String(formData.get("audience") ?? "STUDENTS").trim().toUpperCase();
  const audience =
    audienceRaw === "PARENTS" ||
    audienceRaw === "STUDENTS_AND_PARENTS" ||
    audienceRaw === "STUDENTS" ||
    audienceRaw === "PROFESSOR" ||
    audienceRaw === "ADMINS" ||
    audienceRaw === "SELF"
      ? audienceRaw
      : "STUDENTS";
  const subject = optionalField(formData, "subject");
  const body = String(formData.get("body") ?? "").trim();
  const bodyFormat = String(formData.get("body_format") ?? "TEXT").trim().toUpperCase() === "HTML" ? "HTML" : "TEXT";
  const includedStudentIds = parseStringList(formData.getAll("included_student_ids"));
  const sendToSelf = checkboxField(formData, "send_to_self");
  const ccEmails = emailListField(formData, "cc_emails") ?? [];
  const ccPhoneNumbers = emailListField(formData, "cc_phone_numbers") ?? [];
  const isStudentBasedAudience = audience === "STUDENTS" || audience === "PARENTS" || audience === "STUDENTS_AND_PARENTS";

  if (!sessionId || !body) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.invalid_session_or_message")));
  }
  if (isStudentBasedAudience && includedStudentIds.length === 0) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.select_at_least_one_student")));
  }
  if (channel === "EMAIL" && !subject) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.planning_action.email_subject_required")));
  }

  const result = await backendRequest<{
    channel: "EMAIL" | "SMS";
    recipient_count: number;
    cc_count: number;
    skipped_count: number;
    details: string[];
  }>(
    `/api/v1/admin/sessions/${sessionId}/broadcast`,
    {
      method: "POST",
      body: JSON.stringify({
        channel,
        audience,
        included_student_ids: includedStudentIds,
        send_to_self: sendToSelf,
        subject,
        body,
        body_format: bodyFormat,
        cc_emails: ccEmails,
        cc_phone_numbers: ccPhoneNumbers,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin");
  const successPath = removeQueryParam(returnTo, "message");
  const channelLabel = result.data.channel === "SMS" ? t("admin.planning_action.broadcast_channel_sms") : t("admin.planning_action.broadcast_channel_email");
  const copied = result.data.cc_count > 0 ? t("admin.planning_action.broadcast_copies_suffix", { count: result.data.cc_count }) : "";
  const skipped = result.data.skipped_count > 0 ? t("admin.planning_action.broadcast_skipped_suffix", { count: result.data.skipped_count }) : "";
  redirect(
    appendQueryMessage(
      successPath,
      "ok",
      t("admin.planning_action.broadcast_sent_summary", {
        channel: channelLabel,
        count: result.data.recipient_count,
        copied,
        skipped,
      }),
    ),
  );
}

export async function updatePlanningSettingsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const locationId = String(formData.get("location_id") ?? "").trim();
  if (!locationId) {
    redirect(appendQueryMessage("/admin", "error", t("admin.planning_action.invalid_planning")));
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
    redirect(appendQueryMessage(`/admin/plannings/${locationId}/settings`, "error", t("admin.planning_action.invalid_planning_delays")));
  }
  if (waitlist_capacity === null || auto_cancel_if_booked_less_than === null || auto_cancel_hours_before_start === null) {
    redirect(appendQueryMessage(`/admin/plannings/${locationId}/settings`, "error", t("admin.planning_action.invalid_capacity_settings")));
  }
  if (max_bookings_per_client_raw && max_bookings_per_client === null) {
    redirect(appendQueryMessage(`/admin/plannings/${locationId}/settings`, "error", t("admin.planning_action.invalid_max_bookings_per_client")));
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
    redirect(appendQueryMessage(`/admin/plannings/${locationId}/settings`, "error", result.message));
  }

  revalidatePath("/admin");
  revalidatePath(`/admin/plannings/${locationId}/settings`);
  redirect(appendQueryMessage(`/admin/plannings/${locationId}/settings`, "ok", t("admin.planning_action.settings_updated")));
}

export async function updateAdminClientAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const returnTab = String(formData.get("return_tab") ?? "infos").trim() || "infos";
  if (!clientId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_client")));
  }

  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const firstName = String(formData.get("first_name") ?? "").trim();
  const lastName = String(formData.get("last_name") ?? "").trim();
  const residence_country = String(formData.get("residence_country") ?? "").trim().toUpperCase();
  const preferred_language = supportedLanguageField(formData, "preferred_language");
  const preferred_currency = String(formData.get("preferred_currency") ?? "").trim().toUpperCase();
  const timezone = String(formData.get("timezone") ?? "").trim();
  const address_country = String(formData.get("address_country") ?? "").trim().toUpperCase();
  const client_status = String(formData.get("client_status") ?? "").trim().toUpperCase() || "ACTIVE";
  const student_site = optionalField(formData, "student_site");
  const client_kind_raw = String(formData.get("client_kind") ?? "").trim().toUpperCase();
  const client_kind = client_kind_raw === "CHILD" ? "CHILD" : "ADULT";
  const birthDateRaw = String(formData.get("birth_date") ?? "").trim();

  if (!firstName || !lastName || !address_country) {
    redirect(
      appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", t("admin.client_action.required_identity_country")),
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
    preferred_language,
    preferred_currency,
    timezone,
    portal_contact_visible: checkboxFieldWithDefault(formData, "portal_contact_visible", true),
    email_opt_in: checkboxFieldWithDefault(formData, "email_opt_in", true),
    sms_opt_in: checkboxFieldWithDefault(formData, "sms_opt_in", true),
    lesson_reminder_email_opt_in: checkboxFieldWithDefault(formData, "lesson_reminder_email_opt_in", true),
    lesson_reminder_sms_opt_in: checkboxFieldWithDefault(formData, "lesson_reminder_sms_opt_in", false),
    client_kind,
    client_status,
    student_site,
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
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "ok", t("admin.client_action.client_updated")));
}

export async function updateAdminClientGroupsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const returnTab = String(formData.get("return_tab") ?? "infos").trim() || "infos";
  if (!clientId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_client")));
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
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "ok", t("admin.client_action.groups_updated")));
}

export async function reactivateAdminClientDeliveryAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const returnTab = String(formData.get("return_tab") ?? "infos").trim() || "infos";
  if (!clientId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_client")));
  }

  const reactivateEmail = checkboxFieldWithDefault(formData, "reactivate_email", true);
  const reactivatePhone = checkboxFieldWithDefault(formData, "reactivate_phone", true);

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/admin/notifications/contacts/USER/${clientId}/reactivate`,
    {
      method: "POST",
      body: JSON.stringify({
        reactivate_email: reactivateEmail,
        reactivate_phone: reactivatePhone,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath(`/admin/clients/${clientId}`);
  revalidatePath("/admin/notifications/incidents");
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "ok", t("admin.client_action.contacts_reactivated")));
}

export async function adminClientActionPlaceholder(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const adminLanguage = await ensureAdminAndGetLanguage(token);
  const formLanguage = String(formData.get("language") ?? "").trim();
  const language = formLanguage ? normalizeUiLanguage(formLanguage) : adminLanguage;

  const clientId = String(formData.get("client_id") ?? "").trim();
  const actionName = String(formData.get("action_name") ?? "Action").trim();

  if (!clientId) {
    redirect(appendQueryMessage("/admin/clients", "error", uiText(language, "admin.client_action.invalid_client")));
  }

  redirect(`/admin/clients/${clientId}?ok=${encodeURIComponent(uiText(language, "admin.client_detail.action_in_preparation", { action: actionName }))}`);
}

export async function sendAdminClientMessageAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const toRecipientsChecked = parseStringList(formData.getAll("to_emails"));
  const toRecipientsFree = emailListField(formData, "to_emails_free") ?? [];
  const ccRecipientsChecked = parseStringList(formData.getAll("cc_emails"));
  const ccRecipientsFree = emailListField(formData, "cc_emails_free") ?? [];
  const sendCopyToSelf = parseCheckboxFlag(formData, "send_copy_to_self", false);
  const mergeUniqueEmails = (values: string[]): string[] => {
    const out: string[] = [];
    const seen = new Set<string>();
    for (const raw of values) {
      const value = String(raw || "").trim();
      if (!value) {
        continue;
      }
      const key = value.toLowerCase();
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      out.push(value);
    }
    return out;
  };
  const toRecipients = mergeUniqueEmails([...toRecipientsChecked, ...toRecipientsFree]);
  const ccRecipients = mergeUniqueEmails([...ccRecipientsChecked, ...ccRecipientsFree]);
  const subject = String(formData.get("subject") ?? "").trim();
  const body = String(formData.get("body") ?? "").trim();
  const bodyFormatRaw = String(formData.get("body_format") ?? "HTML").trim().toUpperCase();
  const bodyFormat = bodyFormatRaw === "TEXT" ? "TEXT" : "HTML";
  const source = optionalField(formData, "source");
  const messagesMonthsRaw = String(formData.get("messages_months") ?? "").trim();
  const messagesMonths = messagesMonthsRaw === "6" || messagesMonthsRaw === "12" ? messagesMonthsRaw : "3";
  const messagesQuery = String(formData.get("messages_q") ?? "").trim();
  const messageSearch = new URLSearchParams({
    tab: "messages",
    messages_months: messagesMonths,
  });
  if (messagesQuery) {
    messageSearch.set("messages_q", messagesQuery);
  }

  if (!clientId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_client")));
  }

  if (!subject || !body) {
    messageSearch.set("message_modal", "compose");
    messageSearch.set("error", t("admin.client_action.subject_message_required"));
    redirect(`/admin/clients/${clientId}?${messageSearch.toString()}`);
  }

  const result = await backendRequest<{ sent_at: string; to_recipients: string[]; cc_recipients: string[]; message_ids: string[] }>(
    `/api/v1/admin/clients/${clientId}/messages/email`,
    {
      method: "POST",
      body: JSON.stringify({
        to_emails: toRecipients,
        cc_emails: ccRecipients,
        send_copy_to_self: sendCopyToSelf,
        subject,
        body,
        body_format: bodyFormat,
        source,
      }),
    },
    token,
  );

  if (!result.ok) {
    messageSearch.set("message_modal", "compose");
    messageSearch.set("error", result.message);
    redirect(`/admin/clients/${clientId}?${messageSearch.toString()}`);
  }

  revalidatePath(`/admin/clients/${clientId}`);
  messageSearch.set("ok", t("admin.client_action.message_sent"));
  redirect(`/admin/clients/${clientId}?${messageSearch.toString()}`);
}

export async function sendAdminClientPasswordAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const returnTab = String(formData.get("return_tab") ?? "infos").trim() || "infos";
  if (!clientId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_client")));
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
    appendQueryMessage(
      `/admin/clients/${clientId}?tab=${returnTab}`,
      "ok",
      t("admin.client_action.password_generated_sent", { message_id: result.data.message_id }),
    ),
  );
}

export async function adminViewClientPortalAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const returnTo = String(formData.get("return_to") ?? "").trim() || `/admin/clients/${clientId}?tab=infos`;
  if (!clientId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_client")));
  }

  const result = await backendRequest<AdminImpersonationStartOut>(
    `/api/v1/admin/impersonate/client/${clientId}`,
    {
      method: "POST",
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/clients/${clientId}?tab=infos&error=${encodeURIComponent(result.message)}`);
  }

  setPortalSessionToken(result.data.access_token, result.data.expires_in_seconds);
  setPortalReturnTo(returnTo);
  const redirectPath = appendQueryParam(
    appendQueryParam(result.data.redirect_path, "imp", "1"),
    "imp_name",
    result.data.target_display_name,
  );
  redirect(redirectPath);
}

export async function adminViewTeacherPortalAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);

  const teacherId = String(formData.get("teacher_id") ?? "").trim();
  const returnTo = String(formData.get("return_to") ?? "").trim() || `/admin/professors/${teacherId}?tab=profil`;
  if (!teacherId) {
    redirect("/admin/professors?error=Collaborateur%20invalide");
  }

  const result = await backendRequest<AdminImpersonationStartOut>(
    `/api/v1/admin/impersonate/teacher/${teacherId}`,
    {
      method: "POST",
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/professors/${teacherId}?tab=profil&error=${encodeURIComponent(result.message)}`);
  }

  if (result.data.target_role === "manager") {
    setAdminImpersonationReturnToken(token, result.data.expires_in_seconds);
    setPortalReturnTo(returnTo);
    setAdminSessionToken(result.data.access_token, result.data.expires_in_seconds);
    const redirectPath = appendQueryParam(
      appendQueryParam(result.data.redirect_path, "imp", "1"),
      "imp_name",
      result.data.target_display_name,
    );
    redirect(redirectPath);
  }

  setPortalSessionToken(result.data.access_token, result.data.expires_in_seconds);
  setPortalReturnTo(returnTo);
  const redirectPath = appendQueryParam(
    appendQueryParam(result.data.redirect_path, "imp", "1"),
    "imp_name",
    result.data.target_display_name,
  );
  redirect(redirectPath);
}

export async function endAdminImpersonationAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (token) {
    await backendRequest<{ message: string }>(
      "/api/v1/impersonation/end",
      {
        method: "POST",
      },
      token,
    );
  }

  const returnToRaw = String(formData.get("return_to") ?? "").trim() || getPortalReturnTo() || "/admin";
  const returnTo = returnToRaw.startsWith("/admin") ? returnToRaw : "/admin";
  const adminReturnToken = getAdminImpersonationReturnToken();
  if (adminReturnToken) {
    setAdminSessionToken(adminReturnToken);
  } else {
    clearAdminToken();
  }
  clearAdminImpersonationReturnToken();
  clearPortalReturnTo();
  redirect(returnTo);
}

export async function endPortalImpersonationAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (token) {
    await backendRequest<{ message: string }>(
      "/api/v1/impersonation/end",
      {
        method: "POST",
      },
      token,
    );
  }

  const returnToRaw = String(formData.get("return_to") ?? "").trim() || getPortalReturnTo() || "/admin";
  const returnTo = returnToRaw.startsWith("/admin") ? returnToRaw : "/admin";
  clearPortalToken();
  clearPortalReturnTo();
  redirect(returnTo);
}

export async function adminPurchasePlanForClientAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const planId = String(formData.get("plan_id") ?? "").trim();
  const returnTabRaw = String(formData.get("return_tab") ?? "fiche").trim().toLowerCase();
  const returnTab =
    returnTabRaw === "paiements" || returnTabRaw === "messages" || returnTabRaw === "infos" || returnTabRaw === "famille" || returnTabRaw === "reservations"
      ? returnTabRaw
      : "fiche";

  if (!clientId || !planId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_client_or_plan")));
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
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "ok", t("admin.client_action.product_added")));
}

export async function adminOpenClientPurchaseTermsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const offerId = String(formData.get("plan_id") ?? "").trim();
  const returnTabRaw = String(formData.get("return_tab") ?? "fiche").trim().toLowerCase();
  const returnTab =
    returnTabRaw === "paiements" || returnTabRaw === "messages" || returnTabRaw === "infos" || returnTabRaw === "famille" || returnTabRaw === "reservations"
      ? returnTabRaw
      : "fiche";
  const purchaseType = parsePurchaseType(String(formData.get("purchase_type") ?? "FORMULA"));
  const paymentMethodCode = parsePaymentMethodCode(String(formData.get("payment_method_code") ?? ""));
  const startDateRaw = String(formData.get("start_date") ?? "").trim();
  const discountedTotalRaw = String(formData.get("discounted_total_incl_vat") ?? "").trim();
  const discountedTotal = discountedTotalRaw ? parseNonNegativeDecimal(discountedTotalRaw.replace(",", ".")) : null;

  if (!clientId || !offerId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_client_or_plan")));
  }
  if (!paymentMethodCode) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", t("admin.client_action.purchase_payment_method_required")));
  }
  if (discountedTotalRaw && discountedTotal === null) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", t("admin.client_action.discounted_price_invalid")));
  }
  if (startDateRaw && !parseUtcStartOfDate(startDateRaw)) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", t("admin.client_action.start_date_invalid")));
  }

  if (purchaseType === "FORMULA") {
    const formulaResult = await backendRequest<{ id: string; payment_methods: string[] }>(
      `/api/v1/admin/formulas/${offerId}`,
      {},
      token,
    );
    if (!formulaResult.ok) {
      redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(formulaResult.message)}`);
    }
    const allowedMethods = new Set(
      (formulaResult.data.payment_methods ?? []).map((method) => String(method || "").trim().toUpperCase()).filter(Boolean),
    );
    if (allowedMethods.size > 0 && !allowedMethods.has(paymentMethodCode)) {
      redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", t("admin.client_action.payment_method_not_allowed_for_formula")));
    }
  } else {
    const catalogResult = await backendRequest<Array<{ id: string }>>(
      "/api/v1/admin/config/catalog/products?include_inactive=false",
      {},
      token,
    );
    if (!catalogResult.ok) {
      redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(catalogResult.message)}`);
    }
    const exists = catalogResult.data.some((product) => product.id === offerId);
    if (!exists) {
      redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", t("admin.client_action.catalog_product_missing")));
    }
  }

  const params = new URLSearchParams({
    tab: returnTab,
    purchase_modal: "terms",
    purchase_plan_id: offerId,
    purchase_type: purchaseType,
    purchase_payment_method: paymentMethodCode,
  });
  if (discountedTotal !== null) {
    params.set("purchase_discounted_total", discountedTotal.toFixed(2));
  }
  if (startDateRaw) {
    params.set("purchase_start_date", startDateRaw);
  }

  redirect(`/admin/clients/${clientId}?${params.toString()}`);
}

export async function adminFinalizeClientPurchaseAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const offerId = String(formData.get("plan_id") ?? "").trim();
  const planKind = String(formData.get("plan_kind") ?? "").trim().toUpperCase();
  const planName = String(formData.get("plan_name") ?? "").trim() || "Formule";
  const purchaseType = parsePurchaseType(String(formData.get("purchase_type") ?? "FORMULA"));
  const startDateRaw = String(formData.get("start_date") ?? "").trim();
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
  const canSendPaymentLink = purchaseType === "FORMULA" && isCardOnlinePayment;
  const signatureChannel =
    canSendPaymentLink && (signatureChannelRaw === "EMAIL" || signatureChannelRaw === "SMS") ? signatureChannelRaw : "NONE";
  if (!clientId || !offerId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_client_or_plan")));
  }
  if (!paymentMethodCode) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", t("admin.client_action.payment_method_invalid")));
  }
  if (canSendPaymentLink && signatureChannel === "NONE") {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", t("admin.client_action.payment_link_channel_required")));
  }
  if (discountedTotalRaw && discountedTotal === null) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", t("admin.client_action.discounted_price_invalid")));
  }
  if (startDateRaw && !parseUtcStartOfDate(startDateRaw)) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", t("admin.client_action.start_date_invalid")));
  }

  let subscriptionId: string | null = null;
  if (purchaseType === "FORMULA") {
    const purchaseResult = await backendRequest<{ id: string }>(
      `/api/v1/admin/clients/${clientId}/plans/${offerId}/purchase`,
      {
        method: "POST",
        body: JSON.stringify({
          payment_method_code: paymentMethodCode,
          start_date: startDateRaw || null,
        }),
      },
      token,
    );
    if (!purchaseResult.ok) {
      redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(purchaseResult.message)}`);
    }
    subscriptionId = purchaseResult.data.id;

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

    if (canSendPaymentLink && signatureChannel === "EMAIL") {
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
  } else {
    const productListResult = await backendRequest<
      Array<{ id: string; title: string; category_name: string | null; price_incl_vat: string; vat_rate: string }>
    >("/api/v1/admin/config/catalog/products?include_inactive=false", {}, token);
    if (!productListResult.ok) {
      redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(productListResult.message)}`);
    }
    const product = productListResult.data.find((row) => row.id === offerId);
    if (!product) {
      redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", t("admin.client_action.catalog_product_missing")));
    }
    const basePrice = parseNonNegativeDecimal(String(product.price_incl_vat ?? "").replace(",", "."));
    if (basePrice === null || basePrice <= 0) {
      redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", t("admin.client_action.catalog_product_price_invalid")));
    }
    const vatRate = parseNonNegativeDecimal(String(product.vat_rate ?? "0").replace(",", ".")) ?? 0;
    const amountInclVat = discountedTotal !== null ? discountedTotal : basePrice;

    const paymentMethodsResult = await backendRequest<{
      methods: Array<{ code: string; default_legal_entity_id: string | null }>;
    }>("/api/v1/admin/config/payment-methods", {}, token);
    if (!paymentMethodsResult.ok) {
      redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(paymentMethodsResult.message)}`);
    }
    const selectedMethod = paymentMethodsResult.data.methods.find((method) => method.code.toUpperCase() === paymentMethodCode);
    let legalEntityId = selectedMethod?.default_legal_entity_id ?? null;
    if (!legalEntityId) {
      const legalEntitiesResult = await backendRequest<Array<{ id: string }>>("/api/v1/admin/legal-entities?include_inactive=false", {}, token);
      if (!legalEntitiesResult.ok) {
        redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(legalEntitiesResult.message)}`);
      }
      legalEntityId = legalEntitiesResult.data[0]?.id ?? null;
    }
    if (!legalEntityId) {
      redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", t("admin.client_action.configure_legal_entity_before_catalog_purchase")));
    }

    const manualResult = await backendRequest<{ id: string }>(
      `/api/v1/admin/clients/${clientId}/manual-transactions`,
      {
        method: "POST",
        body: JSON.stringify({
          transaction_type: "CHARGE",
          label: product.title,
          description: "Achat produit catalogue",
          category: product.category_name,
          amount_incl_vat: amountInclVat.toFixed(2),
          vat_rate: vatRate.toFixed(3),
          currency: "EUR",
          reference: `CATALOG:${product.id}`,
          legal_entity_id: legalEntityId,
        }),
      },
      token,
    );
    if (!manualResult.ok) {
      redirect(`/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(manualResult.message)}`);
    }
  }

  const notes: string[] = [];
  notes.push(`Nouvel achat (${purchaseType === "PRODUCT" ? "produit catalogue" : "formule de cours"}): ${planName}.`);
  notes.push(`Reglement: ${paymentMethodCode}.`);
  if (discountedTotal !== null) {
    notes.push(`Prix remise saisi: ${discountedTotal.toFixed(2)} EUR TTC.`);
  }
  if (purchaseType === "FORMULA" && planKind === "FORFAIT") {
    notes.push("Tarification forfait: surcouche par activite disponible en etape optionnelle.");
  }
  notes.push("Achat valide depuis le back-office.");
  if (!canSendPaymentLink) {
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
  const channelMessage = !canSendPaymentLink
    ? t("admin.client_action.purchase_channel_recorded")
    : signatureChannel === "EMAIL"
      ? t("admin.client_action.purchase_channel_email_sent")
      : t("admin.client_action.purchase_channel_sms_pending");
  if (purchaseType === "FORMULA" && planKind === "FORFAIT" && subscriptionId) {
    redirect(
      appendQueryMessage(
        `/admin/clients/${clientId}?tab=fiche&subscription_modal=forfait_pricing&subscription_id=${subscriptionId}`,
        "ok",
        t("admin.client_action.product_added_with_channel_forfait", { channel: channelMessage }),
      ),
    );
  }
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "ok", t("admin.client_action.product_added_with_channel", { channel: channelMessage })));
}

export async function suspendAdminClientSubscriptionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const subscriptionId = String(formData.get("subscription_id") ?? "").trim();
  const startRaw = String(formData.get("suspension_starts_at") ?? "").trim();
  const durationUnit = String(formData.get("duration_unit") ?? "DAY").trim().toUpperCase();
  const durationValue = parsePositiveInt(String(formData.get("duration_value") ?? ""));
  if (!clientId || !subscriptionId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_subscription")));
  }
  const startsAt = parseUtcStartOfDate(startRaw);
  if (!startsAt) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=fiche`, "error", t("admin.client_action.invalid_suspension_start_date")));
  }
  if (!durationValue) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=fiche`, "error", t("admin.client_action.invalid_suspension_duration")));
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
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=fiche`, "error", result.message));
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=fiche`, "ok", t("admin.client_action.subscription_suspended")));
}

export async function updateAdminClientSubscriptionExpiryAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const subscriptionId = String(formData.get("subscription_id") ?? "").trim();
  const endsAtRaw = String(formData.get("ends_at") ?? "").trim();
  if (!clientId || !subscriptionId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_product")));
  }
  const endsAt = parseUtcStartOfDate(endsAtRaw);
  if (!endsAt) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=fiche`, "error", t("admin.client_action.invalid_expiry_date")));
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
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=fiche`, "error", result.message));
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=fiche`, "ok", t("admin.client_action.expiry_date_updated")));
}

export async function updateAdminClientForfaitPricingAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const subscriptionId = String(formData.get("subscription_id") ?? "").trim();
  if (!clientId || !subscriptionId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_package")));
  }

  const rowKeys = parseStringList(formData.getAll("forfait_activity_row_key"));
  const activities: Array<{
    course_type_id: string;
    loyalty_discount_per_hour_ttc: string;
    family_discount_per_hour_ttc: string;
    short_commitment_supplement_per_hour_ttc: string;
    second_course_weekly_discount_per_hour_ttc: string;
  }> = [];
  for (const rowKey of rowKeys) {
    const courseTypeId = String(formData.get(`forfait_course_type_id_${rowKey}`) ?? "").trim();
    const loyaltyRaw = String(formData.get(`forfait_loyalty_discount_per_hour_ttc_${rowKey}`) ?? "").trim();
    const familyRaw = String(formData.get(`forfait_family_discount_per_hour_ttc_${rowKey}`) ?? "").trim();
    const shortCommitmentRaw = String(formData.get(`forfait_short_commitment_supplement_per_hour_ttc_${rowKey}`) ?? "").trim();
    const secondCourseWeeklyRaw = String(formData.get(`forfait_second_course_weekly_discount_per_hour_ttc_${rowKey}`) ?? "").trim();
    const loyalty = loyaltyRaw ? parseNonNegativeDecimal(loyaltyRaw.replace(",", ".")) : 0;
    const family = familyRaw ? parseNonNegativeDecimal(familyRaw.replace(",", ".")) : 0;
    const shortCommitment = shortCommitmentRaw ? parseNonNegativeDecimal(shortCommitmentRaw.replace(",", ".")) : 0;
    const secondCourseWeekly = secondCourseWeeklyRaw ? parseNonNegativeDecimal(secondCourseWeeklyRaw.replace(",", ".")) : 0;
    if (!courseTypeId || loyalty === null || family === null || shortCommitment === null || secondCourseWeekly === null) {
      redirect(
        appendQueryMessage(
          `/admin/clients/${clientId}?tab=fiche&subscription_modal=forfait_pricing&subscription_id=${subscriptionId}`,
          "error",
          t("admin.client_action.invalid_forfait_pricing_values"),
        ),
      );
    }
    activities.push({
      course_type_id: courseTypeId,
      loyalty_discount_per_hour_ttc: loyalty.toFixed(2),
      family_discount_per_hour_ttc: family.toFixed(2),
      short_commitment_supplement_per_hour_ttc: shortCommitment.toFixed(2),
      second_course_weekly_discount_per_hour_ttc: secondCourseWeekly.toFixed(2),
    });
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/clients/${clientId}/subscriptions/${subscriptionId}/forfait-pricing`,
    {
      method: "POST",
      body: JSON.stringify({
        activities,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=fiche`, "error", result.message));
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=fiche`, "ok", t("admin.client_action.forfait_pricing_updated")));
}

export async function cancelAdminClientSubscriptionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const subscriptionId = String(formData.get("subscription_id") ?? "").trim();
  const requestedRaw = String(formData.get("cancellation_requested_at") ?? "").trim();
  const immediateCancel = checkboxField(formData, "immediate_cancel");
  const confirmImmediate = checkboxField(formData, "confirm_immediate");
  if (!clientId || !subscriptionId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_subscription")));
  }
  const requestedAt = parseUtcStartOfDate(requestedRaw);
  const modalName = immediateCancel ? "cancel_now" : "cancel";
  if (!requestedAt) {
    redirect(
      appendQueryMessage(
        `/admin/clients/${clientId}?tab=fiche&subscription_modal=${modalName}&subscription_id=${subscriptionId}`,
        "error",
        t("admin.client_action.invalid_cancellation_date"),
      ),
    );
  }
  if (immediateCancel && !confirmImmediate) {
    redirect(
      appendQueryMessage(
        `/admin/clients/${clientId}?tab=fiche&subscription_modal=${modalName}&subscription_id=${subscriptionId}`,
        "error",
        t("admin.client_action.immediate_cancellation_confirmation_required"),
      ),
    );
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
    const conflictFlag = result.status === 409 ? "&cancel_conflict=1" : "";
    redirect(
      appendQueryMessage(
        `/admin/clients/${clientId}?tab=fiche&subscription_modal=${modalName}&subscription_id=${subscriptionId}${conflictFlag}`,
        "error",
        result.message,
      ),
    );
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(appendQueryMessage(
    `/admin/clients/${clientId}?tab=fiche`,
    "ok",
    immediateCancel ? t("admin.client_action.immediate_cancellation_saved") : t("admin.client_action.cancellation_saved"),
  ));
}

export async function setupAdminClientSubscriptionBillingAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const subscriptionId = String(formData.get("subscription_id") ?? "").trim();
  if (!clientId || !subscriptionId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_subscription")));
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
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=fiche`, "error", result.message));
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=fiche`, "ok", t("admin.client_action.billing_setup_updated")));
}

export async function updateAdminClientManualCreditAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const creditTypeId = String(formData.get("credit_type_id") ?? "").trim();
  const creditsCountRaw = String(formData.get("credits_count") ?? "").trim();
  const creditsCount = parseNonNegativeInt(creditsCountRaw);

  if (!clientId || !creditTypeId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_credit_type")));
  }
  if (creditsCount === null) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=fiche`, "error", t("admin.client_action.invalid_manual_credit_count")));
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
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=fiche`, "error", result.message));
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=fiche`, "ok", t("admin.client_action.manual_credits_updated")));
}

export async function createAdminClientNoteAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const message = String(formData.get("message") ?? "").trim();
  if (!clientId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_client")));
  }
  if (!message) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=fiche`, "error", t("admin.client_action.empty_note")));
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
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=fiche`, "error", result.message));
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=fiche`, "ok", t("admin.client_action.note_added")));
}

export async function refundAdminClientPaymentAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const paymentSource = String(formData.get("payment_source") ?? "").trim().toUpperCase();
  const paymentId = String(formData.get("payment_id") ?? "").trim();
  const reason = optionalField(formData, "reason");
  const returnTabRaw = String(formData.get("return_tab") ?? "").trim().toLowerCase();
  const returnTab = returnTabRaw === "factures" ? "factures" : "paiements";

  if (!clientId || !paymentSource || !paymentId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_payment")));
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
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", result.message));
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "ok", t("admin.client_action.credit_note_recorded")));
}

export async function refundAdminClientPaymentReceiptAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const receiptId = String(formData.get("receipt_id") ?? "").trim();
  const reason = optionalField(formData, "reason");
  const returnTabRaw = String(formData.get("return_tab") ?? "").trim().toLowerCase();
  const returnTab = returnTabRaw === "reservations" ? "reservations" : "reservations";

  if (!clientId || !receiptId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_receipt")));
  }

  const result = await backendRequest<{ source: string; payment_id: string }>(
    `/api/v1/admin/clients/${clientId}/payment-receipts/${receiptId}/refund`,
    {
      method: "POST",
      body: JSON.stringify({
        reason,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", result.message));
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "ok", t("admin.client_action.booking_refunded")));
}

export async function cancelAdminClientInvoiceAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const paymentSource = String(formData.get("payment_source") ?? "").trim().toUpperCase();
  const paymentId = String(formData.get("payment_id") ?? "").trim();
  const returnTabRaw = String(formData.get("return_tab") ?? "").trim().toLowerCase();
  const returnTab = returnTabRaw === "factures" ? "factures" : "paiements";

  if (!clientId || !paymentSource || !paymentId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_invoice")));
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
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", result.message));
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "ok", t("admin.client_action.invoice_cancelled")));
}

export async function createAdminClientRangeInvoiceAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const returnTabRaw = String(formData.get("return_tab") ?? "").trim().toLowerCase();
  const returnTab = returnTabRaw === "paiements" ? "paiements" : "factures";
  if (!clientId) {
    redirect("/admin/clients?error=Client%20invalide");
  }
  const generationModeRaw = String(formData.get("generation_mode") ?? "MANUAL").trim().toUpperCase();
  const generationMode = generationModeRaw === "AUTO" ? "AUTO" : "MANUAL";
  const invoiceStepRaw = String(formData.get("invoice_step") ?? "").trim();
  const invoiceStep = invoiceStepRaw === "2" ? "2" : "1";
  const includePending = String(formData.get("include_pending") ?? "true").trim().toLowerCase() !== "false";
  const includeCancelled = String(formData.get("include_cancelled") ?? "false").trim().toLowerCase() === "true";
  const layoutRaw = String(formData.get("layout") ?? "DETAILED").trim().toUpperCase();
  const layout = layoutRaw === "COMPILED" || layoutRaw === "CONDENSED" || layoutRaw === "GROUPED" ? "COMPILED" : "DETAILED";
  const groupAdjustmentsByType = parseCheckboxFlag(formData, "group_adjustments_by_type", false);
  const includeDiscountAdjustments = parseCheckboxFlag(formData, "include_discount_adjustments", true);
  const includeSupplementAdjustments = parseCheckboxFlag(formData, "include_supplement_adjustments", true);
  const publicNote = optionalField(formData, "public_note");
  const privateNote = optionalField(formData, "private_note");

  const autoCycleStartDate = optionalField(formData, "auto_cycle_start_date");
  const autoFrequencyRaw = String(formData.get("auto_frequency") ?? "MONTHLY").trim().toUpperCase();
  const autoFrequency = autoFrequencyRaw === "QUARTERLY" || autoFrequencyRaw === "YEARLY" ? autoFrequencyRaw : "MONTHLY";
  const autoBillingTimingRaw = String(formData.get("auto_billing_timing") ?? "UPCOMING_LESSONS").trim().toUpperCase();
  const autoBillingTiming = autoBillingTimingRaw === "PREVIOUS_LESSONS" ? "PREVIOUS_LESSONS" : "UPCOMING_LESSONS";
  const autoDueDateRuleTypeRaw = String(formData.get("auto_due_date_rule_type") ?? "SAME_DAY_ISSUE").trim().toUpperCase();
  const autoDueDateRuleType = autoDueDateRuleTypeRaw === "X_DAYS_AFTER_ISSUE" ? "X_DAYS_AFTER_ISSUE" : "SAME_DAY_ISSUE";
  const autoDueDateDaysOffsetRaw = String(formData.get("auto_due_date_days_offset") ?? "").trim();
  const autoLegalEntityId = optionalField(formData, "auto_legal_entity_id");

  const manualIssuedDate = String(formData.get("issued_date") ?? "").trim();
  const manualStartDate = String(formData.get("start_date") ?? "").trim();
  const manualEndDate = String(formData.get("end_date") ?? "").trim();
  const manualDueDate = String(formData.get("due_date") ?? "").trim();
  const manualNoDueDate = parseCheckboxFlag(formData, "no_due_date", false);

  const parseDate = (value: string): Date | null => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      return null;
    }
    const parsed = new Date(`${value}T00:00:00.000Z`);
    if (Number.isNaN(parsed.getTime())) {
      return null;
    }
    return parsed;
  };

  const redirectInvoiceWizardError = (globalMessage: string, fieldErrors: Record<string, string>, targetStep: "1" | "2"): never => {
    const params = new URLSearchParams();
    params.set("tab", returnTab);
    params.set("payment_modal", "invoice_range");
    params.set("payment_return_tab", returnTab);
    params.set("invoice_step", targetStep);
    params.set("generation_mode", generationMode);
    if (manualIssuedDate) {
      params.set("issued_date", manualIssuedDate);
    }
    if (manualStartDate) {
      params.set("start_date", manualStartDate);
    }
    if (manualEndDate) {
      params.set("end_date", manualEndDate);
    }
    if (manualDueDate) {
      params.set("due_date", manualDueDate);
    }
    params.set("no_due_date", manualNoDueDate ? "true" : "false");
    params.set("include_pending", includePending ? "true" : "false");
    params.set("include_cancelled", includeCancelled ? "true" : "false");
    params.set("layout", layout);
    params.set("group_adjustments_by_type", groupAdjustmentsByType ? "true" : "false");
    params.set("include_discount_adjustments", includeDiscountAdjustments ? "true" : "false");
    params.set("include_supplement_adjustments", includeSupplementAdjustments ? "true" : "false");
    if (autoCycleStartDate) {
      params.set("auto_cycle_start_date", autoCycleStartDate);
    }
    params.set("auto_frequency", autoFrequency);
    params.set("auto_billing_timing", autoBillingTiming);
    params.set("auto_due_date_rule_type", autoDueDateRuleType);
    if (autoDueDateDaysOffsetRaw) {
      params.set("auto_due_date_days_offset", autoDueDateDaysOffsetRaw);
    }
    if (autoLegalEntityId) {
      params.set("auto_legal_entity_id", autoLegalEntityId);
    }
    if (publicNote) {
      params.set("public_note", publicNote);
    }
    if (privateNote) {
      params.set("private_note", privateNote);
    }
    params.set("invoice_error_global", globalMessage);
    if (Object.keys(fieldErrors).length > 0) {
      params.set("invoice_error_fields", JSON.stringify(fieldErrors));
    }
    redirect(`/admin/clients/${clientId}?${params.toString()}`);
  };

  if (generationMode === "AUTO") {
    const fieldErrors: Record<string, string> = {};
    if (!autoCycleStartDate || !parseDate(autoCycleStartDate)) {
      fieldErrors.auto_cycle_start_date = t("admin.client_detail.invoice_error_cycle_start_required");
    }
    if (!autoLegalEntityId) {
      fieldErrors.auto_legal_entity_id = t("admin.client_detail.invoice_error_legal_entity_required");
    }
    const autoDueDateDaysOffsetParsed = Number.parseInt(autoDueDateDaysOffsetRaw, 10);
    if (autoDueDateRuleType === "X_DAYS_AFTER_ISSUE") {
      if (!Number.isFinite(autoDueDateDaysOffsetParsed) || autoDueDateDaysOffsetParsed < 0) {
        fieldErrors.auto_due_date_days_offset = t("admin.client_detail.invoice_error_due_days_invalid");
      }
    }
    if (Object.keys(fieldErrors).length > 0) {
      redirectInvoiceWizardError(t("admin.client_detail.invoice_fix_errors"), fieldErrors, "1");
    }

    const ruleResult = await backendRequest<AdminClientAutoInvoiceRuleOut>(
      `/api/v1/admin/clients/${clientId}/invoice-auto-rules`,
      {
        method: "POST",
        body: JSON.stringify({
          cycle_start_date: autoCycleStartDate,
          frequency: autoFrequency,
          billing_timing: autoBillingTiming,
          due_date_rule_type: autoDueDateRuleType,
          due_date_days_offset: autoDueDateRuleType === "X_DAYS_AFTER_ISSUE" ? autoDueDateDaysOffsetParsed : null,
          include_pending_lines: includePending,
          include_cancelled_lines: includeCancelled,
          legal_entity_id: autoLegalEntityId,
          status: "ACTIVE",
        }),
      },
      token,
    );
    if (!ruleResult.ok) {
      const autoFieldErrors: Record<string, string> = {};
      const normalizedRuleError = (ruleResult.message || "").toLowerCase();
      if (normalizedRuleError.includes("due_date_days_offset")) {
        autoFieldErrors.auto_due_date_days_offset = t("admin.client_detail.invoice_error_due_days_required");
      }
      if (normalizedRuleError.includes("legal entity")) {
        autoFieldErrors.auto_legal_entity_id = t("admin.client_detail.invoice_error_legal_entity_invalid");
      }
      redirectInvoiceWizardError(ruleResult.message || t("admin.client_detail.invoice_error_auto_save_failed"), autoFieldErrors, "1");
    }
    revalidatePath(`/admin/clients/${clientId}`);
    redirect(`/admin/clients/${clientId}?tab=${returnTab}&ok=${encodeURIComponent(t("admin.client_detail.invoice_auto_rule_saved"))}`);
  }

  const manualFieldErrors: Record<string, string> = {};
  const issuedAt = parseDate(manualIssuedDate);
  const startAt = parseDate(manualStartDate);
  const endAt = parseDate(manualEndDate);
  const dueAt = parseDate(manualDueDate);
  if (!issuedAt) {
    manualFieldErrors.issued_date = t("admin.client_detail.invoice_error_issued_date_required");
  }
  if (!startAt) {
    manualFieldErrors.start_date = t("admin.client_detail.invoice_error_start_date_required");
  }
  if (!endAt) {
    manualFieldErrors.end_date = t("admin.client_detail.invoice_error_end_date_required");
  }
  if (!manualNoDueDate && !dueAt) {
    manualFieldErrors.due_date = t("admin.client_detail.invoice_error_due_date_required");
  }
  if (startAt && endAt && endAt.getTime() < startAt.getTime()) {
    manualFieldErrors.end_date = t("admin.client_detail.invoice_error_end_before_start");
  }
  const resolvedDueAt = manualNoDueDate ? issuedAt : dueAt;
  if (issuedAt && resolvedDueAt && resolvedDueAt.getTime() < issuedAt.getTime()) {
    manualFieldErrors.due_date = t("admin.client_detail.invoice_error_due_before_issued");
  }
  if (Object.keys(manualFieldErrors).length > 0) {
    redirectInvoiceWizardError(t("admin.client_detail.invoice_fix_errors"), manualFieldErrors, invoiceStep);
  }

  const result = await backendRequest<AdminRangeInvoiceOut>(
    `/api/v1/admin/clients/${clientId}/payments/invoice-range`,
    {
      method: "POST",
      body: JSON.stringify({
        issued_date: manualIssuedDate,
        start_date: manualStartDate,
        end_date: manualEndDate,
        due_date: manualNoDueDate ? manualIssuedDate : manualDueDate,
        no_due_date: manualNoDueDate,
        include_pending: includePending,
        include_cancelled: includeCancelled,
        layout,
        generation_mode: "MANUAL",
        group_adjustments_by_type: groupAdjustmentsByType,
        include_discount_adjustments: includeDiscountAdjustments,
        include_supplement_adjustments: includeSupplementAdjustments,
        auto_cycle_start_date: autoCycleStartDate,
        auto_period_scope: autoBillingTiming === "PREVIOUS_LESSONS" ? "PAST" : "FUTURE",
        auto_frequency: "MONTHLY",
        auto_repeat_every: autoFrequency === "YEARLY" ? 12 : autoFrequency === "QUARTERLY" ? 3 : 1,
        auto_layout_style: "NORMAL",
        auto_include_previous_balance: true,
        auto_send_email: false,
        auto_footer_note: null,
        auto_exclude_pack_subscription_lines: true,
        invoice_number: optionalField(formData, "invoice_number"),
        public_note: publicNote,
        private_note: privateNote,
      }),
    },
    token,
  );

  if (!result.ok) {
    const manualBackendFieldErrors: Record<string, string> = {};
    const normalizedManualError = (result.message || "").toLowerCase();
    if (normalizedManualError.includes("invalid date range")) {
      manualBackendFieldErrors.end_date = t("admin.client_detail.invoice_error_end_before_start");
    }
    if (normalizedManualError.includes("due date must")) {
      manualBackendFieldErrors.due_date = t("admin.client_detail.invoice_error_due_before_issued");
    }
    redirectInvoiceWizardError(result.message || t("admin.client_detail.invoice_error_create_failed"), manualBackendFieldErrors, "2");
  }
  const invoiceData = result.ok ? result.data : null;
  if (!invoiceData) {
    throw new Error("Invoice creation returned no payload.");
  }

  const pdfUrl = new URL(`${backendUrl()}/api/v1/admin/clients/${clientId}/payments/invoice-range`);
  pdfUrl.searchParams.set("start_date", invoiceData.start_date);
  pdfUrl.searchParams.set("end_date", invoiceData.end_date);
  pdfUrl.searchParams.set("issued_date", invoiceData.issued_date);
  pdfUrl.searchParams.set("due_date", invoiceData.due_date);
  pdfUrl.searchParams.set("no_due_date", invoiceData.no_due_date ? "true" : "false");
  pdfUrl.searchParams.set("include_pending", invoiceData.include_pending ? "true" : "false");
  pdfUrl.searchParams.set("include_cancelled", invoiceData.include_cancelled ? "true" : "false");
  pdfUrl.searchParams.set("layout", invoiceData.layout);
  pdfUrl.searchParams.set("generation_mode", invoiceData.generation_mode);
  pdfUrl.searchParams.set("group_adjustments_by_type", invoiceData.group_adjustments_by_type ? "true" : "false");
  pdfUrl.searchParams.set("include_discount_adjustments", invoiceData.include_discount_adjustments ? "true" : "false");
  pdfUrl.searchParams.set("include_supplement_adjustments", invoiceData.include_supplement_adjustments ? "true" : "false");
  if (invoiceData.auto_cycle_start_date) {
    pdfUrl.searchParams.set("auto_cycle_start_date", invoiceData.auto_cycle_start_date);
  }
  pdfUrl.searchParams.set("auto_period_scope", invoiceData.auto_period_scope);
  pdfUrl.searchParams.set("auto_frequency", invoiceData.auto_frequency);
  pdfUrl.searchParams.set("auto_repeat_every", String(invoiceData.auto_repeat_every));
  pdfUrl.searchParams.set("auto_layout_style", invoiceData.auto_layout_style);
  pdfUrl.searchParams.set("auto_include_previous_balance", invoiceData.auto_include_previous_balance ? "true" : "false");
  pdfUrl.searchParams.set("auto_send_email", invoiceData.auto_send_email ? "true" : "false");
  pdfUrl.searchParams.set(
    "auto_exclude_pack_subscription_lines",
    invoiceData.auto_exclude_pack_subscription_lines ? "true" : "false",
  );
  if (invoiceData.auto_footer_note) {
    pdfUrl.searchParams.set("auto_footer_note", invoiceData.auto_footer_note);
  }
  pdfUrl.searchParams.set("invoice_number", invoiceData.invoice_number);
  pdfUrl.searchParams.set("invoice_status", invoiceData.invoice_status);
  pdfUrl.searchParams.set("persist_note", "false");
  if (invoiceData.public_note) {
    pdfUrl.searchParams.set("public_note", invoiceData.public_note);
  }
  if (invoiceData.private_note) {
    pdfUrl.searchParams.set("private_note", invoiceData.private_note);
  }

  await fetch(pdfUrl.toString(), {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  }).catch(() => undefined);

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(`/admin/clients/${clientId}?tab=${returnTab}&ok=${encodeURIComponent(t("admin.client_detail.invoice_created_added"))}`);
}

export async function updateAdminClientRangeInvoiceStatusAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const noteId = String(formData.get("note_id") ?? "").trim();
  const statusRaw = String(formData.get("status") ?? "").trim().toUpperCase();
  const returnTabRaw = String(formData.get("return_tab") ?? "").trim().toLowerCase();
  const returnTab = returnTabRaw === "paiements" ? "paiements" : "factures";

  if (!clientId || !noteId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_invoice")));
  }
  if (statusRaw !== "ISSUED" && statusRaw !== "PAID" && statusRaw !== "CANCELLED") {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", t("admin.client_action.invalid_invoice_status")));
  }

  const result = await backendRequest<AdminRangeInvoiceOut>(
    `/api/v1/admin/clients/${clientId}/invoices/range/${noteId}/status`,
    {
      method: "POST",
      body: JSON.stringify({
        status: statusRaw,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", result.message));
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "ok", t("admin.client_action.invoice_status_updated")));
}

export async function sendAdminClientRangeInvoiceEmailAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const noteId = String(formData.get("note_id") ?? "").trim();
  const kindRaw = String(formData.get("kind") ?? "INVOICE").trim().toUpperCase();
  const returnTabRaw = String(formData.get("return_tab") ?? "").trim().toLowerCase();
  const returnTab = returnTabRaw === "paiements" ? "paiements" : "factures";

  if (!clientId || !noteId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_invoice")));
  }

  const kind = kindRaw === "REMINDER" ? "REMINDER" : "INVOICE";
  const toEmails = emailListField(formData, "to_emails");
  const subject = optionalField(formData, "subject");
  const body = optionalField(formData, "body");
  const bodyFormat = String(formData.get("body_format") ?? "TEXT").trim().toUpperCase() === "HTML" ? "HTML" : "TEXT";
  const result = await backendRequest<AdminRangeInvoiceEmailOut>(
    `/api/v1/admin/clients/${clientId}/invoices/range/${noteId}/email`,
    {
      method: "POST",
      body: JSON.stringify({
        kind,
        to_emails: toEmails,
        subject,
        body,
        body_format: bodyFormat,
      }),
    },
    token,
  );

  if (!result.ok) {
    const modalUrl = new URLSearchParams({
      tab: returnTab,
      payment_modal: "invoice_email",
      payment_return_tab: returnTab,
      invoice_note_id: noteId,
      invoice_email_kind: kind,
      error: result.message,
    });
    redirect(`/admin/clients/${clientId}?${modalUrl.toString()}`);
  }

  revalidatePath(`/admin/clients/${clientId}`);
  const okMessage = kind === "REMINDER"
    ? t("admin.client_action.invoice_reminder_sent")
    : t("admin.client_action.invoice_sent");
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "ok", okMessage));
}

export async function sendAdminClientPaymentReceiptAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const receiptId = String(formData.get("receipt_id") ?? "").trim();
  const returnTabRaw = String(formData.get("return_tab") ?? "reservations").trim().toLowerCase();
  const returnTab = returnTabRaw === "factures" ? "factures" : "reservations";
  if (!clientId || !receiptId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_receipt")));
  }

  const result = await backendRequest<{ receipt_id: string; sent_at: string }>(
    `/api/v1/admin/clients/${clientId}/payment-receipts/${receiptId}/email`,
    {
      method: "POST",
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", result.message));
  }
  revalidatePath(`/admin/clients/${clientId}`);
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "ok", t("admin.client_action.receipt_resent")));
}

export async function generateAdminClientBookingFinalInvoiceAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const bookingId = String(formData.get("booking_id") ?? "").trim();
  const returnTabRaw = String(formData.get("return_tab") ?? "reservations").trim().toLowerCase();
  const returnTab = returnTabRaw === "factures" ? "factures" : "reservations";
  if (!clientId || !bookingId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_booking")));
  }

  const result = await backendRequest<AdminRangeInvoiceOut>(
    `/api/v1/admin/clients/${clientId}/bookings/${bookingId}/final-invoice`,
    {
      method: "POST",
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "error", result.message));
  }
  revalidatePath(`/admin/clients/${clientId}`);
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=${returnTab}`, "ok", t("admin.client_action.final_invoice_generated")));
}

export async function createAdminClientManualTransactionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const transactionType = String(formData.get("transaction_type") ?? "").trim().toUpperCase();
  const isPaymentTransaction = transactionType === "PAYMENT";
  const amountRaw = String(formData.get("amount_incl_vat") ?? "").trim().replace(",", ".");
  const vatRateRaw = String(formData.get("vat_rate") ?? (isPaymentTransaction ? "0" : "20")).trim().replace(",", ".");
  const occurredAtRaw = String(formData.get("occurred_at") ?? "").trim();
  const occurredAt = occurredAtRaw ? parseUtcStartOfDate(occurredAtRaw) : null;
  const amountInclVat = parseNonNegativeDecimal(amountRaw);
  const vatRate = parseNonNegativeDecimal(vatRateRaw);
  const paymentMethodCode = parsePaymentMethodCode(String(formData.get("payment_method_code") ?? ""));
  const legalEntityIdRaw = String(formData.get("legal_entity_id") ?? "").trim();
  const legalEntityId = legalEntityIdRaw ? parseUuid(legalEntityIdRaw) : null;
  const customReference = optionalField(formData, "reference");
  if (!clientId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_client")));
  }
  const reconciledInvoiceNoteIdsRaw = formData
    .getAll("reconciled_invoice_note_ids")
    .map((entry) => String(entry ?? "").trim())
    .filter((entry) => entry.length > 0);
  const reconciledInvoiceNoteIds: string[] = [];
  const seenReconciledInvoiceNoteIds = new Set<string>();
  for (const rawId of reconciledInvoiceNoteIdsRaw) {
    const parsedId = parseUuid(rawId);
    if (!parsedId) {
      redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "error", t("admin.client_action.invalid_reconciled_invoice")));
    }
    if (seenReconciledInvoiceNoteIds.has(parsedId)) {
      continue;
    }
    seenReconciledInvoiceNoteIds.add(parsedId);
    reconciledInvoiceNoteIds.push(parsedId);
  }
  const markReconciledInvoicesPaid = parseCheckboxFlag(formData, "mark_reconciled_invoices_paid", false);
  const sendReceiptEmail = parseCheckboxFlag(formData, "send_receipt_email", false);
  if (!["PAYMENT", "REFUND", "CHARGE", "DISCOUNT"].includes(transactionType)) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "error", t("admin.client_action.invalid_transaction_type")));
  }
  if (amountInclVat === null || amountInclVat <= 0) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "error", t("admin.client_action.invalid_amount")));
  }
  if (isPaymentTransaction && !paymentMethodCode) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "error", t("admin.client_action.manual_payment_method_required")));
  }
  if (legalEntityIdRaw && !legalEntityId) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "error", t("admin.client_action.invalid_legal_entity")));
  }
  if (!isPaymentTransaction && (vatRate === null || vatRate < 0 || vatRate > 100)) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "error", t("admin.client_action.invalid_vat_rate")));
  }
  if (occurredAtRaw && !occurredAt) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "error", t("admin.client_action.invalid_date")));
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
        reference: customReference,
        payment_method_code: paymentMethodCode,
        legal_entity_id: legalEntityId,
        student_id: optionalField(formData, "student_id"),
        amount_incl_vat: amountInclVat,
        vat_rate: isPaymentTransaction ? 0 : vatRate,
        currency: optionalField(formData, "currency"),
        reconciled_invoice_note_ids: reconciledInvoiceNoteIds,
        mark_reconciled_invoices_paid: markReconciledInvoicesPaid,
        send_receipt_email: sendReceiptEmail,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "error", result.message));
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "ok", t("admin.client_action.manual_transaction_added")));
}

export async function updateAdminClientManualTransactionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const transactionId = String(formData.get("transaction_id") ?? "").trim();
  const transactionType = String(formData.get("transaction_type") ?? "").trim().toUpperCase();
  const isPaymentTransaction = transactionType === "PAYMENT";
  const amountRaw = String(formData.get("amount_incl_vat") ?? "").trim().replace(",", ".");
  const vatRateRaw = String(formData.get("vat_rate") ?? (isPaymentTransaction ? "0" : "")).trim().replace(",", ".");
  const occurredAtRaw = String(formData.get("occurred_at") ?? "").trim();
  const occurredAt = occurredAtRaw ? parseUtcStartOfDate(occurredAtRaw) : null;
  const amountInclVat = parseNonNegativeDecimal(amountRaw);
  const vatRate = vatRateRaw ? parseNonNegativeDecimal(vatRateRaw) : null;
  const paymentMethodCode = parsePaymentMethodCode(String(formData.get("payment_method_code") ?? ""));
  const legalEntityIdRaw = String(formData.get("legal_entity_id") ?? "").trim();
  const legalEntityId = legalEntityIdRaw ? parseUuid(legalEntityIdRaw) : null;

  if (!clientId || !transactionId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_transaction")));
  }
  if (amountInclVat === null || amountInclVat <= 0) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "error", t("admin.client_action.invalid_amount")));
  }
  if (isPaymentTransaction && !paymentMethodCode) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "error", t("admin.client_action.manual_payment_method_required")));
  }
  if (legalEntityIdRaw && !legalEntityId) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "error", t("admin.client_action.invalid_legal_entity")));
  }
  if (!isPaymentTransaction && vatRateRaw && (vatRate === null || vatRate < 0 || vatRate > 100)) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "error", t("admin.client_action.invalid_vat_rate")));
  }
  if (occurredAtRaw && !occurredAt) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "error", t("admin.client_action.invalid_date")));
  }

  const result = await backendRequest<AdminClientPaymentOut>(
    `/api/v1/admin/clients/${clientId}/manual-transactions/${transactionId}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        occurred_at: occurredAt,
        label: optionalField(formData, "label"),
        description: optionalField(formData, "description"),
        category: optionalField(formData, "category"),
        reference: optionalField(formData, "reference"),
        student_id: optionalField(formData, "student_id"),
        amount_incl_vat: amountInclVat,
        vat_rate: isPaymentTransaction ? 0 : (vatRate ?? undefined),
        currency: optionalField(formData, "currency"),
        payment_method_code: paymentMethodCode,
        legal_entity_id: legalEntityId,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "error", result.message));
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "ok", t("admin.client_action.manual_transaction_updated")));
}

export async function updateAdminClientManualTransactionStatusAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const transactionId = String(formData.get("transaction_id") ?? "").trim();
  const nextStatus = String(formData.get("status") ?? "").trim().toUpperCase();
  const allowedStatuses = new Set(["CHECK_RECEIVED", "CHECK_DEPOSITED", "CHECK_REFUSED", "PAID", "COMPLETED", "CANCELLED"]);
  if (!clientId || !transactionId || !allowedStatuses.has(nextStatus)) {
    redirect(appendQueryMessage(clientId ? `/admin/clients/${clientId}?tab=paiements` : "/admin/clients", "error", adminReferralActionText(language, "invalid_payment_status")));
  }

  const result = await backendRequest<AdminClientPaymentOut>(
    `/api/v1/admin/clients/${clientId}/manual-transactions/${transactionId}/status`,
    {
      method: "PATCH",
      body: JSON.stringify({ status: nextStatus }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "error", result.message));
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "ok", adminReferralActionText(language, "payment_status_updated")));
}

export async function bulkUpdateAdminCheckDepositStatusAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const requestedReturnTo = String(formData.get("return_to") ?? "").trim();
  const returnTo = requestedReturnTo.startsWith("/admin/check-deposits") ? requestedReturnTo : "/admin/check-deposits";
  const targetStatus = String(formData.get("target_status") ?? "CHECK_DEPOSITED").trim().toUpperCase();
  if (targetStatus !== "CHECK_DEPOSITED" && targetStatus !== "CHECK_REFUSED" && targetStatus !== "PAID") {
    redirect(appendQueryMessage(returnTo, "error", adminReferralActionText(language, "invalid_target_status")));
  }
  const batchReference = String(formData.get("batch_reference") ?? "").trim() || null;
  const effectiveDate = String(formData.get("effective_date") ?? "").trim() || null;
  const transactionIds = formData
    .getAll("transaction_ids")
    .map((value) => parseUuid(String(value ?? "")))
    .filter((value): value is string => Boolean(value));

  let rows: Array<Record<string, string | number | null>> = [];
  const rawFile = formData.get("deposit_file");
  if (typeof File !== "undefined" && rawFile instanceof File && rawFile.size > 0) {
    const name = rawFile.name.toLowerCase();
    if (name.endsWith(".xlsx")) {
      rows = await checkDepositRowsFromSpreadsheet(rawFile);
    } else if (name.endsWith(".xls")) {
      redirect(appendQueryMessage(returnTo, "error", adminReferralActionText(language, "xls_unsupported")));
    } else {
      const text = await rawFile.text();
      rows = checkDepositRowsFromDelimitedText(text);
    }
  }

  if (transactionIds.length === 0 && rows.length === 0) {
    redirect(appendQueryMessage(returnTo, "error", adminReferralActionText(language, "select_checks_or_file")));
  }

  const result = await backendRequest<AdminCheckDepositBulkUpdateOut>(
    "/api/v1/admin/clients/check-deposits/bulk-status",
    {
      method: "POST",
      body: JSON.stringify({
        transaction_ids: transactionIds,
        rows,
        target_status: targetStatus,
        batch_reference: batchReference,
        effective_date: effectiveDate,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/check-deposits");
  revalidatePath("/admin/clients");
  const unmatchedDetails = result.data.unmatched_rows.slice(0, 4).join(" ; ");
  const extraCount = Math.max(result.data.unmatched_rows.length - 4, 0);
  const warning = result.data.unmatched_rows.length > 0
    ? ` (${adminReferralActionText(language, "check_rows_unmatched", {
        count: result.data.unmatched_rows.length,
        details: unmatchedDetails,
        extra: extraCount > 0 ? ` ; +${extraCount}` : "",
      })})`
    : "";
  redirect(appendQueryMessage(returnTo, "ok", adminReferralActionText(language, "check_rows_updated", { count: result.data.updated_count, warning })));
}

export async function validateAdminReferralRewardAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const rewardId = parseUuid(String(formData.get("reward_id") ?? ""));
  const referrerUserId = parseUuid(String(formData.get("referrer_user_id") ?? ""));
  const requestedReturnTo = String(formData.get("return_to") ?? "").trim();
  const returnTo = requestedReturnTo.startsWith("/admin/referrals") ? requestedReturnTo : "/admin/referrals";
  if (!rewardId || !referrerUserId) {
    redirect(appendQueryMessage(returnTo, "error", adminReferralActionText(language, "referral_incomplete")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/admin/clients/referrals/rewards/${encodeURIComponent(rewardId)}/referrer`,
    {
      method: "PATCH",
      body: JSON.stringify({ referrer_user_id: referrerUserId }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/referrals");
  revalidatePath("/admin/intakes");
  redirect(appendQueryMessage(returnTo, "ok", adminReferralActionText(language, "referral_validated")));
}

export async function recomputeAdminReferralRewardAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const rewardId = parseUuid(String(formData.get("reward_id") ?? ""));
  const requestedReturnTo = String(formData.get("return_to") ?? "").trim();
  const returnTo = requestedReturnTo.startsWith("/admin/referrals") ? requestedReturnTo : "/admin/referrals";
  if (!rewardId) {
    redirect(appendQueryMessage(returnTo, "error", adminReferralActionText(language, "referral_not_found")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/admin/clients/referrals/rewards/${encodeURIComponent(rewardId)}/recompute`,
    { method: "POST" },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/referrals");
  redirect(appendQueryMessage(returnTo, "ok", adminReferralActionText(language, "referral_recomputed")));
}

export async function recomputeAllAdminReferralRewardsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const requestedReturnTo = String(formData.get("return_to") ?? "").trim();
  const returnTo = requestedReturnTo.startsWith("/admin/referrals") ? requestedReturnTo : "/admin/referrals";
  const result = await backendRequest<{
    scanned_count: number;
    updated_count: number;
    credit_granted_count: number;
  }>(
    "/api/v1/admin/clients/referrals/rewards/recompute",
    { method: "POST" },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/referrals");
  redirect(
    appendQueryMessage(
      returnTo,
      "ok",
      adminReferralActionText(language, "referrals_recomputed", {
        updated: result.data.updated_count,
        credits: result.data.credit_granted_count,
      }),
    ),
  );
}

export async function deleteAdminClientManualTransactionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const clientId = String(formData.get("client_id") ?? "").trim();
  const transactionId = String(formData.get("transaction_id") ?? "").trim();
  if (!clientId || !transactionId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_transaction")));
  }

  const result = await backendRequest<Record<string, never>>(
    `/api/v1/admin/clients/${clientId}/manual-transactions/${transactionId}`,
    {
      method: "DELETE",
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "error", result.message));
  }

  revalidatePath(`/admin/clients/${clientId}`);
  redirect(appendQueryMessage(`/admin/clients/${clientId}?tab=paiements`, "ok", t("admin.client_action.manual_transaction_deleted")));
}

export async function createAdminClientAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const returnTo = safeAdminReturnPath(formData, "/admin/clients");
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const firstName = String(formData.get("first_name") ?? "").trim();
  const lastName = String(formData.get("last_name") ?? "").trim();
  const residence_country = String(formData.get("residence_country") ?? "FR").trim().toUpperCase();
  const preferred_language = supportedLanguageField(formData, "preferred_language");
  const preferred_currency = String(formData.get("preferred_currency") ?? "EUR").trim().toUpperCase();
  const timezone = String(formData.get("timezone") ?? "Europe/Paris").trim();
  const address_country = String(formData.get("address_country") ?? "FR").trim().toUpperCase();
  const client_kind_raw = String(formData.get("client_kind") ?? "ADULT").trim().toUpperCase();
  const client_kind = client_kind_raw === "CHILD" ? "CHILD" : "ADULT";
  const client_status = String(formData.get("client_status") ?? "").trim().toUpperCase() || "ACTIVE";
  const student_site = optionalField(formData, "student_site");
  const birthDateRaw = String(formData.get("birth_date") ?? "").trim();
  const addressLine = optionalField(formData, "address_line");
  const city = optionalField(formData, "city");

  if (!firstName || !lastName || !address_country) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.client_action.required_identity_country")));
  }

  const isChildClient = client_kind === "CHILD";
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
    preferred_language,
    preferred_currency,
    timezone,
    portal_contact_visible: isChildClient ? false : checkboxFieldWithDefault(formData, "portal_contact_visible", true),
    email_opt_in: isChildClient ? false : checkboxFieldWithDefault(formData, "email_opt_in", true),
    sms_opt_in: isChildClient ? false : checkboxFieldWithDefault(formData, "sms_opt_in", true),
    lesson_reminder_email_opt_in: isChildClient ? false : checkboxFieldWithDefault(formData, "lesson_reminder_email_opt_in", true),
    lesson_reminder_sms_opt_in: isChildClient ? false : checkboxFieldWithDefault(formData, "lesson_reminder_sms_opt_in", false),
    client_status,
    student_site,
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
    const newAdultPreferredLanguage = supportedLanguageField(formData, "adult_preferred_language", preferred_language);
    const newAdultCurrency = String(formData.get("adult_preferred_currency") ?? "EUR").trim().toUpperCase();
    const newAdultTimezone = String(formData.get("adult_timezone") ?? "Europe/Paris").trim();
    const newAdultAddressCountry = String(formData.get("adult_address_country") ?? "FR").trim().toUpperCase();
    const newAdultStatus = String(formData.get("adult_client_status") ?? "").trim().toUpperCase() || "ACTIVE";
    let createdAdultId: string | null = null;

    const adultsToLink: Array<{ adultId: string; isBillingRecipient: boolean }> = [];

    if (existingAdultId) {
      adultsToLink.push({ adultId: existingAdultId, isBillingRecipient: billingForExistingAdult });
    }

    if (newAdultEmail || newAdultFirstName || newAdultLastName) {
      if (!newAdultFirstName || !newAdultLastName) {
        redirect(appendQueryMessage(`/admin/clients/${createdClientId}?tab=famille`, "error", t("admin.client_action.adult_first_last_name_required")));
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
            preferred_language: newAdultPreferredLanguage,
            preferred_currency: newAdultCurrency,
            timezone: newAdultTimezone,
            client_status: newAdultStatus,
            student_site,
            is_active: isActiveFromClientStatus(newAdultStatus),
          }),
        },
        token,
      );

      if (!createAdultResult.ok) {
        redirect(appendQueryMessage(`/admin/clients/${createdClientId}?tab=famille`, "error", createAdultResult.message));
      }

      createdAdultId = createAdultResult.data.id;
      adultsToLink.push({ adultId: createAdultResult.data.id, isBillingRecipient: false });
    }

    if (adultsToLink.length > 0 && !adultsToLink.some((item) => item.isBillingRecipient)) {
      if (createdAdultId) {
        const createdAdultIndex = adultsToLink.findIndex((item) => item.adultId === createdAdultId);
        if (createdAdultIndex >= 0) {
          adultsToLink[createdAdultIndex] = { ...adultsToLink[createdAdultIndex], isBillingRecipient: true };
        }
      } else {
        adultsToLink[0] = { ...adultsToLink[0], isBillingRecipient: true };
      }
    }

    for (const item of adultsToLink) {
      const linkResult = await backendRequest<{ id: string }>(
        "/api/v1/admin/clients/family/links",
        {
          method: "POST",
          body: JSON.stringify({
            adult_client_id: item.adultId,
            child_client_id: createdClientId,
            relationship_label: relationshipLabel,
            is_billing_recipient: item.isBillingRecipient,
          }),
        },
        token,
      );
      if (!linkResult.ok) {
        redirect(appendQueryMessage(`/admin/clients/${createdClientId}?tab=famille`, "error", linkResult.message));
      }
    }
  }

  revalidatePath("/admin/clients");
  revalidatePath(`/admin/clients/${createdClientId}`);
  redirect(
    appendQueryMessage(
      `/admin/clients/${createdClientId}?tab=famille`,
      "ok",
      t("admin.client_action.client_account_created_password_pending"),
    ),
  );
}

export async function createChildForAdultAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const adultClientId = String(formData.get("adult_client_id") ?? "").trim();
  if (!adultClientId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_adult")));
  }

  const email = String(formData.get("child_email") ?? "").trim().toLowerCase();
  const firstName = String(formData.get("child_first_name") ?? "").trim();
  const lastName = String(formData.get("child_last_name") ?? "").trim();
  const residence_country = String(formData.get("child_residence_country") ?? "FR").trim().toUpperCase();
  const preferred_language = supportedLanguageField(formData, "child_preferred_language");
  const preferred_currency = String(formData.get("child_preferred_currency") ?? "EUR").trim().toUpperCase();
  const timezone = String(formData.get("child_timezone") ?? "Europe/Paris").trim();
  const address_country = String(formData.get("child_address_country") ?? "FR").trim().toUpperCase();
  const birthDateRaw = String(formData.get("child_birth_date") ?? "").trim();
  const relationship_label = optionalField(formData, "relationship_label");
  const billingRecipient = checkboxField(formData, "is_billing_recipient");
  const childStatus = String(formData.get("child_client_status") ?? "").trim().toUpperCase() || "ACTIVE";
  const childStudentSite = optionalField(formData, "child_student_site");

  if (!firstName || !lastName || !residence_country || !preferred_currency || !timezone || !address_country) {
    redirect(appendQueryMessage(`/admin/clients/${adultClientId}?tab=famille`, "error", t("admin.client_action.incomplete_child_info")));
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
        portal_contact_visible: false,
        email_opt_in: false,
        sms_opt_in: false,
        lesson_reminder_email_opt_in: false,
        lesson_reminder_sms_opt_in: false,
        residence_country,
        preferred_language,
        preferred_currency,
        timezone,
        client_status: childStatus,
        student_site: childStudentSite,
        is_active: isActiveFromClientStatus(childStatus),
      }),
    },
    token,
  );

  if (!createResult.ok) {
    redirect(appendQueryMessage(`/admin/clients/${adultClientId}?tab=famille`, "error", createResult.message));
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
      appendQueryMessage(
        `/admin/clients/${adultClientId}?tab=famille`,
        "error",
        t("admin.client_action.child_created_link_failed", { message: linkResult.message }),
      ),
    );
  }

  revalidatePath("/admin/clients");
  revalidatePath(`/admin/clients/${adultClientId}`);
  revalidatePath(`/admin/clients/${childClientId}`);
  redirect(appendQueryMessage(
    `/admin/clients/${adultClientId}?tab=famille`,
    "ok",
    t("admin.client_action.child_created_and_linked_password_pending"),
  ));
}

export async function createAdultForChildAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const childClientId = String(formData.get("child_client_id") ?? "").trim();
  if (!childClientId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_child")));
  }

  const email = String(formData.get("adult_email") ?? "").trim().toLowerCase();
  const firstName = String(formData.get("adult_first_name") ?? "").trim();
  const lastName = String(formData.get("adult_last_name") ?? "").trim();
  const residence_country = String(formData.get("adult_residence_country") ?? "FR").trim().toUpperCase();
  const preferred_language = supportedLanguageField(formData, "adult_preferred_language");
  const preferred_currency = String(formData.get("adult_preferred_currency") ?? "EUR").trim().toUpperCase();
  const timezone = String(formData.get("adult_timezone") ?? "Europe/Paris").trim();
  const address_country = String(formData.get("adult_address_country") ?? "FR").trim().toUpperCase();
  const adultStatus = String(formData.get("adult_client_status") ?? "").trim().toUpperCase() || "ACTIVE";
  const adultStudentSite = optionalField(formData, "adult_student_site");
  const relationship_label = optionalField(formData, "relationship_label");
  const adultAddressLine = optionalField(formData, "adult_address_line");
  const adultCity = optionalField(formData, "adult_city");

  if (!firstName || !lastName || !address_country) {
    redirect(appendQueryMessage(`/admin/clients/${childClientId}?tab=famille`, "error", t("admin.client_action.incomplete_adult_info")));
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
        preferred_language,
        preferred_currency,
        timezone,
        client_status: adultStatus,
        student_site: adultStudentSite,
        is_active: isActiveFromClientStatus(adultStatus),
      }),
    },
    token,
  );

  if (!createResult.ok) {
    redirect(appendQueryMessage(`/admin/clients/${childClientId}?tab=famille`, "error", createResult.message));
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
      appendQueryMessage(
        `/admin/clients/${childClientId}?tab=famille`,
        "error",
        t("admin.client_action.adult_created_link_failed", { message: linkResult.message }),
      ),
    );
  }

  revalidatePath("/admin/clients");
  revalidatePath(`/admin/clients/${childClientId}`);
  revalidatePath(`/admin/clients/${adultClientId}`);
  redirect(appendQueryMessage(
    `/admin/clients/${childClientId}?tab=famille`,
    "ok",
    t("admin.client_action.adult_created_and_linked_password_pending"),
  ));
}

export async function linkExistingFamilyMembersAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const adultClientId = String(formData.get("adult_client_id") ?? "").trim();
  const childClientId = String(formData.get("child_client_id") ?? "").trim();
  const returnClientId = String(formData.get("return_client_id") ?? "").trim() || adultClientId || childClientId;
  const relationship_label = optionalField(formData, "relationship_label");
  const isBillingRecipient = checkboxField(formData, "is_billing_recipient");

  if (!adultClientId || !childClientId || !returnClientId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_family_link")));
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
    redirect(appendQueryMessage(`/admin/clients/${returnClientId}?tab=famille`, "error", result.message));
  }

  revalidatePath(`/admin/clients/${returnClientId}`);
  revalidatePath(`/admin/clients/${adultClientId}`);
  revalidatePath(`/admin/clients/${childClientId}`);
  redirect(appendQueryMessage(`/admin/clients/${returnClientId}?tab=famille`, "ok", t("admin.client_action.family_members_linked")));
}

export async function setFamilyBillingRecipientAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const linkId = String(formData.get("link_id") ?? "").trim();
  const returnClientId = String(formData.get("return_client_id") ?? "").trim();
  if (!linkId || !returnClientId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_invoice_recipient")));
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
    redirect(appendQueryMessage(`/admin/clients/${returnClientId}?tab=famille`, "error", result.message));
  }

  revalidatePath(`/admin/clients/${returnClientId}`);
  redirect(appendQueryMessage(`/admin/clients/${returnClientId}?tab=famille`, "ok", t("admin.client_action.invoice_recipient_updated")));
}

export async function unlinkFamilyMembersAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const linkId = String(formData.get("link_id") ?? "").trim();
  const returnClientId = String(formData.get("return_client_id") ?? "").trim();
  if (!linkId || !returnClientId) {
    redirect(appendQueryMessage("/admin/clients", "error", t("admin.client_action.invalid_family_link")));
  }

  const result = await backendRequest<Record<string, never>>(
    `/api/v1/admin/clients/family/links/${linkId}`,
    {
      method: "DELETE",
    },
    token,
  );

  if (!result.ok && result.status !== 204) {
    redirect(appendQueryMessage(`/admin/clients/${returnClientId}?tab=famille`, "error", result.message));
  }

  revalidatePath(`/admin/clients/${returnClientId}`);
  redirect(appendQueryMessage(`/admin/clients/${returnClientId}?tab=famille`, "ok", t("admin.client_action.family_link_deleted")));
}

export async function bulkAdminClientsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const returnTo = safeAdminReturnPath(formData, "/admin/clients");
  const action = String(formData.get("bulk_action") ?? "").trim().toUpperCase();
  const isMessageAction =
    action === "EMAIL_CLIENTS" || action === "EMAIL_PARENTS" || action === "SMS_CLIENTS" || action === "SMS_PARENTS";
  const isEmailAction = action === "EMAIL_CLIENTS" || action === "EMAIL_PARENTS";
  const selectionScopeRaw = String(formData.get("selection_scope") ?? "PAGE").trim().toUpperCase();
  const selectionScope = selectionScopeRaw === "FILTERED" ? "FILTERED" : "PAGE";
  const clientIds = parseStringList(formData.getAll("client_ids"));
  const filteredClientIds = parseStringList(formData.getAll("filtered_client_ids"));
  const targetStatus = String(formData.get("target_status") ?? "").trim().toUpperCase();
  const groupId = String(formData.get("group_id") ?? "").trim();
  const filterSearch = optionalField(formData, "filter_search");
  const filterStatusRaw = String(formData.get("filter_status") ?? "").trim().toUpperCase();
  const filterStatus = filterStatusRaw && filterStatusRaw !== "ALL" ? filterStatusRaw : null;
  const filterStudentSiteRaw = String(formData.get("filter_student_site") ?? "").trim().toUpperCase();
  const filterStudentSite = filterStudentSiteRaw && filterStudentSiteRaw !== "ALL" ? filterStudentSiteRaw : null;
  const filterGroupId = String(formData.get("filter_group_id") ?? "").trim();
  const filterIncludeArchived = String(formData.get("filter_include_archived") ?? "").trim().toLowerCase() === "true";
  const filterActiveOnly = String(formData.get("filter_active_only") ?? "").trim().toLowerCase() === "true";
  const messageSubject = optionalField(formData, "message_subject");
  const messageBody = optionalField(formData, "message_body");
  const messageBodyFormatRaw = String(formData.get("message_body_format") ?? "TEXT").trim().toUpperCase();
  const messageBodyFormat = messageBodyFormatRaw === "HTML" ? "HTML" : "TEXT";

  if (selectionScope === "PAGE" && clientIds.length === 0) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.clients.bulk_alert_select_client")));
  }

  if (action === "EXPORT") {
    const exportIds = selectionScope === "FILTERED" ? filteredClientIds : clientIds;
    if (exportIds.length === 0) {
      redirect(appendQueryMessage(returnTo, "error", t("admin.clients.bulk_export_selection_required")));
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
    filter_student_site: filterStudentSite,
    filter_group_id: filterGroupId || null,
    filter_include_archived: filterIncludeArchived,
    filter_active_only: filterActiveOnly,
  };

  if (action === "UPDATE_STATUS") {
    if (!targetStatus) {
      redirect(appendQueryMessage(returnTo, "error", t("admin.clients.bulk_target_status_required")));
    }
    payload.target_status = targetStatus;
  }

  if (action === "ASSIGN_GROUP") {
    if (!groupId) {
      redirect(appendQueryMessage(returnTo, "error", t("admin.clients.bulk_alert_select_group")));
    }
    payload.group_id = groupId;
  }

  if (isMessageAction) {
    if (!messageBody) {
      redirect(
        appendQueryMessage(
          returnTo,
          "error",
          isEmailAction ? t("admin.clients.bulk_alert_subject_and_message") : t("admin.clients.bulk_alert_sms_message"),
        ),
      );
    }
    if (isEmailAction && !messageSubject) {
      redirect(appendQueryMessage(returnTo, "error", t("admin.clients.bulk_alert_subject_and_message")));
    }
    payload.message_subject = messageSubject;
    payload.message_body = messageBody;
    payload.message_body_format = messageBodyFormat;
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


export async function importMyMusicStaffFamiliesAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const returnTo = safeAdminReturnPath(formData, "/admin/clients?view=groups");
  const rawFile = formData.get("mms_file");
  if (!(rawFile instanceof File) || rawFile.size <= 0) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.clients.mms_import_select_file")));
  }
  if (!rawFile.name.toLowerCase().endsWith(".csv")) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.clients.mms_import_csv_required")));
  }

  const dryRun = checkboxField(formData, "dry_run");
  const uploadPayload = new FormData();
  uploadPayload.set("file", rawFile, rawFile.name);
  const query = new URLSearchParams({ dry_run: dryRun ? "true" : "false" });

  const result = await backendRequest<{
    dry_run: boolean;
    rows_seen: number;
    rows_imported: number;
    families_seen: number;
    parent_contacts_seen: number;
    parents_created: number;
    parents_updated: number;
    parents_reused: number;
    children_created: number;
    children_updated: number;
    children_reused: number;
    family_links_created: number;
    family_links_existing: number;
    group_name: string;
    warnings: string[];
  }>(
    `/api/v1/admin/clients/imports/my-music-staff-2025-2026?${query.toString()}`,
    {
      method: "POST",
      body: uploadPayload,
    },
    token,
    180000,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/clients");
  const summaryKey = dryRun ? "admin.clients.mms_import_preview_done" : "admin.clients.mms_import_done";
  redirect(
    appendQueryMessage(
      returnTo,
      "ok",
      t(summaryKey, {
        rows: result.data.rows_imported,
        families: result.data.families_seen,
        parents: result.data.parents_created + result.data.parents_reused,
        children: result.data.children_created + result.data.children_reused,
        links: result.data.family_links_created + result.data.family_links_existing,
      }),
    ),
  );
}

export async function createAdminClientGroupAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const returnTo = safeAdminReturnPath(formData, "/admin/clients?view=groups");
  const name = String(formData.get("name") ?? "").trim();
  const code = String(formData.get("code") ?? "").trim();
  const active = checkboxField(formData, "active");

  if (!name) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.clients.group_name_required")));
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
  redirect(appendQueryMessage(returnTo, "ok", t("admin.clients.group_created")));
}

export async function createAdminCollaboratorAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const first_name = String(formData.get("first_name") ?? "").trim();
  const last_name = String(formData.get("last_name") ?? "").trim();
  const teacherIsVatApplicable = checkboxField(formData, "teacher_is_vat_applicable");
  const teacherVatRate = optionalField(formData, "teacher_vat_rate");
  const payout_currency = String(formData.get("payout_currency") ?? "EUR").trim().toUpperCase();

  if (!email || !first_name || !last_name) {
    redirect(appendQueryMessage("/admin/professors", "error", t("admin.professor_action.email_first_last_required")));
  }

  const permissions = parseProfessorPermissions(formData);
  permissions.can_view_planning = true;
  permissions.can_take_attendance = true;

  const payload = {
    email,
    first_name,
    last_name,
    phone: optionalField(formData, "phone"),
    siret: optionalField(formData, "siret"),
    iban: optionalField(formData, "iban"),
    address_line: optionalField(formData, "address_line"),
    teacher_invoice_counter: Number.parseInt(String(formData.get("teacher_invoice_counter") ?? "1"), 10) || 1,
    teacher_is_vat_applicable: teacherIsVatApplicable,
    teacher_vat_rate: teacherIsVatApplicable ? teacherVatRate : null,
    teacher_siret: optionalField(formData, "teacher_siret"),
    teacher_iban: optionalField(formData, "teacher_iban"),
    teacher_company_name: optionalField(formData, "teacher_company_name"),
    teacher_company_address: optionalField(formData, "teacher_company_address"),
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
  redirect(appendQueryMessage("/admin/professors", "ok", t("admin.professor_action.created_access_email_sent")));
}

export async function uploadAdminCollaboratorContractAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const professorId = String(formData.get("professor_id") ?? "").trim();
  const returnTabRaw = String(formData.get("return_tab") ?? "profil").trim();
  const returnTab = returnTabRaw === "droits" || returnTabRaw === "tarifs" || returnTabRaw === "planning" ? returnTabRaw : "profil";

  if (!professorId) {
    redirect(appendQueryMessage("/admin/professors", "error", t("admin.professor_action.invalid_collaborator")));
  }

  const returnTo = `/admin/professors/${professorId}?tab=${returnTab}`;
  const rawFile = formData.get("contract_file");
  if (!(rawFile instanceof File) || rawFile.size <= 0) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.professor_action.select_contract_pdf")));
  }
  if (!rawFile.name.toLowerCase().endsWith(".pdf")) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.professor_action.contract_pdf_required")));
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
  redirect(appendQueryMessage(returnTo, "ok", t("admin.professor_action.contract_uploaded")));
}

export async function deleteAdminCollaboratorContractAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const professorId = String(formData.get("professor_id") ?? "").trim();
  const returnTabRaw = String(formData.get("return_tab") ?? "profil").trim();
  const returnTab = returnTabRaw === "droits" || returnTabRaw === "tarifs" || returnTabRaw === "planning" ? returnTabRaw : "profil";

  if (!professorId) {
    redirect(appendQueryMessage("/admin/professors", "error", t("admin.professor_action.invalid_collaborator")));
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
  redirect(appendQueryMessage(returnTo, "ok", t("admin.professor_action.contract_deleted")));
}

export async function sendAdminCollaboratorsMessageAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const returnTo = safeAdminReturnPath(formData, "/admin/professors");
  const collaboratorIds = parseStringList(formData.getAll("collaborator_ids"));
  const channelRaw = String(formData.get("channel") ?? "EMAIL").trim().toUpperCase();
  const channel = channelRaw === "SMS" ? "SMS" : "EMAIL";
  const subjectRaw = String(formData.get("subject") ?? "").trim();
  const body = String(formData.get("body") ?? "").trim();
  const bodyFormatRaw = String(formData.get("body_format") ?? "TEXT").trim().toUpperCase();
  const bodyFormat = bodyFormatRaw === "HTML" ? "HTML" : "TEXT";
  const subject = channel === "SMS" ? subjectRaw || t("admin.professor_action.default_sms_subject") : subjectRaw;

  if (collaboratorIds.length === 0) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.professor_action.select_at_least_one_collaborator")));
  }
  if (!body || (channel === "EMAIL" && !subject)) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.professor_action.subject_message_required")));
  }

  const result = await backendRequest<{ channel: "EMAIL" | "SMS"; requested_count: number; sent_count: number; skipped_count: number }>(
    "/api/v1/admin/collaborators/messages",
    {
      method: "POST",
      body: JSON.stringify({
        collaborator_ids: collaboratorIds,
        channel,
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
      result.data.channel === "SMS"
        ? t("admin.professor_action.sms_logged_summary", {
            sent_count: result.data.sent_count,
            requested_count: result.data.requested_count,
          })
        : t("admin.professor_action.message_sent_summary", {
            sent_count: result.data.sent_count,
            requested_count: result.data.requested_count,
          }),
    ),
  );
}

function parseMoneyInput(raw: string): string | null {
  const normalized = raw.trim().replace(",", ".");
  if (!normalized) {
    return null;
  }
  if (!/^\d+(\.\d{1,2})?$/.test(normalized)) {
    return null;
  }
  return normalized;
}

export async function createAdminCollaboratorSalaryPaymentAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const returnTo = safeAdminReturnPath(formData, "/admin/salary-payments");
  const professorId = String(formData.get("professor_id") ?? "").trim();
  const referenceDate = String(formData.get("reference_date") ?? "").trim();
  const paymentDate = String(formData.get("payment_date") ?? "").trim();
  const invoiceNumber = String(formData.get("invoice_number") ?? "").trim();
  const paymentMethodRaw = String(formData.get("payment_method") ?? "BANK_TRANSFER").trim().toUpperCase();
  const paymentMethod = paymentMethodRaw === "CHEQUE" || paymentMethodRaw === "CASH" ? paymentMethodRaw : "BANK_TRANSFER";
  const amountExclVat = parseMoneyInput(String(formData.get("amount_excl_vat") ?? ""));
  const amountInclVat = parseMoneyInput(String(formData.get("amount_incl_vat") ?? ""));

  if (!professorId || !referenceDate || !paymentDate || !invoiceNumber || !amountExclVat || !amountInclVat) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.professor_action.salary_required_fields")));
  }

  const result = await backendRequest<AdminProfessorSalaryPaymentOut>(
    `/api/v1/admin/collaborators/${professorId}/salary-payments`,
    {
      method: "POST",
      body: JSON.stringify({
        reference_date: referenceDate,
        payment_date: paymentDate,
        invoice_number: invoiceNumber,
        payment_method: paymentMethod,
        amount_excl_vat: amountExclVat,
        amount_incl_vat: amountInclVat,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/professors");
  revalidatePath("/admin/salary-payments");
  redirect(appendQueryMessage(returnTo, "ok", t("admin.professor_action.salary_recorded")));
}

export async function updateAdminCollaboratorProfileAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const professorId = String(formData.get("professor_id") ?? "").trim();
  const returnTab = String(formData.get("return_tab") ?? "profil").trim() || "profil";
  if (!professorId) {
    redirect(appendQueryMessage("/admin/professors", "error", t("admin.professor_action.invalid_collaborator")));
  }

  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const first_name = String(formData.get("first_name") ?? "").trim();
  const last_name = String(formData.get("last_name") ?? "").trim();

  if (!email || !first_name || !last_name) {
    redirect(appendQueryMessage(`/admin/professors/${professorId}?tab=${returnTab}`, "error", t("admin.professor_action.email_first_last_required")));
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
    const activationMessageId = result.data.activation_email_message_id ?? "n/a";
    redirect(
      appendQueryMessage(
        `/admin/professors/${professorId}?tab=${returnTab}`,
        "ok",
        t("admin.professor_action.activation_email_sent", { message_id: activationMessageId }),
      ),
    );
  }

  redirect(appendQueryMessage(`/admin/professors/${professorId}?tab=${returnTab}`, "ok", t("admin.professor_action.profile_updated")));
}

export async function sendAdminCollaboratorPasswordLinkAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const professorId = String(formData.get("professor_id") ?? "").trim();
  const returnTab = String(formData.get("return_tab") ?? "profil").trim() || "profil";
  if (!professorId) {
    redirect(appendQueryMessage("/admin/professors", "error", t("admin.professor_action.invalid_collaborator")));
  }

  const result = await backendRequest<AdminCollaboratorSendPasswordOut>(
    `/api/v1/admin/collaborators/${professorId}/send-password`,
    {
      method: "POST",
    },
    token,
  );
  if (!result.ok) {
    redirect(`/admin/professors/${professorId}?tab=${returnTab}&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/professors");
  revalidatePath(`/admin/professors/${professorId}`);
  const expiresAtLabel = formatAdminDateTime(result.data.expires_at, language);
  redirect(appendQueryMessage(`/admin/professors/${professorId}?tab=${returnTab}`, "ok", t("admin.professor_action.password_link_sent", { expires_at: expiresAtLabel })));
}

export async function updateAdminCollaboratorPermissionsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const professorId = String(formData.get("professor_id") ?? "").trim();
  if (!professorId) {
    redirect(appendQueryMessage("/admin/professors", "error", t("admin.professor_action.invalid_collaborator")));
  }

  const payload = parseProfessorPermissions(formData);
  const isAdmin = checkboxField(formData, "is_admin");
  const teacherProfile = checkboxField(formData, "teacher_profile");
  const managerProfile = checkboxField(formData, "manager_profile");

  const result = await backendRequest<ProfessorPermissionOut>(
    `/api/v1/admin/collaborators/${professorId}/permissions`,
    {
      method: "PUT",
      body: JSON.stringify({ ...payload, is_admin: isAdmin, teacher_profile: teacherProfile, manager_profile: managerProfile }),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/professors/${professorId}?tab=droits&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/professors");
  revalidatePath(`/admin/professors/${professorId}`);
  redirect(appendQueryMessage(`/admin/professors/${professorId}?tab=droits`, "ok", t("admin.professor_action.permissions_updated")));
}

export async function updateAdminCollaboratorRatesAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const professorId = String(formData.get("professor_id") ?? "").trim();
  if (!professorId) {
    redirect(appendQueryMessage("/admin/professors", "error", t("admin.professor_action.invalid_collaborator")));
  }

  const currency = String(formData.get("currency_code") ?? "").trim().toUpperCase() || null;
  const effectiveFrom = String(formData.get("effective_from") ?? "").trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(effectiveFrom)) {
    redirect(appendQueryMessage(`/admin/professors/${professorId}?tab=tarifs`, "error", t("admin.professor_action.invalid_effective_date")));
  }

  const uiVersion = String(formData.get("pay_ui_version") ?? "").trim();
  if (uiVersion === "2" || uiVersion === "3") {
    const parseStructuredRules = (
      minValuesRaw: FormDataEntryValue[],
      maxValuesRaw: FormDataEntryValue[],
      rateValuesRaw: FormDataEntryValue[],
      label: string,
    ): Array<{ min_students: number; max_students: number | null; hourly_rate: number }> => {
      const minValues = minValuesRaw.map((value) => String(value ?? "").trim());
      const maxValues = maxValuesRaw.map((value) => String(value ?? "").trim());
      const rateValues = rateValuesRaw.map((value) => String(value ?? "").trim().replace(",", "."));
      const rowCount = Math.max(minValues.length, maxValues.length, rateValues.length);

      const rows: Array<{ min_students: number; max_students: number | null; hourly_rate: number }> = [];
      for (let index = 0; index < rowCount; index += 1) {
        const minRaw = minValues[index] ?? "";
        const maxRaw = maxValues[index] ?? "";
        const rateRaw = rateValues[index] ?? "";

        if (!minRaw && !maxRaw && !rateRaw) {
          continue;
        }

        const minStudents = parseNonNegativeInt(minRaw);
        if (minStudents === null) {
          redirect(appendQueryMessage(
            `/admin/professors/${professorId}?tab=tarifs`,
            "error",
            t("admin.professor_action.rule_invalid_min_line", { label, index: index + 1 }),
          ));
        }

        let maxStudents: number | null = null;
        if (maxRaw) {
          maxStudents = parseNonNegativeInt(maxRaw);
          if (maxStudents === null) {
            redirect(appendQueryMessage(
              `/admin/professors/${professorId}?tab=tarifs`,
              "error",
              t("admin.professor_action.rule_invalid_max_line", { label, index: index + 1 }),
            ));
          }
          if (maxStudents < minStudents) {
            redirect(appendQueryMessage(
              `/admin/professors/${professorId}?tab=tarifs`,
              "error",
              t("admin.professor_action.rule_min_gt_max_line", { label, index: index + 1 }),
            ));
          }
        }

        const hourlyRate = parseNonNegativeDecimal(rateRaw);
        if (hourlyRate === null) {
          redirect(appendQueryMessage(
            `/admin/professors/${professorId}?tab=tarifs`,
            "error",
            t("admin.professor_action.rule_invalid_rate_line", { label, index: index + 1 }),
          ));
        }

        rows.push({
          min_students: minStudents,
          max_students: maxStudents,
          hourly_rate: hourlyRate,
        });
      }

      rows.sort((a, b) => (a.min_students - b.min_students) || ((a.max_students ?? Number.MAX_SAFE_INTEGER) - (b.max_students ?? Number.MAX_SAFE_INTEGER)));
      for (let index = 1; index < rows.length; index += 1) {
        const previous = rows[index - 1];
        const current = rows[index];
        if (previous.max_students === null || current.min_students <= previous.max_students) {
          redirect(appendQueryMessage(
            `/admin/professors/${professorId}?tab=tarifs`,
            "error",
            t("admin.professor_action.rule_overlapping_ranges", { label }),
          ));
        }
      }

      return rows;
    };

    const baseHourlyRateRaw = String(formData.get("base_hourly_rate") ?? "").trim().replace(",", ".");
    const baseHourlyRate = parseNonNegativeDecimal(baseHourlyRateRaw);
    if (baseHourlyRate === null) {
      redirect(appendQueryMessage(`/admin/professors/${professorId}?tab=tarifs`, "error", t("admin.professor_action.invalid_base_hourly_rate")));
    }

    const rates: Array<{
      course_type_id: string | null;
      hourly_rate: number | null;
      rules: Array<{ min_students: number; max_students: number | null; hourly_rate: number }>;
      currency_code: string | null;
      valid_from?: string | null;
      valid_to?: string | null;
    }> = [
      {
        course_type_id: null,
        hourly_rate: baseHourlyRate,
        rules: [],
        currency_code: currency,
      },
    ];

    const clearCourseTypeIds: string[] = [];
    const courseTypeIds = parseStringList(formData.getAll("activity_course_type_id"));
    for (const courseTypeId of courseTypeIds) {
      const mode = String(formData.get(`activity_rate_mode_${courseTypeId}`) ?? "GENERAL")
        .trim()
        .toUpperCase();
      if (mode !== "SPECIFIC") {
        clearCourseTypeIds.push(courseTypeId);
        continue;
      }

      const activityLabel = t("admin.professor_action.activity_label", { course_type_id: courseTypeId });

      const activityRules = parseStructuredRules(
        formData.getAll(`activity_rule_min_${courseTypeId}`),
        formData.getAll(`activity_rule_max_${courseTypeId}`),
        formData.getAll(`activity_rule_rate_${courseTypeId}`),
        activityLabel,
      );
      const activityDefaultRateRaw = String(formData.get(`activity_default_rate_${courseTypeId}`) ?? "")
        .trim()
        .replace(",", ".");
      const activityDefaultRate = activityDefaultRateRaw ? parseNonNegativeDecimal(activityDefaultRateRaw) : null;
      if (activityDefaultRateRaw && activityDefaultRate === null) {
        redirect(appendQueryMessage(
          `/admin/professors/${professorId}?tab=tarifs`,
          "error",
          t("admin.professor_action.activity_invalid_base_rate", { label: activityLabel }),
        ));
      }
      if (activityDefaultRate === null && activityRules.length === 0) {
        redirect(appendQueryMessage(
          `/admin/professors/${professorId}?tab=tarifs`,
          "error",
          t("admin.professor_action.activity_define_at_least_one_bracket", { label: activityLabel }),
        ));
      }
      const validFrom = String(formData.get(`activity_valid_from_${courseTypeId}`) ?? "").trim() || effectiveFrom;
      if (!/^\d{4}-\d{2}-\d{2}$/.test(validFrom)) {
        redirect(appendQueryMessage(
          `/admin/professors/${professorId}?tab=tarifs`,
          "error",
          t("admin.professor_action.activity_invalid_start_date", { label: activityLabel }),
        ));
      }
      const validTo = String(formData.get(`activity_valid_to_${courseTypeId}`) ?? "").trim();
      if (validTo && !/^\d{4}-\d{2}-\d{2}$/.test(validTo)) {
        redirect(appendQueryMessage(
          `/admin/professors/${professorId}?tab=tarifs`,
          "error",
          t("admin.professor_action.activity_invalid_end_date", { label: activityLabel }),
        ));
      }
      if (validTo && validTo < validFrom) {
        redirect(appendQueryMessage(
          `/admin/professors/${professorId}?tab=tarifs`,
          "error",
          t("admin.professor_action.activity_end_before_start", { label: activityLabel }),
        ));
      }

      rates.push({
        course_type_id: courseTypeId,
        hourly_rate: activityDefaultRate,
        rules: activityRules,
        currency_code: currency,
        valid_from: validFrom,
        valid_to: validTo || null,
      });
    }

    const specificCourseTypeIds = new Set(
      rates
        .map((row) => row.course_type_id)
        .filter((row): row is string => typeof row === "string"),
    );
    const dedupClearCourseTypeIds = [...new Set(clearCourseTypeIds)].filter((courseTypeId) => !specificCourseTypeIds.has(courseTypeId));

    const result = await backendRequest<AdminProfessorRateOut[]>(
      `/api/v1/admin/collaborators/${professorId}/rates`,
      {
        method: "PUT",
        body: JSON.stringify({
          rates,
          effective_from: effectiveFrom,
          clear_course_type_ids: dedupClearCourseTypeIds,
        }),
      },
      token,
    );

    if (!result.ok) {
      redirect(appendQueryMessage(`/admin/professors/${professorId}?tab=tarifs`, "error", result.message));
    }

    revalidatePath("/admin/professors");
    revalidatePath(`/admin/professors/${professorId}`);
    redirect(appendQueryMessage(`/admin/professors/${professorId}?tab=tarifs`, "ok", t("admin.professor_action.hourly_rates_updated")));
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
        redirect(appendQueryMessage(
          `/admin/professors/${professorId}?tab=tarifs`,
          "error",
          t("admin.professor_action.invalid_rate_rule_for_activity", { activity: courseTypeToken }),
        ));
      }
      rules = parsedRules;
    } else {
      hourlyRate = parseNonNegativeDecimal(rateRaw.replace(",", "."));
      if (hourlyRate === null) {
        redirect(appendQueryMessage(
          `/admin/professors/${professorId}?tab=tarifs`,
          "error",
          t("admin.professor_action.invalid_hourly_rate_for_activity", { activity: courseTypeToken }),
        ));
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
    redirect(appendQueryMessage(`/admin/professors/${professorId}?tab=tarifs`, "error", result.message));
  }

  revalidatePath("/admin/professors");
  revalidatePath(`/admin/professors/${professorId}`);
  redirect(appendQueryMessage(`/admin/professors/${professorId}?tab=tarifs`, "ok", t("admin.professor_action.hourly_rates_updated")));
}

export async function upsertAdminCollaboratorContractGridAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const professorId = String(formData.get("professor_id") ?? "").trim();
  if (!professorId) {
    redirect(appendQueryMessage("/admin/professors", "error", t("admin.professor_action.invalid_collaborator")));
  }

  const gridId = String(formData.get("grid_id") ?? "").trim();
  const validFrom = String(formData.get("valid_from") ?? "").trim();
  const validTo = String(formData.get("valid_to") ?? "").trim();
  const locationCode = parseProfessorContractLocationCode(String(formData.get("location_code") ?? ""));
  const notes = optionalField(formData, "notes");
  const cloneFromGridIdRaw = String(formData.get("clone_from_grid_id") ?? "").trim();

  if (!/^\d{4}-\d{2}-\d{2}$/.test(validFrom)) {
    redirect(appendQueryMessage(`/admin/professors/${professorId}?tab=tarifs`, "error", t("admin.professor_action.invalid_contract_grid_start_date")));
  }
  if (validTo && !/^\d{4}-\d{2}-\d{2}$/.test(validTo)) {
    redirect(appendQueryMessage(`/admin/professors/${professorId}?tab=tarifs`, "error", t("admin.professor_action.invalid_contract_grid_end_date")));
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
      redirect(appendQueryMessage(
        `/admin/professors/${professorId}?tab=tarifs`,
        "error",
        t("admin.professor_action.grid_line_missing_activity", { index: index + 1 }),
      ));
    }

    const defaultRate = defaultRateRaw ? parseNonNegativeDecimal(defaultRateRaw) : null;
    if (defaultRateRaw && defaultRate === null) {
      redirect(appendQueryMessage(
        `/admin/professors/${professorId}?tab=tarifs`,
        "error",
        t("admin.professor_action.grid_line_invalid_default_rate", { index: index + 1 }),
      ));
    }

    const rules = parseHeadcountRules(rulesRaw);
    if (rules === null) {
      redirect(appendQueryMessage(
        `/admin/professors/${professorId}?tab=tarifs`,
        "error",
        t("admin.professor_action.grid_line_invalid_headcount_rules", { index: index + 1 }),
      ));
    }

    lines.push({
      course_type_id: courseTypeId,
      default_hourly_rate: defaultRate,
      rules,
    });
  }

  if (lines.length === 0 && !cloneFromGridIdRaw) {
    redirect(appendQueryMessage(`/admin/professors/${professorId}?tab=tarifs`, "error", t("admin.professor_action.grid_requires_line")));
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
    redirect(appendQueryMessage(`/admin/professors/${professorId}?tab=tarifs`, "error", result.message));
  }

  revalidatePath("/admin/professors");
  revalidatePath(`/admin/professors/${professorId}`);
  const message = gridId
    ? t("admin.professor_action.contract_grid_updated")
    : t("admin.professor_action.contract_grid_created");
  redirect(appendQueryMessage(`/admin/professors/${professorId}?tab=tarifs`, "ok", message));
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

function parseFormulaPayload(formData: FormData, t: UiTextResolver): Record<string, unknown> {
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
  const forfaitStartDateRaw = String(formData.get("forfait_start_date") ?? "").trim();
  const forfaitEndDateRaw = String(formData.get("forfait_end_date") ?? "").trim();
  const creditGrants = parseFormulaCreditGrants(formData);
  const creditsCount = creditGrants.reduce((sum, grant) => sum + grant.credits_count, 0);
  const entitlementIds = parseStringList(formData.getAll("entitlement_course_type_ids"));
  const paymentMethods = parseStringList(formData.getAll("payment_methods")).map((value) => value.toUpperCase());
  const options = parseStringList(String(formData.get("options_csv") ?? "").split(","));
  const restrictions = parseFormulaRestrictions(formData);

  if (!name) {
    throw new Error(t("admin.formula_action.name_required"));
  }
  if (price === null && kind !== "FORFAIT") {
    throw new Error(t("admin.formula_action.price_required"));
  }
  if (!currency) {
    throw new Error(t("admin.formula_action.currency_required"));
  }
  if (kind === "PACK" && creditGrants.length === 0) {
    throw new Error(t("admin.formula_action.credit_type_required"));
  }
  if (kind === "PACK" && creditsCount <= 0) {
    throw new Error(t("admin.formula_action.invalid_total_credits"));
  }
  if (kind === "PACK" && (packValidityMonths === null || packValidityMonths < 1 || packValidityMonths > 12)) {
    throw new Error(t("admin.formula_action.invalid_pack_validity"));
  }
  if (kind === "FORFAIT") {
    if (!forfaitStartDateRaw || !forfaitEndDateRaw) {
      throw new Error(t("admin.formula_action.forfait_dates_required"));
    }
    if (!parseUtcStartOfDate(forfaitStartDateRaw) || !parseUtcStartOfDate(forfaitEndDateRaw)) {
      throw new Error(t("admin.formula_action.invalid_forfait_dates"));
    }
    if (forfaitEndDateRaw <= forfaitStartDateRaw) {
      throw new Error(t("admin.formula_action.invalid_forfait_date_order"));
    }
  }
  if (entitlementIds.length === 0) {
    throw new Error(t("admin.formula_action.course_type_required"));
  }

  return {
    name,
    kind,
    active: checkboxField(formData, "active"),
    is_private: checkboxField(formData, "is_private"),
    description: optionalField(formData, "description"),
    credits_count: kind === "PACK" ? creditsCount : null,
    pack_validity_months: kind === "PACK" ? packValidityMonths : null,
    forfait_start_date: kind === "FORFAIT" ? forfaitStartDateRaw : null,
    forfait_end_date: kind === "FORFAIT" ? forfaitEndDateRaw : null,
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
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const returnTo = "/admin/config?section=activities&new_activity=1";

  const name = String(formData.get("name") ?? "").trim();
  const code = String(formData.get("code") ?? "").trim();
  const description = optionalField(formData, "description");
  const serviceCode = String(formData.get("service_code") ?? "ACTIVITY").trim().toUpperCase();
  const sellerLegalEntityId = String(formData.get("seller_legal_entity_id") ?? "").trim();
  const payorLegalEntityId = String(formData.get("payor_legal_entity_id") ?? "").trim();
  const creditTypeId = String(formData.get("credit_type_id") ?? "").trim();
  const durationMinutes = parsePositiveInt(String(formData.get("duration_minutes") ?? ""));
  const defaultCapacity = parseNonNegativeInt(String(formData.get("default_capacity") ?? ""));
  const isVacationActivity = isVacationServiceCode(serviceCode);
  const defaultHourlyRateRaw = String(formData.get("default_hourly_rate") ?? "").trim();
  const defaultHourlyRate = parseNonNegativeDecimal(defaultHourlyRateRaw);
  const defaultCourseRateRaw = String(formData.get("default_course_rate_ttc") ?? "").trim();
  const defaultCourseRate = parseNonNegativeDecimal(defaultCourseRateRaw);
  const colorHex = String(formData.get("color_hex") ?? "#94C973").trim();
  const modeRaw = String(formData.get("mode") ?? "ANY").trim().toUpperCase();
  const mode = modeRaw === "ONLINE" || modeRaw === "ONSITE" ? modeRaw : "ANY";
  const requiresProfessor = checkboxField(formData, "requires_professor");
  const allowsStudentBookings = !checkboxField(formData, "without_students");
  const emailReminderHours = parseReminderHoursOverride(String(formData.get("email_reminder_hours_before_start") ?? ""));
  const smsReminderHours = parseReminderHoursOverride(String(formData.get("sms_reminder_hours_before_start") ?? ""));
  const minBookingNoticeHoursOverride = parseOptionalPlanningRuleOverride(String(formData.get("min_booking_notice_hours_override") ?? ""));
  const cancellationDeadlineHoursOverride = parseOptionalPlanningRuleOverride(
    String(formData.get("cancellation_deadline_hours_override") ?? ""),
  );
  const autoCancelIfBookedLessThanOverride = parseOptionalPlanningRuleOverride(
    String(formData.get("auto_cancel_if_booked_less_than_override") ?? ""),
  );
  const autoCancelHoursBeforeStartOverride = parseOptionalPlanningRuleOverride(
    String(formData.get("auto_cancel_hours_before_start_override") ?? ""),
  );
  const excludeHolidaysInRecurrence = checkboxField(formData, "exclude_holidays_in_recurrence");
  const excludeSchoolVacationsInRecurrence = checkboxField(formData, "exclude_school_vacations_in_recurrence");
  const planningLocationIds = parseStringList(formData.getAll("planning_location_ids"));
  const planningScopeLocationIds = parseStringList(formData.getAll("planning_scope_location_ids"));
  const contentCourseIds = parseStringList(formData.getAll("content_course_ids"));

  if (!name) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.name_required")));
  }
  if (!durationMinutes || durationMinutes < 5) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_duration")));
  }
  if (isVacationActivity && (durationMinutes < 600 || durationMinutes > 1440)) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_vacation_duration")));
  }
  if (allowsStudentBookings && (defaultCapacity === null || defaultCapacity < 1)) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_default_capacity")));
  }
  if (!sellerLegalEntityId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.legal_entity_required")));
  }
  if (defaultHourlyRateRaw && defaultHourlyRate === null) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_default_hourly_rate")));
  }
  if (defaultCourseRateRaw && defaultCourseRate === null) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_default_course_rate")));
  }
  if (emailReminderHours === "INVALID") {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_email_reminder")));
  }
  if (smsReminderHours === "INVALID") {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_sms_reminder")));
  }
  if (minBookingNoticeHoursOverride === "INVALID") {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_min_booking_notice")));
  }
  if (cancellationDeadlineHoursOverride === "INVALID") {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_cancellation_deadline")));
  }
  if (autoCancelIfBookedLessThanOverride === "INVALID") {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_auto_cancel_booked_less_than")));
  }
  if (autoCancelHoursBeforeStartOverride === "INVALID") {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_auto_cancel_hours_before_start")));
  }

  const payload: Record<string, unknown> = {
    name,
    description,
    service_code: serviceCode || "ACTIVITY",
    seller_legal_entity_id: sellerLegalEntityId,
    payor_legal_entity_id: payorLegalEntityId || sellerLegalEntityId,
    credit_type_id: creditTypeId || null,
    duration_minutes: durationMinutes,
    color_hex: colorHex,
    mode,
    requires_professor: allowsStudentBookings ? requiresProfessor : false,
    allows_student_bookings: allowsStudentBookings,
    default_capacity: allowsStudentBookings ? defaultCapacity : 0,
    default_hourly_rate: defaultHourlyRateRaw ? defaultHourlyRate : null,
    default_course_rate_ttc: defaultCourseRateRaw ? defaultCourseRate : null,
    email_reminder_hours_before_start: emailReminderHours,
    sms_reminder_hours_before_start: smsReminderHours,
    min_booking_notice_hours_override: minBookingNoticeHoursOverride,
    cancellation_deadline_hours_override: cancellationDeadlineHoursOverride,
    auto_cancel_if_booked_less_than_override: autoCancelIfBookedLessThanOverride,
    auto_cancel_hours_before_start_override: autoCancelHoursBeforeStartOverride,
    exclude_holidays_in_recurrence: excludeHolidaysInRecurrence,
    exclude_school_vacations_in_recurrence: excludeSchoolVacationsInRecurrence,
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
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  const contentSyncResult = await syncActivityContentMappings({
    token,
    activityId: result.data.id,
    contentCourseIds,
    t,
  });
  if (!contentSyncResult.ok) {
    redirect(
      appendQueryMessage(
        `/admin/config?section=activities&activity_id=${encodeURIComponent(result.data.id)}`,
        "error",
        t("admin.activity_action.created_content_link_failed", { message: contentSyncResult.message }),
      ),
    );
  }

  const syncResult = await syncActivityPlanningAssignments({
    token,
    activityId: result.data.id,
    selectedLocationIds: planningLocationIds,
    scopeLocationIds: planningScopeLocationIds,
    t,
  });

  revalidatePath("/admin/config");
  revalidatePath("/admin");
  if (!syncResult.ok) {
    redirect(
      appendQueryMessage(
        `/admin/config?section=activities&activity_id=${encodeURIComponent(result.data.id)}`,
        "error",
        t("admin.activity_action.created_planning_sync_failed", { message: syncResult.message }),
      ),
    );
  }

  redirect(appendQueryMessage("/admin/config?section=activities", "ok", t("admin.activity_action.created")));
}

export async function updateAdminActivityAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const activityId = String(formData.get("activity_id") ?? "").trim();
  if (!activityId) {
    redirect(appendQueryMessage("/admin/config?section=activities", "error", t("admin.activity_action.invalid_activity")));
  }
  const returnTo = `/admin/config?section=activities&activity_id=${encodeURIComponent(activityId)}`;

  const name = String(formData.get("name") ?? "").trim();
  const code = String(formData.get("code") ?? "").trim();
  const description = optionalField(formData, "description");
  const serviceCode = String(formData.get("service_code") ?? "ACTIVITY").trim().toUpperCase();
  const sellerLegalEntityId = String(formData.get("seller_legal_entity_id") ?? "").trim();
  const payorLegalEntityId = String(formData.get("payor_legal_entity_id") ?? "").trim();
  const creditTypeId = String(formData.get("credit_type_id") ?? "").trim();
  const durationMinutes = parsePositiveInt(String(formData.get("duration_minutes") ?? ""));
  const defaultCapacity = parseNonNegativeInt(String(formData.get("default_capacity") ?? ""));
  const isVacationActivity = isVacationServiceCode(serviceCode);
  const defaultHourlyRateRaw = String(formData.get("default_hourly_rate") ?? "").trim();
  const defaultHourlyRate = parseNonNegativeDecimal(defaultHourlyRateRaw);
  const defaultCourseRateRaw = String(formData.get("default_course_rate_ttc") ?? "").trim();
  const defaultCourseRate = parseNonNegativeDecimal(defaultCourseRateRaw);
  const colorHex = String(formData.get("color_hex") ?? "#94C973").trim();
  const modeRaw = String(formData.get("mode") ?? "ANY").trim().toUpperCase();
  const mode = modeRaw === "ONLINE" || modeRaw === "ONSITE" ? modeRaw : "ANY";
  const requiresProfessor = checkboxField(formData, "requires_professor");
  const allowsStudentBookings = !checkboxField(formData, "without_students");
  const emailReminderHours = parseReminderHoursOverride(String(formData.get("email_reminder_hours_before_start") ?? ""));
  const smsReminderHours = parseReminderHoursOverride(String(formData.get("sms_reminder_hours_before_start") ?? ""));
  const minBookingNoticeHoursOverride = parseOptionalPlanningRuleOverride(String(formData.get("min_booking_notice_hours_override") ?? ""));
  const cancellationDeadlineHoursOverride = parseOptionalPlanningRuleOverride(
    String(formData.get("cancellation_deadline_hours_override") ?? ""),
  );
  const autoCancelIfBookedLessThanOverride = parseOptionalPlanningRuleOverride(
    String(formData.get("auto_cancel_if_booked_less_than_override") ?? ""),
  );
  const autoCancelHoursBeforeStartOverride = parseOptionalPlanningRuleOverride(
    String(formData.get("auto_cancel_hours_before_start_override") ?? ""),
  );
  const excludeHolidaysInRecurrence = checkboxField(formData, "exclude_holidays_in_recurrence");
  const excludeSchoolVacationsInRecurrence = checkboxField(formData, "exclude_school_vacations_in_recurrence");
  const planningLocationIds = parseStringList(formData.getAll("planning_location_ids"));
  const planningScopeLocationIds = parseStringList(formData.getAll("planning_scope_location_ids"));
  const contentCourseIds = parseStringList(formData.getAll("content_course_ids"));

  if (!name) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.name_required")));
  }
  if (!durationMinutes || durationMinutes < 5) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_duration")));
  }
  if (isVacationActivity && (durationMinutes < 600 || durationMinutes > 1440)) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_vacation_duration")));
  }
  if (allowsStudentBookings && (defaultCapacity === null || defaultCapacity < 1)) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_default_capacity")));
  }
  if (!sellerLegalEntityId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.legal_entity_required")));
  }
  if (defaultHourlyRateRaw && defaultHourlyRate === null) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_default_hourly_rate")));
  }
  if (defaultCourseRateRaw && defaultCourseRate === null) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_default_course_rate")));
  }
  if (emailReminderHours === "INVALID") {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_email_reminder")));
  }
  if (smsReminderHours === "INVALID") {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_sms_reminder")));
  }
  if (minBookingNoticeHoursOverride === "INVALID") {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_min_booking_notice")));
  }
  if (cancellationDeadlineHoursOverride === "INVALID") {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_cancellation_deadline")));
  }
  if (autoCancelIfBookedLessThanOverride === "INVALID") {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_auto_cancel_booked_less_than")));
  }
  if (autoCancelHoursBeforeStartOverride === "INVALID") {
    redirect(appendQueryMessage(returnTo, "error", t("admin.activity_action.invalid_auto_cancel_hours_before_start")));
  }

  const payload: Record<string, unknown> = {
    name,
    code: code || undefined,
    description,
    service_code: serviceCode || "ACTIVITY",
    seller_legal_entity_id: sellerLegalEntityId,
    payor_legal_entity_id: payorLegalEntityId || sellerLegalEntityId,
    credit_type_id: creditTypeId || null,
    duration_minutes: durationMinutes,
    color_hex: colorHex,
    mode,
    requires_professor: allowsStudentBookings ? requiresProfessor : false,
    allows_student_bookings: allowsStudentBookings,
    default_capacity: allowsStudentBookings ? defaultCapacity : 0,
    default_hourly_rate: defaultHourlyRateRaw ? defaultHourlyRate : null,
    default_course_rate_ttc: defaultCourseRateRaw ? defaultCourseRate : null,
    email_reminder_hours_before_start: emailReminderHours,
    sms_reminder_hours_before_start: smsReminderHours,
    min_booking_notice_hours_override: minBookingNoticeHoursOverride,
    cancellation_deadline_hours_override: cancellationDeadlineHoursOverride,
    auto_cancel_if_booked_less_than_override: autoCancelIfBookedLessThanOverride,
    auto_cancel_hours_before_start_override: autoCancelHoursBeforeStartOverride,
    exclude_holidays_in_recurrence: excludeHolidaysInRecurrence,
    exclude_school_vacations_in_recurrence: excludeSchoolVacationsInRecurrence,
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
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  const contentSyncResult = await syncActivityContentMappings({
    token,
    activityId,
    contentCourseIds,
    t,
  });
  if (!contentSyncResult.ok) {
    redirect(
      appendQueryMessage(
        returnTo,
        "error",
        t("admin.activity_action.updated_content_link_failed", { message: contentSyncResult.message }),
      ),
    );
  }

  const syncResult = await syncActivityPlanningAssignments({
    token,
    activityId,
    selectedLocationIds: planningLocationIds,
    scopeLocationIds: planningScopeLocationIds,
    t,
  });

  revalidatePath("/admin/config");
  revalidatePath("/admin");
  if (!syncResult.ok) {
    redirect(
      appendQueryMessage(
        returnTo,
        "error",
        t("admin.activity_action.updated_planning_sync_failed", { message: syncResult.message }),
      ),
    );
  }

  redirect(appendQueryMessage("/admin/config?section=activities", "ok", t("admin.activity_action.updated")));
}

export async function createAdminCreditTypeAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = "/admin/config?section=credit-types";

  const name = String(formData.get("name") ?? "").trim();
  const code = String(formData.get("code") ?? "").trim();
  const description = optionalField(formData, "description");
  const active = checkboxField(formData, "active");

  if (!name) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.credit_type_action.name_required")));
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
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin");
  redirect(appendQueryMessage(returnTo, "ok", t("admin.credit_type_action.created")));
}

export async function updateAdminCreditTypeAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = "/admin/config?section=credit-types";

  const creditTypeId = String(formData.get("credit_type_id") ?? "").trim();
  if (!creditTypeId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.credit_type_action.invalid_credit_type")));
  }

  const name = String(formData.get("name") ?? "").trim();
  const code = String(formData.get("code") ?? "").trim();
  const description = optionalField(formData, "description");
  const active = checkboxField(formData, "active");

  if (!name) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.credit_type_action.name_required")));
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
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin");
  redirect(appendQueryMessage(returnTo, "ok", t("admin.credit_type_action.updated")));
}

export async function deleteAdminCreditTypeAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = "/admin/config?section=credit-types";

  const creditTypeId = String(formData.get("credit_type_id") ?? "").trim();
  if (!creditTypeId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.credit_type_action.invalid_credit_type")));
  }

  const result = await backendRequest<Record<string, never>>(
    `/api/v1/admin/credit-types/${creditTypeId}`,
    {
      method: "DELETE",
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin");
  redirect(appendQueryMessage(returnTo, "ok", t("admin.credit_type_action.deleted")));
}

export async function createAdminLegalEntityAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = "/admin/config?section=legal-entities";

  const name = String(formData.get("name") ?? "").trim();
  const invoicePrefix = String(formData.get("invoice_prefix") ?? "").trim().toUpperCase();
  const countryCode = String(formData.get("country_code") ?? "FR").trim().toUpperCase();
  const defaultPaymentProvider = String(formData.get("default_payment_provider") ?? "PAYPLUG").trim().toUpperCase();
  const invoiceNextNumberRaw = String(formData.get("invoice_next_number") ?? "1").trim();
  const invoiceNextNumber = parsePositiveInt(invoiceNextNumberRaw);

  if (!name) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.legal_entity_action.name_required")));
  }
  if (!invoicePrefix) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.legal_entity_action.invoice_prefix_required")));
  }
  if (countryCode.length !== 2) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.legal_entity_action.invalid_country_code")));
  }
  if (invoiceNextNumber === null || invoiceNextNumber < 1) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.legal_entity_action.invalid_invoice_counter")));
  }
  if (!defaultPaymentProvider) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.legal_entity_action.invalid_default_psp")));
  }

  const payload = {
    name,
    siren: optionalField(formData, "siren"),
    siret: optionalField(formData, "siret"),
    vat_number: optionalField(formData, "vat_number"),
    address_text: optionalField(formData, "address_text"),
    accounting_email: optionalField(formData, "accounting_email"),
    phone: optionalField(formData, "phone"),
    legal_form: optionalField(formData, "legal_form"),
    share_capital: optionalField(formData, "share_capital"),
    country_code: countryCode,
    invoice_prefix: invoicePrefix,
    invoice_next_number: invoiceNextNumber,
    default_payment_provider: defaultPaymentProvider,
    is_active: checkboxFieldWithDefault(formData, "is_active", true),
  };

  const result = await backendRequest<AdminLegalEntityOut>(
    "/api/v1/admin/legal-entities",
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
  revalidatePath("/admin");
  redirect(appendQueryMessage(returnTo, "ok", t("admin.legal_entity_action.created")));
}

export async function updateAdminLegalEntityAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const legalEntityId = String(formData.get("legal_entity_id") ?? "").trim();
  const returnTo = legalEntityId
    ? `/admin/config?section=legal-entities&legal_entity_id=${encodeURIComponent(legalEntityId)}`
    : "/admin/config?section=legal-entities";
  if (!legalEntityId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.legal_entity_action.invalid_legal_entity")));
  }

  const name = String(formData.get("name") ?? "").trim();
  const invoicePrefix = String(formData.get("invoice_prefix") ?? "").trim().toUpperCase();
  const countryCode = String(formData.get("country_code") ?? "FR").trim().toUpperCase();
  const defaultPaymentProvider = String(formData.get("default_payment_provider") ?? "PAYPLUG").trim().toUpperCase();
  const invoiceNextNumberRaw = String(formData.get("invoice_next_number") ?? "1").trim();
  const invoiceNextNumber = parsePositiveInt(invoiceNextNumberRaw);

  if (!name) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.legal_entity_action.name_required")));
  }
  if (!invoicePrefix) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.legal_entity_action.invoice_prefix_required")));
  }
  if (countryCode.length !== 2) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.legal_entity_action.invalid_country_code")));
  }
  if (invoiceNextNumber === null || invoiceNextNumber < 1) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.legal_entity_action.invalid_invoice_counter")));
  }
  if (!defaultPaymentProvider) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.legal_entity_action.invalid_default_psp")));
  }

  const payload = {
    name,
    siren: optionalField(formData, "siren"),
    siret: optionalField(formData, "siret"),
    vat_number: optionalField(formData, "vat_number"),
    address_text: optionalField(formData, "address_text"),
    accounting_email: optionalField(formData, "accounting_email"),
    phone: optionalField(formData, "phone"),
    legal_form: optionalField(formData, "legal_form"),
    share_capital: optionalField(formData, "share_capital"),
    country_code: countryCode,
    invoice_prefix: invoicePrefix,
    invoice_next_number: invoiceNextNumber,
    default_payment_provider: defaultPaymentProvider,
    is_active: checkboxFieldWithDefault(formData, "is_active", true),
  };

  const result = await backendRequest<AdminLegalEntityOut>(
    `/api/v1/admin/legal-entities/${legalEntityId}`,
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
  revalidatePath("/admin");
  redirect(appendQueryMessage(returnTo, "ok", t("admin.legal_entity_action.updated")));
}

export async function disableAdminLegalEntityAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = "/admin/config?section=legal-entities";

  const legalEntityId = String(formData.get("legal_entity_id") ?? "").trim();
  if (!legalEntityId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.legal_entity_action.invalid_legal_entity")));
  }

  const result = await backendRequest<AdminLegalEntityOut>(
    `/api/v1/admin/legal-entities/${legalEntityId}/disable`,
    {
      method: "POST",
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin");
  redirect(appendQueryMessage(returnTo, "ok", t("admin.legal_entity_action.disabled")));
}

export async function updateAdminConfigAccountAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = "/admin/config?section=params-account";

  let logoDataUrl = String(formData.get("logo_data_url") ?? "").trim();
  const clearLogo = checkboxField(formData, "clear_logo");
  const rawLogoFile = formData.get("logo_file");
  if (clearLogo) {
    logoDataUrl = "";
  } else if (rawLogoFile instanceof File && rawLogoFile.size > 0) {
    const contentType = String(rawLogoFile.type || "").trim().toLowerCase();
    if (contentType !== "image/jpeg" && contentType !== "image/jpg") {
      redirect(appendQueryMessage(returnTo, "error", t("admin.account_action.logo_must_be_jpeg")));
    }
    if (rawLogoFile.size > 1024 * 1024) {
      redirect(appendQueryMessage(returnTo, "error", t("admin.account_action.logo_too_large")));
    }
    const buffer = Buffer.from(await rawLogoFile.arrayBuffer());
    logoDataUrl = `data:image/jpeg;base64,${buffer.toString("base64")}`;
  }

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
    client_balance_default_date_mode: String(formData.get("client_balance_default_date_mode") ?? "TODAY").trim().toUpperCase(),
    legal_terms: String(formData.get("legal_terms") ?? "").trim(),
    logo_data_url: logoDataUrl,
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
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config");
  redirect(appendQueryMessage(returnTo, "ok", t("admin.account_action.updated")));
}

export async function updateAdminConfigSubscriptionsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = "/admin/config?section=params-subscriptions";

  const directDebitDay = parsePositiveInt(String(formData.get("direct_debit_day") ?? ""));
  if (directDebitDay !== null && (directDebitDay < 1 || directDebitDay > 28)) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.subscription_action.invalid_direct_debit_day")));
  }
  const retryFirstDelayDays = parsePositiveInt(String(formData.get("retry_first_delay_days") ?? ""));
  const retryMaxAutoAttempts = parsePositiveInt(String(formData.get("retry_max_auto_attempts") ?? ""));
  const retryMoveToPreTerminationAfterFailedAttempts = parsePositiveInt(
    String(formData.get("retry_move_to_pre_termination_after_failed_attempts") ?? ""),
  );
  if (
    retryFirstDelayDays === null ||
    retryMaxAutoAttempts === null ||
    retryMoveToPreTerminationAfterFailedAttempts === null ||
    retryFirstDelayDays < 1 ||
    retryFirstDelayDays > 30 ||
    retryMaxAutoAttempts < 1 ||
    retryMaxAutoAttempts > 10 ||
    retryMoveToPreTerminationAfterFailedAttempts < 1 ||
    retryMoveToPreTerminationAfterFailedAttempts > 10
  ) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.subscription_action.invalid_retry_settings")));
  }
  if (retryMoveToPreTerminationAfterFailedAttempts > retryMaxAutoAttempts) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.subscription_action.invalid_pretermination_threshold")));
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
    allow_booking_during_payment_alert: checkboxField(formData, "allow_booking_during_payment_alert"),
    retry_first_delay_days: retryFirstDelayDays,
    retry_max_auto_attempts: retryMaxAutoAttempts,
    retry_move_to_pre_termination_after_failed_attempts: retryMoveToPreTerminationAfterFailedAttempts,
    notify_success_customer_enabled: checkboxField(formData, "notify_success_customer_enabled"),
    notify_success_admin_enabled: checkboxField(formData, "notify_success_admin_enabled"),
    notify_first_failure_customer_enabled: checkboxField(formData, "notify_first_failure_customer_enabled"),
    notify_first_failure_admin_enabled: checkboxField(formData, "notify_first_failure_admin_enabled"),
    notify_final_failure_customer_enabled: checkboxField(formData, "notify_final_failure_customer_enabled"),
    notify_final_failure_admin_enabled: checkboxField(formData, "notify_final_failure_admin_enabled"),
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
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config");
  redirect(appendQueryMessage(returnTo, "ok", t("admin.subscription_action.updated")));
}

export async function updateAdminConfigProfessorDefaultGridAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const parseStructuredRules = (
    minValuesRaw: FormDataEntryValue[],
    maxValuesRaw: FormDataEntryValue[],
    rateValuesRaw: FormDataEntryValue[],
    label: string,
  ): Array<{ min_students: number; max_students: number | null; hourly_rate: number }> => {
    const minValues = minValuesRaw.map((value) => String(value ?? "").trim());
    const maxValues = maxValuesRaw.map((value) => String(value ?? "").trim());
    const rateValues = rateValuesRaw.map((value) => String(value ?? "").trim().replace(",", "."));
    const rowCount = Math.max(minValues.length, maxValues.length, rateValues.length);

    const rows: Array<{ min_students: number; max_students: number | null; hourly_rate: number }> = [];
    for (let index = 0; index < rowCount; index += 1) {
      const minRaw = minValues[index] ?? "";
      const maxRaw = maxValues[index] ?? "";
      const rateRaw = rateValues[index] ?? "";
      if (!minRaw && !maxRaw && !rateRaw) {
        continue;
      }
      const minStudents = parseNonNegativeInt(minRaw);
      if (minStudents === null) {
        redirect(appendQueryMessage("/admin/config?section=params-professor-default-grid", "error", t("admin.professor_action.rule_invalid_min_line", { label, index: index + 1 })));
      }
      let maxStudents: number | null = null;
      if (maxRaw) {
        maxStudents = parseNonNegativeInt(maxRaw);
        if (maxStudents === null || maxStudents < minStudents) {
          redirect(appendQueryMessage("/admin/config?section=params-professor-default-grid", "error", t("admin.professor_action.rule_invalid_max_line", { label, index: index + 1 })));
        }
      }
      const hourlyRate = parseNonNegativeDecimal(rateRaw);
      if (hourlyRate === null) {
        redirect(appendQueryMessage("/admin/config?section=params-professor-default-grid", "error", t("admin.professor_action.rule_invalid_rate_line", { label, index: index + 1 })));
      }
      rows.push({ min_students: minStudents, max_students: maxStudents, hourly_rate: hourlyRate });
    }

    rows.sort((a, b) => (a.min_students - b.min_students) || ((a.max_students ?? Number.MAX_SAFE_INTEGER) - (b.max_students ?? Number.MAX_SAFE_INTEGER)));
    for (let index = 1; index < rows.length; index += 1) {
      const previous = rows[index - 1];
      const current = rows[index];
      if (previous.max_students === null || current.min_students <= previous.max_students) {
        redirect(appendQueryMessage("/admin/config?section=params-professor-default-grid", "error", t("admin.professor_action.rule_overlapping_ranges", { label })));
      }
    }
    return rows;
  };

  const uiVersion = String(formData.get("default_grid_ui_version") ?? "").trim();
  const lines: Array<{
    course_type_id: string;
    default_hourly_rate: number | null;
    rules: Array<{ min_students: number; max_students: number | null; hourly_rate: number }>;
  }> = [];
  if (uiVersion === "2") {
    const courseTypeIds = [...new Set(parseStringList(formData.getAll("line_course_type_id")))];
    for (const courseTypeId of courseTypeIds) {
      const activityLabel = t("admin.professor_action.activity_label", { course_type_id: courseTypeId });
      const defaultRateRaw = String(formData.get(`line_default_rate_${courseTypeId}`) ?? "").trim().replace(",", ".");
      const rules = parseStructuredRules(
        formData.getAll(`line_rule_min_${courseTypeId}`),
        formData.getAll(`line_rule_max_${courseTypeId}`),
        formData.getAll(`line_rule_rate_${courseTypeId}`),
        activityLabel,
      );
      const defaultRate = defaultRateRaw ? parseNonNegativeDecimal(defaultRateRaw) : null;
      if (defaultRateRaw && defaultRate === null) {
        redirect(appendQueryMessage("/admin/config?section=params-professor-default-grid", "error", t("admin.professor_action.activity_invalid_rate", { label: activityLabel })));
      }
      if (defaultRate === null && rules.length === 0) {
        continue;
      }
      lines.push({
        course_type_id: courseTypeId,
        default_hourly_rate: defaultRate,
        rules,
      });
    }
  } else {
    for (let index = 0; index < 16; index += 1) {
      const courseTypeId = String(formData.get(`line_course_type_id_${index}`) ?? "").trim();
      const defaultRateRaw = String(formData.get(`line_default_rate_${index}`) ?? "").trim().replace(",", ".");
      const rulesRaw = String(formData.get(`line_rules_${index}`) ?? "").trim();

      if (!courseTypeId && !defaultRateRaw && !rulesRaw) {
        continue;
      }
      if (!courseTypeId) {
        redirect(appendQueryMessage("/admin/config?section=params-professor-default-grid", "error", t("admin.professor_action.grid_line_missing_activity", { index: index + 1 })));
      }

      const defaultRate = defaultRateRaw ? parseNonNegativeDecimal(defaultRateRaw) : null;
      if (defaultRateRaw && defaultRate === null) {
        redirect(appendQueryMessage("/admin/config?section=params-professor-default-grid", "error", t("admin.professor_action.grid_line_invalid_default_rate", { index: index + 1 })));
      }

      const rules = parseHeadcountRules(rulesRaw);
      if (rules === null) {
        redirect(appendQueryMessage("/admin/config?section=params-professor-default-grid", "error", t("admin.professor_action.grid_line_invalid_headcount_rules", { index: index + 1 })));
      }

      lines.push({
        course_type_id: courseTypeId,
        default_hourly_rate: defaultRate,
        rules,
      });
    }
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
    redirect(appendQueryMessage("/admin/config?section=params-professor-default-grid", "error", result.message));
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin/professors");
  redirect(appendQueryMessage("/admin/config?section=params-professor-default-grid", "ok", t("admin.professor_default_grid_action.default_grid_updated")));
}

export async function createAdminConfigProfessorDefaultGridPeriodAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnToBase = safeAdminReturnPath(formData, "/admin/config?section=params-professor-default-grid");
  const cleanReturnTo = removeQueryParam(removeQueryParam(returnToBase, "ok"), "error");

  const startDate = String(formData.get("start_date") ?? "").trim();
  const endDate = String(formData.get("end_date") ?? "").trim();
  const notes = String(formData.get("notes") ?? "").trim();
  const cloneFromPeriodId = String(formData.get("clone_from_period_id") ?? "").trim() || null;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(startDate)) {
    redirect(appendQueryMessage(cleanReturnTo, "error", t("admin.professor_default_grid_action.invalid_start_date")));
  }
  if (endDate && !/^\d{4}-\d{2}-\d{2}$/.test(endDate)) {
    redirect(appendQueryMessage(cleanReturnTo, "error", t("admin.professor_default_grid_action.invalid_end_date")));
  }
  if (endDate && endDate < startDate) {
    redirect(appendQueryMessage(cleanReturnTo, "error", t("admin.professor_default_grid_action.end_before_start")));
  }

  const result = await backendRequest<AdminProfessorPayGridPeriodOut>(
    "/api/v1/admin/config/professor-default-grid/periods",
    {
      method: "POST",
      body: JSON.stringify({
        start_date: startDate,
        end_date: endDate || null,
        notes: notes || null,
        clone_from_period_id: cloneFromPeriodId,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(cleanReturnTo, "error", result.message));
  }
  revalidatePath("/admin/config");
  revalidatePath("/admin/teacher-invoicing");
  revalidatePath("/admin/teacher-invoicing/salary-grid");
  const scopedReturnTo = setQueryParam(cleanReturnTo, "grid_period", result.data.id);
  redirect(appendQueryMessage(scopedReturnTo, "ok", t("admin.professor_default_grid_action.period_created")));
}

export async function updateAdminConfigProfessorDefaultGridPeriodAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const periodId = String(formData.get("period_id") ?? "").trim();
  const returnToBase = safeAdminReturnPath(formData, "/admin/config?section=params-professor-default-grid");
  const cleanReturnTo = removeQueryParam(removeQueryParam(returnToBase, "ok"), "error");
  const scopedReturnTo = setQueryParam(cleanReturnTo, "grid_period", periodId || null);
  if (!periodId) {
    redirect(appendQueryMessage(cleanReturnTo, "error", t("admin.professor_default_grid_action.invalid_period")));
  }
  const startDate = String(formData.get("start_date") ?? "").trim();
  const endDate = String(formData.get("end_date") ?? "").trim();
  const notes = String(formData.get("notes") ?? "").trim();
  const statusValue = String(formData.get("status") ?? "").trim().toUpperCase();
  if (startDate && !/^\d{4}-\d{2}-\d{2}$/.test(startDate)) {
    redirect(appendQueryMessage(scopedReturnTo, "error", t("admin.professor_default_grid_action.invalid_start_date")));
  }
  if (endDate && !/^\d{4}-\d{2}-\d{2}$/.test(endDate)) {
    redirect(appendQueryMessage(scopedReturnTo, "error", t("admin.professor_default_grid_action.invalid_end_date")));
  }
  if (startDate && endDate && endDate < startDate) {
    redirect(appendQueryMessage(scopedReturnTo, "error", t("admin.professor_default_grid_action.end_before_start")));
  }
  const result = await backendRequest<AdminProfessorPayGridPeriodOut>(
    `/api/v1/admin/config/professor-default-grid/periods/${periodId}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        start_date: startDate || null,
        end_date: endDate || null,
        notes: notes || null,
        status: statusValue || null,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(scopedReturnTo, "error", result.message));
  }
  revalidatePath("/admin/config");
  revalidatePath("/admin/teacher-invoicing");
  revalidatePath("/admin/teacher-invoicing/salary-grid");
  redirect(appendQueryMessage(scopedReturnTo, "ok", t("admin.professor_default_grid_action.period_updated")));
}

export async function archiveAdminConfigProfessorDefaultGridPeriodAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const periodId = String(formData.get("period_id") ?? "").trim();
  const returnToBase = safeAdminReturnPath(formData, "/admin/config?section=params-professor-default-grid");
  const cleanReturnTo = removeQueryParam(removeQueryParam(returnToBase, "ok"), "error");
  const scopedReturnTo = setQueryParam(cleanReturnTo, "grid_period", periodId || null);
  if (!periodId) {
    redirect(appendQueryMessage(cleanReturnTo, "error", t("admin.professor_default_grid_action.invalid_period")));
  }
  const result = await backendRequest<AdminProfessorPayGridPeriodOut>(
    `/api/v1/admin/config/professor-default-grid/periods/${periodId}/archive`,
    { method: "POST" },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(scopedReturnTo, "error", result.message));
  }
  revalidatePath("/admin/config");
  revalidatePath("/admin/teacher-invoicing");
  revalidatePath("/admin/teacher-invoicing/salary-grid");
  const archivedReturnTo = setQueryParam(cleanReturnTo, "grid_period", null);
  redirect(appendQueryMessage(archivedReturnTo, "ok", t("admin.professor_default_grid_action.period_archived")));
}

export async function updateAdminConfigProfessorDefaultGridPeriodRulesAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const periodId = String(formData.get("period_id") ?? "").trim();
  const returnToBase = safeAdminReturnPath(formData, "/admin/config?section=params-professor-default-grid");
  const cleanReturnTo = removeQueryParam(removeQueryParam(returnToBase, "ok"), "error");
  const scopedReturnTo = setQueryParam(cleanReturnTo, "grid_period", periodId || null);
  if (!periodId) {
    redirect(appendQueryMessage(cleanReturnTo, "error", t("admin.professor_default_grid_action.invalid_period")));
  }
  const currencyCode = String(formData.get("currency_code") ?? "").trim().toUpperCase() || "EUR";

  const parseStructuredRules = (
    minValuesRaw: FormDataEntryValue[],
    maxValuesRaw: FormDataEntryValue[],
    rateValuesRaw: FormDataEntryValue[],
    label: string,
  ): Array<{ min_students: number; max_students: number | null; hourly_rate: number }> => {
    const minValues = minValuesRaw.map((value) => String(value ?? "").trim());
    const maxValues = maxValuesRaw.map((value) => String(value ?? "").trim());
    const rateValues = rateValuesRaw.map((value) => String(value ?? "").trim().replace(",", "."));
    const rowCount = Math.max(minValues.length, maxValues.length, rateValues.length);
    const rows: Array<{ min_students: number; max_students: number | null; hourly_rate: number }> = [];
    for (let index = 0; index < rowCount; index += 1) {
      const minRaw = minValues[index] ?? "";
      const maxRaw = maxValues[index] ?? "";
      const rateRaw = rateValues[index] ?? "";
      if (!minRaw && !maxRaw && !rateRaw) {
        continue;
      }
      const minStudents = parseNonNegativeInt(minRaw);
      if (minStudents === null) {
        redirect(appendQueryMessage(scopedReturnTo, "error", t("admin.professor_action.rule_invalid_min_line", { label, index: index + 1 })));
      }
      let maxStudents: number | null = null;
      if (maxRaw) {
        maxStudents = parseNonNegativeInt(maxRaw);
        if (maxStudents === null || maxStudents < minStudents) {
          redirect(appendQueryMessage(scopedReturnTo, "error", t("admin.professor_action.rule_invalid_max_line", { label, index: index + 1 })));
        }
      }
      const hourlyRate = parseNonNegativeDecimal(rateRaw);
      if (hourlyRate === null) {
        redirect(appendQueryMessage(scopedReturnTo, "error", t("admin.professor_action.rule_invalid_rate_line", { label, index: index + 1 })));
      }
      rows.push({ min_students: minStudents, max_students: maxStudents, hourly_rate: hourlyRate });
    }
    rows.sort((a, b) => (a.min_students - b.min_students) || ((a.max_students ?? Number.MAX_SAFE_INTEGER) - (b.max_students ?? Number.MAX_SAFE_INTEGER)));
    for (let index = 1; index < rows.length; index += 1) {
      const previous = rows[index - 1];
      const current = rows[index];
      if (previous.max_students === null || current.min_students <= previous.max_students) {
        redirect(appendQueryMessage(scopedReturnTo, "error", t("admin.professor_action.rule_overlapping_ranges", { label })));
      }
    }
    return rows;
  };

  const lines: Array<{
    course_type_id: string;
    default_hourly_rate: number | null;
    rules: Array<{ min_students: number; max_students: number | null; hourly_rate: number }>;
  }> = [];
  const courseTypeIds = [...new Set(parseStringList(formData.getAll("line_course_type_id")))];
  for (const courseTypeId of courseTypeIds) {
    const activityLabel = t("admin.professor_action.activity_label", { course_type_id: courseTypeId });
    const defaultRateRaw = String(formData.get(`line_default_rate_${courseTypeId}`) ?? "").trim().replace(",", ".");
    const rules = parseStructuredRules(
      formData.getAll(`line_rule_min_${courseTypeId}`),
      formData.getAll(`line_rule_max_${courseTypeId}`),
      formData.getAll(`line_rule_rate_${courseTypeId}`),
      activityLabel,
    );
    const defaultRate = defaultRateRaw ? parseNonNegativeDecimal(defaultRateRaw) : null;
    if (defaultRateRaw && defaultRate === null) {
      redirect(appendQueryMessage(scopedReturnTo, "error", t("admin.professor_action.activity_invalid_rate", { label: activityLabel })));
    }
    if (defaultRate === null && rules.length === 0) {
      continue;
    }
    lines.push({
      course_type_id: courseTypeId,
      default_hourly_rate: defaultRate,
      rules,
    });
  }

  const result = await backendRequest<AdminProfessorPayGridPeriodDetailOut>(
    `/api/v1/admin/config/professor-default-grid/periods/${periodId}/rules`,
    {
      method: "PUT",
      body: JSON.stringify({
        lines,
        currency_code: currencyCode,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(scopedReturnTo, "error", result.message));
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin/professors");
  revalidatePath("/admin/teacher-invoicing");
  revalidatePath("/admin/teacher-invoicing/salary-grid");
  redirect(appendQueryMessage(scopedReturnTo, "ok", t("admin.professor_default_grid_action.period_grid_updated")));
}

export async function updateAdminConfigPaymentMethodsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = "/admin/config?section=params-payments";
  const enabledCodes = parseStringList(formData.getAll("enabled_codes")).map((code) => code.toUpperCase());
  const legalEntityByMethodCode: Record<string, string | null> = {};
  for (const methodCode of ["BANK_TRANSFER", "CHECK", "CASH"]) {
    const parsed = parseUuid(String(formData.get(`legal_entity_for_${methodCode}`) ?? ""));
    legalEntityByMethodCode[methodCode] = parsed;
  }

  const result = await backendRequest<AdminPaymentMethodsOut>(
    "/api/v1/admin/config/payment-methods",
    {
      method: "PUT",
      body: JSON.stringify({ enabled_codes: enabledCodes, legal_entity_by_method_code: legalEntityByMethodCode }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config");
  redirect(appendQueryMessage(returnTo, "ok", t("admin.payment_action.methods_updated")));
}

export async function updateAdminConfigReferralProgramAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const returnTo = "/admin/config?section=params-referrals";
  const categories: Record<string, { label: string; amount: string; active: boolean }> = {};
  for (const code of ["PARIS", "BAR_LE_DUC", "ONLINE", "DOMICILE"]) {
    categories[code] = {
      label: String(formData.get(`category_label_${code}`) ?? code).trim() || code,
      amount: String(formData.get(`category_amount_${code}`) ?? "0").trim() || "0",
      active: formData.get(`category_active_${code}`) === "on",
    };
  }

  const result = await backendRequest<AdminReferralProgramSettingsOut>(
    "/api/v1/admin/config/referral-program",
    {
      method: "PUT",
      body: JSON.stringify({
        enabled: formData.get("enabled") === "on",
        currency: String(formData.get("currency") ?? "EUR").trim().toUpperCase(),
        trigger_ratio: String(formData.get("trigger_ratio") ?? "0.50").trim() || "0.50",
        announcement_email_enabled: formData.get("announcement_email_enabled") === "on",
        credit_email_enabled: formData.get("credit_email_enabled") === "on",
        categories,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config");
  redirect(appendQueryMessage(returnTo, "ok", adminReferralActionText(language, "referral_settings_saved")));
}

export async function updateAdminConfigProductCategoriesAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const locale = localeForUiLanguage(language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/config?section=products");

  const raw = String(formData.get("categories") ?? "");
  const categories = raw
    .split(/[\n,;]+/)
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);

  const deduplicated: string[] = [];
  const seen = new Set<string>();
  for (const category of categories) {
    const key = category.toLocaleLowerCase(locale);
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
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin/products");
  revalidatePath("/admin/clients");
  redirect(
    appendQueryMessage(
      removeQueryParam(removeQueryParam(returnTo, "ok"), "error"),
      "ok",
      t("admin.catalog_action.product_categories_updated"),
    ),
  );
}

export async function createAdminCatalogCategoryAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/config?section=products");

  const name = String(formData.get("name") ?? "").trim();
  const code = optionalField(formData, "code");
  const description = optionalField(formData, "description");
  const displayOrder = parseNonNegativeInt(String(formData.get("display_order") ?? "0")) ?? 0;
  const statusValue = String(formData.get("status") ?? "").trim().toLowerCase();
  const active = statusValue ? statusValue === "active" : checkboxFieldWithDefault(formData, "active", true);
  const canBeRequestedByProfessor = checkboxFieldWithDefault(formData, "can_be_requested_by_professor", true);
  if (!name) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.category_name_required")));
  }

  const result = await backendRequest<AdminCatalogCategoryOut>(
    "/api/v1/admin/config/catalog/categories",
    {
      method: "POST",
      body: JSON.stringify({
        name,
        code,
        description,
        display_order: displayOrder,
        active,
        can_be_requested_by_professor: canBeRequestedByProfessor,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config");
  revalidatePath("/admin/config/catalog");
  revalidatePath("/admin/products");
  revalidatePath("/admin/clients");
  redirect(appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.category_created")));
}

export async function updateAdminCatalogCategoryAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/config?section=products");

  const categoryId = parseUuid(String(formData.get("category_id") ?? ""));
  const name = String(formData.get("name") ?? "").trim();
  const code = optionalField(formData, "code");
  const description = optionalField(formData, "description");
  const displayOrder = parseNonNegativeInt(String(formData.get("display_order") ?? "0")) ?? 0;
  const statusValue = String(formData.get("status") ?? "").trim().toLowerCase();
  const active = statusValue ? statusValue === "active" : checkboxFieldWithDefault(formData, "active", true);
  const canBeRequestedByProfessor = checkboxFieldWithDefault(formData, "can_be_requested_by_professor", true);
  if (!categoryId || !name) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_category")));
  }

  const result = await backendRequest<AdminCatalogCategoryOut>(
    `/api/v1/admin/config/catalog/categories/${categoryId}`,
    {
      method: "PUT",
      body: JSON.stringify({
        name,
        code,
        description,
        display_order: displayOrder,
        active,
        can_be_requested_by_professor: canBeRequestedByProfessor,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config");
  revalidatePath("/admin/config/catalog");
  revalidatePath("/admin/products");
  revalidatePath("/admin/clients");
  redirect(appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.category_updated")));
}

export async function deleteAdminCatalogCategoryAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/config?section=products");
  const categoryId = parseUuid(String(formData.get("category_id") ?? ""));
  if (!categoryId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_category")));
  }

  const result = await backendRequest<void>(
    `/api/v1/admin/config/catalog/categories/${categoryId}`,
    {
      method: "DELETE",
    },
    token,
  );
  if (!result.ok && result.status !== 204) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config");
  revalidatePath("/admin/config/catalog");
  revalidatePath("/admin/products");
  revalidatePath("/admin/clients");
  redirect(appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.category_deleted")));
}

export async function toggleAdminCatalogCategoryArchiveAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/config/catalog");
  const categoryId = parseUuid(String(formData.get("category_id") ?? ""));
  const archiveValue = String(formData.get("archive") ?? "").trim().toLowerCase();
  const shouldArchive = archiveValue === "1" || archiveValue === "true" || archiveValue === "yes" || archiveValue === "on";
  if (!categoryId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_category")));
  }

  const categoriesResult = await backendRequest<AdminCatalogCategoryOut[]>(
    "/api/v1/admin/config/catalog/categories?include_inactive=true",
    {},
    token,
  );
  if (!categoriesResult.ok) {
    redirect(appendQueryMessage(returnTo, "error", categoriesResult.message));
  }
  const current = categoriesResult.data.find((row) => row.id === categoryId);
  if (!current) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.category_not_found")));
  }

  const updateResult = await backendRequest<AdminCatalogCategoryOut>(
    `/api/v1/admin/config/catalog/categories/${categoryId}`,
    {
      method: "PUT",
      body: JSON.stringify({
        name: current.name,
        code: current.code,
        description: current.description,
        display_order: current.display_order,
        can_be_requested_by_professor: current.can_be_requested_by_professor,
        active: !shouldArchive,
      }),
    },
    token,
  );
  if (!updateResult.ok) {
    redirect(appendQueryMessage(returnTo, "error", updateResult.message));
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin/config/catalog");
  revalidatePath("/admin/products");
  revalidatePath("/admin/clients");
  redirect(
    appendQueryMessage(
      removeQueryParam(removeQueryParam(returnTo, "ok"), "error"),
      "ok",
      shouldArchive ? t("admin.catalog_action.category_archived") : t("admin.catalog_action.category_unarchived"),
    ),
  );
}

export async function createAdminCatalogProductAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/config?section=products");

  const title = String(formData.get("title") ?? "").trim();
  const categoryId = parseUuid(String(formData.get("category_id") ?? ""));
  const primaryLocationId = parseUuid(String(formData.get("primary_location_id") ?? ""));
  const priceExclVatInput = parseNonNegativeDecimal(String(formData.get("price_excl_vat") ?? ""));
  const priceInclVat = parseNonNegativeDecimal(String(formData.get("price_incl_vat") ?? ""));
  const vatRateInput = parseNonNegativeDecimal(String(formData.get("vat_rate") ?? ""));
  const reserveStockInput = parseNonNegativeInt(String(formData.get("reserve_stock") ?? ""));
  const imageFileEntry = formData.get("image_file");
  const imageFile =
    typeof File !== "undefined" && imageFileEntry instanceof File && imageFileEntry.size > 0
      ? imageFileEntry
      : null;
  const vatRate = vatRateInput ?? 20;
  const reserveStock = reserveStockInput ?? 0;
  const reorderStatus = String(formData.get("reorder_status") ?? "NORMAL").trim().toUpperCase();
  const nature = String(formData.get("nature") ?? "material").trim().toLowerCase() === "service" ? "service" : "material";
  const isVirtual = String(formData.get("is_virtual") ?? "false").trim().toLowerCase() === "true";
  if (!title || !categoryId || priceInclVat === null) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.product_required_fields")));
  }
  if (imageFile) {
    const allowedImageTypes = new Set(["image/jpeg", "image/jpg", "image/png", "image/webp"]);
    if (imageFile.size > 5 * 1024 * 1024) {
      redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.image_too_large")));
    }
    if (!allowedImageTypes.has((imageFile.type || "").toLowerCase())) {
      redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_image_format")));
    }
  }
  const divisor = 1 + vatRate / 100;
  if (!Number.isFinite(divisor) || divisor <= 0) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_vat_rate")));
  }
  const computedPriceExclVat = Math.round((priceInclVat / divisor) * 100) / 100;
  const priceExclVat = priceExclVatInput ?? computedPriceExclVat;

  const payload = {
    category_id: categoryId,
    primary_location_id: primaryLocationId,
    title,
    barcode: optionalField(formData, "barcode"),
    price_excl_vat: priceExclVat,
    price_incl_vat: priceInclVat,
    vat_rate: vatRate,
    reserve_stock: isVirtual ? 0 : reserveStock,
    reorder_status: isVirtual ? "NORMAL" : reorderStatus,
    image_url: optionalField(formData, "image_url"),
    short_description: optionalField(formData, "short_description"),
    long_description: optionalField(formData, "long_description"),
    web_link: optionalField(formData, "web_link"),
    nature,
    is_virtual: isVirtual,
    purchasable_online: checkboxField(formData, "purchasable_online"),
    is_public: checkboxFieldWithDefault(formData, "is_public", true),
    active: checkboxFieldWithDefault(formData, "active", true),
  };

  const result = await backendRequest<AdminCatalogProductOut>(
    "/api/v1/admin/config/catalog/products",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  let successMessage = t("admin.catalog_action.product_created");
  if (imageFile) {
    const uploadPayload = new FormData();
    uploadPayload.set("file", imageFile, imageFile.name || "image");
    const uploadResult = await backendRequest<AdminCatalogProductImageUploadOut>(
      `/api/v1/admin/config/catalog/products/${result.data.id}/image`,
      {
        method: "POST",
        body: uploadPayload,
      },
      token,
    );
    if (!uploadResult.ok) {
      successMessage = t("admin.catalog_action.product_created_image_failed");
    }
  }
  revalidatePath("/admin/config");
  revalidatePath("/admin/products");
  let successPath = removeQueryParam(removeQueryParam(returnTo, "ok"), "error");
  successPath = removeQueryParam(successPath, "add");
  redirect(appendQueryMessage(successPath, "ok", successMessage));
}

export async function updateAdminCatalogProductAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/config?section=products");

  const productId = parseUuid(String(formData.get("product_id") ?? ""));
  const title = String(formData.get("title") ?? "").trim();
  const categoryId = parseUuid(String(formData.get("category_id") ?? ""));
  const primaryLocationId = parseUuid(String(formData.get("primary_location_id") ?? ""));
  const priceExclVat = parseNonNegativeDecimal(String(formData.get("price_excl_vat") ?? ""));
  const priceInclVat = parseNonNegativeDecimal(String(formData.get("price_incl_vat") ?? ""));
  const vatRate = parseNonNegativeDecimal(String(formData.get("vat_rate") ?? "20"));
  const reserveStock = parseNonNegativeInt(String(formData.get("reserve_stock") ?? "0"));
  const reorderStatus = String(formData.get("reorder_status") ?? "NORMAL").trim().toUpperCase();
  const nature = String(formData.get("nature") ?? "material").trim().toLowerCase() === "service" ? "service" : "material";
  const isVirtual = String(formData.get("is_virtual") ?? "false").trim().toLowerCase() === "true";
  if (!productId || !title || priceExclVat === null || priceInclVat === null || vatRate === null || reserveStock === null) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_product")));
  }

  const payload = {
    category_id: categoryId,
    primary_location_id: primaryLocationId,
    title,
    barcode: optionalField(formData, "barcode"),
    price_excl_vat: priceExclVat,
    price_incl_vat: priceInclVat,
    vat_rate: vatRate,
    reserve_stock: isVirtual ? 0 : reserveStock,
    reorder_status: isVirtual ? "NORMAL" : reorderStatus,
    image_url: optionalField(formData, "image_url"),
    short_description: optionalField(formData, "short_description"),
    long_description: optionalField(formData, "long_description"),
    web_link: optionalField(formData, "web_link"),
    nature,
    is_virtual: isVirtual,
    purchasable_online: checkboxField(formData, "purchasable_online"),
    is_public: checkboxFieldWithDefault(formData, "is_public", true),
    active: checkboxFieldWithDefault(formData, "active", true),
  };

  const result = await backendRequest<AdminCatalogProductOut>(
    `/api/v1/admin/config/catalog/products/${productId}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config");
  revalidatePath("/admin/products");
  redirect(appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.product_updated")));
}

export async function deleteAdminCatalogProductAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/config?section=products");
  const productId = parseUuid(String(formData.get("product_id") ?? ""));
  if (!productId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_product")));
  }
  const result = await backendRequest<void>(
    `/api/v1/admin/config/catalog/products/${productId}`,
    {
      method: "DELETE",
    },
    token,
  );
  if (!result.ok && result.status !== 204) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config");
  revalidatePath("/admin/products");
  redirect(appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.product_deleted")));
}

export async function createAdminCatalogKitAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/config?section=products");

  const title = String(formData.get("title") ?? "").trim();
  const code = optionalField(formData, "code");
  const categoryId = parseUuid(String(formData.get("category_id") ?? ""));
  const priceMode = parseCatalogKitPriceMode(String(formData.get("price_mode") ?? ""));
  const forcedPrice = parseNonNegativeDecimal(String(formData.get("forced_price") ?? ""));
  const legacyPriceInclVat = parseNonNegativeDecimal(String(formData.get("price_incl_vat") ?? ""));
  const effectiveForcedPrice = forcedPrice ?? legacyPriceInclVat;
  const currency = parseCurrencyCode(String(formData.get("currency") ?? "EUR"));
  const vatRate = parseNonNegativeDecimal(String(formData.get("vat_rate") ?? "20"));
  const statusValue = String(formData.get("status") ?? "").trim().toLowerCase();
  const active = statusValue ? statusValue === "active" : checkboxFieldWithDefault(formData, "active", true);
  const isPublic = parseCheckboxFlag(formData, "is_public", true);
  const useInManualBilling = parseCheckboxFlag(formData, "use_in_manual_billing", true);
  const useInEnrollments = parseCheckboxFlag(formData, "use_in_enrollments", true);
  const purchasableOnline = parseCheckboxFlag(formData, "purchasable_online", false);
  const items = parseCatalogKitItemsFromFormData(formData);
  if (!title || vatRate === null || items === null || (priceMode === "forced" && effectiveForcedPrice === null)) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_kit")));
  }

  const payload = {
    category_id: categoryId,
    code,
    title,
    image_url: optionalField(formData, "image_url"),
    short_description: optionalField(formData, "short_description"),
    long_description: optionalField(formData, "long_description"),
    price_mode: priceMode,
    forced_price: priceMode === "forced" ? effectiveForcedPrice : null,
    currency,
    price_incl_vat: effectiveForcedPrice ?? 0,
    vat_rate: vatRate,
    use_in_manual_billing: useInManualBilling,
    use_in_enrollments: useInEnrollments,
    purchasable_online: purchasableOnline,
    is_public: isPublic,
    active,
    items,
  };

  const result = await backendRequest<AdminCatalogKitOut>(
    "/api/v1/admin/config/catalog/kits",
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
  revalidatePath("/admin/config/catalog");
  revalidatePath("/admin/products");
  redirect(appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.kit_created")));
}

export async function updateAdminCatalogKitAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/config?section=products");
  const kitId = parseUuid(String(formData.get("kit_id") ?? ""));
  const title = String(formData.get("title") ?? "").trim();
  const code = optionalField(formData, "code");
  const categoryId = parseUuid(String(formData.get("category_id") ?? ""));
  const priceMode = parseCatalogKitPriceMode(String(formData.get("price_mode") ?? ""));
  const forcedPrice = parseNonNegativeDecimal(String(formData.get("forced_price") ?? ""));
  const legacyPriceInclVat = parseNonNegativeDecimal(String(formData.get("price_incl_vat") ?? ""));
  const effectiveForcedPrice = forcedPrice ?? legacyPriceInclVat;
  const currency = parseCurrencyCode(String(formData.get("currency") ?? "EUR"));
  const vatRate = parseNonNegativeDecimal(String(formData.get("vat_rate") ?? "20"));
  const statusValue = String(formData.get("status") ?? "").trim().toLowerCase();
  const active = statusValue ? statusValue === "active" : checkboxFieldWithDefault(formData, "active", true);
  const isPublic = parseCheckboxFlag(formData, "is_public", true);
  const useInManualBilling = parseCheckboxFlag(formData, "use_in_manual_billing", true);
  const useInEnrollments = parseCheckboxFlag(formData, "use_in_enrollments", true);
  const purchasableOnline = parseCheckboxFlag(formData, "purchasable_online", false);
  const items = parseCatalogKitItemsFromFormData(formData);
  if (!kitId || !title || vatRate === null || items === null || (priceMode === "forced" && effectiveForcedPrice === null)) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_kit")));
  }

  const payload = {
    category_id: categoryId,
    code,
    title,
    image_url: optionalField(formData, "image_url"),
    short_description: optionalField(formData, "short_description"),
    long_description: optionalField(formData, "long_description"),
    price_mode: priceMode,
    forced_price: priceMode === "forced" ? effectiveForcedPrice : null,
    currency,
    price_incl_vat: effectiveForcedPrice ?? 0,
    vat_rate: vatRate,
    use_in_manual_billing: useInManualBilling,
    use_in_enrollments: useInEnrollments,
    purchasable_online: purchasableOnline,
    is_public: isPublic,
    active,
    items,
  };

  const result = await backendRequest<AdminCatalogKitOut>(
    `/api/v1/admin/config/catalog/kits/${kitId}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config");
  revalidatePath("/admin/config/catalog");
  revalidatePath("/admin/products");
  redirect(appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.kit_updated")));
}

export async function deleteAdminCatalogKitAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/config?section=products");
  const kitId = parseUuid(String(formData.get("kit_id") ?? ""));
  if (!kitId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_kit")));
  }
  const result = await backendRequest<void>(
    `/api/v1/admin/config/catalog/kits/${kitId}`,
    {
      method: "DELETE",
    },
    token,
  );
  if (!result.ok && result.status !== 204) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config");
  revalidatePath("/admin/config/catalog");
  revalidatePath("/admin/products");
  redirect(appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.kit_deleted")));
}

export async function duplicateAdminCatalogKitAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const locale = localeForUiLanguage(language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/config/catalog");
  const kitId = parseUuid(String(formData.get("kit_id") ?? ""));
  if (!kitId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_kit")));
  }

  const kitsResult = await backendRequest<AdminCatalogKitOut[]>("/api/v1/admin/config/catalog/kits?include_inactive=true", {}, token);
  if (!kitsResult.ok) {
    redirect(appendQueryMessage(returnTo, "error", kitsResult.message));
  }
  const sourceKit = kitsResult.data.find((row) => row.id === kitId);
  if (!sourceKit) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.kit_not_found")));
  }

  const existingTitles = new Set(kitsResult.data.map((row) => row.title.trim().toLocaleLowerCase(locale)));
  const existingCodes = new Set(
    kitsResult.data
      .map((row) => (row.code || "").trim().toUpperCase())
      .filter((value) => value.length > 0),
  );
  const baseTitle = `${sourceKit.title} ${t("admin.catalog_action.copy_suffix")}`;
  let titleCandidate = baseTitle;
  let titleIndex = 2;
  while (existingTitles.has(titleCandidate.toLocaleLowerCase(locale))) {
    titleCandidate = `${baseTitle} ${titleIndex}`;
    titleIndex += 1;
  }

  let codeCandidate: string | null = sourceKit.code ? `${sourceKit.code}-COPY` : null;
  if (codeCandidate) {
    codeCandidate = codeCandidate.slice(0, 64);
    let codeIndex = 2;
    while (existingCodes.has(codeCandidate)) {
      const suffix = `-COPY-${codeIndex}`;
      codeCandidate = `${sourceKit.code}${suffix}`.slice(0, 64);
      codeIndex += 1;
    }
  }

  const payload = {
    category_id: sourceKit.category_id,
    code: codeCandidate,
    title: titleCandidate,
    image_url: sourceKit.image_url,
    short_description: sourceKit.short_description,
    long_description: sourceKit.long_description,
    price_mode: parseCatalogKitPriceMode(sourceKit.price_mode),
    forced_price: sourceKit.price_mode === "forced" ? Number(sourceKit.forced_price ?? sourceKit.price_effective_incl_vat) : null,
    currency: parseCurrencyCode(sourceKit.currency || "EUR"),
    price_incl_vat: Number(sourceKit.price_effective_incl_vat || sourceKit.price_incl_vat),
    vat_rate: Number(sourceKit.vat_rate),
    use_in_manual_billing: sourceKit.use_in_manual_billing,
    use_in_enrollments: sourceKit.use_in_enrollments,
    purchasable_online: sourceKit.purchasable_online,
    is_public: sourceKit.is_public,
    active: sourceKit.active,
    items: sourceKit.items.map((item) => ({
      product_id: item.product_id,
      quantity: item.quantity,
      display_order: item.display_order,
    })),
  };

  const createResult = await backendRequest<AdminCatalogKitOut>(
    "/api/v1/admin/config/catalog/kits",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
  if (!createResult.ok) {
    redirect(appendQueryMessage(returnTo, "error", createResult.message));
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin/config/catalog");
  revalidatePath("/admin/products");
  redirect(appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.kit_duplicated")));
}

export async function toggleAdminCatalogKitArchiveAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/config/catalog");
  const kitId = parseUuid(String(formData.get("kit_id") ?? ""));
  const archiveValue = String(formData.get("archive") ?? "").trim().toLowerCase();
  const shouldArchive = archiveValue === "1" || archiveValue === "true" || archiveValue === "yes" || archiveValue === "on";
  if (!kitId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_kit")));
  }

  const kitsResult = await backendRequest<AdminCatalogKitOut[]>("/api/v1/admin/config/catalog/kits?include_inactive=true", {}, token);
  if (!kitsResult.ok) {
    redirect(appendQueryMessage(returnTo, "error", kitsResult.message));
  }
  const current = kitsResult.data.find((row) => row.id === kitId);
  if (!current) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.kit_not_found")));
  }
  const items = current.items.map((item) => ({
    product_id: item.product_id,
    quantity: item.quantity,
    display_order: item.display_order,
  }));

  const updateResult = await backendRequest<AdminCatalogKitOut>(
    `/api/v1/admin/config/catalog/kits/${kitId}`,
    {
      method: "PUT",
      body: JSON.stringify({
        category_id: current.category_id,
        code: current.code,
        title: current.title,
        image_url: current.image_url,
        short_description: current.short_description,
        long_description: current.long_description,
        price_mode: parseCatalogKitPriceMode(current.price_mode),
        forced_price: current.price_mode === "forced" ? Number(current.forced_price ?? current.price_effective_incl_vat) : null,
        currency: parseCurrencyCode(current.currency || "EUR"),
        price_incl_vat: Number(current.price_effective_incl_vat || current.price_incl_vat),
        vat_rate: Number(current.vat_rate),
        use_in_manual_billing: current.use_in_manual_billing,
        use_in_enrollments: current.use_in_enrollments,
        purchasable_online: current.purchasable_online,
        is_public: current.is_public,
        active: !shouldArchive,
        items,
      }),
    },
    token,
  );
  if (!updateResult.ok) {
    redirect(appendQueryMessage(returnTo, "error", updateResult.message));
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin/config/catalog");
  revalidatePath("/admin/products");
  redirect(
    appendQueryMessage(
      removeQueryParam(removeQueryParam(returnTo, "ok"), "error"),
      "ok",
      shouldArchive ? t("admin.catalog_action.kit_archived") : t("admin.catalog_action.kit_unarchived"),
    ),
  );
}

export async function updateAdminCatalogInventoryAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/config?section=products");
  const productId = parseUuid(String(formData.get("product_id") ?? ""));
  const locationId = parseUuid(String(formData.get("location_id") ?? ""));
  const inventoryQuantity = parseNonNegativeInt(String(formData.get("inventory_quantity") ?? ""));
  const inventoryDate = parseDateOnly(String(formData.get("inventory_date") ?? ""));
  if (!productId || !locationId || inventoryQuantity === null) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_inventory")));
  }

  const result = await backendRequest<AdminCatalogStockOut>(
    `/api/v1/admin/config/catalog/stocks/${productId}/${locationId}/inventory`,
    {
      method: "PUT",
      body: JSON.stringify({
        inventory_quantity: inventoryQuantity,
        inventory_date: inventoryDate,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config");
  revalidatePath("/admin/products");
  redirect(
    appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.inventory_updated")),
  );
}

export async function updateAdminCatalogReorderStatusAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/products");
  const productId = parseUuid(String(formData.get("product_id") ?? ""));
  const reorderStatus = String(formData.get("reorder_status") ?? "").trim().toUpperCase();
  if (!productId || !reorderStatus) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_reorder_status_update")));
  }

  const result = await backendRequest<AdminCatalogReorderProductOut>(
    `/api/v1/admin/config/catalog/reorder-products/${productId}/status`,
    {
      method: "POST",
      body: JSON.stringify({ reorder_status: reorderStatus }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/products");
  redirect(appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.reorder_status_updated")));
}

export async function createAdminCatalogTransferAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/products");
  const productId = parseUuid(String(formData.get("product_id") ?? ""));
  const sourceLocationId = parseUuid(String(formData.get("source_location_id") ?? ""));
  const targetLocationId = parseUuid(String(formData.get("target_location_id") ?? ""));
  const quantity = parsePositiveInt(String(formData.get("quantity") ?? "1"));
  const plannedTransferDate = parseDateOnly(String(formData.get("planned_transfer_date") ?? ""));
  const assignedToUserId = parseUuid(String(formData.get("assigned_to_user_id") ?? ""));
  const note = optionalField(formData, "note");
  if (!productId || !sourceLocationId || !targetLocationId || quantity === null) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_transfer_request")));
  }
  const result = await backendRequest<AdminCatalogStockTransferOut>(
    "/api/v1/admin/config/catalog/transfers",
    {
      method: "POST",
      body: JSON.stringify({
        product_id: productId,
        source_location_id: sourceLocationId,
        target_location_id: targetLocationId,
        quantity,
        planned_transfer_date: plannedTransferDate,
        assigned_to_user_id: assignedToUserId,
        note,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/products");
  redirect(appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.transfer_created")));
}

export async function completeAdminCatalogTransferAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/products");
  const transferId = parseUuid(String(formData.get("transfer_id") ?? ""));
  const completedTransferDate = parseDateOnly(String(formData.get("completed_transfer_date") ?? ""));
  const note = optionalField(formData, "note");
  if (!transferId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_transfer")));
  }
  const result = await backendRequest<AdminCatalogStockTransferOut>(
    `/api/v1/admin/config/catalog/transfers/${transferId}/complete`,
    {
      method: "POST",
      body: JSON.stringify({
        completed_transfer_date: completedTransferDate,
        note,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/products");
  redirect(appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.transfer_completed")));
}

export async function cancelAdminCatalogTransferAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/products");
  const transferId = parseUuid(String(formData.get("transfer_id") ?? ""));
  const note = optionalField(formData, "note");
  if (!transferId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_transfer")));
  }
  const result = await backendRequest<AdminCatalogStockTransferOut>(
    `/api/v1/admin/config/catalog/transfers/${transferId}/cancel`,
    {
      method: "POST",
      body: JSON.stringify({ note }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/products");
  redirect(appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.transfer_cancelled")));
}

export async function createAdminStockEntryAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/products?view=entries");
  const productId = parseUuid(String(formData.get("product_id") ?? ""));
  const locationId = parseUuid(String(formData.get("location_id") ?? ""));
  const quantity = parseNonNegativeDecimal(String(formData.get("quantity") ?? ""));
  const occurredAtDate = parseDateOnly(String(formData.get("occurred_at") ?? ""));
  const sourceType = String(formData.get("source_type") ?? "other").trim().toLowerCase();
  if (!productId || !locationId || quantity === null || quantity <= 0) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_stock_entry")));
  }
  const payload = {
    product_id: productId,
    location_id: locationId,
    quantity,
    occurred_at: occurredAtDate ? `${occurredAtDate}T00:00:00Z` : null,
    source_type: sourceType,
    source_reference: optionalField(formData, "source_reference"),
    note: optionalField(formData, "note"),
  };
  const result = await backendRequest<AdminStockEntryCreateOut>(
    "/api/v1/admin/stock/entries",
    {
      method: "POST",
      headers: {
        "Idempotency-Key": `entry-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      },
      body: JSON.stringify(payload),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/products");
  redirect(appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.stock_entry_created")));
}

export async function createAdminStockAdjustmentAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/products?view=entries");
  const productId = parseUuid(String(formData.get("adjust_product_id") ?? ""));
  const locationId = parseUuid(String(formData.get("adjust_location_id") ?? ""));
  const quantity = parseSignedDecimal(String(formData.get("adjust_quantity") ?? ""));
  const occurredAtDate = parseDateOnly(String(formData.get("adjust_occurred_at") ?? ""));
  const sourceType = String(formData.get("adjust_source_type") ?? "correction").trim().toLowerCase();
  if (!productId || !locationId || quantity === null || quantity === 0) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_stock_adjustment")));
  }
  const payload = {
    product_id: productId,
    location_id: locationId,
    quantity,
    occurred_at: occurredAtDate ? `${occurredAtDate}T00:00:00Z` : null,
    source_type: sourceType,
    source_reference: optionalField(formData, "adjust_source_reference"),
    note: optionalField(formData, "adjust_note"),
  };
  const result = await backendRequest<AdminStockEntryCreateOut>(
    "/api/v1/admin/stock/adjustments",
    {
      method: "POST",
      headers: {
        "Idempotency-Key": `adjust-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      },
      body: JSON.stringify(payload),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/products");
  redirect(appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.stock_adjustment_created")));
}

export async function createAdminCatalogRequestAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/config?section=products");

  const studentUserId = parseUuid(String(formData.get("student_user_id") ?? ""));
  const productId = parseUuid(String(formData.get("product_id") ?? ""));
  const locationId = parseUuid(String(formData.get("location_id") ?? ""));
  const quantity = parsePositiveInt(String(formData.get("quantity") ?? "1")) ?? 1;
  const shouldBill = checkboxField(formData, "should_bill");
  const note = optionalField(formData, "note");
  if (!studentUserId || !productId || !locationId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_product_request")));
  }

  const result = await backendRequest<AdminCatalogRequestOut>(
    "/api/v1/admin/catalog/requests",
    {
      method: "POST",
      body: JSON.stringify({
        student_user_id: studentUserId,
        product_id: productId,
        location_id: locationId,
        quantity,
        should_bill: shouldBill,
        note,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config");
  revalidatePath("/admin/products");
  revalidatePath("/admin/clients");
  redirect(appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.product_request_created")));
}

export async function reviewAdminCatalogRequestAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/config?section=products");
  const requestId = parseUuid(String(formData.get("request_id") ?? ""));
  const decision = String(formData.get("decision") ?? "").trim().toUpperCase();
  const shouldBill = checkboxField(formData, "should_bill");
  const note = optionalField(formData, "note");
  if (!requestId || (decision !== "ACCEPT" && decision !== "REJECT")) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_request_review")));
  }

  const result = await backendRequest<AdminCatalogRequestOut>(
    `/api/v1/admin/catalog/requests/${requestId}/review`,
    {
      method: "POST",
      body: JSON.stringify({
        accept: decision === "ACCEPT",
        should_bill: decision === "ACCEPT" ? shouldBill : false,
        note,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config");
  revalidatePath("/admin/products");
  revalidatePath("/admin/clients");
  redirect(appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.request_updated")));
}

export async function deliverAdminCatalogRequestAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/config?section=products");
  const requestId = parseUuid(String(formData.get("request_id") ?? ""));
  const deliveredByUserId = parseUuid(String(formData.get("delivered_by_user_id") ?? ""));
  const note = optionalField(formData, "note");
  if (!requestId) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.catalog_action.invalid_request")));
  }

  const result = await backendRequest<AdminCatalogRequestOut>(
    `/api/v1/admin/catalog/requests/${requestId}/deliver`,
    {
      method: "POST",
      body: JSON.stringify({
        delivered_by_user_id: deliveredByUserId,
        note,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config");
  revalidatePath("/admin/products");
  revalidatePath("/admin/clients");
  redirect(
    appendQueryMessage(removeQueryParam(removeQueryParam(returnTo, "ok"), "error"), "ok", t("admin.catalog_action.product_delivered_to_student")),
  );
}

export async function professorCreateCatalogRequestAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureProfessorAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeProfessorReturnPath(formData, "/prof?tab=catalog");
  const studentUserId = parseUuid(String(formData.get("student_user_id") ?? ""));
  const productId = parseUuid(String(formData.get("product_id") ?? ""));
  const locationId = parseUuid(String(formData.get("location_id") ?? ""));
  const quantity = parsePositiveInt(String(formData.get("quantity") ?? "1")) ?? 1;
  const note = optionalField(formData, "note");
  if (!studentUserId || !productId || !locationId) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.catalog_action.invalid_product_request")));
  }

  const result = await backendRequest<AdminCatalogRequestOut>(
    "/api/v1/professors/me/catalog/requests",
    {
      method: "POST",
      body: JSON.stringify({
        student_user_id: studentUserId,
        product_id: productId,
        location_id: locationId,
        quantity,
        note,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/prof");
  redirect(appendQueryMessage(returnTo, "ok", t("teacher.catalog_action.product_request_sent")));
}

export async function professorDeliverCatalogRequestAction(formData: FormData): Promise<void> {
  const token = currentPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureProfessorAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeProfessorReturnPath(formData, "/prof?tab=catalog");
  const requestId = parseUuid(String(formData.get("request_id") ?? ""));
  const note = optionalField(formData, "note");
  if (!requestId) {
    redirect(appendQueryMessage(returnTo, "error", t("teacher.catalog_action.invalid_request")));
  }

  const result = await backendRequest<AdminCatalogRequestOut>(
    `/api/v1/professors/me/catalog/requests/${requestId}/deliver`,
    {
      method: "POST",
      body: JSON.stringify({ note }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/prof");
  redirect(appendQueryMessage(returnTo, "ok", t("teacher.catalog_action.product_delivery_confirmed")));
}

export async function updateAdminConfigPaymentProviderAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = "/admin/config?section=params-payments";

  const payload = {
    provider: String(formData.get("provider") ?? "PAYPLUG").trim().toUpperCase(),
    mode: String(formData.get("mode") ?? "TEST").trim().toUpperCase(),
    payplug_test_secret: optionalField(formData, "payplug_test_secret"),
    payplug_live_secret: optionalField(formData, "payplug_live_secret"),
    mollie_test_api_key: optionalField(formData, "mollie_test_api_key"),
    mollie_live_api_key: optionalField(formData, "mollie_live_api_key"),
    stripe_test_secret: optionalField(formData, "stripe_test_secret"),
    stripe_live_secret: optionalField(formData, "stripe_live_secret"),
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
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config");
  redirect(appendQueryMessage(returnTo, "ok", t("admin.payment_action.provider_updated")));
}

export async function updateAdminConfigExternalContentSettingsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);

  const timeoutSeconds = Number.parseInt(String(formData.get("timeout_seconds") ?? "").trim() || "20", 10);
  const payload = {
    base_url: String(formData.get("base_url") ?? "").trim(),
    courses_endpoint: String(formData.get("courses_endpoint") ?? "").trim(),
    bearer_token: optionalField(formData, "bearer_token"),
    clear_bearer_token: checkboxField(formData, "clear_bearer_token"),
    timeout_seconds: Number.isFinite(timeoutSeconds) ? timeoutSeconds : 20,
  };

  const result = await backendRequest<AdminExternalContentSettingsOut>(
    "/api/v1/admin/config/external-content/wordpress-learndash",
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(`/admin/config?section=activities&error=${encodeURIComponent(result.message)}`);
  }

  revalidatePath("/admin/config");
  redirect("/admin/config?section=activities&ok=Connexion%20WordPress%20LearnDash%20mise%20a%20jour");
}

function normalizeMessagingConfigTab(raw: string, fallback = "settings"): string {
  const value = raw.trim().toLowerCase();
  if (
    value === "settings" ||
    value === "predefined-email" ||
    value === "predefined-sms" ||
    value === "custom-email" ||
    value === "custom-sms" ||
    value === "group-notes"
  ) {
    return value;
  }
  return fallback;
}

function buildMessagingConfigPath(tab: string, params: Record<string, string> = {}): string {
  const searchParams = new URLSearchParams();
  searchParams.set("section", "params-messaging");
  searchParams.set("messaging_tab", normalizeMessagingConfigTab(tab));
  for (const [key, value] of Object.entries(params)) {
    if (!value) {
      continue;
    }
    searchParams.set(key, value);
  }
  return `/admin/config?${searchParams.toString()}`;
}

export async function updateAdminConfigMessagingSettingsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const messagingTab = normalizeMessagingConfigTab(String(formData.get("messaging_tab") ?? ""), "settings");
  const smtpPort = Number.parseInt(String(formData.get("smtp_port") ?? "").trim() || "587", 10);
  const smtpTimeoutSeconds = Number.parseInt(String(formData.get("smtp_timeout_seconds") ?? "").trim() || "15", 10);

  const payload = {
    studio_email: String(formData.get("studio_email") ?? "").trim(),
    studio_sender_name: String(formData.get("studio_sender_name") ?? "").trim(),
    teacher_sender_name: String(formData.get("teacher_sender_name") ?? "").trim(),
    use_studio_name_as_default_sender: checkboxField(formData, "use_studio_name_as_default_sender"),
    use_studio_email_for_reminders: checkboxField(formData, "use_studio_email_for_reminders"),
    use_studio_email_for_lesson_notes: checkboxField(formData, "use_studio_email_for_lesson_notes"),
    send_birthday_emails: checkboxField(formData, "send_birthday_emails"),
    email_provider: String(formData.get("email_provider") ?? "LOG").trim().toUpperCase(),
    email_reply_to: String(formData.get("email_reply_to") ?? "").trim(),
    email_subject_prefix: String(formData.get("email_subject_prefix") ?? "").trim(),
    smtp_host: String(formData.get("smtp_host") ?? "").trim(),
    smtp_port: Number.isFinite(smtpPort) ? smtpPort : 587,
    smtp_username: String(formData.get("smtp_username") ?? "").trim(),
    smtp_password: String(formData.get("smtp_password") ?? "").trim(),
    smtp_use_tls: checkboxField(formData, "smtp_use_tls"),
    smtp_use_ssl: checkboxField(formData, "smtp_use_ssl"),
    smtp_timeout_seconds: Number.isFinite(smtpTimeoutSeconds) ? smtpTimeoutSeconds : 15,
    frontend_base_url: String(formData.get("frontend_base_url") ?? "").trim(),
    sms_provider: String(formData.get("sms_provider") ?? "LOG").trim().toUpperCase(),
    sms_sender: String(formData.get("sms_sender") ?? "").trim(),
    brevo_sms_api_key: String(formData.get("brevo_sms_api_key") ?? "").trim(),
    quote_send_template_ref: String(formData.get("quote_send_template_ref") ?? "").trim(),
    quote_send_sms_template_ref: String(formData.get("quote_send_sms_template_ref") ?? "").trim(),
    quote_reminder_template_ref: String(formData.get("quote_reminder_template_ref") ?? "").trim(),
    quote_reminder_sms_template_ref: String(formData.get("quote_reminder_sms_template_ref") ?? "").trim(),
    quote_cancel_template_ref: String(formData.get("quote_cancel_template_ref") ?? "").trim(),
    quote_cancel_sms_template_ref: String(formData.get("quote_cancel_sms_template_ref") ?? "").trim(),
    quote_approved_template_ref: String(formData.get("quote_approved_template_ref") ?? "").trim(),
    quote_rejected_template_ref: String(formData.get("quote_rejected_template_ref") ?? "").trim(),
    quote_change_requested_template_ref: String(formData.get("quote_change_requested_template_ref") ?? "").trim(),
    quote_reminder_enabled: checkboxField(formData, "quote_reminder_enabled"),
    quote_reminder_sms_enabled: checkboxField(formData, "quote_reminder_sms_enabled"),
    quote_reminder_lead_hours: Number.parseInt(String(formData.get("quote_reminder_lead_hours") ?? "").trim() || "24", 10),
    quote_reminder_lead_hours_csv: String(formData.get("quote_reminder_lead_hours_csv") ?? "").trim() || "24",
    quote_daily_job_local_time: String(formData.get("quote_daily_job_local_time") ?? "").trim() || "07:00",
    quote_auto_cancel_enabled: checkboxField(formData, "quote_auto_cancel_enabled"),
    quote_auto_cancel_delay_hours: Number.parseInt(String(formData.get("quote_auto_cancel_delay_hours") ?? "").trim() || "24", 10),
    quote_cancel_notification_enabled: checkboxField(formData, "quote_cancel_notification_enabled"),
    quote_cancel_sms_notification_enabled: checkboxField(formData, "quote_cancel_sms_notification_enabled"),
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
    redirect(buildMessagingConfigPath(messagingTab, { error: result.message }));
  }

  revalidatePath("/admin/config");
  redirect(buildMessagingConfigPath(messagingTab, { ok: t("admin.messaging_action.settings_updated") }));
}

export async function updateAdminConfigInvoiceTemplateAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = "/admin/config?section=params-messaging";

  const body = String(formData.get("body") ?? "").trim();
  if (!body) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.billing_action.invoice_template_required")));
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
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin/clients");
  redirect(appendQueryMessage(returnTo, "ok", t("admin.billing_action.invoice_template_updated")));
}

export async function updateAdminConfigInvoiceNumberingAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = "/admin/config?section=params-messaging";

  const formatPattern = String(formData.get("format_pattern") ?? "").trim();
  const nextNumberRaw = String(formData.get("next_number") ?? "").trim();
  const nextNumber = Number.parseInt(nextNumberRaw, 10);

  if (!formatPattern) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.billing_action.invoice_number_format_required")));
  }
  if (!Number.isFinite(nextNumber) || nextNumber < 1) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.billing_action.invalid_next_invoice_number")));
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
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin/clients");
  redirect(appendQueryMessage(returnTo, "ok", t("admin.billing_action.invoice_numbering_updated")));
}

export async function updateAdminTeacherInvoiceTemplateAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = "/admin/teacher-invoicing/template";

  const htmlTemplate = String(formData.get("html_template") ?? "").trim();
  if (!htmlTemplate) {
    redirect(appendQueryMessage(returnTo, "error", t("admin.teacher_invoice_action.html_template_required")));
  }

  const result = await backendRequest<AdminTeacherInvoiceTemplateOut>(
    "/api/v1/admin/teacher-invoice-template",
    {
      method: "PUT",
      body: JSON.stringify({ html_template: htmlTemplate }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/teacher-invoicing/template");
  redirect(appendQueryMessage(returnTo, "ok", t("admin.teacher_invoice_action.template_updated")));
}

export async function saveAdminConfigMessagingTemplateAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const templateKind = String(formData.get("template_kind") ?? "").trim().toUpperCase();
  const templateChannel = String(formData.get("template_channel") ?? "").trim().toUpperCase();
  const templateCode = String(formData.get("template_code") ?? "").trim().toUpperCase();
  const templateId = String(formData.get("template_id") ?? "").trim();
  const name = String(formData.get("name") ?? "").trim();
  const subject = localizedBaseField(formData, "subject");
  const subjectTranslations = localizedTranslationsField(formData, "subject");
  const body = localizedBaseField(formData, "body") ?? "";
  const bodyTranslations = localizedTranslationsField(formData, "body");
  const bodyFormat = String(formData.get("body_format") ?? "TEXT").trim().toUpperCase() === "HTML" ? "HTML" : "TEXT";
  const active = checkboxField(formData, "active");
  const usageContexts = parseStringList(formData.getAll("usage_contexts"));
  const requestedTabRaw = String(formData.get("messaging_tab") ?? "");

  const defaultTabForChannel =
    templateChannel === "EMAIL"
      ? templateKind === "PREDEFINED"
        ? "predefined-email"
        : "custom-email"
      : templateChannel === "SMS"
        ? templateKind === "PREDEFINED"
          ? "predefined-sms"
          : "custom-sms"
        : "group-notes";
  const messagingTab = normalizeMessagingConfigTab(requestedTabRaw, defaultTabForChannel);

  if (!body) {
    redirect(buildMessagingConfigPath(messagingTab, { error: t("admin.messaging_action.body_required") }));
  }

  if (templateKind === "PREDEFINED") {
    if (!templateCode) {
      redirect(buildMessagingConfigPath(messagingTab, { error: t("admin.messaging_action.predefined_template_not_found") }));
    }

    const result = await backendRequest<AdminMessagingTemplateOut>(
      `/api/v1/admin/config/messaging-templates/predefined/${encodeURIComponent(templateCode)}`,
      {
        method: "PUT",
        body: JSON.stringify({
          subject,
          subject_translations: subjectTranslations,
          body,
          body_translations: bodyTranslations,
          body_format: bodyFormat,
          active,
        }),
      },
      token,
    );

    if (!result.ok) {
      redirect(buildMessagingConfigPath(messagingTab, { error: result.message }));
    }

    revalidatePath("/admin/config");
    redirect(buildMessagingConfigPath(messagingTab, { ok: t("admin.messaging_action.predefined_template_updated") }));
  }

  if (templateKind !== "CUSTOM") {
    redirect(buildMessagingConfigPath(messagingTab, { error: t("admin.messaging_action.invalid_template_kind") }));
  }

  if (!name) {
    redirect(buildMessagingConfigPath(messagingTab, { error: t("admin.messaging_action.template_name_required") }));
  }
  if (templateChannel !== "EMAIL" && templateChannel !== "SMS" && templateChannel !== "GROUP_NOTE") {
    redirect(buildMessagingConfigPath(messagingTab, { error: t("admin.messaging_action.invalid_channel") }));
  }
  if (templateChannel === "EMAIL" && !subject) {
    redirect(buildMessagingConfigPath(messagingTab, { error: t("admin.messaging_action.email_subject_required") }));
  }

  const payload = {
    channel: templateChannel,
    name,
    subject,
    subject_translations: subjectTranslations,
    body,
    body_translations: bodyTranslations,
    body_format: bodyFormat,
    active,
    usage_contexts: usageContexts,
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
    redirect(buildMessagingConfigPath(messagingTab, { error: result.message }));
  }

  revalidatePath("/admin/config");
  redirect(
    buildMessagingConfigPath(
      messagingTab,
      {
        ok: templateId ? t("admin.messaging_action.custom_template_updated") : t("admin.messaging_action.custom_template_created"),
      },
    ),
  );
}

export async function resetAdminConfigPredefinedMessagingTemplateAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const messagingTab = normalizeMessagingConfigTab(String(formData.get("messaging_tab") ?? ""), "predefined-email");

  const templateCode = String(formData.get("template_code") ?? "").trim().toUpperCase();
  if (!templateCode) {
    redirect(buildMessagingConfigPath(messagingTab, { error: t("admin.messaging_action.predefined_template_not_found") }));
  }

  const result = await backendRequest<AdminMessagingTemplateOut>(
    `/api/v1/admin/config/messaging-templates/predefined/${encodeURIComponent(templateCode)}`,
    {
      method: "DELETE",
    },
    token,
  );

  if (!result.ok) {
    redirect(buildMessagingConfigPath(messagingTab, { error: result.message }));
  }

  revalidatePath("/admin/config");
  redirect(buildMessagingConfigPath(messagingTab, { ok: t("admin.messaging_action.predefined_template_restored") }));
}

export async function deleteAdminConfigMessagingTemplateAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const messagingTab = normalizeMessagingConfigTab(String(formData.get("messaging_tab") ?? ""), "custom-email");

  const templateId = String(formData.get("template_id") ?? "").trim();
  if (!templateId) {
    redirect(buildMessagingConfigPath(messagingTab, { error: t("admin.messaging_action.template_not_found") }));
  }

  const result = await backendRequest<Record<string, never>>(
    `/api/v1/admin/config/messaging-templates/custom/${encodeURIComponent(templateId)}`,
    { method: "DELETE" },
    token,
  );

  if (!result.ok) {
    redirect(buildMessagingConfigPath(messagingTab, { error: result.message }));
  }

  revalidatePath("/admin/config");
  redirect(buildMessagingConfigPath(messagingTab, { ok: t("admin.messaging_action.custom_template_deleted") }));
}

export async function updateAdminClientPasswordEmailTemplateAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const subject = String(formData.get("subject") ?? "").trim();
  const body = String(formData.get("body") ?? "").trim();
  if (!subject || !body) {
    redirect(appendQueryMessage("/admin/config?section=params-messaging", "error", t("admin.messaging_action.client_password_subject_body_required")));
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
  redirect(appendQueryMessage("/admin/config?section=params-messaging", "ok", t("admin.messaging_action.client_password_template_updated")));
}

export async function createAdminFormulaAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const returnTo = safeAdminReturnPath(formData, "/admin/config/formulas/new");

  let payload: Record<string, unknown>;
  try {
    payload = parseFormulaPayload(formData, t);
  } catch (error) {
    const message = error instanceof Error ? error.message : t("admin.formula_action.invalid_form_payload");
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
    redirect(appendQueryMessage(`/admin/config/formulas/${result.data.id}`, "ok", t("admin.formula_action.created")));
  }

  redirect(appendQueryMessage("/admin/config/formulas", "ok", t("admin.formula_action.created")));
}

export async function updateAdminFormulaAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const formulaId = String(formData.get("formula_id") ?? "").trim();
  if (!formulaId) {
    redirect(appendQueryMessage("/admin/config/formulas", "error", t("admin.formula_action.invalid_formula")));
  }
  const returnTo = safeAdminReturnPath(formData, `/admin/config/formulas/${formulaId}`);

  let payload: Record<string, unknown>;
  try {
    payload = parseFormulaPayload(formData, t);
  } catch (error) {
    const message = error instanceof Error ? error.message : t("admin.formula_action.invalid_form_payload");
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
  redirect(appendQueryMessage(returnTo, "ok", t("admin.formula_action.updated")));
}

export async function duplicateAdminFormulaAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const formulaId = String(formData.get("formula_id") ?? "").trim();
  if (!formulaId) {
    redirect(appendQueryMessage("/admin/config/formulas", "error", t("admin.formula_action.invalid_formula")));
  }
  const returnTo = safeAdminReturnPath(formData, "/admin/config/formulas");

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
    redirect(appendQueryMessage(`/admin/config/formulas/${result.data.id}`, "ok", t("admin.formula_action.duplicated")));
  }

  redirect(appendQueryMessage("/admin/config/formulas", "ok", t("admin.formula_action.duplicated")));
}

export async function disableAdminFormulaAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const formulaId = String(formData.get("formula_id") ?? "").trim();
  if (!formulaId) {
    redirect(appendQueryMessage("/admin/config/formulas", "error", t("admin.formula_action.invalid_formula")));
  }
  const returnTo = safeAdminReturnPath(formData, "/admin/config/formulas");

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
  redirect(appendQueryMessage(returnTo, "ok", t("admin.formula_action.disabled")));
}

export async function updatePlanningActivitiesAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const locationId = String(formData.get("location_id") ?? "").trim();
  if (!locationId) {
    redirect(appendQueryMessage("/admin", "error", t("admin.planning_action.invalid_planning")));
  }

  const activityIds = parseStringList(formData.getAll("activity_ids"));
  if (activityIds.length === 0) {
    redirect(appendQueryMessage(`/admin/plannings/${locationId}/settings`, "error", t("admin.planning_action.select_at_least_one_activity")));
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
    redirect(appendQueryMessage(`/admin/plannings/${locationId}/settings`, "error", result.message));
  }

  revalidatePath("/admin");
  revalidatePath(`/admin/plannings/${locationId}/settings`);
  redirect(appendQueryMessage(`/admin/plannings/${locationId}/settings`, "ok", t("admin.planning_action.planning_activities_updated")));
}

async function syncActivityPlanningAssignments(params: {
  token: string;
  activityId: string;
  selectedLocationIds: string[];
  scopeLocationIds: string[];
  t: UiTextResolver;
}): Promise<{ ok: true } | { ok: false; message: string }> {
  const activityId = params.activityId.trim();
  const scopeLocationIds = Array.from(new Set(params.scopeLocationIds.map((value) => value.trim()).filter(Boolean)));
  if (!activityId || scopeLocationIds.length === 0) {
    return { ok: true };
  }

  const selectedLocationIds = new Set(
    params.selectedLocationIds.map((value) => value.trim()).filter((value) => scopeLocationIds.includes(value)),
  );

  for (const locationId of scopeLocationIds) {
    const planningResult = await backendRequest<AdminPlanningActivitiesOut>(
      `/api/v1/admin/plannings/${locationId}/activities`,
      {},
      params.token,
    );
    if (!planningResult.ok) {
      return {
        ok: false,
        message: params.t("admin.activity_action.planning_load_failed", {
          locationId,
          message: planningResult.message,
        }),
      };
    }

    const planning = planningResult.data;
    const currentIds = planning.selected_activity_ids;
    const isCurrentlySelected = currentIds.includes(activityId);
    const shouldBeSelected = selectedLocationIds.has(locationId);

    if (isCurrentlySelected === shouldBeSelected) {
      continue;
    }

    const nextIds = shouldBeSelected
      ? [...currentIds, activityId]
      : currentIds.filter((candidateId) => candidateId !== activityId);

    if (nextIds.length === 0) {
      return {
        ok: false,
        message: params.t("admin.activity_action.planning_requires_one_activity", {
          location: planning.location_name,
        }),
      };
    }

    const updateResult = await backendRequest<AdminPlanningActivitiesOut>(
      `/api/v1/admin/plannings/${locationId}/activities`,
      {
        method: "PUT",
        body: JSON.stringify({ activity_ids: nextIds }),
      },
      params.token,
    );
    if (!updateResult.ok) {
      return {
        ok: false,
        message: params.t("admin.activity_action.planning_sync_failed", {
          location: planning.location_name,
          message: updateResult.message,
        }),
      };
    }

    revalidatePath(`/admin/plannings/${locationId}/settings`);
  }

  return { ok: true };
}

async function syncActivityContentMappings(params: {
  token: string;
  activityId: string;
  contentCourseIds: string[];
  t: UiTextResolver;
}): Promise<{ ok: true; data: AdminActivityContentMappingOut[] } | { ok: false; message: string }> {
  const activityId = params.activityId.trim();
  if (!activityId) {
    return { ok: false, message: params.t("admin.activity_action.invalid_activity") };
  }
  const contentCourseIds = Array.from(new Set(params.contentCourseIds.map((value) => value.trim()).filter(Boolean)));
  const result = await backendRequest<AdminActivityContentMappingOut[]>(
    `/api/v1/admin/activities/${activityId}/content-mappings`,
    {
      method: "PUT",
      body: JSON.stringify({
        content_course_ids: contentCourseIds,
        access_rule: "ACTIVE_ENROLLMENT",
      }),
    },
    params.token,
  );
  if (!result.ok) {
    return { ok: false, message: result.message };
  }
  return { ok: true, data: result.data };
}

export async function syncAdminExternalContentCatalogAction(): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  await ensureAdmin(token);

  const result = await backendRequest<AdminExternalContentSyncOut>(
    "/api/v1/admin/external-content/sync/wordpress-learndash",
    {
      method: "POST",
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage("/admin/config?section=activities", "error", result.message));
  }

  revalidatePath("/admin/config");
  revalidatePath("/admin");
  redirect(
    appendQueryMessage(
      "/admin/config?section=activities",
      "ok",
      `Catalogue LearnDash synchronise (${result.data.courses_seen} cours)`,
    ),
  );
}

type QuoteWizardLinePayload = {
  line_category: "service" | "product";
  line_type: "item" | "discount" | "surcharge";
  master_item_type: "activity" | "product" | "kit" | "option" | "discount_rule" | "surcharge_rule" | null;
  activity_id: string | null;
  product_id: string | null;
  kit_id: string | null;
  title: string;
  quantity: string;
  vat_rate: string;
  unit_price_ttc: string;
  sort_order: number;
  meta: Record<string, unknown>;
};

function safeAdminQuotesPath(path: string, fallback = "/admin/quotes"): string {
  const value = path.trim();
  if (value.startsWith("/admin/quotes")) {
    return value;
  }
  return fallback;
}

function safeAdminProspectsPath(path: string, fallback = "/admin/prospects"): string {
  const value = path.trim();
  if (value.startsWith("/admin/prospects") || value.startsWith("/admin/quotes")) {
    return value;
  }
  return fallback;
}

function safeAdminIntakesPath(path: string, fallback = "/admin/intakes"): string {
  const value = path.trim();
  if (value.startsWith("/admin/intakes") || value.startsWith("/admin/quotes")) {
    return value;
  }
  return fallback;
}

function collectTypeformSelectedSessionIds(formData: FormData): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of formData.entries()) {
    if (!key.startsWith("selected_session_for_")) {
      continue;
    }
    const activityId = key.slice("selected_session_for_".length).trim();
    const sessionId = String(value ?? "").trim();
    if (!activityId || !sessionId) {
      continue;
    }
    out[activityId] = sessionId;
  }
  return out;
}

export async function saveTypeformIntakeResolutionAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  await ensureAdmin(token);

  const intakeId = String(formData.get("intake_id") ?? "").trim();
  const returnTo = safeAdminIntakesPath(String(formData.get("return_to") ?? "/admin/intakes"));
  const cleanReturnTo = setQueryParam(
    setQueryParam(
      setQueryParam(returnTo, "error", null),
      "ok",
      null,
    ),
    "success_modal",
    null,
  );
  if (!intakeId) {
    redirect(appendQueryMessage(cleanReturnTo, "error", "Intake introuvable"));
  }

  const clientModeRaw = String(formData.get("client_mode") ?? "").trim();
  const clientMode =
    clientModeRaw === "existing_client"
    || clientModeRaw === "existing_family"
    || clientModeRaw === "new_parent_child_prospect"
    || clientModeRaw === "new_adult_prospect"
      ? clientModeRaw
      : "new_adult_prospect";

  const selectedClientId = parseUuid(String(formData.get("selected_client_id") ?? ""));
  const selectedFamilyAdultClientId = parseUuid(String(formData.get("selected_family_adult_client_id") ?? ""));
  const selectedFamilyChildClientId = parseUuid(String(formData.get("selected_family_child_client_id") ?? ""));
  const selectedFamilyBillingClientId = parseUuid(String(formData.get("selected_family_billing_client_id") ?? ""));
  const notes = optionalField(formData, "resolution_notes");
  const selectedSessionIds = collectTypeformSelectedSessionIds(formData);

  const result = await backendRequest<{ id: string }>(
    `/api/v1/typeform/intakes/${encodeURIComponent(intakeId)}/resolution`,
    {
      method: "PATCH",
      body: JSON.stringify({
        resolution: {
          client_resolution: {
            mode: clientMode,
            selected_client_id: selectedClientId,
            selected_family_adult_client_id: selectedFamilyAdultClientId,
            selected_family_child_client_id: selectedFamilyChildClientId,
            selected_family_billing_client_id: selectedFamilyBillingClientId,
          },
          slot_resolution: {
            selected_session_ids: selectedSessionIds,
          },
          notes,
        },
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(cleanReturnTo, "error", result.message));
  }

  revalidatePath("/admin/intakes");
  revalidatePath(`/admin/intakes/${intakeId}`);
  redirect(
    setQueryParam(
      appendQueryMessage(cleanReturnTo, "ok", "Arbitrage enregistre"),
      "success_modal",
      "resolution_saved",
    ),
  );
}

export async function saveTypeformIntakeReferralAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const intakeId = String(formData.get("intake_id") ?? "").trim();
  const returnTo = safeAdminIntakesPath(String(formData.get("return_to") ?? "/admin/intakes"));
  const cleanReturnTo = setQueryParam(setQueryParam(returnTo, "error", null), "ok", null);
  const referrerUserId = parseUuid(String(formData.get("referrer_user_id") ?? ""));
  if (!intakeId || !referrerUserId) {
    redirect(appendQueryMessage(cleanReturnTo, "error", adminReferralActionText(language, "referral_incomplete")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/typeform/intakes/${encodeURIComponent(intakeId)}/referral`,
    {
      method: "PATCH",
      body: JSON.stringify({ referrer_user_id: referrerUserId }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(cleanReturnTo, "error", result.message));
  }

  revalidatePath("/admin/intakes");
  revalidatePath(`/admin/intakes/${intakeId}`);
  redirect(appendQueryMessage(cleanReturnTo, "ok", adminReferralActionText(language, "referral_validated")));
}

export async function reanalyzeTypeformIntakeAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  await ensureAdmin(token);

  const intakeId = String(formData.get("intake_id") ?? "").trim();
  const returnTo = safeAdminIntakesPath(String(formData.get("return_to") ?? "/admin/intakes"));
  const cleanReturnTo = setQueryParam(
    setQueryParam(
      setQueryParam(returnTo, "error", null),
      "ok",
      null,
    ),
    "success_modal",
    null,
  );
  if (!intakeId) {
    redirect(appendQueryMessage(cleanReturnTo, "error", "Intake introuvable"));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/typeform/intakes/${encodeURIComponent(intakeId)}/reanalyze`,
    { method: "POST" },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(cleanReturnTo, "error", result.message));
  }

  revalidatePath("/admin/intakes");
  revalidatePath(`/admin/intakes/${intakeId}`);
  redirect(appendQueryMessage(cleanReturnTo, "ok", "Analyse des propositions mise a jour"));
}

export async function saveTypeformIntakeNormalizedDataAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  await ensureAdmin(token);

  const intakeId = String(formData.get("intake_id") ?? "").trim();
  const returnTo = safeAdminIntakesPath(String(formData.get("return_to") ?? "/admin/intakes"));
  const cleanReturnTo = setQueryParam(
    setQueryParam(
      setQueryParam(
        setQueryParam(returnTo, "editor", null),
        "editor_error",
        null,
      ),
      "error",
      null,
    ),
    "ok",
    null,
  );
  if (!intakeId) {
    redirect(setQueryParam(cleanReturnTo, "error", "Intake introuvable"));
  }

  const normalizedPayload = {
    parent_first_name: optionalField(formData, "parent_first_name"),
    parent_last_name: optionalField(formData, "parent_last_name"),
    parent_email: optionalField(formData, "parent_email"),
    parent_phone: optionalField(formData, "parent_phone"),
    child_first_name: optionalField(formData, "child_first_name"),
    child_last_name: optionalField(formData, "child_last_name"),
    child_birth_date: optionalField(formData, "child_birth_date"),
    customer_type: optionalField(formData, "customer_type"),
    requested_course_mode: optionalField(formData, "requested_course_mode"),
    requested_location: optionalField(formData, "requested_location"),
    requested_days: multiValueField(formData, "requested_days"),
    requested_times: multiValueField(formData, "requested_times"),
    requested_slot_preferences: multiValueField(formData, "requested_slot_preferences"),
    requested_formula_type: optionalField(formData, "requested_formula_type"),
    requested_products: multiValueField(formData, "requested_products"),
    referral_referrer_name: optionalField(formData, "referral_referrer_name"),
    referral_category: optionalField(formData, "referral_category"),
    notes: optionalField(formData, "notes"),
  };

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/typeform/intakes/${encodeURIComponent(intakeId)}/normalized`,
    {
      method: "PATCH",
      body: JSON.stringify({
        normalized_payload_json: normalizedPayload,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(setQueryParam(setQueryParam(cleanReturnTo, "editor", "normalized"), "editor_error", result.message));
  }

  revalidatePath("/admin/intakes");
  revalidatePath(`/admin/intakes/${intakeId}`);
  redirect(setQueryParam(cleanReturnTo, "ok", "Donnees normalisees mises a jour"));
}

export async function ignoreTypeformIntakeAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  await ensureAdmin(token);

  const intakeId = String(formData.get("intake_id") ?? "").trim();
  const returnTo = safeAdminIntakesPath(String(formData.get("return_to") ?? "/admin/intakes"));
  if (!intakeId) {
    redirect(appendQueryMessage(returnTo, "error", "Intake introuvable"));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/typeform/intakes/${encodeURIComponent(intakeId)}/admin-state`,
    {
      method: "PATCH",
      body: JSON.stringify({ ignored: true }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/intakes");
  revalidatePath(`/admin/intakes/${intakeId}`);
  redirect(appendQueryMessage(returnTo, "ok", "Intake ignoree"));
}

export async function restoreTypeformIntakeAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  await ensureAdmin(token);

  const intakeId = String(formData.get("intake_id") ?? "").trim();
  const returnTo = safeAdminIntakesPath(String(formData.get("return_to") ?? "/admin/intakes"));
  if (!intakeId) {
    redirect(appendQueryMessage(returnTo, "error", "Intake introuvable"));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/typeform/intakes/${encodeURIComponent(intakeId)}/admin-state`,
    {
      method: "PATCH",
      body: JSON.stringify({ ignored: false }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/intakes");
  revalidatePath(`/admin/intakes/${intakeId}`);
  redirect(appendQueryMessage(returnTo, "ok", "Intake reactivee"));
}

export async function deleteTypeformIntakeAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  await ensureAdmin(token);

  const intakeId = String(formData.get("intake_id") ?? "").trim();
  const returnTo = safeAdminIntakesPath(String(formData.get("return_to") ?? "/admin/intakes"));
  if (!intakeId) {
    redirect(appendQueryMessage(returnTo, "error", "Intake introuvable"));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/typeform/intakes/${encodeURIComponent(intakeId)}`,
    {
      method: "DELETE",
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/intakes");
  revalidatePath(`/admin/intakes/${intakeId}`);
  redirect(appendQueryMessage(returnTo, "ok", "Intake supprimee"));
}

export async function generateTypeformDraftQuoteAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  await ensureAdmin(token);

  const intakeId = String(formData.get("intake_id") ?? "").trim();
  const allowEmptyQuote = String(formData.get("allow_empty_quote") ?? "").trim() === "1";
  const familyOnlyQuote = String(formData.get("family_only_quote") ?? "").trim() === "1";
  const returnTo = safeAdminIntakesPath(String(formData.get("return_to") ?? "/admin/intakes"));
  if (!intakeId) {
    redirect(setQueryParam(returnTo, "error", "Intake introuvable"));
  }

  const query = new URLSearchParams();
  if (allowEmptyQuote) {
    query.set("allow_empty_quote", "true");
  }
  if (familyOnlyQuote) {
    query.set("family_only_quote", "true");
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const result = await backendRequest<{ quote_id: string }>(
    `/api/v1/typeform/intakes/${encodeURIComponent(intakeId)}/draft-quote${suffix}`,
    {
      method: "POST",
    },
    token,
  );

  if (!result.ok) {
    redirect(setQueryParam(setQueryParam(returnTo, "ok", null), "error", result.message));
  }

  revalidatePath("/admin/intakes");
  revalidatePath("/admin/quotes");
  redirect(`/admin/quotes/${encodeURIComponent(result.data.quote_id)}?back=${encodeURIComponent("/admin/intakes")}&ok=${encodeURIComponent("Devis brouillon cree depuis intake")}`);
}

export async function seedTypeformDemoAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  await ensureAdmin(token);

  const returnTo = safeAdminIntakesPath(String(formData.get("return_to") ?? "/admin/intakes"));
  const result = await backendRequest<{ created_intakes: number; created_form_configs: number }>(
    "/api/v1/typeform/demo/seed",
    {
      method: "POST",
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/intakes");
  redirect(
    appendQueryMessage(
      returnTo,
      "ok",
      `Demo Typeform chargee (${result.data.created_form_configs} configs, ${result.data.created_intakes} intakes)`,
    ),
  );
}

function parseQuoteWizardLines(raw: string): QuoteWizardLinePayload[] {
  const value = raw.trim();
  if (!value) {
    return [];
  }
  try {
    const parsed = JSON.parse(value);
    if (!Array.isArray(parsed)) {
      return [];
    }
    const out: QuoteWizardLinePayload[] = [];
    for (const item of parsed) {
      if (!item || typeof item !== "object") {
        continue;
      }
      const row = item as Record<string, unknown>;
      const lineCategory = String(row.line_category ?? "").trim().toLowerCase();
      const lineType = String(row.line_type ?? "").trim().toLowerCase();
      const title = String(row.title ?? "").trim();
      const quantity = String(row.quantity ?? "").trim();
      const vatRate = String(row.vat_rate ?? "").trim();
      const unitPrice = String(row.unit_price_ttc ?? "").trim();
      const sortOrder = Number.parseInt(String(row.sort_order ?? "0"), 10);
      const meta =
        row.meta && typeof row.meta === "object" && !Array.isArray(row.meta)
          ? (row.meta as Record<string, unknown>)
          : {};
      if ((lineCategory !== "service" && lineCategory !== "product") || (lineType !== "item" && lineType !== "discount" && lineType !== "surcharge")) {
        continue;
      }
      if (!title) {
        continue;
      }
      if (!Number.isFinite(Number(quantity)) || Number(quantity) <= 0) {
        continue;
      }
      if (!Number.isFinite(Number(unitPrice))) {
        continue;
      }
      if (vatRate && (!Number.isFinite(Number(vatRate)) || Number(vatRate) < 0 || Number(vatRate) > 100)) {
        continue;
      }
      const activityId = parseUuid(String(row.activity_id ?? "")) ?? null;
      const productId = parseUuid(String(row.product_id ?? "")) ?? null;
      const kitId = parseUuid(String(row.kit_id ?? "")) ?? null;
      const masterTypeRaw = String(row.master_item_type ?? "").trim().toLowerCase();
      const masterType =
        masterTypeRaw === "activity" ||
        masterTypeRaw === "product" ||
        masterTypeRaw === "kit" ||
        masterTypeRaw === "option" ||
        masterTypeRaw === "discount_rule" ||
        masterTypeRaw === "surcharge_rule"
          ? masterTypeRaw
          : null;
      out.push({
        line_category: lineCategory,
        line_type: lineType,
        master_item_type: masterType,
        activity_id: activityId,
        product_id: productId,
        kit_id: kitId,
        title,
        quantity,
        vat_rate: vatRate || "0",
        unit_price_ttc: unitPrice,
        sort_order: Number.isFinite(sortOrder) ? sortOrder : 0,
        meta,
      });
    }
    return out;
  } catch {
    return [];
  }
}

export async function createQuoteProspectAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const adminLanguage = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? "/admin/quotes"));
  const successReturnTo = withUiLanguage(returnTo, adminLanguage);
  const email = String(formData.get("prospect_email") ?? "").trim().toLowerCase();
  const firstName = String(formData.get("prospect_first_name") ?? "").trim();
  const lastName = String(formData.get("prospect_last_name") ?? "").trim();
  const phone = String(formData.get("prospect_phone") ?? "").trim();

  if (!email || !email.includes("@")) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_prospect_email_invalid", { lang: adminLanguage }));
  }

  const result = await backendRequest<{ id: string }>(
    "/api/v1/prospects",
    {
      method: "POST",
      body: JSON.stringify({
        email,
        first_name: firstName || null,
        last_name: lastName || null,
        phone: phone || null,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(successReturnTo, "error", result.message));
  }

  revalidatePath("/admin/quotes");
  const nextPath = setQueryParam(successReturnTo, "prospect_id", result.data.id);
  redirect(withUiMessageCode(nextPath, "ok", "prospect_created", { lang: adminLanguage }));
}

export async function createQuoteDraftAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const adminLanguage = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? "/admin/quotes"));
  const successReturnTo = withUiLanguage(returnTo, adminLanguage);
  const contextType = String(formData.get("context_type") ?? "acquisition").trim().toLowerCase() === "active_client" ? "active_client" : "acquisition";
  const prospectId = parseUuid(String(formData.get("prospect_id") ?? ""));
  const clientId = parseUuid(String(formData.get("client_id") ?? ""));
  const quoteTypeId = parseUuid(String(formData.get("quote_type_id") ?? ""));
  const pricingCatalogId = parseUuid(String(formData.get("pricing_catalog_id") ?? ""));
  const legalEntityId = parseUuid(String(formData.get("legal_entity_id") ?? ""));
  const paymentPlanId = parseUuid(String(formData.get("payment_plan_id") ?? ""));
  const termsTemplateId = parseUuid(String(formData.get("terms_template_id") ?? ""));
  const locationId = parseUuid(String(formData.get("location_id") ?? ""));
  const quoteTemplateUuid = parseUuid(String(formData.get("quote_template_uuid") ?? ""));
  const quoteLanguageRaw = String(formData.get("language") ?? "").trim().toLowerCase();
  const quoteLanguage = quoteLanguageRaw ? quoteLanguageRaw.slice(0, 8) : null;
  const currencyRaw = String(formData.get("currency") ?? "EUR").trim().toUpperCase();
  const currency = currencyRaw.length === 3 ? currencyRaw : "EUR";
  const tvaRateRaw = String(formData.get("tva_rate") ?? "").trim();
  const expiryDaysRaw = String(formData.get("expiry_days") ?? "").trim();
  const expiryDays = expiryDaysRaw ? parsePositiveInt(expiryDaysRaw) : null;
  const schoolYearLabel = String(formData.get("school_year_label") ?? "").trim() || null;
  const estimatedSolfegeLevel = String(formData.get("estimated_solfege_level") ?? "").trim() || null;
  const solfegeSlotJsonRaw = String(formData.get("solfege_slot_json") ?? "").trim();
  const passRecupModeRaw = String(formData.get("pass_recup_mode") ?? "auto").trim().toLowerCase();
  const passRecupMode = passRecupModeRaw === "enabled" || passRecupModeRaw === "disabled" ? passRecupModeRaw : "auto";
  const parsedSolfegeSlot = parseSolfegeSlotJson(solfegeSlotJsonRaw);
  if (parsedSolfegeSlot === undefined) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_solfege_slot_invalid", { lang: adminLanguage }));
  }
  const planningBlocksRaw = String(formData.get("planning_blocks_json") ?? "").trim();
  const planningBlocks = planningBlocksRaw ? parsePlanningBlocksJson(planningBlocksRaw) : [];
  if (planningBlocks === null) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_planning_invalid", { lang: adminLanguage }));
  }
  const effectivePlanningSchoolYearLabel = deriveSchoolYearLabelFromBlocks(planningBlocks, schoolYearLabel);
  const resolvedEstimatedSolfegeLevel = estimatedSolfegeLevel;
  const resolvedSolfegeSlot = parsedSolfegeSlot || null;
  const calendarActivityId = parseUuid(String(formData.get("calendar_activity_id") ?? ""));
  const startDate = parseDateOnly(String(formData.get("calendar_start_date") ?? ""));
  const endDate = parseDateOnly(String(formData.get("calendar_end_date") ?? ""));
  const startTime = String(formData.get("calendar_start_time") ?? "").trim();
  const endTime = String(formData.get("calendar_end_time") ?? "").trim();
  const weekdays = formData
    .getAll("calendar_weekdays")
    .map((entry) => Number.parseInt(String(entry), 10))
    .filter((value) => Number.isFinite(value) && value >= 0 && value <= 6);
  const lines = parseQuoteWizardLines(String(formData.get("lines_json") ?? ""));
  const financialAdjustment = parseQuoteFinancialAdjustment(formData);
  if (financialAdjustment.error) {
    redirect(appendQueryMessage(returnTo, "error", financialAdjustment.error));
  }
  const preRegistrationDeposit = parseQuotePreRegistrationDeposit(formData);
  if (preRegistrationDeposit.error) {
    redirect(appendQueryMessage(returnTo, "error", preRegistrationDeposit.error));
  }

  let tvaRate: string | null = null;
  if (tvaRateRaw) {
    const parsedTva = Number(tvaRateRaw);
    if (!Number.isFinite(parsedTva) || parsedTva < 0 || parsedTva > 100) {
      redirect(withUiMessageCode(successReturnTo, "error", "quote_vat_invalid", { lang: adminLanguage }));
    }
    tvaRate = parsedTva.toFixed(2);
  }

  if (contextType === "acquisition" && !prospectId) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_acquisition_prospect_required", { lang: adminLanguage }));
  }
  if (contextType === "active_client" && !clientId) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_active_client_required", { lang: adminLanguage }));
  }
  if (expiryDaysRaw && expiryDays === null) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_expiry_invalid", { lang: adminLanguage }));
  }

  let calendarSnapshot: Record<string, unknown> = {};
  if (planningBlocks.length > 0) {
    calendarSnapshot = await buildCalendarSnapshotFromBlocks({
      blocks: planningBlocks,
      token,
      returnTo,
      schoolYearLabel: effectivePlanningSchoolYearLabel,
    });
  } else if (startDate && endDate && startTime && endTime && weekdays.length > 0) {
    const preview = await backendRequest<Record<string, unknown>>(
      "/api/v1/quotes/calendar/preview",
      {
        method: "POST",
        body: JSON.stringify({
          start_date: startDate,
          end_date: endDate,
          weekdays,
          recurrence_frequency: "weekly",
          start_time: startTime,
          end_time: endTime,
          activity_id: calendarActivityId,
          location_id: locationId,
        }),
      },
      token,
    );
    if (preview.ok) {
      calendarSnapshot = preview.data;
    }
  }
  if (resolvedEstimatedSolfegeLevel && resolvedSolfegeSlot) {
    calendarSnapshot = {
      ...(calendarSnapshot || {}),
      solfege: {
        estimated_level: resolvedEstimatedSolfegeLevel,
        selected_slot: resolvedSolfegeSlot,
      },
    };
  }
  const nextMeta: Record<string, unknown> = {
    ...(tvaRate ? { tva_rate: tvaRate } : {}),
    financial_adjustment: financialAdjustment.value,
    pre_registration_deposit: preRegistrationDeposit.value,
    pass_recup_mode: passRecupMode,
    ...(resolvedSolfegeSlot ? { selected_solfege_slot: resolvedSolfegeSlot } : {}),
  };
  if (passRecupMode === "enabled") {
    nextMeta.pass_recup_enabled = true;
  } else if (passRecupMode === "disabled") {
    nextMeta.pass_recup_enabled = false;
  }

  const payload = {
    context_type: contextType,
    quote_type: "forfait",
    quote_type_id: quoteTypeId,
    pricing_catalog_id: pricingCatalogId,
    legal_entity_id: legalEntityId,
    prospect_id: contextType === "acquisition" ? prospectId : null,
    client_id: contextType === "active_client" ? clientId : null,
    location_id: locationId,
    payment_plan_id: paymentPlanId,
    quote_template_uuid: quoteTemplateUuid,
    terms_template_id: termsTemplateId,
    school_year_label: effectivePlanningSchoolYearLabel,
    currency,
    language: quoteLanguage,
    vat_rate: tvaRate,
    meta: nextMeta,
    expiry_days: expiryDays,
    estimated_solfege_level: resolvedEstimatedSolfegeLevel,
    calendar_snapshot: calendarSnapshot,
    lines: lines.map((line) => ({
      line_category: line.line_category,
      line_type: line.line_type,
      master_item_type: line.master_item_type,
      activity_id: line.activity_id,
      product_id: line.product_id,
      kit_id: line.kit_id,
      title: line.title,
      quantity: line.quantity,
      vat_rate: line.vat_rate,
      unit_price_ttc: line.unit_price_ttc,
      meta: line.meta,
      pricing_unit: line.line_category === "service" ? "session" : "item",
      sort_order: line.sort_order,
    })),
  };

  const result = await backendRequest<{ quote: { id: string } }>(
    "/api/v1/quotes",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(successReturnTo, "error", result.message));
  }

  revalidatePath("/admin/quotes");
  const detailPath = withUiLanguage(`/admin/quotes/${encodeURIComponent(result.data.quote.id)}?back=${encodeURIComponent(successReturnTo)}`, adminLanguage);
  redirect(withUiMessageCode(detailPath, "ok", "quote_detail_created", { lang: adminLanguage }));
}

export async function sendQuoteAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const recipientEmail = String(formData.get("recipient_email") ?? "").trim();
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? `/admin/quotes?quote_id=${encodeURIComponent(quoteId)}`));
  const successReturnTo = withUiLanguage(returnTo, language);
  if (!quoteId) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_not_found", { lang: language }));
  }

  const result = await backendRequest<{ quote: { id: string } }>(
    `/api/v1/quotes/${encodeURIComponent(quoteId)}/send`,
    {
      method: "POST",
      body: JSON.stringify({
        recipient_email: recipientEmail || null,
        template_ref: optionalField(formData, "template_ref"),
        send_sms: checkboxField(formData, "send_sms"),
        recipient_phone: optionalField(formData, "recipient_phone"),
        sms_template_ref: optionalField(formData, "sms_template_ref"),
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(successReturnTo, "error", result.message));
  }
  revalidatePath("/admin/quotes");
  revalidatePath(`/admin/quotes/${quoteId}`);
  redirect(withUiMessageCode(successReturnTo, "ok", "quote_sent", { lang: language }));
}

export async function resendQuoteAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const recipientEmail = String(formData.get("recipient_email") ?? "").trim();
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? `/admin/quotes?quote_id=${encodeURIComponent(quoteId)}`));
  const successReturnTo = withUiLanguage(returnTo, language);
  if (!quoteId) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_not_found", { lang: language }));
  }

  const result = await backendRequest<{ quote: { id: string } }>(
    `/api/v1/quotes/${encodeURIComponent(quoteId)}/resend`,
    {
      method: "POST",
      body: JSON.stringify({
        recipient_email: recipientEmail || null,
        template_ref: optionalField(formData, "template_ref"),
        send_sms: checkboxField(formData, "send_sms"),
        recipient_phone: optionalField(formData, "recipient_phone"),
        sms_template_ref: optionalField(formData, "sms_template_ref"),
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(successReturnTo, "error", result.message));
  }
  revalidatePath("/admin/quotes");
  revalidatePath("/admin/communications");
  revalidatePath(`/admin/quotes/${quoteId}`);
  redirect(withUiMessageCode(successReturnTo, "ok", "quote_resent", { lang: language }));
}

export async function sendQuoteManualEmailAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const recipientEmail = String(formData.get("recipient_email") ?? "").trim();
  const subject = String(formData.get("subject") ?? "").trim();
  const body = String(formData.get("body") ?? "").trim();
  const bodyFormat = String(formData.get("body_format") ?? "TEXT").trim().toUpperCase() === "HTML" ? "HTML" : "TEXT";
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? `/admin/quotes/${encodeURIComponent(quoteId)}?section=interactions`));
  const successReturnTo = withUiLanguage(returnTo, language);
  if (!quoteId) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_not_found", { lang: language }));
  }
  if (!recipientEmail || !recipientEmail.includes("@") || !subject || !body) {
    redirect(appendQueryMessage(successReturnTo, "error", "Email, sujet et message sont obligatoires."));
  }

  const result = await backendRequest<{ quote: { id: string } }>(
    `/api/v1/quotes/${encodeURIComponent(quoteId)}/manual-email`,
    {
      method: "POST",
      body: JSON.stringify({
        recipient_email: recipientEmail,
        subject,
        body,
        body_format: bodyFormat,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(successReturnTo, "error", result.message));
  }
  revalidatePath("/admin/quotes");
  revalidatePath("/admin/communications");
  revalidatePath(`/admin/quotes/${quoteId}`);
  redirect(appendQueryMessage(successReturnTo, "ok", "Email envoye et trace dans les interactions."));
}

export async function logQuoteManualReplyAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const senderEmail = String(formData.get("sender_email") ?? "").trim();
  const subject = String(formData.get("subject") ?? "").trim();
  const body = String(formData.get("body") ?? "").trim();
  const bodyFormat = String(formData.get("body_format") ?? "TEXT").trim().toUpperCase() === "HTML" ? "HTML" : "TEXT";
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? `/admin/quotes/${encodeURIComponent(quoteId)}?section=interactions`));
  const successReturnTo = withUiLanguage(returnTo, language);
  if (!quoteId) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_not_found", { lang: language }));
  }
  if (!senderEmail || !senderEmail.includes("@") || !body) {
    redirect(appendQueryMessage(successReturnTo, "error", "Email expediteur et reponse sont obligatoires."));
  }

  const result = await backendRequest<{ quote: { id: string } }>(
    `/api/v1/quotes/${encodeURIComponent(quoteId)}/manual-reply`,
    {
      method: "POST",
      body: JSON.stringify({
        sender_email: senderEmail,
        subject: subject || null,
        body,
        body_format: bodyFormat,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(successReturnTo, "error", result.message));
  }
  revalidatePath("/admin/quotes");
  revalidatePath(`/admin/quotes/${quoteId}`);
  redirect(appendQueryMessage(successReturnTo, "ok", "Reponse prospect ajoutee aux interactions."));
}

export async function cancelQuoteAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? `/admin/quotes?quote_id=${encodeURIComponent(quoteId)}`));
  const successReturnTo = withUiLanguage(returnTo, language);
  if (!quoteId) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_not_found", { lang: language }));
  }

  const result = await backendRequest<{ quote: { id: string } }>(
    `/api/v1/quotes/${encodeURIComponent(quoteId)}/cancel`,
    {
      method: "POST",
      body: JSON.stringify({
        notify_recipient: checkboxField(formData, "notify_recipient"),
        recipient_email: optionalField(formData, "recipient_email"),
        template_ref: optionalField(formData, "template_ref"),
        notify_recipient_sms: checkboxField(formData, "notify_recipient_sms"),
        recipient_phone: optionalField(formData, "recipient_phone"),
        sms_template_ref: optionalField(formData, "sms_template_ref"),
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(successReturnTo, "error", result.message));
  }

  revalidatePath("/admin/quotes");
  revalidatePath("/admin/communications");
  revalidatePath(`/admin/quotes/${quoteId}`);
  redirect(withUiMessageCode(successReturnTo, "ok", "quote_cancelled", { lang: language }));
}

export async function restoreQuotePublicResponseAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? `/admin/quotes?quote_id=${encodeURIComponent(quoteId)}`));
  const successReturnTo = withUiLanguage(returnTo, language);
  if (!quoteId) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_not_found", { lang: language }));
  }

  const result = await backendRequest<{ quote: { id: string } }>(
    `/api/v1/quotes/${encodeURIComponent(quoteId)}/restore-public-response`,
    {
      method: "POST",
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(successReturnTo, "error", result.message));
  }

  revalidatePath("/admin/quotes");
  revalidatePath(`/admin/quotes/${quoteId}`);
  redirect(withUiMessageCode(successReturnTo, "ok", "quote_public_response_restored", { lang: language }));
}

export async function resendQuotePublicConfirmationAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const language = await ensureAdminAndGetLanguage(token);
  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? `/admin/quotes?quote_id=${encodeURIComponent(quoteId)}`));
  if (!quoteId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_detail.quote_not_found")));
  }

  const recipientEmail = String(formData.get("recipient_email") ?? "").trim();
  const result = await backendRequest<{ quote: { id: string } }>(
    `/api/v1/quotes/${encodeURIComponent(quoteId)}/resend-public-confirmation-email`,
    {
      method: "POST",
      body: JSON.stringify({
        recipient_email: recipientEmail || null,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/quotes");
  revalidatePath("/admin/communications");
  revalidatePath(`/admin/quotes/${quoteId}`);
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_detail.public_confirmation_resent")));
}

export async function resendCommunicationAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  await ensureAdmin(token);

  const communicationId = String(formData.get("communication_id") ?? "").trim();
  const normalizedCommunicationId = communicationId.replace(/^communication-log-/, "");
  const recipientEmail = String(formData.get("recipient_email") ?? "").trim();
  const returnTo = safeAdminReturnPath(formData, "/admin/communications");
  if (!normalizedCommunicationId) {
    redirect(appendQueryMessage(returnTo, "error", "Communication introuvable"));
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/admin/reports/communications/${encodeURIComponent(normalizedCommunicationId)}/resend`,
    {
      method: "POST",
      body: JSON.stringify({ recipient_email: recipientEmail || null }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/communications");
  const successReturnTo = setQueryParam(setQueryParam(returnTo, "message_id", result.data.id), "ok", "Communication renvoyee");
  redirect(successReturnTo);
}

export async function regenerateQuoteDocumentAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? "/admin/quotes"));
  const successReturnTo = withUiLanguage(returnTo, language);
  if (!quoteId) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_not_found", { lang: language }));
  }

  const result = await backendRequest<{ quote_id: string; document_status: string }>(
    `/api/v1/quotes/${encodeURIComponent(quoteId)}/document/regenerate`,
    { method: "POST" },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(successReturnTo, "error", result.message));
  }

  revalidatePath("/admin/quotes");
  revalidatePath(`/admin/quotes/${quoteId}`);
  redirect(withUiMessageCode(successReturnTo, "ok", "quote_document_regenerated", { lang: language }));
}

export async function duplicateQuoteAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? "/admin/quotes"));
  const successReturnTo = withUiLanguage(returnTo, language);
  if (!quoteId) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_not_found", { lang: language }));
  }

  const result = await backendRequest<{ quote: { id: string } }>(
    `/api/v1/quotes/${encodeURIComponent(quoteId)}/duplicate`,
    { method: "POST" },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(successReturnTo, "error", result.message));
  }
  revalidatePath("/admin/quotes");
  const detailPath = withUiLanguage(`/admin/quotes/${encodeURIComponent(result.data.quote.id)}?back=${encodeURIComponent(successReturnTo)}`, language);
  redirect(withUiMessageCode(detailPath, "ok", "quote_duplicated", { lang: language }));
}

export async function duplicateQuoteForChildAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? "/admin/quotes"));
  const successReturnTo = withUiLanguage(returnTo, language);
  const firstName = String(formData.get("child_first_name") ?? "").trim();
  const lastName = String(formData.get("child_last_name") ?? "").trim();
  const birthDate = parseDateOnly(String(formData.get("child_birth_date") ?? ""));
  const notes = optionalField(formData, "notes");
  if (!quoteId) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_not_found", { lang: language }));
  }
  if (!firstName || !lastName) {
    redirect(withUiMessageCode(successReturnTo, "error", "invalid_prospect_fields", { lang: language }));
  }

  const result = await backendRequest<{ quote: { id: string } }>(
    `/api/v1/quotes/${encodeURIComponent(quoteId)}/duplicate-for-child`,
    {
      method: "POST",
      body: JSON.stringify({
        first_name: firstName,
        last_name: lastName,
        birth_date: birthDate,
        notes,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(successReturnTo, "error", result.message));
  }
  revalidatePath("/admin/quotes");
  const detailPath = withUiLanguage(`/admin/quotes/${encodeURIComponent(result.data.quote.id)}?back=${encodeURIComponent(successReturnTo)}`, language);
  redirect(withUiMessageCode(detailPath, "ok", "quote_sibling_created", { lang: language }));
}

export async function updateQuoteSettingsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? "/admin/quotes"));
  const successReturnTo = withUiLanguage(returnTo, language);
  if (!quoteId) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_not_found", { lang: language }));
  }

  const quoteTypeId = parseUuid(String(formData.get("quote_type_id") ?? ""));
  const pricingCatalogId = parseUuid(String(formData.get("pricing_catalog_id") ?? ""));
  const legalEntityId = parseUuid(String(formData.get("legal_entity_id") ?? ""));
  const paymentPlanId = parseUuid(String(formData.get("payment_plan_id") ?? ""));
  const quoteTemplateUuid = parseUuid(String(formData.get("quote_template_uuid") ?? ""));
  const termsTemplateId = parseUuid(String(formData.get("terms_template_id") ?? ""));
  const schoolYearLabel = String(formData.get("school_year_label") ?? "").trim();
  const currencyRaw = String(formData.get("currency") ?? "EUR").trim().toUpperCase();
  const currency = currencyRaw.length === 3 ? currencyRaw : "EUR";
  const quoteLanguageRaw = String(formData.get("language") ?? "").trim().toLowerCase();
  const quoteLanguage = quoteLanguageRaw ? quoteLanguageRaw.slice(0, 8) : null;
  const expiryDays = parsePositiveInt(String(formData.get("expiry_days") ?? "")) ?? null;
  const hasEstimatedSolfegeLevel = formData.has("estimated_solfege_level");
  const estimatedSolfegeLevelRaw = String(formData.get("estimated_solfege_level") ?? "").trim();
  const estimatedSolfegeLevel = estimatedSolfegeLevelRaw || null;
  const passRecupModeRaw = String(formData.get("pass_recup_mode") ?? "").trim().toLowerCase();
  const hasPassRecupMode = formData.has("pass_recup_mode");
  const hasTvaRate = formData.has("tva_rate");
  const tvaRateRaw = String(formData.get("tva_rate") ?? "").trim();

  if (expiryDays !== null && (expiryDays < 1 || expiryDays > 120)) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_expiry_invalid", { lang: language }));
  }

  let meta: Record<string, unknown> = {};
  const currentMetaRaw = String(formData.get("current_meta_json") ?? "").trim();
  if (currentMetaRaw) {
    try {
      const parsed = JSON.parse(currentMetaRaw) as unknown;
      if (parsed && typeof parsed === "object") {
        meta = parsed as Record<string, unknown>;
      }
    } catch {
      meta = {};
    }
  }
  if (hasTvaRate) {
    if (tvaRateRaw) {
      const parsedTva = Number(tvaRateRaw);
      if (!Number.isFinite(parsedTva) || parsedTva < 0 || parsedTva > 100) {
        redirect(withUiMessageCode(successReturnTo, "error", "quote_vat_invalid", { lang: language }));
      }
      meta.tva_rate = parsedTva.toFixed(2);
    } else {
      delete meta.tva_rate;
    }
  }
  const financialAdjustment = parseQuoteFinancialAdjustment(formData);
  if (financialAdjustment.error) {
    redirect(appendQueryMessage(returnTo, "error", financialAdjustment.error));
  }
  meta.financial_adjustment = financialAdjustment.value;
  const hasPreRegistrationDeposit =
    formData.has("pre_registration_deposit_enabled") || formData.has("pre_registration_deposit_amount_ttc");
  if (hasPreRegistrationDeposit) {
    const preRegistrationDeposit = parseQuotePreRegistrationDeposit(formData);
    if (preRegistrationDeposit.error) {
      redirect(appendQueryMessage(returnTo, "error", preRegistrationDeposit.error));
    }
    meta.pre_registration_deposit = preRegistrationDeposit.value;
  }
  if (hasPassRecupMode) {
    const normalizedPassRecupMode =
      passRecupModeRaw === "enabled" || passRecupModeRaw === "disabled" ? passRecupModeRaw : "auto";
    meta.pass_recup_mode = normalizedPassRecupMode;
    if (normalizedPassRecupMode === "enabled") {
      meta.pass_recup_enabled = true;
    } else if (normalizedPassRecupMode === "disabled") {
      meta.pass_recup_enabled = false;
    } else {
      delete meta.pass_recup_enabled;
    }
  }

  const payload: Record<string, unknown> = {
    quote_type_id: quoteTypeId,
    pricing_catalog_id: pricingCatalogId,
    legal_entity_id: legalEntityId,
    payment_plan_id: paymentPlanId,
    school_year_label: schoolYearLabel || null,
    currency,
    language: quoteLanguage,
    meta,
  };
  if (quoteTemplateUuid) {
    payload.quote_template_uuid = quoteTemplateUuid;
  }
  if (termsTemplateId) {
    payload.terms_template_id = termsTemplateId;
  }
  if (hasTvaRate) {
    payload.vat_rate = tvaRateRaw ? Number(tvaRateRaw).toFixed(2) : null;
  }
  if (hasEstimatedSolfegeLevel) {
    payload.estimated_solfege_level = estimatedSolfegeLevel;
  }
  if (expiryDays !== null) {
    payload.expiry_days = expiryDays;
  }

  const result = await backendRequest<{ quote: { id: string } }>(
    `/api/v1/quotes/${encodeURIComponent(quoteId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(successReturnTo, "error", result.message));
  }

  revalidatePath("/admin/quotes");
  revalidatePath(`/admin/quotes/${quoteId}`);
  redirect(withUiMessageCode(successReturnTo, "ok", "quote_settings_updated", { lang: language }));
}

export async function updateQuoteLinesAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? "/admin/quotes"));
  const successReturnTo = withUiLanguage(returnTo, language);
  if (!quoteId) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_not_found", { lang: language }));
  }

  const lines = parseQuoteWizardLines(String(formData.get("lines_json") ?? ""));
  const payload = {
    lines: lines.map((line) => ({
      line_category: line.line_category,
      line_type: line.line_type,
      master_item_type: line.master_item_type,
      activity_id: line.activity_id,
      product_id: line.product_id,
      kit_id: line.kit_id,
      title: line.title,
      quantity: line.quantity,
      vat_rate: line.vat_rate,
      unit_price_ttc: line.unit_price_ttc,
      pricing_unit: line.line_category === "service" ? "session" : "item",
      meta: line.meta,
      sort_order: line.sort_order,
    })),
  };

  const result = await backendRequest<{ quote: { id: string } }>(
    `/api/v1/quotes/${encodeURIComponent(quoteId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(successReturnTo, "error", result.message));
  }

  revalidatePath("/admin/quotes");
  revalidatePath(`/admin/quotes/${quoteId}`);
  redirect(withUiMessageCode(successReturnTo, "ok", "quote_lines_updated", { lang: language }));
}

type QuotePlanningBlockInput = {
  activity_id: string | null;
  activity_label: string | null;
  location_id: string | null;
  location_label: string | null;
  series_key?: string | null;
  recommendation_key?: string | null;
  source?: string | null;
  duration_minutes?: number | null;
  sessions_count?: number | null;
  calendar_name?: string | null;
  weekday: number;
  weekday_label: string | null;
  recurrence_frequency: "weekly" | "biweekly" | "monthly";
  start_date: string;
  end_date: string;
  start_time: string;
  end_time: string;
  modality: string | null;
  selection_pending?: boolean;
  pending_solfege_level?: string | null;
  pending_slot_options?: Array<Record<string, unknown>>;
  exclude_holidays_in_recurrence?: boolean;
  exclude_school_vacations_in_recurrence?: boolean;
};

type QuoteSolfegeSlotInput = {
  weekday: number;
  weekday_label: string | null;
  start_time: string;
  end_time: string;
  label: string | null;
  duration_minutes: number;
  location_id: string | null;
  location_label: string | null;
  modality: string | null;
};

function parsePlanningBlocksJson(raw: string): QuotePlanningBlockInput[] | null {
  const value = raw.trim();
  if (!value) {
    return [];
  }
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!Array.isArray(parsed)) {
      return null;
    }
    const out: QuotePlanningBlockInput[] = [];
    for (const row of parsed) {
      if (!row || typeof row !== "object") {
        return null;
      }
      const item = row as Record<string, unknown>;
      const weekday = Number.parseInt(String(item.weekday ?? ""), 10);
      const weekdayLabel = String(item.weekday_label ?? "").trim();
      const startDate = String(item.start_date ?? "").trim();
      const endDate = String(item.end_date ?? "").trim();
      const startTime = String(item.start_time ?? "").trim();
      const endTime = String(item.end_time ?? "").trim();
      const activityIdRaw = String(item.activity_id ?? "").trim();
      const activityLabel = String(item.activity_label ?? "").trim();
      const locationIdRaw = String(item.location_id ?? "").trim();
      const locationLabel = String(item.location_label ?? "").trim();
      const seriesKey = String(item.series_key ?? "").trim();
      const recommendationKey = String(item.recommendation_key ?? "").trim();
      const source = String(item.source ?? "").trim();
      const durationMinutesRaw = Number.parseInt(String(item.duration_minutes ?? ""), 10);
      const sessionsCountRaw = Number.parseInt(String(item.sessions_count ?? ""), 10);
      const calendarName = String(item.calendar_name ?? "").trim();
      const modalityRaw = String(item.modality ?? "").trim().toUpperCase();
      const recurrenceRaw = String(item.recurrence_frequency ?? "").trim().toLowerCase();
      const recurrenceFrequency: QuotePlanningBlockInput["recurrence_frequency"] =
        recurrenceRaw === "biweekly" || recurrenceRaw === "monthly" ? recurrenceRaw : "weekly";
      const selectionPending = Boolean(item.selection_pending) || weekday === -1;
      const pendingSolfegeLevel = String(item.pending_solfege_level ?? "").trim();
      const pendingSlotsRaw = Array.isArray(item.pending_slot_options) ? item.pending_slot_options : [];
      const pendingSlotOptions = pendingSlotsRaw
        .map((slot) => (slot && typeof slot === "object" ? (slot as Record<string, unknown>) : null))
        .filter((slot): slot is Record<string, unknown> => slot !== null)
        .map((slot) => {
          const start = String(slot.start_time ?? slot.start ?? "").trim();
          const end = String(slot.end_time ?? slot.end ?? "").trim();
          const weekdayValue = Number.parseInt(String(slot.weekday ?? ""), 10);
          const weekdayValueLabel = String(slot.weekday_label ?? "").trim();
          const slotLabel = String(slot.label ?? "").trim();
          const durationRaw = Number.parseInt(String(slot.duration_minutes ?? ""), 10);
          const modality = String(slot.modality ?? "").trim().toUpperCase();
          return {
            weekday: Number.isFinite(weekdayValue) && weekdayValue >= 0 && weekdayValue <= 6 ? weekdayValue : null,
            weekday_label: weekdayValueLabel || null,
            start_time: start || null,
            end_time: end || null,
            duration_minutes: Number.isFinite(durationRaw) && durationRaw > 0 ? durationRaw : null,
            location_id: parseUuid(String(slot.location_id ?? "").trim()),
            location_label: String(slot.location_label ?? "").trim() || null,
            modality: modality === "ONLINE" || modality === "ONSITE" ? modality : null,
            label: slotLabel || null,
          };
        });
      const excludeHolidaysInRecurrence =
        typeof item.exclude_holidays_in_recurrence === "boolean"
          ? item.exclude_holidays_in_recurrence
          : true;
      const excludeSchoolVacationsInRecurrence =
        typeof item.exclude_school_vacations_in_recurrence === "boolean"
          ? item.exclude_school_vacations_in_recurrence
          : true;
      if (!selectionPending && (!Number.isFinite(weekday) || weekday < 0 || weekday > 6)) {
        return null;
      }
      if (!activityIdRaw) {
        return null;
      }
      if (!selectionPending && (!startDate || !endDate)) {
        return null;
      }
      if (!selectionPending && (!startTime || !endTime)) {
        return null;
      }
      const parsedActivityId = parseUuid(activityIdRaw);
      if (!parsedActivityId) {
        return null;
      }
      out.push({
        activity_id: parsedActivityId,
        activity_label: activityLabel || null,
        location_id: parseUuid(locationIdRaw),
        location_label: locationLabel || null,
        series_key: seriesKey || null,
        recommendation_key: recommendationKey || null,
        source: source || null,
        duration_minutes: Number.isFinite(durationMinutesRaw) && durationMinutesRaw > 0 ? durationMinutesRaw : null,
        sessions_count: Number.isFinite(sessionsCountRaw) && sessionsCountRaw >= 0 ? sessionsCountRaw : null,
        calendar_name: calendarName || null,
        weekday: selectionPending ? -1 : weekday,
        weekday_label: selectionPending ? (weekdayLabel || "Selection a faire") : (weekdayLabel || null),
        recurrence_frequency: recurrenceFrequency,
        start_date: startDate,
        end_date: endDate,
        start_time: selectionPending ? "" : startTime,
        end_time: selectionPending ? "" : endTime,
        modality: modalityRaw === "ONLINE" || modalityRaw === "ONSITE" ? modalityRaw : null,
        selection_pending: selectionPending,
        pending_solfege_level: selectionPending && pendingSolfegeLevel ? pendingSolfegeLevel : null,
        pending_slot_options: selectionPending ? pendingSlotOptions : [],
        exclude_holidays_in_recurrence: excludeHolidaysInRecurrence,
        exclude_school_vacations_in_recurrence: excludeSchoolVacationsInRecurrence,
      });
    }
    return out;
  } catch {
    return null;
  }
}

function parseSolfegeSlotJson(raw: string): QuoteSolfegeSlotInput | null | undefined {
  const value = raw.trim();
  if (!value) {
    return null;
  }
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!parsed || typeof parsed !== "object") {
      return undefined;
    }
    const row = parsed as Record<string, unknown>;
    const weekday = Number.parseInt(String(row.weekday ?? ""), 10);
    const weekdayLabel = String(row.weekday_label ?? "").trim();
    const startTime = String(row.start_time ?? "").trim();
    const endTime = String(row.end_time ?? "").trim();
    const slotLabel = String(row.label ?? "").trim();
    const durationMinutes = Number.parseInt(String(row.duration_minutes ?? ""), 10);
    if (!Number.isFinite(weekday) || weekday < 0 || weekday > 6) {
      return undefined;
    }
    if (!startTime || !endTime || !Number.isFinite(durationMinutes) || durationMinutes <= 0) {
      return undefined;
    }
    const modalityRaw = String(row.modality ?? "").trim().toUpperCase();
    return {
      weekday,
      weekday_label: weekdayLabel || null,
      start_time: startTime,
      end_time: endTime,
      label: slotLabel || null,
      duration_minutes: durationMinutes,
      location_id: parseUuid(String(row.location_id ?? "").trim()),
      location_label: String(row.location_label ?? "").trim() || null,
      modality: modalityRaw === "ONLINE" || modalityRaw === "ONSITE" ? modalityRaw : null,
    };
  } catch {
    return undefined;
  }
}

function deriveSchoolYearLabelFromDate(dateRaw: string): string | null {
  const trimmed = dateRaw.trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return null;
  }
  const year = Number.parseInt(trimmed.slice(0, 4), 10);
  const month = Number.parseInt(trimmed.slice(5, 7), 10);
  if (!Number.isFinite(year) || !Number.isFinite(month) || month < 1 || month > 12) {
    return null;
  }
  const startYear = month >= 9 ? year : year - 1;
  const endYear = startYear + 1;
  return `${startYear}-${endYear}`;
}

function deriveSchoolYearLabelFromBlocks(
  blocks: QuotePlanningBlockInput[],
  fallback: string | null,
): string | null {
  const labels = Array.from(
    new Set(
      blocks
        .map((block) => deriveSchoolYearLabelFromDate(block.start_date))
        .filter((label): label is string => Boolean(label)),
    ),
  );
  if (labels.length === 1) {
    return labels[0];
  }
  return fallback;
}

async function buildCalendarSnapshotFromBlocks({
  blocks,
  token,
  returnTo,
  schoolYearLabel,
}: {
  blocks: QuotePlanningBlockInput[];
  token: string;
  returnTo: string;
  schoolYearLabel: string | null;
}): Promise<Record<string, unknown>> {
  const sessions: Array<Record<string, unknown>> = [];
  const calendarByLocation = new Map<string, {
    calendar: Record<string, unknown> | null;
    holiday_dates: string[];
    closure_dates: string[];
  }>();

  async function resolveLocationCalendar(
    locationId: string | null,
    requestedSchoolYearLabel: string | null,
  ): Promise<{
    calendar: Record<string, unknown> | null;
    holiday_dates: string[];
    closure_dates: string[];
  }> {
    if (!locationId) {
      return { calendar: null, holiday_dates: [], closure_dates: [] };
    }
    const cacheKey = `${locationId}|${requestedSchoolYearLabel || "*"}`;
    const cached = calendarByLocation.get(cacheKey);
    if (cached) {
      return cached;
    }
    const query = requestedSchoolYearLabel ? `?school_year_label=${encodeURIComponent(requestedSchoolYearLabel)}` : "";
    const result = await backendRequest<{
      calendar: Record<string, unknown> | null;
      holiday_dates: string[];
      closure_dates: string[];
    }>(
      `/api/v1/quote-school-calendars/active/by-location/${encodeURIComponent(locationId)}${query}`,
      {},
      token,
    );
    if (!result.ok) {
      redirect(appendQueryMessage(returnTo, "error", result.message));
    }
    let value = {
      calendar: result.data.calendar || null,
      holiday_dates: Array.isArray(result.data.holiday_dates) ? result.data.holiday_dates.map((item) => String(item)) : [],
      closure_dates: Array.isArray(result.data.closure_dates) ? result.data.closure_dates.map((item) => String(item)) : [],
    };
    if (!value.calendar && requestedSchoolYearLabel) {
      const fallbackResult = await backendRequest<{
        calendar: Record<string, unknown> | null;
        holiday_dates: string[];
        closure_dates: string[];
      }>(
        `/api/v1/quote-school-calendars/active/by-location/${encodeURIComponent(locationId)}`,
        {},
        token,
      );
      if (!fallbackResult.ok) {
        redirect(appendQueryMessage(returnTo, "error", fallbackResult.message));
      }
      value = {
        calendar: fallbackResult.data.calendar || null,
        holiday_dates: Array.isArray(fallbackResult.data.holiday_dates)
          ? fallbackResult.data.holiday_dates.map((item) => String(item))
          : [],
        closure_dates: Array.isArray(fallbackResult.data.closure_dates)
          ? fallbackResult.data.closure_dates.map((item) => String(item))
          : [],
      };
    }
    calendarByLocation.set(cacheKey, value);
    return value;
  }

  const normalizedBlocks = blocks.map((block) => ({
    ...block,
    location_id: block.location_id || null,
    location_label: block.location_label || null,
  }));

  for (const block of normalizedBlocks) {
    const inferredSchoolYearLabel = deriveSchoolYearLabelFromDate(block.start_date) || schoolYearLabel || null;
    const resolvedCalendar = await resolveLocationCalendar(block.location_id, inferredSchoolYearLabel);
    const holidayDates = block.exclude_holidays_in_recurrence === false ? [] : resolvedCalendar.holiday_dates;
    const closureDates = block.exclude_school_vacations_in_recurrence === false ? [] : resolvedCalendar.closure_dates;
    if (block.selection_pending) {
      Object.assign(block, {
        calendar_id: String(resolvedCalendar.calendar?.id ?? ""),
        calendar_name: String(resolvedCalendar.calendar?.name ?? ""),
        calendar_school_year: String(resolvedCalendar.calendar?.school_year_label ?? ""),
        holiday_dates: holidayDates,
        closure_dates: closureDates,
        weekday: -1,
        weekday_label: block.weekday_label || "Selection a faire",
        start_time: "",
        end_time: "",
      });
      continue;
    }

    const preview = await backendRequest<Record<string, unknown>>(
      "/api/v1/quotes/calendar/preview",
      {
        method: "POST",
        body: JSON.stringify({
          start_date: block.start_date,
          end_date: block.end_date,
          weekdays: [block.weekday],
          recurrence_frequency: block.recurrence_frequency || "weekly",
          start_time: block.start_time,
          end_time: block.end_time,
          activity_id: block.activity_id,
          location_id: block.location_id,
          modality: block.modality,
          holiday_dates: holidayDates,
          closure_dates: closureDates,
        }),
      },
      token,
    );
    if (!preview.ok) {
      redirect(appendQueryMessage(returnTo, "error", preview.message));
    }
    const rows = Array.isArray(preview.data.sessions) ? (preview.data.sessions as Array<Record<string, unknown>>) : [];

    const liveMatch = await loadLivePlanningMatchForBlock({
      block: block as LivePlanningBlockInput,
      token,
    });
    if (liveMatch && (rows.length === 0 || liveMatch.sessions.length >= rows.length)) {
      sessions.push(...liveMatch.sessions);
      Object.assign(block, liveMatch.block, {
        calendar_id: String(resolvedCalendar.calendar?.id ?? ""),
        calendar_name: String(resolvedCalendar.calendar?.name ?? ""),
        calendar_school_year: String(resolvedCalendar.calendar?.school_year_label ?? ""),
        holiday_dates: holidayDates,
        closure_dates: closureDates,
      });
      continue;
    }

    for (const row of rows) {
      sessions.push({
        ...row,
        activity_label: block.activity_label,
        location_label: block.location_label,
        weekday: block.weekday,
        weekday_label: block.weekday_label,
        calendar_id: String(resolvedCalendar.calendar?.id ?? ""),
        calendar_name: String(resolvedCalendar.calendar?.name ?? ""),
      });
    }
    Object.assign(block, {
      calendar_id: String(resolvedCalendar.calendar?.id ?? ""),
      calendar_name: String(resolvedCalendar.calendar?.name ?? ""),
      calendar_school_year: String(resolvedCalendar.calendar?.school_year_label ?? ""),
      holiday_dates: holidayDates,
      closure_dates: closureDates,
    });
  }

  sessions.sort((a, b) => {
    const dateA = String(a.date ?? "");
    const dateB = String(b.date ?? "");
    if (dateA < dateB) return -1;
    if (dateA > dateB) return 1;
    const timeA = String(a.start_time ?? "");
    const timeB = String(b.start_time ?? "");
    if (timeA < timeB) return -1;
    if (timeA > timeB) return 1;
    return 0;
  });

  return {
    blocks: normalizedBlocks,
    sessions,
    sessions_count: sessions.length,
    school_year_label: schoolYearLabel,
    generated_at: new Date().toISOString(),
  };
}

export async function updateQuotePlanningAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? "/admin/quotes"));
  const successReturnTo = withUiLanguage(returnTo, language);
  if (!quoteId) {
    redirect(withUiMessageCode(successReturnTo, "error", "quote_not_found", { lang: language }));
  }

  const blocks = parsePlanningBlocksJson(String(formData.get("planning_blocks_json") ?? ""));
  if (blocks === null) {
    redirect(withUiMessageCode(successReturnTo, "error", "planning_invalid", { lang: language }));
  }
  const removedActivityIds = (() => {
    const raw = String(formData.get("removed_activity_ids_json") ?? "").trim();
    if (!raw) {
      return [];
    }
    try {
      const parsed = JSON.parse(raw) as unknown;
      if (!Array.isArray(parsed)) {
        return [];
      }
      return parsed
        .map((value) => parseUuid(String(value ?? "")))
        .filter((value): value is string => Boolean(value));
    } catch {
      return [];
    }
  })();

  let currentMeta: Record<string, unknown> = {};
  const currentMetaRaw = String(formData.get("current_meta_json") ?? "").trim();
  if (currentMetaRaw) {
    try {
      const parsed = JSON.parse(currentMetaRaw) as unknown;
      if (parsed && typeof parsed === "object") {
        currentMeta = parsed as Record<string, unknown>;
      }
    } catch {
      currentMeta = {};
    }
  }

  // Solfege and masterclass are now configured as standalone activities.
  delete currentMeta.activity_solfege;
  delete currentMeta.masterclass_blocks;
  delete currentMeta.selected_solfege_slot;

  const schoolYearLabel = String(formData.get("school_year_label") ?? "").trim() || null;
  const effectivePlanningSchoolYearLabel = deriveSchoolYearLabelFromBlocks(blocks, schoolYearLabel);
  let snapshot = await buildCalendarSnapshotFromBlocks({
    blocks,
    token,
    returnTo,
    schoolYearLabel: effectivePlanningSchoolYearLabel,
  });
  if (snapshot && typeof snapshot === "object" && !Array.isArray(snapshot)) {
    const next = { ...(snapshot as Record<string, unknown>) };
    delete next.solfege;
    delete next.masterclass_blocks;
    snapshot = next;
  }

  const result = await backendRequest<{ quote: { id: string } }>(
    `/api/v1/quotes/${encodeURIComponent(quoteId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        calendar_snapshot: snapshot,
        school_year_label: effectivePlanningSchoolYearLabel,
        meta: currentMeta,
        remove_orphan_activity_line_ids: removedActivityIds,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(successReturnTo, "error", result.message));
  }

  revalidatePath("/admin/quotes");
  revalidatePath(`/admin/quotes/${quoteId}`);
  redirect(withUiMessageCode(successReturnTo, "ok", "quote_planning_updated", { lang: language }));
}

type ProspectPayload = {
  first_name: string | null;
  last_name: string | null;
  email: string;
  phone: string | null;
  parent_prospect_id: string | null;
  source: string | null;
  notes: string | null;
  meta: Record<string, unknown>;
};

function buildProspectPayloadFromForm(formData: FormData): ProspectPayload | null {
  const prospectType = String(formData.get("prospect_type") ?? "adult").trim().toLowerCase() === "child" ? "child" : "adult";
  const parentMode = String(formData.get("parent_referent_mode") ?? "new_parent").trim().toLowerCase() === "existing_parent"
    ? "existing_parent"
    : "new_parent";
  const source = optionalField(formData, "source");
  const notes = optionalField(formData, "notes");

  if (prospectType === "adult") {
    const firstName = String(formData.get("adult_first_name") ?? "").trim();
    const lastName = String(formData.get("adult_last_name") ?? "").trim();
    const email = String(formData.get("adult_email") ?? "").trim().toLowerCase();
    const phone = optionalField(formData, "adult_phone");
    const address = optionalField(formData, "adult_address");
    if (!firstName || !lastName || !email || !email.includes("@")) {
      return null;
    }
    return {
      first_name: firstName,
      last_name: lastName,
      email,
      phone,
      parent_prospect_id: null,
      source,
      notes,
      meta: {
        prospect_type: "adult",
        adult_address: address,
      },
    };
  }

  const childFirstName = String(formData.get("child_first_name") ?? "").trim();
  const childLastName = String(formData.get("child_last_name") ?? "").trim();
  const childBirthDate = optionalField(formData, "child_birth_date");
  if (!childFirstName || !childLastName) {
    return null;
  }

  if (parentMode === "existing_parent") {
    const parentProspectId = parseUuid(String(formData.get("parent_existing_prospect_id") ?? ""));
    const parentEmail = String(formData.get("parent_existing_email") ?? "").trim().toLowerCase();
    const parentFirstName = optionalField(formData, "parent_existing_first_name");
    const parentLastName = optionalField(formData, "parent_existing_last_name");
    const parentPhone = optionalField(formData, "parent_existing_phone");
    const parentAddress = optionalField(formData, "parent_existing_address");
    if (!parentProspectId || !parentEmail || !parentEmail.includes("@")) {
      return null;
    }
    return {
      first_name: childFirstName,
      last_name: childLastName,
      email: parentEmail,
      phone: parentPhone,
      parent_prospect_id: parentProspectId,
      source,
      notes,
      meta: {
        prospect_type: "child",
        parent_referent_mode: "existing_parent",
        parent_existing_prospect_id: parentProspectId,
        child: {
          first_name: childFirstName,
          last_name: childLastName,
          birth_date: childBirthDate,
        },
        parent_referent: {
          title: null,
          first_name: parentFirstName,
          last_name: parentLastName,
          email: parentEmail,
          phone: parentPhone,
          address: parentAddress,
        },
      },
    };
  }

  const parentTitle = optionalField(formData, "parent_title");
  const parentFirstName = String(formData.get("parent_first_name") ?? "").trim();
  const parentLastName = String(formData.get("parent_last_name") ?? "").trim();
  const parentEmail = String(formData.get("parent_email") ?? "").trim().toLowerCase();
  const parentPhone = optionalField(formData, "parent_phone");
  const parentAddress = optionalField(formData, "parent_address");
  if (!parentFirstName || !parentLastName || !parentEmail || !parentEmail.includes("@")) {
    return null;
  }

  return {
    first_name: childFirstName,
    last_name: childLastName,
    email: parentEmail,
    phone: parentPhone,
    parent_prospect_id: null,
    source,
    notes,
    meta: {
      prospect_type: "child",
      parent_referent_mode: "new_parent",
      child: {
        first_name: childFirstName,
        last_name: childLastName,
        birth_date: childBirthDate,
      },
      parent_referent: {
        title: parentTitle,
        first_name: parentFirstName,
        last_name: parentLastName,
        email: parentEmail,
        phone: parentPhone,
        address: parentAddress,
      },
    },
  };
}

export async function createAdminProspectAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminProspectsPath(String(formData.get("return_to") ?? "/admin/prospects"));
  const successReturnTo = withUiLanguage(returnTo, language);
  const payload = buildProspectPayloadFromForm(formData);
  if (!payload) {
    redirect(withUiMessageCode(successReturnTo, "error", "invalid_prospect_fields", { lang: language }));
  }

  const result = await backendRequest<{ id: string }>(
    "/api/v1/prospects",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(successReturnTo, "error", result.message));
  }

  revalidatePath("/admin/prospects");
  revalidatePath("/admin/quotes/new");
  redirect(withUiMessageCode(successReturnTo, "ok", "prospect_created", { lang: language }));
}

export async function updateAdminProspectAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const prospectId = String(formData.get("prospect_id") ?? "").trim();
  const returnTo = safeAdminProspectsPath(String(formData.get("return_to") ?? "/admin/prospects"));
  const successReturnTo = withUiLanguage(returnTo, language);
  if (!prospectId) {
    redirect(withUiMessageCode(successReturnTo, "error", "prospect_not_found", { lang: language }));
  }

  const payload = buildProspectPayloadFromForm(formData);
  if (!payload) {
    redirect(withUiMessageCode(successReturnTo, "error", "invalid_prospect_fields", { lang: language }));
  }

  const status = String(formData.get("status") ?? "").trim().toLowerCase();
  const normalizedStatus = status === "active" || status === "new" || status === "lost" || status === "converted" || status === "archived"
    ? status
    : null;

  const patchPayload: Record<string, unknown> = {
    first_name: payload.first_name,
    last_name: payload.last_name,
    email: payload.email,
    phone: payload.phone,
    parent_prospect_id: payload.parent_prospect_id,
    source: payload.source,
    notes: payload.notes,
    meta: payload.meta,
  };
  if (normalizedStatus) {
    patchPayload.status = normalizedStatus;
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/prospects/${encodeURIComponent(prospectId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(patchPayload),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(successReturnTo, "error", result.message));
  }

  revalidatePath("/admin/prospects");
  revalidatePath("/admin/quotes/new");
  redirect(withUiMessageCode(successReturnTo, "ok", "prospect_updated", { lang: language }));
}

function safeAdminConfigQuotesPath(path: string, fallback = "/admin/config/quotes"): string {
  const value = path.trim();
  if (value.startsWith("/admin/config/quotes") || value.startsWith("/admin/config/calendars")) {
    return value;
  }
  return fallback;
}

function parseUtcEndOfDate(dateRaw: string): string | null {
  const datePart = dateRaw.trim();
  if (!datePart) {
    return null;
  }
  const parsed = new Date(`${datePart}T23:59:59Z`);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed.toISOString();
}

const WEEKDAY_TOKEN_MAP: Record<string, number> = {
  lundi: 0,
  lun: 0,
  monday: 0,
  mon: 0,
  mardi: 1,
  mar: 1,
  tuesday: 1,
  tue: 1,
  mer: 2,
  mercredi: 2,
  wednesday: 2,
  wed: 2,
  jeudi: 3,
  jeu: 3,
  thursday: 3,
  thu: 3,
  vendredi: 4,
  ven: 4,
  friday: 4,
  fri: 4,
  samedi: 5,
  sam: 5,
  saturday: 5,
  sat: 5,
  dimanche: 6,
  dim: 6,
  sunday: 6,
  sun: 6,
};

function normalizeWeekdayToken(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

function parseWeekdayValues(values: string[]): number[] | null {
  const out: number[] = [];
  for (const raw of values) {
    const token = normalizeWeekdayToken(raw);
    if (!token) {
      continue;
    }
    let parsed: number | null = null;
    if (/^\d+$/.test(token)) {
      const value = Number.parseInt(token, 10);
      if (Number.isFinite(value) && value >= 0 && value <= 6) {
        parsed = value;
      }
    } else if (Object.prototype.hasOwnProperty.call(WEEKDAY_TOKEN_MAP, token)) {
      parsed = WEEKDAY_TOKEN_MAP[token];
    }
    if (parsed === null) {
      return null;
    }
    if (!out.includes(parsed)) {
      out.push(parsed);
    }
  }
  return out.sort((a, b) => a - b);
}

function parseJsonObject(raw: string): Record<string, unknown> | null {
  const value = raw.trim();
  if (!value) {
    return {};
  }
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return null;
    }
    return parsed as Record<string, unknown>;
  } catch {
    return null;
  }
}

function normalizePaymentPlanScheduleType(raw: string): "single" | "split_2" | "split_3" | "split_4" | "monthly" | null {
  const value = raw.trim().toLowerCase();
  if (value === "single" || value === "split_2" || value === "split_3" || value === "split_4" || value === "monthly") {
    return value;
  }
  return null;
}

function defaultInstallmentsForScheduleType(scheduleType: "single" | "split_2" | "split_3" | "split_4" | "monthly"): number {
  if (scheduleType === "split_2") return 2;
  if (scheduleType === "split_3") return 3;
  if (scheduleType === "split_4") return 4;
  if (scheduleType === "monthly") return 10;
  return 1;
}

function defaultDeferredMonthsForScheduleType(scheduleType: "single" | "split_2" | "split_3" | "split_4" | "monthly"): number[] {
  if (scheduleType === "split_2") return [12];
  if (scheduleType === "split_3") return [12, 2];
  if (scheduleType === "split_4") return [12, 2, 4];
  return [];
}

function parseMonthNumber(raw: string): number | null {
  const parsed = parseNonNegativeInt(raw);
  if (parsed === null || parsed < 1 || parsed > 12) {
    return null;
  }
  return parsed;
}

function normalizePaymentPlanPresetLabel(raw: string): string {
  const value = raw.trim();
  if (!value) {
    return "";
  }
  const allowed = new Set([
    "Carte bancaire",
    "Carte bancaire mensuelle",
    "Cheque en 1 fois",
    "Cheque en 2 fois",
    "Cheque en 4 fois",
    "Virement bancaire",
    "Especes",
    "4 fois avec frais",
  ]);
  if (allowed.has(value)) {
    return value;
  }
  return "";
}

function paymentPlanCodeFromName(name: string): string {
  const normalized = name
    .trim()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return (normalized || "PAYMENT_PLAN").slice(0, 60);
}

function quoteTemplateCodeFromName(name: string): string {
  const normalized = name
    .trim()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return (normalized || "QUOTE_TEMPLATE").slice(0, 80);
}

function termsTemplateCodeFromName(name: string): string {
  const normalized = name
    .trim()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return (normalized || "TERMS_TEMPLATE").slice(0, 80);
}

function buildPaymentPlanRules(
  scheduleType: "single" | "split_2" | "split_3" | "split_4" | "monthly",
  feePercent: number | null,
  options: {
    deferredMonths: Array<number | null>;
    collectAllChecksUpfront: boolean;
    checkSubmissionAddress: string | null;
    checkSubmissionInstruction: string | null;
    showSchedulePublic: boolean;
    showSchedulePdf: boolean;
  },
): Record<string, unknown> {
  const installments = defaultInstallmentsForScheduleType(scheduleType);
  const deferredDefaults = defaultDeferredMonthsForScheduleType(scheduleType);
  const deferredDueMonths = options.deferredMonths
    .map((month, index) => month ?? deferredDefaults[index] ?? null)
    .filter((month): month is number => month !== null && Number.isFinite(month) && month >= 1 && month <= 12);
  const normalizedDeferredDueMonths = deferredDueMonths.slice(0, Math.max(0, installments - 1));
  return {
    installment_count: installments,
    cadence:
      scheduleType === "monthly"
        ? "monthly"
        : scheduleType === "single"
          ? "single"
          : "manual_split",
    has_fees: feePercent !== null && feePercent > 0,
    fee_percent: feePercent !== null && feePercent > 0 ? Number(feePercent.toFixed(2)) : 0,
    deferred_due_months: normalizedDeferredDueMonths,
    collect_all_checks_upfront: options.collectAllChecksUpfront,
    check_submission_address: options.checkSubmissionAddress ?? "",
    check_submission_instruction: options.checkSubmissionInstruction ?? "",
    schedule_visibility: {
      admin_preview: true,
      public_page: options.showSchedulePublic,
      client_pdf: options.showSchedulePdf,
    },
  };
}

function addMinutesToTimeLabel(start: string, durationMinutes: number): string | null {
  const match = start.trim().match(/^([01]\d|2[0-3]):([0-5]\d)$/);
  if (!match) {
    return null;
  }
  const hours = Number.parseInt(match[1], 10);
  const minutes = Number.parseInt(match[2], 10);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
    return null;
  }
  const totalMinutes = (hours * 60 + minutes + Math.max(0, durationMinutes)) % (24 * 60);
  const outHours = Math.floor(totalMinutes / 60).toString().padStart(2, "0");
  const outMinutes = (totalMinutes % 60).toString().padStart(2, "0");
  return `${outHours}:${outMinutes}`;
}

function parseStructuredSolfegeSlots(
  formData: FormData,
  durationMinutes: number,
): Array<{ weekday: number; start_time: string; end_time: string }> | null {
  const weekdays = formData.getAll("slot_weekday").map((entry) => String(entry).trim());
  const starts = formData.getAll("slot_start_time").map((entry) => String(entry).trim());
  const out: Array<{ weekday: number; start_time: string; end_time: string }> = [];
  const rows = Math.max(weekdays.length, starts.length);
  for (let index = 0; index < rows; index += 1) {
    const weekdayRaw = weekdays[index] ?? "";
    const startRaw = starts[index] ?? "";
    if (!weekdayRaw && !startRaw) {
      continue;
    }
    const parsedWeekdays = parseWeekdayValues([weekdayRaw]);
    if (!parsedWeekdays || parsedWeekdays.length !== 1) {
      return null;
    }
    const start = startRaw.match(/^([01]\d|2[0-3]):([0-5]\d)$/) ? startRaw : "";
    if (!start) {
      return null;
    }
    const end = addMinutesToTimeLabel(start, durationMinutes);
    if (!end) {
      return null;
    }
    out.push({
      weekday: parsedWeekdays[0],
      start_time: start,
      end_time: end,
    });
  }
  return out;
}

type QuoteCalendarPeriodPayload = {
  start_date: string;
  end_date: string;
  label: string | null;
};

function parseCalendarDateList(values: FormDataEntryValue[], multilineRaw?: string): string[] | null {
  const out = new Set<string>();
  const pushDate = (rawInput: string): boolean => {
    const raw = rawInput.trim();
    if (!raw) {
      return true;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
      return false;
    }
    out.add(raw);
    return true;
  };
  for (const value of values) {
    if (!pushDate(String(value))) {
      return null;
    }
  }
  if (multilineRaw) {
    const lines = multilineRaw
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    for (const line of lines) {
      if (!pushDate(line)) {
        return null;
      }
    }
  }
  return Array.from(out).sort();
}

function parseCalendarVacationPeriods(formData: FormData): QuoteCalendarPeriodPayload[] | null {
  const rawTextarea = String(formData.get("vacation_periods_text") ?? "").trim();
  if (rawTextarea) {
    const out: QuoteCalendarPeriodPayload[] = [];
    const lines = rawTextarea
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    for (const line of lines) {
      const parts = line.split("|").map((part) => part.trim());
      let start = "";
      let end = "";
      let label = "";
      if (parts.length >= 2) {
        start = parts[0] ?? "";
        end = parts[1] ?? "";
        label = parts.slice(2).join(" | ").trim();
      } else {
        const arrowMatch = line.match(/^(\d{4}-\d{2}-\d{2})\s*(?:->|→|au)\s*(\d{4}-\d{2}-\d{2})(?:\s*[|;]\s*(.+))?$/i);
        if (!arrowMatch) {
          return null;
        }
        start = arrowMatch[1];
        end = arrowMatch[2];
        label = (arrowMatch[3] || "").trim();
      }
      if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) {
        return null;
      }
      if (end < start) {
        return null;
      }
      out.push({
        start_date: start,
        end_date: end,
        label: label || null,
      });
    }
    return out;
  }

  const starts = formData.getAll("vacation_start").map((entry) => String(entry).trim());
  const ends = formData.getAll("vacation_end").map((entry) => String(entry).trim());
  const labels = formData.getAll("vacation_label").map((entry) => String(entry).trim());
  const size = Math.max(starts.length, ends.length, labels.length);
  const out: QuoteCalendarPeriodPayload[] = [];
  for (let index = 0; index < size; index += 1) {
    const start = starts[index] ?? "";
    const end = ends[index] ?? "";
    const label = labels[index] ?? "";
    if (!start && !end && !label) {
      continue;
    }
    if (!start || !end) {
      return null;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) {
      return null;
    }
    if (end < start) {
      return null;
    }
    out.push({
      start_date: start,
      end_date: end,
      label: label || null,
    });
  }
  return out;
}

export async function createAdminQuoteTypeConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=types"));
  const code = optionalField(formData, "code");
  const name = String(formData.get("name") ?? "").trim();
  const description = optionalField(formData, "description");
  const defaultExpiryDays = parsePositiveInt(String(formData.get("default_expiry_days") ?? "")) ?? null;
  const formulaId = parseUuid(String(formData.get("formula_id") ?? ""));
  const schoolYearLabel = optionalField(formData, "school_year_label");
  const isActive = parseCheckboxFlag(formData, "is_active", true);

  if (!name || defaultExpiryDays === null) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_quote_type_fields")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    "/api/v1/quote-types",
    {
      method: "POST",
      body: JSON.stringify({
        code,
        name,
        description,
        default_expiry_days: defaultExpiryDays,
        formula_id: formulaId,
        school_year_label: schoolYearLabel,
        is_active: isActive,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_config_action.quote_type_created")));
}

export async function updateAdminQuoteTypeConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=types"));
  const quoteTypeId = parseUuid(String(formData.get("quote_type_id") ?? ""));
  const code = optionalField(formData, "code");
  const name = String(formData.get("name") ?? "").trim();
  const description = optionalField(formData, "description");
  const defaultExpiryDays = parsePositiveInt(String(formData.get("default_expiry_days") ?? "")) ?? null;
  const formulaId = parseUuid(String(formData.get("formula_id") ?? ""));
  const schoolYearLabel = optionalField(formData, "school_year_label");
  const isActive = parseCheckboxFlag(formData, "is_active", true);
  if (!quoteTypeId || !name || defaultExpiryDays === null) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_quote_type")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/quote-types/${encodeURIComponent(quoteTypeId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        code,
        name,
        description,
        default_expiry_days: defaultExpiryDays,
        formula_id: formulaId,
        school_year_label: schoolYearLabel,
        is_active: isActive,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_config_action.quote_type_updated")));
}

export async function deleteAdminQuoteTypeConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=types"));
  const quoteTypeId = parseUuid(String(formData.get("quote_type_id") ?? ""));
  if (!quoteTypeId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_quote_type")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/quote-types/${encodeURIComponent(quoteTypeId)}`,
    { method: "DELETE" },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_config_action.quote_type_deleted")));
}

export async function createAdminPricingCatalogConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=catalogs"));
  const name = String(formData.get("name") ?? "").trim();
  const schoolYearLabel = optionalField(formData, "school_year_label");
  const effectiveFromRaw = parseDateOnly(String(formData.get("effective_from") ?? ""));
  const effectiveToRaw = parseDateOnly(String(formData.get("effective_to") ?? ""));
  const isDefault = parseCheckboxFlag(formData, "is_default", false);
  const isActive = parseCheckboxFlag(formData, "is_active", true);

  if (!name || !effectiveFromRaw) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.catalog_name_start_required")));
  }
  const effectiveFrom = parseUtcStartOfDate(effectiveFromRaw);
  const effectiveTo = effectiveToRaw ? parseUtcEndOfDate(effectiveToRaw) : null;
  if (!effectiveFrom || (effectiveToRaw && !effectiveTo)) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_catalog_dates")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    "/api/v1/pricing-catalogs",
    {
      method: "POST",
      body: JSON.stringify({
        name,
        school_year_label: schoolYearLabel,
        effective_from: effectiveFrom,
        effective_to: effectiveTo,
        is_default: isDefault,
        is_active: isActive,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_config_action.catalog_created")));
}

export async function updateAdminPricingCatalogConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=catalogs"));
  const catalogId = parseUuid(String(formData.get("catalog_id") ?? ""));
  const name = String(formData.get("name") ?? "").trim();
  const schoolYearLabel = optionalField(formData, "school_year_label");
  const effectiveFromRaw = parseDateOnly(String(formData.get("effective_from") ?? ""));
  const effectiveToRaw = parseDateOnly(String(formData.get("effective_to") ?? ""));
  const isDefault = parseCheckboxFlag(formData, "is_default", false);
  const isActive = parseCheckboxFlag(formData, "is_active", true);

  if (!catalogId || !name || !effectiveFromRaw) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_catalog")));
  }
  const effectiveFrom = parseUtcStartOfDate(effectiveFromRaw);
  const effectiveTo = effectiveToRaw ? parseUtcEndOfDate(effectiveToRaw) : null;
  if (!effectiveFrom || (effectiveToRaw && !effectiveTo)) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_catalog_dates")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/pricing-catalogs/${encodeURIComponent(catalogId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        name,
        school_year_label: schoolYearLabel,
        effective_from: effectiveFrom,
        effective_to: effectiveTo,
        is_default: isDefault,
        is_active: isActive,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_config_action.catalog_updated")));
}

export async function archiveAdminPricingCatalogConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=catalogs"));
  const catalogId = parseUuid(String(formData.get("catalog_id") ?? ""));
  const name = String(formData.get("name") ?? "").trim();
  const schoolYearLabel = optionalField(formData, "school_year_label");
  const effectiveFromRaw = parseDateOnly(String(formData.get("effective_from") ?? ""));
  const effectiveToRaw = parseDateOnly(String(formData.get("effective_to") ?? ""));
  const shouldArchive = parseCheckboxFlag(formData, "archive", true);
  const wasDefault = parseCheckboxFlag(formData, "is_default", false);

  if (!catalogId || !name || !effectiveFromRaw) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_catalog")));
  }
  const effectiveFrom = parseUtcStartOfDate(effectiveFromRaw);
  const effectiveTo = effectiveToRaw ? parseUtcEndOfDate(effectiveToRaw) : null;
  if (!effectiveFrom || (effectiveToRaw && !effectiveTo)) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_catalog_dates")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/pricing-catalogs/${encodeURIComponent(catalogId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        name,
        school_year_label: schoolYearLabel,
        effective_from: effectiveFrom,
        effective_to: effectiveTo,
        is_default: shouldArchive ? false : wasDefault,
        is_active: !shouldArchive,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(
    returnTo,
    "ok",
    uiText(language, shouldArchive ? "admin.quote_config_action.catalog_archived" : "admin.quote_config_action.catalog_unarchived"),
  ));
}

export async function deleteAdminPricingCatalogConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=catalogs"));
  const catalogId = parseUuid(String(formData.get("catalog_id") ?? ""));
  if (!catalogId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_catalog")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/pricing-catalogs/${encodeURIComponent(catalogId)}`,
    { method: "DELETE" },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_config_action.catalog_deleted")));
}

export async function updateAdminTypeformQuoteDefaultsConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=catalogs"));
  const configId = parseUuid(String(formData.get("config_id") ?? ""));
  const enabled = parseCheckboxFlag(formData, "default_pre_registration_deposit_enabled", true);
  const amountRaw = String(formData.get("default_pre_registration_deposit_amount_ttc") ?? "").trim().replace(",", ".");
  const amount = Number(amountRaw || "0");
  if (!configId || !Number.isFinite(amount) || amount < 0) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_typeform_defaults")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/typeform/form-configs/${encodeURIComponent(configId)}/quote-defaults`,
    {
      method: "PATCH",
      body: JSON.stringify({
        default_pre_registration_deposit_enabled: enabled,
        default_pre_registration_deposit_amount_ttc: amount.toFixed(2),
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/intakes");
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_config_action.typeform_defaults_updated")));
}

export async function upsertAdminPricingActivityPriceConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=catalogs"));
  const catalogId = parseUuid(String(formData.get("catalog_id") ?? ""));
  const activityId = parseUuid(String(formData.get("activity_id") ?? ""));
  const locationId = parseUuid(String(formData.get("location_id") ?? ""));
  const pricingUnitRaw = String(formData.get("pricing_unit") ?? "").trim();
  const pricingUnit = pricingUnitRaw === "hourly" || pricingUnitRaw === "fixed" ? pricingUnitRaw : "per_session";
  const unitPriceTtc = String(formData.get("unit_price_ttc") ?? "").trim().replace(",", ".");

  if (!catalogId || !activityId || !unitPriceTtc || !Number.isFinite(Number(unitPriceTtc)) || Number(unitPriceTtc) < 0) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_activity_price")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    "/api/v1/pricing-activity-prices",
    {
      method: "POST",
      body: JSON.stringify({
        catalog_id: catalogId,
        activity_id: activityId,
        location_id: locationId,
        student_category: null,
        pricing_unit: pricingUnit,
        unit_price_ttc: unitPriceTtc,
        currency: "EUR",
        is_active: true,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  revalidatePath("/admin/intakes");
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_config_action.activity_price_saved")));
}

export async function createAdminQuoteDiscountRuleConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=discounts"));
  const code = optionalField(formData, "code");
  const label = String(formData.get("label") ?? "").trim();
  const unitPriceTtc = String(formData.get("unit_price_ttc") ?? "").trim().replace(",", ".");
  const vatRate = String(formData.get("vat_rate") ?? "0").trim().replace(",", ".");
  const sortOrder = parsePositiveInt(String(formData.get("sort_order") ?? "")) ?? 0;
  const isActive = parseCheckboxFlag(formData, "is_active", true);

  if (!label || !unitPriceTtc || !Number.isFinite(Number(unitPriceTtc)) || Number(unitPriceTtc) < 0 || !Number.isFinite(Number(vatRate)) || Number(vatRate) < 0 || Number(vatRate) > 100) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_discount_rule")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    "/api/v1/quote-discount-rules",
    {
      method: "POST",
      body: JSON.stringify({
        code,
        label,
        unit_price_ttc: Number(unitPriceTtc).toFixed(2),
        vat_rate: Number(vatRate).toFixed(2),
        currency: "EUR",
        is_active: isActive,
        sort_order: sortOrder,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes");
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_config_action.discount_rule_created")));
}

export async function updateAdminQuoteDiscountRuleConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=discounts"));
  const ruleId = parseUuid(String(formData.get("discount_rule_id") ?? ""));
  const code = optionalField(formData, "code");
  const label = String(formData.get("label") ?? "").trim();
  const unitPriceTtc = String(formData.get("unit_price_ttc") ?? "").trim().replace(",", ".");
  const vatRate = String(formData.get("vat_rate") ?? "0").trim().replace(",", ".");
  const sortOrder = parsePositiveInt(String(formData.get("sort_order") ?? "")) ?? 0;
  const isActive = parseCheckboxFlag(formData, "is_active", true);

  if (!ruleId || !label || !unitPriceTtc || !Number.isFinite(Number(unitPriceTtc)) || Number(unitPriceTtc) < 0 || !Number.isFinite(Number(vatRate)) || Number(vatRate) < 0 || Number(vatRate) > 100) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_discount_rule")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/quote-discount-rules/${encodeURIComponent(ruleId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        code,
        label,
        unit_price_ttc: Number(unitPriceTtc).toFixed(2),
        vat_rate: Number(vatRate).toFixed(2),
        currency: "EUR",
        is_active: isActive,
        sort_order: sortOrder,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes");
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_config_action.discount_rule_updated")));
}

export async function createAdminPaymentPlanConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=payment_plans"));
  const presetLabel = normalizePaymentPlanPresetLabel(String(formData.get("plan_label_preset") ?? ""));
  const customLabel = String(formData.get("name_custom") ?? "").trim();
  const name = customLabel || presetLabel;
  const paymentMethod = String(formData.get("payment_method") ?? "").trim().toUpperCase();
  const scheduleType = normalizePaymentPlanScheduleType(String(formData.get("schedule_type") ?? ""));
  const feePercentRaw = String(formData.get("fee_percent") ?? "").trim().replace(",", ".");
  const feePercent = feePercentRaw ? Number(feePercentRaw) : null;
  const normalizedFeePercent = Number.isFinite(feePercent ?? NaN) ? Number(feePercent) : null;
  const dueMonth2Raw = String(formData.get("due_month_2") ?? "").trim();
  const dueMonth3Raw = String(formData.get("due_month_3") ?? "").trim();
  const dueMonth4Raw = String(formData.get("due_month_4") ?? "").trim();
  const dueMonth2 = dueMonth2Raw ? parseMonthNumber(dueMonth2Raw) : null;
  const dueMonth3 = dueMonth3Raw ? parseMonthNumber(dueMonth3Raw) : null;
  const dueMonth4 = dueMonth4Raw ? parseMonthNumber(dueMonth4Raw) : null;
  const collectAllChecksUpfront = parseCheckboxFlag(formData, "collect_all_checks_upfront", paymentMethod === "CHECK");
  const checkSubmissionAddress = optionalField(formData, "check_submission_address");
  const checkSubmissionInstruction = optionalField(formData, "check_submission_instruction");
  const showSchedulePublic = parseCheckboxFlag(formData, "show_schedule_public", scheduleType !== "single");
  const showSchedulePdf = parseCheckboxFlag(formData, "show_schedule_pdf", scheduleType !== "single");
  const isActive = parseCheckboxFlag(formData, "is_active", true);
  const code = paymentPlanCodeFromName(name);
  const scheduleRules = scheduleType
    ? buildPaymentPlanRules(scheduleType, normalizedFeePercent, {
      deferredMonths: [dueMonth2, dueMonth3, dueMonth4],
      collectAllChecksUpfront,
      checkSubmissionAddress,
      checkSubmissionInstruction,
      showSchedulePublic,
      showSchedulePdf,
    })
    : null;

  if (!name || !paymentMethod || !scheduleType || scheduleRules === null) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_payment_plan")));
  }
  if (feePercentRaw && (normalizedFeePercent === null || normalizedFeePercent < 0 || normalizedFeePercent > 100)) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_fee")));
  }
  if ((dueMonth2Raw && dueMonth2 === null) || (dueMonth3Raw && dueMonth3 === null) || (dueMonth4Raw && dueMonth4 === null)) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_due_months")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    "/api/v1/payment-plans",
    {
      method: "POST",
      body: JSON.stringify({
        code,
        name,
        payment_method: paymentMethod,
        schedule_type: scheduleType,
        schedule_rules: scheduleRules,
        is_active: isActive,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_config_action.payment_plan_created")));
}

export async function updateAdminPaymentPlanConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=payment_plans"));
  const planId = parseUuid(String(formData.get("plan_id") ?? ""));
  const presetLabel = normalizePaymentPlanPresetLabel(String(formData.get("plan_label_preset") ?? ""));
  const customLabel = String(formData.get("name_custom") ?? "").trim();
  const currentLabel = String(formData.get("name_current") ?? "").trim();
  const name = customLabel || presetLabel || currentLabel;
  const paymentMethod = String(formData.get("payment_method") ?? "").trim().toUpperCase();
  const scheduleType = normalizePaymentPlanScheduleType(String(formData.get("schedule_type") ?? ""));
  const feePercentRaw = String(formData.get("fee_percent") ?? "").trim().replace(",", ".");
  const feePercent = feePercentRaw ? Number(feePercentRaw) : null;
  const normalizedFeePercent = Number.isFinite(feePercent ?? NaN) ? Number(feePercent) : null;
  const dueMonth2Raw = String(formData.get("due_month_2") ?? "").trim();
  const dueMonth3Raw = String(formData.get("due_month_3") ?? "").trim();
  const dueMonth4Raw = String(formData.get("due_month_4") ?? "").trim();
  const dueMonth2 = dueMonth2Raw ? parseMonthNumber(dueMonth2Raw) : null;
  const dueMonth3 = dueMonth3Raw ? parseMonthNumber(dueMonth3Raw) : null;
  const dueMonth4 = dueMonth4Raw ? parseMonthNumber(dueMonth4Raw) : null;
  const collectAllChecksUpfront = parseCheckboxFlag(formData, "collect_all_checks_upfront", paymentMethod === "CHECK");
  const checkSubmissionAddress = optionalField(formData, "check_submission_address");
  const checkSubmissionInstruction = optionalField(formData, "check_submission_instruction");
  const showSchedulePublic = parseCheckboxFlag(formData, "show_schedule_public", scheduleType !== "single");
  const showSchedulePdf = parseCheckboxFlag(formData, "show_schedule_pdf", scheduleType !== "single");
  const isActive = parseCheckboxFlag(formData, "is_active", true);
  const code = paymentPlanCodeFromName(name);
  const scheduleRules = scheduleType
    ? buildPaymentPlanRules(scheduleType, normalizedFeePercent, {
      deferredMonths: [dueMonth2, dueMonth3, dueMonth4],
      collectAllChecksUpfront,
      checkSubmissionAddress,
      checkSubmissionInstruction,
      showSchedulePublic,
      showSchedulePdf,
    })
    : null;

  if (!planId || !name || !paymentMethod || !scheduleType || scheduleRules === null) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_payment_plan")));
  }
  if (feePercentRaw && (normalizedFeePercent === null || normalizedFeePercent < 0 || normalizedFeePercent > 100)) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_fee")));
  }
  if ((dueMonth2Raw && dueMonth2 === null) || (dueMonth3Raw && dueMonth3 === null) || (dueMonth4Raw && dueMonth4 === null)) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_due_months")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/payment-plans/${encodeURIComponent(planId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        code,
        name,
        payment_method: paymentMethod,
        schedule_type: scheduleType,
        schedule_rules: scheduleRules,
        is_active: isActive,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_config_action.payment_plan_updated")));
}

export async function deleteAdminPaymentPlanConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=payment_plans"));
  const planId = parseUuid(String(formData.get("plan_id") ?? ""));
  if (!planId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_payment_plan")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/payment-plans/${encodeURIComponent(planId)}`,
    { method: "DELETE" },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_config_action.payment_plan_deleted")));
}

export async function upsertAdminSolfegeLevelRuleConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=solfege"));
  const levelCode = String(formData.get("level_code") ?? "").trim();
  const durationMinutes = parsePositiveInt(String(formData.get("duration_minutes") ?? "")) ?? null;
  const locationId = parseUuid(String(formData.get("location_id") ?? ""));
  const modalityRaw = String(formData.get("modality") ?? "").trim().toUpperCase();
  const isActive = parseCheckboxFlag(formData, "is_active", true);
  if (!levelCode || durationMinutes === null || durationMinutes < 10 || durationMinutes > 180) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_solfege_level_or_duration")));
  }

  const structuredSlots = parseStructuredSolfegeSlots(formData, durationMinutes);
  if (structuredSlots === null) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_solfege_slots")));
  }
  if (structuredSlots.length === 0) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.solfege_slot_required")));
  }
  const weekdays = Array.from(new Set(structuredSlots.map((slot) => slot.weekday))).sort((a, b) => a - b);
  const timeSlots = structuredSlots;

  const modality = modalityRaw === "ONLINE" || modalityRaw === "ONSITE" || modalityRaw === "ANY" ? modalityRaw : null;

  const result = await backendRequest<Record<string, unknown>>(
    "/api/v1/solfege-level-rules",
    {
      method: "POST",
      body: JSON.stringify({
        level_code: levelCode,
        duration_minutes: durationMinutes,
        allowed_weekdays: weekdays,
        allowed_time_slots: timeSlots,
        location_id: locationId,
        modality,
        is_active: isActive,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_config_action.solfege_rule_saved")));
}

export async function deleteAdminSolfegeLevelRuleConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=solfege"));
  const ruleId = parseUuid(String(formData.get("rule_id") ?? ""));
  if (!ruleId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_solfege_rule")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/solfege-level-rules/${encodeURIComponent(ruleId)}`,
    { method: "DELETE" },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_config_action.solfege_rule_deleted")));
}

export async function createAdminQuoteSchoolCalendarConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/calendars"), "/admin/config/calendars");
  const successReturnTo = safeAdminConfigQuotesPath(String(formData.get("success_return_to") ?? returnTo), returnTo);
  const name = String(formData.get("name") ?? "").trim();
  const schoolYearLabel = String(formData.get("school_year_label") ?? "").trim();
  const selectedLocationIds = formData
    .getAll("location_ids")
    .map((entry) => parseUuid(String(entry)))
    .filter((value): value is string => Boolean(value));
  const fallbackLocationId = parseUuid(String(formData.get("location_id") ?? ""));
  const locationIds = selectedLocationIds.length > 0
    ? Array.from(new Set(selectedLocationIds))
    : (fallbackLocationId ? [fallbackLocationId] : []);
  const isActive = parseCheckboxFlag(formData, "is_active", true);
  const applyToManagementPlanning = parseCheckboxFlag(formData, "apply_to_management_planning", false);
  const vacationPeriods = parseCalendarVacationPeriods(formData);
  const holidayDates = parseCalendarDateList(formData.getAll("holiday_date"), String(formData.get("holiday_dates_text") ?? ""));
  const closureDates = parseCalendarDateList(formData.getAll("closure_date"), String(formData.get("closure_dates_text") ?? ""));

  if (!name || !schoolYearLabel || locationIds.length === 0) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_calendar")));
  }
  if (vacationPeriods === null || holidayDates === null || closureDates === null) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_calendar_dates")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    "/api/v1/quote-school-calendars",
    {
      method: "POST",
      body: JSON.stringify({
        name,
        school_year_label: schoolYearLabel,
        location_id: locationIds[0],
        location_ids: locationIds,
        vacation_periods: vacationPeriods,
        holiday_dates: holidayDates,
        closure_dates: closureDates,
        is_active: isActive,
        apply_to_management_planning: applyToManagementPlanning,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config/calendars");
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(
    appendQueryMessage(
      successReturnTo,
      "ok",
      applyToManagementPlanning
        ? uiText(language, "admin.quote_config_action.calendar_saved_applied")
        : uiText(language, "admin.quote_config_action.calendar_saved"),
    ),
  );
}

export async function updateAdminQuoteSchoolCalendarConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/calendars"), "/admin/config/calendars");
  const successReturnTo = safeAdminConfigQuotesPath(String(formData.get("success_return_to") ?? returnTo), returnTo);
  const calendarId = parseUuid(String(formData.get("calendar_id") ?? ""));
  const name = String(formData.get("name") ?? "").trim();
  const schoolYearLabel = String(formData.get("school_year_label") ?? "").trim();
  const selectedLocationIds = formData
    .getAll("location_ids")
    .map((entry) => parseUuid(String(entry)))
    .filter((value): value is string => Boolean(value));
  const fallbackLocationId = parseUuid(String(formData.get("location_id") ?? ""));
  const locationIds = selectedLocationIds.length > 0
    ? Array.from(new Set(selectedLocationIds))
    : (fallbackLocationId ? [fallbackLocationId] : []);
  const isActive = parseCheckboxFlag(formData, "is_active", true);
  const applyToManagementPlanning = parseCheckboxFlag(formData, "apply_to_management_planning", false);
  const vacationPeriods = parseCalendarVacationPeriods(formData);
  const holidayDates = parseCalendarDateList(formData.getAll("holiday_date"), String(formData.get("holiday_dates_text") ?? ""));
  const closureDates = parseCalendarDateList(formData.getAll("closure_date"), String(formData.get("closure_dates_text") ?? ""));

  if (!calendarId || !name || !schoolYearLabel || locationIds.length === 0) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_calendar")));
  }
  if (vacationPeriods === null || holidayDates === null || closureDates === null) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_calendar_dates")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/quote-school-calendars/${encodeURIComponent(calendarId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        name,
        school_year_label: schoolYearLabel,
        location_id: locationIds[0],
        location_ids: locationIds,
        vacation_periods: vacationPeriods,
        holiday_dates: holidayDates,
        closure_dates: closureDates,
        is_active: isActive,
        apply_to_management_planning: applyToManagementPlanning,
      }),
    },
    token,
  );

  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config/calendars");
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(
    appendQueryMessage(
      successReturnTo,
      "ok",
      applyToManagementPlanning
        ? uiText(language, "admin.quote_config_action.calendar_updated_applied")
        : uiText(language, "admin.quote_config_action.calendar_updated"),
    ),
  );
}

function parseCalendarGroupEntries(formData: FormData): Array<{ calendarId: string; locationId: string }> {
  const seen = new Set<string>();
  const out: Array<{ calendarId: string; locationId: string }> = [];
  for (const entry of formData.getAll("existing_calendar_entries")) {
    const raw = String(entry ?? "").trim();
    if (!raw) {
      continue;
    }
    const [calendarIdRaw, locationIdRaw] = raw.split(":", 2);
    const calendarId = parseUuid(calendarIdRaw ?? "");
    const locationId = parseUuid(locationIdRaw ?? "");
    if (!calendarId || !locationId) {
      continue;
    }
    const key = `${calendarId}:${locationId}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    out.push({ calendarId, locationId });
  }
  return out;
}

export async function updateAdminQuoteSchoolCalendarGroupAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/calendars"), "/admin/config/calendars");
  const successReturnTo = safeAdminConfigQuotesPath(String(formData.get("success_return_to") ?? returnTo), returnTo);
  const name = String(formData.get("name") ?? "").trim();
  const schoolYearLabel = String(formData.get("school_year_label") ?? "").trim();
  const selectedLocationIds = formData
    .getAll("location_ids")
    .map((entry) => parseUuid(String(entry)))
    .filter((value): value is string => Boolean(value));
  const locationIds = Array.from(new Set(selectedLocationIds));
  const existingEntries = parseCalendarGroupEntries(formData);
  const isActive = parseCheckboxFlag(formData, "is_active", true);
  const applyToManagementPlanning = parseCheckboxFlag(formData, "apply_to_management_planning", false);
  const vacationPeriods = parseCalendarVacationPeriods(formData);
  const holidayDates = parseCalendarDateList(formData.getAll("holiday_date"), String(formData.get("holiday_dates_text") ?? ""));
  const closureDates = parseCalendarDateList(formData.getAll("closure_date"), String(formData.get("closure_dates_text") ?? ""));

  if (!name || !schoolYearLabel || locationIds.length === 0 || existingEntries.length === 0) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_calendar_group")));
  }
  if (vacationPeriods === null || holidayDates === null || closureDates === null) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_calendar_dates")));
  }

  const nextLocationIds = new Set(locationIds);

  for (const entry of existingEntries) {
    if (!nextLocationIds.has(entry.locationId)) {
      const removeDeploymentResult = await backendRequest<{ message?: string }>(
        `/api/v1/quote-school-calendars/${encodeURIComponent(entry.calendarId)}/deployment`,
        { method: "DELETE" },
        token,
      );
      if (!removeDeploymentResult.ok) {
        redirect(appendQueryMessage(returnTo, "error", removeDeploymentResult.message));
      }
      const deleteResult = await backendRequest<Record<string, unknown>>(
        `/api/v1/quote-school-calendars/${encodeURIComponent(entry.calendarId)}`,
        { method: "DELETE" },
        token,
      );
      if (!deleteResult.ok) {
        redirect(appendQueryMessage(returnTo, "error", deleteResult.message));
      }
      continue;
    }

    const updateResult = await backendRequest<Record<string, unknown>>(
      `/api/v1/quote-school-calendars/${encodeURIComponent(entry.calendarId)}`,
      {
        method: "PATCH",
        body: JSON.stringify({
          name,
          school_year_label: schoolYearLabel,
          location_id: entry.locationId,
          location_ids: [entry.locationId],
          vacation_periods: vacationPeriods,
          holiday_dates: holidayDates,
          closure_dates: closureDates,
          is_active: isActive,
          apply_to_management_planning: applyToManagementPlanning,
        }),
      },
      token,
    );
    if (!updateResult.ok) {
      redirect(appendQueryMessage(returnTo, "error", updateResult.message));
    }
    nextLocationIds.delete(entry.locationId);
  }

  for (const locationId of nextLocationIds) {
    const createResult = await backendRequest<Record<string, unknown>>(
      "/api/v1/quote-school-calendars",
      {
        method: "POST",
        body: JSON.stringify({
          name,
          school_year_label: schoolYearLabel,
          location_id: locationId,
          location_ids: [locationId],
          vacation_periods: vacationPeriods,
          holiday_dates: holidayDates,
          closure_dates: closureDates,
          is_active: isActive,
          apply_to_management_planning: applyToManagementPlanning,
        }),
      },
      token,
    );
    if (!createResult.ok) {
      redirect(appendQueryMessage(returnTo, "error", createResult.message));
    }
  }

  revalidatePath("/admin/config/calendars");
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(
    appendQueryMessage(
      successReturnTo,
      "ok",
      applyToManagementPlanning
        ? uiText(language, "admin.quote_config_action.calendar_group_updated_reapplied")
        : uiText(language, "admin.quote_config_action.calendar_group_updated"),
    ),
  );
}

export async function deleteAdminQuoteSchoolCalendarConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/calendars"), "/admin/config/calendars");
  const successReturnTo = safeAdminConfigQuotesPath(String(formData.get("success_return_to") ?? returnTo), returnTo);
  const calendarId = parseUuid(String(formData.get("calendar_id") ?? ""));
  if (!calendarId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_calendar")));
  }

  const removeDeploymentResult = await backendRequest<{ message?: string }>(
    `/api/v1/quote-school-calendars/${encodeURIComponent(calendarId)}/deployment`,
    { method: "DELETE" },
    token,
  );
  if (!removeDeploymentResult.ok) {
    redirect(appendQueryMessage(returnTo, "error", removeDeploymentResult.message));
  }
  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/quote-school-calendars/${encodeURIComponent(calendarId)}`,
    { method: "DELETE" },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/config/calendars");
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(successReturnTo, "ok", uiText(language, "admin.quote_config_action.calendar_deleted")));
}

export async function previewAdminQuoteSchoolCalendarDeploymentAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/calendars"), "/admin/config/calendars");
  const calendarId = parseUuid(String(formData.get("calendar_id") ?? ""));
  if (!calendarId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_calendar")));
  }

  const result = await backendRequest<{
    summary?: { total_target_days?: number };
    would_create?: number;
    would_keep?: number;
    would_reactivate?: number;
    would_cancel?: number;
  }>(
    `/api/v1/quote-school-calendars/${encodeURIComponent(calendarId)}/deployment/preview`,
    {},
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  const total = Number(result.data.summary?.total_target_days ?? 0);
  const createCount = Number(result.data.would_create ?? 0);
  const keepCount = Number(result.data.would_keep ?? 0);
  const reactivateCount = Number(result.data.would_reactivate ?? 0);
  const cancelCount = Number(result.data.would_cancel ?? 0);
  redirect(
    appendQueryMessage(
      returnTo,
      "ok",
      uiText(language, "admin.quote_config_action.calendar_deployment_preview", {
        total,
        create_count: createCount,
        keep_count: keepCount,
        reactivate_count: reactivateCount,
        cancel_count: cancelCount,
      }),
    ),
  );
}

export async function deployAdminQuoteSchoolCalendarAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/calendars"), "/admin/config/calendars");
  const successReturnTo = safeAdminConfigQuotesPath(String(formData.get("success_return_to") ?? returnTo), returnTo);
  const calendarId = parseUuid(String(formData.get("calendar_id") ?? ""));
  if (!calendarId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_calendar")));
  }
  const result = await backendRequest<{ message?: string }>(
    `/api/v1/quote-school-calendars/${encodeURIComponent(calendarId)}/deployment`,
    { method: "POST" },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config/calendars");
  revalidatePath("/admin/config/quotes");
  redirect(appendQueryMessage(successReturnTo, "ok", uiText(language, "admin.quote_config_action.calendar_deployment_done")));
}

export async function syncAdminQuoteSchoolCalendarDeploymentAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/calendars"), "/admin/config/calendars");
  const successReturnTo = safeAdminConfigQuotesPath(String(formData.get("success_return_to") ?? returnTo), returnTo);
  const calendarId = parseUuid(String(formData.get("calendar_id") ?? ""));
  if (!calendarId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_calendar")));
  }
  const result = await backendRequest<{ message?: string }>(
    `/api/v1/quote-school-calendars/${encodeURIComponent(calendarId)}/deployment/sync`,
    { method: "POST" },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config/calendars");
  revalidatePath("/admin/config/quotes");
  redirect(appendQueryMessage(successReturnTo, "ok", uiText(language, "admin.quote_config_action.calendar_deployment_updated")));
}

export async function removeAdminQuoteSchoolCalendarDeploymentAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/calendars"), "/admin/config/calendars");
  const successReturnTo = safeAdminConfigQuotesPath(String(formData.get("success_return_to") ?? returnTo), returnTo);
  const calendarId = parseUuid(String(formData.get("calendar_id") ?? ""));
  if (!calendarId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_calendar")));
  }
  const result = await backendRequest<{ message?: string }>(
    `/api/v1/quote-school-calendars/${encodeURIComponent(calendarId)}/deployment`,
    { method: "DELETE" },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config/calendars");
  revalidatePath("/admin/config/quotes");
  redirect(appendQueryMessage(successReturnTo, "ok", uiText(language, "admin.quote_config_action.calendar_deployment_removed")));
}

function parseCalendarIdsFromFormData(formData: FormData): string[] {
  return Array.from(
    new Set(
      formData
        .getAll("calendar_ids")
        .map((entry) => parseUuid(String(entry)))
        .filter((value): value is string => Boolean(value)),
    ),
  );
}

type CalendarBulkAction = "DEPLOY" | "SYNC" | "REMOVE" | "DELETE";

function parseCalendarBulkAction(raw: string): CalendarBulkAction | null {
  const value = raw.trim().toUpperCase();
  if (value === "DEPLOY" || value === "SYNC" || value === "REMOVE" || value === "DELETE") {
    return value;
  }
  return null;
}

export async function bulkAdminQuoteSchoolCalendarsAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/calendars"), "/admin/config/calendars");
  const successReturnTo = safeAdminConfigQuotesPath(String(formData.get("success_return_to") ?? returnTo), returnTo);
  const calendarIds = parseCalendarIdsFromFormData(formData);
  const bulkAction = parseCalendarBulkAction(String(formData.get("bulk_action") ?? ""));
  if (calendarIds.length === 0) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.select_calendar_required")));
  }
  if (bulkAction === null) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.invalid_calendar_bulk_action")));
  }

  let processedCount = 0;
  for (const calendarId of calendarIds) {
    if (bulkAction === "DEPLOY") {
      const result = await backendRequest<{ message?: string }>(
        `/api/v1/quote-school-calendars/${encodeURIComponent(calendarId)}/deployment`,
        { method: "POST" },
        token,
      );
      if (!result.ok) {
        redirect(appendQueryMessage(returnTo, "error", result.message));
      }
      processedCount += 1;
      continue;
    }
    if (bulkAction === "SYNC") {
      const result = await backendRequest<{ message?: string }>(
        `/api/v1/quote-school-calendars/${encodeURIComponent(calendarId)}/deployment/sync`,
        { method: "POST" },
        token,
      );
      if (!result.ok) {
        redirect(appendQueryMessage(returnTo, "error", result.message));
      }
      processedCount += 1;
      continue;
    }
    if (bulkAction === "REMOVE") {
      const result = await backendRequest<{ message?: string }>(
        `/api/v1/quote-school-calendars/${encodeURIComponent(calendarId)}/deployment`,
        { method: "DELETE" },
        token,
      );
      if (!result.ok) {
        redirect(appendQueryMessage(returnTo, "error", result.message));
      }
      processedCount += 1;
      continue;
    }
    const removeDeploymentResult = await backendRequest<{ message?: string }>(
      `/api/v1/quote-school-calendars/${encodeURIComponent(calendarId)}/deployment`,
      { method: "DELETE" },
      token,
    );
    if (!removeDeploymentResult.ok) {
      redirect(appendQueryMessage(returnTo, "error", removeDeploymentResult.message));
    }
    const result = await backendRequest<Record<string, unknown>>(
      `/api/v1/quote-school-calendars/${encodeURIComponent(calendarId)}`,
      { method: "DELETE" },
      token,
    );
    if (!result.ok) {
      redirect(appendQueryMessage(returnTo, "error", result.message));
    }
    processedCount += 1;
  }

  revalidatePath("/admin/config/calendars");
  revalidatePath("/admin/config/quotes");
  if (bulkAction === "DEPLOY") {
    redirect(appendQueryMessage(successReturnTo, "ok", uiText(language, "admin.quote_config_action.calendar_bulk_deploy", { count: processedCount })));
  }
  if (bulkAction === "SYNC") {
    redirect(appendQueryMessage(successReturnTo, "ok", uiText(language, "admin.quote_config_action.calendar_bulk_sync", { count: processedCount })));
  }
  if (bulkAction === "REMOVE") {
    redirect(appendQueryMessage(successReturnTo, "ok", uiText(language, "admin.quote_config_action.calendar_bulk_remove", { count: processedCount })));
  }
  redirect(appendQueryMessage(successReturnTo, "ok", uiText(language, "admin.quote_config_action.calendar_bulk_delete", { count: processedCount })));
}

export async function previewAdminQuoteSchoolCalendarGroupDeploymentAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/calendars"), "/admin/config/calendars");
  const calendarIds = parseCalendarIdsFromFormData(formData);
  if (calendarIds.length === 0) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.no_target_local_calendar")));
  }

  let totalTargetDays = 0;
  let totalCreate = 0;
  let totalKeep = 0;
  let totalReactivate = 0;
  let totalCancel = 0;
  for (const calendarId of calendarIds) {
    const result = await backendRequest<{
      summary?: { total_target_days?: number };
      would_create?: number;
      would_keep?: number;
      would_reactivate?: number;
      would_cancel?: number;
    }>(
      `/api/v1/quote-school-calendars/${encodeURIComponent(calendarId)}/deployment/preview`,
      {},
      token,
    );
    if (!result.ok) {
      redirect(appendQueryMessage(returnTo, "error", result.message));
    }
    totalTargetDays += Number(result.data.summary?.total_target_days ?? 0);
    totalCreate += Number(result.data.would_create ?? 0);
    totalKeep += Number(result.data.would_keep ?? 0);
    totalReactivate += Number(result.data.would_reactivate ?? 0);
    totalCancel += Number(result.data.would_cancel ?? 0);
  }

  redirect(
    appendQueryMessage(
      returnTo,
      "ok",
      uiText(language, "admin.quote_config_action.calendar_group_preview", {
        count: calendarIds.length,
        total: totalTargetDays,
        create_count: totalCreate,
        keep_count: totalKeep,
        reactivate_count: totalReactivate,
        cancel_count: totalCancel,
      }),
    ),
  );
}

export async function deployAdminQuoteSchoolCalendarGroupAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/calendars"), "/admin/config/calendars");
  const successReturnTo = safeAdminConfigQuotesPath(String(formData.get("success_return_to") ?? returnTo), returnTo);
  const calendarIds = parseCalendarIdsFromFormData(formData);
  if (calendarIds.length === 0) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.no_target_local_calendar")));
  }
  let deployedCount = 0;
  for (const calendarId of calendarIds) {
    const result = await backendRequest<{ message?: string }>(
      `/api/v1/quote-school-calendars/${encodeURIComponent(calendarId)}/deployment`,
      { method: "POST" },
      token,
    );
    if (!result.ok) {
      redirect(appendQueryMessage(returnTo, "error", result.message));
    }
    deployedCount += 1;
  }
  revalidatePath("/admin/config/calendars");
  revalidatePath("/admin/config/quotes");
  redirect(appendQueryMessage(successReturnTo, "ok", uiText(language, "admin.quote_config_action.calendar_group_deploy", { count: deployedCount })));
}

export async function syncAdminQuoteSchoolCalendarGroupAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/calendars"), "/admin/config/calendars");
  const successReturnTo = safeAdminConfigQuotesPath(String(formData.get("success_return_to") ?? returnTo), returnTo);
  const calendarIds = parseCalendarIdsFromFormData(formData);
  if (calendarIds.length === 0) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.no_target_local_calendar")));
  }
  let syncedCount = 0;
  for (const calendarId of calendarIds) {
    const result = await backendRequest<{ message?: string }>(
      `/api/v1/quote-school-calendars/${encodeURIComponent(calendarId)}/deployment/sync`,
      { method: "POST" },
      token,
    );
    if (!result.ok) {
      redirect(appendQueryMessage(returnTo, "error", result.message));
    }
    syncedCount += 1;
  }
  revalidatePath("/admin/config/calendars");
  revalidatePath("/admin/config/quotes");
  redirect(appendQueryMessage(successReturnTo, "ok", uiText(language, "admin.quote_config_action.calendar_group_sync", { count: syncedCount })));
}

export async function removeAdminQuoteSchoolCalendarGroupDeploymentAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/calendars"), "/admin/config/calendars");
  const successReturnTo = safeAdminConfigQuotesPath(String(formData.get("success_return_to") ?? returnTo), returnTo);
  const calendarIds = parseCalendarIdsFromFormData(formData);
  if (calendarIds.length === 0) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_config_action.no_target_local_calendar")));
  }
  let removedCount = 0;
  for (const calendarId of calendarIds) {
    const result = await backendRequest<{ message?: string }>(
      `/api/v1/quote-school-calendars/${encodeURIComponent(calendarId)}/deployment`,
      { method: "DELETE" },
      token,
    );
    if (!result.ok) {
      redirect(appendQueryMessage(returnTo, "error", result.message));
    }
    removedCount += 1;
  }
  revalidatePath("/admin/config/calendars");
  revalidatePath("/admin/config/quotes");
  redirect(appendQueryMessage(successReturnTo, "ok", uiText(language, "admin.quote_config_action.calendar_group_remove", { count: removedCount })));
}

export async function createAdminQuoteTemplateV2ConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const adminLanguage = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=doc_templates"));
  const name = String(formData.get("name") ?? "").trim();
  const code = quoteTemplateCodeFromName(name);
  const templateType = "quote_body";
  const target = optionalField(formData, "target");
  const templateLanguage = String(formData.get("language") ?? "fr").trim().toLowerCase();
  const description = optionalField(formData, "description");
  const subjectTemplate = String(formData.get("subject_template") ?? "").trim();
  const bodyTemplate = String(formData.get("body_template") ?? "").trim();
  const changelog = optionalField(formData, "changelog");
  const isActive = parseCheckboxFlag(formData, "is_active", true);
  const isDefault = parseCheckboxFlag(formData, "is_default", false);
  const publishNow = parseCheckboxFlag(formData, "publish_now", true);
  const statusValue = String(formData.get("status") ?? "draft").trim().toLowerCase();
  const normalizedStatus = statusValue === "archived" || statusValue === "published" ? statusValue : "draft";

  if (!name || !subjectTemplate || !bodyTemplate) {
    redirect(appendQueryMessage(returnTo, "error", uiText(adminLanguage, "admin.quote_config_action.invalid_quote_doc_template")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    "/api/v1/quote-templates-v2",
    {
      method: "POST",
      body: JSON.stringify({
        code,
        name,
        template_type: templateType || "quote_body",
        target,
        language: templateLanguage,
        description,
        is_active: isActive,
        is_default: isDefault,
        status: normalizedStatus,
        subject_template: subjectTemplate,
        body_template: bodyTemplate,
        changelog,
        publish_now: publishNow,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(adminLanguage, "admin.quote_config_action.quote_doc_template_created")));
}

export async function updateAdminQuoteTemplateV2ConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const adminLanguage = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=doc_templates"));
  const templateId = parseUuid(String(formData.get("template_id") ?? ""));
  const currentCode = String(formData.get("code") ?? "").trim();
  const name = String(formData.get("name") ?? "").trim();
  const code = currentCode || quoteTemplateCodeFromName(name);
  const templateType = "quote_body";
  const target = optionalField(formData, "target");
  const templateLanguage = String(formData.get("language") ?? "fr").trim().toLowerCase();
  const description = optionalField(formData, "description");
  const subjectTemplate = String(formData.get("subject_template") ?? "").trim();
  const bodyTemplate = String(formData.get("body_template") ?? "").trim();
  const changelog = optionalField(formData, "changelog");
  const isActive = parseCheckboxFlag(formData, "is_active", true);
  const isDefault = parseCheckboxFlag(formData, "is_default", false);
  const publishNow = parseCheckboxFlag(formData, "publish_now", true);
  const statusValue = String(formData.get("status") ?? "draft").trim().toLowerCase();
  const normalizedStatus = statusValue === "archived" || statusValue === "published" ? statusValue : "draft";

  if (!templateId || !name || !subjectTemplate || !bodyTemplate) {
    redirect(appendQueryMessage(returnTo, "error", uiText(adminLanguage, "admin.quote_config_action.invalid_quote_doc_template")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/quote-templates-v2/${encodeURIComponent(templateId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        code,
        name,
        template_type: templateType || "quote_body",
        target,
        language: templateLanguage,
        description,
        is_active: isActive,
        is_default: isDefault,
        status: normalizedStatus,
        subject_template: subjectTemplate,
        body_template: bodyTemplate,
        changelog,
        publish_now: publishNow,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(adminLanguage, "admin.quote_config_action.quote_doc_template_updated")));
}

export async function deleteAdminQuoteTemplateV2ConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const adminLanguage = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=doc_templates"));
  const templateId = parseUuid(String(formData.get("template_id") ?? ""));
  if (!templateId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(adminLanguage, "admin.quote_config_action.invalid_quote_doc_template")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/quote-templates-v2/${encodeURIComponent(templateId)}`,
    { method: "DELETE" },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(adminLanguage, "admin.quote_config_action.quote_doc_template_archived")));
}

export async function hardDeleteAdminQuoteTemplateV2ConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const adminLanguage = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=doc_templates"));
  const templateId = parseUuid(String(formData.get("template_id") ?? ""));
  const confirmation = String(formData.get("confirm_delete") ?? "").trim().toUpperCase();
  if (!templateId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(adminLanguage, "admin.quote_config_action.invalid_quote_doc_template")));
  }
  if (!isDeleteConfirmationValue(confirmation)) {
    redirect(appendQueryMessage(returnTo, "error", uiText(adminLanguage, "admin.quote_config_action.invalid_delete_confirmation")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/quote-templates-v2/${encodeURIComponent(templateId)}/permanent`,
    { method: "DELETE" },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(adminLanguage, "admin.quote_config_action.quote_doc_template_deleted_permanently")));
}

export async function createAdminTermsTemplateConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const adminLanguage = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=doc_terms"));
  const name = String(formData.get("name") ?? "").trim();
  const code = termsTemplateCodeFromName(name);
  const termsType = "cgv";
  const target = optionalField(formData, "target");
  const templateLanguage = String(formData.get("language") ?? "fr").trim().toLowerCase();
  const description = optionalField(formData, "description");
  const versionLabel = String(formData.get("version_label") ?? "").trim();
  const content = String(formData.get("content") ?? "").trim();
  const changelog = optionalField(formData, "changelog");
  const isActive = parseCheckboxFlag(formData, "is_active", true);
  const publishNow = parseCheckboxFlag(formData, "publish_now", true);
  const statusValue = String(formData.get("status") ?? "draft").trim().toLowerCase();
  const normalizedStatus = statusValue === "archived" || statusValue === "published" ? statusValue : "draft";
  if (!name || !versionLabel || !content) {
    redirect(appendQueryMessage(returnTo, "error", uiText(adminLanguage, "admin.quote_config_action.invalid_terms_template")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    "/api/v1/terms-templates",
    {
      method: "POST",
      body: JSON.stringify({
        code,
        name,
        terms_type: termsType,
        target,
        language: templateLanguage,
        description,
        is_active: isActive,
        status: normalizedStatus,
        version_label: versionLabel,
        content,
        changelog,
        publish_now: publishNow,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(adminLanguage, "admin.quote_config_action.terms_template_created")));
}

export async function updateAdminTermsTemplateConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const adminLanguage = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=doc_terms"));
  const templateId = parseUuid(String(formData.get("template_id") ?? ""));
  const currentCode = String(formData.get("current_code") ?? "").trim();
  const name = String(formData.get("name") ?? "").trim();
  const code = currentCode || termsTemplateCodeFromName(name);
  const termsType = "cgv";
  const target = optionalField(formData, "target");
  const templateLanguage = String(formData.get("language") ?? "fr").trim().toLowerCase();
  const description = optionalField(formData, "description");
  const versionLabel = String(formData.get("version_label") ?? "").trim();
  const content = String(formData.get("content") ?? "").trim();
  const changelog = optionalField(formData, "changelog");
  const isActive = parseCheckboxFlag(formData, "is_active", true);
  const publishNow = parseCheckboxFlag(formData, "publish_now", true);
  const statusValue = String(formData.get("status") ?? "draft").trim().toLowerCase();
  const normalizedStatus = statusValue === "archived" || statusValue === "published" ? statusValue : "draft";
  if (!templateId || !name || !versionLabel || !content) {
    redirect(appendQueryMessage(returnTo, "error", uiText(adminLanguage, "admin.quote_config_action.invalid_terms_template")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/terms-templates/${encodeURIComponent(templateId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        code,
        name,
        terms_type: termsType,
        target,
        language: templateLanguage,
        description,
        is_active: isActive,
        status: normalizedStatus,
        version_label: versionLabel,
        content,
        changelog,
        publish_now: publishNow,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(adminLanguage, "admin.quote_config_action.terms_template_updated")));
}

export async function deleteAdminTermsTemplateConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const adminLanguage = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=doc_terms"));
  const templateId = parseUuid(String(formData.get("template_id") ?? ""));
  if (!templateId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(adminLanguage, "admin.quote_config_action.invalid_terms_template")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/terms-templates/${encodeURIComponent(templateId)}`,
    { method: "DELETE" },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(adminLanguage, "admin.quote_config_action.terms_template_archived")));
}

export async function hardDeleteAdminTermsTemplateConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const adminLanguage = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=doc_terms"));
  const templateId = parseUuid(String(formData.get("template_id") ?? ""));
  const confirmation = String(formData.get("confirm_delete") ?? "").trim().toUpperCase();
  if (!templateId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(adminLanguage, "admin.quote_config_action.invalid_terms_template")));
  }
  if (!isDeleteConfirmationValue(confirmation)) {
    redirect(appendQueryMessage(returnTo, "error", uiText(adminLanguage, "admin.quote_config_action.invalid_delete_confirmation")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/terms-templates/${encodeURIComponent(templateId)}/permanent`,
    { method: "DELETE" },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(adminLanguage, "admin.quote_config_action.terms_template_deleted_permanently")));
}

export async function createAdminQuoteDocumentBindingConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const adminLanguage = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=doc_bindings"));
  const prospectType = optionalField(formData, "prospect_type");
  const contextType = optionalField(formData, "context_type");
  const activityFamily = optionalField(formData, "activity_family");
  const activityId = parseUuid(String(formData.get("activity_id") ?? ""));
  const quoteTypeId = parseUuid(String(formData.get("quote_type_id") ?? ""));
  const bindingLanguage = optionalField(formData, "language");
  const currency = optionalField(formData, "currency")?.toUpperCase() || null;
  const quoteTemplateId = parseUuid(String(formData.get("quote_template_id") ?? ""));
  const quoteTemplateVersionId = parseUuid(String(formData.get("quote_template_version_id") ?? ""));
  const termsTemplateId = parseUuid(String(formData.get("terms_template_id") ?? ""));
  const termsTemplateVersionId = parseUuid(String(formData.get("terms_template_version_id") ?? ""));
  const priority = parseNonNegativeInt(String(formData.get("priority") ?? "100")) ?? 100;
  const isActive = parseCheckboxFlag(formData, "is_active", true);
  const notes = optionalField(formData, "notes");

  const result = await backendRequest<Record<string, unknown>>(
    "/api/v1/quote-document-bindings",
    {
      method: "POST",
      body: JSON.stringify({
        prospect_type: prospectType,
        context_type: contextType,
        activity_family: activityFamily,
        activity_id: activityId,
        quote_type_id: quoteTypeId,
        language: bindingLanguage,
        currency,
        quote_template_id: quoteTemplateId,
        quote_template_version_id: quoteTemplateVersionId,
        terms_template_id: termsTemplateId,
        terms_template_version_id: termsTemplateVersionId,
        priority,
        is_active: isActive,
        notes,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(adminLanguage, "admin.quote_config_action.selection_rule_created")));
}

export async function updateAdminQuoteDocumentBindingConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const adminLanguage = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=doc_bindings"));
  const bindingId = parseUuid(String(formData.get("binding_id") ?? ""));
  const prospectType = optionalField(formData, "prospect_type");
  const contextType = optionalField(formData, "context_type");
  const activityFamily = optionalField(formData, "activity_family");
  const activityId = parseUuid(String(formData.get("activity_id") ?? ""));
  const quoteTypeId = parseUuid(String(formData.get("quote_type_id") ?? ""));
  const bindingLanguage = optionalField(formData, "language");
  const currency = optionalField(formData, "currency")?.toUpperCase() || null;
  const quoteTemplateId = parseUuid(String(formData.get("quote_template_id") ?? ""));
  const quoteTemplateVersionId = parseUuid(String(formData.get("quote_template_version_id") ?? ""));
  const termsTemplateId = parseUuid(String(formData.get("terms_template_id") ?? ""));
  const termsTemplateVersionId = parseUuid(String(formData.get("terms_template_version_id") ?? ""));
  const priority = parseNonNegativeInt(String(formData.get("priority") ?? "100")) ?? 100;
  const isActive = parseCheckboxFlag(formData, "is_active", true);
  const notes = optionalField(formData, "notes");
  if (!bindingId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(adminLanguage, "admin.quote_config_action.invalid_selection_rule")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/quote-document-bindings/${encodeURIComponent(bindingId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        prospect_type: prospectType,
        context_type: contextType,
        activity_family: activityFamily,
        activity_id: activityId,
        quote_type_id: quoteTypeId,
        language: bindingLanguage,
        currency,
        quote_template_id: quoteTemplateId,
        quote_template_version_id: quoteTemplateVersionId,
        terms_template_id: termsTemplateId,
        terms_template_version_id: termsTemplateVersionId,
        priority,
        is_active: isActive,
        notes,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(adminLanguage, "admin.quote_config_action.selection_rule_updated")));
}

export async function deleteAdminQuoteDocumentBindingConfigAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const adminLanguage = await ensureAdminAndGetLanguage(token);

  const returnTo = safeAdminConfigQuotesPath(String(formData.get("return_to") ?? "/admin/config/quotes?tab=doc_bindings"));
  const bindingId = parseUuid(String(formData.get("binding_id") ?? ""));
  if (!bindingId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(adminLanguage, "admin.quote_config_action.invalid_selection_rule")));
  }

  const result = await backendRequest<Record<string, unknown>>(
    `/api/v1/quote-document-bindings/${encodeURIComponent(bindingId)}`,
    { method: "DELETE" },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/config/quotes");
  revalidatePath("/admin/quotes/new");
  redirect(appendQueryMessage(returnTo, "ok", uiText(adminLanguage, "admin.quote_config_action.selection_rule_deleted")));
}

async function runPublicQuoteAction({
  action,
  quoteId,
  token,
  body,
}: {
  action: "approve" | "reject" | "change-request";
  quoteId: string;
  token: string;
  body: Record<string, unknown> | null;
}): Promise<{ ok: boolean; message: string }> {
  const result = await backendRequest<{ quote: { id: string } }>(
    `/api/v1/public/quotes/${encodeURIComponent(quoteId)}/${action}?t=${encodeURIComponent(token)}`,
    {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    },
  );
  if (!result.ok) {
    return { ok: false, message: result.message };
  }
  return { ok: true, message: "" };
}

function safeQuotePublicPath(path: string, fallback: string): string {
  const value = path.trim();
  if (value.startsWith("/q/")) {
    return value;
  }
  return fallback;
}

export async function approvePublicQuoteAction(formData: FormData): Promise<void> {
  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const token = String(formData.get("public_token") ?? "").trim();
  const returnTo = safeQuotePublicPath(String(formData.get("return_to") ?? `/q/${quoteId}?t=${encodeURIComponent(token)}`), `/q/${quoteId}?t=${encodeURIComponent(token)}`);
  const solfegeSlotRequired = String(formData.get("solfege_slot_required") ?? "").trim() === "1";
  const selectedSolfegeSlotKey = String(formData.get("selected_solfege_slot_key") ?? "").trim();
  if (!quoteId || !token) {
    redirect(setQueryParam(returnTo, "error_code", "quote_public_invalid_link"));
  }
  if (solfegeSlotRequired && !selectedSolfegeSlotKey) {
    redirect(setQueryParam(returnTo, "error_code", "quote_public_solfege_slot_required"));
  }
  const result = await runPublicQuoteAction({
    action: "approve",
    quoteId,
    token,
    body: selectedSolfegeSlotKey ? { selected_solfege_slot_key: selectedSolfegeSlotKey } : {},
  });
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  redirect(setQueryParam(returnTo, "ok_code", "quote_public_approved"));
}

export async function rejectPublicQuoteAction(formData: FormData): Promise<void> {
  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const token = String(formData.get("public_token") ?? "").trim();
  const returnTo = safeQuotePublicPath(String(formData.get("return_to") ?? `/q/${quoteId}?t=${encodeURIComponent(token)}`), `/q/${quoteId}?t=${encodeURIComponent(token)}`);
  if (!quoteId || !token) {
    redirect(setQueryParam(returnTo, "error_code", "quote_public_invalid_link"));
  }
  const result = await runPublicQuoteAction({
    action: "reject",
    quoteId,
    token,
    body: null,
  });
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  redirect(setQueryParam(returnTo, "ok_code", "quote_public_rejected"));
}

export async function changeRequestPublicQuoteAction(formData: FormData): Promise<void> {
  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const token = String(formData.get("public_token") ?? "").trim();
  const message = String(formData.get("change_message") ?? "").trim();
  const returnTo = safeQuotePublicPath(String(formData.get("return_to") ?? `/q/${quoteId}?t=${encodeURIComponent(token)}`), `/q/${quoteId}?t=${encodeURIComponent(token)}`);
  if (!quoteId || !token) {
    redirect(setQueryParam(returnTo, "error_code", "quote_public_invalid_link"));
  }
  if (!message) {
    redirect(setQueryParam(returnTo, "error_code", "quote_public_change_request_required"));
  }
  const result = await runPublicQuoteAction({
    action: "change-request",
    quoteId,
    token,
    body: { message },
  });
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  redirect(setQueryParam(returnTo, "ok_code", "quote_public_change_request_sent"));
}

export async function selectQuoteFollowupSlotAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const followupId = String(formData.get("followup_id") ?? "").trim();
  const levelCode = String(formData.get("solfege_level_code") ?? "").trim();
  const slotJson = String(formData.get("slot_json") ?? "").trim();
  const slotDate = String(formData.get("slot_date") ?? "").trim();
  const slotStart = String(formData.get("slot_start_time") ?? "").trim();
  const slotEnd = String(formData.get("slot_end_time") ?? "").trim();
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? "/admin/quotes"));
  if (!followupId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_transform_action.incomplete_solfege_slot")));
  }

  let slotPayload: Record<string, unknown> | null = null;
  if (slotJson) {
    try {
      const parsed = JSON.parse(slotJson) as unknown;
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        slotPayload = { ...(parsed as Record<string, unknown>) };
      }
    } catch {
      slotPayload = null;
    }
  }

  if (slotPayload && levelCode && !String(slotPayload.level_code ?? "").trim()) {
    slotPayload.level_code = levelCode;
  }

  if (!slotPayload && slotDate && slotStart && slotEnd) {
    slotPayload = {
      level_code: levelCode || null,
      date: slotDate,
      start_time: slotStart,
      end_time: slotEnd,
    };
  }

  if (!slotPayload) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_transform_action.incomplete_solfege_slot")));
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/quote-followups/${encodeURIComponent(followupId)}/select-solfege-slot`,
    {
      method: "POST",
      body: JSON.stringify({
        slot: slotPayload,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/quotes");
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_transform_action.solfege_slot_saved")));
}

export async function changeQuoteFollowupPaymentMethodAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const followupId = String(formData.get("followup_id") ?? "").trim();
  const paymentMethodCode = String(formData.get("payment_method_code") ?? "").trim();
  const paymentPlanId = parseUuid(String(formData.get("payment_plan_id") ?? ""));
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? "/admin/quotes"));
  if (!followupId || !paymentMethodCode) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_transform_action.invalid_payment_method")));
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/quote-followups/${encodeURIComponent(followupId)}/change-payment-method`,
    {
      method: "POST",
      body: JSON.stringify({
        payment_method_code: paymentMethodCode,
        payment_plan_id: paymentPlanId,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/quotes");
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_transform_action.payment_method_updated")));
}

export async function finalizeQuoteFollowupAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);
  const followupId = String(formData.get("followup_id") ?? "").trim();
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? "/admin/quotes"));
  if (!followupId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_transform_action.followup_not_found")));
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/quote-followups/${encodeURIComponent(followupId)}/finalize`,
    { method: "POST" },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/quotes");
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_transform_action.followup_finalized")));
}

export async function rollbackQuoteTransformationAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const followupId = String(formData.get("followup_id") ?? "").trim();
  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? `/admin/quotes/${quoteId}?section=integration`));
  if (!followupId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_transform_action.followup_not_found")));
  }

  const result = await backendRequest<{ id: string }>(
    `/api/v1/quote-followups/${encodeURIComponent(followupId)}/rollback-transformation`,
    { method: "POST" },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }

  revalidatePath("/admin/quotes");
  if (quoteId) {
    revalidatePath(`/admin/quotes/${quoteId}`);
    revalidatePath(`/admin/quotes/${quoteId}/transform`);
  }
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_transform_action.transformation_rolled_back")));
}

function ensureRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

type QuoteFollowupForTransformation = {
  id: string;
  status: string;
  created_at?: string;
  updated_at?: string;
  payload: Record<string, unknown>;
};

type QuoteTransformLineOut = {
  id: string;
  line_type: string;
  line_category: string;
  master_item_type: string | null;
  activity_id: string | null;
  title: string;
  quantity: string;
  vat_rate: string;
  amount_ht: string;
  amount_ttc: string;
  meta?: Record<string, unknown>;
};

type QuoteTransformQuoteOut = {
  id: string;
  quote_number: string;
  status: string;
  context_type: string;
  currency: string;
  total_ttc: string;
  school_year_label: string | null;
  legal_entity_id: string | null;
  payment_plan_id: string | null;
  quote_type: string;
  quote_type_id: string | null;
  location_id: string | null;
  client_id: string | null;
  prospect_id: string | null;
  meta: Record<string, unknown>;
  calendar_snapshot: Record<string, unknown>;
  payment_terms_snapshot: Record<string, unknown>;
};

type QuoteTransformDetailOut = {
  quote: QuoteTransformQuoteOut;
  lines: QuoteTransformLineOut[];
};

type QuoteTransformProspectOut = {
  id: string;
  first_name: string | null;
  last_name: string | null;
  email: string;
  phone: string | null;
  parent_prospect_id: string | null;
  meta: Record<string, unknown>;
};

type QuoteTransformQuoteTypeOut = {
  id: string;
  formula_name: string | null;
};

type QuoteTransformPaymentPlanOut = {
  id: string;
  name: string;
};

function transformToNumber(raw: string | number | null | undefined, fallback = 0): number {
  const parsed = Number(String(raw ?? "").replace(",", "."));
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return parsed;
}

function transformLocationNameById(locations: Array<{ id: string; name: string }>, locationId: string | null): string {
  if (!locationId) {
    return "Lieu non defini";
  }
  return locations.find((location) => location.id === locationId)?.name || "Lieu non defini";
}

async function loadQuoteQuickTransformAnalysis(
  quoteId: string,
  token: string,
): Promise<{
  analysis: QuoteQuickTransformAnalysis;
  followupId: string | null;
}> {
  const [detailResult, followupsResult, clientsResult, activitiesResult, plansResult, locationsResult, quoteTypesResult, paymentPlansResult] = await Promise.all([
    backendRequest<QuoteTransformDetailOut>(`/api/v1/quotes/${encodeURIComponent(quoteId)}`, {}, token),
    backendRequest<QuoteFollowupForTransformation[]>(`/api/v1/quote-followups?quote_id=${encodeURIComponent(quoteId)}`, {}, token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?limit=1000&include_archived=false", {}, token),
    backendRequest<AdminActivityOut[]>("/api/v1/admin/activities?include_inactive=true", {}, token),
    backendRequest<PlanOut[]>("/api/v1/plans?active=true", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=false", {}, token),
    backendRequest<QuoteTransformQuoteTypeOut[]>("/api/v1/quote-types", {}, token),
    backendRequest<QuoteTransformPaymentPlanOut[]>("/api/v1/payment-plans", {}, token),
  ]);

  if (!detailResult.ok) {
    throw new Error(detailResult.message);
  }

  const detail = detailResult.data;
  const clientsRaw = clientsResult.ok ? clientsResult.data : [];
  const activitiesRaw = activitiesResult.ok ? activitiesResult.data : [];
  const plansRaw = plansResult.ok ? plansResult.data : [];
  const locationsRaw = locationsResult.ok ? locationsResult.data : [];
  const quoteTypes = quoteTypesResult.ok ? quoteTypesResult.data : [];
  const paymentPlans = paymentPlansResult.ok ? paymentPlansResult.data : [];
  const followups = followupsResult.ok ? followupsResult.data.slice() : [];
  followups.sort((left, right) => {
    const leftTime = Date.parse(String(left.updated_at ?? ""));
    const rightTime = Date.parse(String(right.updated_at ?? ""));
    return (Number.isFinite(rightTime) ? rightTime : 0) - (Number.isFinite(leftTime) ? leftTime : 0);
  });
  const activeFollowup = followups[0] || null;

  const activityIds = Array.from(new Set(
    detail.lines
      .map((line) => line.activity_id)
      .filter((activityId): activityId is string => Boolean(activityId)),
  ));
  const sessionsPerActivity = await Promise.all(
    activityIds.map(async (activityId) => {
      const query = new URLSearchParams();
      query.set("course_type_id", activityId);
      const result = await backendRequest<AdminSessionOut[]>(`/api/v1/admin/sessions?${query.toString()}`, {}, token);
      return {
        activityId,
        sessions: result.ok ? result.data : [],
      };
    }),
  );

  const prospectResult = detail.quote.prospect_id
    ? await backendRequest<QuoteTransformProspectOut>(`/api/v1/prospects/${encodeURIComponent(detail.quote.prospect_id)}`, {}, token)
    : null;
  const prospectRaw = prospectResult && prospectResult.ok ? prospectResult.data : null;
  const sourceClientRaw = detail.quote.client_id
    ? clientsRaw.find((client) => client.id === detail.quote.client_id) || null
    : null;

  const prospectTypeRaw = String((prospectRaw?.meta || {}).prospect_type || "adult").trim().toLowerCase();
  const fallbackProspectTypeRaw = String(sourceClientRaw?.client_kind || "").trim().toUpperCase();
  const prospect: QuoteTransformProspect | null = prospectRaw
    ? {
      id: prospectRaw.id,
      firstName: prospectRaw.first_name,
      lastName: prospectRaw.last_name,
      email: prospectRaw.email,
      phone: prospectRaw.phone,
      parentProspectId: prospectRaw.parent_prospect_id,
      prospectType: prospectTypeRaw === "child" ? "child" : "adult",
      meta: prospectRaw.meta || {},
    }
    : sourceClientRaw
      ? {
        id: `client:${sourceClientRaw.id}`,
        firstName: sourceClientRaw.first_name,
        lastName: sourceClientRaw.last_name,
        email: sourceClientRaw.email,
        phone: sourceClientRaw.mobile_phone_1 || sourceClientRaw.phone || sourceClientRaw.home_phone,
        parentProspectId: null,
        prospectType: fallbackProspectTypeRaw === "CHILD" ? "child" : "adult",
        meta: {
          source: "linked_client_fallback",
          linked_client_id: sourceClientRaw.id,
        },
      }
      : null;

  const clients: QuoteTransformClient[] = clientsRaw.map((client) => ({
    id: client.id,
    firstName: client.first_name,
    lastName: client.last_name,
    email: client.email,
    phone: client.phone,
    mobilePhone1: client.mobile_phone_1,
    mobilePhone2: client.mobile_phone_2,
    homePhone: client.home_phone,
    familyName: client.family_name,
    clientKind: client.client_kind,
    clientStatus: client.client_status,
  }));

  const activities: QuoteTransformActivityCatalog[] = activitiesRaw.map((activity) => ({
    id: activity.id,
    name: activity.name,
    serviceCode: activity.service_code,
    durationMinutes: activity.duration_minutes,
    defaultCourseRateTtc: activity.default_course_rate_ttc ? transformToNumber(activity.default_course_rate_ttc) : null,
    mode: activity.mode,
    active: activity.active,
  }));

  const sessionsByActivityId: Record<string, QuoteTransformSession[]> = {};
  for (const item of sessionsPerActivity) {
    sessionsByActivityId[item.activityId] = item.sessions.map((session) => {
      const seatsRemaining = Math.max(0, Number(session.capacity_max || 0) - Number(session.booked_count || 0));
      return {
        id: session.id,
        courseTypeId: session.course_type_id,
        locationId: session.location_id,
        title: session.title,
        startAtUtc: session.start_at_utc,
        endAtUtc: session.end_at_utc,
        timezone: session.timezone,
        teacherDisplayName: session.effective_teacher_display_name,
        status: session.status,
        statusLabel: session.status_label,
        capacityMax: session.capacity_max,
        bookedCount: session.booked_count,
        seatsRemaining,
      };
    });
  }

  const plans: QuoteTransformPlan[] = plansRaw.map((plan) => ({
    id: plan.id,
    name: plan.name,
    kind: plan.kind,
    active: plan.active,
  }));

  const quoteType = quoteTypes.find((row) => row.id === detail.quote.quote_type_id) || null;
  const paymentPlan = paymentPlans.find((row) => row.id === detail.quote.payment_plan_id) || null;

  const lines: QuoteTransformLine[] = detail.lines.map((line) => ({
    id: line.id,
    lineType: line.line_type,
    lineCategory: line.line_category,
    masterItemType: line.master_item_type,
    activityId: line.activity_id,
    title: line.title,
    quantity: transformToNumber(line.quantity, 1),
    durationMinutes: null,
    pricingUnit: line.line_category === "service" ? "session" : "item",
    amountHt: transformToNumber(line.amount_ht),
    amountTtc: transformToNumber(line.amount_ttc),
    vatRate: transformToNumber(line.vat_rate),
    meta: line.meta || {},
  }));
  const defaultVatRate = lines.find((line) => line.vatRate > 0)?.vatRate ?? 20;

  const quote: QuoteTransformQuote = {
    id: detail.quote.id,
    quoteNumber: detail.quote.quote_number,
    status: detail.quote.status,
    clientId: detail.quote.client_id,
    currency: detail.quote.currency || "EUR",
    totalTtc: transformToNumber(detail.quote.total_ttc),
    totalHt: Number(lines.reduce((sum, line) => sum + line.amountHt, 0).toFixed(2)),
    schoolYearLabel: detail.quote.school_year_label,
    legalEntityId: detail.quote.legal_entity_id,
    legalEntityName: "A definir",
    paymentPlanName: paymentPlan?.name || String((detail.quote.payment_terms_snapshot || {}).payment_plan_name || "-"),
    quoteType: detail.quote.quote_type,
    quoteTypeFormulaName: quoteType?.formula_name || null,
    locationId: detail.quote.location_id,
    locationName: transformLocationNameById(locationsRaw, detail.quote.location_id),
    financialAdjustment: quoteTransformFinancialAdjustmentFromMeta(detail.quote.meta || {}, defaultVatRate),
  };

  const analysis = analyzeQuoteQuickTransformStatus({
    quote,
    prospect,
    lines,
    clients,
    activities,
    sessionsByActivityId,
    plans,
    calendarSnapshot: detail.quote.calendar_snapshot || {},
    followupId: activeFollowup?.id || null,
    followupStatus: activeFollowup?.status || null,
    scenario: "live",
  });

  return {
    analysis,
    followupId: activeFollowup?.id || null,
  };
}

export async function saveQuoteTransformationDraftAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const followupId = String(formData.get("followup_id") ?? "").trim();
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? `/admin/quotes/${quoteId}/transform`));
  const transformationRaw = parseJsonObject(String(formData.get("transformation_json") ?? ""));

  if (!quoteId || !followupId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_transform_action.followup_required_save_draft")));
  }
  if (!transformationRaw) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_transform_action.invalid_transformation_payload")));
  }

  const followupResult = await backendRequest<QuoteFollowupForTransformation>(
    `/api/v1/quote-followups/${encodeURIComponent(followupId)}`,
    {},
    token,
  );
  if (!followupResult.ok) {
    redirect(appendQueryMessage(returnTo, "error", followupResult.message));
  }

  const currentPayload = ensureRecord(followupResult.data.payload);
  const nextPayload = {
    ...currentPayload,
    quote_to_enrollment: transformationRaw,
  };

  const patchResult = await backendRequest<QuoteFollowupForTransformation>(
    `/api/v1/quote-followups/${encodeURIComponent(followupId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        status: followupResult.data.status === "completed" ? "completed" : "partially_configured",
        payload: nextPayload,
      }),
    },
    token,
  );
  if (!patchResult.ok) {
    redirect(appendQueryMessage(returnTo, "error", patchResult.message));
  }

  revalidatePath("/admin/quotes");
  revalidatePath(`/admin/quotes/${quoteId}`);
  revalidatePath(`/admin/quotes/${quoteId}/transform`);
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_transform_action.transformation_draft_saved")));
}

export async function finalizeQuoteTransformationAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const followupId = String(formData.get("followup_id") ?? "").trim();
  const allowForceFinalize = String(formData.get("allow_force_finalize") ?? "0").trim() === "1";
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? `/admin/quotes/${quoteId}/transform`));
  const transformationRaw = parseJsonObject(String(formData.get("transformation_json") ?? ""));

  if (!quoteId || !followupId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_transform_action.followup_required_finalize")));
  }
  if (!transformationRaw) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_transform_action.invalid_transformation_payload")));
  }
  if (!allowForceFinalize) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_transform_action.critical_blocks_remaining")));
  }

  const followupResult = await backendRequest<QuoteFollowupForTransformation>(
    `/api/v1/quote-followups/${encodeURIComponent(followupId)}`,
    {},
    token,
  );
  if (!followupResult.ok) {
    redirect(appendQueryMessage(returnTo, "error", followupResult.message));
  }

  const currentPayload = ensureRecord(followupResult.data.payload);
  const existingTransformation = ensureRecord(currentPayload.quote_to_enrollment);
  const existingExecution = ensureRecord(currentPayload.quote_to_enrollment_execution);
  const incomingIdempotencyKey = String(transformationRaw.idempotencyKey ?? "").trim();
  const existingIdempotencyKey = String(existingTransformation.idempotencyKey ?? "").trim();
  const existingFinalizedAt = String(existingTransformation.finalizedAt ?? "").trim();
  const existingExecutionStatus = String(existingExecution.status ?? "").trim().toLowerCase();

  if (
    existingExecutionStatus === "executed"
    && existingFinalizedAt
    && incomingIdempotencyKey
    && incomingIdempotencyKey === existingIdempotencyKey
  ) {
    redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_transform_action.transformation_already_executed_idempotent")));
  }

  const finalizedAt = new Date().toISOString();
  const nextTransformation = {
    ...transformationRaw,
    finalizedAt,
  };
  const nextPayload = {
    ...currentPayload,
    quote_to_enrollment: nextTransformation,
  };

  const patchResult = await backendRequest<QuoteFollowupForTransformation>(
    `/api/v1/quote-followups/${encodeURIComponent(followupId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        status: existingExecutionStatus === "executed" ? "completed" : "partially_configured",
        payload: nextPayload,
      }),
    },
    token,
  );
  if (!patchResult.ok) {
    redirect(appendQueryMessage(returnTo, "error", patchResult.message));
  }

  const finalizeResult = await backendRequest<QuoteFollowupForTransformation>(
    `/api/v1/quote-followups/${encodeURIComponent(followupId)}/finalize`,
    { method: "POST" },
    token,
  );
  if (!finalizeResult.ok) {
    redirect(appendQueryMessage(returnTo, "error", finalizeResult.message));
  }

  revalidatePath("/admin/quotes");
  revalidatePath(`/admin/quotes/${quoteId}`);
  revalidatePath(`/admin/quotes/${quoteId}/transform`);
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_transform_action.transformation_executed")));
}

export async function quickTransformQuoteAction(formData: FormData): Promise<void> {
  const token = currentToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const language = await ensureAdminAndGetLanguage(token);

  const quoteId = String(formData.get("quote_id") ?? "").trim();
  const returnTo = safeAdminQuotesPath(String(formData.get("return_to") ?? `/admin/quotes/${quoteId}?section=integration`));
  if (!quoteId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_transform_action.quote_not_found")));
  }

  let runtime: { analysis: QuoteQuickTransformAnalysis; followupId: string | null };
  try {
    runtime = await loadQuoteQuickTransformAnalysis(quoteId, token);
  } catch (error) {
    const message = error instanceof Error ? error.message : uiText(language, "admin.quote_transform_action.quick_analysis_impossible");
    redirect(appendQueryMessage(returnTo, "error", message));
  }

  const { analysis, followupId } = runtime;
  if (!analysis.canQuickTransform || !analysis.suggestedDraft) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_transform_action.quick_transform_not_auto_validable")));
  }
  if (!followupId) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.quote_transform_action.quick_transform_followup_missing")));
  }

  const followupResult = await backendRequest<QuoteFollowupForTransformation>(
    `/api/v1/quote-followups/${encodeURIComponent(followupId)}`,
    {},
    token,
  );
  if (!followupResult.ok) {
    redirect(appendQueryMessage(returnTo, "error", followupResult.message));
  }

  const currentPayload = ensureRecord(followupResult.data.payload);
  const existingTransformation = ensureRecord(currentPayload.quote_to_enrollment);
  const existingExecution = ensureRecord(currentPayload.quote_to_enrollment_execution);
  const existingFinalizedAt = String(existingTransformation.finalizedAt ?? "").trim();
  const existingExecutionStatus = String(existingExecution.status ?? "").trim().toLowerCase();
  if (existingExecutionStatus === "executed" && existingFinalizedAt) {
    redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.quote_transform_action.transformation_already_executed")));
  }

  const quickDraft = {
    ...analysis.suggestedDraft,
    logs: [
      ...(analysis.suggestedDraft.logs || []),
      {
        at: new Date().toISOString(),
        action: "quote_quick_transform_execute",
        detail: "validation rapide executee via panneau devis",
      },
    ],
  };

  const delegated = new FormData();
  delegated.set("quote_id", quoteId);
  delegated.set("followup_id", followupId);
  delegated.set("allow_force_finalize", "1");
  delegated.set("return_to", returnTo);
  delegated.set("transformation_json", JSON.stringify(quickDraft));

  await finalizeQuoteTransformationAction(delegated);
}

function safeAdminReportingPath(formData: FormData, fallback = "/admin/reporting"): string {
  const raw = String(formData.get("return_to") ?? "").trim();
  if (raw.startsWith("/admin/reporting")) {
    return raw;
  }
  return fallback;
}

export async function createGeneratedReportAction(formData: FormData): Promise<void> {
  const token = currentToken();
  const returnTo = safeAdminReportingPath(formData);
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const criteria = {
    q: String(formData.get("q") ?? "").trim(),
    school_year_label: String(formData.get("school_year_label") ?? "").trim(),
    received_from: String(formData.get("received_from") ?? "").trim(),
    received_to: String(formData.get("received_to") ?? "").trim(),
    segment: String(formData.get("segment") ?? "").trim(),
    status: String(formData.get("status") ?? "").trim(),
    min_children: String(formData.get("min_children") ?? "2").trim() || "2",
  };
  const result = await backendRequest<{ id: string }>(
    "/api/v1/admin/reports/generated",
    {
      method: "POST",
      body: JSON.stringify({
        report_type: String(formData.get("report_type") ?? "intake-families").trim(),
        period_start: criteria.received_from || null,
        period_end: criteria.received_to || null,
        note: String(formData.get("note") ?? "").trim() || null,
        criteria,
      }),
    },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/reporting");
  redirect(appendQueryMessage(returnTo, "ok", "Rapport genere"));
}

export async function deleteGeneratedReportAction(formData: FormData): Promise<void> {
  const token = currentToken();
  const returnTo = safeAdminReportingPath(formData);
  const reportId = String(formData.get("report_id") ?? "").trim();
  if (!token || !reportId) {
    redirect(appendQueryMessage(returnTo, "error", "Suppression impossible"));
  }
  const result = await backendRequest<Record<string, never>>(
    `/api/v1/admin/reports/generated/${encodeURIComponent(reportId)}`,
    { method: "DELETE" },
    token,
  );
  if (!result.ok) {
    redirect(appendQueryMessage(returnTo, "error", result.message));
  }
  revalidatePath("/admin/reporting");
  redirect(appendQueryMessage(returnTo, "ok", "Rapport supprime"));
}
