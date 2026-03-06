import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest } from "../../../../lib/backend";
import type { NotificationIncidentOut } from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatDateTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "medium" });
}

export default async function AdminNotificationIncidentsPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

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
        <h2>Incidents de communication</h2>
        <p className="muted">Suspensions email/telephone, incidents provider et actions correctives.</p>
      </section>

      <section className="card">
        {!incidentsResult.ok ? <p className="flash-err">Erreur backend: {incidentsResult.message}</p> : null}
        <form className="grid cols-5 sticky-filters" method="get">
          <label>
            Date du
            <input type="datetime-local" name="from" defaultValue={from} />
          </label>
          <label>
            Date au
            <input type="datetime-local" name="to" defaultValue={to} />
          </label>
          <label>
            Canal
            <select name="channel" defaultValue={channel}>
              <option value="">Tous</option>
              <option value="email">email</option>
              <option value="sms">sms</option>
            </select>
          </label>
          <label>
            Incident
            <input type="text" name="incident_type" defaultValue={incidentType} placeholder="email_bounced" />
          </label>
          <label>
            Contact ID
            <input type="text" name="contact_id" defaultValue={contactId} />
          </label>
          <div className="row end cols-span-5 top-gap-sm">
            <button type="submit">Appliquer</button>
            <a className="ghost top-gap-sm-inline" href="/admin/notifications/incidents">
              Reset filtres
            </a>
          </div>
        </form>
      </section>

      <section className="card">
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Contact</th>
                <th>Type contact</th>
                <th>Canal</th>
                <th>Incident</th>
                <th>Severite</th>
                <th>Detail</th>
                <th>Derniere notif</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {incidents.length === 0 ? (
                <tr>
                  <td colSpan={9}>
                    <p className="muted">Aucun incident trouve.</p>
                  </td>
                </tr>
              ) : (
                incidents.map((row) => (
                  <tr key={row.id}>
                    <td>{formatDateTime(row.detected_at)}</td>
                    <td>{row.contact_id}</td>
                    <td>{row.contact_type}</td>
                    <td>{row.channel}</td>
                    <td>{row.incident_type}</td>
                    <td>{row.severity}</td>
                    <td>{row.detail_text ?? "-"}</td>
                    <td>{row.notification_id ?? "-"}</td>
                    <td>
                      {row.contact_type === "USER" ? (
                        <a className="ghost" href={`/admin/clients/${row.contact_id}?tab=infos`}>
                          Ouvrir fiche
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
