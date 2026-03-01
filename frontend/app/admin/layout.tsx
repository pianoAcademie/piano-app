import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import AdminBreadcrumb from "../../components/admin-breadcrumb";
import AdminNav from "../../components/admin-nav";
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
      <aside className="admin-sidebar">
        <div className="admin-brand">Piano Academie</div>
        <div className="admin-user-card">
          <p className="admin-user-name">{displayName}</p>
          <small className="muted">Administrateur</small>
        </div>
        <AdminNav />
      </aside>

      <div className="admin-main">
        <header className="admin-topbar">
          <div className="admin-topbar-left">
            <strong>Portail admin</strong>
            <small className="muted">Planning, clients, collaborateurs, produits, configuration, reporting</small>
          </div>
          <div className="row">
            <Link className="reset-link" href="/dashboard">
              Vue client
            </Link>
            <form action={logoutAction}>
              <button className="ghost" type="submit">
                Se deconnecter
              </button>
            </form>
          </div>
        </header>

        <section className="admin-content">
          <Suspense fallback={null}>
            <AdminBreadcrumb />
          </Suspense>
          {children}
        </section>
      </div>
    </div>
  );
}
