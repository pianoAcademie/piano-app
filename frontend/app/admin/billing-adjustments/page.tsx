import Link from "next/link";
import { redirect } from "next/navigation";

import {
  approveAdminClientBillingAdjustmentAction,
  dismissAdminClientBillingAdjustmentAction,
} from "../../../lib/actions";
import { getAdminToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import type { AdminClientBillingAdjustmentQueueOut, UserOut } from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage } from "../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

type PageProps = {
  searchParams: SearchParams;
};

const STATUS_OPTIONS = ["READY", "CONVERTED", "DISMISSED", ""] as const;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatMoney(value: string, currency: string, language: UiLanguage): string {
  const amount = Number(value);
  return new Intl.NumberFormat(localeForUiLanguage(language), {
    style: "currency",
    currency: currency || "EUR",
    maximumFractionDigits: 2,
  }).format(Number.isFinite(amount) ? amount : 0);
}

function formatDate(value: string, language: UiLanguage): string {
  return new Date(value).toLocaleString(localeForUiLanguage(language), {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Paris",
  });
}

function statusLabel(status: string): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "CONVERTED") return "Ajoute aux lignes a facturer";
  if (normalized === "DISMISSED") return "Ignore";
  return "A valider";
}

function statusClass(status: string): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "CONVERTED") return "status-ok";
  if (normalized === "DISMISSED") return "status-off";
  return "status-warn";
}

function changeTypeLabel(type: string | null): string {
  const normalized = (type || "").trim().toUpperCase();
  if (normalized === "SLOT_CHANGE") return "Changement de creneau";
  if (normalized === "COURSE_CANCELLED") return "Cours annule";
  if (normalized === "COURSE_ADDED") return "Cours ajoute";
  if (normalized === "COURSE_REMOVED") return "Cours supprime";
  if (normalized === "FORMULA_CHANGE") return "Changement de formule";
  if (normalized === "EXCEPTIONAL_ADJUSTMENT") return "Ajustement exceptionnel";
  return "Autre changement";
}

function statusHref(status: string): string {
  const params = new URLSearchParams();
  if (status) {
    params.set("status", status);
  }
  const query = params.toString();
  return `/admin/billing-adjustments${query ? `?${query}` : ""}`;
}

export default async function AdminBillingAdjustmentsPage({ searchParams }: PageProps): Promise<JSX.Element> {
  const token = getAdminToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  const language = meResult.ok ? normalizeUiLanguage(meResult.data.preferred_language) : "fr";
  const rawStatus = readParam(searchParams, "status").trim().toUpperCase();
  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error");
  const selectedStatus = STATUS_OPTIONS.includes(rawStatus as (typeof STATUS_OPTIONS)[number]) ? rawStatus : "READY";

  const query = new URLSearchParams();
  if (selectedStatus) {
    query.set("status", selectedStatus);
  }
  const result = await backendRequest<AdminClientBillingAdjustmentQueueOut[]>(
    `/api/v1/admin/billing-adjustments${query.toString() ? `?${query.toString()}` : ""}`,
    {},
    token,
  );
  const rows = result.ok ? result.data : [];
  const readyCount = rows.filter((row) => row.status === "READY").length;
  const totalByCurrency = rows.reduce((acc, row) => {
    if (row.status !== "READY") {
      return acc;
    }
    const amount = Number(row.total_incl_vat);
    const currency = row.currency || "EUR";
    acc.set(currency, (acc.get(currency) ?? 0) + (Number.isFinite(amount) ? amount : 0));
    return acc;
  }, new Map<string, number>());
  const returnTo = statusHref(selectedStatus);

  return (
    <section className="stack-lg">
      <div className="row spread">
        <div>
          <h1>Regularisations a valider</h1>
          <p className="muted">File des changements de parcours ayant un impact sur une prochaine facture ou deduction.</p>
        </div>
        <div className="row">
          <span className="badge">{readyCount} a valider</span>
          {[...totalByCurrency.entries()].map(([currency, total]) => (
            <span key={currency} className="badge">
              {formatMoney(String(total), currency, language)}
            </span>
          ))}
        </div>
      </div>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {result.ok ? null : <section className="flash-err">{result.message}</section>}

      <article className="card">
        <div className="row spread">
          <div className="segmented-tabs">
            <Link className={`segmented-tab ${selectedStatus === "READY" ? "active" : ""}`} href={statusHref("READY")}>
              A valider
            </Link>
            <Link className={`segmented-tab ${selectedStatus === "CONVERTED" ? "active" : ""}`} href={statusHref("CONVERTED")}>
              Valides
            </Link>
            <Link className={`segmented-tab ${selectedStatus === "DISMISSED" ? "active" : ""}`} href={statusHref("DISMISSED")}>
              Ignores
            </Link>
            <Link className={`segmented-tab ${selectedStatus === "" ? "active" : ""}`} href={statusHref("")}>
              Tous
            </Link>
          </div>
        </div>

        {rows.length === 0 ? (
          <p className="muted top-gap-sm">Aucun ajustement dans ce filtre.</p>
        ) : (
          <div className="table-wrap top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Client / eleve</th>
                  <th>Origine</th>
                  <th>Montant</th>
                  <th>Statut</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>{formatDate(row.created_at, language)}</td>
                    <td>
                      <Link href={`/admin/clients/${row.client_id}?tab=changements`} className="mode-link">
                        {row.client_display_name}
                      </Link>
                      {row.student_display_name ? <div className="muted">{row.student_display_name}</div> : null}
                    </td>
                    <td>
                      <strong>{row.label}</strong>
                      <div className="muted">{changeTypeLabel(row.change_type)}</div>
                      <div className="muted">{row.quote_number ?? "Sans devis rattache"}</div>
                      {row.description ? <div className="muted">{row.description}</div> : null}
                    </td>
                    <td>
                      <strong>{formatMoney(row.total_incl_vat, row.currency, language)}</strong>
                      <div className="muted">{row.adjustment_type === "CREDIT_NOTE" ? "Avoir / deduction" : "Facture complementaire"}</div>
                    </td>
                    <td>
                      <span className={`status-pill ${statusClass(row.status)}`}>{statusLabel(row.status)}</span>
                      {row.dismissed_reason ? <div className="muted">{row.dismissed_reason}</div> : null}
                    </td>
                    <td>
                      {row.status === "READY" ? (
                        <div className="row payment-row-actions">
                          <form action={approveAdminClientBillingAdjustmentAction}>
                            <input type="hidden" name="client_id" value={row.client_id} />
                            <input type="hidden" name="adjustment_id" value={row.id} />
                            <input type="hidden" name="return_to" value={returnTo} />
                            <button type="submit" className="client-action-icon" title="Ajouter aux lignes a facturer">
                              ✓
                            </button>
                          </form>
                          <form action={dismissAdminClientBillingAdjustmentAction}>
                            <input type="hidden" name="client_id" value={row.client_id} />
                            <input type="hidden" name="adjustment_id" value={row.id} />
                            <input type="hidden" name="return_to" value={returnTo} />
                            <button type="submit" className="client-action-icon danger" title="Ignorer cet ajustement">
                              ×
                            </button>
                          </form>
                        </div>
                      ) : (
                        <Link href={`/admin/clients/${row.client_id}?tab=changements`} className="mode-link">
                          Voir
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </article>
    </section>
  );
}
