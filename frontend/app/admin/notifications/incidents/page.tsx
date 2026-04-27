import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest } from "../../../../lib/backend";
import type { NotificationIncidentOut, UserOut } from "../../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatDateTime(value: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString(localeForUiLanguage(language), { dateStyle: "short", timeStyle: "medium" });
}

function channelLabel(channel: string, language: UiLanguage): string {
  const normalized = channel.trim().toLowerCase();
  if (normalized === "email") {
    return uiText(language, "common.email");
  }
  if (normalized === "sms") {
    return uiText(language, "common.sms");
  }
  return channel;
}

export default async function AdminNotificationIncidentsPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
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

  const from = readParam(searchParams, "from");
  const to = readParam(searchParams, "to");
  const channel = readParam(searchParams, "channel");
  const incidentType = readParam(searchParams, "incident_type");
  const contactId = readParam(searchParams, "contact_id");

  const params = new URLSearchParams();
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  if (channel) params.set("channel", channel);
  if (incidentType) params.set("incident_type", incidentType);
  if (contactId) params.set("contact_id", contactId);
  params.set("limit", "1000");

  const incidentsResult = await backendRequest<NotificationIncidentOut[]>(
    `/api/v1/admin/notifications/incidents?${params.toString()}`,
    {},
    token,
  );
  const incidents = incidentsResult.ok ? incidentsResult.data : [];

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h2>{t("admin.incidents.title")}</h2>
        <p className="muted">{t("admin.incidents.subtitle")}</p>
      </section>

      <section className="card">
        {!incidentsResult.ok ? <p className="flash-err">{t("admin.incidents.backend_error")}: {incidentsResult.message}</p> : null}
        <form className="grid cols-5 sticky-filters" method="get">
          <label>
            {t("admin.incidents.date_from")}
            <input type="datetime-local" name="from" defaultValue={from} />
          </label>
          <label>
            {t("admin.incidents.date_to")}
            <input type="datetime-local" name="to" defaultValue={to} />
          </label>
          <label>
            {t("admin.incidents.channel")}
            <select name="channel" defaultValue={channel}>
              <option value="">{uiText(language, "common.all")}</option>
              <option value="email">{uiText(language, "common.email")}</option>
              <option value="sms">{uiText(language, "common.sms")}</option>
            </select>
          </label>
          <label>
            {t("admin.incidents.incident")}
            <input type="text" name="incident_type" defaultValue={incidentType} placeholder="email_bounced" />
          </label>
          <label>
            {t("admin.incidents.contact_id")}
            <input type="text" name="contact_id" defaultValue={contactId} />
          </label>
          <div className="row end cols-span-5 top-gap-sm">
            <button type="submit">{uiText(language, "common.apply")}</button>
            <a className="ghost top-gap-sm-inline" href="/admin/notifications/incidents">
              {t("admin.incidents.reset_filters")}
            </a>
          </div>
        </form>
      </section>

      <section className="card">
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>{uiText(language, "common.date")}</th>
                <th>{t("admin.incidents.contact")}</th>
                <th>{t("admin.incidents.contact_type")}</th>
                <th>{t("admin.incidents.channel")}</th>
                <th>{t("admin.incidents.incident")}</th>
                <th>{t("admin.incidents.severity")}</th>
                <th>{t("admin.incidents.detail")}</th>
                <th>{t("admin.incidents.last_notification")}</th>
                <th>{uiText(language, "client.action")}</th>
              </tr>
            </thead>
            <tbody>
              {incidents.length === 0 ? (
                <tr>
                  <td colSpan={9}>
                    <p className="muted">{t("admin.incidents.no_incident")}</p>
                  </td>
                </tr>
              ) : (
                incidents.map((row) => (
                  <tr key={row.id}>
                    <td>{formatDateTime(row.detected_at, language)}</td>
                    <td>{row.contact_id}</td>
                    <td>{row.contact_type}</td>
                    <td>{channelLabel(row.channel, language)}</td>
                    <td>{row.incident_type}</td>
                    <td>{row.severity}</td>
                    <td>{row.detail_text ?? "-"}</td>
                    <td>{row.notification_id ?? "-"}</td>
                    <td>
                      {row.contact_type === "USER" ? (
                        <a className="ghost" href={`/admin/clients/${row.contact_id}?tab=infos`}>
                          {t("admin.incidents.open_record")}
                        </a>
                      ) : (
                        "-"
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
