import Link from "next/link";

import {
  approvePublicQuoteAction,
  changeRequestPublicQuoteAction,
  rejectPublicQuoteAction,
} from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import { localeForUiLanguage, normalizeUiLanguage, translateBackendMessage, type UiLanguage, uiText } from "../../../lib/ui-i18n";
import { sanitizeRichHtml } from "../../../lib/sanitize-rich-html";

type SearchParams = Record<string, string | string[] | undefined>;

type RouteParams = {
  params: {
    quoteId: string;
  };
  searchParams: SearchParams;
};

type QuoteOut = {
  id: string;
  quote_number: string;
  status: string;
  context_type: string;
  quote_type: string;
  school_year_label: string | null;
  currency: string;
  total_ttc: string;
  expires_at: string | null;
  estimated_solfege_level: string | null;
  solfege_duration_minutes: number | null;
  calendar_snapshot: Record<string, unknown>;
  payment_terms_snapshot: Record<string, unknown>;
  cgv_snapshot: Record<string, unknown>;
  public_token: string | null;
  pdf_token: string | null;
  language: string | null;
  timezone: string | null;
};

type QuoteLineOut = {
  id: string;
  line_type: string;
  line_category: string;
  title: string;
  description: string | null;
  quantity: string;
  unit_price_ttc: string;
  amount_ttc: string;
};

type QuotePublicOut = {
  quote: QuoteOut;
  lines: QuoteLineOut[];
  payment_schedule: Array<Record<string, unknown>>;
  solfege_selection: QuotePublicSolfegeSelectionOut | null;
};

type QuotePublicDocumentOut = {
  quote_id: string;
  audience: string;
  document_hash: string;
  combined_html: string;
  display_flags: Record<string, boolean>;
  visible_blocks: string[];
  hidden_blocks: string[];
  payment_schedule_compact_notice: string;
};

type QuotePublicSolfegeSlotOptionOut = {
  key: string;
  label: string;
};

type QuotePublicSolfegeSelectionOut = {
  level_code: string | null;
  duration_minutes: number | null;
  pending_selection: boolean;
  required: boolean;
  selected_key: string | null;
  selected_label: string | null;
  available_slots: QuotePublicSolfegeSlotOptionOut[];
};

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function resolveQuotePublicOkMessage(rawOk: string, okCode: string, language: UiLanguage): string {
  if (rawOk) {
    return rawOk;
  }
  const normalized = okCode.trim().toLowerCase();
  if (normalized === "quote_public_approved") {
    return uiText(language, "quote_public.approved_flash");
  }
  if (normalized === "quote_public_rejected") {
    return uiText(language, "quote_public.rejected_flash");
  }
  if (normalized === "quote_public_change_request_sent") {
    return uiText(language, "quote_public.change_request_sent");
  }
  return "";
}

function resolveQuotePublicErrorMessage(rawError: string, errorCode: string, errorStatus: string, language: UiLanguage): string {
  if (rawError) {
    return translateBackendMessage(language, rawError);
  }
  const normalized = errorCode.trim().toLowerCase();
  if (normalized === "quote_public_invalid_link") {
    return uiText(language, "quote_public.invalid_link");
  }
  if (normalized === "quote_public_change_request_required") {
    return uiText(language, "quote_public.change_request_required");
  }
  if (normalized === "quote_public_solfege_slot_required") {
    return uiText(language, "quote_public.solfege_slot_required");
  }
  if (normalized === "quote_pdf_token_invalid") {
    return uiText(language, "quote_public.invalid_pdf_link");
  }
  if (normalized === "quote_pdf_unavailable") {
    return uiText(language, "quote_public.pdf_unavailable", { status: errorStatus || "?" });
  }
  return "";
}

function normalizeTimezone(value: string | null | undefined): string {
  const candidate = (value ?? "").trim() || "Europe/Paris";
  try {
    new Intl.DateTimeFormat("fr-FR", { timeZone: candidate }).format(new Date());
    return candidate;
  } catch {
    return "Europe/Paris";
  }
}

