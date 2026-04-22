import Link from "next/link";

import {
  approvePublicQuoteAction,
  changeRequestPublicQuoteAction,
  rejectPublicQuoteAction,
} from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../lib/ui-i18n";

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

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatDate(value: string | null, language: UiLanguage): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString(localeForUiLanguage(language), { dateStyle: "full", timeStyle: "short" });
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
  return status.replace(/_/g, " ");
}

function quoteStatusClass(status: string): string {
  if (status === "approved") return "status-ok";
  if (status === "sent" || status === "change_requested") return "status-warn";
  if (status === "rejected" || status === "expired" || status === "cancelled") return "status-cancelled";
  return "status-off";
}

function readObject(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function buildSelfPath(quoteId: string, token: string): string {
  return `/q/${quoteId}?t=${encodeURIComponent(token)}`;
}

export default async function PublicQuotePage({ params, searchParams }: RouteParams): Promise<JSX.Element> {
  const quoteId = String(params.quoteId || "").trim();
  const token = readParam(searchParams, "t").trim();
  const ok = readParam(searchParams, "ok").trim();
  const error = readParam(searchParams, "error").trim();

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
  const language = normalizeUiLanguage(payload?.quote.language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const canAct = payload ? ["sent", "change_requested"].includes(payload.quote.status) : false;
  const selfPath = buildSelfPath(quoteId, token);

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
                    <strong>{formatDate(payload.quote.expires_at, language)}</strong>
                  </article>
                </div>
              </article>

              <article className="card quote-public-lines-card">
                <h3>{t("quote_public.document_title")}</h3>
                {documentPayload ? (
                  <div className="top-gap-sm" dangerouslySetInnerHTML={{ __html: documentPayload.combined_html }} />
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
              <Link className="ghost quote-public-action" href={`/q/${payload.quote.id}/pdf?t=${encodeURIComponent(payload.quote.pdf_token)}`} target="_blank">
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
                  <button type="submit" className="quote-cta-success">{t("quote_public.approve_cta")}</button>
                </form>

                <form action={rejectPublicQuoteAction} className="quote-public-form-action top-gap-sm">
                  <input type="hidden" name="quote_id" value={quoteId} />
                  <input type="hidden" name="public_token" value={token} />
                  <input type="hidden" name="return_to" value={selfPath} />
                  <input type="hidden" name="language" value={language} />
                  <button type="submit" className="quote-cta-danger">{t("quote_public.reject_cta")}</button>
                </form>

                <form action={changeRequestPublicQuoteAction} className="quote-public-change-request top-gap-sm">
                  <input type="hidden" name="quote_id" value={quoteId} />
                  <input type="hidden" name="public_token" value={token} />
                  <input type="hidden" name="return_to" value={selfPath} />
                  <input type="hidden" name="language" value={language} />
                  <label>
                    {t("quote_public.change_request_label")}
                    <textarea
                      name="change_message"
                      required
                      rows={4}
                      placeholder={t("quote_public.change_request_placeholder")}
                    />
                  </label>
                  <button type="submit" className="ghost">{t("quote_public.change_request_submit")}</button>
                </form>
              </>
            ) : (
              <p className="muted top-gap-sm">{t("quote_public.no_actions")}</p>
            )}
          </article>
        </aside>
      </section>

      {canAct ? (
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
