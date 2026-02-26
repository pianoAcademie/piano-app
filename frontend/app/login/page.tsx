import { forgotPasswordAction, loginAction, registerAction, resetPasswordAction } from "../../lib/actions";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

export default function LoginPage({ searchParams }: { searchParams: SearchParams }): JSX.Element {
  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error");
  const resetToken = readParam(searchParams, "reset_token");

  return (
    <main className="page">
      <section className="card">
        <h1>Piano Academie</h1>
        <p className="muted">Portail client V1: inscription, connexion, achat de plan et reservation.</p>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

      <section className="grid cols-2">
        {resetToken ? (
          <article className="card">
            <h2>Reinitialiser le mot de passe</h2>
            <p className="muted">Choisissez un nouveau mot de passe pour ce compte.</p>
            <form action={resetPasswordAction} className="grid">
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
          </article>
        ) : null}

        <article className="card">
          <h2>Connexion</h2>
          <p className="muted">Utilisez votre compte existant.</p>
          <form action={loginAction} className="grid">
            <label>
              Email
              <input type="email" name="email" required autoComplete="email" />
            </label>
            <label>
              Mot de passe
              <input type="password" name="password" required minLength={8} autoComplete="current-password" />
            </label>
            <button type="submit">Se connecter</button>
          </form>

          <hr />

          <h3>Mot de passe oublie ?</h3>
          <p className="muted">Saisissez votre email pour recevoir un lien de reinitialisation.</p>
          <form action={forgotPasswordAction} className="grid">
            <label>
              Email
              <input type="email" name="email" required autoComplete="email" />
            </label>
            <button type="submit">Envoyer le lien</button>
          </form>
        </article>

        <article className="card">
          <h2>Creer un compte client</h2>
          <p className="muted">Les informations de profil peuvent etre completees ici ou dans le dashboard.</p>
          <form action={registerAction} className="grid">
            <label>
              Email
              <input type="email" name="email" required autoComplete="email" />
            </label>
            <label>
              Mot de passe
              <input type="password" name="password" required minLength={8} autoComplete="new-password" />
            </label>
            <label>
              Prenom
              <input type="text" name="first_name" maxLength={100} />
            </label>
            <label>
              Nom
              <input type="text" name="last_name" maxLength={100} />
            </label>
            <label>
              Adresse
              <input type="text" name="address_line" maxLength={255} />
            </label>
            <label>
              Telephone
              <input type="text" name="phone" maxLength={30} />
            </label>
            <label>
              Pays de residence (ISO 2)
              <input type="text" name="residence_country" defaultValue="FR" minLength={2} maxLength={2} required />
            </label>
            <label>
              Devise preferee (ISO 3)
              <input type="text" name="preferred_currency" defaultValue="EUR" minLength={3} maxLength={3} required />
            </label>
            <label>
              Fuseau horaire
              <input type="text" name="timezone" defaultValue="Europe/Paris" required maxLength={100} />
            </label>
            <button type="submit">Creer le compte</button>
          </form>
        </article>
      </section>
    </main>
  );
}
