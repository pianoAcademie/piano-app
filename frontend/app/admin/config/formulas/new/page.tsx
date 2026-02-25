import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import AdminFormulaEditor from "../../../../../components/admin-formula-editor";
import { backendRequest } from "../../../../../lib/backend";
import type { AdminConfigAccountOut, AdminCreditTypeOut, AdminPaymentMethodsOut, CourseTypeOut } from "../../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

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

export default async function AdminFormulaCreatePage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const params = searchParams ?? {};
  const okMessage = readParam(params, "ok");
  const errorMessage = readParam(params, "error");
  const backHref = safeAdminHref(readParam(params, "back"), "/admin/config?section=formulas");

  const [paymentMethodsResult, courseTypesResult, creditTypesResult, accountResult] = await Promise.all([
    backendRequest<AdminPaymentMethodsOut>("/api/v1/admin/config/payment-methods", {}, token),
    backendRequest<CourseTypeOut[]>("/api/v1/course-types", {}, token),
    backendRequest<AdminCreditTypeOut[]>("/api/v1/admin/credit-types", {}, token),
    backendRequest<AdminConfigAccountOut>("/api/v1/admin/config/account", {}, token),
  ]);

  const paymentMethods = paymentMethodsResult.ok ? paymentMethodsResult.data.methods : [];
  const courseTypes = courseTypesResult.ok ? courseTypesResult.data.filter((row) => row.active) : [];
  const creditTypes = creditTypesResult.ok ? creditTypesResult.data.filter((row) => row.active) : [];
  const currencyOptions = accountResult.ok ? accountResult.data.allowed_currencies : ["EUR", "USD"];

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
      mode="create"
      formula={null}
      courseTypes={courseTypes}
      creditTypes={creditTypes}
      paymentMethods={paymentMethods}
      currencyOptions={currencyOptions}
      returnTo="/admin/config/formulas/new"
      backHref={backHref}
      okMessage={okMessage}
      errorMessage={errorMessage}
    />
  );
}
