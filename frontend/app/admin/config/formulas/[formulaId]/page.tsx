import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import AdminFormulaEditor from "../../../../../components/admin-formula-editor";
import { backendRequest } from "../../../../../lib/backend";
import type {
  AdminConfigAccountOut,
  AdminCreditTypeOut,
  AdminFormulaOut,
  AdminPaymentMethodsOut,
  CourseTypeOut,
  UserOut,
} from "../../../../../lib/types";
import { normalizeUiLanguage, uiText } from "../../../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

type Params = {
  formulaId: string;
};

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function safeAdminHref(raw: string, fallback: string): string {
  const value = raw.trim();
  if (!value.startsWith("/admin")) {
    return fallback;
  }
  return value;
}

export default async function AdminFormulaEditPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams?: SearchParams;
}): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const formulaId = params.formulaId;
  const query = searchParams ?? {};
  const okMessage = readParam(query, "ok");
  const errorMessage = readParam(query, "error");
  const backHref = safeAdminHref(readParam(query, "back"), "/admin/config/formulas");

  const [meResult, formulaResult, paymentMethodsResult, courseTypesResult, creditTypesResult, accountResult] = await Promise.all([
    backendRequest<UserOut>("/api/v1/auth/me", {}, token),
    backendRequest<AdminFormulaOut>(`/api/v1/admin/formulas/${formulaId}`, {}, token),
    backendRequest<AdminPaymentMethodsOut>("/api/v1/admin/config/payment-methods", {}, token),
    backendRequest<CourseTypeOut[]>("/api/v1/course-types", {}, token),
    backendRequest<AdminCreditTypeOut[]>("/api/v1/admin/credit-types", {}, token),
    backendRequest<AdminConfigAccountOut>("/api/v1/admin/config/account", {}, token),
  ]);

  const language = meResult.ok ? normalizeUiLanguage(meResult.data.preferred_language) : "fr";
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  if (!formulaResult.ok) {
    return (
      <section className="admin-page-grid">
        <section className="card">
          <h2>{t("admin.formulas.editor_edit_title")}</h2>
          <p className="flash-err">{t("admin.formulas.load_formula_error", { message: formulaResult.message })}</p>
          <Link className="reset-link" href={backHref}>
            {t("admin.formulas.editor_back")}
          </Link>
        </section>
      </section>
    );
  }

  if (!paymentMethodsResult.ok || !courseTypesResult.ok || !creditTypesResult.ok || !accountResult.ok) {
    const messages: string[] = [];
    if (!paymentMethodsResult.ok) {
      messages.push(t("admin.formulas.load_payment_methods", { message: paymentMethodsResult.message }));
    }
    if (!courseTypesResult.ok) {
      messages.push(t("admin.formulas.load_course_types", { message: courseTypesResult.message }));
    }
    if (!creditTypesResult.ok) {
      messages.push(t("admin.formulas.load_credit_types", { message: creditTypesResult.message }));
    }
    if (!accountResult.ok) {
      messages.push(t("admin.formulas.load_account_config", { message: accountResult.message }));
    }

    return (
      <section className="admin-page-grid">
        <section className="flash-err">{messages.join(" | ")}</section>
      </section>
    );
  }

  return (
    <AdminFormulaEditor
      mode="edit"
      formula={formulaResult.data}
      courseTypes={courseTypesResult.data.filter((row) => row.active)}
      creditTypes={creditTypesResult.data.filter((row) => row.active)}
      paymentMethods={paymentMethodsResult.data.methods}
      currencyOptions={accountResult.data.allowed_currencies}
      returnTo={`/admin/config/formulas/${formulaId}`}
      backHref={backHref}
      okMessage={okMessage}
      errorMessage={errorMessage}
      language={language}
    />
  );
}
