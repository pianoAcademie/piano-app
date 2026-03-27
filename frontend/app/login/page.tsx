import Link from "next/link";

import { forgotPasswordAction, loginAction, registerAction, resetPasswordAction } from "../../lib/actions";
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
  const mode = resolveMode(readParam(searchParams, "mode").trim().toLowerCase(), resetToken);
  const preservedPurchaseContext = purchaseContext ? `&purchase_context=${encodeURIComponent(purchaseContext)}` : "";
  const preservedReturnTo = returnTo ? `&return_to=${encodeURIComponent(returnTo)}` : "";
  const preservedEmail = emailHint ? `&email=${encodeURIComponent(emailHint)}` : "";
  const loginHref = `/login?mode=login${preservedEmail}${preservedPurchaseContext}${preservedReturnTo}`;
  const signupHref = `/login?mode=signup${preservedEmail}${preservedPurchaseContext}${preservedReturnTo}`;
  const forgotHref = `/login?mode=forgot${preservedEmail}${preservedPurchaseContext}${preservedReturnTo}`;
  const isEmbedReturn = returnTo.startsWith("/embed/");

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
              <p className="muted">
                {isEmbedReturn
                  ? "Renseignez les informations de base pour finaliser votre reservation."
                  : "Renseignez les informations de base, ajoutez la photo eleve et validez les consentements."}
              </p>

              <ol className="auth-step-indicator">
                <li>Etape 1 - Informations obligatoires</li>
                {!isEmbedReturn ? <li>Etape 2 - Photo de l eleve</li> : null}
                <li>{isEmbedReturn ? "Etape 2 - Consentements et validation" : "Etape 3 - Consentements et validation"}</li>
              </ol>

              <form action={registerAction} className="grid auth-form" encType="multipart/form-data">
                <input type="hidden" name="auth_mode" value="signup" />
                <input type="hidden" name="purchase_context" value={purchaseContext} />
                <input type="hidden" name="return_to" value={returnTo} />

                <section className="auth-step-card">
                  <h3>Etape 1 - Informations obligatoires</h3>
                  <label>
                    Cette inscription concerne
                    <select name="registration_subject_type" defaultValue="self" required>
                      <option value="self">Moi-meme</option>
                      <option value="child">Mon enfant</option>
                    </select>
                  </label>
                  <label>
                    Prenom
                    <input type="text" name="first_name" required maxLength={100} autoComplete="given-name" />
                  </label>
                  <label>
                    Nom
                    <input type="text" name="last_name" required maxLength={100} autoComplete="family-name" />
                  </label>
                  <label>
                    Email
                    <input type="email" name="email" required autoComplete="email" defaultValue={emailHint} />
                  </label>
                  <label>
                    Telephone
                    <input type="tel" name="phone" required maxLength={30} autoComplete="tel" />
                  </label>
                  <label>
                    Pays de residence
                    <select name="residence_country" defaultValue={DEFAULT_COUNTRY} required>
                      {COUNTRY_OPTIONS.map((country) => (
                        <option key={country.value} value={country.value}>
                          {country.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Mot de passe
                    <input type="password" name="password" required minLength={8} autoComplete="new-password" />
                  </label>
                  <p className="muted">
                    {isEmbedReturn
                      ? "Vous pourrez ensuite revenir directement sur le planning externe pour confirmer votre reservation."
                      : "Une photo de l eleve sera demandee a l etape suivante pour faciliter l identification pendant les cours en ligne."}
                  </p>
                </section>

                {!isEmbedReturn ? (
                  <section className="auth-step-card">
                    <h3>Etape 2 - Photo de l eleve</h3>
                    <p className="muted">Cette photo est obligatoire pour finaliser la creation du compte.</p>
                    <label>
                      Prendre une photo (mobile) ou choisir une image
                      <input type="file" name="student_photo" accept="image/jpeg,image/jpg,image/png,image/webp" capture="user" required />
                    </label>
                    <p className="muted">Si la camera est indisponible, choisissez une photo existante depuis votre galerie.</p>
                  </section>
                ) : null}

                <section className="auth-step-card">
                  <h3>{isEmbedReturn ? "Etape 2 - Consentements et validation" : "Etape 3 - Consentements et validation"}</h3>
                  <p>
                    En creant votre compte, vous autorisez Piano Academie a vous envoyer des emails et SMS lies a la gestion de votre compte, de vos reservations, de vos cours et au fonctionnement du service.
                  </p>
                  <p className="muted">
                    Vous pourrez ensuite modifier vos preferences de communication depuis votre espace client et vous desinscrire des communications non essentielles.
                  </p>
                  <label className="checkline">
                    <input type="checkbox" name="marketing_email_opt_in" />
                    Je souhaite egalement recevoir les actualites et offres par email.
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="marketing_sms_opt_in" />
                    Je souhaite egalement recevoir les actualites et offres par SMS.
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="confirm_accuracy" required />
                    Je confirme l exactitude des informations renseignees.
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="accept_account_terms" required />
                    J accepte les conditions de creation de mon compte.
                  </label>
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
