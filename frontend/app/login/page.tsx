import Link from "next/link";

import { forgotPasswordAction, loginAction, registerAction, resetPasswordAction } from "../../lib/actions";
import AuthSignupFields from "../../components/auth-signup-fields";
import { COUNTRY_OPTIONS, DEFAULT_COUNTRY } from "../../lib/reference-data";

type SearchParams = Record<string, string | string[] | undefined>;
type AuthMode = "login" | "signup" | "forgot";

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

export default function LoginPage({ searchParams }: { searchParams: SearchParams }): JSX.Element {
  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error");
  const resetToken = readParam(searchParams, "reset_token");
  const emailHint = readParam(searchParams, "email");
  const purchaseContext = readParam(searchParams, "purchase_context");
  const returnTo = readParam(searchParams, "return_to");
  const registrationSubjectType = readParam(searchParams, "registration_subject_type").trim().toLowerCase() === "child" ? "child" : "self";
  const mode = resolveMode(readParam(searchParams, "mode").trim().toLowerCase(), resetToken);
  const preservedPurchaseContext = purchaseContext ? `&purchase_context=${encodeURIComponent(purchaseContext)}` : "";
  const preservedReturnTo = returnTo ? `&return_to=${encodeURIComponent(returnTo)}` : "";
  const preservedEmail = emailHint ? `&email=${encodeURIComponent(emailHint)}` : "";
  const preservedRegistrationSubjectType =
    registrationSubjectType === "child" ? `&registration_subject_type=${encodeURIComponent(registrationSubjectType)}` : "";
  const loginHref = `/login?mode=login${preservedEmail}${preservedPurchaseContext}${preservedReturnTo}${preservedRegistrationSubjectType}`;
  const signupHref = `/login?mode=signup${preservedEmail}${preservedPurchaseContext}${preservedReturnTo}${preservedRegistrationSubjectType}`;
  const forgotHref = `/login?mode=forgot${preservedEmail}${preservedPurchaseContext}${preservedReturnTo}${preservedRegistrationSubjectType}`;

  return (
    <main className="page auth-page">
      <section className="auth-shell">
        <header className="auth-header">
          <h1>Piano Academie</h1>
          <p>Accedez a votre espace client pour reserver vos cours, gerer vos informations et suivre vos inscriptions.</p>
        </header>

        {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
        {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

        <article className="card auth-card">
          <nav className="auth-tabs" aria-label="Navigation authentification">
            <Link className={`auth-tab ${mode === "login" ? "active" : ""}`} href={loginHref}>
              Se connecter
            </Link>
            <Link className={`auth-tab ${mode === "signup" ? "active" : ""}`} href={signupHref}>
              Creer un compte
            </Link>
          </nav>

          {mode === "login" ? (
            <section className="auth-section">
              <h2>Connexion</h2>
              <p className="muted">Utilisez votre compte existant pour acceder a votre espace client.</p>
              <form action={loginAction} className="grid auth-form">
                <input type="hidden" name="auth_mode" value="login" />
                <input type="hidden" name="purchase_context" value={purchaseContext} />
                <input type="hidden" name="return_to" value={returnTo} />
                <input type="hidden" name="registration_subject_type" value={registrationSubjectType} />
                <label>
                  Email
                  <input type="email" name="email" required autoComplete="email" defaultValue={emailHint} />
                </label>
                <label>
                  Mot de passe
                  <input type="password" name="password" required minLength={8} autoComplete="current-password" />
                </label>
                <button type="submit">Se connecter</button>
              </form>
              <div className="auth-links">
                <Link href={forgotHref}>Mot de passe oublie ?</Link>
                <Link href={signupHref}>Creer un compte</Link>
              </div>
            </section>
          ) : null}

          {mode === "forgot" ? (
            <section className="auth-section">
              {resetToken ? (
                <>
                  <h2>Reinitialiser votre mot de passe</h2>
                  <p className="muted">Choisissez un nouveau mot de passe pour votre compte.</p>
                  <form action={resetPasswordAction} className="grid auth-form">
                    <input type="hidden" name="token" value={resetToken} />
                    <label>
                      Nouveau mot de passe
                      <input type="password" name="password" required minLength={8} autoComplete="new-password" />
                    </label>
                    <label>
                      Confirmer le mot de passe
                      <input type="password" name="password_confirm" required minLength={8} autoComplete="new-password" />
                    </label>
                    <button type="submit">Mettre a jour le mot de passe</button>
                  </form>
                </>
              ) : (
                <>
                  <h2>Reinitialiser votre mot de passe</h2>
                  <p className="muted">Saisissez votre adresse email pour recevoir un lien de reinitialisation.</p>
                  <form action={forgotPasswordAction} className="grid auth-form">
                    <input type="hidden" name="auth_mode" value="forgot" />
                    <input type="hidden" name="purchase_context" value={purchaseContext} />
                    <input type="hidden" name="return_to" value={returnTo} />
                    <label>
                      Email
                      <input type="email" name="email" required autoComplete="email" defaultValue={emailHint} />
                    </label>
                    <button type="submit">Envoyer le lien</button>
                  </form>
                </>
              )}
              <div className="auth-links">
                <Link href={loginHref}>Retour a la connexion</Link>
              </div>
            </section>
          ) : null}

          {mode === "signup" ? (
            <section className="auth-section">
              <h2>Creer un compte</h2>
              <p className="muted">Renseignez les informations de base puis validez les consentements. La photo eleve est facultative.</p>

              <ol className="auth-step-indicator">
                <li>Etape 1 - Informations obligatoires</li>
                <li>Etape 2 - Photo de l eleve (optionnel)</li>
                <li>Etape 3 - Consentements et validation</li>
              </ol>

              <form action={registerAction} className="grid auth-form" encType="multipart/form-data">
                <input type="hidden" name="auth_mode" value="signup" />
                <input type="hidden" name="purchase_context" value={purchaseContext} />
                <input type="hidden" name="return_to" value={returnTo} />
                <AuthSignupFields
                  emailHint={emailHint}
                  defaultCountry={DEFAULT_COUNTRY}
                  countryOptions={COUNTRY_OPTIONS}
                  defaultRegistrationSubjectType={registrationSubjectType}
                />

                <section className="auth-step-card auth-consent-card">
                  <h3>Etape 3 - Consentements et validation</h3>
                  <div className="auth-consent-copy">
                    <p>
                      En creant votre compte, vous autorisez Piano Academie a vous envoyer les emails et SMS necessaires a la gestion de votre compte, de vos reservations et de vos cours.
                    </p>
                    <p className="muted">
                      Vous pourrez ensuite modifier vos preferences de communication depuis votre espace client et vous desinscrire des communications non essentielles.
                    </p>
                  </div>

                  <div className="auth-consent-group">
                    <p className="auth-consent-group-title">Preferences optionnelles</p>
                    <label className="auth-consent-option">
                      <input type="checkbox" name="marketing_email_opt_in" />
                      <span>
                        <strong>Recevoir les actualites et offres par email</strong>
                        <small className="muted">Informations commerciales occasionnelles de Piano Academie.</small>
                      </span>
                    </label>
                    <label className="auth-consent-option">
                      <input type="checkbox" name="marketing_sms_opt_in" />
                      <span>
                        <strong>Recevoir les actualites et offres par SMS</strong>
                        <small className="muted">Messages promotionnels ponctuels sur mobile.</small>
                      </span>
                    </label>
                  </div>

                  <div className="auth-consent-group">
                    <p className="auth-consent-group-title">Confirmations obligatoires</p>
                    <label className="auth-consent-option is-required">
                      <input type="checkbox" name="confirm_accuracy" required />
                      <span>
                        <strong>Je confirme l exactitude des informations renseignees</strong>
                        <small className="muted">Ces informations servent a creer et gerer votre compte client.</small>
                      </span>
                    </label>
                    <label className="auth-consent-option is-required">
                      <input type="checkbox" name="accept_account_terms" required />
                      <span>
                        <strong>J accepte les conditions de creation de mon compte</strong>
                        <small className="muted">Validation necessaire pour finaliser l ouverture du compte.</small>
                      </span>
                    </label>
                  </div>
                </section>

                <button type="submit">Creer mon compte</button>
              </form>

              <div className="auth-links">
                <Link href={loginHref}>J ai deja un compte</Link>
              </div>
            </section>
          ) : null}
        </article>
      </section>
    </main>
  );
}
