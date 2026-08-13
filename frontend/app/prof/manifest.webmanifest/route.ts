const professorManifest = {
  name: "Piano Academie Professeur",
  short_name: "PA Prof",
  description: "Espace professeur Piano Academie",
  lang: "fr",
  categories: ["education", "productivity"],
  id: "/prof",
  start_url: "/prof?source=installed_web",
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
      url: "/prof?tab=planning",
      icons: [{ src: "/app-icons/piano-academie-192.png", sizes: "192x192" }],
    },
    {
      name: "Feuilles",
      short_name: "Feuilles",
      url: "/prof/statements",
      icons: [{ src: "/app-icons/piano-academie-192.png", sizes: "192x192" }],
    },
    {
      name: "Messages",
      short_name: "Messages",
      url: "/prof?tab=messages",
      icons: [{ src: "/app-icons/piano-academie-192.png", sizes: "192x192" }],
    },
  ],
};

export function GET(): Response {
  return Response.json(professorManifest, {
    headers: {
      "Cache-Control": "public, max-age=3600",
      "Content-Type": "application/manifest+json",
    },
  });
}
