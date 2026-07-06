import Link from "next/link";

import type { AdminActivityOut, LocationOut } from "../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";
import CopyLinkButton from "./copy-link-button";

const VIRTUAL_PARIS_LOCATION_ID = "__virtual_paris__";
const EMBED_IFRAME_HEIGHT = 900;
const PARIS_LOCATION_TOKENS = ["dulong", "scheffer", "assas", "richelieu", "pompe"];

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

function normalizeLocationName(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/[^a-zA-Z0-9]+/g, " ")
    .trim()
    .toLowerCase();
}

function isParisAggregateLocation(location: LocationOut): boolean {
  const normalized = normalizeLocationName(location.name);
  return PARIS_LOCATION_TOKENS.some((token) => normalized.includes(token));
}

function isIsoDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value.trim());
}

type AdminIntegrationPlanningEmbedProps = {
  accountWebsite?: string | null;
  activities: AdminActivityOut[];
  locations: LocationOut[];
  selectedActivityIds?: string[];
  selectedLocationId?: string;
  selectedDisplayDate?: string;
  language?: UiLanguage | string;
};

export default function AdminIntegrationPlanningEmbed({
  accountWebsite,
  activities,
  locations,
  selectedActivityIds = [],
  selectedLocationId = "",
  selectedDisplayDate = "",
  language: languageProp = "fr",
}: AdminIntegrationPlanningEmbedProps): JSX.Element {
  const language = normalizeUiLanguage(languageProp);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const locale = localeForUiLanguage(language);
  const eligibleActivities = [...activities]
    .filter((activity) => activity.active && activity.allows_student_bookings)
    .sort((left, right) => left.name.localeCompare(right.name, locale));
  const activeLocations = [...locations]
    .filter((location) => location.active)
    .sort((left, right) => left.name.localeCompare(right.name, locale));
  const parisLocations = activeLocations.filter(isParisAggregateLocation);
  const selectableLocations = [
    ...(parisLocations.length > 0
      ? [
          {
            id: VIRTUAL_PARIS_LOCATION_ID,
            name: "Paris - tous les lieux",
          },
        ]
      : []),
    ...activeLocations.map((location) => ({
      id: location.id,
      name: location.name,
    })),
  ];

  const eligibleActivityIds = new Set(eligibleActivities.map((activity) => activity.id));
  const selectedActivityIdSet = new Set(selectedActivityIds.filter((id) => eligibleActivityIds.has(id)));
  const selectedActivities = eligibleActivities.filter((activity) => selectedActivityIdSet.has(activity.id));
  const selectedLocation = activeLocations.find((location) => location.id === selectedLocationId) ?? null;
  const isParisVirtualLocation = selectedLocationId === VIRTUAL_PARIS_LOCATION_ID && parisLocations.length > 0;
  const selectedLocationLabel = isParisVirtualLocation
    ? "Paris - tous les lieux"
    : (selectableLocations.find((location) => location.id === selectedLocationId)?.name ?? "");
  const selectedActivityLabel = selectedActivities.map((activity) => activity.name).join(" + ");
  const embedPath = (() => {
    if (selectedActivities.length === 0 || (!selectedLocation && !isParisVirtualLocation)) {
      return "";
    }
    const params = new URLSearchParams();
    selectedActivities.forEach((activity) => {
      params.append("course_type_id", activity.id);
    });
    if (isParisVirtualLocation) {
      params.set("location_group", "paris");
    } else if (selectedLocation) {
      params.set("location_id", selectedLocation.id);
    }
    if (isIsoDate(selectedDisplayDate)) {
      params.set("date", selectedDisplayDate.trim());
    }
    if (language === "en") {
      params.set("lang", "en");
    }
    return `/embed/planning?${params.toString()}`;
  })();
  const normalizedBaseUrl = normalizeBaseUrl(accountWebsite);
  const absoluteEmbedUrl = embedPath && normalizedBaseUrl ? `${normalizedBaseUrl}${embedPath}` : "";
  const iframeTitle =
    selectedActivities.length > 0
      ? `${t("admin.integration_embed.iframe_title_prefix")} ${selectedActivityLabel}${selectedLocationLabel ? ` - ${selectedLocationLabel}` : ""}`
      : t("admin.integration_embed.external_planning");
  const iframeHtml = absoluteEmbedUrl
    ? `<iframe src="${absoluteEmbedUrl}" title="${iframeTitle}" width="100%" height="${EMBED_IFRAME_HEIGHT}" style="width:100%;min-height:${EMBED_IFRAME_HEIGHT}px;border:0;border-radius:16px;overflow:hidden;" loading="lazy" referrerpolicy="strict-origin-when-cross-origin"></iframe>`
    : "";

  return (
    <section className="card config-placeholder-card">
      <h3>{t("admin.integration_embed.title")}</h3>
      <p className="muted">{t("admin.integration_embed.subtitle")}</p>

      <form method="get" action="/admin/config" className="grid cols-2 config-form-grid top-gap-sm">
        <input type="hidden" name="section" value="integrations" />

        <fieldset className="integration-course-picker">
          <legend>{t("common.course")}</legend>
          <p className="muted">{t("admin.integration_embed.choose_courses_help")}</p>
          <div className="integration-course-options">
            {eligibleActivities.map((activity) => (
              <label key={activity.id} className="checkline integration-course-option">
                <input
                  type="checkbox"
                  name="integration_course_type_id"
                  value={activity.id}
                  defaultChecked={selectedActivityIdSet.has(activity.id)}
                />
                <span>{activity.name}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <label>
          {t("common.location")}
          <select name="integration_location_id" defaultValue={selectedLocationId}>
            <option value="">{language === "en" ? "Choose a location" : "Choisir un lieu"}</option>
            {selectableLocations.map((location) => (
              <option key={location.id} value={location.id}>
                {location.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          {language === "en" ? "Display date" : "Date d affichage"}
          <input type="date" name="integration_date" defaultValue={isIsoDate(selectedDisplayDate) ? selectedDisplayDate : ""} />
        </label>

        <div className="row span-2">
          <button type="submit">{t("admin.integration_embed.generate_iframe")}</button>
          {selectedActivities.length > 0 || selectedLocationId || selectedDisplayDate ? (
            <Link className="ghost small-btn" href="/admin/config?section=integrations">
              {t("common.reset")}
            </Link>
          ) : null}
        </div>
      </form>

      <section className="top-gap-sm">
        <h4>{t("admin.integration_embed.rules_title")}</h4>
        <ul className="config-error-list">
          <li>{t("admin.integration_embed.rule_external_booking")}</li>
          <li>{t("admin.integration_embed.rule_external_price")}</li>
          <li>{t("admin.integration_embed.rule_visitor_flow")}</li>
          <li>{t("admin.integration_embed.rule_start_date")}</li>
        </ul>
      </section>

      {!normalizedBaseUrl ? (
        <p className="flash-err top-gap-sm">{t("admin.integration_embed.missing_public_site")}</p>
      ) : null}

      {embedPath ? (
        <section className="top-gap-sm">
          <div className="row spread">
            <div>
              <h4>{t("admin.integration_embed.result")}</h4>
              <p className="muted">
                {selectedActivityLabel} · {selectedLocationLabel}
                {isIsoDate(selectedDisplayDate) ? ` · ${t("admin.integration_embed.start_prefix")} ${selectedDisplayDate}` : ""}
              </p>
            </div>
            <div className="row">
              <Link className="ghost small-btn" href={embedPath} target="_blank" rel="noreferrer">
                {t("admin.integration_embed.preview")}
              </Link>
              {absoluteEmbedUrl ? (
                <CopyLinkButton
                  value={absoluteEmbedUrl}
                  label={t("admin.integration_embed.copy_url")}
                  copiedLabel={t("common.link_copied")}
                />
              ) : null}
              {iframeHtml ? (
                <CopyLinkButton
                  value={iframeHtml}
                  label={t("admin.integration_embed.copy_html")}
                  copiedLabel={t("common.link_copied")}
                />
              ) : null}
            </div>
          </div>

          <label className="top-gap-sm">
            {t("admin.integration_embed.iframe_url")}
            <textarea rows={3} readOnly defaultValue={absoluteEmbedUrl || embedPath} />
          </label>

          <label className="top-gap-sm">
            {t("admin.integration_embed.html_code")}
            <textarea rows={6} readOnly defaultValue={iframeHtml || `<!-- ${t("admin.integration_embed.configure_public_site_first")} -->`} />
          </label>
        </section>
      ) : null}
    </section>
  );
}
