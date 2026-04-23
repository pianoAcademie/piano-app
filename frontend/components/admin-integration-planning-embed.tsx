import Link from "next/link";

import type { AdminActivityOut, LocationOut } from "../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";
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
  language?: UiLanguage | string;
};

export default function AdminIntegrationPlanningEmbed({
  accountWebsite,
  activities,
  locations,
  selectedActivityId = "",
  selectedLocationId = "",
  selectedStartDate = "",
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

  const selectedActivity = eligibleActivities.find((activity) => activity.id === selectedActivityId) ?? null;
  const selectedLocation = activeLocations.find((location) => location.id === selectedLocationId) ?? null;
  const allLocationsLabel = t("admin.integration_embed.all_locations");
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
  const embedPath = selectedActivity ? `/embed/planning?${embedParams.toString()}` : "";
  const normalizedBaseUrl = normalizeBaseUrl(accountWebsite);
  const absoluteEmbedUrl = embedPath && normalizedBaseUrl ? `${normalizedBaseUrl}${embedPath}` : "";
  const iframeTitle =
    selectedActivity
      ? `${t("admin.integration_embed.iframe_title_prefix")} ${selectedActivity.name}${selectedLocation ? ` - ${selectedLocation.name}` : ` - ${allLocationsLabel}`}`
      : t("admin.integration_embed.external_planning");
  const iframeHtml = absoluteEmbedUrl
    ? `<iframe src="${absoluteEmbedUrl}" title="${iframeTitle}" width="100%" height="840" style="width:100%;min-height:840px;border:0;border-radius:16px;overflow:hidden;" loading="lazy" referrerpolicy="strict-origin-when-cross-origin"></iframe>`
    : "";

  return (
    <section className="card config-placeholder-card">
      <h3>{t("admin.integration_embed.title")}</h3>
      <p className="muted">{t("admin.integration_embed.subtitle")}</p>

      <form method="get" action="/admin/config" className="grid cols-2 config-form-grid top-gap-sm">
        <input type="hidden" name="section" value="integrations" />

        <label>
          {t("common.course")}
          <select name="integration_course_type_id" defaultValue={selectedActivityId}>
            <option value="">{t("admin.integration_embed.choose_course")}</option>
            {eligibleActivities.map((activity) => (
              <option key={activity.id} value={activity.id}>
                {activity.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          {t("common.location")}
          <select name="integration_location_id" defaultValue={selectedLocationId}>
            <option value="">{allLocationsLabel}</option>
            {activeLocations.map((location) => (
              <option key={location.id} value={location.id}>
                {location.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          {t("admin.integration_embed.start_date_optional")}
          <input type="date" name="integration_date" defaultValue={selectedStartDate} />
        </label>

        <div className="row span-2">
          <button type="submit">{t("admin.integration_embed.generate_iframe")}</button>
          {selectedActivity || selectedLocation || selectedStartDate ? (
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
                {selectedActivity?.name}
                {selectedLocation ? ` · ${selectedLocation.name}` : ` · ${allLocationsLabel}`}
                {selectedStartDate ? ` · ${t("admin.integration_embed.start_prefix")} ${selectedStartDate}` : ""}
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
