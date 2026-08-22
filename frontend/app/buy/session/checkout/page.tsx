import Link from "next/link";
import { redirect } from "next/navigation";

import PortalBrandLockup from "../../../../components/portal-brand-lockup";
import { startFormulaPurchaseLinkAction, submitPublicSessionCheckoutAction } from "../../../../lib/actions";
import { getPortalToken } from "../../../../lib/auth-cookies";
import { backendRequest } from "../../../../lib/backend";
import { localeForUiLanguage, normalizeUiLanguage, resolveAuthErrorMessage, resolveAuthOkMessage, translateBackendMessage, type UiLanguage, uiText } from "../../../../lib/ui-i18n";
import type {
  ClientSessionPurchaseCatalogOut,
  ClientSessionReservationMemberOptionOut,
  ClientSessionReservationOptionsOut,
  SessionOut,
  UserOut,
} from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatMoney(amountRaw: string | null, currencyRaw: string | null, language: UiLanguage): string {
  if (!amountRaw) {
    return uiText(language, "public_booking.price_to_confirm");
  }
  const amount = Number(amountRaw);
  const currency = (currencyRaw || "EUR").trim().toUpperCase() || "EUR";
  if (!Number.isFinite(amount)) {
    return `${amountRaw} ${currency}`;
  }
  try {
    return new Intl.NumberFormat(localeForUiLanguage(language), {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

function formatDateTime(value: string, timezone: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return new Intl.DateTimeFormat(localeForUiLanguage(language), {
    weekday: "long",
    day: "2-digit",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone || "Europe/Paris",
  }).format(parsed);
}

function formatTime(value: string, timezone: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "--:--";
  }
  return new Intl.DateTimeFormat(localeForUiLanguage(language), {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone || "Europe/Paris",
  }).format(parsed);
}

function buildCheckoutHref(sessionId: string, planningReturnTo: string, bookingUserId: string, language: UiLanguage): string {
  const params = new URLSearchParams();
  params.set("session_id", sessionId);
  if (planningReturnTo) {
    params.set("planning_return_to", planningReturnTo);
  }
  if (bookingUserId) {
    params.set("booking_user_id", bookingUserId);
  }
  if (language === "en") {
    params.set("lang", "en");
  }
  return `/buy/session/checkout?${params.toString()}`;
}

function memberActionLabel(option: ClientSessionReservationMemberOptionOut, language: UiLanguage): string {
  const normalized = String(option.action_code || "").trim().toUpperCase();
  if (normalized === "BOOK_WITH_CREDIT" && option.coverage_source === "TRIAL") {
    return uiText(language, "client.use_trial_credit");
  }
  if (normalized === "BOOK_WITH_CREDIT" && option.coverage_source === "MAKEUP") {
    return uiText(language, "client.use_makeup");
  }
  if (language === "fr" && option.action_label?.trim()) {
    return option.action_label;
  }
  if (normalized === "ALREADY_BOOKED" || normalized === "ALREADY_WAITLISTED") return uiText(language, "public_session_checkout.action_view_booking");
  if (normalized === "FINALIZE_PAYMENT") return uiText(language, "public_session_checkout.action_finalize_payment");
  if (normalized === "JOIN_WAITLIST") return uiText(language, "public_session_checkout.action_join_waitlist");
  if (normalized === "BOOK_WITH_CREDIT") return uiText(language, "public_session_checkout.action_book_now");
  if (normalized === "BUY_FORMULA_OR_PAY_UNIT") return uiText(language, "public_session_checkout.action_choose_option");
  if (normalized === "BUY_FORMULA") return uiText(language, "public_session_checkout.action_buy_formula");
  if (normalized === "PAY_UNIT") return uiText(language, "public_session_checkout.action_pay_and_book");
  if (normalized === "UNAVAILABLE") return uiText(language, "public_session_checkout.action_unavailable");
  return option.action_label || uiText(language, "public_session_checkout.action_unavailable");
}

function memberStatusLabel(option: ClientSessionReservationMemberOptionOut, language: UiLanguage): string {
  if (language === "fr" && option.status_label?.trim()) {
    return option.status_label;
  }
  const normalized = String(option.action_code || "").trim().toUpperCase();
  if (normalized === "ALREADY_BOOKED") return uiText(language, "public_session_checkout.status_booked");
  if (normalized === "ALREADY_WAITLISTED" || normalized === "JOIN_WAITLIST") return uiText(language, "public_session_checkout.status_waitlist");
  if (normalized === "FINALIZE_PAYMENT") return uiText(language, "public_session_checkout.status_payment_pending");
  if (normalized === "BOOK_WITH_CREDIT") {
    if (option.coverage_source === "MAKEUP") return uiText(language, "client.makeup_available");
    if (option.coverage_source === "FORFAIT") return uiText(language, "client.compatible_fixed_plan_available");
    if (option.coverage_source === "SUBSCRIPTION") return uiText(language, "client.compatible_subscription_available");
    if (option.coverage_source === "PACK") return uiText(language, "client.compatible_pack_available");
    return uiText(language, "public_session_checkout.status_credit_available");
  }
  if (normalized === "BUY_FORMULA_OR_PAY_UNIT" || normalized === "PAY_UNIT") return uiText(language, "public_session_checkout.status_payment_required");
  if (normalized === "BUY_FORMULA" || normalized === "UNAVAILABLE") return uiText(language, "public_session_checkout.status_no_coverage");
  return option.status_label || uiText(language, "public_session_checkout.status_unavailable");
}

function memberReasonLabel(option: ClientSessionReservationMemberOptionOut, language: UiLanguage): string {
  if (option.reason_code === "ACTIVE_PACK_INCOMPATIBLE") {
    return uiText(language, "public_session_checkout.reason_active_plan_incompatible");
  }
  if (language === "fr" && option.reason?.trim()) {
    return option.reason;
  }
  const normalized = String(option.action_code || "").trim().toUpperCase();
  if (normalized === "ALREADY_BOOKED") return uiText(language, "public_session_checkout.reason_already_booked");
  if (normalized === "ALREADY_WAITLISTED") return uiText(language, "public_session_checkout.reason_already_waitlisted");
  if (normalized === "FINALIZE_PAYMENT") return uiText(language, "public_session_checkout.reason_finalize_payment");
  if (normalized === "JOIN_WAITLIST") return uiText(language, "public_session_checkout.reason_join_waitlist");
  if (normalized === "BOOK_WITH_CREDIT") {
    return option.coverage_source === "MAKEUP"
      ? uiText(language, "client.makeup_covers_slot", { member: option.member_display_name })
      : option.coverage_source === "TRIAL"
      ? uiText(language, "client.trial_credit_covers_slot", { member: option.member_display_name })
      : option.coverage_source === "MANUAL_CREDIT"
      ? uiText(language, "public_session_checkout.reason_credit_manual")
      : uiText(language, "public_session_checkout.reason_credit_plan");
  }
  if (normalized === "BUY_FORMULA_OR_PAY_UNIT") return uiText(language, "public_session_checkout.reason_buy_formula_or_pay_unit");
  if (normalized === "BUY_FORMULA") return uiText(language, "public_session_checkout.reason_buy_formula");
  if (normalized === "PAY_UNIT") return uiText(language, "public_session_checkout.reason_pay_unit");
  return uiText(language, "public_session_checkout.reason_unavailable");
}

export default async function BuySessionCheckoutPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const params = searchParams ?? {};
  const queryLanguage = normalizeUiLanguage(readParam(params, "lang"));
  const sessionId = readParam(params, "session_id").trim();
  const planningReturnTo = readParam(params, "planning_return_to").trim();
  const bookingUserId = readParam(params, "booking_user_id").trim();
  const okMessage = resolveAuthOkMessage(readParam(params, "ok"), readParam(params, "ok_code"), queryLanguage);
  const errorMessage = resolveAuthErrorMessage(readParam(params, "error"), readParam(params, "error_code"), queryLanguage);
  const checkoutReturnTo = sessionId ? buildCheckoutHref(sessionId, planningReturnTo, bookingUserId, queryLanguage) : `/buy/session/checkout${queryLanguage === "en" ? "?lang=en" : ""}`;

  if (!sessionId) {
    return (
      <main className="page public-buy-page">
        <section className="public-buy-shell">
          <article className="card public-buy-card">
            <h1>{uiText(queryLanguage, "public_session_checkout.invalid_slot_title")}</h1>
            <p className="flash-err">{uiText(queryLanguage, "public_session_checkout.invalid_slot_body")}</p>
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
            <h1>{uiText(queryLanguage, "public_session_checkout.unavailable_title")}</h1>
            <p className="flash-err">{sessionResult.message}</p>
          </article>
        </section>
      </main>
    );
  }

  const session = sessionResult.data;
  const portalToken = getPortalToken();
  if (!portalToken) {
    redirect(`/login?mode=login&return_to=${encodeURIComponent(checkoutReturnTo)}${queryLanguage === "en" ? "&lang=en" : ""}`);
  }
  const authResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, portalToken);
  if (!authResult.ok) {
    redirect(
      `/login?mode=login&return_to=${encodeURIComponent(checkoutReturnTo)}&error_code=session_expired${queryLanguage === "en" ? "&lang=en" : ""}`,
    );
  }
  const me = authResult.data;
  const language = normalizeUiLanguage(readParam(params, "lang") || me.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
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
            <h1>{t("public_session_checkout.booking_unavailable_title")}</h1>
            <p className="flash-err">{reservationOptionsResult.message}</p>
            <div className="row">
              <Link className="ghost small-btn" href={planningReturnTo || `/embed/planning${language === "en" ? "?lang=en" : ""}`}>
                {t("public_session_checkout.back_to_planning")}
              </Link>
            </div>
          </article>
        </section>
      </main>
    );
  }
  const reservationOptions = reservationOptionsResult.data;
  const purchaseCatalogResult = await backendRequest<ClientSessionPurchaseCatalogOut>(
    `/api/v1/clients/me/sessions/${encodeURIComponent(sessionId)}/purchase-catalog`,
    {},
    portalToken,
  );
  const purchaseCatalog = purchaseCatalogResult.ok ? purchaseCatalogResult.data : null;
  const members = reservationOptions.members;
  const selectedMemberId = bookingUserId || (members.length === 1 ? members[0]?.member_id ?? "" : "");
  const selectedMember = members.find((option) => option.member_id === selectedMemberId) ?? null;
  const selectedMemberFormulaOptions =
    selectedMember != null
      ? selectedMember.formula_options ?? []
      : purchaseCatalog?.formula_options ?? [];
  const selectedMemberDirectPaymentAmount =
    selectedMember?.direct_payment_amount_ttc ?? purchaseCatalog?.direct_payment_amount_ttc ?? null;
  const selectedMemberDirectPaymentCurrency =
    selectedMember?.direct_payment_currency ?? purchaseCatalog?.direct_payment_currency ?? null;
  const selectedMemberEffectiveActionCode =
    selectedMember == null
      ? ""
      : selectedMember.action_code === "PAY_UNIT" && selectedMemberFormulaOptions.length > 0
        ? selectedMemberDirectPaymentAmount
          ? "BUY_FORMULA_OR_PAY_UNIT"
          : "BUY_FORMULA"
        : selectedMember.action_code;
  const coverageLabel =
    selectedMember?.coverage_source === "TRIAL"
      ? t("client.trial_credit_available")
      : selectedMember?.coverage_source === "MANUAL_CREDIT"
      ? t("public_session_checkout.coverage_manual_credit")
      : selectedMember?.coverage_source === "PACK"
        ? t("public_session_checkout.coverage_pack")
        : selectedMember?.coverage_source === "FORFAIT"
          ? t("public_session_checkout.coverage_package")
          : selectedMember?.coverage_source === "SUBSCRIPTION"
            ? t("public_session_checkout.coverage_subscription")
            : null;
  const sessionTimeLabel = `${formatTime(session.start_at_utc, session.session_timezone || session.timezone, language)} - ${formatTime(session.end_at_utc, session.session_timezone || session.timezone, language)}`;

  return (
    <main className="page public-buy-page">
      <section className="public-buy-shell">
        <article className="card public-buy-card">
          <nav className="public-buy-sticky-navigation" aria-label={t("public_session_checkout.back_to_planning")}>
            <Link
              className="mode-link public-buy-back-link"
              href={planningReturnTo || `/embed/planning${language === "en" ? "?lang=en" : ""}`}
            >
              <span aria-hidden="true">←</span>
              {t("public_session_checkout.back_to_planning")}
            </Link>
          </nav>
          <header className="public-buy-header">
            <PortalBrandLockup
              title="Piano Academie"
              subtitle={t("public_session_checkout.brand_subtitle")}
              eyebrow="Mi-Young Lee"
              className="public-buy-brand-lockup"
            />
            <h1>{t("public_session_checkout.page_title")}</h1>
            <p className="muted">{t("public_session_checkout.page_subtitle")}</p>
          </header>

          {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
          {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

          <section className="public-buy-summary">
            <article className="public-buy-line">
              <span>{t("public_session_checkout.activity_label")}</span>
              <strong>{session.title}</strong>
            </article>
            <article className="public-buy-line">
              <span>{uiText(language, "common.date")}</span>
              <strong>{formatDateTime(session.start_at_utc, session.session_timezone || session.timezone, language)}</strong>
            </article>
            <article className="public-buy-line">
              <span>{t("public_session_checkout.time_label")}</span>
              <strong>{sessionTimeLabel}</strong>
            </article>
            <article className="public-buy-line">
              <span>{uiText(language, "common.location")}</span>
              <strong>{session.location.name}</strong>
            </article>
            <article className="public-buy-line">
              <span>{t("public_session_checkout.rate_label")}</span>
              <strong>{formatMoney(session.external_booking_price_ttc, session.external_booking_currency, language)}</strong>
            </article>
            <article className="public-buy-line">
              <span>{t("public_session_checkout.availability_label")}</span>
              <strong>{reservationOptions.is_full ? t("public_session_checkout.availability_waitlist_possible") : t("public_session_checkout.availability_available")}</strong>
            </article>
          </section>

          {members.length > 1 ? (
            <section className="modal-card">
              <div className="client-session-member-picker">
                <div className="client-session-member-picker-heading">
                  <small className="muted">{t("public_session_checkout.member_label")}</small>
                  <p>{t("public_session_checkout.member_help")}</p>
                </div>
                <div className="client-session-member-grid">
                  {members.map((option) => {
                    const isSelected = option.member_id === selectedMemberId;
                    return (
                      <Link
                        key={option.member_id}
                        className={`client-session-member-card ${isSelected ? "active" : ""}`}
                        href={buildCheckoutHref(session.id, planningReturnTo, option.member_id, language)}
                        aria-current={isSelected ? "true" : undefined}
                      >
                        {isSelected ? (
                          <span className="client-session-member-selected-label">{t("public_session_checkout.member_selected")}</span>
                        ) : null}
                        <div className="client-session-member-card-head">
                          <strong>{option.member_display_name}</strong>
                          <div className="client-session-member-card-badges">
                            <span className="status-badge status-draft">{memberStatusLabel(option, language)}</span>
                          </div>
                        </div>
                        <small className="muted">{memberReasonLabel(option, language) || memberActionLabel(option, language)}</small>
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
                    <small className="muted">{t("public_session_checkout.next_step_label")}</small>
                    <p className="client-session-modal-state-title">{memberActionLabel(selectedMember, language)}</p>
                    <p>{memberReasonLabel(selectedMember, language) || t("public_session_checkout.continue_help")}</p>
                  </div>
                </div>
                {coverageLabel ? (
                  <div className="client-session-modal-state-meta">
                    <span className="badge">{coverageLabel}</span>
                    <span className="badge">{t("public_session_checkout.for_member", { member: selectedMember.member_display_name })}</span>
                  </div>
                ) : null}
              </section>

              {selectedMemberFormulaOptions.length > 0 ? (
                <section className="modal-card">
                  <small className="muted">
                    {selectedMemberEffectiveActionCode === "BUY_FORMULA_OR_PAY_UNIT"
                      ? t("public_session_checkout.formulas_alternative_for_member", { member: selectedMember.member_display_name })
                      : t("public_session_checkout.formulas_for_member", { member: selectedMember.member_display_name })}
                  </small>
                  <div className="client-plan-grid client-session-formula-grid">
                    {selectedMemberFormulaOptions.map((formula) => (
                      <article key={formula.formula_id} className="modal-card client-plan-card client-session-formula-card">
                        <div className="client-session-formula-copy">
                          <div className="client-session-choice-card-head">
                            <strong>{formula.name}</strong>
                            <span className="badge">
                              {formula.is_trial_offer ? t("client.trial_offer_badge") : t("client.plan_badge")}
                            </span>
                          </div>
                          {formula.description ? <p className="muted">{formula.description}</p> : null}
                          <small className="muted">
                            {[formula.formula_type, formula.frequency_label, ...formula.restriction_labels]
                              .filter(Boolean)
                              .map((item) => translateBackendMessage(queryLanguage, item))
                              .join(" · ")}
                          </small>
                        </div>
                        <form action={startFormulaPurchaseLinkAction} className="client-session-formula-action">
                          <input type="hidden" name="formula_id" value={formula.formula_id} />
                          <input type="hidden" name="email" value={me.email} />
                          <input type="hidden" name="session_id" value={session.id} />
                          <input type="hidden" name="booking_user_id" value={selectedMember.member_id} />
                          <input type="hidden" name="planning_return_to" value={planningReturnTo} />
                          <input type="hidden" name="language" value={language} />
                          <button type="submit" className="client-session-secondary-button">
                            {formula.is_trial_offer && formula.price_ttc
                              ? t("client.book_trial_price", {
                                  amount: formatMoney(formula.price_ttc, formula.currency, language),
                                })
                              : formula.price_ttc
                              ? t("public_session_checkout.buy_formula_for_member_price", {
                                  member: selectedMember.member_display_name,
                                  amount: formatMoney(formula.price_ttc, formula.currency, language),
                                })
                              : t("public_session_checkout.buy_formula_for_member", { member: selectedMember.member_display_name })}
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
                        {t("public_session_checkout.add_to_calendar")}
                      </Link>
                    ) : null}
                  </div>
                ) : null}

                {["BOOK_WITH_CREDIT", "FINALIZE_PAYMENT", "JOIN_WAITLIST"].includes(selectedMemberEffectiveActionCode) ? (
                  <form action={submitPublicSessionCheckoutAction} className="grid">
                    <input type="hidden" name="session_id" value={session.id} />
                    <input type="hidden" name="checkout_return_to" value={checkoutReturnTo} />
                    <input type="hidden" name="planning_return_to" value={planningReturnTo} />
                    <input type="hidden" name="booking_user_id" value={selectedMember.member_id} />
                    <button
                      type="submit"
                      className={
                        ["PAY_UNIT", "FINALIZE_PAYMENT"].includes(selectedMemberEffectiveActionCode)
                          ? "client-session-primary-button"
                          : "client-session-secondary-button"
                      }
                    >
                      {memberActionLabel(selectedMember, language)}
                      {selectedMemberEffectiveActionCode !== "BOOK_WITH_CREDIT" && selectedMemberDirectPaymentAmount
                        ? ` · ${formatMoney(selectedMemberDirectPaymentAmount, selectedMemberDirectPaymentCurrency, language)}`
                        : ""}
                    </button>
                  </form>
                ) : null}

                {["BUY_FORMULA_OR_PAY_UNIT", "PAY_UNIT"].includes(selectedMemberEffectiveActionCode) && selectedMemberDirectPaymentAmount ? (
                  <form action={submitPublicSessionCheckoutAction} className="grid">
                    <input type="hidden" name="session_id" value={session.id} />
                    <input type="hidden" name="checkout_return_to" value={checkoutReturnTo} />
                    <input type="hidden" name="planning_return_to" value={planningReturnTo} />
                    <input type="hidden" name="booking_user_id" value={selectedMember.member_id} />
                    <button type="submit" className="client-session-primary-button">
                      {t("public_session_checkout.pay_unit_price", {
                        amount: formatMoney(selectedMemberDirectPaymentAmount, selectedMemberDirectPaymentCurrency, language),
                      })}
                    </button>
                  </form>
                ) : null}

                {selectedMemberEffectiveActionCode === "UNAVAILABLE" ? (
                  <section className="flash-err">{memberReasonLabel(selectedMember, language) || t("public_session_checkout.reason_unavailable")}</section>
                ) : null}
              </div>
            </>
          ) : (
            <section className="flash-ok">
              {t("public_session_checkout.choose_member_prompt")}
            </section>
          )}

          <div className="row">
            <Link className="ghost small-btn" href={planningReturnTo || `/embed/planning${language === "en" ? "?lang=en" : ""}`}>
              {t("public_session_checkout.back_to_planning")}
            </Link>
          </div>
        </article>
      </section>
    </main>
  );
}
