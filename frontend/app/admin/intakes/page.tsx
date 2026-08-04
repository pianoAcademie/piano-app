import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import ConfirmSubmitButton from "../../../components/confirm-submit-button";
import {
  deleteTypeformIntakeAction,
  ignoreTypeformIntakeAction,
  restoreTypeformIntakeAction,
  seedTypeformDemoAction,
} from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import { hasAdminPermission } from "../../../lib/admin-access";
import type { UserOut } from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../lib/ui-i18n";
import styles from "./typeform-intakes.module.css";

type SearchParams = Record<string, string | string[] | undefined>;

type TypeformIntakeListOut = {
  id: string;
  source_form_id: string;
  source_form_label: string;
  source_response_id: string;
  received_at: string;
  intake_status: string;
  detected_location: string | null;
  detected_segment: string | null;
  detected_school_year: string | null;
  prospect_label: string | null;
  child_label: string | null;
  warnings: string[];
  blockages: string[];
  admin_comment: string | null;
  related_quote_id: string | null;
  local_confirmation_status: string;
  local_confirmation_assignee_name: string | null;
  local_confirmation_schedule_snapshot: string | null;
  local_confirmation_partition_snapshot: string | null;
  local_confirmation_confirmed_at: string | null;
};

type TypeformIntakeListPageOut = {
  items: TypeformIntakeListOut[];
  total: number;
  page: number;
  page_size: number;
};

const DEFAULT_PAGE = 1;
const PAGE_SIZE_OPTIONS = [25, 50, 100] as const;
const DEFAULT_PAGE_SIZE = 50;
const DEFAULT_EXCLUDE_PROCESSED = true;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function readPositiveIntParam(params: SearchParams, key: string, fallback: number): number {
  const raw = readParam(params, key).trim();
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return fallback;
  }
  return parsed;
}

function readPageSizeParam(params: SearchParams): number {
  const value = readPositiveIntParam(params, "page_size", DEFAULT_PAGE_SIZE);
  if (PAGE_SIZE_OPTIONS.includes(value as (typeof PAGE_SIZE_OPTIONS)[number])) {
    return value;
  }
  return DEFAULT_PAGE_SIZE;
}

function readBooleanParam(params: SearchParams, key: string): boolean {
  const value = readParam(params, key).trim().toLowerCase();
  return value === "1" || value === "true" || value === "on" || value === "yes";
}

function readBooleanParamWithDefault(params: SearchParams, key: string, fallback: boolean): boolean {
  const raw = readParam(params, key).trim();
  if (!raw) {
    return fallback;
  }
  const value = raw.toLowerCase();
  if (value === "0" || value === "false" || value === "off" || value === "no") {
    return false;
  }
  return value === "1" || value === "true" || value === "on" || value === "yes";
}

function safeStatus(raw: string): string {
  const value = raw.trim().toUpperCase();
  if (
    value === "NEW"
    || value === "NORMALIZED"
    || value === "MATCHING_REQUIRED"
    || value === "READY_FOR_DRAFT_QUOTE"
    || value === "BLOCKED"
    || value === "PROCESSED"
    || value === "IGNORED"
  ) {
    return value;
  }
  return "";
}

function formatDate(value: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString(localeForUiLanguage(language), { dateStyle: "short", timeStyle: "short" });
}

function statusLabel(value: string, language: UiLanguage): string {
  if (value === "NEW") return uiText(language, "admin.intakes.status_new");
  if (value === "NORMALIZED") return uiText(language, "admin.intakes.status_normalized");
  if (value === "MATCHING_REQUIRED") return uiText(language, "admin.intakes.status_matching_required");
  if (value === "READY_FOR_DRAFT_QUOTE") return uiText(language, "admin.intakes.status_ready_draft");
  if (value === "BLOCKED") return uiText(language, "admin.intakes.status_blocked");
  if (value === "PROCESSED") return uiText(language, "admin.intakes.status_processed");
  if (value === "IGNORED") return uiText(language, "admin.intakes.status_ignored");
  return value;
}

