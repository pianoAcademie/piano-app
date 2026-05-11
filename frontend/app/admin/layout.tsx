import Link from "next/link";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import AdminBreadcrumb from "../../components/admin-breadcrumb";
import AdminSidebar from "../../components/admin-sidebar";
import { getAdminToken, getPortalReturnTo, readAdminImpersonationClaims } from "../../lib/auth-cookies";
import { endAdminImpersonationAction, logoutAction } from "../../lib/actions";
import { adminRoleLabel, hasAnyAdminAccess } from "../../lib/admin-access";
import { backendRequest } from "../../lib/backend";
import { uiLanguageFromAcceptLanguage, withUiLanguage, withUiMessageCode } from "../../lib/ui-messages";
import type { UserOut } from "../../lib/types";

export default async function AdminLayout({ children }: { children: React.ReactNode }): Promise<JSX.Element> {
  const language = uiLanguageFromAcceptLanguage(headers().get("accept-language"), "fr");
  const token = getAdminToken();
  if (!token) {
    redirect(withUiMessageCode("/login", "error", "session_expired", { lang: language }));
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || !hasAnyAdminAccess(meResult.data)) {
    redirect(withUiMessageCode("/login", "error", "admin_access_required", { lang: language }));
  }

  const displayName = [meResult.data.first_name, meResult.data.last_name].filter(Boolean).join(" ") || meResult.data.email;
  const impersonationClaims = readAdminImpersonationClaims();
  const isImpersonatingManager = Boolean(impersonationClaims?.imp && impersonationClaims.target_role === "manager");
  const impersonationReturnTo = getPortalReturnTo() ?? "/admin";

  return (
    <div className="admin-shell" data-ui-language={language}>
      <AdminSidebar
        displayName={displayName}
        email={meResult.data.email}
        roleLabel={adminRoleLabel(meResult.data, language)}
        isFullAdmin={meResult.data.role === "admin"}
        permissions={meResult.data.admin_permissions ?? {}}
      />

      <div className="admin-main">
        <header className="admin-topbar">
          <div className="admin-topbar-left">
            <strong className="admin-topbar-title">{language === "en" ? "Admin portal" : "Portail admin"}</strong>
            <Suspense fallback={<span className="muted">...</span>}>
              <AdminBreadcrumb compact />
            </Suspense>
          </div>
          <div className="row admin-topbar-actions">
            <Link className="reset-link topbar-btn" href={withUiLanguage("/client?tab=home", language)}>
              {language === "en" ? "Client view" : "Vue client"}
            </Link>
            <form action={logoutAction}>
              <button className="ghost topbar-btn" type="submit">
                {language === "en" ? "Sign out" : "Se deconnecter"}
              </button>
            </form>
          </div>
        </header>

        <section className="admin-content">
          {isImpersonatingManager ? (
            <section className="portal-impersonation-banner" role="status" aria-live="polite">
              <span>
                {language === "en" ? "Admin mode: signed in as" : "Mode admin: connecte en tant que"} <strong>{displayName}</strong>
              </span>
              <form action={endAdminImpersonationAction}>
                <input type="hidden" name="return_to" value={impersonationReturnTo} />
                <button type="submit" className="mode-link">
                  {language === "en" ? "Leave" : "Quitter"}
                </button>
              </form>
            </section>
          ) : null}
          {children}
        </section>
      </div>
    </div>
  );
}
