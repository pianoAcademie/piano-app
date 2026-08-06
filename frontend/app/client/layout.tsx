import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Piano Academie Client",
  description: "Espace client Piano Academie",
  manifest: "/client/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "PA Client",
  },
};

export default function ClientLayout({ children }: { children: React.ReactNode }): JSX.Element {
  return <>{children}</>;
}
