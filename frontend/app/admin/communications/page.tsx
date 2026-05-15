import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { resendCommunicationAction } from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import type {
  CommunicationFiltersOut,
  CommunicationPeriod,
  CommunicationReportPageOut,
  CommunicationReportRow,
  UserOut,
} from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;
type ChannelFilter = "ALL" | "EMAIL" | "SMS";
type PerPage = 25 | 50 | 100;
const ADMIN_COMMUNICATION_TIMEZONE = "Europe/Paris";

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function parseChannel(value: string): ChannelFilter {
  if (value === "EMAIL" || value === "SMS") {
    return value;
  }
  return "ALL";
}

function parsePeriod(value: string): CommunicationPeriod {
  if (
    value === "TODAY" ||
    value === "WEEK" ||
    value === "MONTH" ||
    value === "SEMESTER" ||
    value === "YEAR" ||
    value === "ALL"
  ) {
    return value;
  }
  return "TODAY";
}

function parsePerPage(value: string): PerPage {
  if (value === "25") {
    return 25;
  }
  if (value === "100") {
    return 100;
  }
  return 50;
}

function parsePage(value: string): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return 1;
  }
  return parsed;
}

function formatDate(value: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString(localeForUiLanguage(language), {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: ADMIN_COMMUNICATION_TIMEZONE,
  });
}

function deliveryLabel(value: CommunicationReportRow["delivery_status"], language: UiLanguage): string {
  if (value === "DELIVERED") {
    return uiText(language, "admin.communications.delivery_delivered");
  }
  if (value === "SENT") {
    return uiText(language, "admin.communications.delivery_sent");
  }
  if (value === "FAILED") {
    return uiText(language, "admin.communications.delivery_failed");
  }
  if (value === "PENDING") {
    return uiText(language, "admin.communications.delivery_pending");
  }
  if (value === "SKIPPED") {
    return uiText(language, "admin.communications.delivery_skipped");
  }
  return uiText(language, "admin.communications.delivery_unknown");
}

function senderCategoryLabel(value: CommunicationReportRow["sender_category"], language: UiLanguage): string {
  if (value === "PROFESSOR") {
    return uiText(language, "admin.communications.sender_professor");
  }
  if (value === "SYSTEM") {
    return uiText(language, "admin.communications.sender_system");
  }
  return uiText(language, "admin.communications.sender_other");
}

function channelLabel(value: CommunicationReportRow["channel"], language: UiLanguage): string {
  return value === "SMS" ? uiText(language, "common.sms") : uiText(language, "common.email");
}

function periodLabel(value: CommunicationPeriod, language: UiLanguage): string {
  if (value === "TODAY") {
    return uiText(language, "admin.communications.period_today");
  }
  if (value === "WEEK") {
    return uiText(language, "admin.communications.period_week");
  }
  if (value === "MONTH") {
    return uiText(language, "admin.communications.period_month");
  }
  if (value === "SEMESTER") {
    return uiText(language, "admin.communications.period_semester");
  }
  if (value === "YEAR") {
    return uiText(language, "admin.communications.period_year");
  }
  return uiText(language, "admin.communications.period_all");
}

type CommunicationFiltersState = {
  channel: ChannelFilter;
  q: string;
  communicationType: string;
  period: CommunicationPeriod;
  professorId: string;
  messageId: string;
  page: number;
  perPage: PerPage;
};

function buildHref(filters: CommunicationFiltersState, overrides?: Partial<CommunicationFiltersState>): string {
  const next: CommunicationFiltersState = { ...filters, ...(overrides ?? {}) };
  const params = new URLSearchParams();
  if (next.channel !== "ALL") {
    params.set("channel", next.channel);
  }
  if (next.q) {
    params.set("q", next.q);
  }
  if (next.communicationType) {
    params.set("communication_type", next.communicationType);
  }
  if (next.period !== "TODAY") {
    params.set("period", next.period);
  }
  if (next.professorId) {
    params.set("professor_id", next.professorId);
  }
  if (next.messageId) {
    params.set("message_id", next.messageId);
  }
  if (next.page > 1) {
    params.set("page", String(next.page));
  }
  if (next.perPage !== 50) {
    params.set("per_page", String(next.perPage));
  }
  const query = params.toString();
  return query ? `/admin/communications?${query}` : "/admin/communications";
}

function buildApiHref(filters: CommunicationFiltersState): string {
  const params = new URLSearchParams();
  if (filters.channel !== "ALL") {
    params.set("channel", filters.channel);
  }
  params.set("period", filters.period);
  params.set("page", String(filters.page));
  params.set("per_page", String(filters.perPage));
  if (filters.q) {
    params.set("q", filters.q);
  }
  if (filters.communicationType) {
    params.set("communication_type", filters.communicationType);
  }
  if (filters.professorId) {
    params.set("professor_id", filters.professorId);
  }
  return `/api/v1/admin/reports/communications?${params.toString()}`;
}

