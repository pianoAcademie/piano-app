import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import AdminProfessorDefaultGridManager from "../../../../components/admin-professor-default-grid-manager";
import AdminTeacherInvoicingNav from "../../../../components/admin-teacher-invoicing-nav";
import {
  archiveAdminConfigProfessorDefaultGridPeriodAction,
  createAdminConfigProfessorDefaultGridPeriodAction,
  updateAdminConfigProfessorDefaultGridPeriodAction,
  updateAdminConfigProfessorDefaultGridPeriodRulesAction,
} from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import type {
  AdminActivityOut,
  AdminConfigAccountOut,
  AdminProfessorPayGridPeriodDetailOut,
  AdminProfessorPayGridPeriodOut,
  UserOut,
} from "../../../../lib/types";
import { normalizeUiLanguage, uiText } from "../../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

export default async function AdminTeacherInvoicingSalaryGridPage({
  searchParams,
}: {
  searchParams: SearchParams;
}): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const params = searchParams ?? {};
  const selectedGridPeriodIdParam = readParam(params, "grid_period").trim();
  const okMessage = readParam(params, "ok").trim();
  const errorMessage = readParam(params, "error").trim();

  const gridPeriodsRequest = backendRequest<AdminProfessorPayGridPeriodOut[]>(
    "/api/v1/admin/config/professor-default-grid/periods",
    {},
    token,
  );

  const [accountResult, activitiesResult, periodsResult, selectedPeriodResult] = await Promise.all([
    backendRequest<AdminConfigAccountOut>("/api/v1/admin/config/account", {}, token),
    backendRequest<AdminActivityOut[]>("/api/v1/admin/activities?include_inactive=true", {}, token),
    gridPeriodsRequest,
    (async () => {
      const periods = await gridPeriodsRequest;
      if (!periods.ok || periods.data.length === 0) {
        return { ok: true as const, status: 200, data: null as AdminProfessorPayGridPeriodDetailOut | null };
      }
      const selectedPeriodId = selectedGridPeriodIdParam || periods.data.find((period) => period.is_active)?.id || periods.data[0]?.id || "";
      if (!selectedPeriodId) {
        return { ok: true as const, status: 200, data: null as AdminProfessorPayGridPeriodDetailOut | null };
      }
      return backendRequest<AdminProfessorPayGridPeriodDetailOut>(
        `/api/v1/admin/config/professor-default-grid/periods/${selectedPeriodId}`,
        {},
        token,
      );
    })(),
  ]);

  const loadErrors: string[] = [];
  const accountDefaultCurrency = accountResult.ok
    ? accountResult.data.default_currency
    : (() => {
        loadErrors.push(t("admin.professor_default_grid.load_account_config", { message: accountResult.message }));
        return "EUR";
      })();
  const activities = activitiesResult.ok
    ? activitiesResult.data
    : (() => {
        loadErrors.push(t("admin.professor_default_grid.load_activities", { message: activitiesResult.message }));
        return [] as AdminActivityOut[];
      })();
  const periods = periodsResult.ok
    ? periodsResult.data
    : (() => {
        loadErrors.push(t("admin.professor_default_grid.load_periods", { message: periodsResult.message }));
        return [] as AdminProfessorPayGridPeriodOut[];
      })();
  const selectedPeriodDetail = selectedPeriodResult.ok
    ? selectedPeriodResult.data
    : (() => {
        loadErrors.push(t("admin.professor_default_grid.load_period_detail", { message: selectedPeriodResult.message }));
        return null as AdminProfessorPayGridPeriodDetailOut | null;
      })();

  return (
    <section className="admin-page-grid">
      <AdminTeacherInvoicingNav activeTab="salary-grid" language={language} />

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {loadErrors.length > 0 ? (
        <section className="card">
          <h3>{uiText(language, "admin.teacher_invoicing.load_errors")}</h3>
          <ul className="config-error-list">
            {loadErrors.map((message) => (
              <li key={message} className="flash-err">
                {message}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <AdminProfessorDefaultGridManager
        activities={activities}
        periods={periods}
        selectedPeriod={selectedPeriodDetail?.period ?? null}
        selectedLines={selectedPeriodDetail?.lines ?? []}
        selectedPeriodId={selectedPeriodDetail?.period.id ?? null}
        createPeriodAction={createAdminConfigProfessorDefaultGridPeriodAction}
        updatePeriodAction={updateAdminConfigProfessorDefaultGridPeriodAction}
        archivePeriodAction={archiveAdminConfigProfessorDefaultGridPeriodAction}
        updatePeriodRulesAction={updateAdminConfigProfessorDefaultGridPeriodRulesAction}
        defaultCurrency={accountDefaultCurrency}
        sectionPath="/admin/teacher-invoicing/salary-grid"
        language={language}
      />
    </section>
  );
}