function statusClass(value: string): string {
  if (value === "READY_FOR_DRAFT_QUOTE" || value === "PROCESSED") {
    return "status-ok";
  }
  if (value === "MATCHING_REQUIRED" || value === "NEW" || value === "NORMALIZED") {
    return "status-warn";
  }
  return "status-off";
}

function segmentLabel(value: string | null, language: UiLanguage): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "eveil") return uiText(language, "admin.intakes.segment_eveil");
  if (normalized === "child") return uiText(language, "admin.intakes.segment_child");
  if (normalized === "teen") return uiText(language, "admin.intakes.segment_teen");
  if (normalized === "adult") return uiText(language, "admin.intakes.segment_adult");
  return value || "-";
}

function compactList(values: string[]): string {
  if (values.length === 0) {
    return "-";
  }
  if (values.length === 1) {
    return values[0] || "-";
  }
  return `${values[0]} (+${values.length - 1})`;
}

function buildIntakesHref({
  q,
  status,
  includeIgnored,
  excludeProcessed,
  page,
  pageSize,
}: {
  q: string;
  status: string;
  includeIgnored?: boolean;
  excludeProcessed?: boolean;
  page?: number;
  pageSize?: number;
}): string {
  const params = new URLSearchParams();
  if (q) {
    params.set("q", q);
  }
  if (status) {
    params.set("status", status);
  }
  if (includeIgnored) {
    params.set("include_ignored", "1");
  }
  if ((excludeProcessed ?? DEFAULT_EXCLUDE_PROCESSED) !== DEFAULT_EXCLUDE_PROCESSED) {
    params.set("exclude_processed", excludeProcessed ? "1" : "0");
  } else if (excludeProcessed && !DEFAULT_EXCLUDE_PROCESSED) {
    params.set("exclude_processed", "1");
  }
  if ((page ?? DEFAULT_PAGE) > DEFAULT_PAGE) {
    params.set("page", String(page));
  }
  if ((pageSize ?? DEFAULT_PAGE_SIZE) !== DEFAULT_PAGE_SIZE) {
    params.set("page_size", String(pageSize));
  }
  const search = params.toString();
  return search ? `/admin/intakes?${search}` : "/admin/intakes";
}

