import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { updatePlanningActivitiesAction, updatePlanningSettingsAction } from "../../../../../lib/actions";
import { backendRequest } from "../../../../../lib/backend";
import type { AdminPlanningActivitiesOut, AdminPlanningSettingsOut, UserOut } from "../../../../../lib/types";
import { normalizeUiLanguage, type UiLanguage, uiText } from "../../../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function activityModeLabel(mode: string, language: UiLanguage): string {
  const normalized = mode.trim().toUpperCase();
  if (normalized === "ONLINE") {
    return uiText(language, "admin.professor_detail.mode_online");
  }
  if (normalized === "ONSITE") {
    return uiText(language, "admin.professor_detail.mode_onsite");
  }
  return uiText(language, "admin.professor_detail.mode_all");
}

export default async function AdminPlanningSettingsPage({
  params,
  searchParams,
}: {
  params: { locationId: string };
  searchParams: SearchParams;
}): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const [settingsResult, planningActivitiesResult, meResult] = await Promise.all([
    backendRequest<AdminPlanningSettingsOut>(
      `/api/v1/admin/plannings/${params.locationId}/settings`,
      {},
      token,
    ),
    backendRequest<AdminPlanningActivitiesOut>(
      `/api/v1/admin/plannings/${params.locationId}/activities`,
      {},
      token,
    ),
    backendRequest<UserOut>("/api/v1/users/me", {}, token),
  ]);

  const language = meResult.ok ? normalizeUiLanguage(meResult.data.preferred_language) : "fr";
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  if (!settingsResult.ok) {
    return (
      <section className="admin-page-grid">
        <section className="flash-err">{t("admin.planning_settings.load_error", { message: settingsResult.message })}</section>
        <section className="card">
          <Link className="reset-link" href="/admin">
            {t("admin.planning_settings.back_to_planning")}
          </Link>
        </section>
      </section>
    );
  }

  const settings = settingsResult.data;
  const planningActivities = planningActivitiesResult.ok ? planningActivitiesResult.data : null;
  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error");

  return (
    <section className="admin-page-grid">
      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

      <section className="card">
        <div className="row spread">
          <h2>{t("admin.planning_settings.page_title", { name: settings.location_name })}</h2>
          <Link className="reset-link" href={`/admin?location_id=${settings.location_id}&edit=1`}>
            {t("admin.planning_settings.back_to_planning")}
          </Link>
        </div>
        <p className="muted">{t("admin.planning_settings.page_subtitle")}</p>
      </section>

      <section className="card">
        <form action={updatePlanningSettingsAction} className="grid cols-2">
          <input type="hidden" name="location_id" value={settings.location_id} />

          <label>
            {t("common.description")}
            <input type="text" name="description" defaultValue={settings.description ?? ""} />
          </label>

          <label>
            {t("admin.planning_settings.min_booking_notice")}
            <input type="number" min={0} name="min_booking_notice_hours" defaultValue={settings.min_booking_notice_hours} required />
          </label>

          <label>
            {t("admin.planning_settings.max_booking_horizon")}
            <input type="number" min={1} name="max_booking_horizon_months" defaultValue={settings.max_booking_horizon_months} required />
          </label>

          <label>
            {t("admin.planning_settings.cancellation_deadline")}
            <input type="number" min={0} name="cancellation_deadline_hours" defaultValue={settings.cancellation_deadline_hours} required />
          </label>

          <label>
            {t("admin.planning_settings.max_bookings_per_client")}
            <input type="number" min={1} name="max_bookings_per_client" defaultValue={settings.max_bookings_per_client ?? ""} />
          </label>

          <label>
            {t("admin.planning_settings.waitlist_capacity")}
            <input type="number" min={0} name="waitlist_capacity" defaultValue={settings.waitlist_capacity} required />
          </label>

          <input type="hidden" name="auto_cancel_if_booked_less_than" value={settings.auto_cancel_if_booked_less_than} />
          <input type="hidden" name="auto_cancel_hours_before_start" value={settings.auto_cancel_hours_before_start} />
          <p className="muted span-2">
            Les règles d'annulation automatique se configurent désormais dans chaque activité, avec une dérogation possible sur le créneau.
          </p>

          <label className="checkline">
            <input type="checkbox" name="is_private" defaultChecked={settings.is_private} />
            {t("admin.planning_settings.is_private")}
          </label>

          <label className="checkline">
            <input type="checkbox" name="allow_force_booking" defaultChecked={settings.allow_force_booking} />
            {t("admin.planning_settings.allow_force_booking")}
          </label>

          <label className="checkline">
            <input type="checkbox" name="allow_multi_booking" defaultChecked={settings.allow_multi_booking} />
            {t("admin.planning_settings.allow_multi_booking")}
          </label>

          <label className="checkline">
            <input type="checkbox" name="allow_negative_credits" defaultChecked={settings.allow_negative_credits} />
            {t("admin.planning_settings.allow_negative_credits")}
          </label>

          <label className="checkline">
            <input type="checkbox" name="notify_coach" defaultChecked={settings.notify_coach} />
            {t("admin.planning_settings.notify_coach")}
          </label>

          <label className="checkline">
            <input type="checkbox" name="notify_admins" defaultChecked={settings.notify_admins} />
            {t("admin.planning_settings.notify_admins")}
          </label>

          <label className="checkline">
            <input type="checkbox" name="hide_booking_count" defaultChecked={settings.hide_booking_count} />
            {t("admin.planning_settings.hide_booking_count")}
          </label>

          <label className="checkline">
            <input type="checkbox" name="block_client_cancellation" defaultChecked={settings.block_client_cancellation} />
            {t("admin.planning_settings.block_client_cancellation")}
          </label>

          <div className="row">
            <button type="submit">{t("admin.planning_settings.save_settings")}</button>
          </div>
        </form>
      </section>

      <section className="card">
        <div className="row spread">
          <h3>{t("admin.planning_settings.allowed_activities_title")}</h3>
          <Link className="reset-link" href="/admin/config?section=activities">
            {t("admin.planning_settings.activities_catalog")}
          </Link>
        </div>
        {!planningActivitiesResult.ok ? (
          <p className="flash-err">{t("admin.planning_settings.activities_load_error", { message: planningActivitiesResult.message })}</p>
        ) : (
          <form action={updatePlanningActivitiesAction} className="grid">
            <input type="hidden" name="location_id" value={settings.location_id} />

            <div className="list">
              {planningActivities?.activities.map((activity) => (
                <label key={activity.id} className="item row spread">
                  <span className="row">
                    <input
                      type="checkbox"
                      name="activity_ids"
                      value={activity.id}
                      defaultChecked={activity.selected}
                      disabled={!activity.active}
                    />
                    <span
                      aria-hidden
                      style={{
                        width: 12,
                        height: 12,
                        borderRadius: 999,
                        display: "inline-block",
                        backgroundColor: activity.color_hex,
                        border: "1px solid #d3c2a5",
                      }}
                    />
                    <span>
                      <strong>{activity.name}</strong>
                      <small className="muted">
                        {" "}
                        | {activity.duration_minutes} min | {activityModeLabel(activity.mode, language)}
                        {!activity.active ? ` | ${t("common.inactive")}` : ""}
                      </small>
                      {activity.description ? <small className="muted"> - {activity.description}</small> : null}
                    </span>
                  </span>
                </label>
              ))}
            </div>

            <div className="row">
              <button type="submit">{t("admin.planning_settings.save_activities")}</button>
            </div>
          </form>
        )}
      </section>
    </section>
  );
}
