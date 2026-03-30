"use client";

import { useMemo, useState } from "react";

import type { SessionAudienceScope } from "../lib/types";

type SessionVisibilityFieldsProps = {
  initialVisibilityScopes: SessionAudienceScope[];
  initialBookingScopes: SessionAudienceScope[];
  allowsStudentBookings?: boolean;
};

const NON_PRIVATE_SCOPE_OPTIONS: Array<{ value: SessionAudienceScope; label: string; hint: string }> = [
  {
    value: "EXTERNAL",
    label: "Externe",
    hint: "Visible ou reservable hors connexion, et aussi pour tous les clients connectes.",
  },
  {
    value: "SUBSCRIPTION",
    label: "Abonne / carnet",
    hint: "Reserve aux clients avec abonnement ou carnet compatible.",
  },
  {
    value: "FORFAIT",
    label: "Forfait",
    hint: "Reserve aux clients couverts par un forfait compatible.",
  },
];

function normalizeScopes(values: SessionAudienceScope[], fallback: SessionAudienceScope[]): SessionAudienceScope[] {
  const unique = Array.from(new Set(values));
  if (unique.includes("PRIVATE")) {
    return ["PRIVATE"];
  }
  const ordered = NON_PRIVATE_SCOPE_OPTIONS.map((option) => option.value).filter((value) => unique.includes(value));
  return ordered.length > 0 ? ordered : fallback;
}

function toggleScope(current: SessionAudienceScope[], scope: SessionAudienceScope): SessionAudienceScope[] {
  if (scope === "PRIVATE") {
    return current.includes("PRIVATE") ? ["EXTERNAL"] : ["PRIVATE"];
  }
  const base = current.includes("PRIVATE") ? [] : [...current];
  const next = base.includes(scope) ? base.filter((value) => value !== scope) : [...base, scope];
  return normalizeScopes(next, [scope]);
}

function scopeGroupSummary(scopes: SessionAudienceScope[]): string {
  if (scopes.length === 1 && scopes[0] === "PRIVATE") {
    return "Prive (admin seulement)";
  }
  const labels = NON_PRIVATE_SCOPE_OPTIONS.filter((option) => scopes.includes(option.value)).map((option) => option.label);
  return labels.join(" + ");
}

export default function SessionVisibilityFields({
  initialVisibilityScopes,
  initialBookingScopes,
  allowsStudentBookings = true,
}: SessionVisibilityFieldsProps): JSX.Element {
  const [visibilityScopes, setVisibilityScopes] = useState<SessionAudienceScope[]>(
    normalizeScopes(initialVisibilityScopes, ["EXTERNAL"]),
  );
  const [bookingScopes, setBookingScopes] = useState<SessionAudienceScope[]>(
    normalizeScopes(initialBookingScopes, allowsStudentBookings ? ["EXTERNAL"] : ["PRIVATE"]),
  );

  const visibilityIsPrivate = visibilityScopes.length === 1 && visibilityScopes[0] === "PRIVATE";
  const effectiveBookingScopes = useMemo<SessionAudienceScope[]>(() => {
    if (visibilityIsPrivate || !allowsStudentBookings) {
      return ["PRIVATE"];
    }
    return normalizeScopes(bookingScopes, ["EXTERNAL"]);
  }, [allowsStudentBookings, bookingScopes, visibilityIsPrivate]);
  const bookingIsPrivate = effectiveBookingScopes.length === 1 && effectiveBookingScopes[0] === "PRIVATE";

  return (
    <>
      <fieldset className="session-audience-fieldset">
        <legend>Affichage</legend>
        <small className="muted">
          Cochez un ou plusieurs cas. Les eleves deja inscrits voient toujours le creneau dans leur portail, meme si l'affichage est restreint.
        </small>
        <div className="session-audience-option-list">
          {NON_PRIVATE_SCOPE_OPTIONS.map((option) => (
            <label key={`visibility-${option.value}`} className="session-audience-option">
              <input
                type="checkbox"
                name="visibility_scopes"
                value={option.value}
                checked={!visibilityIsPrivate && visibilityScopes.includes(option.value)}
                onChange={() => setVisibilityScopes((current) => toggleScope(current, option.value))}
              />
              <span>
                <strong>{option.label}</strong>
                <small className="muted">{option.hint}</small>
              </span>
            </label>
          ))}
          <label className="session-audience-option">
            <input
              type="checkbox"
              name="visibility_scopes"
              value="PRIVATE"
              checked={visibilityIsPrivate}
              onChange={() => setVisibilityScopes((current) => toggleScope(current, "PRIVATE"))}
            />
            <span>
              <strong>Prive</strong>
              <small className="muted">Visible uniquement en admin. Les eleves deja inscrits le voient quand meme dans leur portail.</small>
            </span>
          </label>
        </div>
        <small className="muted">Actuel: {scopeGroupSummary(visibilityScopes)}.</small>
      </fieldset>

      <fieldset className="session-audience-fieldset">
        <legend>Reservation en ligne</legend>
        <small className="muted">
          Cochez un ou plusieurs cas. En pratique, <strong>Externe</strong> rend aussi le creneau reservable pour tous les clients connectes, meme sans formule active.
        </small>
        {visibilityIsPrivate || !allowsStudentBookings ? (
          <input type="hidden" name="booking_scopes" value="PRIVATE" />
        ) : null}
        <div className="session-audience-option-list">
          {NON_PRIVATE_SCOPE_OPTIONS.map((option) => (
            <label
              key={`booking-${option.value}`}
              className={`session-audience-option ${visibilityIsPrivate || !allowsStudentBookings ? "is-disabled" : ""}`}
            >
              <input
                type="checkbox"
                name={visibilityIsPrivate || !allowsStudentBookings ? undefined : "booking_scopes"}
                value={option.value}
                checked={!bookingIsPrivate && effectiveBookingScopes.includes(option.value)}
                disabled={visibilityIsPrivate || !allowsStudentBookings}
                onChange={() => setBookingScopes((current) => toggleScope(current, option.value))}
              />
              <span>
                <strong>{option.label}</strong>
                <small className="muted">{option.hint}</small>
              </span>
            </label>
          ))}
          <label className={`session-audience-option ${!allowsStudentBookings ? "is-disabled" : ""}`}>
            <input
              type="checkbox"
              name={visibilityIsPrivate || !allowsStudentBookings ? undefined : "booking_scopes"}
              value="PRIVATE"
              checked={bookingIsPrivate}
              disabled={visibilityIsPrivate || !allowsStudentBookings}
              onChange={() => setBookingScopes((current) => toggleScope(current, "PRIVATE"))}
            />
            <span>
              <strong>Prive</strong>
              <small className="muted">Aucune reservation en ligne. Gestion manuelle uniquement.</small>
            </span>
          </label>
        </div>
        <small className="muted">
          {!allowsStudentBookings
            ? "Ce type de creneau n'accepte pas de reservation eleve."
            : visibilityIsPrivate
              ? "Un creneau prive ne peut pas etre reserve en ligne."
              : `Actuel: ${scopeGroupSummary(effectiveBookingScopes)}.`}
        </small>
      </fieldset>
    </>
  );
}
