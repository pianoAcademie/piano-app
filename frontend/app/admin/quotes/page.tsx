import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import CopyLinkButton from "../../../components/copy-link-button";
import QuoteWizardForm from "../../../components/quote-wizard-form";
import {
  changeQuoteFollowupPaymentMethodAction,
  createQuoteDraftAction,
  createQuoteProspectAction,
  duplicateQuoteAction,
  finalizeQuoteFollowupAction,
  selectQuoteFollowupSlotAction,
  sendQuoteAction,
} from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import type { AdminActivityOut, AdminCatalogKitOut, AdminCatalogProductOut, AdminClientOut, LocationOut } from "../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

type ProspectOut = {
  id: string;
  first_name: string | null;
  last_name: string | null;
  email: string;
};

type QuoteLineOut = {
  id: string;
  line_type: string;
  title: string;
  quantity: string;
  unit_price_ttc: string;
  amount_ttc: string;
};

type QuoteOut = {
  id: string;
  quote_number: string;
  status: string;
  context_type: string;
  currency: string;
  total_ttc: string;
  created_at: string;
  expires_at: string | null;
  sent_at: string | null;
  approved_at: string | null;
  prospect_id: string | null;
  client_id: string | null;
  quote_type: string;
  school_year_label: string | null;
  estimated_solfege_level: string | null;
  calendar_snapshot: Record<string, unknown>;
  payment_terms_snapshot: Record<string, unknown>;
  public_token: string | null;
  pdf_token: string | null;
};

type QuoteDetailOut = {
  quote: QuoteOut;
  lines: QuoteLineOut[];
};

