import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import AdminTeacherInvoicingNav from "../../../../components/admin-teacher-invoicing-nav";
import { updateAdminTeacherInvoiceTemplateAction } from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import type { AdminTeacherInvoiceTemplateOut, UserOut } from "../../../../lib/types";
import { normalizeUiLanguage, uiText } from "../../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

export default async function AdminTeacherInvoiceTemplatePage({
  searchParams,
}: {
  searchParams: SearchParams;
}): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error=Acces%20admin%20requis");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const templateResult = await backendRequest<AdminTeacherInvoiceTemplateOut>(
    "/api/v1/admin/teacher-invoice-template",
    {},
    token,
  );
  if (!templateResult.ok) {
    return <section className="flash-err">{t("admin.teacher_invoicing.backend_error")}: {templateResult.message}</section>;
  }

  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");
  const template = templateResult.data;

  return (
    <section className="admin-page-grid">
      <AdminTeacherInvoicingNav activeTab="template" language={language} />

      <article className="card">
        <div className="row spread">
          <h3>{t("admin.teacher_invoicing.invoice_template")}</h3>
          <Link className="reset-link" href="/admin/teacher-invoicing">
            {t("admin.teacher_invoicing.back_module")}
          </Link>
        </div>
        <p className="muted">
          {t("admin.teacher_invoicing.template_subtitle")}
        </p>
      </article>

      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}

      <article className="card">
        <div className="row spread">
          <strong>{t("admin.teacher_invoicing.available_variables")}</strong>
          <span className="badge">v{template.version}</span>
        </div>
        <p className="muted">{template.variables.join(", ")}</p>
      </article>

      <article className="card">
        <form action={updateAdminTeacherInvoiceTemplateAction} className="grid">
          <label>
            {t("admin.teacher_invoicing.html_template")}
            <textarea name="html_template" rows={24} defaultValue={template.html_template} />
          </label>
          <div className="row">
            <button type="submit">{t("admin.teacher_invoicing.save_template")}</button>
            <a className="mode-link" href="/admin/teacher-invoicing/template/preview">
              {t("admin.teacher_invoicing.preview_pdf")}
            </a>
          </div>
        </form>
      </article>
    </section>
  );
}
