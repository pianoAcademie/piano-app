"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}): JSX.Element {
  useEffect(() => {
    const message = String(error?.message ?? "");
    const isChunkLoadError =
      message.includes("Loading chunk") || message.includes("ChunkLoadError") || message.includes("Failed to fetch dynamically imported module");
    if (!isChunkLoadError) {
      return;
    }

    const marker = "root-chunk-reload-once";
    if (sessionStorage.getItem(marker) === "1") {
      sessionStorage.removeItem(marker);
      return;
    }

    sessionStorage.setItem(marker, "1");
    const url = new URL(window.location.href);
    url.searchParams.set("_chunk_retry", String(Date.now()));
    window.location.replace(url.toString());
  }, [error]);

  return (
    <html lang="fr">
      <body>
        <main style={{ padding: 24 }}>
          <section className="card">
            <h2>Erreur d affichage</h2>
            <p className="muted">Une erreur JavaScript est survenue. Rechargez la page puis reessayez.</p>
            {error?.message ? <p className="muted">Detail: {error.message}</p> : null}
            <div className="row">
              <button type="button" onClick={() => reset()}>
                Reessayer
              </button>
              <button type="button" className="ghost" onClick={() => window.location.reload()}>
                Recharger la page
              </button>
            </div>
          </section>
        </main>
      </body>
    </html>
  );
}
