import Link from "next/link";

import type { AdminActivityOut, LocationOut } from "../lib/types";
import CopyLinkButton from "./copy-link-button";

function normalizeBaseUrl(raw: string | null | undefined): string {
  const value = (raw ?? "").trim();
  if (!value) {
    return "";
  }
  if (value.startsWith("http://") || value.startsWith("https://")) {
    return value.replace(/\/+$/, "");
  }
  return `https://${value.replace(/\/+$/, "")}`;
}

type AdminIntegrationPlanningEmbedProps = {
  accountWebsite?: string | null;
  activities: AdminActivityOut[];
  locations: LocationOut[];
  selectedActivityId?: string;
  selectedLocationId?: string;
  selectedStartDate?: string;
};

export default function AdminIntegrationPlanningEmbed({
  accountWebsite,
  activities,
  locations,
  selectedActivityId = "",
  selectedLocationId = "",
  selectedStartDate = "",
}: AdminIntegrationPlanningEmbedProps): JSX.Element {
  const eligibleActivities = [...activities]
    .filter((activity) => activity.active && activity.allows_student_bookings)
    .sort((left, right) => left.name.localeCompare(right.name, "fr"));
  const activeLocations = [...locations]
    .filter((location) => location.active)
    .sort((left, right) => left.name.localeCompare(right.name, "fr"));

  const selectedActivity = eligibleActivities.find((activity) => activity.id === selectedActivityId) ?? null;
  const selectedLocation = activeLocations.find((location) => location.id === selectedLocationId) ?? null;
  const embedParams = new URLSearchParams();
  if (selectedActivity) {
    embedParams.set("course_type_id", selectedActivity.id);
  }
  if (selectedLocation) {
    embedParams.set("location_id", selectedLocation.id);
  }
  if (selectedStartDate) {
    embedParams.set("date", selectedStartDate);
  }
  const embedPath = selectedActivity && selectedLocation ? `/embed/planning?${embedParams.toString()}` : "";
  const normalizedBaseUrl = normalizeBaseUrl(accountWebsite);
  const absoluteEmbedUrl = embedPath && normalizedBaseUrl ? `${normalizedBaseUrl}${embedPath}` : "";
  const iframeTitle =
    selectedActivity && selectedLocation
      ? `Reservations ${selectedActivity.name} - ${selectedLocation.name}`
      : "Planning externe";
  const iframeHtml = absoluteEmbedUrl
    ? `<iframe src="${absoluteEmbedUrl}" title="${iframeTitle}" width="100%" height="840" style="width:100%;min-height:840px;border:0;border-radius:16px;overflow:hidden;" loading="lazy" referrerpolicy="strict-origin-when-cross-origin"></iframe>`
    : "";

  return (
    <section className="card config-placeholder-card">
      <h3>Integration</h3>
      <p className="muted">
        Generez ici le code HTML d iframe pour embarquer la vue semaine d un cours sur un site externe, par exemple dans un bloc
        HTML WordPress.
      </p>

      <form method="get" action="/admin/config" className="grid cols-2 config-form-grid top-gap-sm">
        <input type="hidden" name="section" value="integrations" />

        <label>
          Cours
          <select name="integration_course_type_id" defaultValue={selectedActivityId}>
            <option value="">Choisir un cours</option>
            {eligibleActivities.map((activity) => (
              <option key={activity.id} value={activity.id}>
                {activity.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Lieu
          <select name="integration_location_id" defaultValue={selectedLocationId}>
            <option value="">Choisir un lieu</option>
            {activeLocations.map((location) => (
              <option key={location.id} value={location.id}>
                {location.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Date de depart (optionnel)
          <input type="date" name="integration_date" defaultValue={selectedStartDate} />
        </label>

        <div className="row span-2">
          <button type="submit">Generer le code iframe</button>
          {selectedActivity || selectedLocation || selectedStartDate ? (
            <Link className="ghost small-btn" href="/admin/config?section=integrations">
              Reinitialiser
            </Link>
          ) : null}
        </div>
      </form>

      <section className="top-gap-sm">
        <h4>Regles de publication</h4>
        <ul className="config-error-list">
          <li>Seuls les creneaux avec reservation externe active et un tarif externe TTC renseigne apparaitront dans l iframe.</li>
          <li>Le tarif externe se regle directement sur chaque creneau dans l agenda admin.</li>
          <li>Le visiteur peut ouvrir un slot, se connecter ou creer un compte, puis reserver la session depuis l iframe.</li>
          <li>Vous pouvez fixer une date de depart pour ouvrir directement le planning sur une semaine ciblee.</li>
        </ul>
      </section>

      {!normalizedBaseUrl ? (
        <p className="flash-err top-gap-sm">
          Le champ Site web n est pas renseigne dans les informations du compte. Le lien de previsualisation fonctionne en local, mais le code HTML
          pour WordPress a besoin d une URL publique configuree.
        </p>
      ) : null}

      {embedPath ? (
        <section className="top-gap-sm">
          <div className="row spread">
            <div>
              <h4>Resultat</h4>
              <p className="muted">
                {selectedActivity?.name} · {selectedLocation?.name}
                {selectedStartDate ? ` · debut ${selectedStartDate}` : ""}
              </p>
            </div>
            <div className="row">
              <Link className="ghost small-btn" href={embedPath} target="_blank" rel="noreferrer">
                Previsualiser
              </Link>
              {absoluteEmbedUrl ? <CopyLinkButton value={absoluteEmbedUrl} label="Copier l URL" /> : null}
              {iframeHtml ? <CopyLinkButton value={iframeHtml} label="Copier le code HTML" /> : null}
            </div>
          </div>

          <label className="top-gap-sm">
            URL iframe
            <textarea rows={3} readOnly defaultValue={absoluteEmbedUrl || embedPath} />
          </label>

          <label className="top-gap-sm">
            Code HTML a coller dans WordPress
            <textarea rows={6} readOnly defaultValue={iframeHtml || "<!-- Configurez d abord le site web public du compte -->"} />
          </label>
        </section>
      ) : null}
    </section>
  );
}
