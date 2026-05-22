import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Piano Academie Professeur",
  description: "Espace professeur Piano Academie",
  manifest: "/prof/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "PA Prof",
  },
};

export default function ProfessorLayout({ children }: { children: React.ReactNode }): JSX.Element {
  return <>{children}</>;
}