export default async function AdminCommunicationsPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const channel = parseChannel(readParam(searchParams, "channel"));
  const selectedMessageId = readParam(searchParams, "message_id");
  const q = readParam(searchParams, "q");
  const communicationType = readParam(searchParams, "communication_type");
  const period = parsePeriod(readParam(searchParams, "period"));
  const professorId = readParam(searchParams, "professor_id");
  const page = parsePage(readParam(searchParams, "page"));
  const perPage = parsePerPage(readParam(searchParams, "per_page"));
  const flashError = readParam(searchParams, "error");
  const flashOk = readParam(searchParams, "ok");

  const filters: CommunicationFiltersState = {
    channel,
    q,
    communicationType,
    period,
    professorId,
    messageId: selectedMessageId,
    page,
    perPage,
  };

  const dataResult = await backendRequest<CommunicationReportPageOut>(buildApiHref(filters), {}, token);
  const filterQuery = new URLSearchParams();
  if (channel !== "ALL") {
    filterQuery.set("channel", channel);
  }
  const filtersResult = await backendRequest<CommunicationFiltersOut>(
    `/api/v1/admin/reports/communications/filters?${filterQuery.toString()}`,
    {},
    token,
  );

  const pageData: CommunicationReportPageOut = dataResult.ok
    ? dataResult.data
    : { items: [], page: 1, per_page: perPage, total: 0, total_pages: 1 };
  const rows = pageData.items;
  const selected = selectedMessageId ? rows.find((row) => row.id === selectedMessageId) ?? null : null;
  const closeDetailHref = buildHref(filters, { messageId: "" });
  const resetHref = buildHref({
    ...filters,
    channel: "ALL",
    q: "",
    communicationType: "",
    period: "TODAY",
    professorId: "",
    messageId: "",
    page: 1,
    perPage: 50,
  });
  const communicationTypeOptions = filtersResult.ok ? filtersResult.data.communication_types : [];
  const professorOptions = filtersResult.ok ? filtersResult.data.professors : [];

  const previousPageHref = buildHref(filters, { page: Math.max(1, pageData.page - 1), messageId: "" });
  const nextPageHref = buildHref(filters, { page: Math.min(pageData.total_pages, pageData.page + 1), messageId: "" });

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h2>{t("admin.communications.title")}</h2>
        <p className="muted">{t("admin.communications.subtitle")}</p>
      </section>

      <section className="card">
        {flashError ? <p className="flash-err top-gap-sm">{flashError}</p> : null}
        {flashOk ? <p className="flash-ok top-gap-sm">{flashOk}</p> : null}
        {!dataResult.ok ? <p className="flash-err top-gap-sm">{t("admin.communications.backend_error")}: {dataResult.message}</p> : null}
        {!filtersResult.ok ? <p className="flash-err top-gap-sm">{t("admin.communications.filters_error")}: {filtersResult.message}</p> : null}
      </section>

      <section className="card">
        <form method="get" className="grid cols-4">
          <label className="stack-sm">
            {t("admin.communications.search")}
            <input type="text" name="q" defaultValue={q} placeholder={t("admin.communications.search_placeholder")} />
          </label>
          <label className="stack-sm">
            {t("admin.communications.channel")}
            <select name="channel" defaultValue={channel}>
              <option value="ALL">{t("common.all")}</option>
              <option value="EMAIL">{t("admin.communications.channel_email_plural")}</option>
              <option value="SMS">{t("common.sms")}</option>
            </select>
          </label>
          <label className="stack-sm">
            {t("admin.communications.communication_type")}
            <select name="communication_type" defaultValue={communicationType || ""}>
              <option value="">{t("common.all")}</option>
              {communicationTypeOptions.map((option) => (
                <option key={option.code} value={option.code}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="stack-sm">
            {t("common.period")}
            <select name="period" defaultValue={period}>
              <option value="TODAY">{t("admin.communications.period_option_today")}</option>
              <option value="WEEK">{t("admin.communications.period_option_week")}</option>
              <option value="MONTH">{t("admin.communications.period_option_month")}</option>
              <option value="SEMESTER">{t("admin.communications.period_option_semester")}</option>
              <option value="YEAR">{t("admin.communications.period_option_year")}</option>
              <option value="ALL">{t("admin.communications.period_option_all")}</option>
            </select>
          </label>
          <label className="stack-sm">
            {t("admin.communications.professor")}
            <select name="professor_id" defaultValue={professorId || ""}>
              <option value="">{t("common.all")}</option>
              {professorOptions.map((professor) => (
                <option key={professor.id} value={professor.id}>
                  {professor.label}
                </option>
              ))}
            </select>
          </label>
          <label className="stack-sm">
            {t("admin.communications.messages_per_page")}
            <select name="per_page" defaultValue={String(perPage)}>
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
          </label>
          <input type="hidden" name="page" value="1" />
          <div className="row">
            <button type="submit">{t("common.apply")}</button>
            <a className="mode-link" href={resetHref}>
              {t("common.reset")}
            </a>
          </div>
        </form>
        <p className="muted">
          {t("admin.communications.default_display_note")}
        </p>
      </section>

      <section className="card row" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <p className="muted">
          {t("admin.communications.total_messages_period", { count: pageData.total, period: periodLabel(period, language) })}
        </p>
        <div className="row">
          <a className={`mode-link ${pageData.page <= 1 ? "disabled" : ""}`} href={pageData.page <= 1 ? "#" : previousPageHref}>
            ← {t("common.previous")}
          </a>
          <span className="muted">
            {t("common.page")} {pageData.page} / {pageData.total_pages}
          </span>
          <a
            className={`mode-link ${pageData.page >= pageData.total_pages ? "disabled" : ""}`}
            href={pageData.page >= pageData.total_pages ? "#" : nextPageHref}
          >
            {t("common.next")} →
          </a>
        </div>
      </section>

      <section className="card table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t("admin.communications.column_datetime")}</th>
              <th>{t("admin.communications.channel")}</th>
              <th>{t("admin.communications.sender")}</th>
              <th>{t("admin.communications.communication_type")}</th>
              <th>{t("admin.communications.subject")}</th>
              <th>{t("admin.communications.recipient")}</th>
              <th>{t("admin.communications.delivery_status")}</th>
              <th>{t("client.action")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={8}>
                  <p className="muted">{t("admin.communications.no_results")}</p>
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.id}>
                  <td>{formatDate(row.occurred_at, language)}</td>
                  <td>{channelLabel(row.channel, language)}</td>
                  <td>
                    <strong>{row.sender_label}</strong>
                    <div className="muted">{senderCategoryLabel(row.sender_category, language)}</div>
                  </td>
                  <td>{row.communication_type_label}</td>
                  <td>{row.subject}</td>
                  <td>{row.recipient}</td>
                  <td>
                    <span className="badge">{deliveryLabel(row.delivery_status, language)}</span>
                  </td>
                  <td>
                    <div className="row wrap gap-sm">
                      <a className="mode-link" href={buildHref(filters, { messageId: row.id })}>
                        {t("common.view")}
                      </a>
                      {row.channel === "EMAIL" ? (
                        <form action={resendCommunicationAction}>
                          <input type="hidden" name="communication_id" value={row.id} />
                          <input type="hidden" name="recipient_email" value={row.recipient} />
                          <input type="hidden" name="return_to" value={buildHref(filters, { messageId: row.id })} />
                          <button type="submit" className="ghost">{t("admin.communications.resend")}</button>
                        </form>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      {selected ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <a className="modal-close-x" href={closeDetailHref} aria-label={t("common.close")}>
              ×
            </a>
            <h2 className="modal-title">{t("admin.communications.detail_title")}</h2>
            <p className="muted">
              {channelLabel(selected.channel, language)} | {selected.source}
            </p>
            <p>
              <strong>{t("admin.communications.detail_date")}:</strong> {formatDate(selected.occurred_at, language)}
            </p>
            <p>
              <strong>{t("admin.communications.detail_sender")}:</strong> {selected.sender_label} ({senderCategoryLabel(selected.sender_category, language)})
            </p>
            <p>
              <strong>{t("admin.communications.detail_type")}:</strong> {selected.communication_type_label}
            </p>
            <p>
              <strong>{t("admin.communications.detail_recipient")}:</strong> {selected.recipient}
            </p>
            <p>
              <strong>{t("admin.communications.detail_subject")}:</strong> {selected.subject}
            </p>
            <p>
              <strong>{t("admin.communications.detail_status")}:</strong> {deliveryLabel(selected.delivery_status, language)}
            </p>
            {selected.provider ? (
              <p>
                <strong>{t("admin.communications.detail_provider")}:</strong> {selected.provider}
              </p>
            ) : null}
            {selected.provider_message_id ? (
              <p>
                <strong>{t("admin.communications.detail_provider_message_id")}:</strong> {selected.provider_message_id}
              </p>
            ) : null}
            {selected.error_message ? (
              <p>
                <strong>{t("admin.communications.detail_provider_error")}:</strong> {selected.error_message}
              </p>
            ) : null}
            {flashError ? <p className="flash-err top-gap-sm">{flashError}</p> : null}
            {flashOk ? <p className="flash-ok top-gap-sm">{flashOk}</p> : null}
            {selected.provider === "LOG" ? (
              <p className="flash-err top-gap-sm">
                {t("admin.communications.log_only_warning")}
              </p>
            ) : null}

            {selected.channel === "EMAIL" ? (
              <div className="row wrap gap-sm top-gap-sm">
                <form action={resendCommunicationAction} className="row wrap gap-sm">
                  <input type="hidden" name="communication_id" value={selected.id} />
                  <input type="hidden" name="return_to" value={buildHref(filters, { messageId: selected.id })} />
                  <input type="email" name="recipient_email" defaultValue={selected.recipient} />
                  <button type="submit">{t("admin.communications.resend_email")}</button>
                </form>
              </div>
            ) : null}

            <h3>{t("admin.communications.content")}</h3>
            {selected.content_format === "HTML" ? (
              <div className="card modal-card">
                <div dangerouslySetInnerHTML={{ __html: selected.content }} />
              </div>
            ) : (
              <pre className="message-body-preview">{selected.content}</pre>
            )}
          </article>
        </section>
      ) : null}
    </section>
  );
}
