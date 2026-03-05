import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { updatePlanningActivitiesAction, updatePlanningSettingsAction } from "../../../../../lib/actions";
import { backendRequest } from "../../../../../lib/backend";
import type { AdminPlanningActivitiesOut, AdminPlanningSettingsOut } from "../../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
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
    redirect("/login?error=Session%20expiree");
  }

  const [settingsResult, planningActivitiesResult] = await Promise.all([
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
  ]);

  if (!settingsResult.ok) {
    return (
      <section className="admin-page-grid">
        <section className="flash-err">Erreur chargement planning: {settingsResult.message}</section>
        <section className="card">
          <Link className="reset-link" href="/admin">
            Retour au planning
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
          <h2>Parametres du planning - {settings.location_name}</h2>
          <Link className="reset-link" href={`/admin?location_id=${settings.location_id}&edit=1`}>
            Retour au planning
          </Link>
        </div>
        <p className="muted">Regles de reservation/annulation et options d affichage pour ce lieu.</p>
      </section>

      <section className="card">
        <form action={updatePlanningSettingsAction} className="grid cols-2">
          <input type="hidden" name="location_id" value={settings.location_id} />

          <label>
            Description
            <input type="text" name="description" defaultValue={settings.description ?? ""} />
          </label>

          <label>
            Delai minimum de reservation (heures)
            <input type="number" min={0} name="min_booking_notice_hours" defaultValue={settings.min_booking_notice_hours} required />
          </label>

          <label>
            Delai maximum de reservation (mois)
            <input type="number" min={1} name="max_booking_horizon_months" defaultValue={settings.max_booking_horizon_months} required />
          </label>

          <label>
            Delai autorise pour annulation (heures)
            <input type="number" min={0} name="cancellation_deadline_hours" defaultValue={settings.cancellation_deadline_hours} required />
          </label>

          <label>
            Nombre de reservations max par client (optionnel)
            <input type="number" min={1} name="max_bookings_per_client" defaultValue={settings.max_bookings_per_client ?? ""} />
          </label>

          <label>
            Taille de liste d attente
            <input type="number" min={0} name="waitlist_capacity" defaultValue={settings.waitlist_capacity} required />
          </label>

          <label>
            Auto-annulation si inscrits &lt; a
            <input
              type="number"
              min={0}
              name="auto_cancel_if_booked_less_than"
              defaultValue={settings.auto_cancel_if_booked_less_than}
              required
            />
          </label>

          <label>
            Auto-annulation X heures avant debut
            <input type="number" min={0} name="auto_cancel_hours_before_start" defaultValue={settings.auto_cancel_hours_before_start} required />
          </label>

          <label className="checkline">
            <input type="checkbox" name="is_private" defaultChecked={settings.is_private} />
            Planning prive
          </label>

          <label className="checkline">
            <input type="checkbox" name="allow_force_booking" defaultChecked={settings.allow_force_booking} />
            Autoriser inscription forcee
          </label>

          <label className="checkline">
            <input type="checkbox" name="allow_multi_booking" defaultChecked={settings.allow_multi_booking} />
            Autoriser multi-reservations
          </label>

          <label className="checkline">
            <input type="checkbox" name="allow_negative_credits" defaultChecked={settings.allow_negative_credits} />
            Credits negatifs autorises
          </label>

          <label className="checkline">
            <input type="checkbox" name="notify_coach" defaultChecked={settings.notify_coach} />
            Envoyer mail au coach
          </label>

          <label className="checkline">
            <input type="checkbox" name="notify_admins" defaultChecked={settings.notify_admins} />
            Envoyer mail aux admins
          </label>

          <label className="checkline">
            <input type="checkbox" name="hide_booking_count" defaultChecked={settings.hide_booking_count} />
            Cacher le nombre d inscrits
          </label>

          <label className="checkline">
            <input type="checkbox" name="block_client_cancellation" defaultChecked={settings.block_client_cancellation} />
            Bloquer annulation cote client
          </label>

          <div className="row">
            <button type="submit">Valider les parametres</button>
          </div>
        </form>
      </section>

      <section className="card">
        <div className="row spread">
          <h3>Activites autorisees sur ce planning</h3>
          <Link className="reset-link" href="/admin/config?section=activities">
            Referentiel activites
          </Link>
        </div>
        {!planningActivitiesResult.ok ? (
          <p className="flash-err">Erreur chargement activites: {planningActivitiesResult.message}</p>
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
                        | {activity.duration_minutes} min | {activity.mode}
                        {!activity.active ? " | Inactive" : ""}
                      </small>
                      {activity.description ? <small className="muted"> - {activity.description}</small> : null}
                    </span>
                  </span>
                </label>
              ))}
            </div>

            <div className="row">
              <button type="submit">Valider les activites du planning</button>
            </div>
          </form>
        )}
      </section>
    </section>
  );
}
