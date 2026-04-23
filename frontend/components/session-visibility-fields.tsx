"use client";

import { useMemo, useState } from "react";

import { type UiLanguage, uiText } from "../lib/ui-i18n";
import type { SessionAudienceScope } from "../lib/types";

type SessionVisibilityFieldsProps = {
  language: UiLanguage;
  initialVisibilityScopes: SessionAudienceScope[];
  initialBookingScopes: SessionAudienceScope[];
  allowsStudentBookings?: boolean;
  initialShowExternalRemainingSeats?: boolean;
};

const NON_PRIVATE_SCOPE_OPTIONS: Array<{ value: SessionAudienceScope }> = [
  { value: "EXTERNAL" },
  { value: "SUBSCRIPTION" },
  { value: "FORFAIT" },
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
    return uiText(language, "admin.planning.private_admin_only");
  }
  const labels = NON_PRIVATE_SCOPE_OPTIONS
    .filter((option) => scopes.includes(option.value))
    .map((option) =>
      option.value === "EXTERNAL"
        ? uiText(language, "admin.planning.audience.external")
        : option.value === "SUBSCRIPTION"
          ? uiText(language, "admin.planning.audience.subscription")
          : uiText(language, "admin.planning.audience.forfait"),
    );
  return labels.join(" + ");
}

export default function SessionVisibilityFields({
  language,
  initialVisibilityScopes,
  initialBookingScopes,
  allowsStudentBookings = true,
  initialShowExternalRemainingSeats = true,
}: SessionVisibilityFieldsProps): JSX.Element {
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
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
        <legend>{t("admin.planning.display")}</legend>
        <small className="muted">
          {t("admin.planning.visibility_help")}
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
                <strong>{option.value === "EXTERNAL" ? t("admin.planning.audience.external") : option.value === "SUBSCRIPTION" ? t("admin.planning.audience.subscription") : t("admin.planning.audience.forfait")}</strong>
                <small className="muted">
                  {option.value === "EXTERNAL"
                    ? t("admin.planning.audience.external_hint")
                    : option.value === "SUBSCRIPTION"
                      ? t("admin.planning.audience.subscription_hint")
                      : t("admin.planning.audience.forfait_hint")}
                </small>
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
              <strong>{t("admin.planning.audience.private")}</strong>
              <small className="muted">{t("admin.planning.audience.private_visibility_hint")}</small>
            </span>
          </label>
        </div>
        <small className="muted">{t("admin.planning.current_scopes", { value: scopeGroupSummary(visibilityScopes, language) })}</small>
      </fieldset>

      <fieldset className="session-audience-fieldset">
        <legend>{t("admin.planning.online_booking")}</legend>
        <small className="muted">
          {t("admin.planning.online_booking_help")}
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
                <strong>{option.value === "EXTERNAL" ? t("admin.planning.audience.external") : option.value === "SUBSCRIPTION" ? t("admin.planning.audience.subscription") : t("admin.planning.audience.forfait")}</strong>
                <small className="muted">
                  {option.value === "EXTERNAL"
                    ? t("admin.planning.audience.external_hint")
                    : option.value === "SUBSCRIPTION"
                      ? t("admin.planning.audience.subscription_hint")
                      : t("admin.planning.audience.forfait_hint")}
                </small>
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
              <strong>{t("admin.planning.audience.private")}</strong>
              <small className="muted">{t("admin.planning.private_booking_hint")}</small>
            </span>
          </label>
        </div>
        <small className="muted">
          {!allowsStudentBookings
            ? t("admin.planning.no_student_booking_type")
            : visibilityIsPrivate
              ? t("admin.planning.private_slot_no_booking")
              : t("admin.planning.current_scopes", { value: scopeGroupSummary(effectiveBookingScopes, language) })}
        </small>
      </fieldset>

      <fieldset className="session-audience-fieldset">
        <legend>{t("admin.planning.external_integration")}</legend>
        <small className="muted">
          {t("admin.planning.external_integration_help")}
        </small>
        <label className="session-audience-option">
          <input type="hidden" name="show_external_remaining_seats" value="0" />
          <input
            type="checkbox"
            name="show_external_remaining_seats"
            value="1"
            defaultChecked={initialShowExternalRemainingSeats}
          />
          <span>
            <strong>{t("admin.planning.show_remaining_seats")}</strong>
            <small className="muted">{t("admin.planning.remaining_seats_help")}</small>
          </span>
        </label>
      </fieldset>
    </>
  );
}
