"use client";

import { useEffect, useState } from "react";

import { normalizeUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}): JSX.Element {
  const [language, setLanguage] = useState<UiLanguage>("fr");
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  useEffect(() => {
    const languageHint =
      document.querySelector("[data-ui-language]")?.getAttribute("data-ui-language")
      || document.documentElement.getAttribute("lang")
      || navigator.language;
    setLanguage(normalizeUiLanguage(languageHint));
  }, []);

  useEffect(() => {
    const message = String(error?.message ?? "");
    const isChunkLoadError =
      message.includes("Loading chunk") || message.includes("ChunkLoadError") || message.includes("Failed to fetch dynamically imported module");
    if (!isChunkLoadError) {
      return;
    }

    const marker = "chunk-reload-once";
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
    <main style={{ padding: 24 }}>
      <section className="card">
        <h2>{t("app.error.title")}</h2>
        <p className="muted">
          {t("app.error.subtitle")}
        </p>
        {error?.message ? <p className="muted">{t("app.error.detail_prefix", { message: error.message })}</p> : null}
        <div className="row">
          <button type="button" onClick={() => reset()}>
            {t("app.error.retry")}
          </button>
          <button type="button" className="ghost" onClick={() => window.location.reload()}>
            {t("app.error.reload_page")}
          </button>
        </div>
      </section>
    </main>
  );
}
