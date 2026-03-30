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
  related_quote_id: string | null;
};

type TypeformIntakeListPageOut = {
  items: TypeformIntakeListOut[];
  total: number;
  page: number;
  page_size: number;
};

const DEFAULT_PAGE = 1;
const DEFAULT_PAGE_SIZE = 10;

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

function formatDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function statusLabel(value: string): string {
  if (value === "NEW") return "Nouveau";
  if (value === "NORMALIZED") return "Normalise";
  if (value === "MATCHING_REQUIRED") return "Matching requis";
  if (value === "READY_FOR_DRAFT_QUOTE") return "Pret devis";
  if (value === "BLOCKED") return "Bloque";
  if (value === "PROCESSED") return "Traite";
  if (value === "IGNORED") return "Ignore";
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

function segmentLabel(value: string | null): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "eveil") return "Eveil";
  if (normalized === "child") return "Enfants";
  if (normalized === "teen") return "Ados";
  if (normalized === "adult") return "Adultes";
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
  page,
}: {
  q: string;
  status: string;
  page?: number;
}): string {
  const params = new URLSearchParams();
  if (q) {
    params.set("q", q);
  }
  if (status) {
    params.set("status", status);
  }
  if ((page ?? DEFAULT_PAGE) > DEFAULT_PAGE) {
    params.set("page", String(page));
  }
  const search = params.toString();
  return search ? `/admin/intakes?${search}` : "/admin/intakes";
}

