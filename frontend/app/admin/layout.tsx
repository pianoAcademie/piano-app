import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import AdminBreadcrumb from "../../components/admin-breadcrumb";
import AdminSidebar from "../../components/admin-sidebar";
import { logoutAction } from "../../lib/actions";
import { backendRequest } from "../../lib/backend";
import type { UserOut } from "../../lib/types";

export default async function AdminLayout({ children }: { children: React.ReactNode }): Promise<JSX.Element> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error=Acces%20admin%20requis");
  }

  const displayName = [meResult.data.first_name, meResult.data.last_name].filter(Boolean).join(" ") || meResult.data.email;

  return (
    <div className="admin-shell">
      <AdminSidebar displayName={displayName} email={meResult.data.email} roleLabel="Administrateur" />

      <div className="admin-main">
        <header className="admin-topbar">
          <div className="admin-topbar-left">
            <strong className="admin-topbar-title">Portail admin</strong>
            <Suspense fallback={<span className="muted">...</span>}>
              <AdminBreadcrumb compact />
            </Suspense>
          </div>
          <div className="row admin-topbar-actions">
            <Link className="reset-link topbar-btn" href="/dashboard">
              Vue client
            </Link>
            <form action={logoutAction}>
              <button className="ghost topbar-btn" type="submit">
                Se deconnecter
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
