import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Piano Academie | Reservation",
  description: "Reservation de cours piano en ligne et presentiel",
};

export default function RootLayout({ children }: { children: React.ReactNode }): JSX.Element {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
