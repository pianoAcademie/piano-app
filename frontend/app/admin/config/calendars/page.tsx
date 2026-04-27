import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import ConditionalConfirmSubmitButton from "../../../../components/conditional-confirm-submit-button";
import ConfirmSubmitButton from "../../../../components/confirm-submit-button";

import {
  bulkAdminQuoteSchoolCalendarsAction,
  createAdminQuoteSchoolCalendarConfigAction,
  deployAdminQuoteSchoolCalendarAction,
  deployAdminQuoteSchoolCalendarGroupAction,
  deleteAdminQuoteSchoolCalendarConfigAction,
  previewAdminQuoteSchoolCalendarDeploymentAction,
  previewAdminQuoteSchoolCalendarGroupDeploymentAction,
  removeAdminQuoteSchoolCalendarDeploymentAction,
  removeAdminQuoteSchoolCalendarGroupDeploymentAction,
  syncAdminQuoteSchoolCalendarDeploymentAction,
  syncAdminQuoteSchoolCalendarGroupAction,
  updateAdminQuoteSchoolCalendarConfigAction,
  updateAdminQuoteSchoolCalendarGroupAction,
} from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import { normalizeUiLanguage, type UiLanguage, uiText } from "../../../../lib/ui-i18n";
import type { LocationOut, UserOut } from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

type QuoteSchoolCalendarPeriodOut = {
  start_date: string;
  end_date: string;
  label: string | null;
};

type QuoteSchoolCalendarOut = {
  id: string;
  name: string;
  school_year_label: string;
  location_id: string;
  vacation_periods: QuoteSchoolCalendarPeriodOut[];
  holiday_dates: string[];
  closure_dates: string[];
  is_active: boolean;
  deployment_status: string;
  deployment_last_at: string | null;
  deployment_last_sync_at: string | null;
  deployment_source_hash: string | null;
  deployment_generated_count: number;
  deployment_generated_active_count: number;
  updated_at: string;
};

type QuoteSchoolCalendarGeneratedSlotOut = {
  session_id: string;
  location_id: string;
  date: string;
  reason_types: string[];
  status: string;
  title: string;
  start_at: string;
  end_at: string;
};

type CalendarGroupSummary = {
  key: string;
  name: string;
  school_year_label: string;
  items: QuoteSchoolCalendarOut[];
  representative: QuoteSchoolCalendarOut;
  location_names: string[];
  active_slots: number;
  badge_class: string;
  badge_label: string;
  is_fully_removed: boolean;
};

type GeneratedGroupSlotRow = QuoteSchoolCalendarGeneratedSlotOut & {
  location_name: string;
};

type QuoteSchoolCalendarDeploymentPreviewOut = {
  calendar_id: string;
  location_id: string;
  deployment_status: string;
  source_hash: string;
  existing_generated_active_count: number;
  summary: {
    total_target_days: number;
    vacation_days: number;
    holiday_days: number;
    closure_days: number;
  };
  would_create: number;
  would_keep: number;
  would_reactivate: number;
  would_cancel: number;
  sample_dates: string[];
};

function readParam(params: SearchParams, key: string): string {
  const raw = params[key];
  if (Array.isArray(raw)) {
    return raw[0] ?? "";
  }
  return raw ?? "";
}

function calendarVacationPeriodsText(periods: QuoteSchoolCalendarPeriodOut[]): string {
  if (!periods.length) {
    return "";
  }
  return periods
    .map((period) => {
      const label = (period.label || "").trim();
      return label
        ? `${period.start_date} | ${period.end_date} | ${label}`
        : `${period.start_date} | ${period.end_date}`;
    })
    .join("\n");
}

function calendarDatesText(dates: string[]): string {
  if (!dates.length) {
    return "";
  }
  return dates.join("\n");
}

function deploymentStatusLabel(value: string, language: UiLanguage): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "deployed") {
    return uiText(language, "admin.calendars.deployment_deployed");
  }
  if (normalized === "stale") {
    return uiText(language, "admin.calendars.deployment_stale");
  }
  if (normalized === "removed") {
    return uiText(language, "admin.calendars.deployment_removed");
  }
  return uiText(language, "admin.calendars.deployment_not_deployed");
}

function deploymentStatusClass(value: string): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "deployed") {
    return "status-ok";
  }
  if (normalized === "stale") {
    return "status-warn";
  }
  return "status-off";
}

function buildCalendarsPath(params: {
  locationFilter?: string;
  deploymentFilter?: string;
  statusFilter?: string;
  generatedFor?: string;
  previewGroup?: string;
  editGroup?: string;
  generatedGroup?: string;
  createModal?: string;
}): string {
  const search = new URLSearchParams();
  if (params.locationFilter) {
    search.set("location_filter", params.locationFilter);
  }
  if (params.deploymentFilter) {
    search.set("deployment_filter", params.deploymentFilter);
  }
  if (params.statusFilter) {
    search.set("status_filter", params.statusFilter);
  }
  if (params.generatedFor) {
    search.set("generated_for", params.generatedFor);
  }
  if (params.previewGroup) {
    search.set("preview_group", params.previewGroup);
  }
  if (params.editGroup) {
    search.set("edit_group", params.editGroup);
  }
  if (params.generatedGroup) {
    search.set("generated_group", params.generatedGroup);
  }
  if (params.createModal === "1") {
    search.set("create_modal", "1");
  }
  const query = search.toString();
  return query ? `/admin/config/calendars?${query}` : "/admin/config/calendars";
}

function calendarLocationSummary(names: string[]): string {
  if (names.length <= 4) {
    return names.join(", ");
  }
  const preview = names.slice(0, 4).join(", ");
  return `${preview} +${names.length - 4}`;
}

function deploymentReasonLabel(value: string, language: UiLanguage): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "holiday") {
    return uiText(language, "admin.calendars.reason_holiday");
  }
  if (normalized === "vacation") {
    return uiText(language, "admin.calendars.reason_vacation");
  }
  if (normalized === "closure") {
    return uiText(language, "admin.calendars.reason_closure");
  }
  return value || "-";
}

