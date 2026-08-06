"use client";

import Script from "next/script";

declare global {
  interface Window {
    zE?: (...args: unknown[]) => void;
  }
}

function configureZendesk(locale: "fr" | "en-US"): void {
  if (!window.zE) return;
  window.zE("messenger:set", "locale", locale);
  window.zE("messenger", "hide");
  window.zE("messenger:on", "close", () => window.zE?.("messenger", "hide"));
}

export default function ZendeskLoader({ language }: { language: "fr" | "en" }): JSX.Element {
  const locale = language === "en" ? "en-US" : "fr";
  return (
    <Script
      id="ze-snippet"
      src="https://static.zdassets.com/ekr/snippet.js?key=fa3deb6d-e96b-4ea2-b6f3-36a4c05b4bab"
      strategy="afterInteractive"
      onLoad={() => configureZendesk(locale)}
    />
  );
}
