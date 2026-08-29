import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import AdminTeacherInvoicingNav from "../../../components/admin-teacher-invoicing-nav";
import { hasAdminPermission } from "../../../lib/admin-access";
import { backendRequest } from "../../../lib/backend";
import type { UserOut } from "../../../lib/types";
import { normalizeUiLanguage, uiText } from "../../../lib/ui-i18n";

const HUB_LINKS: Array<{ href: string; titleKey: string; descriptionKey: string }> = [
  {
    href: "/admin/teacher-invoicing/statements",
    titleKey: "admin.teacher_invoicing.statements",
    descriptionKey: "admin.teacher_invoicing.hub_statements_description",
  },
  {
    href: "/admin/teacher-invoicing/invoices",
    titleKey: "common.invoices",
    descriptionKey: "admin.teacher_invoicing.hub_invoices_description",
  },
  {
    href: "/admin/teacher-invoicing/template",
    titleKey: "admin.teacher_invoicing.invoice_template",
    descriptionKey: "admin.teacher_invoicing.hub_template_description",
  },
  {
    href: "/admin/teacher-invoicing/salary-grid",
    titleKey: "admin.teacher_invoicing.salary_grid",
    descriptionKey: "admin.teacher_invoicing.hub_salary_grid_description",
  },
];

export default async function AdminTeacherInvoicingHubPage(): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || !hasAdminPermission(meResult.data, "can_manage_invoices_and_accounts")) {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);

  return (
    <section className="admin-page-grid">
      <AdminTeacherInvoicingNav activeTab="hub" language={language} isFullAdmin={meResult.data.role === "admin"} />

      <section className="grid cols-2 teacher-invoicing-hub-grid">
        {HUB_LINKS.filter((entry) => meResult.data.role === "admin" || entry.href.endsWith("/statements") || entry.href.endsWith("/invoices")).map((entry) => (
          <article key={entry.href} className="card teacher-invoicing-hub-card">
            <h3>{uiText(language, entry.titleKey)}</h3>
            <p className="muted">{uiText(language, entry.descriptionKey)}</p>
            <div className="row top-gap-sm">
              <Link className="mode-link" href={entry.href}>
                {uiText(language, "common.open")}
              </Link>
            </div>
          </article>
        ))}
      </section>
    </section>
  );
}
