import Link from "next/link";

type SearchParams = Record<string, string | string[] | undefined>;

function safeReturnTo(value: string | string[] | undefined): string {
  const candidate = Array.isArray(value) ? value[0] : value;
  if (!candidate || !candidate.startsWith("/") || candidate.startsWith("//")) return "/";
  return candidate;
}

export default function AccessDeniedPage({ searchParams }: { searchParams: SearchParams }): JSX.Element {
  const returnTo = safeReturnTo(searchParams.return_to);
  return (
    <main className="page auth-page">
      <section className="card auth-card">
        <h1>Accès non autorisé</h1>
        <p>Votre session est toujours active, mais ce compte ne dispose pas des droits nécessaires pour cette page.</p>
        <div className="row">
          <Link className="button-link" href={returnTo}>Retour</Link>
          <Link className="ghost" href="/login">Utiliser un autre compte</Link>
        </div>
      </section>
    </main>
  );
}
