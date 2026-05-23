import Link from "next/link";
import { headers } from "next/headers";

import { forgotPasswordAction, loginAction, registerAction, resetPasswordAction } from "../../lib/actions";
import AuthSignupFields from "../../components/auth-signup-fields";
import PortalBrandLockup from "../../components/portal-brand-lockup";
import { COUNTRY_OPTIONS, DEFAULT_COUNTRY } from "../../lib/reference-data";
import { resolveAuthErrorMessage, resolveAuthOkMessage, type UiLanguage, uiText } from "../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;
type AuthMode = "login" | "signup" | "forgot";
type AuthPortal = "client" | "prof";

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function resolveMode(rawMode: string, resetToken: string): AuthMode {
  if (resetToken) {
    return "forgot";
  }
  if (rawMode === "signup") {
    return "signup";
  }
  if (rawMode === "forgot") {
    return "forgot";
  }
  return "login";
}

function resolvePortal(rawPortal: string, returnTo: string): AuthPortal {
  const normalizedPortal = rawPortal.trim().toLowerCase();
  if (normalizedPortal === "prof" || normalizedPortal === "teacher") {
    return "prof";
  }
  const normalizedReturnTo = returnTo.trim().toLowerCase();
  if (normalizedReturnTo === "/prof" || normalizedReturnTo.startsWith("/prof?")) {
    return "prof";
  }
  return "client";
}

function resolveUiLanguage(rawLanguage: string, acceptLanguage: string): UiLanguage {
  for (const candidate of [rawLanguage, acceptLanguage]) {
    const normalized = candidate.trim().toLowerCase();
    if (!normalized) {
      continue;
    }
    if (normalized === "en" || normalized.startsWith("en-")) {
      return "en";
    }
    if (normalized === "fr" || normalized.startsWith("fr-")) {
      return "fr";
    }
  }
  return "fr";
}

