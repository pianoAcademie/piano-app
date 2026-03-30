import Link from "next/link";
import { redirect } from "next/navigation";

import { submitPublicSessionCheckoutAction } from "../../../../lib/actions";
import { getPortalToken } from "../../../../lib/auth-cookies";
import { backendRequest } from "../../../../lib/backend";
import type { SessionOut, UserOut } from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatMoney(amountRaw: string | null, currencyRaw: string | null): string {
  if (!amountRaw) {
    return "Tarif a confirmer";
  }
  const amount = Number(amountRaw);
  const currency = (currencyRaw || "EUR").trim().toUpperCase() || "EUR";
  if (!Number.isFinite(amount)) {
    return `${amountRaw} ${currency}`;
  }
  try {
    return new Intl.NumberFormat("fr-FR", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

function formatDateTime(value: string, timezone: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return new Intl.DateTimeFormat("fr-FR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone || "Europe/Paris",
  }).format(parsed);
}

function buildCheckoutHref(sessionId: string, planningReturnTo: string): string {
  const params = new URLSearchParams();
  params.set("session_id", sessionId);
  if (planningReturnTo) {
    params.set("planning_return_to", planningReturnTo);
  }
  return `/buy/session/checkout?${params.toString()}`;
}

export default async function BuySessionCheckoutPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const params = searchParams ?? {};
  const sessionId = readParam(params, "session_id").trim();
  const planningReturnTo = readParam(params, "planning_return_to").trim();
  const okMessage = readParam(params, "ok");
  const errorMessage = readParam(params, "error");
  const checkoutReturnTo = sessionId ? buildCheckoutHref(sessionId, planningReturnTo) : "/buy/session/checkout";

  if (!sessionId) {
    return (
      <main className="page public-buy-page">
        <section className="public-buy-shell">
          <article className="card public-buy-card">
            <h1>Creneau introuvable</h1>
            <p className="flash-err">Le lien de reservation est incomplet. Reprends le planning depuis le debut.</p>
          </article>
        </section>
      </main>
    );
  }

  const sessionResult = await backendRequest<SessionOut>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}?timezone=${encodeURIComponent("Europe/Paris")}`,
  );
  if (!sessionResult.ok) {
    return (
      <main className="page public-buy-page">
        <section className="public-buy-shell">
          <article className="card public-buy-card">
            <h1>Creneau indisponible</h1>
            <p className="flash-err">{sessionResult.message}</p>
          </article>
        </section>
      </main>
    );
  }

  const session = sessionResult.data;
  const portalToken = getPortalToken();
  if (!portalToken) {
    redirect(`/login?mode=login&return_to=${encodeURIComponent(checkoutReturnTo)}`);
  }
  const authResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, portalToken);
  if (!authResult.ok) {
    redirect(
      `/login?mode=login&return_to=${encodeURIComponent(checkoutReturnTo)}&error=${encodeURIComponent(
        "Session expiree, reconnectez-vous pour poursuivre la reservation",
      )}`,
    );
  }

  const isFull = session.seats_remaining <= 0;
  const hasOnlinePrice = Boolean(session.external_booking_price_ttc);
  const submitLabel = isFull
    ? "Rejoindre la liste d attente"
    : hasOnlinePrice
      ? "Payer et reserver"
      : "Confirmer la reservation";

  return (
    <main className="page public-buy-page">
      <section className="public-buy-shell">
        <article className="card public-buy-card">
          <header className="public-buy-header">
            <h1>Reservation du creneau</h1>
            <p className="muted">Verifie les informations puis continue vers le paiement securise.</p>
          </header>

          {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
          {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

          <section className="public-buy-summary">
            <article className="public-buy-line">
              <span>Activite</span>
              <strong>{session.title}</strong>
            </article>
            <article className="public-buy-line">
              <span>Date</span>
              <strong>{formatDateTime(session.start_at_utc, session.session_timezone || session.timezone)}</strong>
            </article>
            <article className="public-buy-line">
              <span>Lieu</span>
              <strong>{session.location.name}</strong>
            </article>
            <article className="public-buy-line">
              <span>Tarif</span>
              <strong>{formatMoney(session.external_booking_price_ttc, session.external_booking_currency)}</strong>
            </article>
            <article className="public-buy-line">
              <span>Disponibilite</span>
              <strong>{isFull ? "Liste d attente" : "Reservation disponible"}</strong>
            </article>
          </section>

          <form action={submitPublicSessionCheckoutAction} className="grid public-buy-form">
            <input type="hidden" name="session_id" value={session.id} />
            <input type="hidden" name="checkout_return_to" value={checkoutReturnTo} />
            <input type="hidden" name="planning_return_to" value={planningReturnTo} />
            <button type="submit">{submitLabel}</button>
          </form>

          <div className="row">
            <Link className="ghost small-btn" href={planningReturnTo || "/embed/planning"}>
              Revenir au planning
            </Link>
          </div>
        </article>
      </section>
    </main>
  );
}
