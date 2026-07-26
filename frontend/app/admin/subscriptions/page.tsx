import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest, backendUrl } from "../../../lib/backend";
import type { AdminSubscriptionEngineDetailOut, AdminSubscriptionEngineListOut, UserOut } from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, translateBackendMessage, type UiLanguage, uiText } from "../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

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
  return parsed.toLocaleString(localeForUiLanguage(language), { dateStyle: "short", timeStyle: "short" });
}

function formatAmount(value: string | null, currency: string | null, language: UiLanguage): string {
  if (!value) {
    return "-";
  }
  const amount = Number(value);
  if (!Number.isFinite(amount)) {
    return `${value} ${currency ?? ""}`.trim();
  }
  const safeCurrency = (currency ?? "EUR").toUpperCase();
  try {
    return new Intl.NumberFormat(localeForUiLanguage(language), {
      style: "currency",
      currency: safeCurrency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${safeCurrency}`;
  }
}

function statusClass(status: string): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "ACTIVE" || normalized === "PAID") {
    return "status-ok";
  }
  if (normalized === "REFUNDED") {
    return "status-off";
  }
  if (normalized === "PAYMENT_ALERT" || normalized === "FAILED_FIRST_ATTEMPT") {
    return "status-warn";
  }
  if (normalized === "PRE_TERMINATION" || normalized === "TERMINATED" || normalized === "FAILED_FINAL") {
    return "status-cancelled";
  }
  return "status-off";
}

function subscriptionStatusLabel(status: string, language: UiLanguage): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "ACTIVE") return uiText(language, "admin.subscriptions.status_active");
  if (normalized === "PAYMENT_ALERT") return uiText(language, "admin.subscriptions.status_payment_alert");
  if (normalized === "PRE_TERMINATION") return uiText(language, "admin.subscriptions.status_pre_termination");
  if (normalized === "TERMINATED") return uiText(language, "admin.subscriptions.status_terminated");
  if (normalized === "PAUSED") return uiText(language, "admin.subscriptions.status_paused");
  if (normalized === "CANCELLED") return uiText(language, "admin.subscriptions.status_cancelled");
  if (normalized === "PAID") return uiText(language, "admin.subscriptions.status_paid");
  if (normalized === "FAILED_FIRST_ATTEMPT") return uiText(language, "admin.subscriptions.status_failed_first_attempt");
  if (normalized === "FAILED_FINAL") return uiText(language, "admin.subscriptions.status_failed_final");
  if (normalized === "REFUNDED") return uiText(language, "admin.subscriptions.status_refunded");
  return status;
}

function readLanguageFromFormData(formData: FormData): UiLanguage {
  return normalizeUiLanguage(String(formData.get("ui_language") ?? ""));
}

async function retryNowAction(formData: FormData): Promise<void> {
  "use server";

  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  const language = readLanguageFromFormData(formData);
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const subscriptionId = String(formData.get("subscription_id") ?? "").trim();
  if (!subscriptionId) {
    redirect(`/admin/subscriptions?error=${encodeURIComponent(uiText(language, "admin.subscriptions.subscription_not_found"))}`);
  }

  const response = await fetch(`${backendUrl()}/api/v1/admin/subscriptions/${subscriptionId}/retry-now`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: "{}",
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));

  revalidatePath("/admin/subscriptions");
  if (!response.ok) {
    const detail =
      (payload && typeof payload === "object" && "detail" in payload ? String((payload as { detail?: unknown }).detail ?? "") : "") ||
      `HTTP_${response.status}`;
    redirect(`/admin/subscriptions?error=${encodeURIComponent(detail)}`);
  }
  redirect(
    `/admin/subscriptions?subscription_id=${encodeURIComponent(subscriptionId)}&ok=${encodeURIComponent(
      uiText(language, "admin.subscriptions.retry_started"),
    )}`,
  );
}

async function chargeNowAction(formData: FormData): Promise<void> {
  "use server";
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  const language = readLanguageFromFormData(formData);
  const subscriptionId = String(formData.get("subscription_id") ?? "").trim();
  const expectedAmount = String(formData.get("expected_amount") ?? "").trim();
  if (!token) redirect("/login?error_code=session_expired");
  const response = await fetch(`${backendUrl()}/api/v1/admin/subscriptions/${subscriptionId}/charge-now`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ expected_amount: expectedAmount, expected_currency: "EUR", confirm_charge: true }),
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  revalidatePath("/admin/subscriptions");
  if (!response.ok) {
    const detail = payload && typeof payload === "object" && "detail" in payload ? String((payload as { detail?: unknown }).detail ?? "") : `HTTP_${response.status}`;
    redirect(`/admin/subscriptions?subscription_id=${encodeURIComponent(subscriptionId)}&error=${encodeURIComponent(detail)}`);
  }
  redirect(`/admin/subscriptions?subscription_id=${encodeURIComponent(subscriptionId)}&ok=${encodeURIComponent(uiText(language, "admin.subscriptions.charge_completed"))}`);
}

async function refundInitialAction(formData: FormData): Promise<void> {
  "use server";
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  const language = readLanguageFromFormData(formData);
  const subscriptionId = String(formData.get("subscription_id") ?? "").trim();
  if (!token) redirect("/login?error_code=session_expired");
  const response = await fetch(`${backendUrl()}/api/v1/admin/subscriptions/${subscriptionId}/refund-initial`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ confirm_refund: true }),
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  revalidatePath("/admin/subscriptions");
  if (!response.ok) {
    const detail = payload && typeof payload === "object" && "detail" in payload ? String((payload as { detail?: unknown }).detail ?? "") : `HTTP_${response.status}`;
    redirect(`/admin/subscriptions?subscription_id=${encodeURIComponent(subscriptionId)}&error=${encodeURIComponent(detail)}`);
  }
  redirect(`/admin/subscriptions?subscription_id=${encodeURIComponent(subscriptionId)}&ok=${encodeURIComponent(uiText(language, "admin.subscriptions.refund_completed"))}`);
}

async function refundAttemptAction(formData: FormData): Promise<void> {
  "use server";
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  const language = readLanguageFromFormData(formData);
  const subscriptionId = String(formData.get("subscription_id") ?? "").trim();
  const attemptId = String(formData.get("attempt_id") ?? "").trim();
  if (!token) redirect("/login?error_code=session_expired");
  const response = await fetch(`${backendUrl()}/api/v1/admin/subscriptions/${subscriptionId}/attempts/${attemptId}/refund`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ confirm_refund: true }),
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  revalidatePath("/admin/subscriptions");
  if (!response.ok) {
    const detail = payload && typeof payload === "object" && "detail" in payload ? String((payload as { detail?: unknown }).detail ?? "") : `HTTP_${response.status}`;
    redirect(`/admin/subscriptions?subscription_id=${encodeURIComponent(subscriptionId)}&error=${encodeURIComponent(detail)}`);
  }
  redirect(`/admin/subscriptions?subscription_id=${encodeURIComponent(subscriptionId)}&ok=${encodeURIComponent(uiText(language, "admin.subscriptions.refund_completed"))}`);
}

export default async function AdminSubscriptionsPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
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

  const status = readParam(searchParams, "status");
  const q = readParam(searchParams, "q");
  const onlyRetryDue = readParam(searchParams, "only_retry_due");
  const selectedSubscriptionId = readParam(searchParams, "subscription_id");
  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");

  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (q) params.set("q", q);
  if (onlyRetryDue === "1") params.set("only_retry_due", "true");
  params.set("limit", "300");

  const listResult = await backendRequest<AdminSubscriptionEngineListOut>(
    `/api/v1/admin/subscriptions?${params.toString()}`,
    {},
    token,
  );
  const items = listResult.ok ? listResult.data.items : [];

  let detailResult: Awaited<ReturnType<typeof backendRequest<AdminSubscriptionEngineDetailOut>>> | null = null;
  if (selectedSubscriptionId) {
    detailResult = await backendRequest<AdminSubscriptionEngineDetailOut>(
      `/api/v1/admin/subscriptions/${selectedSubscriptionId}`,
      {},
      token,
    );
  }
  const detailData = detailResult && detailResult.ok ? detailResult.data : null;
  const detailPeriodLabel = detailData
    ? `${formatDate(detailData.subscription.current_period_start, language)} -> ${formatDate(detailData.subscription.current_period_end, language)}`
    : "-";

  const baseParams = new URLSearchParams();
  if (status) baseParams.set("status", status);
  if (q) baseParams.set("q", q);
  if (onlyRetryDue === "1") baseParams.set("only_retry_due", "1");
  const baseHref = baseParams.toString() ? `/admin/subscriptions?${baseParams.toString()}` : "/admin/subscriptions";

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h2>{t("admin.subscriptions.title")}</h2>
        <p className="muted">{t("admin.subscriptions.subtitle")}</p>
      </section>

      <section className="card">
        {!listResult.ok ? <p className="flash-err">{t("admin.subscriptions.backend_error")}: {translateBackendMessage(language, listResult.message)}</p> : null}
        {ok ? <p className="flash-ok">{ok}</p> : null}
        {error ? <p className="flash-err">{translateBackendMessage(language, error)}</p> : null}
        <form method="get" className="admin-list-filter-form">
          <div className="admin-list-filter-primary">
            <label>
              {t("admin.subscriptions.search_text")}
              <input type="search" name="q" defaultValue={q} placeholder={t("admin.subscriptions.search_placeholder")} enterKeyHint="search" />
            </label>
            <label>
              {t("admin.subscriptions.filter_status")}
              <select name="status" defaultValue={status}>
                <option value="">{uiText(language, "common.all")}</option>
                <option value="ACTIVE">{subscriptionStatusLabel("ACTIVE", language)}</option>
                <option value="PAYMENT_ALERT">{subscriptionStatusLabel("PAYMENT_ALERT", language)}</option>
                <option value="PRE_TERMINATION">{subscriptionStatusLabel("PRE_TERMINATION", language)}</option>
                <option value="TERMINATED">{subscriptionStatusLabel("TERMINATED", language)}</option>
                <option value="PAUSED">{subscriptionStatusLabel("PAUSED", language)}</option>
                <option value="CANCELLED">{subscriptionStatusLabel("CANCELLED", language)}</option>
              </select>
            </label>
            <div className="admin-list-filter-actions">
              <button type="submit">{uiText(language, "common.apply")}</button>
              <a className="ghost" href="/admin/subscriptions">{t("admin.subscriptions.reset_filters")}</a>
            </div>
          </div>
          <details className="admin-filter-disclosure">
            <summary>{language === "en" ? "Advanced filters" : "Filtres avances"}</summary>
            <div className="admin-filter-disclosure-content">
              <label className="row align-end">
                <input type="checkbox" name="only_retry_due" value="1" defaultChecked={onlyRetryDue === "1"} />
                {t("admin.subscriptions.retry_due_today")}
              </label>
            </div>
          </details>
        </form>
      </section>

      <section className="card">
        <div className="table-wrap admin-table-card-wrap">
          <table className="data-table admin-responsive-table">
            <thead>
              <tr>
                <th>{t("admin.subscriptions.column_client")}</th>
                <th>{t("admin.subscriptions.column_subscription")}</th>
                <th>{uiText(language, "common.status")}</th>
                <th>{uiText(language, "common.amount")}</th>
                <th>{t("admin.subscriptions.column_next_due")}</th>
                <th>{t("admin.subscriptions.column_last_attempt")}</th>
                <th>{t("admin.subscriptions.column_last_payment")}</th>
                <th>{t("admin.subscriptions.column_booking_block")}</th>
                <th>{uiText(language, "client.action")}</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={9}>
                    <p className="muted">{t("admin.subscriptions.no_results")}</p>
                  </td>
                </tr>
              ) : (
                items.map((row) => {
                  const hrefParams = new URLSearchParams(baseParams);
                  hrefParams.set("subscription_id", row.id);
                  return (
                    <tr key={row.id}>
                      <td data-mobile-label="" className="mobile-row-primary">
                        <strong>{row.customer_name}</strong>
                        <br />
                        <span className="muted">{row.customer_email}</span>
                      </td>
                      <td data-mobile-label={t("admin.subscriptions.column_subscription")}>{row.plan_name}</td>
                      <td data-mobile-label={uiText(language, "common.status")}>
                        <span className={`status-pill ${statusClass(row.status)}`}>{subscriptionStatusLabel(row.status, language)}</span>
                      </td>
                      <td data-mobile-label={uiText(language, "common.amount")}>{formatAmount(row.amount, row.currency, language)}</td>
                      <td data-mobile-label={t("admin.subscriptions.column_next_due")}>{formatDate(row.next_billing_date, language)}</td>
                      <td data-mobile-hidden="true">{formatDate(row.last_attempt_at, language)}</td>
                      <td data-mobile-hidden="true">{formatDate(row.last_successful_charge_at, language)}</td>
                      <td data-mobile-label={t("admin.subscriptions.column_booking_block")}>{row.bookings_blocked ? uiText(language, "common.yes") : uiText(language, "common.no")}</td>
                      <td data-mobile-label={uiText(language, "client.action")}>
                        <a className="ghost" href={`/admin/subscriptions?${hrefParams.toString()}`}>
                          {t("admin.subscriptions.view_detail")}
                        </a>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      {detailData ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-panel-wide">
            <a className="modal-close-x" href={baseHref} aria-label={uiText(language, "common.close")}>
              ×
            </a>
            <header className="activity-modal-header">
              <h2 className="modal-title">{t("admin.subscriptions.detail_title")}</h2>
              <p className="muted">
                {detailData.subscription.customer_name} - {detailData.subscription.plan_name}
              </p>
            </header>

            <section className="card modal-card">
              <h3>{uiText(language, "common.summary")}</h3>
              <div className="list">
                <article className="item row spread"><span>{uiText(language, "common.status")}</span><strong>{subscriptionStatusLabel(detailData.subscription.status, language)}</strong></article>
                <article className="item row spread"><span>{t("admin.subscriptions.current_period")}</span><strong>{detailPeriodLabel}</strong></article>
                <article className="item row spread"><span>{t("admin.subscriptions.column_next_due")}</span><strong>{formatDate(detailData.subscription.next_billing_date, language)}</strong></article>
                <article className="item row spread"><span>{t("admin.subscriptions.bookings_blocked")}</span><strong>{detailData.subscription.bookings_blocked ? uiText(language, "common.yes") : uiText(language, "common.no")}</strong></article>
                <article className="item row spread"><span>{t("admin.subscriptions.recovery_link")}</span><strong>{detailData.subscription.recovery_url ? t("admin.subscriptions.recovery_available") : uiText(language, "common.no")}</strong></article>
                <article className="item row spread"><span>{t("admin.subscriptions.initial_payment")}</span><strong>{detailData.initial_payment_refunded ? t("admin.subscriptions.status_refunded") : detailData.initial_payment_refundable ? t("admin.subscriptions.refundable") : "-"}</strong></article>
              </div>
              <div className="row top-gap-sm">
                <form action={retryNowAction}>
                  <input type="hidden" name="subscription_id" value={detailData.subscription.id} />
                  <input type="hidden" name="ui_language" value={language} />
                  <button type="submit">{t("admin.subscriptions.retry_now")}</button>
                </form>
                {detailData.attempts.length === 0 && detailData.subscription.status.toUpperCase() === "ACTIVE" ? (
                  <form action={chargeNowAction} className="row">
                    <input type="hidden" name="subscription_id" value={detailData.subscription.id} />
                    <input type="hidden" name="ui_language" value={language} />
                    <label>
                      {t("admin.subscriptions.expected_amount")}
                      <input type="number" name="expected_amount" min="0.01" step="0.01" required className="input-compact" />
                    </label>
                    <button type="submit" className="danger">{t("admin.subscriptions.charge_now")}</button>
                  </form>
                ) : null}
                {detailData.initial_payment_refundable ? (
                  <form action={refundInitialAction}>
                    <input type="hidden" name="subscription_id" value={detailData.subscription.id} />
                    <input type="hidden" name="ui_language" value={language} />
                    <button type="submit" className="danger">{t("admin.subscriptions.refund_initial")}</button>
                  </form>
                ) : null}
              </div>
            </section>

            <section className="card modal-card">
              <h3>{t("admin.subscriptions.billing_cycles")}</h3>
              <div className="table-wrap admin-table-card-wrap">
                <table className="data-table admin-responsive-table">
                  <thead>
                    <tr>
                      <th>{uiText(language, "common.period")}</th>
                      <th>{t("admin.subscriptions.column_due_date")}</th>
                      <th>{uiText(language, "common.status")}</th>
                      <th>{t("admin.subscriptions.column_attempts")}</th>
                      <th>{t("admin.subscriptions.column_retry")}</th>
                      <th>{uiText(language, "common.amount")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detailData.cycles.length === 0 ? (
                      <tr><td colSpan={6}>{t("admin.subscriptions.no_cycles")}</td></tr>
                    ) : (
                      detailData.cycles.map((row) => (
                        <tr key={row.id}>
                          <td className="mobile-row-primary" data-mobile-label={uiText(language, "common.period")}>{`${formatDate(row.period_start, language)} -> ${formatDate(row.period_end, language)}`}</td>
                          <td data-mobile-label={t("admin.subscriptions.column_due_date")}>{formatDate(row.billing_date, language)}</td>
                          <td data-mobile-label={uiText(language, "common.status")}><span className={`status-pill ${statusClass(row.status)}`}>{subscriptionStatusLabel(row.status, language)}</span></td>
                          <td data-mobile-label={t("admin.subscriptions.column_attempts")}>{row.attempt_count}</td>
                          <td data-mobile-label={t("admin.subscriptions.column_retry")}>{formatDate(row.next_retry_at, language)}</td>
                          <td data-mobile-label={uiText(language, "common.amount")}>{formatAmount(row.amount, row.currency, language)}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="card modal-card">
              <h3>{t("admin.subscriptions.payment_attempts")}</h3>
              <div className="table-wrap admin-table-card-wrap">
                <table className="data-table admin-responsive-table">
                  <thead>
                    <tr>
                      <th>{uiText(language, "common.date")}</th>
                      <th>#</th>
                      <th>{uiText(language, "common.status")}</th>
                      <th>{t("admin.subscriptions.column_provider")}</th>
                      <th>{t("admin.subscriptions.column_code")}</th>
                      <th>{t("admin.subscriptions.column_reason")}</th>
                      <th>{uiText(language, "client.action")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detailData.attempts.length === 0 ? (
                      <tr><td colSpan={7}>{t("admin.subscriptions.no_attempts")}</td></tr>
                    ) : (
                      detailData.attempts.map((row) => (
                        <tr key={row.id}>
                          <td className="mobile-row-primary" data-mobile-label={uiText(language, "common.date")}>{formatDate(row.attempted_at, language)}</td>
                          <td data-mobile-label="#">#{row.attempt_number}</td>
                          <td data-mobile-label={uiText(language, "common.status")}><span className={`status-pill ${statusClass(row.status)}`}>{subscriptionStatusLabel(row.status, language)}</span></td>
                          <td data-mobile-label={t("admin.subscriptions.column_provider")}>{row.provider_name ?? "-"}</td>
                          <td data-mobile-label={t("admin.subscriptions.column_code")}>{row.failure_code ?? row.provider_status ?? "-"}</td>
                          <td data-mobile-label={t("admin.subscriptions.column_reason")}>{row.failure_reason ?? "-"}</td>
                          <td data-mobile-label={uiText(language, "client.action")}>
                            {row.status.toLowerCase() === "success" && row.provider_name?.toUpperCase() === "PAYPLUG" && row.provider_payment_id ? (
                              <form action={refundAttemptAction}>
                                <input type="hidden" name="subscription_id" value={detailData.subscription.id} />
                                <input type="hidden" name="attempt_id" value={row.id} />
                                <input type="hidden" name="ui_language" value={language} />
                                <button type="submit" className="danger">{t("admin.subscriptions.refund_attempt")}</button>
                              </form>
                            ) : null}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </article>
        </section>
      ) : null}
    </section>
  );
}
