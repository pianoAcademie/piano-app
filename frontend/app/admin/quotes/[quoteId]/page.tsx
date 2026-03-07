import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import CopyLinkButton from "../../../../components/copy-link-button";
import {
  changeQuoteFollowupPaymentMethodAction,
  duplicateQuoteAction,
  finalizeQuoteFollowupAction,
  selectQuoteFollowupSlotAction,
  sendQuoteAction,
} from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import type { AdminClientOut } from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

type RouteParams = {
  params: {
    quoteId: string;
  };
  searchParams: SearchParams;
};

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

type PaymentPlanOut = {
  id: string;
  name: string;
  payment_method: string;
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

function safeBackPath(raw: string): string {
  const value = raw.trim();
  if (value.startsWith("/admin/quotes")) {
    return value;
  }
  return "/admin/quotes";
}

export default async function AdminQuoteDetailPage({ params, searchParams }: RouteParams): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const quoteId = String(params.quoteId || "").trim();
  if (!quoteId) {
    redirect("/admin/quotes?error=Devis%20introuvable");
  }

  const backPath = safeBackPath(readParam(searchParams, "back"));
  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");

  const [detailResult, followupsResult, paymentPlansResult, prospectsResult, clientsResult] = await Promise.all([
    backendRequest<QuoteDetailOut>(`/api/v1/quotes/${encodeURIComponent(quoteId)}`, {}, token),
    backendRequest<QuoteFollowupOut[]>(`/api/v1/quote-followups?quote_id=${encodeURIComponent(quoteId)}`, {}, token),
    backendRequest<PaymentPlanOut[]>("/api/v1/payment-plans", {}, token),
    backendRequest<ProspectOut[]>("/api/v1/prospects?limit=1000", {}, token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?limit=800&include_archived=false", {}, token),
  ]);

  if (!detailResult.ok) {
    return (
      <section className="admin-page-grid">
        <section className="card">
          <h2>Detail devis</h2>
          <p className="flash-err">{detailResult.message}</p>
          <div className="row top-gap-sm">
            <Link className="ghost" href={backPath}>Retour liste devis</Link>
          </div>
        </section>
      </section>
    );
  }

  const detail = detailResult.data;
  const followups = followupsResult.ok ? followupsResult.data : [];
  const activeFollowup = followups[0] ?? null;
  const paymentPlans = paymentPlansResult.ok ? paymentPlansResult.data : [];
  const prospects = prospectsResult.ok ? prospectsResult.data : [];
  const clients = clientsResult.ok ? clientsResult.data : [];

  const prospectById = new Map(prospects.map((row) => [row.id, row]));
  const clientById = new Map(clients.map((row) => [row.id, row]));

  const owner = detail.quote.context_type === "acquisition"
    ? prospectById.get(detail.quote.prospect_id || "")
    : clientById.get(detail.quote.client_id || "");

  const ownerName = owner
    ? displayName(owner.first_name, owner.last_name, owner.email)
    : "-";

  const selfPath = `/admin/quotes/${encodeURIComponent(detail.quote.id)}?back=${encodeURIComponent(backPath)}`;

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>Devis {detail.quote.quote_number}</h2>
            <p className="muted">
              {labelForContext(detail.quote.context_type)} · {detail.quote.status} · {formatAmount(detail.quote.total_ttc, detail.quote.currency)}
            </p>
            <p className="muted">Destinataire: {ownerName}</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href={backPath}>Retour liste devis</Link>
            <Link className="ghost" href="/admin/quotes/new">Nouveau devis</Link>
          </div>
        </div>
      </section>

      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}

      <section className="card">
        <h3>Actions</h3>
        <div className="row wrap gap-sm top-gap-sm">
          {detail.quote.status === "created" ? (
            <form action={sendQuoteAction} className="row wrap gap-sm">
              <input type="hidden" name="quote_id" value={detail.quote.id} />
              <input type="hidden" name="return_to" value={selfPath} />
              <input type="email" name="recipient_email" placeholder="Email destinataire (optionnel)" />
              <button type="submit">Envoyer le devis</button>
            </form>
          ) : null}

          <form action={duplicateQuoteAction}>
            <input type="hidden" name="quote_id" value={detail.quote.id} />
            <input type="hidden" name="return_to" value={selfPath} />
            <button type="submit" className="ghost">Dupliquer en nouvelle version</button>
          </form>

          {detail.quote.public_token ? (
            <>
              <Link
                className="ghost"
                href={`/q/${detail.quote.id}?t=${encodeURIComponent(detail.quote.public_token)}`}
                target="_blank"
              >
                Ouvrir page publique
              </Link>
              <CopyLinkButton
                value={`${process.env.NEXT_PUBLIC_FRONTEND_URL ?? "http://localhost:3000"}/q/${detail.quote.id}?t=${detail.quote.public_token}`}
                label="Copier lien public"
              />
            </>
          ) : (
            <small className="muted">Le lien public sera disponible apres envoi.</small>
          )}

          {detail.quote.pdf_token ? (
            <Link
              className="ghost"
              href={`/q/${detail.quote.id}/pdf?t=${encodeURIComponent(detail.quote.pdf_token)}`}
              target="_blank"
            >
              PDF public
            </Link>
          ) : null}
          <Link className="ghost" href={`/admin/quotes/${detail.quote.id}/pdf`} target="_blank">
            PDF admin
          </Link>
        </div>
      </section>

      <section className="card">
        <h3>Infos devis</h3>
        <div className="grid cols-3 top-gap-sm">
          <p><strong>Type:</strong> {detail.quote.quote_type}</p>
          <p><strong>Annee scolaire:</strong> {detail.quote.school_year_label ?? "-"}</p>
          <p><strong>Creation:</strong> {formatDate(detail.quote.created_at)}</p>
          <p><strong>Envoi:</strong> {formatDate(detail.quote.sent_at)}</p>
          <p><strong>Expiration:</strong> {formatDate(detail.quote.expires_at)}</p>
          <p><strong>Solfege:</strong> {detail.quote.estimated_solfege_level ? `Niveau ${detail.quote.estimated_solfege_level}` : "Non"}</p>
        </div>
      </section>

      <section className="card">
        <h3>Calendrier previsionnel</h3>
        <p className="muted">{getCalendarSessions(detail.quote.calendar_snapshot).length} seances calculees.</p>
        <div className="quote-public-lines top-gap-sm">
          {getCalendarSessions(detail.quote.calendar_snapshot).slice(0, 20).map((session, index) => (
            <article key={`session-${index}`} className="quote-public-line-item">
              <strong>{String(session.date ?? "-")}</strong>
              <span>{String(session.start_time ?? "--:--")} - {String(session.end_time ?? "--:--")}</span>
              <small className="muted">{String(session.modality ?? "")}</small>
            </article>
          ))}
        </div>
      </section>

      <section className="card">
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
              {detail.lines.length === 0 ? (
                <tr><td colSpan={5}>Aucune ligne</td></tr>
              ) : (
                detail.lines.map((row) => (
                  <tr key={row.id}>
                    <td>{row.line_type}</td>
                    <td>{row.title}</td>
                    <td>{row.quantity}</td>
                    <td>{formatAmount(row.unit_price_ttc, detail.quote.currency)}</td>
                    <td>{formatAmount(row.amount_ttc, detail.quote.currency)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
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
                <input type="hidden" name="return_to" value={selfPath} />
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
                <input type="hidden" name="return_to" value={selfPath} />
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
              <input type="hidden" name="return_to" value={selfPath} />
              <button type="submit">Finaliser le parcours post-approbation</button>
            </form>
          </>
        ) : (
          <p className="muted">Aucun follow-up actif pour ce devis. Il sera cree automatiquement apres approbation du devis.</p>
        )}
      </section>

      <section className="card">
        <h3>Echeancier snapshot</h3>
        <div className="quote-public-lines top-gap-sm">
          {getScheduleItems(detail.quote.payment_terms_snapshot).length === 0 ? (
            <p className="muted">Aucun echeancier.</p>
          ) : (
            getScheduleItems(detail.quote.payment_terms_snapshot).map((item, index) => (
              <article key={`schedule-${index}`} className="quote-public-line-item">
                <strong>{String(item.label ?? `Echeance ${index + 1}`)}</strong>
                <span>{String(item.due_label ?? item.due_type ?? "-")}</span>
                <small>{String(item.amount_ttc ?? "0")} {detail.quote.currency}</small>
              </article>
            ))
          )}
        </div>
      </section>
    </section>
  );
}
