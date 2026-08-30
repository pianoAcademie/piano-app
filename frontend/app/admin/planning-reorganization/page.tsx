import Link from "next/link";
import { redirect } from "next/navigation";

import { hasAdminPermission } from "../../../lib/admin-access";
import { getAdminToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import type { UserOut } from "../../../lib/types";
import { normalizeUiLanguage } from "../../../lib/ui-messages";
import {
  PlanningReorganizationBoard,
  type PlanningReorganizationSession,
} from "./reorganization-board";

type SearchParams = Record<string, string | string[] | undefined>;

type PlanningReorganizationLocation = {
  id: string;
  name: string;
  timezone: string;
};

type PlanningReorganizationOut = {
  school_years: string[];
  locations: PlanningReorganizationLocation[];
  available_days: string[];
  selected_school_year: string;
  selected_location_id: string | null;
  selected_day: string | null;
  sessions: PlanningReorganizationSession[];
};

function readParam(params: SearchParams, key: string): string {
  const raw = params[key];
  if (Array.isArray(raw)) {
    return raw[0] ?? "";
  }
  return raw ?? "";
}

function messageParam(params: SearchParams, key: "ok" | "error"): string {
  const raw = readParam(params, key);
  return raw || "";
}

function formatDay(value: string): string {
  const parsed = new Date(`${value}T12:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("fr-FR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(parsed);
}

function currentReturnTo(params: SearchParams): string {
  const query = new URLSearchParams();
  const schoolYear = readParam(params, "school_year").trim();
  const locationId = readParam(params, "location_id").trim();
  const day = readParam(params, "day").trim();
  const scope = readParam(params, "scope").trim();
  const bookingId = readParam(params, "booking_id").trim();
  if (bookingId) query.set("booking_id", bookingId);
  if (schoolYear) query.set("school_year", schoolYear);
  if (locationId) query.set("location_id", locationId);
  if (day) query.set("day", day);
  if (scope === "single" || scope === "series_future") query.set("scope", scope);
  const queryString = query.toString();
  return queryString ? `/admin/planning-reorganization?${queryString}` : "/admin/planning-reorganization";
}

export default async function AdminPlanningReorganizationPage({
  searchParams,
}: {
  searchParams?: SearchParams;
}): Promise<JSX.Element> {
  const token = getAdminToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || !hasAdminPermission(meResult.data, "can_edit_planning")) {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);

  const params = searchParams ?? {};
  const requestedSchoolYear = readParam(params, "school_year").trim();
  const requestedLocationId = readParam(params, "location_id").trim();
  const requestedDay = readParam(params, "day").trim();
  const requestedBookingId = readParam(params, "booking_id").trim();
  const initialScope = readParam(params, "scope").trim() === "single" ? "single" : "series_future";
  const query = new URLSearchParams();
  if (requestedBookingId) query.set("booking_id", requestedBookingId);
  if (requestedSchoolYear) query.set("school_year", requestedSchoolYear);
  if (requestedLocationId) query.set("location_id", requestedLocationId);
  if (requestedDay) query.set("day", requestedDay);
  const path = query.size
    ? `/api/v1/admin/planning-reorganization?${query.toString()}`
    : "/api/v1/admin/planning-reorganization";

  const result = await backendRequest<PlanningReorganizationOut>(path, {}, token);
  const snapshot = result.ok ? result.data : null;
  const selectedLocation = snapshot?.locations.find((location) => location.id === snapshot.selected_location_id) ?? null;
  const selectedDay = snapshot?.selected_day ?? requestedDay;
  const returnTo = currentReturnTo({
    school_year: snapshot?.selected_school_year ?? requestedSchoolYear,
    location_id: snapshot?.selected_location_id ?? requestedLocationId,
    day: selectedDay,
    scope: initialScope,
    booking_id: requestedBookingId,
  });
  const okMessage = messageParam(params, "ok");
  const errorMessage = messageParam(params, "error") || (result.ok ? "" : result.message);
  const totalStudents = snapshot?.sessions.reduce((sum, session) => sum + session.bookings.length, 0) ?? 0;

  return (
    <main className="admin-page">
      <section className="card reorg-hero">
        <div>
          <p className="eyebrow">Planning</p>
          <h1>Reorganisation saison</h1>
          <p>
            Travaillez par lieu et par jour pour equilibrer les groupes avant le demarrage, sans passer par les fiches
            une par une.
          </p>
        </div>
        <div className="row gap-sm">
          <Link className="button secondary" href="/admin">
            Planning
          </Link>
          <Link className="button secondary" href="/admin/simulation-planning">
            Simulation
          </Link>
        </div>
      </section>

      {okMessage ? <p className="form-feedback success">{okMessage}</p> : null}
      {errorMessage ? <p className="form-feedback error">{errorMessage}</p> : null}

      <details className="card">
        <summary><strong>Comment déplacer un élève sans modifier sa facturation ?</strong></summary>
        <ol>
          <li>Depuis Clients → fiche de l'élève → Réservations, cliquez sur Déplacer à côté de la première séance concernée.</li>
          <li>Choisissez le jour de destination, puis une séance seule ou toutes les séances futures de la série.</li>
          <li>Sélectionnez le groupe de destination. Vérifiez les dates et les montants dans l'aperçu, puis confirmez.</li>
        </ol>
        <p>Le tarif, les remises et la couverture de facture sont conservés. L'opération est tracée dans Changements, sans ajout de lignes de régularisation dans Compte. Aucun email client n'est envoyé par ce déplacement.</p>
        <p>Une place indisponible bloque toute l'opération. Un changement d'activité, de lieu, de durée ou du nombre de séances doit être traité séparément par un avenant ; ce parcours ne recalcule pas le contrat.</p>
      </details>

      <form className="card reorg-filters" method="get">
        {requestedBookingId ? <input type="hidden" name="booking_id" value={requestedBookingId} /> : null}
        <label>
          Saison
          <select name="school_year" defaultValue={snapshot?.selected_school_year ?? requestedSchoolYear}>
            {(snapshot?.school_years ?? [requestedSchoolYear || "2026-2027"]).filter(Boolean).map((schoolYear) => (
              <option key={schoolYear} value={schoolYear}>
                {schoolYear}
              </option>
            ))}
          </select>
        </label>
        <label>
          Lieu
          <select name="location_id" defaultValue={snapshot?.selected_location_id ?? requestedLocationId}>
            {(snapshot?.locations ?? []).map((location) => (
              <option key={location.id} value={location.id}>
                {location.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Jour
          <select name="day" defaultValue={selectedDay ?? ""}>
            {(snapshot?.available_days ?? []).map((day) => (
              <option key={day} value={day}>
                {formatDay(day)}
              </option>
            ))}
          </select>
        </label>
        <button className="button primary" type="submit">
          Charger
        </button>
      </form>

      <section className="reorg-summary-grid">
        <div className="card">
          <span>Creneaux</span>
          <strong>{snapshot?.sessions.length ?? 0}</strong>
        </div>
        <div className="card">
          <span>Eleves places</span>
          <strong>{totalStudents}</strong>
        </div>
        <div className="card">
          <span>Lieu</span>
          <strong>{selectedLocation?.name ?? "-"}</strong>
        </div>
        <div className="card">
          <span>Jour</span>
          <strong>{selectedDay ? formatDay(selectedDay) : "-"}</strong>
        </div>
      </section>

      {snapshot ? (
        <PlanningReorganizationBoard
          sessions={snapshot.sessions}
          returnTo={returnTo}
          initialScope={initialScope}
          initialBookingId={requestedBookingId}
          language={language}
        />
      ) : null}
    </main>
  );
}
