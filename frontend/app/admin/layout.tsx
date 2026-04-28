import Link from "next/link";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import AdminBreadcrumb from "../../components/admin-breadcrumb";
import AdminSidebar from "../../components/admin-sidebar";
import { getAdminToken } from "../../lib/auth-cookies";
import { logoutAction } from "../../lib/actions";
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
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect(withUiMessageCode("/login", "error", "admin_access_required", { lang: language }));
  }

  const displayName = [meResult.data.first_name, meResult.data.last_name].filter(Boolean).join(" ") || meResult.data.email;

  return (
    <div className="admin-shell" data-ui-language={language}>
      <AdminSidebar
        displayName={displayName}
        email={meResult.data.email}
        roleLabel={language === "en" ? "Administrator" : "Administrateur"}
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
          {children}
        </section>
      </div>
    </div>
  );
}
