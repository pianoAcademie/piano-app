"use client";

import { useMemo, useState } from "react";

import type { SessionAudienceScope } from "../lib/types";

type UiLanguage = "fr" | "en";

type LocalizedLabel = Record<UiLanguage, string>;

type SessionVisibilityFieldsProps = {
  initialVisibilityScopes: SessionAudienceScope[];
  initialBookingScopes: SessionAudienceScope[];
  allowsStudentBookings?: boolean;
  language?: UiLanguage;
};

const NON_PRIVATE_SCOPE_OPTIONS: Array<{ value: SessionAudienceScope; label: LocalizedLabel; hint: LocalizedLabel }> = [
  {
    value: "EXTERNAL",
    label: { fr: "Externe", en: "External" },
    hint: {
      fr: "Visible ou reservable hors connexion, et aussi pour tous les clients connectes.",
      en: "Visible or bookable without sign-in, and also for all signed-in clients.",
    },
  },
  {
    value: "SUBSCRIPTION",
    label: { fr: "Abonne / carnet", en: "Subscription / pass" },
    hint: {
      fr: "Reserve aux clients avec abonnement ou carnet compatible.",
      en: "Reserved for clients with a compatible subscription or lesson pass.",
    },
  },
  {
    value: "FORFAIT",
    label: { fr: "Forfait", en: "Package" },
    hint: {
      fr: "Reserve aux clients couverts par un forfait compatible.",
      en: "Reserved for clients covered by a compatible package.",
    },
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

function scopeGroupSummary(scopes: SessionAudienceScope[], language: UiLanguage): string {
  if (scopes.length === 1 && scopes[0] === "PRIVATE") {
    return language === "en" ? "Private (admin only)" : "Prive (admin seulement)";
  }
  const labels = NON_PRIVATE_SCOPE_OPTIONS.filter((option) => scopes.includes(option.value)).map((option) => option.label[language]);
  return labels.join(" + ");
}

export default function SessionVisibilityFields({
  initialVisibilityScopes,
  initialBookingScopes,
  allowsStudentBookings = true,
  language = "fr",
}: SessionVisibilityFieldsProps): JSX.Element {
  const text = language === "en"
    ? {
        visibility: "Visibility",
        visibilityHint: "Check one or more cases. Students already enrolled always see the slot in their portal, even if visibility is restricted.",
        private: "Private",
        privateVisibilityHint: "Visible only in admin. Already-enrolled students still see it in their portal.",
        current: "Current",
        onlineBooking: "Online booking",
        onlineBookingHint: "Check one or more cases. In practice, External also makes the slot bookable for all signed-in clients, even without an active formula.",
        privateBookingHint: "No online booking. Manual management only.",
        noStudentBookings: "This slot type does not accept student bookings.",
        privateSlotsNotBookable: "A private slot cannot be booked online.",
      }
    : {
        visibility: "Affichage",
        visibilityHint: "Cochez un ou plusieurs cas. Les eleves deja inscrits voient toujours le creneau dans leur portail, meme si l'affichage est restreint.",
        private: "Prive",
        privateVisibilityHint: "Visible uniquement en admin. Les eleves deja inscrits le voient quand meme dans leur portail.",
        current: "Actuel",
        onlineBooking: "Reservation en ligne",
        onlineBookingHint: "Cochez un ou plusieurs cas. En pratique, Externe rend aussi le creneau reservable pour tous les clients connectes, meme sans formule active.",
        privateBookingHint: "Aucune reservation en ligne. Gestion manuelle uniquement.",
        noStudentBookings: "Ce type de creneau n'accepte pas de reservation eleve.",
        privateSlotsNotBookable: "Un creneau prive ne peut pas etre reserve en ligne.",
      };

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
        <legend>{text.visibility}</legend>
        <small className="muted">{text.visibilityHint}</small>
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
                <strong>{option.label[language]}</strong>
                <small className="muted">{option.hint[language]}</small>
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
              <strong>{text.private}</strong>
              <small className="muted">{text.privateVisibilityHint}</small>
            </span>
          </label>
        </div>
        <small className="muted">{text.current}: {scopeGroupSummary(visibilityScopes, language)}.</small>
      </fieldset>

      <fieldset className="session-audience-fieldset">
        <legend>{text.onlineBooking}</legend>
        <small className="muted">
          {text.onlineBookingHint}
        </small>
        {visibilityIsPrivate || !allowsStudentBookings ? (
          <input type="hidden" name="booking_scopes" value="PRIVATE" />
        ) : null}
        <div className="session-audience-option-list">
          {NON_PRIVATE_SCOPE_OPTIONS.map((option) => (
            <label key={`booking-${option.value}`} className={`session-audience-option ${visibilityIsPrivate || !allowsStudentBookings ? "is-disabled" : ""}`}>
              <input
                type="checkbox"
                name={visibilityIsPrivate || !allowsStudentBookings ? undefined : "booking_scopes"}
                value={option.value}
                checked={!bookingIsPrivate && effectiveBookingScopes.includes(option.value)}
                disabled={visibilityIsPrivate || !allowsStudentBookings}
                onChange={() => setBookingScopes((current) => toggleScope(current, option.value))}
              />
              <span>
                <strong>{option.label[language]}</strong>
                <small className="muted">{option.hint[language]}</small>
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
              <strong>{text.private}</strong>
              <small className="muted">{text.privateBookingHint}</small>
            </span>
          </label>
        </div>
        <small className="muted">
          {!allowsStudentBookings
            ? text.noStudentBookings
            : visibilityIsPrivate
              ? text.privateSlotsNotBookable
              : `${text.current}: ${scopeGroupSummary(effectiveBookingScopes, language)}.`}
        </small>
      </fieldset>
    </>
  );
}
