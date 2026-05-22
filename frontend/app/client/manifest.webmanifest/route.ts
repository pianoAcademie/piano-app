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
      name: "Planning",
      short_name: "Planning",
      url: "/client?tab=planning",
      icons: [{ src: "/app-icons/piano-academie-192.png", sizes: "192x192" }],
    },
    {
      name: "Paiements",
      short_name: "Finance",
      url: "/client?tab=finance",
      icons: [{ src: "/app-icons/piano-academie-192.png", sizes: "192x192" }],
    },
    {
      name: "Messages",
      short_name: "Messages",
      url: "/client?tab=messages",
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
