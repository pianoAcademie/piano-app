import Link from "next/link";
import { redirect } from "next/navigation";

import { adminSavePartitionPiecesAction } from "../../../lib/actions";
import { getAdminToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import type { RepertoirePartitionOut } from "../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export default async function PartitionsPage({ searchParams = {} }: { searchParams?: SearchParams }) {
  const token = getAdminToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const result = await backendRequest<RepertoirePartitionOut[]>("/api/v1/repertoire/partitions", {}, token);
  if (!result.ok) {
    return <section className="flash-err">{result.message}</section>;
  }

  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");

  return (
    <main className="page-shell stack">
      <header className="row spread">
        <div>
          <h1>Partitions et morceaux</h1>
          <p className="muted">Bibliothèque pédagogique utilisée sur les fiches élèves et pendant les cours.</p>
        </div>
        <Link href="/admin">Retour au portail</Link>
      </header>

      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}

      {result.data.map((partition) => {
        const emptyRows = Array.from({ length: Math.max(3, 10 - partition.pieces.length) }, () => null);
        return (
          <article className="card" key={partition.product_id}>
            <h2>{partition.title}</h2>
            <p className="muted">Les morceaux sont proposés au professeur dans cet ordre.</p>
            <form action={adminSavePartitionPiecesAction} className="stack">
              <input type="hidden" name="product_id" value={partition.product_id} />
              <input type="hidden" name="return_to" value="/admin/partitions" />
              {[...partition.pieces, ...emptyRows].map((piece, index) => (
                <div className="grid cols-2" key={piece?.id ?? `new-${index}`}>
                  <input type="hidden" name="piece_id" value={piece?.id ?? ""} />
                  <label>
                    Morceau {index + 1}
                    <input name="piece_title" defaultValue={piece?.title ?? ""} placeholder="Titre du morceau" />
                  </label>
                  <label>
                    Vidéo en ligne
                    <input
                      type="url"
                      name="piece_video_url"
                      defaultValue={piece?.video_url ?? ""}
                      placeholder="https://…"
                    />
                  </label>
                </div>
              ))}
              <button type="submit">Enregistrer les morceaux</button>
            </form>
          </article>
        );
      })}

      {result.data.length === 0 ? (
        <section className="card">
          <p>Aucun produit de catégorie « partition » n’est actif dans le catalogue.</p>
        </section>
      ) : null}
    </main>
  );
}