function deploymentReasonListLabel(values: string[], language: UiLanguage): string {
  if (!values.length) {
    return "-";
  }
  return values.map((value) => deploymentReasonLabel(value, language)).join(", ");
}

export default async function AdminSchoolCalendarsPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const params = searchParams ?? {};
  const okMessage = readParam(params, "ok");
  const errorMessage = readParam(params, "error");
  const generatedFor = readParam(params, "generated_for");
  const previewGroupKey = readParam(params, "preview_group");
  const editGroupKey = readParam(params, "edit_group");
  const generatedGroupKey = readParam(params, "generated_group");
  const createModalOpen = readParam(params, "create_modal") === "1";
  const locationFilter = readParam(params, "location_filter");
  const deploymentFilter = readParam(params, "deployment_filter");
  const statusFilter = readParam(params, "status_filter");

  const [quoteSchoolCalendarsResult, locationsResult] = await Promise.all([
    backendRequest<QuoteSchoolCalendarOut[]>("/api/v1/quote-school-calendars", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=false", {}, token),
  ]);

  const loadErrors: string[] = [];
  const quoteSchoolCalendars = quoteSchoolCalendarsResult.ok
    ? quoteSchoolCalendarsResult.data
    : (() => {
        loadErrors.push(`${t("admin.calendars.load_school_calendars")}: ${quoteSchoolCalendarsResult.message}`);
        return [] as QuoteSchoolCalendarOut[];
      })();
  const locations = locationsResult.ok
    ? locationsResult.data
    : (() => {
        loadErrors.push(`${t("admin.calendars.load_locations")}: ${locationsResult.message}`);
        return [] as LocationOut[];
      })();

  const locationById = new Map(locations.map((row) => [row.id, row.name]));
  const sortLocale = language === "en" ? "en" : "fr";
  const filteredCalendars = quoteSchoolCalendars.filter((row) => {
    if (locationFilter && row.location_id !== locationFilter) {
      return false;
    }
    if (deploymentFilter && row.deployment_status !== deploymentFilter) {
      return false;
    }
    if (statusFilter === "active" && !row.is_active) {
      return false;
    }
    if (statusFilter === "inactive" && row.is_active) {
      return false;
    }
    return true;
  });
  const groupedCalendars = Array.from(
    quoteSchoolCalendars.reduce<Map<string, { key: string; name: string; school_year_label: string; items: QuoteSchoolCalendarOut[] }>>(
      (acc, row) => {
        const key = `${row.name.trim().toLowerCase()}::${row.school_year_label.trim().toLowerCase()}`;
        const existing = acc.get(key);
        if (existing) {
          existing.items.push(row);
        } else {
          acc.set(key, {
            key,
            name: row.name,
            school_year_label: row.school_year_label,
            items: [row],
          });
        }
        return acc;
      },
      new Map(),
    ).values(),
  ).sort((a, b) => a.name.localeCompare(b.name, sortLocale));
  const groupSummaries: CalendarGroupSummary[] = groupedCalendars.map((group) => {
    const representative = [...group.items].sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0] ?? group.items[0];
    const locationNames = Array.from(new Set(group.items.map((item) => locationById.get(item.location_id) || item.location_id))).sort((a, b) =>
      a.localeCompare(b, sortLocale)
    );
    const activeSlots = group.items.reduce((sum, item) => sum + Number(item.deployment_generated_active_count || 0), 0);
    const hasStale = group.items.some((item) => item.deployment_status === "stale");
    const allDeployed = group.items.every((item) => item.deployment_status === "deployed");
    const allRemoved = group.items.every((item) => item.deployment_status === "removed");
    return {
      ...group,
      representative,
      location_names: locationNames,
      active_slots: activeSlots,
      badge_class: hasStale ? "status-warn" : allDeployed ? "status-ok" : allRemoved ? "status-off" : "status-warn",
      badge_label: hasStale
        ? t("admin.calendars.deployment_stale")
        : allDeployed
          ? t("admin.calendars.deployment_deployed")
          : allRemoved
            ? t("admin.calendars.deployment_removed")
            : t("admin.calendars.deployment_partial"),
      is_fully_removed: allRemoved,
    };
  });
  const returnPath = buildCalendarsPath({
    locationFilter,
    deploymentFilter,
    statusFilter,
    generatedFor,
    previewGroup: previewGroupKey,
    editGroup: editGroupKey,
    generatedGroup: generatedGroupKey,
    createModal: createModalOpen ? "1" : "",
  });
  const basePath = buildCalendarsPath({
    locationFilter,
    deploymentFilter,
    statusFilter,
    generatedFor,
    previewGroup: previewGroupKey,
    generatedGroup: generatedGroupKey,
  });
  const createModalPath = buildCalendarsPath({
    locationFilter,
    deploymentFilter,
    statusFilter,
    generatedFor,
    previewGroup: previewGroupKey,
    generatedGroup: generatedGroupKey,
    createModal: "1",
  });
  const resetFiltersPath = buildCalendarsPath({
    generatedFor,
    previewGroup: previewGroupKey,
    editGroup: editGroupKey,
    generatedGroup: generatedGroupKey,
    createModal: createModalOpen ? "1" : "",
  });

  const previewGroup = groupSummaries.find((group) => group.key === previewGroupKey) ?? null;
  const editGroup = groupSummaries.find((group) => group.key === editGroupKey) ?? null;
  const generatedGroup = groupSummaries.find((group) => group.key === generatedGroupKey) ?? null;
  const groupPreviewRows = previewGroup
    ? (
        await Promise.all(
          previewGroup.items.map(async (item) => {
            const result = await backendRequest<QuoteSchoolCalendarDeploymentPreviewOut>(
              `/api/v1/quote-school-calendars/${encodeURIComponent(item.id)}/deployment/preview`,
              {},
              token,
            );
            if (!result.ok) {
              loadErrors.push(
                `${t("admin.calendars.load_preview")}: ${item.name} (${locationById.get(item.location_id) || item.location_id}): ${result.message}`,
              );
              return null;
            }
            return { calendar: item, preview: result.data };
          }),
        )
      ).filter((entry): entry is { calendar: QuoteSchoolCalendarOut; preview: QuoteSchoolCalendarDeploymentPreviewOut } => entry !== null)
    : [];

  const groupPreviewTotals = groupPreviewRows.reduce(
    (acc, row) => {
      acc.totalTargetDays += Number(row.preview.summary?.total_target_days ?? 0);
      acc.vacationDays += Number(row.preview.summary?.vacation_days ?? 0);
      acc.holidayDays += Number(row.preview.summary?.holiday_days ?? 0);
      acc.closureDays += Number(row.preview.summary?.closure_days ?? 0);
      acc.wouldCreate += Number(row.preview.would_create ?? 0);
      acc.wouldKeep += Number(row.preview.would_keep ?? 0);
      acc.wouldReactivate += Number(row.preview.would_reactivate ?? 0);
      acc.wouldCancel += Number(row.preview.would_cancel ?? 0);
      acc.existingGenerated += Number(row.preview.existing_generated_active_count ?? 0);
      return acc;
    },
    {
      totalTargetDays: 0,
      vacationDays: 0,
      holidayDays: 0,
      closureDays: 0,
      wouldCreate: 0,
      wouldKeep: 0,
      wouldReactivate: 0,
      wouldCancel: 0,
      existingGenerated: 0,
    },
  );
  const selectedCalendar = quoteSchoolCalendars.find((row) => row.id === generatedFor) ?? null;
  const generatedSlotsResult = selectedCalendar
    ? await backendRequest<QuoteSchoolCalendarGeneratedSlotOut[]>(
        `/api/v1/quote-school-calendars/${encodeURIComponent(selectedCalendar.id)}/generated-blocking-slots`,
        {},
        token,
      )
    : null;
  const generatedSlots = generatedSlotsResult?.ok ? generatedSlotsResult.data : [];
  if (generatedSlotsResult && !generatedSlotsResult.ok) {
    loadErrors.push(`${t("admin.calendars.load_generated_slots")}: ${generatedSlotsResult.message}`);
  }
  const generatedGroupSlots = generatedGroup
    ? (
        await Promise.all(
          generatedGroup.items.map(async (item) => {
            const result = await backendRequest<QuoteSchoolCalendarGeneratedSlotOut[]>(
              `/api/v1/quote-school-calendars/${encodeURIComponent(item.id)}/generated-blocking-slots`,
              {},
              token,
            );
            if (!result.ok) {
              loadErrors.push(
                `${t("admin.calendars.load_group_slots")}: ${generatedGroup.name} (${locationById.get(item.location_id) || item.location_id}): ${result.message}`,
              );
              return [] as GeneratedGroupSlotRow[];
            }
            const locationName = locationById.get(item.location_id) || item.location_id;
            return result.data.map((slot) => ({ ...slot, location_name: locationName }));
          }),
        )
      )
        .flat()
        .sort((a, b) => `${a.date}-${a.location_name}-${a.title}`.localeCompare(`${b.date}-${b.location_name}-${b.title}`, sortLocale))
    : [];
  const modalErrorMessage = errorMessage || "";

  const renderCalendarBlockForm = (params: {
    action: (formData: FormData) => Promise<void>;
    returnTo: string;
    successReturnTo: string;
    submitLabel: string;
    cancelHref: string;
    defaults: {
      name: string;
      schoolYearLabel: string;
      selectedLocationIds: string[];
      vacationPeriodsText: string;
      holidayDatesText: string;
      closureDatesText: string;
      isActive: boolean;
    };
    applyPlanningLabel: string;
    existingEntries?: Array<{ calendarId: string; locationId: string }>;
    errorText?: string;
    footerNote?: string;
    extraActions?: JSX.Element | null;
  }): JSX.Element => (
    <form action={params.action} className="calendar-editor-form">
      <input type="hidden" name="return_to" value={params.returnTo} />
      <input type="hidden" name="success_return_to" value={params.successReturnTo} />
      {(params.existingEntries || []).map((entry) => (
        <input
          key={`calendar-editor-existing-${entry.calendarId}-${entry.locationId}`}
          type="hidden"
          name="existing_calendar_entries"
          value={`${entry.calendarId}:${entry.locationId}`}
        />
      ))}
      {params.errorText ? (
        <section className="flash-err modal-flash" role="alert">
          {params.errorText}
        </section>
      ) : null}
      <div className="grid cols-2 config-form-grid">
        <label>
          {t("admin.calendars.block_name")}
          <input
            type="text"
            name="name"
            defaultValue={params.defaults.name}
            required
            maxLength={180}
            placeholder={t("admin.calendars.block_name_placeholder")}
          />
        </label>
        <label>
          {t("admin.calendars.school_year")}
          <input
            type="text"
            name="school_year_label"
            defaultValue={params.defaults.schoolYearLabel}
            required
            maxLength={40}
            placeholder={t("admin.calendars.school_year_placeholder")}
          />
        </label>
      </div>

      <section className="calendar-editor-section">
        <header className="calendar-editor-section-header">
          <h4>{t("admin.calendars.target_locations_title")}</h4>
          <p className="muted">{t("admin.calendars.target_locations_help")}</p>
        </header>
        <fieldset className="calendar-locations-fieldset">
          <div className="calendar-location-grid">
            {locations.map((location) => (
              <label key={`calendar-modal-location-${location.id}`} className="checkline">
                <input
                  type="checkbox"
                  name="location_ids"
                  value={location.id}
                  defaultChecked={params.defaults.selectedLocationIds.includes(location.id)}
                />
                {location.name}
              </label>
            ))}
          </div>
        </fieldset>
      </section>

      <section className="calendar-editor-section">
        <header className="calendar-editor-section-header">
          <h4>{t("admin.calendars.date_entry_title")}</h4>
          <p className="muted">{t("admin.calendars.date_entry_help")}</p>
        </header>
        <div className="calendar-inline-help">
          <strong>{t("admin.calendars.quick_entry_title")}</strong>
          <p className="muted">
            {t("admin.calendars.quick_entry_help")} <code>{t("admin.calendars.quick_entry_format")}</code>.{" "}
            {t("admin.calendars.quick_entry_single_date")}
          </p>
        </div>
        <div className="grid cols-3 config-form-grid calendar-editor-text-grid">
          <label className="calendar-textarea-field">
            {t("admin.calendars.vacation_periods")}
            <textarea
              name="vacation_periods_text"
              rows={8}
              defaultValue={params.defaults.vacationPeriodsText}
              placeholder={t("admin.calendars.vacation_periods_placeholder")}
            />
          </label>
          <label className="calendar-textarea-field">
            {t("admin.calendars.holidays")}
            <textarea
              name="holiday_dates_text"
              rows={8}
              defaultValue={params.defaults.holidayDatesText}
              placeholder={t("admin.calendars.holidays_placeholder")}
            />
          </label>
          <label className="calendar-textarea-field">
            {t("admin.calendars.closures")}
            <textarea
              name="closure_dates_text"
              rows={8}
              defaultValue={params.defaults.closureDatesText}
              placeholder={t("admin.calendars.closures_placeholder")}
            />
          </label>
        </div>
      </section>

      <section className="calendar-editor-section">
        <header className="calendar-editor-section-header">
          <h4>{t("admin.calendars.options_title")}</h4>
          <p className="muted">{t("admin.calendars.options_help")}</p>
        </header>
        <div className="calendar-editor-toggle-grid">
          <label className="checkline">
            <input type="checkbox" name="is_active" defaultChecked={params.defaults.isActive} />
            {t("common.active")}
          </label>
          <label className="checkline">
            <input type="checkbox" name="apply_to_management_planning" />
            {params.applyPlanningLabel}
          </label>
        </div>
      </section>

      <footer className="calendar-editor-footer">
        <div className="calendar-editor-footer-copy">
          <p className="muted">{params.footerNote || t("admin.calendars.footer_default")}</p>
          {params.extraActions}
        </div>
        <div className="row wrap gap-sm">
          <Link className="ghost" href={params.cancelHref}>
            {t("common.cancel")}
          </Link>
          <button type="submit">{params.submitLabel}</button>
        </div>
      </footer>
    </form>
  );

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>{t("admin.calendars.page_title")}</h2>
            <p className="muted">{t("admin.calendars.page_subtitle")}</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href="/admin/config">{t("admin.calendars.back_config")}</Link>
            <Link className="ghost" href="/admin/config/quotes">{t("admin.calendars.back_quotes_config")}</Link>
          </div>
        </div>
      </section>

      {okMessage ? (
        <section className="card calendar-feedback-banner calendar-feedback-banner-ok" role="status">
          <strong>{t("admin.calendars.feedback_saved_title")}</strong>
          <p>{okMessage}</p>
        </section>
      ) : null}
      {errorMessage ? (
        <section className="card calendar-feedback-banner calendar-feedback-banner-error" role="alert">
          <strong>{t("admin.calendars.feedback_failed_title")}</strong>
          <p>{errorMessage}</p>
        </section>
      ) : null}
      {loadErrors.length > 0 ? (
        <section className="card">
          <h3>{t("admin.calendars.loading_errors")}</h3>
          <ul className="config-error-list">
            {loadErrors.map((message) => (
              <li key={message} className="flash-err">{message}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h3>{t("admin.calendars.group_section_title")}</h3>
            <p className="muted">{t("admin.calendars.group_section_subtitle")}</p>
          </div>
          <Link className="ghost" href={createModalPath}>
            {t("admin.calendars.add_calendar")}
          </Link>
        </div>

        <section className="top-gap-sm">
          <div className="row spread wrap gap-sm">
            <div>
              <h4>{t("admin.calendars.blocks_title")}</h4>
              <p className="muted">{t("admin.calendars.blocks_subtitle")}</p>
            </div>
            <span className="status-pill status-info">{t("admin.calendars.block_count", { count: groupSummaries.length })}</span>
          </div>
          {groupSummaries.length === 0 ? (
            <p className="muted">{t("admin.calendars.no_group_blocks")}</p>
          ) : (
            <div className="table-wrap top-gap-sm">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t("admin.calendars.column_block")}</th>
                    <th>{t("admin.calendars.column_year")}</th>
                    <th>{t("admin.calendars.column_locations")}</th>
                    <th>{t("admin.calendars.column_deployment")}</th>
                    <th>{t("admin.calendars.column_active_slots")}</th>
                    <th>{t("common.actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {groupSummaries.map((group) => (
                    <tr key={group.key}>
                      <td><strong>{group.name}</strong></td>
                      <td>{group.school_year_label}</td>
                      <td title={group.location_names.join(", ")}>{calendarLocationSummary(group.location_names)}</td>
                      <td><span className={`status-pill ${group.badge_class}`}>{group.badge_label}</span></td>
                      <td>{group.active_slots}</td>
                      <td>
                        <div className="row wrap gap-sm">
                          <Link
                            className="ghost"
                            href={buildCalendarsPath({
                              locationFilter,
                              deploymentFilter,
                              statusFilter,
                              generatedFor,
                              previewGroup: previewGroupKey,
                              editGroup: group.key,
                              generatedGroup: generatedGroupKey,
                            })}
                          >
                            {t("admin.calendars.edit_block")}
                          </Link>
                          <Link
                            className="ghost"
                            href={buildCalendarsPath({
                              locationFilter,
                              deploymentFilter,
                              statusFilter,
                              generatedFor,
                              previewGroup: previewGroupKey,
                              editGroup: editGroupKey,
                              generatedGroup: group.key,
                            })}
                          >
                            {t("admin.calendars.view_all_slots")}
                          </Link>
                          <form action={previewAdminQuoteSchoolCalendarGroupDeploymentAction}>
                            {group.items.map((item) => (
                              <input key={`${group.key}-preview-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
                            ))}
                            <input type="hidden" name="return_to" value={returnPath} />
                            <button type="submit" className="ghost">{t("admin.calendars.preview")}</button>
                          </form>
                          <form action={deployAdminQuoteSchoolCalendarGroupAction}>
                            {group.items.map((item) => (
                              <input key={`${group.key}-deploy-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
                            ))}
                            <input type="hidden" name="return_to" value={returnPath} />
                            <button type="submit">{t("admin.calendars.deploy")}</button>
                          </form>
                          <form action={syncAdminQuoteSchoolCalendarGroupAction}>
                            {group.items.map((item) => (
                              <input key={`${group.key}-sync-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
                            ))}
                            <input type="hidden" name="return_to" value={returnPath} />
                            <button type="submit" className="ghost">{t("admin.calendars.resync")}</button>
                          </form>
                          <form action={removeAdminQuoteSchoolCalendarGroupDeploymentAction}>
                            {group.items.map((item) => (
                              <input key={`${group.key}-remove-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
                            ))}
                            <input type="hidden" name="return_to" value={returnPath} />
                            <button type="submit" className="danger">{t("admin.calendars.remove")}</button>
                          </form>
                          {group.is_fully_removed ? (
                            <>
                              <form id={`calendar-group-delete-${group.key}`} action={bulkAdminQuoteSchoolCalendarsAction}>
                                {group.items.map((item) => (
                                  <input key={`${group.key}-delete-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
                                ))}
                                <input type="hidden" name="bulk_action" value="DELETE" />
                                <input type="hidden" name="return_to" value={returnPath} />
                                <input type="hidden" name="success_return_to" value={basePath} />
                              </form>
                              <ConfirmSubmitButton
                                formId={`calendar-group-delete-${group.key}`}
                                label={t("common.delete")}
                                title={t("admin.calendars.delete_block_title")}
                                description={t("admin.calendars.delete_block_description", { name: group.name, count: group.items.length })}
                                confirmLabel={t("admin.calendars.delete_block_confirm")}
                                closeAriaLabel={t("common.close")}
                                className="danger"
                              />
                            </>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </section>

      <section className="card top-gap-sm">
        <div className="row spread wrap gap-sm">
          <div>
            <h4>{t("admin.calendars.fine_admin_title")}</h4>
            <p className="muted">{t("admin.calendars.fine_admin_subtitle")}</p>
          </div>
          <span className="status-pill status-info">{t("admin.calendars.visible_count", { count: filteredCalendars.length })}</span>
        </div>
        <form method="GET" className="grid cols-4 config-form-grid top-gap-sm">
          {generatedFor ? <input type="hidden" name="generated_for" value={generatedFor} /> : null}
          {previewGroupKey ? <input type="hidden" name="preview_group" value={previewGroupKey} /> : null}
          <label>
            {t("common.location")}
            <select name="location_filter" defaultValue={locationFilter || ""}>
              <option value="">{t("common.all")}</option>
              {locations.map((row) => (
                <option key={`calendar-filter-location-${row.id}`} value={row.id}>{row.name}</option>
              ))}
            </select>
          </label>
          <label>
            {t("admin.calendars.column_deployment")}
            <select name="deployment_filter" defaultValue={deploymentFilter || ""}>
              <option value="">{t("common.all")}</option>
              <option value="not_deployed">{t("admin.calendars.deployment_not_deployed")}</option>
              <option value="deployed">{t("admin.calendars.deployment_deployed")}</option>
              <option value="stale">{t("admin.calendars.deployment_stale")}</option>
              <option value="removed">{t("admin.calendars.deployment_removed")}</option>
            </select>
          </label>
          <label>
            {t("common.status")}
            <select name="status_filter" defaultValue={statusFilter || ""}>
              <option value="">{t("common.all")}</option>
              <option value="active">{t("common.active")}</option>
              <option value="inactive">{t("common.inactive")}</option>
            </select>
          </label>
          <div className="row wrap gap-sm" style={{ alignItems: "end" }}>
            <button type="submit" className="ghost">{t("admin.quotes.filter")}</button>
            <Link className="ghost" href={resetFiltersPath}>{t("common.reset")}</Link>
          </div>
        </form>
        <form id="calendar-bulk-form" action={bulkAdminQuoteSchoolCalendarsAction} className="grid cols-4 config-form-grid top-gap-sm">
          <input type="hidden" name="return_to" value={returnPath} />
          <input type="hidden" name="success_return_to" value={basePath} />
          <label className="span-2">
            {t("admin.calendars.bulk_action")}
            <select name="bulk_action" defaultValue="SYNC">
              <option value="DEPLOY">{t("admin.calendars.bulk_deploy_selected")}</option>
              <option value="SYNC">{t("admin.calendars.bulk_sync_selected")}</option>
              <option value="REMOVE">{t("admin.calendars.bulk_remove_selected")}</option>
              <option value="DELETE">{t("admin.calendars.bulk_delete_selected")}</option>
            </select>
          </label>
          <div className="span-2 row wrap gap-sm" style={{ alignItems: "end" }}>
            <ConditionalConfirmSubmitButton
              formId="calendar-bulk-form"
              label={t("common.apply")}
              confirmFieldName="bulk_action"
              confirmFieldValue="DELETE"
              title={t("admin.calendars.bulk_delete_title")}
              description={t("admin.calendars.bulk_delete_description")}
              confirmLabel={t("admin.calendars.bulk_delete_confirm")}
              cancelLabel={t("common.cancel")}
              closeAriaLabel={t("common.close")}
              missingFormError={t("admin.calendars.form_not_found")}
              language={language}
            />
            <span className="muted">{t("admin.calendars.bulk_hint")}</span>
          </div>
        </form>

        <div className="table-wrap top-gap-sm">
          <table className="data-table">
            <thead>
              <tr>
                <th>{t("admin.calendars.column_selection")}</th>
                <th>{t("common.name")}</th>
                <th>{t("admin.calendars.column_year")}</th>
                <th>{t("common.location")}</th>
                <th>{t("admin.calendars.column_vacations")}</th>
                <th>{t("admin.calendars.column_holidays")}</th>
                <th>{t("admin.calendars.column_closures")}</th>
                <th>{t("admin.calendars.column_deployment")}</th>
                <th>{t("admin.calendars.column_active_slots")}</th>
                <th>{t("common.status")}</th>
                <th>{t("common.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {filteredCalendars.length === 0 ? (
                <tr><td colSpan={11}><p className="muted">{t("admin.calendars.no_calendars_for_filters")}</p></td></tr>
              ) : (
                filteredCalendars.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <input
                        type="checkbox"
                        name="calendar_ids"
                        value={row.id}
                        form="calendar-bulk-form"
                        aria-label={t("admin.calendars.select_row_aria", {
                          name: row.name,
                          location: locationById.get(row.location_id) || row.location_id,
                        })}
                      />
                    </td>
                    <td><strong>{row.name}</strong></td>
                    <td>{row.school_year_label}</td>
                    <td>{locationById.get(row.location_id) || row.location_id}</td>
                    <td>{row.vacation_periods.length}</td>
                    <td>{row.holiday_dates.length}</td>
                    <td>{row.closure_dates.length}</td>
                    <td>
                      <span className={`status-pill ${deploymentStatusClass(row.deployment_status)}`}>
                        {deploymentStatusLabel(row.deployment_status, language)}
                      </span>
                    </td>
                    <td>{row.deployment_generated_active_count || 0}</td>
                    <td>
                      <span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>
                        {row.is_active ? t("common.active") : t("common.inactive")}
                      </span>
                    </td>
                    <td>
                      <details>
                        <summary className="mode-link">{t("admin.calendars.local_actions")}</summary>
                        <form action={updateAdminQuoteSchoolCalendarConfigAction} className="grid config-form-grid top-gap-sm">
                          <input type="hidden" name="calendar_id" value={row.id} />
                          <input type="hidden" name="return_to" value={returnPath} />
                          <label className="span-2">
                            {t("common.name")}
                            <input type="text" name="name" defaultValue={row.name} required maxLength={180} />
                          </label>
                          <label>
                            {t("admin.calendars.school_year")}
                            <input type="text" name="school_year_label" defaultValue={row.school_year_label} required maxLength={40} />
                          </label>
                          <fieldset className="span-4 calendar-locations-fieldset">
                            <legend>{t("admin.calendars.target_locations_title")}</legend>
                            <p className="muted">{t("admin.calendars.target_locations_help_local")}</p>
                            <div className="calendar-location-grid">
                              {locations.map((location) => (
                                <label key={`${row.id}-location-${location.id}`} className="checkline">
                                  <input
                                    type="checkbox"
                                    name="location_ids"
                                    value={location.id}
                                    defaultChecked={location.id === row.location_id}
                                  />
                                  {location.name}
                                </label>
                              ))}
                            </div>
                          </fieldset>
                          <div className="span-4 calendar-inline-help">
                            <strong>{t("admin.calendars.quick_entry_title")}</strong>
                            <p className="muted">
                              {t("admin.calendars.quick_entry_help")} <code>{t("admin.calendars.quick_entry_format")}</code>.{" "}
                              {t("admin.calendars.quick_entry_single_date")}
                            </p>
                          </div>
                          <label className="span-2 calendar-textarea-field">
                            {t("admin.calendars.vacation_periods")}
                            <textarea
                              name="vacation_periods_text"
                              rows={8}
                              defaultValue={calendarVacationPeriodsText(row.vacation_periods)}
                            />
                          </label>
                          <label className="calendar-textarea-field">
                            {t("admin.calendars.holidays")}
                            <textarea
                              name="holiday_dates_text"
                              rows={8}
                              defaultValue={calendarDatesText(row.holiday_dates)}
                            />
                          </label>
                          <label className="calendar-textarea-field">
                            {t("admin.calendars.closures")}
                            <textarea
                              name="closure_dates_text"
                              rows={8}
                              defaultValue={calendarDatesText(row.closure_dates)}
                            />
                          </label>
                          <label className="checkline">
                            <input type="checkbox" name="is_active" defaultChecked={row.is_active} />
                            {t("common.active")}
                          </label>
                          <label className="checkline span-3">
                            <input type="checkbox" name="apply_to_management_planning" />
                            {t("admin.calendars.apply_planning_create")}
                          </label>
                          <div className="row">
                            <button type="submit">{t("common.save")}</button>
                          </div>
                        </form>
                        <div className="row wrap top-gap-sm gap-sm">
                          <form action={previewAdminQuoteSchoolCalendarDeploymentAction}>
                            <input type="hidden" name="calendar_id" value={row.id} />
                            <input type="hidden" name="return_to" value={returnPath} />
                            <button type="submit" className="ghost">{t("admin.calendars.preview_deployment")}</button>
                          </form>
                          <form action={deployAdminQuoteSchoolCalendarAction}>
                            <input type="hidden" name="calendar_id" value={row.id} />
                            <input type="hidden" name="return_to" value={returnPath} />
                            <button type="submit">{t("admin.calendars.deploy")}</button>
                          </form>
                          <form action={syncAdminQuoteSchoolCalendarDeploymentAction}>
                            <input type="hidden" name="calendar_id" value={row.id} />
                            <input type="hidden" name="return_to" value={returnPath} />
                            <button type="submit" className="ghost">{t("admin.calendars.update_deployment")}</button>
                          </form>
                          <form action={removeAdminQuoteSchoolCalendarDeploymentAction}>
                            <input type="hidden" name="calendar_id" value={row.id} />
                            <input type="hidden" name="return_to" value={returnPath} />
                            <button type="submit" className="danger">{t("admin.calendars.remove_generated_slots")}</button>
                          </form>
                          <Link
                            className="ghost"
                            href={buildCalendarsPath({
                              locationFilter,
                              deploymentFilter,
                              statusFilter,
                              generatedFor: row.id,
                              previewGroup: previewGroupKey,
                            })}
                          >
                            {t("admin.calendars.view_generated_slots")}
                          </Link>
                        </div>
                        <form id={`calendar-delete-${row.id}`} action={deleteAdminQuoteSchoolCalendarConfigAction} className="row top-gap-sm">
                          <input type="hidden" name="calendar_id" value={row.id} />
                          <input type="hidden" name="return_to" value={returnPath} />
                          <ConfirmSubmitButton
                            formId={`calendar-delete-${row.id}`}
                            label={t("common.delete")}
                            title={t("admin.calendars.delete_local_title")}
                            description={t("admin.calendars.delete_local_description", {
                              name: row.name,
                              location: locationById.get(row.location_id) || row.location_id,
                            })}
                            confirmLabel={t("common.delete")}
                            closeAriaLabel={t("common.close")}
                            className="danger"
                          />
                        </form>
                      </details>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {createModalOpen ? (
        <section className="modal-overlay">
          <article className="modal-panel client-create-modal calendar-editor-modal">
            <Link className="modal-close-x" href={basePath} aria-label={t("common.close")}>
              ×
            </Link>
            <header className="calendar-editor-header">
              <div>
                <h3 className="modal-title">{t("admin.calendars.create_modal_title")}</h3>
                <p className="muted">{t("admin.calendars.create_modal_subtitle")}</p>
              </div>
            </header>
            {renderCalendarBlockForm({
              action: createAdminQuoteSchoolCalendarConfigAction,
              returnTo: createModalPath,
              successReturnTo: basePath,
              submitLabel: t("admin.calendars.create_modal_submit"),
              cancelHref: basePath,
              defaults: {
                name: "",
                schoolYearLabel: "",
                selectedLocationIds: [],
                vacationPeriodsText: "",
                holidayDatesText: "",
                closureDatesText: "",
                isActive: true,
              },
              applyPlanningLabel: t("admin.calendars.apply_planning_create"),
              errorText: modalErrorMessage,
              footerNote: t("admin.calendars.create_modal_footer"),
            })}
          </article>
        </section>
      ) : null}

      {editGroup ? (
        <section className="modal-overlay">
          <article className="modal-panel client-create-modal calendar-editor-modal">
            <Link className="modal-close-x" href={basePath} aria-label={t("common.close")}>
              ×
            </Link>
            <header className="calendar-editor-header">
              <div>
                <h3 className="modal-title">{t("admin.calendars.edit_modal_title")}</h3>
                <p className="muted">
                  {editGroup.name} · {editGroup.school_year_label} · {editGroup.location_names.join(", ")}
                </p>
              </div>
              <span className={`status-pill ${editGroup.badge_class}`}>{editGroup.badge_label}</span>
            </header>
            {renderCalendarBlockForm({
              action: updateAdminQuoteSchoolCalendarGroupAction,
              returnTo: buildCalendarsPath({
                locationFilter,
                deploymentFilter,
                statusFilter,
                generatedFor,
                previewGroup: previewGroupKey,
                editGroup: editGroup.key,
                generatedGroup: generatedGroupKey,
              }),
              successReturnTo: basePath,
              submitLabel: t("admin.calendars.edit_modal_submit"),
              cancelHref: basePath,
              defaults: {
                name: editGroup.representative.name,
                schoolYearLabel: editGroup.representative.school_year_label,
                selectedLocationIds: editGroup.items.map((item) => item.location_id),
                vacationPeriodsText: calendarVacationPeriodsText(editGroup.representative.vacation_periods),
                holidayDatesText: calendarDatesText(editGroup.representative.holiday_dates),
                closureDatesText: calendarDatesText(editGroup.representative.closure_dates),
                isActive: editGroup.representative.is_active,
              },
              applyPlanningLabel: t("admin.calendars.apply_planning_update"),
              existingEntries: editGroup.items.map((item) => ({ calendarId: item.id, locationId: item.location_id })),
              errorText: modalErrorMessage,
              footerNote: editGroup.is_fully_removed
                ? t("admin.calendars.edit_modal_footer_removed")
                : t("admin.calendars.edit_modal_footer_default"),
              extraActions: editGroup.is_fully_removed ? (
                <>
                  <form id={`calendar-group-delete-modal-${editGroup.key}`} action={bulkAdminQuoteSchoolCalendarsAction}>
                    {editGroup.items.map((item) => (
                      <input key={`calendar-group-delete-modal-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
                    ))}
                    <input type="hidden" name="bulk_action" value="DELETE" />
                    <input type="hidden" name="return_to" value={buildCalendarsPath({
                      locationFilter,
                      deploymentFilter,
                      statusFilter,
                      generatedFor,
                      previewGroup: previewGroupKey,
                      editGroup: editGroup.key,
                      generatedGroup: generatedGroupKey,
                    })} />
                    <input type="hidden" name="success_return_to" value={basePath} />
                  </form>
                  <ConfirmSubmitButton
                    formId={`calendar-group-delete-modal-${editGroup.key}`}
                    label={t("admin.calendars.delete_block_cta")}
                    title={t("admin.calendars.delete_block_title")}
                    description={t("admin.calendars.delete_block_description", { name: editGroup.name, count: editGroup.items.length })}
                    confirmLabel={t("admin.calendars.delete_block_confirm")}
                    closeAriaLabel={t("common.close")}
                    className="danger"
                  />
                </>
              ) : null,
            })}
          </article>
        </section>
      ) : null}

      {previewGroup ? (
        <section className="card">
          <div className="row spread wrap gap-sm">
            <h3>{t("admin.calendars.preview_section_title")}</h3>
            <Link
              className="ghost"
              href={buildCalendarsPath({
                locationFilter,
                deploymentFilter,
                statusFilter,
                generatedFor,
                editGroup: editGroupKey,
                generatedGroup: generatedGroupKey,
              })}
            >
              {t("common.close")}
            </Link>
          </div>
          <p className="muted">{t("admin.calendars.preview_section_subtitle", {
            name: previewGroup.name,
            school_year: previewGroup.school_year_label,
            count: previewGroup.items.length,
          })}</p>
          <div className="row wrap gap-sm top-gap-sm">
            <span className="status-pill status-info">{t("admin.calendars.target_dates_badge", { count: groupPreviewTotals.totalTargetDays })}</span>
            <span className="status-pill status-info">{t("admin.calendars.vacations_badge", { count: groupPreviewTotals.vacationDays })}</span>
            <span className="status-pill status-info">{t("admin.calendars.holidays_badge", { count: groupPreviewTotals.holidayDays })}</span>
            <span className="status-pill status-info">{t("admin.calendars.closures_badge", { count: groupPreviewTotals.closureDays })}</span>
            <span className="status-pill status-ok">{t("admin.calendars.create_badge", { count: groupPreviewTotals.wouldCreate })}</span>
            <span className="status-pill status-ok">{t("admin.calendars.reactivate_badge", { count: groupPreviewTotals.wouldReactivate })}</span>
            <span className="status-pill status-warn">{t("admin.calendars.remove_badge", { count: groupPreviewTotals.wouldCancel })}</span>
            <span className="status-pill status-info">{t("admin.calendars.existing_active_badge", { count: groupPreviewTotals.existingGenerated })}</span>
          </div>

          <div className="table-wrap top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t("common.location")}</th>
                  <th>{t("admin.calendars.target_dates")}</th>
                  <th>{t("admin.calendars.column_vacations")}</th>
                  <th>{t("admin.calendars.column_holidays")}</th>
                  <th>{t("admin.calendars.column_closures")}</th>
                  <th>{t("admin.calendars.to_create")}</th>
                  <th>{t("admin.calendars.to_reactivate")}</th>
                  <th>{t("admin.calendars.to_remove")}</th>
                  <th>{t("admin.calendars.existing_active")}</th>
                </tr>
              </thead>
              <tbody>
                {groupPreviewRows.length === 0 ? (
                  <tr><td colSpan={9}><p className="muted">{t("admin.calendars.no_preview_data")}</p></td></tr>
                ) : (
                  groupPreviewRows.map(({ calendar, preview }) => (
                    <tr key={`preview-${calendar.id}`}>
                      <td>{locationById.get(calendar.location_id) || calendar.location_id}</td>
                      <td>{Number(preview.summary?.total_target_days ?? 0)}</td>
                      <td>{Number(preview.summary?.vacation_days ?? 0)}</td>
                      <td>{Number(preview.summary?.holiday_days ?? 0)}</td>
                      <td>{Number(preview.summary?.closure_days ?? 0)}</td>
                      <td>{Number(preview.would_create ?? 0)}</td>
                      <td>{Number(preview.would_reactivate ?? 0)}</td>
                      <td>{Number(preview.would_cancel ?? 0)}</td>
                      <td>{Number(preview.existing_generated_active_count ?? 0)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="row wrap gap-sm top-gap-sm">
            <form action={deployAdminQuoteSchoolCalendarGroupAction}>
              {previewGroup.items.map((item) => (
                <input key={`preview-deploy-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
              ))}
              <input type="hidden" name="return_to" value={returnPath} />
              <button type="submit">{t("admin.calendars.confirm_and_deploy")}</button>
            </form>
            <form action={syncAdminQuoteSchoolCalendarGroupAction}>
              {previewGroup.items.map((item) => (
                <input key={`preview-sync-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
              ))}
              <input type="hidden" name="return_to" value={returnPath} />
              <button type="submit" className="ghost">{t("admin.calendars.resync_group")}</button>
            </form>
            <form action={removeAdminQuoteSchoolCalendarGroupDeploymentAction}>
              {previewGroup.items.map((item) => (
                <input key={`preview-remove-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
              ))}
              <input type="hidden" name="return_to" value={returnPath} />
              <button type="submit" className="danger">{t("admin.calendars.remove_group_slots")}</button>
            </form>
          </div>
        </section>
      ) : null}

      {generatedGroup ? (
        <section className="card">
          <div className="row spread wrap gap-sm">
            <div>
              <h3>{t("admin.calendars.group_slots_title")}</h3>
              <p className="muted">{t("admin.calendars.group_slots_subtitle", {
                name: generatedGroup.name,
                school_year: generatedGroup.school_year_label,
                locations: generatedGroup.location_names.join(", "),
              })}</p>
            </div>
            <Link
              className="ghost"
              href={buildCalendarsPath({
                locationFilter,
                deploymentFilter,
                statusFilter,
                generatedFor,
                previewGroup: previewGroupKey,
                editGroup: editGroupKey,
              })}
            >
              {t("common.close")}
            </Link>
          </div>
          {generatedGroupSlots.length === 0 ? (
            <p className="muted">{t("admin.calendars.no_group_slots")}</p>
          ) : (
            <div className="table-wrap top-gap-sm">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t("common.location")}</th>
                    <th>{t("common.date")}</th>
                    <th>{t("admin.calendars.column_reasons")}</th>
                    <th>{t("common.status")}</th>
                    <th>{t("admin.calendars.column_session")}</th>
                  </tr>
                </thead>
                <tbody>
                  {generatedGroupSlots.map((slot) => (
                    <tr key={`${slot.session_id}-${slot.location_name}`}>
                      <td>{slot.location_name}</td>
                      <td>{slot.date}</td>
                      <td>{deploymentReasonListLabel(slot.reason_types, language)}</td>
                      <td>{slot.status}</td>
                      <td>{slot.title}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}

      {selectedCalendar ? (
        <section className="card">
          <div className="row spread wrap gap-sm">
            <h3>{t("admin.calendars.generated_slots_title")}</h3>
            <Link
              className="ghost"
              href={buildCalendarsPath({
                locationFilter,
                deploymentFilter,
                statusFilter,
                previewGroup: previewGroupKey,
                editGroup: editGroupKey,
                generatedGroup: generatedGroupKey,
              })}
            >
              {t("common.close")}
            </Link>
          </div>
          <p className="muted">{t("admin.calendars.generated_slots_subtitle", {
            name: selectedCalendar.name,
            location: locationById.get(selectedCalendar.location_id) || selectedCalendar.location_id,
          })}</p>
          {generatedSlots.length === 0 ? (
            <p className="muted">{t("admin.calendars.no_generated_slots")}</p>
          ) : (
            <div className="table-wrap top-gap-sm">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t("common.date")}</th>
                    <th>{t("admin.calendars.column_reasons")}</th>
                    <th>{t("common.status")}</th>
                    <th>{t("admin.calendars.column_session")}</th>
                  </tr>
                </thead>
                <tbody>
                  {generatedSlots.map((slot) => (
                    <tr key={slot.session_id}>
                      <td>{slot.date}</td>
                      <td>{deploymentReasonListLabel(slot.reason_types, language)}</td>
                      <td>{slot.status}</td>
                      <td>{slot.title}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}
    </section>
  );
}
