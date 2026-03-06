import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import AdminTeacherInvoicingNav from "../../../../components/admin-teacher-invoicing-nav";
import { updateAdminTeacherInvoiceTemplateAction } from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import type { AdminTeacherInvoiceTemplateOut } from "../../../../lib/types";

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

  const templateResult = await backendRequest<AdminTeacherInvoiceTemplateOut>(
    "/api/v1/admin/teacher-invoice-template",
    {},
    token,
  );
  if (!templateResult.ok) {
    return <section className="flash-err">Erreur backend: {templateResult.message}</section>;
  }

  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");
  const template = templateResult.data;

  return (
    <section className="admin-page-grid">
      <AdminTeacherInvoicingNav activeTab="template" />

      <article className="card">
        <div className="row spread">
          <h3>Template de facture</h3>
          <Link className="reset-link" href="/admin/teacher-invoicing">
            Retour facturation professeurs
          </Link>
        </div>
        <p className="muted">
          Editez le template HTML stocke en base, puis testez un rendu PDF de previsualisation.
        </p>
      </article>

      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}

      <article className="card">
        <div className="row spread">
          <strong>Variables disponibles</strong>
          <span className="badge">v{template.version}</span>
        </div>
        <p className="muted">{template.variables.join(", ")}</p>
      </article>

      <article className="card">
        <form action={updateAdminTeacherInvoiceTemplateAction} className="grid">
          <label>
            Template HTML
            <textarea name="html_template" rows={24} defaultValue={template.html_template} />
          </label>
          <div className="row">
            <button type="submit">Enregistrer le modele</button>
            <a className="mode-link" href="/admin/teacher-invoicing/template/preview">
              Preview PDF
            </a>
          </div>
        </form>
      </article>
    </section>
  );
}