type QuoteFollowupOut = {
  id: string;
  quote_id: string;
  target_client_id: string | null;
  status: string;
  payment_method_status: string;
  solfege_slot_status: string;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

type QuoteTypeOut = {
  id: string;
  name: string;
};

type PricingCatalogOut = {
  id: string;
  name: string;
};

type PaymentPlanOut = {
  id: string;
  name: string;
  payment_method: string;
};

type CgvVersionOut = {
  id: string;
  version_label: string;
};

type SolfegeLevelRuleOut = {
  id: string;
  level_code: string;
  duration_minutes: number;
  allowed_weekdays: number[];
  allowed_time_slots: Array<Record<string, unknown>>;
};

function readParam(params: SearchParams, key: string): string {
  const raw = params[key];
  if (Array.isArray(raw)) {
    return raw[0] ?? "";
  }
  return raw ?? "";
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

function formatAmount(value: string, currency: string): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) {
    return `${value} ${currency}`;
  }
  try {
    return new Intl.NumberFormat("fr-FR", { style: "currency", currency: currency || "EUR" }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${(currency || "EUR").toUpperCase()}`;
  }
}

function quoteStatusClass(status: string): string {
  const normalized = status.trim().toLowerCase();
  if (normalized === "approved") return "status-ok";
  if (normalized === "sent" || normalized === "change_requested") return "status-warn";
  if (normalized === "rejected" || normalized === "expired" || normalized === "cancelled") return "status-cancelled";
  return "status-off";
}

function labelForContext(contextType: string): string {
  return contextType === "active_client" ? "Client actif" : "Acquisition";
}

function displayName(firstName: string | null, lastName: string | null, fallback: string): string {
  const value = [firstName, lastName].filter(Boolean).join(" ").trim();
  return value || fallback;
}

function getScheduleItems(snapshot: Record<string, unknown>): Array<Record<string, unknown>> {
  const raw = snapshot.schedule;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter((item): item is Record<string, unknown> => !!item && typeof item === "object");
}

function getCalendarSessions(snapshot: Record<string, unknown>): Array<Record<string, unknown>> {
  const raw = snapshot.sessions;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter((item): item is Record<string, unknown> => !!item && typeof item === "object");
}

function quotesBasePath(statusFilter: string, contextFilter: string, query: string): string {
  const params = new URLSearchParams();
  if (statusFilter) params.set("status", statusFilter);
  if (contextFilter) params.set("context_type", contextFilter);
  if (query) params.set("q", query);
  const value = params.toString();
  return value ? `/admin/quotes?${value}` : "/admin/quotes";
}

export default async function AdminQuotesPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const statusFilter = readParam(searchParams, "status");
  const contextFilter = readParam(searchParams, "context_type");
  const query = readParam(searchParams, "q");
  const selectedQuoteId = readParam(searchParams, "quote_id");
  const selectedProspectId = readParam(searchParams, "prospect_id");
  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");

  const listQuery = new URLSearchParams();
  if (statusFilter) listQuery.set("status", statusFilter);
  if (contextFilter) listQuery.set("context_type", contextFilter);
  if (query) listQuery.set("q", query);
  listQuery.set("limit", "300");

  const [
    prospectsResult,
    clientsResult,
    quoteTypesResult,
    catalogsResult,
    paymentPlansResult,
    cgvVersionsResult,
    locationsResult,
    activitiesResult,
    productsResult,
    kitsResult,
    solfegeRulesResult,
    quotesResult,
  ] = await Promise.all([
    backendRequest<ProspectOut[]>("/api/v1/prospects", {}, token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?limit=500&include_archived=false", {}, token),
    backendRequest<QuoteTypeOut[]>("/api/v1/quote-types", {}, token),
    backendRequest<PricingCatalogOut[]>("/api/v1/pricing-catalogs", {}, token),
    backendRequest<PaymentPlanOut[]>("/api/v1/payment-plans", {}, token),
    backendRequest<CgvVersionOut[]>("/api/v1/cgv-versions", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=false", {}, token),
    backendRequest<AdminActivityOut[]>("/api/v1/admin/activities?include_inactive=true", {}, token),
    backendRequest<AdminCatalogProductOut[]>("/api/v1/admin/config/catalog/products?include_inactive=true", {}, token),
    backendRequest<AdminCatalogKitOut[]>("/api/v1/admin/config/catalog/kits?include_inactive=true", {}, token),
    backendRequest<SolfegeLevelRuleOut[]>("/api/v1/solfege-level-rules", {}, token),
    backendRequest<QuoteOut[]>(`/api/v1/quotes?${listQuery.toString()}`, {}, token),
  ]);

  const prospects = prospectsResult.ok ? prospectsResult.data : [];
  const clients = clientsResult.ok ? clientsResult.data : [];
  const quoteTypes = quoteTypesResult.ok ? quoteTypesResult.data : [];
  const catalogs = catalogsResult.ok ? catalogsResult.data : [];
  const paymentPlans = paymentPlansResult.ok ? paymentPlansResult.data : [];
  const cgvVersions = cgvVersionsResult.ok ? cgvVersionsResult.data : [];
  const locations = locationsResult.ok ? locationsResult.data : [];
  const activities = activitiesResult.ok ? activitiesResult.data : [];
  const products = productsResult.ok ? productsResult.data : [];
  const kits = kitsResult.ok ? kitsResult.data : [];
  const solfegeRules = solfegeRulesResult.ok ? solfegeRulesResult.data : [];
  const quotes = quotesResult.ok ? quotesResult.data : [];

  let detailResult: Awaited<ReturnType<typeof backendRequest<QuoteDetailOut>>> | null = null;
  let followupsResult: Awaited<ReturnType<typeof backendRequest<QuoteFollowupOut[]>>> | null = null;
  if (selectedQuoteId) {
    detailResult = await backendRequest<QuoteDetailOut>(`/api/v1/quotes/${encodeURIComponent(selectedQuoteId)}`, {}, token);
    followupsResult = await backendRequest<QuoteFollowupOut[]>(`/api/v1/quote-followups?quote_id=${encodeURIComponent(selectedQuoteId)}`, {}, token);
  }

  const selectedDetail = detailResult && detailResult.ok ? detailResult.data : null;
  const followups = followupsResult && followupsResult.ok ? followupsResult.data : [];
  const activeFollowup = followups[0] ?? null;

  const prospectById = new Map(prospects.map((row) => [row.id, row]));
  const clientById = new Map(clients.map((row) => [row.id, row]));

  const basePath = quotesBasePath(statusFilter, contextFilter, query);

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h2>Devis</h2>
        <p className="muted">Wizard BO, envoi public, actions sticky et suivi post-approbation dans un seul espace.</p>
      </section>

      {!quotesResult.ok ? <section className="flash-err">Erreur devis: {quotesResult.message}</section> : null}
      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}

      <section className="card">
        <h3>Nouveau prospect rapide</h3>
        <form action={createQuoteProspectAction} className="grid cols-4 top-gap-sm">
          <input type="hidden" name="return_to" value={basePath} />
          <label>
            Prenom
            <input type="text" name="prospect_first_name" placeholder="Prenom" />
          </label>
          <label>
            Nom
            <input type="text" name="prospect_last_name" placeholder="Nom" />
          </label>
          <label>
            Email
            <input type="email" name="prospect_email" placeholder="email@exemple.com" required />
          </label>
          <label>
            Telephone
            <input type="text" name="prospect_phone" placeholder="06..." />
          </label>
          <div className="row end cols-span-4 top-gap-sm">
            <button type="submit">Creer prospect</button>
          </div>
        </form>
      </section>

      <QuoteWizardForm
        returnTo={basePath}
        prospects={prospects.map((row) => ({
          id: row.id,
          label: displayName(row.first_name, row.last_name, row.email),
          email: row.email,
        }))}
        clients={clients.map((row) => ({
          id: row.id,
          label: displayName(row.first_name, row.last_name, row.email),
          email: row.email,
        }))}
        quoteTypes={quoteTypes.map((row) => ({ id: row.id, name: row.name }))}
        catalogs={catalogs.map((row) => ({ id: row.id, name: row.name }))}
        paymentPlans={paymentPlans.map((row) => ({ id: row.id, name: row.name, payment_method: row.payment_method }))}
        cgvVersions={cgvVersions.map((row) => ({ id: row.id, version_label: row.version_label }))}
        locations={locations.map((row) => ({ id: row.id, name: row.name }))}
        activities={activities.map((row) => ({
          id: row.id,
          name: row.name,
          duration_minutes: row.duration_minutes,
          default_course_rate_ttc: row.default_course_rate_ttc,
        }))}
        products={products.map((row) => ({ id: row.id, title: row.title, price_incl_vat: row.price_incl_vat }))}
        kits={kits.map((row) => ({ id: row.id, title: row.title, effective_price_ttc: row.price_effective_incl_vat }))}
        solfegeRules={solfegeRules.map((row) => ({
          id: row.id,
          level_code: row.level_code,
          duration_minutes: row.duration_minutes,
          allowed_weekdays: row.allowed_weekdays,
          allowed_time_slots: row.allowed_time_slots,
        }))}
        defaultProspectId={selectedProspectId}
        createAction={createQuoteDraftAction}
      />

      <section className="card">
        <h3>Liste des devis</h3>
        <form method="get" className="grid cols-4 sticky-filters top-gap-sm">
          <label>
            Statut
            <select name="status" defaultValue={statusFilter}>
              <option value="">Tous</option>
              <option value="created">created</option>
              <option value="sent">sent</option>
              <option value="change_requested">change_requested</option>
              <option value="approved">approved</option>
              <option value="rejected">rejected</option>
              <option value="expired">expired</option>
              <option value="cancelled">cancelled</option>
            </select>
          </label>
          <label>
            Contexte
            <select name="context_type" defaultValue={contextFilter}>
              <option value="">Tous</option>
              <option value="acquisition">Acquisition</option>
              <option value="active_client">Client actif</option>
            </select>
          </label>
          <label className="cols-span-2">
            Recherche (numero)
            <input type="text" name="q" defaultValue={query} placeholder="DV-..." />
          </label>
          <div className="row end cols-span-4 top-gap-sm">
            <button type="submit">Filtrer</button>
            <a className="ghost" href="/admin/quotes">Reset</a>
          </div>
        </form>

        <div className="table-wrap top-gap-sm">
          <table className="data-table">
            <thead>
              <tr>
                <th>Numero</th>
                <th>Contexte</th>
                <th>Prospect / client</th>
                <th>Statut</th>
                <th>Total</th>
                <th>Creation</th>
                <th>Expiration</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {quotes.length === 0 ? (
                <tr>
                  <td colSpan={8}><p className="muted">Aucun devis sur ces filtres.</p></td>
                </tr>
              ) : (
                quotes.map((row) => {
                  const quoteParams = new URLSearchParams();
                  if (statusFilter) quoteParams.set("status", statusFilter);
                  if (contextFilter) quoteParams.set("context_type", contextFilter);
                  if (query) quoteParams.set("q", query);
                  quoteParams.set("quote_id", row.id);

                  const owner = row.context_type === "acquisition"
                    ? prospectById.get(row.prospect_id || "")
                    : clientById.get(row.client_id || "");
                  const ownerName = owner
                    ? displayName(
                        owner.first_name,
                        owner.last_name,
                        owner.email,
                      )
                    : "-";

                  return (
                    <tr key={row.id}>
                      <td>
                        <strong>{row.quote_number}</strong>
                        <br />
                        <small className="muted">{row.quote_type}</small>
                      </td>
                      <td>{labelForContext(row.context_type)}</td>
                      <td>
                        <strong>{ownerName}</strong>
                        <br />
                        <small className="muted">{owner?.email ?? "-"}</small>
                      </td>
                      <td><span className={`status-pill ${quoteStatusClass(row.status)}`}>{row.status}</span></td>
                      <td>{formatAmount(row.total_ttc, row.currency)}</td>
                      <td>{formatDate(row.created_at)}</td>
                      <td>{formatDate(row.expires_at)}</td>
                      <td>
                        <a className="ghost" href={`/admin/quotes?${quoteParams.toString()}`}>Detail</a>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      {selectedQuoteId ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-panel-wide quote-detail-panel">
            <a className="modal-close-x" href={basePath} aria-label="Fermer">×</a>
            {!selectedDetail ? (
              <section className="card modal-card">
                <h3>Detail devis</h3>
                <p className="flash-err">{detailResult?.ok === false ? detailResult.message : "Devis introuvable"}</p>
              </section>
            ) : (
              <>
                <header className="activity-modal-header">
                  <h2 className="modal-title">Devis {selectedDetail.quote.quote_number}</h2>
                  <p className="muted">
                    {labelForContext(selectedDetail.quote.context_type)} · {selectedDetail.quote.status} · {formatAmount(selectedDetail.quote.total_ttc, selectedDetail.quote.currency)}
                  </p>
                </header>

                <section className="card modal-card">
                  <h3>Actions</h3>
                  <div className="row wrap gap-sm top-gap-sm">
                    {selectedDetail.quote.status === "created" ? (
                      <form action={sendQuoteAction} className="row wrap gap-sm">
                        <input type="hidden" name="quote_id" value={selectedDetail.quote.id} />
                        <input type="hidden" name="return_to" value={`/admin/quotes?quote_id=${encodeURIComponent(selectedDetail.quote.id)}`} />
                        <input type="email" name="recipient_email" placeholder="Email destinataire (optionnel)" />
                        <button type="submit">Envoyer le devis</button>
                      </form>
                    ) : null}

                    <form action={duplicateQuoteAction}>
                      <input type="hidden" name="quote_id" value={selectedDetail.quote.id} />
                      <input type="hidden" name="return_to" value={basePath} />
                      <button type="submit" className="ghost">Dupliquer en nouvelle version</button>
                    </form>

                    {selectedDetail.quote.public_token ? (
                      <>
                        <Link
                          className="ghost"
                          href={`/q/${selectedDetail.quote.id}?t=${encodeURIComponent(selectedDetail.quote.public_token)}`}
                          target="_blank"
                        >
                          Ouvrir page publique
                        </Link>
                        <CopyLinkButton
                          value={`${process.env.NEXT_PUBLIC_FRONTEND_URL ?? "http://localhost:3000"}/q/${selectedDetail.quote.id}?t=${selectedDetail.quote.public_token}`}
                          label="Copier lien public"
                        />
                      </>
                    ) : (
                      <small className="muted">Le lien public sera disponible apres envoi.</small>
                    )}

                    {selectedDetail.quote.pdf_token ? (
                      <Link
                        className="ghost"
                        href={`/q/${selectedDetail.quote.id}/pdf?t=${encodeURIComponent(selectedDetail.quote.pdf_token)}`}
                        target="_blank"
                      >
                        PDF public
                      </Link>
                    ) : null}
                    <Link className="ghost" href={`/admin/quotes/${selectedDetail.quote.id}/pdf`} target="_blank">
                      PDF admin
                    </Link>
                  </div>
                </section>

                <section className="card modal-card">
                  <h3>Calendrier previsionnel</h3>
                  <p className="muted">{getCalendarSessions(selectedDetail.quote.calendar_snapshot).length} seances calculees.</p>
                  <div className="quote-public-lines top-gap-sm">
                    {getCalendarSessions(selectedDetail.quote.calendar_snapshot).slice(0, 12).map((session, index) => (
                      <article key={`session-${index}`} className="quote-public-line-item">
                        <strong>{String(session.date ?? "-")}</strong>
                        <span>{String(session.start_time ?? "--:--")} - {String(session.end_time ?? "--:--")}</span>
                        <small className="muted">{String(session.modality ?? "")}</small>
                      </article>
                    ))}
                  </div>
                </section>

                <section className="card modal-card">
                  <h3>Lignes du devis</h3>
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Type</th>
                          <th>Intitule</th>
                          <th>Quantite</th>
                          <th>PU TTC</th>
                          <th>Montant TTC</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedDetail.lines.length === 0 ? (
                          <tr><td colSpan={5}>Aucune ligne</td></tr>
                        ) : (
                          selectedDetail.lines.map((row) => (
                            <tr key={row.id}>
                              <td>{row.line_type}</td>
                              <td>{row.title}</td>
                              <td>{row.quantity}</td>
                              <td>{formatAmount(row.unit_price_ttc, selectedDetail.quote.currency)}</td>
                              <td>{formatAmount(row.amount_ttc, selectedDetail.quote.currency)}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </section>

                <section className="card modal-card">
                  <h3>Parcours post-approbation</h3>
                  {activeFollowup ? (
                    <>
                      <p className="muted">
                        Statut follow-up: <strong>{activeFollowup.status}</strong> · Paiement: <strong>{activeFollowup.payment_method_status}</strong> · Solfege: <strong>{activeFollowup.solfege_slot_status}</strong>
                      </p>

                      <div className="grid cols-2 top-gap-sm">
                        <form action={selectQuoteFollowupSlotAction} className="card quote-followup-form">
                          <h4>Selectionner / modifier le creneau solfege</h4>
                          <input type="hidden" name="followup_id" value={activeFollowup.id} />
                          <input type="hidden" name="return_to" value={`/admin/quotes?quote_id=${encodeURIComponent(selectedDetail.quote.id)}`} />
                          <label>
                            Date
                            <input type="date" name="slot_date" required />
                          </label>
                          <label>
                            Debut
                            <input type="time" name="slot_start_time" required />
                          </label>
                          <label>
                            Fin
                            <input type="time" name="slot_end_time" required />
                          </label>
                          <button type="submit">Enregistrer creneau</button>
                        </form>

                        <form action={changeQuoteFollowupPaymentMethodAction} className="card quote-followup-form">
                          <h4>Changer le mode de paiement</h4>
                          <input type="hidden" name="followup_id" value={activeFollowup.id} />
                          <input type="hidden" name="return_to" value={`/admin/quotes?quote_id=${encodeURIComponent(selectedDetail.quote.id)}`} />
                          <label>
                            Methode
                            <select name="payment_method_code" required>
                              <option value="">Selectionner</option>
                              {Array.from(new Set(paymentPlans.map((row) => row.payment_method))).map((method) => (
                                <option key={method} value={method}>{method}</option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Plan de paiement (optionnel)
                            <select name="payment_plan_id" defaultValue="">
                              <option value="">Aucun</option>
                              {paymentPlans.map((row) => (
                                <option key={row.id} value={row.id}>{row.name}</option>
                              ))}
                            </select>
                          </label>
                          <button type="submit">Mettre a jour paiement</button>
                        </form>
                      </div>

                      <form action={finalizeQuoteFollowupAction} className="row top-gap-sm">
                        <input type="hidden" name="followup_id" value={activeFollowup.id} />
                        <input type="hidden" name="return_to" value={`/admin/quotes?quote_id=${encodeURIComponent(selectedDetail.quote.id)}`} />
                        <button type="submit">Finaliser le parcours post-approbation</button>
                      </form>
                    </>
                  ) : (
                    <p className="muted">Aucun follow-up actif pour ce devis. Il sera cree automatiquement apres approbation du devis.</p>
                  )}
                </section>

                <section className="card modal-card">
                  <h3>Echeancier snapshot</h3>
                  <div className="quote-public-lines top-gap-sm">
                    {getScheduleItems(selectedDetail.quote.payment_terms_snapshot).length === 0 ? (
                      <p className="muted">Aucun echeancier.</p>
                    ) : (
                      getScheduleItems(selectedDetail.quote.payment_terms_snapshot).map((item, index) => (
                        <article key={`schedule-${index}`} className="quote-public-line-item">
                          <strong>{String(item.label ?? `Echeance ${index + 1}`)}</strong>
                          <span>{String(item.due_label ?? item.due_type ?? "-")}</span>
                          <small>{String(item.amount_ttc ?? "0")} {selectedDetail.quote.currency}</small>
                        </article>
                      ))
                    )}
                  </div>
                </section>
              </>
            )}
          </article>
        </section>
      ) : null}
    </section>
  );
}
