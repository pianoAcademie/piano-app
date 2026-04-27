import Link from "next/link";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import AdminBreadcrumb from "../../components/admin-breadcrumb";
import AdminSidebar from "../../components/admin-sidebar";
import { getAdminToken } from "../../lib/auth-cookies";
import { logoutAction } from "../../lib/actions";
import { backendRequest } from "../../lib/backend";
import type { UserOut } from "../../lib/types";
import { normalizeUiLanguage, uiText } from "../../lib/ui-i18n";

export default async function AdminLayout({ children }: { children: React.ReactNode }): Promise<JSX.Element> {
  const token = getAdminToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error=Acces%20admin%20requis");
  }

  const displayName = [meResult.data.first_name, meResult.data.last_name].filter(Boolean).join(" ") || meResult.data.email;
  const language = normalizeUiLanguage(meResult.data.preferred_language);

  return (
    <div className="admin-shell" data-ui-language={language}>
      <AdminSidebar
        displayName={displayName}
        email={meResult.data.email}
        roleLabel={uiText(language, "common.administrator")}
        language={language}
      />

      <div className="admin-main">
        <header className="admin-topbar">
          <div className="admin-topbar-left">
            <strong className="admin-topbar-title">{uiText(language, "admin.portal_title")}</strong>
            <Suspense fallback={<span className="muted">...</span>}>
              <AdminBreadcrumb compact language={language} />
            </Suspense>
          </div>
          <div className="row admin-topbar-actions">
            <Link className="reset-link topbar-btn" href="/client?tab=home">
              {uiText(language, "admin.client_view")}
            </Link>
            <form action={logoutAction}>
              <button className="ghost topbar-btn" type="submit">
                {uiText(language, "common.logout")}
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
