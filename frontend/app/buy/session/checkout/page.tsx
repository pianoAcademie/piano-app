import Link from "next/link";
import { redirect } from "next/navigation";

import PortalBrandLockup from "../../../../components/portal-brand-lockup";
import { startFormulaPurchaseLinkAction, submitPublicSessionCheckoutAction } from "../../../../lib/actions";
import { getPortalToken } from "../../../../lib/auth-cookies";
import { backendRequest } from "../../../../lib/backend";
import type { ClientSessionReservationOptionsOut, SessionOut, UserOut } from "../../../../lib/types";

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

function formatTime(value: string, timezone: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "--:--";
  }
  return new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone || "Europe/Paris",
  }).format(parsed);
}

function buildCheckoutHref(sessionId: string, planningReturnTo: string, bookingUserId: string): string {
  const params = new URLSearchParams();
  params.set("session_id", sessionId);
  if (planningReturnTo) {
    params.set("planning_return_to", planningReturnTo);
  }
  if (bookingUserId) {
    params.set("booking_user_id", bookingUserId);
  }
  return `/buy/session/checkout?${params.toString()}`;
}

export default async function BuySessionCheckoutPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const params = searchParams ?? {};
  const sessionId = readParam(params, "session_id").trim();
  const planningReturnTo = readParam(params, "planning_return_to").trim();
  const bookingUserId = readParam(params, "booking_user_id").trim();
  const okMessage = readParam(params, "ok");
  const errorMessage = readParam(params, "error");
  const checkoutReturnTo = sessionId ? buildCheckoutHref(sessionId, planningReturnTo, bookingUserId) : "/buy/session/checkout";

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
  const me = authResult.data;
  const reservationOptionsResult = await backendRequest<ClientSessionReservationOptionsOut>(
    `/api/v1/clients/me/sessions/${encodeURIComponent(sessionId)}/reservation-options`,
    {},
    portalToken,
  );
  if (!reservationOptionsResult.ok) {
    return (
      <main className="page public-buy-page">
        <section className="public-buy-shell">
          <article className="card public-buy-card">
            <h1>Reservation indisponible</h1>
            <p className="flash-err">{reservationOptionsResult.message}</p>
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
  const reservationOptions = reservationOptionsResult.data;
  const members = reservationOptions.members;
  const selectedMemberId = bookingUserId || (members.length === 1 ? members[0]?.member_id ?? "" : "");
  const selectedMember = members.find((option) => option.member_id === selectedMemberId) ?? null;
  const coverageLabel =
    selectedMember?.coverage_source === "MANUAL_CREDIT"
      ? "Credit manuel disponible"
      : selectedMember?.coverage_source === "PACK"
        ? "Carnet compatible disponible"
        : selectedMember?.coverage_source === "FORFAIT"
          ? "Forfait compatible disponible"
          : selectedMember?.coverage_source === "SUBSCRIPTION"
            ? "Abonnement compatible disponible"
            : null;
  const sessionTimeLabel = `${formatTime(session.start_at_utc, session.session_timezone || session.timezone)} - ${formatTime(session.end_at_utc, session.session_timezone || session.timezone)}`;

  return (
    <main className="page public-buy-page">
      <section className="public-buy-shell">
        <article className="card public-buy-card">
          <header className="public-buy-header">
            <PortalBrandLockup
              title="Piano Academie"
              subtitle="Reservation en ligne"
              eyebrow="Mi-Young Lee"
              className="public-buy-brand-lockup"
            />
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
              <span>Horaire</span>
              <strong>{sessionTimeLabel}</strong>
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
              <strong>{reservationOptions.is_full ? "Liste d attente possible" : "Reservation disponible"}</strong>
            </article>
          </section>

          {members.length > 1 ? (
            <section className="modal-card">
              <div className="client-session-member-picker">
                <div className="client-session-member-picker-heading">
                  <small className="muted">Membre concerne</small>
                  <p>Choisissez le membre a inscrire. Nous adaptons ensuite automatiquement l option la plus pertinente.</p>
                </div>
                <div className="client-session-member-grid">
                  {members.map((option) => {
                    const isSelected = option.member_id === selectedMemberId;
                    return (
                      <Link
                        key={option.member_id}
                        className={`client-session-member-card ${isSelected ? "active" : ""}`}
                        href={buildCheckoutHref(session.id, planningReturnTo, option.member_id)}
                        aria-current={isSelected ? "true" : undefined}
                      >
                        {isSelected ? (
                          <span className="client-session-member-selected-label">Membre selectionne</span>
                        ) : null}
                        <div className="client-session-member-card-head">
                          <strong>{option.member_display_name}</strong>
                          <div className="client-session-member-card-badges">
                            <span className="status-badge status-draft">{option.status_label}</span>
                          </div>
                        </div>
                        <small className="muted">{option.reason || option.action_label}</small>
                      </Link>
                    );
                  })}
                </div>
              </div>
            </section>
          ) : null}

          {selectedMember ? (
            <>
              <section className="modal-card client-session-modal-state">
                <div className="row spread">
                  <div className="client-session-modal-state-copy">
                    <small className="muted">Prochaine etape</small>
                    <p className="client-session-modal-state-title">{selectedMember.action_label}</p>
                    <p>{selectedMember.reason || "Continuez pour finaliser votre reservation."}</p>
                  </div>
                </div>
                {coverageLabel ? (
                  <div className="client-session-modal-state-meta">
                    <span className="badge">{coverageLabel}</span>
                    <span className="badge">{`Pour ${selectedMember.member_display_name}`}</span>
                  </div>
                ) : null}
              </section>

              {selectedMember.formula_options.length > 0 ? (
                <section className="modal-card">
                  <small className="muted">
                    {selectedMember.action_code === "BUY_FORMULA_OR_PAY_UNIT"
                      ? `Ou choisissez une formule compatible pour ${selectedMember.member_display_name}`
                      : `Formules compatibles pour ${selectedMember.member_display_name}`}
                  </small>
                  <div className="client-plan-grid client-session-formula-grid">
                    {selectedMember.formula_options.map((formula) => (
                      <article key={formula.formula_id} className="modal-card client-plan-card client-session-formula-card">
                        <div className="client-session-formula-copy">
                          <strong>{formula.name}</strong>
                          {formula.description ? <p className="muted">{formula.description}</p> : null}
                          <small className="muted">
                            {[formula.formula_type, formula.frequency_label, ...formula.restriction_labels].filter(Boolean).join(" · ")}
                          </small>
                        </div>
                        <form action={startFormulaPurchaseLinkAction} className="client-session-formula-action">
                          <input type="hidden" name="formula_id" value={formula.formula_id} />
                          <input type="hidden" name="email" value={me.email} />
                          <input type="hidden" name="session_id" value={session.id} />
                          <input type="hidden" name="booking_user_id" value={selectedMember.member_id} />
                          <input type="hidden" name="planning_return_to" value={planningReturnTo} />
                          <button type="submit" className="client-session-secondary-button">
                            {formula.price_ttc
                              ? `Acheter pour ${selectedMember.member_display_name} · ${formatMoney(formula.price_ttc, formula.currency)}`
                              : `Acheter la formule pour ${selectedMember.member_display_name}`}
                          </button>
                        </form>
                      </article>
                    ))}
                  </div>
                </section>
              ) : null}

              <div className="grid public-buy-form">
                {selectedMember.booking_id &&
                ["BOOKED", "WAITLISTED"].includes((selectedMember.booking_status || "").toUpperCase()) ? (
                  <div className="client-session-modal-booking-actions">
                    {(selectedMember.booking_status || "").toUpperCase() === "BOOKED" ? (
                      <Link className="mode-link client-session-calendar-link" href={`/client/bookings/${selectedMember.booking_id}/calendar`}>
                        Ajouter a mon agenda
                      </Link>
                    ) : null}
                  </div>
                ) : null}

                {["BOOK_WITH_CREDIT", "PAY_UNIT", "FINALIZE_PAYMENT", "JOIN_WAITLIST"].includes(selectedMember.action_code) ? (
                  <form action={submitPublicSessionCheckoutAction} className="grid">
                    <input type="hidden" name="session_id" value={session.id} />
                    <input type="hidden" name="checkout_return_to" value={checkoutReturnTo} />
                    <input type="hidden" name="planning_return_to" value={planningReturnTo} />
                    <input type="hidden" name="booking_user_id" value={selectedMember.member_id} />
                    <button
                      type="submit"
                      className={
                        ["PAY_UNIT", "FINALIZE_PAYMENT"].includes(selectedMember.action_code)
                          ? "client-session-primary-button"
                          : "client-session-secondary-button"
                      }
                    >
                      {selectedMember.action_label}
                      {selectedMember.direct_payment_amount_ttc
                        ? ` · ${formatMoney(selectedMember.direct_payment_amount_ttc, selectedMember.direct_payment_currency)}`
                        : ""}
                    </button>
                  </form>
                ) : null}

                {selectedMember.action_code === "BUY_FORMULA_OR_PAY_UNIT" && selectedMember.direct_payment_amount_ttc ? (
                  <form action={submitPublicSessionCheckoutAction} className="grid">
                    <input type="hidden" name="session_id" value={session.id} />
                    <input type="hidden" name="checkout_return_to" value={checkoutReturnTo} />
                    <input type="hidden" name="planning_return_to" value={planningReturnTo} />
                    <input type="hidden" name="booking_user_id" value={selectedMember.member_id} />
                    <button type="submit" className="client-session-primary-button">
                      {`Payer a l unite · ${formatMoney(
                        selectedMember.direct_payment_amount_ttc,
                        selectedMember.direct_payment_currency,
                      )}`}
                    </button>
                  </form>
                ) : null}

                {selectedMember.action_code === "UNAVAILABLE" ? (
                  <section className="flash-err">{selectedMember.reason || "Reservation indisponible pour ce membre."}</section>
                ) : null}
              </div>
            </>
          ) : (
            <section className="flash-ok">
              Choisissez le membre a inscrire. Nous vous proposerons ensuite automatiquement la meilleure option:
              credit disponible, formule compatible, paiement a l unite ou liste d attente.
            </section>
          )}

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
