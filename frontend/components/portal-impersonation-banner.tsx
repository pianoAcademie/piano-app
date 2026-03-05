import Link from "next/link";

type PortalImpersonationBannerProps = {
  displayName: string;
  returnTo: string;
};

export default function PortalImpersonationBanner({
  displayName,
  returnTo,
}: PortalImpersonationBannerProps): JSX.Element {
  const safeReturnTo = returnTo.startsWith("/admin") ? returnTo : "/admin";
  return (
    <section className="portal-impersonation-banner" role="status" aria-live="polite">
      <span>
        Mode admin: connecte en tant que <strong>{displayName}</strong>
      </span>
      <Link className="mode-link" href={safeReturnTo}>
        Quitter
      </Link>
    </section>
  );
}