export default async function AdminTypeformIntakesPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const q = readParam(searchParams, "q").trim();
  const status = safeStatus(readParam(searchParams, "status"));
  const requestedPage = readPositiveIntParam(searchParams, "page", DEFAULT_PAGE);
  const ok = readParam(searchParams, "ok").trim();
  const error = readParam(searchParams, "error").trim();

  const query = new URLSearchParams();
  if (q) query.set("q", q);
  if (status) query.set("status", status);
  query.set("page", String(requestedPage));
  query.set("page_size", String(DEFAULT_PAGE_SIZE));

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
  const returnTo = buildIntakesHref({ q, status, page: currentPage });
  const previousPageHref = buildIntakesHref({ q, status, page: currentPage - 1 });
  const nextPageHref = buildIntakesHref({ q, status, page: currentPage + 1 });

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>Inbox Typeform</h2>
            <p className="muted">Pipeline Typeform → Intake → Normalisation → Pre-devis → Devis brouillon.</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href="/admin/quotes">Devis</Link>
            <Link className="ghost" href="/admin/prospects">Prospects</Link>
            <form action={seedTypeformDemoAction}>
              <input type="hidden" name="return_to" value="/admin/intakes" />
              <button type="submit">Charger la demo</button>
            </form>
          </div>
        </div>
      </section>

      {!result.ok ? <section className="flash-err">Erreur backend: {result.message}</section> : null}
      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}

      <section className="card">
        <form method="get" className="grid cols-4 sticky-filters">
          <label className="span-2">
            Recherche
            <input type="search" name="q" defaultValue={q} placeholder="Prospect, enfant, site, segment..." />
          </label>
          <label>
            Statut
            <select name="status" defaultValue={status}>
              <option value="">Tous</option>
              <option value="NEW">Nouveau</option>
              <option value="NORMALIZED">Normalise</option>
              <option value="MATCHING_REQUIRED">Matching requis</option>
              <option value="READY_FOR_DRAFT_QUOTE">Pret devis</option>
              <option value="BLOCKED">Bloque</option>
              <option value="PROCESSED">Traite</option>
              <option value="IGNORED">Ignore</option>
            </select>
          </label>
          <div className="row wrap gap-sm" style={{ alignItems: "end" }}>
            <button type="submit">Filtrer</button>
            <Link className="ghost" href="/admin/intakes">Reinitialiser</Link>
          </div>
        </form>
      </section>

      <section className="card">
        <div className="row spread wrap gap-sm">
          <h3>Intakes</h3>
          <p className="muted">{total} element(s)</p>
        </div>
        {rows.length === 0 ? (
          <div className={`${styles.emptyState} top-gap-sm`}>
            <p className="muted">Aucune intake pour le moment. Chargez la demo pour obtenir les 4 scenarios de reference.</p>
            <form action={seedTypeformDemoAction} className="row gap-sm">
              <input type="hidden" name="return_to" value="/admin/intakes" />
              <button type="submit">Installer les scenarios demo</button>
            </form>
          </div>
        ) : (
          <div className="table-wrap top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Source form</th>
                  <th>Prospect</th>
                  <th>Enfant</th>
                  <th>Site</th>
                  <th>Segment</th>
                  <th>Statut</th>
                  <th>Warnings</th>
                  <th>Blocages</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>{formatDate(row.received_at)}</td>
                    <td>
                      <strong>{row.source_form_label}</strong>
                      <div className="muted">{row.source_form_id}</div>
                    </td>
                    <td>{row.prospect_label || "-"}</td>
                    <td>{row.child_label || "-"}</td>
                    <td>{row.detected_location || "-"}</td>
                    <td>{segmentLabel(row.detected_segment)}</td>
                    <td>
                      <span className={`status-pill ${statusClass(row.intake_status)}`}>{statusLabel(row.intake_status)}</span>
                    </td>
                    <td>{compactList(row.warnings)}</td>
                    <td>{compactList(row.blockages)}</td>
                    <td>
                      <div className="row wrap gap-sm">
                        <Link className="ghost" href={`/admin/intakes/${encodeURIComponent(row.id)}`}>Ouvrir</Link>
                        {row.related_quote_id ? (
                          <Link className="ghost" href={`/admin/quotes/${encodeURIComponent(row.related_quote_id)}`}>Devis</Link>
                        ) : null}
                        {!row.related_quote_id && row.intake_status !== "IGNORED" ? (
                          <form action={ignoreTypeformIntakeAction}>
                            <input type="hidden" name="intake_id" value={row.id} />
                            <input type="hidden" name="return_to" value={returnTo} />
                            <button type="submit" className="ghost">Ignorer</button>
                          </form>
                        ) : null}
                        {!row.related_quote_id && row.intake_status === "IGNORED" ? (
                          <form action={restoreTypeformIntakeAction}>
                            <input type="hidden" name="intake_id" value={row.id} />
                            <input type="hidden" name="return_to" value={returnTo} />
                            <button type="submit" className="ghost">Reprendre</button>
                          </form>
                        ) : null}
                        {!row.related_quote_id ? (
                          <form id={`delete-intake-${row.id}`} action={deleteTypeformIntakeAction}>
                            <input type="hidden" name="intake_id" value={row.id} />
                            <input type="hidden" name="return_to" value={returnTo} />
                            <ConfirmSubmitButton
                              formId={`delete-intake-${row.id}`}
                              label="Supprimer"
                              title="Supprimer cette intake ?"
                              description="Cette action supprime definitivement la reponse Typeform si aucun devis n'y est rattache."
                              confirmLabel="Supprimer"
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
        )}
        {total > 0 ? (
          <div className="row spread clients-pagination top-gap-sm">
            <small className="muted">
              Affichage {pageStart + 1}-{Math.min(pageStart + rows.length, total)} sur {total} intake(s)
            </small>
            <div className="row">
              {currentPage > 1 ? (
                <Link className="mode-link" href={previousPageHref}>
                  ← Precedent
                </Link>
              ) : (
                <span className="mode-link disabled-link">← Precedent</span>
              )}
              <span className="badge">
                Page {currentPage}/{totalPages}
              </span>
              {currentPage < totalPages ? (
                <Link className="mode-link" href={nextPageHref}>
                  Suivant →
                </Link>
              ) : (
                <span className="mode-link disabled-link">Suivant →</span>
              )}
            </div>
          </div>
        ) : null}
      </section>
    </section>
  );
}
