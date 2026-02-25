import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import AdminFormulaEditor from "../../../../../components/admin-formula-editor";
import { backendRequest } from "../../../../../lib/backend";
import type { AdminConfigAccountOut, AdminCreditTypeOut, AdminFormulaOut, AdminPaymentMethodsOut, CourseTypeOut } from "../../../../../lib/types";

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
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const formulaId = params.formulaId;
  const query = searchParams ?? {};
  const okMessage = readParam(query, "ok");
  const errorMessage = readParam(query, "error");
  const backHref = safeAdminHref(readParam(query, "back"), "/admin/config?section=formulas");

  const [formulaResult, paymentMethodsResult, courseTypesResult, creditTypesResult, accountResult] = await Promise.all([
    backendRequest<AdminFormulaOut>(`/api/v1/admin/formulas/${formulaId}`, {}, token),
    backendRequest<AdminPaymentMethodsOut>("/api/v1/admin/config/payment-methods", {}, token),
    backendRequest<CourseTypeOut[]>("/api/v1/course-types", {}, token),
    backendRequest<AdminCreditTypeOut[]>("/api/v1/admin/credit-types", {}, token),
    backendRequest<AdminConfigAccountOut>("/api/v1/admin/config/account", {}, token),
  ]);

  if (!formulaResult.ok) {
    return (
      <section className="admin-page-grid">
        <section className="card">
          <h2>Edition formule</h2>
          <p className="flash-err">Impossible de charger la formule: {formulaResult.message}</p>
          <Link className="reset-link" href={backHref}>
            Retour
          </Link>
        </section>
      </section>
    );
  }

  if (!paymentMethodsResult.ok || !courseTypesResult.ok || !creditTypesResult.ok || !accountResult.ok) {
    const messages: string[] = [];
    if (!paymentMethodsResult.ok) {
      messages.push(`Moyens de paiement: ${paymentMethodsResult.message}`);
    }
    if (!courseTypesResult.ok) {
      messages.push(`Types de cours: ${courseTypesResult.message}`);
    }
    if (!creditTypesResult.ok) {
      messages.push(`Types de credit: ${creditTypesResult.message}`);
    }
    if (!accountResult.ok) {
      messages.push(`Configuration compte: ${accountResult.message}`);
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
    />
  );
}
