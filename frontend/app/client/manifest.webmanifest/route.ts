import { cookies } from "next/headers";

import { backendRequest } from "../../../lib/backend";
import type { UserOut } from "../../../lib/types";

function clientManifest(language: "fr" | "en") {
  const english = language === "en";
  const clientPath = (query: string) => `/client?${query}&lang=${language}`;
  return {
    name: "Piano Academie Client",
    short_name: "PA Client",
    description: english ? "Piano Academie client area" : "Espace client Piano Academie",
    id: "/client",
    start_url: "/client?source=installed_web",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#f6f7f9",
    theme_color: "#111827",
    icons: [
      {
        src: "/app-icons/piano-academie-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any maskable",
      },
      {
        src: "/app-icons/piano-academie-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any maskable",
      },
    ],
    shortcuts: [
    {
      name: english ? "My bookings" : "Mes reservations",
      short_name: english ? "Bookings" : "Reservations",
      url: clientPath("tab=planning&planning_mode=reservations"),
      icons: [{ src: "/app-icons/piano-academie-192.png", sizes: "192x192" }],
    },
    {
      name: english ? "Book a lesson" : "Reserver un cours",
      short_name: english ? "Book" : "Reserver",
      url: clientPath("tab=planning&planning_mode=book&planning_slot_filter=AVAILABLE"),
      icons: [{ src: "/app-icons/piano-academie-192.png", sizes: "192x192" }],
    },
    {
      name: english ? "Offers and purchases" : "Offres et achats",
      short_name: english ? "Offers" : "Offres",
      url: clientPath("tab=offers"),
      icons: [{ src: "/app-icons/piano-academie-192.png", sizes: "192x192" }],
    },
    {
      name: english ? "Payments" : "Paiements",
      short_name: english ? "Finance" : "Finance",
      url: clientPath("tab=finance"),
      icons: [{ src: "/app-icons/piano-academie-192.png", sizes: "192x192" }],
    },
    ],
  };
}

export async function GET(request: Request): Promise<Response> {
  const requestedLanguage = new URL(request.url).searchParams.get("lang")?.trim().toLowerCase();
  let language: "fr" | "en" = requestedLanguage === "en" || (!requestedLanguage && request.headers.get("accept-language")?.toLowerCase().startsWith("en"))
    ? "en"
    : "fr";
  if (!requestedLanguage) {
    const token = cookies().get("access_token")?.value;
    if (token) {
      const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
      if (meResult.ok) {
        language = meResult.data.preferred_language?.trim().toLowerCase() === "en" ? "en" : "fr";
      }
    }
  }
  return Response.json(clientManifest(language), {
    headers: {
      "Cache-Control": "private, max-age=3600",
      "Content-Type": "application/manifest+json",
      Vary: "Accept-Language",
    },
  });
}
