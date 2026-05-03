import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest } from "../../../lib/backend";
import type {
  AdminPlanningActivitiesOut,
  AdminPlanningSettingsOut,
  LocationOut,
  UserOut,
} from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage } from "../../../lib/ui-i18n";

type PlanningLocationSummary = {
  location: LocationOut;
  settings: AdminPlanningSettingsOut | null;
  settingsError: string | null;
  activities: AdminPlanningActivitiesOut | null;
  activitiesError: string | null;
};

async function loadPlanningSimulationLocations(
  token: string,
): Promise<{ ok: true; data: LocationOut[] } | { ok: false; message: string }> {
  const directResult = await backendRequest<LocationOut[]>("/api/v1/locations?active=true", {}, token);
  if (directResult.ok) {
    return directResult;
  }
  const legacyResult = await backendRequest<LocationOut[]>("/api/v1/catalogue/locations?active=true", {}, token);
  if (legacyResult.ok) {
    return legacyResult;
  }
  return { ok: false, message: `${directResult.message} | ${legacyResult.message}` };
}

function text(language: UiLanguage, fr: string, en: string): string {
  return language === "en" ? en : fr;
}

function formatDateTime(value: string | null, language: UiLanguage): string {
  if (!value) {
    return text(language, "Non disponible", "Unavailable");
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(localeForUiLanguage(language), {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function locationSubtitle(location: LocationOut, language: UiLanguage): string {
  const parts = [location.city, location.timezone].filter(Boolean);
  if (parts.length > 0) {
    return parts.join(" · ");
  }
  return text(language, "Lieu sans adresse detaillee", "Location without detailed address");
}

export default async function AdminSimulationPlanningPage(): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error_code=admin_access_required");
  }

  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const locationsResult = await loadPlanningSimulationLocations(token);

  const locationSummaries: PlanningLocationSummary[] = locationsResult.ok
    ? await Promise.all(
        locationsResult.data.map(async (location) => {
          const [settingsResult, activitiesResult] = await Promise.all([
            backendRequest<AdminPlanningSettingsOut>(
              `/api/v1/admin/plannings/${encodeURIComponent(location.id)}/settings`,
              {},
              token,
            ),
            backendRequest<AdminPlanningActivitiesOut>(
              `/api/v1/admin/plannings/${encodeURIComponent(location.id)}/activities`,
              {},
              token,
            ),
          ]);

          return {
            location,
            settings: settingsResult.ok ? settingsResult.data : null,
            settingsError: settingsResult.ok ? null : settingsResult.message,
            activities: activitiesResult.ok ? activitiesResult.data : null,
            activitiesError: activitiesResult.ok ? null : activitiesResult.message,
          };
        }),
      )
    : [];

  const configuredLocations = locationSummaries.filter((summary) => summary.settings).length;
  const totalSelectedActivities = locationSummaries.reduce(
    (total, summary) => total + (summary.activities?.selected_activity_ids.length ?? 0),
    0,
  );
  const onlineLocations = locationSummaries.filter((summary) => summary.location.is_online).length;
  const lastUpdatedAt = locationSummaries
    .map((summary) => summary.settings?.updated_at ?? null)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1) ?? null;

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread">
          <div>
            <h2>{text(language, "Simulation planning", "Planning simulation")}</h2>
            <p className="muted">
              {text(
                language,
                "Point d'entree pour preparer les regles de capacite par lieu et retrouver rapidement les reglages de planning utiles aux simulations.",
                "Hub to prepare per-location capacity rules and quickly reach the planning settings used by simulations.",
              )}
            </p>
          </div>
          <div className="row">
            <Link className="ghost" href="/admin">
              {text(language, "Retour au planning", "Back to planning")}
            </Link>
            <Link className="ghost" href="/admin/config?section=activities">
              {text(language, "Catalogue des activites", "Activities catalog")}
            </Link>
          </div>
        </div>
      </section>

      {!locationsResult.ok ? (
        <section className="flash-err">
          {text(language, "Impossible de charger les lieux : ", "Unable to load locations: ")}
          {locationsResult.message}
        </section>
      ) : null}

      <section className="grid cols-4">
        <article className="card">
          <h3>{text(language, "Lieux actifs", "Active locations")}</h3>
          <p className="muted">
            {text(language, "Lieux disponibles dans le module.", "Locations available in the module.")}
          </p>
          <strong>{locationSummaries.length}</strong>
        </article>

        <article className="card">
          <h3>{text(language, "Lieux configures", "Configured locations")}</h3>
          <p className="muted">
            {text(language, "Reglages planning joignables.", "Planning settings reachable.")}
          </p>
          <strong>{configuredLocations}</strong>
        </article>

        <article className="card">
          <h3>{text(language, "Activites rattachees", "Assigned activities")}</h3>
          <p className="muted">
            {text(language, "Total des activites autorisees sur les lieux.", "Total activities enabled across locations.")}
          </p>
          <strong>{totalSelectedActivities}</strong>
        </article>

        <article className="card">
          <h3>{text(language, "Derniere mise a jour", "Last update")}</h3>
          <p className="muted">
            {text(language, "Dernier reglage planning modifie.", "Most recent planning settings update.")}
          </p>
          <strong>{formatDateTime(lastUpdatedAt, language)}</strong>
        </article>
      </section>

      <section className="card">
        <div className="row spread">
          <div>
            <h3>{text(language, "Lecture rapide", "Quick read")}</h3>
            <p className="muted">
              {text(
                language,
                "Le moteur de simulation s'appuie sur les activites autorisees par lieu, les capacites et les regles d'affectation utilisees ensuite dans les parcours devis et planning.",
                "The simulation engine relies on per-location allowed activities, capacities, and assignment rules later reused in quote and planning flows.",
              )}
            </p>
          </div>
          <strong>
            {onlineLocations} {text(language, "lieu(x) en ligne", "online location(s)")}
          </strong>
        </div>
      </section>

      <section className="grid cols-2">
        {locationSummaries.map((summary) => {
          const settings = summary.settings;
          const activities = summary.activities;

          return (
            <article className="card" key={summary.location.id}>
              <div className="row spread">
                <div>
                  <h3>{summary.location.name}</h3>
                  <p className="muted">{locationSubtitle(summary.location, language)}</p>
                </div>
                <strong>
                  {summary.location.is_online
                    ? text(language, "En ligne", "Online")
                    : text(language, "Presentiel", "Onsite")}
                </strong>
              </div>

              {settings ? (
                <div className="grid cols-2">
                  <article className="item">
                    <strong>{text(language, "Preavis mini", "Min notice")}</strong>
                    <p className="muted">
                      {settings.min_booking_notice_hours} {text(language, "h", "h")}
                    </p>
                  </article>
                  <article className="item">
                    <strong>{text(language, "Horizon de reservation", "Booking horizon")}</strong>
                    <p className="muted">
                      {settings.max_booking_horizon_months} {text(language, "mois", "months")}
                    </p>
                  </article>
                  <article className="item">
                    <strong>{text(language, "Liste d'attente", "Waitlist")}</strong>
                    <p className="muted">
                      {settings.waitlist_capacity} {text(language, "place(s)", "seat(s)")}
                    </p>
                  </article>
                  <article className="item">
                    <strong>{text(language, "Activites autorisees", "Allowed activities")}</strong>
                    <p className="muted">{activities?.selected_activity_ids.length ?? 0}</p>
                  </article>
                </div>
              ) : (
                <p className="flash-err">
                  {text(language, "Reglages indisponibles : ", "Settings unavailable: ")}
                  {summary.settingsError}
                </p>
              )}

              {activities && activities.activities.length > 0 ? (
                <p className="muted">
                  {text(language, "Exemples : ", "Examples: ")}
                  {activities.activities
                    .filter((activity) => activity.selected)
                    .slice(0, 3)
                    .map((activity) => activity.name)
                    .join(", ") || text(language, "Aucune activite selectionnee", "No selected activity")}
                </p>
              ) : summary.activitiesError ? (
                <p className="flash-err">
                  {text(language, "Activites indisponibles : ", "Activities unavailable: ")}
                  {summary.activitiesError}
                </p>
              ) : null}

              {settings?.description ? <p className="muted">{settings.description}</p> : null}

              <div className="row">
                <Link className="ghost" href={`/admin?location_id=${encodeURIComponent(summary.location.id)}`}>
                  {text(language, "Ouvrir le planning", "Open planning")}
                </Link>
                <Link className="ghost" href={`/admin?location_id=${encodeURIComponent(summary.location.id)}&edit=1`}>
                  {text(language, "Ouvrir en edition", "Open in edit mode")}
                </Link>
                <Link
                  className="ghost"
                  href={`/admin/plannings/${encodeURIComponent(summary.location.id)}/settings`}
                >
                  {text(language, "Reglages du lieu", "Location settings")}
                </Link>
              </div>
            </article>
          );
        })}
      </section>
    </section>
  );
}
