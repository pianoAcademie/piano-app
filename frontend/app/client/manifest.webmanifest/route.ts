const clientManifest = {
  name: "Piano Academie Client",
  short_name: "PA Client",
  description: "Espace client Piano Academie",
  id: "/client",
  start_url: "/client?source=mobile_app",
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
      name: "Mes reservations",
      short_name: "Reservations",
      url: "/client?tab=planning&planning_mode=reservations",
      icons: [{ src: "/app-icons/piano-academie-192.png", sizes: "192x192" }],
    },
    {
      name: "Reserver un cours",
      short_name: "Reserver",
      url: "/client?tab=planning&planning_mode=book&planning_slot_filter=AVAILABLE",
      icons: [{ src: "/app-icons/piano-academie-192.png", sizes: "192x192" }],
    },
    {
      name: "Offres et achats",
      short_name: "Offres",
      url: "/client?tab=offers",
      icons: [{ src: "/app-icons/piano-academie-192.png", sizes: "192x192" }],
    },
    {
      name: "Paiements",
      short_name: "Finance",
      url: "/client?tab=finance",
      icons: [{ src: "/app-icons/piano-academie-192.png", sizes: "192x192" }],
    },
  ],
};

export function GET(): Response {
  return Response.json(clientManifest, {
    headers: {
      "Cache-Control": "public, max-age=3600",
      "Content-Type": "application/manifest+json",
    },
  });
}
