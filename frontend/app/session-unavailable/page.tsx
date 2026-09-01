import Link from "next/link";

type SearchParams = Record<string, string | string[] | undefined>;

function safeReturnTo(value: string | string[] | undefined): string {
  const candidate = Array.isArray(value) ? value[0] : value;
  if (!candidate || !candidate.startsWith("/") || candidate.startsWith("//")) return "/";
  return candidate;
}

export default function SessionUnavailablePage({ searchParams }: { searchParams: SearchParams }): JSX.Element {
  const returnTo = safeReturnTo(searchParams.return_to);
  return (
    <main className="page auth-page">
      <section className="card auth-card">
        <h1>Connexion momentanément indisponible</h1>
        <p>
          Votre session a été conservée. Le service n’a simplement pas répondu à temps.
          Vous pouvez réessayer sans saisir à nouveau votre mot de passe.
        </p>
        <div className="row">
          <Link className="button-link" href={returnTo}>Réessayer</Link>
        </div>
      </section>
    </main>
  );
}
