import Link from "next/link";

import { type UiLanguage, uiText } from "../lib/ui-i18n";

type PortalImpersonationBannerProps = {
  displayName: string;
  returnTo: string;
  language?: UiLanguage;
};

export default function PortalImpersonationBanner({
  displayName,
  returnTo,
  language = "fr",
}: PortalImpersonationBannerProps): JSX.Element {
  const safeReturnTo = returnTo.startsWith("/admin") ? returnTo : "/admin";
  return (
    <section className="portal-impersonation-banner" role="status" aria-live="polite">
      <span>
        {uiText(language, "portal.impersonation")} <strong>{displayName}</strong>
      </span>
      <Link className="mode-link" href={safeReturnTo}>
        {uiText(language, "portal.leave")}
      </Link>
    </section>
  );
}