function IntakePaginationControls({
  q,
  status,
  includeIgnored,
  excludeProcessed,
  total,
  currentPage,
  totalPages,
  pageSize,
  pageStart,
  language,
}: {
  q: string;
  status: string;
  includeIgnored: boolean;
  excludeProcessed: boolean;
  total: number;
  currentPage: number;
  totalPages: number;
  pageSize: number;
  pageStart: number;
  language: UiLanguage;
}): JSX.Element {
  const previousPageHref = buildIntakesHref({ q, status, includeIgnored, excludeProcessed, page: currentPage - 1, pageSize });
  const nextPageHref = buildIntakesHref({ q, status, includeIgnored, excludeProcessed, page: currentPage + 1, pageSize });
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  return (
    <div className="row spread wrap clients-pagination top-gap-sm">
      <div className="row wrap gap-sm">
        <small className="muted">
          {t("admin.intakes.pagination_summary", {
            start: total === 0 ? 0 : pageStart + 1,
            end: Math.min(pageStart + pageSize, total),
            total,
          })}
        </small>
        <form method="get" className="row wrap gap-sm">
          {q ? <input type="hidden" name="q" value={q} /> : null}
          {status ? <input type="hidden" name="status" value={status} /> : null}
          {includeIgnored ? <input type="hidden" name="include_ignored" value="1" /> : null}
          <input type="hidden" name="exclude_processed" value={excludeProcessed ? "1" : "0"} />
          <label className="row gap-sm">
            <span className="muted">{uiText(language, "common.per_page")}</span>
            <select name="page_size" defaultValue={String(pageSize)}>
              {PAGE_SIZE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className="ghost">{uiText(language, "common.apply")}</button>
        </form>
      </div>
      <div className="row">
        {currentPage > 1 ? (
          <Link className="mode-link" href={previousPageHref}>
            ← {uiText(language, "common.previous")}
          </Link>
        ) : (
          <span className="mode-link disabled-link">← {uiText(language, "common.previous")}</span>
        )}
        <span className="badge">
          {uiText(language, "common.page")} {currentPage}/{totalPages}
        </span>
        {currentPage < totalPages ? (
          <Link className="mode-link" href={nextPageHref}>
            {uiText(language, "common.next")} →
          </Link>
        ) : (
          <span className="mode-link disabled-link">{uiText(language, "common.next")} →</span>
        )}
      </div>
    </div>
  );
}

export default async function AdminTypeformIntakesPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || !hasAdminPermission(meResult.data, "can_view_intakes")) {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const q = readParam(searchParams, "q").trim();
  const status = safeStatus(readParam(searchParams, "status"));
  const includeIgnored = readBooleanParam(searchParams, "include_ignored");
  const excludeProcessed = readBooleanParamWithDefault(searchParams, "exclude_processed", DEFAULT_EXCLUDE_PROCESSED);
  const requestedPage = readPositiveIntParam(searchParams, "page", DEFAULT_PAGE);
  const requestedPageSize = readPageSizeParam(searchParams);
  const ok = readParam(searchParams, "ok").trim();
  const error = readParam(searchParams, "error").trim();

  const query = new URLSearchParams();
  if (q) query.set("q", q);
  if (status) query.set("status", status);
  if (includeIgnored) query.set("include_ignored", "1");
  if (excludeProcessed) query.set("exclude_processed", "1");
  query.set("page", String(requestedPage));
  query.set("page_size", String(requestedPageSize));

  const result = await backendRequest<TypeformIntakeListPageOut>(
    `/api/v1/typeform/intakes?${query.toString()}`,
    {},
    token,
  );
  const pageData = result.ok
    ? result.data
    : { items: [], total: 0, page: DEFAULT_PAGE, page_size: DEFAULT_PAGE_SIZE };
  const rows = pageData.items;
  const total = pageData.total;
  const currentPage = pageData.page;
  const pageSize = pageData.page_size;
  const totalPages = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));
  const pageStart = total === 0 ? 0 : (currentPage - 1) * pageSize;
  const returnTo = buildIntakesHref({ q, status, includeIgnored, excludeProcessed, page: currentPage, pageSize });
  const intakeStats = {
    visible: rows.length,
    toReview: rows.filter((row) => ["NEW", "NORMALIZED", "MATCHING_REQUIRED"].includes(row.intake_status)).length,
    readyForQuote: rows.filter((row) => row.intake_status === "READY_FOR_DRAFT_QUOTE").length,
    blocked: rows.filter((row) => row.intake_status === "BLOCKED" || row.blockages.length > 0).length,
    withQuote: rows.filter((row) => Boolean(row.related_quote_id)).length,
  };

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>{t("admin.intakes.title")}</h2>
            <p className="muted">{t("admin.intakes.subtitle")}</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href="/admin/quotes">{t("admin.intakes.open_quote")}</Link>
            <Link className="ghost" href="/admin/prospects">{uiText(language, "admin.nav.prospects")}</Link>
            <form action={seedTypeformDemoAction}>
              <input type="hidden" name="return_to" value="/admin/intakes" />
              <button type="submit">{t("admin.intakes.load_demo")}</button>
            </form>
          </div>
        </div>
      </section>

      {!result.ok ? <section className="flash-err">{t("admin.intakes.backend_error")}: {result.message}</section> : null}
      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}

      <section className="card">
        <div className="config-metric-grid">
          <article>
            <span>{t("admin.intakes.metrics_visible")}</span>
            <strong>{intakeStats.visible}</strong>
          </article>
          <article className={intakeStats.toReview > 0 ? "is-warning" : ""}>
            <span>{t("admin.intakes.metrics_to_review")}</span>
            <strong>{intakeStats.toReview}</strong>
          </article>
          <article>
            <span>{t("admin.intakes.metrics_ready_quote")}</span>
            <strong>{intakeStats.readyForQuote}</strong>
          </article>
          <article className={intakeStats.blocked > 0 ? "is-warning" : ""}>
            <span>{t("admin.intakes.metrics_blocked")}</span>
            <strong>{intakeStats.blocked}</strong>
          </article>
          <article>
            <span>{t("admin.intakes.metrics_with_quote")}</span>
            <strong>{intakeStats.withQuote}</strong>
          </article>
        </div>
      </section>

      <section className="card">
        <form method="get" className="admin-list-filter-form">
          <div className="admin-list-filter-primary">
            <label>
              {uiText(language, "common.search")}
              <input type="search" name="q" defaultValue={q} placeholder={t("admin.intakes.search_placeholder")} enterKeyHint="search" />
            </label>
            <label>
              {uiText(language, "common.status")}
              <select name="status" defaultValue={status}>
                <option value="">{uiText(language, "common.all")}</option>
                <option value="NEW">{t("admin.intakes.status_new")}</option>
                <option value="NORMALIZED">{t("admin.intakes.status_normalized")}</option>
                <option value="MATCHING_REQUIRED">{t("admin.intakes.status_matching_required")}</option>
                <option value="READY_FOR_DRAFT_QUOTE">{t("admin.intakes.status_ready_draft")}</option>
                <option value="BLOCKED">{t("admin.intakes.status_blocked")}</option>
                <option value="PROCESSED">{t("admin.intakes.status_processed")}</option>
                <option value="IGNORED">{t("admin.intakes.status_ignored")}</option>
              </select>
            </label>
            <div className="admin-list-filter-actions">
              <button type="submit">{uiText(language, "common.apply")}</button>
              <Link className="ghost" href="/admin/intakes">{uiText(language, "common.reset")}</Link>
            </div>
          </div>
          <details className="admin-filter-disclosure">
            <summary>{language === "en" ? "Advanced filters" : "Filtres avances"}</summary>
            <div className="admin-filter-disclosure-content">
              <label>
                {uiText(language, "common.per_page")}
                <select name="page_size" defaultValue={String(pageSize)}>
                  {PAGE_SIZE_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
              </label>
              <label className="row gap-sm">
                <input type="checkbox" name="include_ignored" value="1" defaultChecked={includeIgnored} />
                <span>{t("admin.intakes.include_ignored")}</span>
              </label>
              <label className="row gap-sm">
                <input type="checkbox" name="exclude_processed" value="1" defaultChecked={excludeProcessed} />
                <span>{t("admin.intakes.exclude_processed")}</span>
              </label>
              <input type="hidden" name="exclude_processed" value="0" />
            </div>
          </details>
        </form>
      </section>

      <section className="card">
        <div className="row spread wrap gap-sm">
          <h3>{t("admin.intakes.table_title")}</h3>
          <p className="muted">{t("admin.intakes.records_count", { count: total })}</p>
        </div>
        {rows.length === 0 ? (
          <div className={`${styles.emptyState} top-gap-sm`}>
            <p className="muted">{t("admin.intakes.empty_message")}</p>
            <form action={seedTypeformDemoAction} className="row gap-sm">
              <input type="hidden" name="return_to" value="/admin/intakes" />
              <button type="submit">{t("admin.intakes.install_demo")}</button>
            </form>
          </div>
        ) : (
          <>
            <IntakePaginationControls
              q={q}
              status={status}
              total={total}
              currentPage={currentPage}
              totalPages={totalPages}
              pageSize={pageSize}
              pageStart={pageStart}
              includeIgnored={includeIgnored}
              excludeProcessed={excludeProcessed}
              language={language}
            />
            <div className="table-wrap top-gap-sm admin-table-card-wrap">
            <table className="data-table admin-responsive-table">
              <thead>
                <tr>
                  <th>{uiText(language, "common.date")}</th>
                  <th>{t("admin.intakes.source_form")}</th>
                  <th>{t("admin.intakes.prospect")}</th>
                  <th>{uiText(language, "client.child")}</th>
                  <th>{uiText(language, "common.site")}</th>
                  <th>{t("admin.intakes.segment")}</th>
                  <th>{uiText(language, "common.status")}</th>
                  <th>{language === "fr" ? "Commentaire admin" : "Admin comment"}</th>
                  <th>{uiText(language, "common.warnings")}</th>
                  <th>{uiText(language, "common.blockages")}</th>
                  <th>{uiText(language, "client.action")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td data-mobile-label={uiText(language, "common.date")}>{formatDate(row.received_at, language)}</td>
                    <td data-mobile-hidden="true">
                      <strong>{row.source_form_label}</strong>
                      <div className="muted">{row.source_form_id}</div>
                    </td>
                    <td data-mobile-label="" className="mobile-row-primary">{row.prospect_label || "-"}</td>
                    <td data-mobile-label={uiText(language, "client.child")}>{row.child_label || "-"}</td>
                    <td data-mobile-label={uiText(language, "common.site")}>{row.detected_location || "-"}</td>
                    <td data-mobile-label={t("admin.intakes.segment")}>{segmentLabel(row.detected_segment, language)}</td>
                    <td data-mobile-label={uiText(language, "common.status")}>
                      <span className={`status-pill ${statusClass(row.intake_status)}`}>{statusLabel(row.intake_status, language)}</span>
                      {row.local_confirmation_status !== "NOT_REQUIRED" ? (
                        <div className="top-gap-xs">
                          <span className={`status-pill ${row.local_confirmation_status === "CONFIRMED" ? "status-ok" : "status-warn"}`}>
                            {row.local_confirmation_status === "CONFIRMED"
                              ? "Confirmé par Bar-le-Duc"
                              : "En attente de confirmation Bar-le-Duc"}
                          </span>
                        </div>
                      ) : null}
                    </td>
                    <td data-mobile-label={language === "fr" ? "Commentaire" : "Comment"}>
                      {row.admin_comment ? (
                        <p className={styles.adminCommentPreview}>{row.admin_comment}</p>
                      ) : (
                        <span className="muted">-</span>
                      )}
                    </td>
                    <td data-mobile-hidden="true">{compactList(row.warnings)}</td>
                    <td data-mobile-label={uiText(language, "common.blockages")}>{compactList(row.blockages)}</td>
                    <td data-mobile-label={uiText(language, "client.action")}>
                      <div className="row wrap gap-sm">
                        <Link className="ghost" href={`/admin/intakes/${encodeURIComponent(row.id)}`}>{uiText(language, "common.open")}</Link>
                        {row.related_quote_id ? (
                          <Link className="ghost" href={`/admin/quotes/${encodeURIComponent(row.related_quote_id)}`}>{t("admin.intakes.open_quote")}</Link>
                        ) : null}
                        {!row.related_quote_id && row.intake_status !== "IGNORED" ? (
                          <form action={ignoreTypeformIntakeAction}>
                            <input type="hidden" name="intake_id" value={row.id} />
                            <input type="hidden" name="return_to" value={returnTo} />
                            <button type="submit" className="ghost">{t("admin.intakes.ignore")}</button>
                          </form>
                        ) : null}
                        {!row.related_quote_id && row.intake_status === "IGNORED" ? (
                          <form action={restoreTypeformIntakeAction}>
                            <input type="hidden" name="intake_id" value={row.id} />
                            <input type="hidden" name="return_to" value={returnTo} />
                            <button type="submit" className="ghost">{t("admin.intakes.resume")}</button>
                          </form>
                        ) : null}
                        {!row.related_quote_id ? (
                          <form id={`delete-intake-${row.id}`} action={deleteTypeformIntakeAction}>
                            <input type="hidden" name="intake_id" value={row.id} />
                            <input type="hidden" name="return_to" value={returnTo} />
                            <ConfirmSubmitButton
                              formId={`delete-intake-${row.id}`}
                              label={uiText(language, "common.delete")}
                              title={t("admin.intakes.delete_title")}
                              description={t("admin.intakes.delete_description")}
                              confirmLabel={t("admin.intakes.delete_confirm")}
                              cancelLabel={uiText(language, "common.cancel")}
                              closeAriaLabel={uiText(language, "common.close")}
                              missingFormError={uiText(language, "common.form_not_found")}
                              className="danger ghost"
                            />
                          </form>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </>
        )}
        {total > 0 ? (
            <IntakePaginationControls
              q={q}
              status={status}
              total={total}
              currentPage={currentPage}
              totalPages={totalPages}
              pageSize={pageSize}
              pageStart={pageStart}
              includeIgnored={includeIgnored}
              excludeProcessed={excludeProcessed}
              language={language}
            />
          ) : null}
      </section>
    </section>
  );
}
