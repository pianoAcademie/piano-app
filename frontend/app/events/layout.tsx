import PortalReadOnlyPreviewGuard from "../../components/portal-read-only-preview-guard";
import { readPortalImpersonationClaims } from "../../lib/auth-cookies";

export default function EventsLayout({ children }: { children: React.ReactNode }): JSX.Element {
  const claims = readPortalImpersonationClaims();
  const isReadOnlyPreview = Boolean(claims?.imp && claims?.preview_read_only);

  return (
    <>
      <PortalReadOnlyPreviewGuard enabled={isReadOnlyPreview} language="fr" />
      {children}
    </>
  );
}
