import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Piano Academie | Reservation",
  description: "Reservation de cours piano en ligne et presentiel",
  applicationName: "Piano Academie",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Piano Academie",
  },
  formatDetection: {
    telephone: false,
  },
  icons: {
    icon: [
      { url: "/app-icons/piano-academie-192.png", sizes: "192x192", type: "image/png" },
      { url: "/app-icons/piano-academie-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/app-icons/piano-academie-180.png", sizes: "180x180", type: "image/png" }],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#111827",
};

export default function RootLayout({ children }: { children: React.ReactNode }): JSX.Element {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