export default function LoginPage({ searchParams }: { searchParams: SearchParams }): JSX.Element {
  const language = resolveUiLanguage(readParam(searchParams, "lang"), headers().get("accept-language") ?? "");
  const okMessage = resolveAuthOkMessage(readParam(searchParams, "ok"), readParam(searchParams, "ok_code"), language);
  const errorMessage = resolveAuthErrorMessage(readParam(searchParams, "error"), readParam(searchParams, "error_code"), language);
  const resetToken = readParam(searchParams, "reset_token");
  const emailHint = readParam(searchParams, "email");
  const purchaseContext = readParam(searchParams, "purchase_context");
  const returnTo = readParam(searchParams, "return_to");
  const portal = resolvePortal(readParam(searchParams, "portal"), returnTo);
  const registrationSubjectType = readParam(searchParams, "registration_subject_type").trim().toLowerCase() === "child" ? "child" : "self";
  const mode = resolveMode(readParam(searchParams, "mode").trim().toLowerCase(), resetToken);
  const preservedPortal = portal === "prof" ? "&portal=prof" : "";
  const preservedPurchaseContext = purchaseContext ? `&purchase_context=${encodeURIComponent(purchaseContext)}` : "";
  const preservedReturnTo = returnTo ? `&return_to=${encodeURIComponent(returnTo)}` : "";
  const preservedEmail = emailHint ? `&email=${encodeURIComponent(emailHint)}` : "";
  const preservedRegistrationSubjectType =
    registrationSubjectType === "child" ? `&registration_subject_type=${encodeURIComponent(registrationSubjectType)}` : "";
  const preservedLanguage = language === "en" ? "&lang=en" : "";
  const loginHref = `/login?mode=login${preservedPortal}${preservedEmail}${preservedPurchaseContext}${preservedReturnTo}${preservedRegistrationSubjectType}${preservedLanguage}`;
  const signupHref = `/login?mode=signup${preservedPortal}${preservedEmail}${preservedPurchaseContext}${preservedReturnTo}${preservedRegistrationSubjectType}${preservedLanguage}`;
  const forgotHref = `/login?mode=forgot${preservedPortal}${preservedEmail}${preservedPurchaseContext}${preservedReturnTo}${preservedRegistrationSubjectType}${preservedLanguage}`;
  const displayedMode = portal === "prof" && mode === "signup" ? "login" : mode;
  const portalTitleKey = portal === "prof" ? "auth.prof_space_title" : "auth.client_space_title";
  const portalSubtitleKey = portal === "prof" ? "auth.prof_space_subtitle" : "auth.client_space_subtitle";
  const loginSubtitleKey = portal === "prof" ? "auth.prof_login_subtitle" : "auth.login_subtitle";

  return (
    <main className="page auth-page">
      <section className="auth-shell">
        <header className="auth-header">
          <PortalBrandLockup
            title={uiText(language, "common.app_name")}
            subtitle={uiText(language, "auth.portal_subtitle")}
            tone="light"
            compact
            className="auth-brand-lockup"
          />
          <div className="auth-header-copy">
            <h1>{uiText(language, portalTitleKey)}</h1>
            <p>{uiText(language, portalSubtitleKey)}</p>
          </div>
        </header>

        {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
        {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

        <article className="card auth-card">
          <nav className="auth-tabs" aria-label={uiText(language, "auth.nav_label")}>
            <Link className={`auth-tab ${displayedMode === "login" ? "active" : ""}`} href={loginHref}>
              {uiText(language, "auth.login_tab")}
            </Link>
            {portal === "client" ? (
              <Link className={`auth-tab ${displayedMode === "signup" ? "active" : ""}`} href={signupHref}>
                {uiText(language, "auth.signup_tab")}
              </Link>
            ) : null}
          </nav>

          {displayedMode === "login" ? (
            <section className="auth-section">
              <h2>{uiText(language, "auth.login_title")}</h2>
              <p className="muted">{uiText(language, loginSubtitleKey)}</p>
              <form action={loginAction} className="grid auth-form">
                <input type="hidden" name="auth_mode" value="login" />
                <input type="hidden" name="portal" value={portal} />
                <input type="hidden" name="purchase_context" value={purchaseContext} />
                <input type="hidden" name="return_to" value={returnTo} />
                <input type="hidden" name="registration_subject_type" value={registrationSubjectType} />
                <input type="hidden" name="lang" value={language} />
                <label>
                  {uiText(language, "common.email")}
                  <input type="email" name="email" required autoComplete="email" defaultValue={emailHint} />
                </label>
                <label>
                  {uiText(language, "common.password")}
                  <input type="password" name="password" required minLength={8} autoComplete="current-password" />
                </label>
                <button type="submit">{uiText(language, "auth.login_tab")}</button>
              </form>
              <div className="auth-links">
                <Link href={forgotHref}>{uiText(language, "auth.forgot_link")}</Link>
                {portal === "client" ? <Link href={signupHref}>{uiText(language, "auth.create_account_link")}</Link> : null}
              </div>
            </section>
          ) : null}

          {displayedMode === "forgot" ? (
            <section className="auth-section">
              {resetToken ? (
                <>
                  <h2>{uiText(language, "auth.reset_title")}</h2>
                  <p className="muted">{uiText(language, "auth.reset_subtitle")}</p>
                  <form action={resetPasswordAction} className="grid auth-form">
                    <input type="hidden" name="token" value={resetToken} />
                    <label>
                      {uiText(language, "common.new_password")}
                      <input type="password" name="password" required minLength={8} autoComplete="new-password" />
                    </label>
                    <label>
                      {uiText(language, "common.confirm_password")}
                      <input type="password" name="password_confirm" required minLength={8} autoComplete="new-password" />
                    </label>
                    <button type="submit">{uiText(language, "auth.update_password")}</button>
                  </form>
                </>
              ) : (
                <>
                  <h2>{uiText(language, "auth.reset_title")}</h2>
                  <p className="muted">{uiText(language, "auth.reset_request_subtitle")}</p>
                  <form action={forgotPasswordAction} className="grid auth-form">
                    <input type="hidden" name="auth_mode" value="forgot" />
                    <input type="hidden" name="portal" value={portal} />
                    <input type="hidden" name="purchase_context" value={purchaseContext} />
                    <input type="hidden" name="return_to" value={returnTo} />
                    <input type="hidden" name="lang" value={language} />
                    <label>
                      {uiText(language, "common.email")}
                      <input type="email" name="email" required autoComplete="email" defaultValue={emailHint} />
                    </label>
                    <button type="submit">{uiText(language, "auth.send_link")}</button>
                  </form>
                </>
              )}
              <div className="auth-links">
                <Link href={loginHref}>{uiText(language, "auth.back_to_login")}</Link>
              </div>
            </section>
          ) : null}

          {displayedMode === "signup" ? (
            <section className="auth-section">
              <h2>{uiText(language, "auth.signup_title")}</h2>
              <p className="muted">{uiText(language, "auth.signup_subtitle")}</p>

              <ol className="auth-step-indicator">
                <li>{uiText(language, "auth.step_1")}</li>
                <li>{uiText(language, "auth.step_2")}</li>
                <li>{uiText(language, "auth.step_3")}</li>
              </ol>

              <form action={registerAction} className="grid auth-form" encType="multipart/form-data">
                <input type="hidden" name="auth_mode" value="signup" />
                <input type="hidden" name="portal" value={portal} />
                <input type="hidden" name="purchase_context" value={purchaseContext} />
                <input type="hidden" name="return_to" value={returnTo} />
                <input type="hidden" name="lang" value={language} />
                <AuthSignupFields
                  emailHint={emailHint}
                  defaultCountry={DEFAULT_COUNTRY}
                  countryOptions={COUNTRY_OPTIONS}
                  language={language}
                  defaultRegistrationSubjectType={registrationSubjectType}
                />

                <section className="auth-step-card auth-consent-card">
                  <h3>{uiText(language, "auth.step_3")}</h3>
                  <div className="auth-consent-copy">
                    <p>{uiText(language, "auth.consent_intro")}</p>
                    <p className="muted">{uiText(language, "auth.consent_followup")}</p>
                  </div>

                  <div className="auth-consent-group">
                    <p className="auth-consent-group-title">{uiText(language, "auth.optional_preferences")}</p>
                    <label className="auth-consent-option">
                      <input type="checkbox" name="marketing_email_opt_in" />
                      <span>
                        <strong>{uiText(language, "auth.marketing_email_title")}</strong>
                        <small className="muted">{uiText(language, "auth.marketing_email_help")}</small>
                      </span>
                    </label>
                    <label className="auth-consent-option">
                      <input type="checkbox" name="marketing_sms_opt_in" />
                      <span>
                        <strong>{uiText(language, "auth.marketing_sms_title")}</strong>
                        <small className="muted">{uiText(language, "auth.marketing_sms_help")}</small>
                      </span>
                    </label>
                  </div>

                  <div className="auth-consent-group">
                    <p className="auth-consent-group-title">{uiText(language, "auth.required_confirmations")}</p>
                    <label className="auth-consent-option is-required">
                      <input type="checkbox" name="confirm_accuracy" required />
                      <span>
                        <strong>{uiText(language, "auth.confirm_accuracy_title")}</strong>
                        <small className="muted">{uiText(language, "auth.confirm_accuracy_help")}</small>
                      </span>
                    </label>
                    <label className="auth-consent-option is-required">
                      <input type="checkbox" name="accept_account_terms" required />
                      <span>
                        <strong>{uiText(language, "auth.accept_terms_title")}</strong>
                        <small className="muted">{uiText(language, "auth.accept_terms_help")}</small>
                      </span>
                    </label>
                  </div>
                </section>

                <button type="submit">{uiText(language, "auth.submit_account")}</button>
              </form>

              <div className="auth-links">
                <Link href={loginHref}>{uiText(language, "auth.already_have_account")}</Link>
              </div>
            </section>
          ) : null}
        </article>
      </section>
    </main>
  );
}