function formatDate(value: string | null, language: UiLanguage, timezone: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString(localeForUiLanguage(language), {
    dateStyle: "full",
    timeStyle: "short",
    timeZone: normalizeTimezone(timezone),
  });
}

function formatAmount(value: string, currency: string, language: UiLanguage): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) {
    return `${value} ${currency}`;
  }
  try {
    return new Intl.NumberFormat(localeForUiLanguage(language), { style: "currency", currency: currency || "EUR" }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${(currency || "EUR").toUpperCase()}`;
  }
}

function quoteStatusLabel(status: string, language: UiLanguage): string {
  if (status === "sent") {
    return uiText(language, "quote_public.status_sent");
  }
  if (status === "change_requested") {
    return uiText(language, "quote_public.status_change_requested");
  }
  if (status === "approved") {
    return uiText(language, "quote_public.status_approved");
  }
  if (status === "rejected") {
    return uiText(language, "quote_public.status_rejected");
  }
  if (status === "expired") {
    return uiText(language, "quote_public.status_expired");
  }
  if (status === "cancelled") {
    return uiText(language, "quote_public.status_cancelled");
  }
  if (status === "replaced") {
    return uiText(language, "quote_public.status_replaced");
  }
  return status.replace(/_/g, " ");
}

function quoteStatusClass(status: string): string {
  if (status === "approved") return "status-ok";
  if (status === "sent" || status === "change_requested") return "status-warn";
  if (status === "rejected" || status === "expired" || status === "cancelled" || status === "replaced") return "status-cancelled";
  return "status-off";
}

function readObject(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function buildSelfPath(quoteId: string, token: string, language: UiLanguage): string {
  const suffix = language === "en" ? "&lang=en" : "";
  return `/q/${quoteId}?t=${encodeURIComponent(token)}${suffix}`;
}

export default async function PublicQuotePage({ params, searchParams }: RouteParams): Promise<JSX.Element> {
  const quoteId = String(params.quoteId || "").trim();
  const token = readParam(searchParams, "t").trim();
  const queryLanguage = normalizeUiLanguage(readParam(searchParams, "lang"));

  const invalidLink = !quoteId || !token;
  const quoteResult = invalidLink
    ? null
    : await backendRequest<QuotePublicOut>(`/api/v1/public/quotes/${encodeURIComponent(quoteId)}?t=${encodeURIComponent(token)}`);
  const documentResult =
    invalidLink
      ? null
      : await backendRequest<QuotePublicDocumentOut>(
          `/api/v1/public/quotes/${encodeURIComponent(quoteId)}/document?t=${encodeURIComponent(token)}&audience=public_page`,
        );
  const payload = quoteResult && quoteResult.ok ? quoteResult.data : null;
  const documentPayload = documentResult && documentResult.ok ? documentResult.data : null;
  const language = normalizeUiLanguage(payload?.quote.language || queryLanguage);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const ok = resolveQuotePublicOkMessage(readParam(searchParams, "ok").trim(), readParam(searchParams, "ok_code"), language);
  const error = resolveQuotePublicErrorMessage(
    readParam(searchParams, "error").trim(),
    readParam(searchParams, "error_code"),
    readParam(searchParams, "error_status"),
    language,
  );

  const canAct = payload ? ["sent", "change_requested"].includes(payload.quote.status) : false;
  const canRequestChange = payload?.quote.status === "sent";
  const selfPath = buildSelfPath(quoteId, token, language);
  const solfegeSelection = payload?.solfege_selection ?? null;
  const requiresSolfegeSelection = canAct && Boolean(solfegeSelection?.required);
  const shouldShowSolfegeSelector = canAct && Boolean(
    solfegeSelection
      && (
        solfegeSelection.required
        || (solfegeSelection.pending_selection && solfegeSelection.available_slots.length > 0)
      ),
  );

  return (
    <main className="quote-public-page">
      <section className="quote-public-shell">
        <section className="quote-public-main">
          <article className="card quote-public-header">
            <h1>{t("quote_public.page_title")}</h1>
            <p className="muted">{t("quote_public.page_subtitle")}</p>
            {ok ? <p className="flash-ok top-gap-sm">{ok}</p> : null}
            {error ? <p className="flash-err top-gap-sm">{error}</p> : null}
          </article>

          {invalidLink ? (
            <article className="card quote-public-error">
              <h2>{t("quote_public.invalid_link_title")}</h2>
              <p className="muted">{t("quote_public.invalid_link_body")}</p>
            </article>
          ) : !payload ? (
            <article className="card quote-public-error">
              <h2>{t("quote_public.inaccessible_title")}</h2>
              <p className="muted">{quoteResult?.ok === false ? quoteResult.message : t("quote_public.inaccessible_not_found")}</p>
            </article>
          ) : (
            <>
              <article className="card quote-public-meta">
                <div className="row spread wrap gap-sm">
                  <div>
                    <h2>{payload.quote.quote_number}</h2>
                    <p className="muted">{payload.quote.quote_type} · {payload.quote.school_year_label ?? t("quote_public.no_school_year")}</p>
                  </div>
                  <span className={`status-pill ${quoteStatusClass(payload.quote.status)}`}>{quoteStatusLabel(payload.quote.status, language)}</span>
                </div>
                <div className="quote-public-meta-grid top-gap-sm">
                  <article>
                    <span>{t("quote_public.total_ttc")}</span>
                    <strong>{formatAmount(payload.quote.total_ttc, payload.quote.currency, language)}</strong>
                  </article>
                  <article>
                    <span>{t("quote_public.expires_on")}</span>
                    <strong>{formatDate(payload.quote.expires_at, language, payload.quote.timezone)}</strong>
                  </article>
                </div>
              </article>

              <article className="card quote-public-lines-card">
                <h3>{t("quote_public.document_title")}</h3>
                {documentPayload ? (
                  <div className="top-gap-sm" dangerouslySetInnerHTML={{ __html: sanitizeRichHtml(documentPayload.combined_html) }} />
                ) : (
                  <p className="muted top-gap-sm">{t("quote_public.document_unavailable")}</p>
                )}
              </article>
            </>
          )}
        </section>

        <aside className="quote-public-sticky">
          <article className="card quote-public-sticky-card">
            <h3>{t("quote_public.actions_title")}</h3>
            {payload?.quote.pdf_token ? (
              <Link
                className="ghost quote-public-action"
                href={`/q/${payload.quote.id}/pdf?t=${encodeURIComponent(payload.quote.pdf_token)}${language === "en" ? "&lang=en" : ""}`}
                target="_blank"
              >
                {t("quote_public.download_pdf")}
              </Link>
            ) : null}

            {canAct ? (
              <>
                <form action={approvePublicQuoteAction} className="quote-public-form-action top-gap-sm">
                  <input type="hidden" name="quote_id" value={quoteId} />
                  <input type="hidden" name="public_token" value={token} />
                  <input type="hidden" name="return_to" value={selfPath} />
                  <input type="hidden" name="language" value={language} />
                  {shouldShowSolfegeSelector && solfegeSelection ? (
                    <section className="quote-public-solfege-box">
                      <div className="quote-public-solfege-header">
                        <div>
                          <span className="quote-public-solfege-kicker">{t("quote_public.solfege_kicker")}</span>
                          <strong>{t("quote_public.solfege_title")}</strong>
                        </div>
                        <span className="quote-public-solfege-badge">
                          {t(solfegeSelection.required ? "quote_public.solfege_required_badge" : "quote_public.solfege_optional_badge")}
                        </span>
                      </div>
                      <p className="quote-public-solfege-help">{t("quote_public.solfege_help")}</p>
                      <div className="quote-public-solfege-meta">
                        {solfegeSelection.level_code ? (
                          <span>{t("quote_public.solfege_level", { level: solfegeSelection.level_code })}</span>
                        ) : null}
                        {solfegeSelection.duration_minutes ? (
                          <span>{t("quote_public.solfege_duration", { duration: solfegeSelection.duration_minutes })}</span>
                        ) : null}
                      </div>
                      <input type="hidden" name="solfege_slot_required" value={solfegeSelection.required ? "1" : "0"} />
                      <fieldset className="quote-public-solfege-options">
                        <legend>{t("quote_public.solfege_slot_label")}</legend>
                        {solfegeSelection.available_slots.map((option) => (
                          <label key={option.key} className="quote-public-solfege-option">
                            <input
                              type="radio"
                              name="selected_solfege_slot_key"
                              value={option.key}
                              defaultChecked={option.key === solfegeSelection.selected_key}
                              required={solfegeSelection.required}
                            />
                            <span className="quote-public-solfege-option-main">
                              <span className="quote-public-solfege-option-title">{option.label}</span>
                              <span className="quote-public-solfege-option-helper">{t("quote_public.solfege_option_helper")}</span>
                            </span>
                          </label>
                        ))}
                      </fieldset>
                      {solfegeSelection.selected_label ? (
                        <p className="muted">{t("quote_public.solfege_selected_hint", { slot: solfegeSelection.selected_label })}</p>
                      ) : null}
                      <p className="muted">{t("quote_public.solfege_pending_notice")}</p>
                    </section>
                  ) : null}
                  <button type="submit" className="quote-cta-success">{t("quote_public.approve_cta")}</button>
                </form>

                {canRequestChange ? (
                  <form action={changeRequestPublicQuoteAction} className="quote-public-change-request top-gap-sm">
                    <input type="hidden" name="quote_id" value={quoteId} />
                    <input type="hidden" name="public_token" value={token} />
                    <input type="hidden" name="return_to" value={selfPath} />
                    <input type="hidden" name="language" value={language} />
                    <label>
                      <span className="quote-public-change-title">{t("quote_public.change_request_title")}</span>
                      <span className="quote-public-change-help">{t("quote_public.change_request_help")}</span>
                      <textarea
                        name="change_message"
                        required
                        rows={4}
                        placeholder={t("quote_public.change_request_placeholder")}
                      />
                    </label>
                    <button type="submit" className="quote-cta-change">{t("quote_public.change_request_submit")}</button>
                  </form>
                ) : null}

                <form action={rejectPublicQuoteAction} className="quote-public-form-action quote-public-reject-action top-gap-sm">
                  <input type="hidden" name="quote_id" value={quoteId} />
                  <input type="hidden" name="public_token" value={token} />
                  <input type="hidden" name="return_to" value={selfPath} />
                  <input type="hidden" name="language" value={language} />
                  <p className="muted">{t("quote_public.reject_help")}</p>
                  <button type="submit" className="quote-cta-danger">{t("quote_public.reject_cta")}</button>
                </form>
              </>
            ) : (
              <p className="muted top-gap-sm">{t("quote_public.no_actions")}</p>
            )}
          </article>
        </aside>
      </section>

      {canAct && !requiresSolfegeSelection ? (
        <section className="quote-mobile-sticky-actions">
          <form action={approvePublicQuoteAction}>
            <input type="hidden" name="quote_id" value={quoteId} />
            <input type="hidden" name="public_token" value={token} />
            <input type="hidden" name="return_to" value={selfPath} />
            <input type="hidden" name="language" value={language} />
            <button type="submit" className="quote-cta-success">{t("quote_public.approve_short")}</button>
          </form>
          <form action={rejectPublicQuoteAction}>
            <input type="hidden" name="quote_id" value={quoteId} />
            <input type="hidden" name="public_token" value={token} />
            <input type="hidden" name="return_to" value={selfPath} />
            <input type="hidden" name="language" value={language} />
            <button type="submit" className="quote-cta-danger">{t("quote_public.reject_short")}</button>
          </form>
        </section>
      ) : null}
    </main>
  );
}
