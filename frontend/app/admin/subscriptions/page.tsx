import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest, backendUrl } from "../../../lib/backend";
import type { AdminSubscriptionEngineDetailOut, AdminSubscriptionEngineListOut } from "../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatDate(value: string | null): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function formatAmount(value: string | null, currency: string | null): string {
  if (!value) {
    return "-";
  }
  const amount = Number(value);
  if (!Number.isFinite(amount)) {
    return `${value} ${currency ?? ""}`.trim();
  }
  const safeCurrency = (currency ?? "EUR").toUpperCase();
  try {
    return new Intl.NumberFormat("fr-FR", {
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
  if (normalized === "PAYMENT_ALERT" || normalized === "FAILED_FIRST_ATTEMPT") {
    return "status-warn";
  }
  if (normalized === "PRE_TERMINATION" || normalized === "TERMINATED" || normalized === "FAILED_FINAL") {
    return "status-cancelled";
  }
  return "status-off";
}

async function retryNowAction(formData: FormData): Promise<void> {
  "use server";

  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const subscriptionId = String(formData.get("subscription_id") ?? "").trim();
  if (!subscriptionId) {
    redirect("/admin/subscriptions?error=Abonnement%20introuvable");
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
  redirect(`/admin/subscriptions?subscription_id=${encodeURIComponent(subscriptionId)}&ok=Retry%20lance`);
}

export default async function AdminSubscriptionsPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

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
    ? `${formatDate(detailData.subscription.current_period_start)} -> ${formatDate(detailData.subscription.current_period_end)}`
    : "-";

  const baseParams = new URLSearchParams();
  if (status) baseParams.set("status", status);
  if (q) baseParams.set("q", q);
  if (onlyRetryDue === "1") baseParams.set("only_retry_due", "1");
  const baseHref = baseParams.toString() ? `/admin/subscriptions?${baseParams.toString()}` : "/admin/subscriptions";

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h2>Abonnements mensuels</h2>
        <p className="muted">Suivi des renouvellements, impayes, retries et regularisations.</p>
      </section>

      <section className="card">
        {!listResult.ok ? <p className="flash-err">Erreur backend: {listResult.message}</p> : null}
        {ok ? <p className="flash-ok">{ok}</p> : null}
        {error ? <p className="flash-err">{error}</p> : null}
        <form method="get" className="grid cols-4 sticky-filters">
          <label>
            Statut
            <select name="status" defaultValue={status}>
              <option value="">Tous</option>
              <option value="ACTIVE">ACTIVE</option>
              <option value="PAYMENT_ALERT">PAYMENT_ALERT</option>
              <option value="PRE_TERMINATION">PRE_TERMINATION</option>
              <option value="TERMINATED">TERMINATED</option>
              <option value="PAUSED">PAUSED</option>
              <option value="CANCELLED">CANCELLED</option>
            </select>
          </label>
          <label className="cols-span-2">
            Recherche texte
            <input type="text" name="q" defaultValue={q} placeholder="nom client, email, plan..." />
          </label>
          <label className="row align-end top-gap-sm">
            <input type="checkbox" name="only_retry_due" value="1" defaultChecked={onlyRetryDue === "1"} />
            Retry prevu aujourd hui
          </label>
          <div className="row end cols-span-4 top-gap-sm">
            <button type="submit">Appliquer</button>
            <a className="ghost" href="/admin/subscriptions">
              Reset filtres
            </a>
          </div>
        </form>
      </section>

      <section className="card">
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Client</th>
                <th>Abonnement</th>
                <th>Statut</th>
                <th>Montant</th>
                <th>Prochaine echeance</th>
                <th>Derniere tentative</th>
                <th>Dernier paiement</th>
                <th>Blocage reservations</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={9}>
                    <p className="muted">Aucun abonnement sur ces filtres.</p>
                  </td>
                </tr>
              ) : (
                items.map((row) => {
                  const hrefParams = new URLSearchParams(baseParams);
                  hrefParams.set("subscription_id", row.id);
                  return (
                    <tr key={row.id}>
                      <td>
                        <strong>{row.customer_name}</strong>
                        <br />
                        <span className="muted">{row.customer_email}</span>
                      </td>
                      <td>{row.plan_name}</td>
                      <td>
                        <span className={`status-pill ${statusClass(row.status)}`}>{row.status}</span>
                      </td>
                      <td>{formatAmount(row.amount, row.currency)}</td>
                      <td>{formatDate(row.next_billing_date)}</td>
                      <td>{formatDate(row.last_attempt_at)}</td>
                      <td>{formatDate(row.last_successful_charge_at)}</td>
                      <td>{row.bookings_blocked ? "Oui" : "Non"}</td>
                      <td>
                        <a className="ghost" href={`/admin/subscriptions?${hrefParams.toString()}`}>
                          Voir detail
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
            <a className="modal-close-x" href={baseHref} aria-label="Fermer">
              ×
            </a>
            <header className="activity-modal-header">
              <h2 className="modal-title">Detail abonnement</h2>
              <p className="muted">
                {detailData.subscription.customer_name} - {detailData.subscription.plan_name}
              </p>
            </header>

            <section className="card modal-card">
              <h3>Resume</h3>
              <div className="list">
                <article className="item row spread"><span>Statut</span><strong>{detailData.subscription.status}</strong></article>
                <article className="item row spread"><span>Periode courante</span><strong>{detailPeriodLabel}</strong></article>
                <article className="item row spread"><span>Prochaine echeance</span><strong>{formatDate(detailData.subscription.next_billing_date)}</strong></article>
                <article className="item row spread"><span>Reservations bloquees</span><strong>{detailData.subscription.bookings_blocked ? "Oui" : "Non"}</strong></article>
                <article className="item row spread"><span>Lien regularisation</span><strong>{detailData.subscription.recovery_url ? "Disponible" : "Non"}</strong></article>
              </div>
              <form action={retryNowAction} className="top-gap-sm">
                <input type="hidden" name="subscription_id" value={detailData.subscription.id} />
                <button type="submit">Relancer maintenant</button>
              </form>
            </section>

            <section className="card modal-card">
              <h3>Cycles de facturation</h3>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Periode</th>
                      <th>Echeance</th>
                      <th>Statut</th>
                      <th>Tentatives</th>
                      <th>Retry</th>
                      <th>Montant</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detailData.cycles.length === 0 ? (
                      <tr><td colSpan={6}>Aucun cycle</td></tr>
                    ) : (
                      detailData.cycles.map((row) => (
                        <tr key={row.id}>
                          <td>{formatDate(row.period_start)} -> {formatDate(row.period_end)}</td>
                          <td>{formatDate(row.billing_date)}</td>
                          <td><span className={`status-pill ${statusClass(row.status)}`}>{row.status}</span></td>
                          <td>{row.attempt_count}</td>
                          <td>{formatDate(row.next_retry_at)}</td>
                          <td>{formatAmount(row.amount, row.currency)}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="card modal-card">
              <h3>Tentatives de paiement</h3>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>#</th>
                      <th>Statut</th>
                      <th>Provider</th>
                      <th>Code</th>
                      <th>Raison</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detailData.attempts.length === 0 ? (
                      <tr><td colSpan={6}>Aucune tentative</td></tr>
                    ) : (
                      detailData.attempts.map((row) => (
                        <tr key={row.id}>
                          <td>{formatDate(row.attempted_at)}</td>
                          <td>{row.attempt_number}</td>
                          <td><span className={`status-pill ${statusClass(row.status)}`}>{row.status}</span></td>
                          <td>{row.provider_name ?? "-"}</td>
                          <td>{row.failure_code ?? row.provider_status ?? "-"}</td>
                          <td>{row.failure_reason ?? "-"}</td>
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
