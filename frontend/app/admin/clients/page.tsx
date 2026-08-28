import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import AdultLinkSelector from "../../../components/adult-link-selector";
import ClientKindCreateSync from "../../../components/client-kind-create-sync";
import ClientBulkControls from "../../../components/client-bulk-controls";
import {
  bulkAdminClientsAction,
  createAdminClientAction,
  createAdminClientGroupAction,
  importMyMusicStaffFamiliesAction,
} from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import { hasAdminPermission } from "../../../lib/admin-access";
import {
  COUNTRY_OPTIONS,
  CURRENCY_OPTIONS,
  DEFAULT_COUNTRY,
  DEFAULT_CURRENCY,
  DEFAULT_TIMEZONE,
  TIMEZONE_OPTIONS,
} from "../../../lib/reference-data";
import type { AdminClientGroupOut, AdminClientOut, AdminClientStatsOut, AdminMessagingTemplateOut, UserOut } from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;
type SortColumn = "last_name" | "first_name" | "family_name" | "client_status" | "client_kind" | "student_site" | "next_session";
type SortDirection = "asc" | "desc";
type ClientsView = "students" | "groups";
type PerPage = 5 | 50;
type MyMusicStaffImportStatus = {
  group_found: boolean;
  group_name: string;
  members_count: number;
  parents_count: number;
  children_count: number;
  imported_note_count: number;
  family_links_count: number;
  inactive_children_count: number;
  responsible_parents_count: number;
};

const CLIENT_STATUS_OPTIONS = ["ACTIVE", "RESPONSABLE", "TRIAL", "PENDING", "INACTIVE", "ARCHIVED"] as const;
const STUDENT_SITE_OPTIONS = ["PARIS", "BAR_LE_DUC", "ONLINE"] as const;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatDate(value: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString(localeForUiLanguage(language), {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatDateOnly(value: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleDateString(localeForUiLanguage(language), { dateStyle: "short" });
}

function compactNameList(names: string[], max = 2): string {
  const cleanNames = names.map((name) => name.trim()).filter(Boolean);
  if (cleanNames.length <= max) {
    return cleanNames.join(", ");
  }
  return `${cleanNames.slice(0, max).join(", ")} +${cleanNames.length - max}`;
}

function parseSortColumn(value: string): SortColumn {
  if (
    value === "last_name" ||
    value === "first_name" ||
    value === "family_name" ||
    value === "client_status" ||
    value === "client_kind" ||
    value === "student_site" ||
    value === "next_session"
  ) {
    return value;
  }
  return "last_name";
}

function parseSortDirection(value: string): SortDirection {
  if (value === "desc") {
    return "desc";
  }
  return "asc";
}

function parseView(value: string): ClientsView {
  if (value === "groups") {
    return "groups";
  }
  return "students";
}

function parsePerPage(value: string): PerPage {
  if (value === "5") {
    return 5;
  }
  return 50;
}

function parsePage(value: string): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return 1;
  }
  return parsed;
}

function statusLabel(status: string, language: UiLanguage): string {
  const normalized = status.toUpperCase();
  if (normalized === "ACTIVE") return uiText(language, "admin.clients.status_active");
  if (normalized === "RESPONSABLE") return uiText(language, "admin.clients.status_responsable");
  if (normalized === "TRIAL") return uiText(language, "admin.clients.status_trial");
  if (normalized === "PENDING") return uiText(language, "admin.clients.status_pending");
  if (normalized === "INACTIVE") return uiText(language, "admin.clients.status_inactive");
  if (normalized === "ARCHIVED") return uiText(language, "admin.clients.status_archived");
  return normalized;
}

function statusPillClass(status: string): string {
  const normalized = status.toUpperCase();
  if (normalized === "ACTIVE") {
    return "status-ok";
  }
  if (normalized === "RESPONSABLE") {
    return "status-info";
  }
  if (normalized === "TRIAL" || normalized === "PENDING") {
    return "status-warn";
  }
  return "status-off";
}

function clientTypeLabel(kind: string, language: UiLanguage): string {
  return kind === "CHILD" ? uiText(language, "client.child") : uiText(language, "client.adult");
}

function studentSiteLabel(site: string | null | undefined): string {
  if (site === "PARIS") return "Paris";
  if (site === "BAR_LE_DUC") return "Bar-le-Duc";
  if (site === "ONLINE") return "En ligne";
  return "-";
}

function buildClientsHref(params: {
  search: string;
  status: string;
  site: string;
  groupId: string;
  sortBy: SortColumn;
  sortDir: SortDirection;
  view: ClientsView;
  page: number;
  perPage: PerPage;
}): string {
  const query = new URLSearchParams();
  if (params.search) {
    query.set("search", params.search);
  }
  if (params.status && params.status !== "ALL") {
    query.set("status", params.status);
  }
  if (params.site && params.site !== "ALL") {
    query.set("site", params.site);
  }
  if (params.groupId) {
    query.set("group_id", params.groupId);
  }
  if (params.sortBy !== "last_name") {
    query.set("sort_by", params.sortBy);
  }
  if (params.sortDir !== "asc") {
    query.set("sort_dir", params.sortDir);
  }
  if (params.view === "groups") {
    query.set("view", "groups");
  }
  if (params.page > 1) {
    query.set("page", String(params.page));
  }
  if (params.perPage !== 50) {
    query.set("per_page", String(params.perPage));
  }

  const qs = query.toString();
  return qs ? `/admin/clients?${qs}` : "/admin/clients";
}

function closeModalHref(params: {
  search: string;
  status: string;
  site: string;
  groupId: string;
  sortBy: SortColumn;
  sortDir: SortDirection;
  view: ClientsView;
  page: number;
  perPage: PerPage;
}): string {
  return buildClientsHref(params);
}

function sortHref(params: {
  currentSortBy: SortColumn;
  currentSortDir: SortDirection;
  targetSortBy: SortColumn;
  search: string;
  status: string;
  site: string;
  groupId: string;
  view: ClientsView;
  page: number;
  perPage: PerPage;
}): string {
  const nextDir: SortDirection =
    params.currentSortBy === params.targetSortBy && params.currentSortDir === "asc" ? "desc" : "asc";

  return buildClientsHref({
    search: params.search,
    status: params.status,
    site: params.site,
    groupId: params.groupId,
    sortBy: params.targetSortBy,
    sortDir: nextDir,
    view: params.view,
    page: 1,
    perPage: params.perPage,
  });
}

function sortIndicator(currentSortBy: SortColumn, currentSortDir: SortDirection, targetSortBy: SortColumn): string {
  if (currentSortBy !== targetSortBy) {
    return "↕";
  }
  return currentSortDir === "asc" ? "↑" : "↓";
}

export default async function AdminClientsPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || !hasAdminPermission(meResult.data, "can_view_clients")) {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const search = readParam(searchParams, "search").trim();
  const selectedStatus = readParam(searchParams, "status") || "ALL";
  const selectedSite = readParam(searchParams, "site") || "ALL";
  const selectedGroupId = readParam(searchParams, "group_id");
  const sortBy = parseSortColumn(readParam(searchParams, "sort_by"));
  const sortDir = parseSortDirection(readParam(searchParams, "sort_dir"));
  const view = parseView(readParam(searchParams, "view"));
  const perPage = parsePerPage(readParam(searchParams, "per_page"));
  const requestedPage = parsePage(readParam(searchParams, "page"));
  const openCreateModal = readParam(searchParams, "new_client") === "1";

  const includeArchived = selectedStatus === "ARCHIVED";
  const clientsQuery = new URLSearchParams();
  clientsQuery.set("limit", String(perPage));
  clientsQuery.set("offset", String((requestedPage - 1) * perPage));
  clientsQuery.set("paginate", "true");
  clientsQuery.set("sort_by", sortBy);
  clientsQuery.set("sort_dir", sortDir);
  clientsQuery.set("include_archived", includeArchived ? "true" : "false");
  if (search) {
    clientsQuery.set("search", search);
  }
  if (selectedStatus !== "ALL") {
    clientsQuery.set("client_status", selectedStatus);
  }
  if (selectedSite !== "ALL") {
    clientsQuery.set("student_site", selectedSite);
  }
  if (selectedGroupId) {
    clientsQuery.set("group_id", selectedGroupId);
  }

  const statsQuery = new URLSearchParams(clientsQuery);
  statsQuery.delete("limit");
  statsQuery.delete("offset");
  statsQuery.delete("paginate");
  statsQuery.delete("sort_by");
  statsQuery.delete("sort_dir");

  const [clientsResult, statsResult, groupsResult, mmsImportStatusResult, emailTemplatesResult] = await Promise.all([
    view === "students"
      ? backendRequest<AdminClientOut[]>(`/api/v1/admin/clients?${clientsQuery.toString()}`, {}, token)
      : Promise.resolve({ ok: true as const, status: 200, data: [] as AdminClientOut[] }),
    view === "students"
      ? backendRequest<AdminClientStatsOut>(`/api/v1/admin/clients/stats?${statsQuery.toString()}`, {}, token)
      : Promise.resolve({ ok: true as const, status: 200, data: { total: 0, by_status: {} } as AdminClientStatsOut }),
    backendRequest<AdminClientGroupOut[]>("/api/v1/admin/clients/groups?include_inactive=true", {}, token),
    view === "groups"
      ? backendRequest<MyMusicStaffImportStatus>("/api/v1/admin/clients/imports/my-music-staff-2025-2026/status", {}, token)
      : Promise.resolve({ ok: true as const, status: 200, data: null as MyMusicStaffImportStatus | null }),
    view === "students"
      ? backendRequest<AdminMessagingTemplateOut[]>(
          "/api/v1/admin/config/messaging-templates?channel=EMAIL&kind=CUSTOM&active_only=true",
          {},
          token,
        )
      : Promise.resolve({ ok: true as const, status: 200, data: [] as AdminMessagingTemplateOut[] }),
  ]);

  const listedClientsRaw = clientsResult.ok ? clientsResult.data : [];
  const groups = groupsResult.ok ? groupsResult.data : [];
  const emailTemplates = emailTemplatesResult.ok ? emailTemplatesResult.data : [];
  const mmsImportStatus = mmsImportStatusResult.ok ? mmsImportStatusResult.data : null;
  const counts = {
    ACTIVE: statsResult.ok ? statsResult.data.by_status.ACTIVE ?? 0 : 0,
    RESPONSABLE: statsResult.ok ? statsResult.data.by_status.RESPONSABLE ?? 0 : 0,
    TRIAL: statsResult.ok ? statsResult.data.by_status.TRIAL ?? 0 : 0,
    PENDING: statsResult.ok ? statsResult.data.by_status.PENDING ?? 0 : 0,
    INACTIVE: statsResult.ok ? statsResult.data.by_status.INACTIVE ?? 0 : 0,
    ARCHIVED: statsResult.ok ? statsResult.data.by_status.ARCHIVED ?? 0 : 0,
  };

  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error");

  const totalFiltered = statsResult.ok ? statsResult.data.total : listedClientsRaw.length;
  const totalPages = Math.max(1, Math.ceil(totalFiltered / perPage));
  const currentPage = Math.min(requestedPage, totalPages);
  const pageStart = (currentPage - 1) * perPage;
  if (requestedPage !== currentPage) {
    redirect(buildClientsHref({
      search,
      status: selectedStatus,
      site: selectedSite,
      groupId: selectedGroupId,
      sortBy,
      sortDir,
      view,
      page: currentPage,
      perPage,
    }));
  }
  const listedClients = listedClientsRaw;

  const baseHref = buildClientsHref({
    search,
    status: selectedStatus,
    site: selectedSite,
    groupId: selectedGroupId,
    sortBy,
    sortDir,
    view,
    page: currentPage,
    perPage,
  });
  const closeHref = closeModalHref({
    search,
    status: selectedStatus,
    site: selectedSite,
    groupId: selectedGroupId,
    sortBy,
    sortDir,
    view,
    page: currentPage,
    perPage,
  });

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread">
          <h2>{t("admin.clients.page_title")}</h2>
          <Link className="mode-link" href={`${closeHref}${closeHref.includes("?") ? "&" : "?"}new_client=1`}>
            {t("admin.clients.add_new")}
          </Link>
        </div>
        <p className="muted">{t("admin.clients.subtitle")}</p>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {!clientsResult.ok ? <section className="flash-err">{t("admin.clients.backend_clients_error")}: {clientsResult.message}</section> : null}
      {!groupsResult.ok ? <section className="flash-err">{t("admin.clients.backend_groups_error")}: {groupsResult.message}</section> : null}

      <section className="card">
        <nav
          className="row client-subtabs"
          aria-label={language === "en" ? "Client sections" : "Rubriques clients"}
        >
          <Link
            className={`mode-link ${view === "students" ? "mode-active" : ""}`}
            href={buildClientsHref({
              search,
              status: selectedStatus,
              site: selectedSite,
              groupId: selectedGroupId,
              sortBy,
              sortDir,
              view: "students",
              page: 1,
              perPage,
            })}
          >
            {t("admin.clients.tab_students")}
          </Link>
          <Link
            className={`mode-link ${view === "groups" ? "mode-active" : ""}`}
            href={buildClientsHref({
              search,
              status: selectedStatus,
              site: selectedSite,
              groupId: selectedGroupId,
              sortBy,
              sortDir,
              view: "groups",
              page: 1,
              perPage,
            })}
          >
            {t("admin.clients.tab_groups")}
          </Link>
        </nav>
      </section>

      {view === "students" ? (
        <>
          <section className="card">
            <div className="row client-status-counts">
              <span>
                <strong>{counts.ACTIVE}</strong> {statusLabel("ACTIVE", language)}
              </span>
              <span>
                <strong>{counts.RESPONSABLE}</strong> {statusLabel("RESPONSABLE", language)}
              </span>
              <span>
                <strong>{counts.TRIAL}</strong> {statusLabel("TRIAL", language)}
              </span>
              <span>
                <strong>{counts.PENDING}</strong> {statusLabel("PENDING", language)}
              </span>
              <span>
                <strong>{counts.INACTIVE}</strong> {statusLabel("INACTIVE", language)}
              </span>
              <span>
                <strong>{counts.ARCHIVED}</strong> {statusLabel("ARCHIVED", language)}
              </span>
            </div>
          </section>

          <section className="card">
            <h2>{t("admin.clients.filters_title")}</h2>
            <form method="get" className="admin-list-filter-form">
              <input type="hidden" name="view" value="students" />
              <input type="hidden" name="sort_by" value={sortBy} />
              <input type="hidden" name="sort_dir" value={sortDir} />
              <input type="hidden" name="page" value="1" />

              <div className="admin-list-filter-primary">
                <label>
                  {t("admin.clients.search_label")}
                  <input type="search" name="search" defaultValue={search} placeholder={t("admin.clients.search_placeholder")} enterKeyHint="search" />
                </label>

                <label>
                  {t("admin.clients.client_status_label")}
                  <select name="status" defaultValue={selectedStatus}>
                    <option value="ALL">{t("admin.clients.all_excluding_archived")}</option>
                    {CLIENT_STATUS_OPTIONS.map((statusValue) => (
                      <option key={statusValue} value={statusValue}>
                        {statusLabel(statusValue, language)}
                      </option>
                    ))}
                  </select>
                </label>

                <div className="admin-list-filter-actions">
                  <button type="submit">{uiText(language, "common.apply")}</button>
                  <a className="reset-link" href="/admin/clients">{uiText(language, "common.reset")}</a>
                </div>
              </div>

              <details className="admin-filter-disclosure">
                <summary>{language === "en" ? "Advanced filters" : "Filtres avances"}</summary>
                <div className="admin-filter-disclosure-content">
                  <label>
                    Site
                    <select name="site" defaultValue={selectedSite}>
                      <option value="ALL">{uiText(language, "common.all")}</option>
                      {STUDENT_SITE_OPTIONS.map((siteValue) => (
                        <option key={siteValue} value={siteValue}>{studentSiteLabel(siteValue)}</option>
                      ))}
                    </select>
                  </label>

                  <label>
                    {t("admin.clients.group_label")}
                    <select name="group_id" defaultValue={selectedGroupId}>
                      <option value="">{uiText(language, "common.all")}</option>
                      {groups.filter((group) => group.active).map((group) => (
                        <option key={group.id} value={group.id}>{group.name}</option>
                      ))}
                    </select>
                  </label>

                  <label>
                    {t("admin.clients.clients_per_page")}
                    <select name="per_page" defaultValue={String(perPage)}>
                      <option value="5">5</option>
                      <option value="50">50</option>
                    </select>
                  </label>
                </div>
              </details>
            </form>
          </section>

          <form id="clients-bulk-form" action={bulkAdminClientsAction} className="admin-page-grid">
            <input type="hidden" name="return_to" value={baseHref} />
            <input type="hidden" name="filter_search" value={search} />
            <input type="hidden" name="filter_status" value={selectedStatus !== "ALL" ? selectedStatus : ""} />
            <input type="hidden" name="filter_student_site" value={selectedSite !== "ALL" ? selectedSite : ""} />
            <input type="hidden" name="filter_group_id" value={selectedGroupId} />
            <input type="hidden" name="filter_include_archived" value={includeArchived ? "true" : "false"} />
            <input type="hidden" name="filter_active_only" value="false" />
            <section className="card">
              <ClientBulkControls
                groups={groups.filter((group) => group.active).map((group) => ({ id: group.id, name: group.name }))}
                emailTemplates={emailTemplates.map((template) => ({
                  id: template.id,
                  name: template.name,
                  subject: template.subject ?? "",
                  body: template.body,
                  bodyFormat: template.body_format,
                }))}
                pageCount={listedClients.length}
                filteredCount={listedClientsRaw.length}
                language={language}
              />
            </section>

            <section className="card table-wrap admin-table-card-wrap">
              <table className="data-table clients-table admin-responsive-table">
                <thead>
                  <tr>
                    <th style={{ width: "52px" }}>
                      <input type="checkbox" aria-label={t("admin.clients.select_page_aria")} data-role="select-page-toggle" />
                    </th>
                    <th>
                      <Link
                        className="sort-link"
                        href={sortHref({
                          currentSortBy: sortBy,
                          currentSortDir: sortDir,
                          targetSortBy: "last_name",
                          search,
                          status: selectedStatus,
                          site: selectedSite,
                          groupId: selectedGroupId,
                          view,
                          page: currentPage,
                          perPage,
                        })}
                      >
                        {t("admin.clients.sort_last_name")} {sortIndicator(sortBy, sortDir, "last_name")}
                      </Link>
                    </th>
                    <th>
                      <Link
                        className="sort-link"
                        href={sortHref({
                          currentSortBy: sortBy,
                          currentSortDir: sortDir,
                          targetSortBy: "first_name",
                          search,
                          status: selectedStatus,
                          site: selectedSite,
                          groupId: selectedGroupId,
                          view,
                          page: currentPage,
                          perPage,
                        })}
                      >
                        {t("admin.clients.sort_first_name")} {sortIndicator(sortBy, sortDir, "first_name")}
                      </Link>
                    </th>
                    <th>
                      <Link
                        className="sort-link"
                        href={sortHref({
                          currentSortBy: sortBy,
                          currentSortDir: sortDir,
                          targetSortBy: "family_name",
                          search,
                          status: selectedStatus,
                          site: selectedSite,
                          groupId: selectedGroupId,
                          view,
                          page: currentPage,
                          perPage,
                        })}
                      >
                        {t("admin.clients.sort_family_name")} {sortIndicator(sortBy, sortDir, "family_name")}
                      </Link>
                    </th>
                    <th>
                      <Link
                        className="sort-link"
                        href={sortHref({
                          currentSortBy: sortBy,
                          currentSortDir: sortDir,
                          targetSortBy: "client_status",
                          search,
                          status: selectedStatus,
                          site: selectedSite,
                          groupId: selectedGroupId,
                          view,
                          page: currentPage,
                          perPage,
                        })}
                      >
                        {uiText(language, "common.status")} {sortIndicator(sortBy, sortDir, "client_status")}
                      </Link>
                    </th>
                    <th>
                      <Link
                        className="sort-link"
                        href={sortHref({
                          currentSortBy: sortBy,
                          currentSortDir: sortDir,
                          targetSortBy: "client_kind",
                          search,
                          status: selectedStatus,
                          site: selectedSite,
                          groupId: selectedGroupId,
                          view,
                          page: currentPage,
                          perPage,
                        })}
                      >
                        {uiText(language, "common.type")} {sortIndicator(sortBy, sortDir, "client_kind")}
                      </Link>
                    </th>
                    <th>
                      <Link
                        className="sort-link"
                        href={sortHref({
                          currentSortBy: sortBy,
                          currentSortDir: sortDir,
                          targetSortBy: "student_site",
                          search,
                          status: selectedStatus,
                          site: selectedSite,
                          groupId: selectedGroupId,
                          view,
                          page: currentPage,
                          perPage,
                        })}
                      >
                        Site {sortIndicator(sortBy, sortDir, "student_site")}
                      </Link>
                    </th>
                    <th>
                      <Link
                        className="sort-link"
                        href={sortHref({
                          currentSortBy: sortBy,
                          currentSortDir: sortDir,
                          targetSortBy: "next_session",
                          search,
                          status: selectedStatus,
                          site: selectedSite,
                          groupId: selectedGroupId,
                          view,
                          page: currentPage,
                          perPage,
                        })}
                      >
                        {t("admin.clients.sort_next_session")} {sortIndicator(sortBy, sortDir, "next_session")}
                      </Link>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {listedClients.map((client) => (
                    <tr key={client.id}>
                      <td data-mobile-label="">
                        <input type="checkbox" name="client_ids" value={client.id} aria-label={`${t("admin.clients.select_page_aria")} ${client.email}`} />
                      </td>
                      <td data-mobile-label="" className="mobile-row-primary">
                        <Link className="client-name-link" href={`/admin/clients/${client.id}`}>
                          {client.last_name || "-"}
                        </Link>
                        <small className="muted row-inline">{client.email}</small>
                      </td>
                      <td data-mobile-label={t("admin.clients.sort_first_name")}>
                        <span>{client.first_name || "-"}</span>
                        {client.phone ? <small className="muted row-inline">{client.phone}</small> : null}
                      </td>
                      <td data-mobile-label={t("admin.clients.sort_family_name")}>
                        <span>{client.family_name || "-"}</span>
                        {client.linked_children_count > 0 ? (
                          <small className="muted row-inline">
                            {client.linked_children_count} enfant{client.linked_children_count > 1 ? "s" : ""}:{" "}
                            {compactNameList(client.linked_children_names)}
                          </small>
                        ) : null}
                        {client.linked_adults_count > 0 ? (
                          <small className="muted row-inline">
                            Responsable{client.linked_adults_count > 1 ? "s" : ""}: {compactNameList(client.linked_adult_names)}
                          </small>
                        ) : null}
                        {client.group_names.length > 0 ? <small className="muted row-inline">{client.group_names.join(" | ")}</small> : null}
                      </td>
                      <td data-mobile-label={uiText(language, "common.status")}>
                        <span className={`status-pill ${statusPillClass(client.client_status)}`}>{statusLabel(client.client_status, language)}</span>
                        <small className="muted row-inline">Cree {formatDateOnly(client.created_at, language)}</small>
                        <small className="muted row-inline">Maj {formatDateOnly(client.updated_at, language)}</small>
                      </td>
                      <td data-mobile-label={uiText(language, "common.type")}>{clientTypeLabel(client.client_kind, language)}</td>
                      <td data-mobile-label="Site">{studentSiteLabel(client.student_site)}</td>
                      <td data-mobile-label={t("admin.clients.sort_next_session")}>{client.next_session_start_at_utc ? formatDate(client.next_session_start_at_utc, language) : "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {clientsResult.ok && totalFiltered > 0 ? (
                <div className="row spread clients-pagination">
                  <small className="muted">
                    {t("admin.clients.pagination_summary", {
                      start: pageStart + 1,
                      end: Math.min(pageStart + listedClients.length, totalFiltered),
                      total: totalFiltered,
                    })}
                  </small>
                  <div className="row">
                    {currentPage > 1 ? (
                      <Link
                        className="mode-link"
                        href={buildClientsHref({
                          search,
                          status: selectedStatus,
                          site: selectedSite,
                          groupId: selectedGroupId,
                          sortBy,
                          sortDir,
                          view,
                          page: currentPage - 1,
                          perPage,
                        })}
                      >
                        ← {uiText(language, "common.previous")}
                      </Link>
                    ) : (
                      <span className="mode-link disabled-link">← {uiText(language, "common.previous")}</span>
                    )}
                    <span className="badge">
                      {uiText(language, "common.page")} {currentPage}/{totalPages}
                    </span>
                    {currentPage < totalPages ? (
                      <Link
                        className="mode-link"
                        href={buildClientsHref({
                          search,
                          status: selectedStatus,
                          site: selectedSite,
                          groupId: selectedGroupId,
                          sortBy,
                          sortDir,
                          view,
                          page: currentPage + 1,
                          perPage,
                        })}
                      >
                        {uiText(language, "common.next")} →
                      </Link>
                    ) : (
                      <span className="mode-link disabled-link">{uiText(language, "common.next")} →</span>
                    )}
                  </div>
                </div>
              ) : null}

              {clientsResult.ok && listedClients.length === 0 ? <p className="muted">{t("admin.clients.no_clients_for_filters")}</p> : null}
            </section>
          </form>
        </>
      ) : (
        <>
          <section className="card">
            <h2>{t("admin.clients.mms_import_title")}</h2>
            <p className="muted">{t("admin.clients.mms_import_subtitle")}</p>
            <form action={importMyMusicStaffFamiliesAction} className="grid cols-4">
              <input type="hidden" name="return_to" value="/admin/clients?view=groups" />
              <label className="span-2">
                {t("admin.clients.mms_import_file")}
                <input name="mms_file" type="file" accept=".csv,text/csv" required />
              </label>
              <label className="checkline">
                <input type="checkbox" name="dry_run" defaultChecked />
                {t("admin.clients.mms_import_dry_run")}
              </label>
              <div className="row">
                <button type="submit">{t("admin.clients.mms_import_submit")}</button>
              </div>
            </form>
            <small className="muted">{t("admin.clients.mms_import_note")}</small>
            {mmsImportStatus ? (
              <div className="quote-saved-card-metrics top-gap-sm">
                <div>
                  <span>{t("admin.clients.mms_status_members")}</span>
                  <strong>{mmsImportStatus.members_count}</strong>
                </div>
                <div>
                  <span>{t("admin.clients.mms_status_parents")}</span>
                  <strong>{mmsImportStatus.parents_count}</strong>
                </div>
                <div>
                  <span>{t("admin.clients.mms_status_children")}</span>
                  <strong>{mmsImportStatus.children_count}</strong>
                </div>
                <div>
                  <span>{t("admin.clients.mms_status_links")}</span>
                  <strong>{mmsImportStatus.family_links_count}</strong>
                </div>
              </div>
            ) : null}
            {mmsImportStatus ? (
              <small className="muted">
                {mmsImportStatus.group_found
                  ? t("admin.clients.mms_status_detail", {
                      inactiveChildren: mmsImportStatus.inactive_children_count,
                      responsibleParents: mmsImportStatus.responsible_parents_count,
                      noted: mmsImportStatus.imported_note_count,
                    })
                  : t("admin.clients.mms_status_missing")}
              </small>
            ) : null}
          </section>

          <section className="card">
            <h2>{t("admin.clients.new_group_title")}</h2>
            <form action={createAdminClientGroupAction} className="grid cols-4">
              <input type="hidden" name="return_to" value="/admin/clients?view=groups" />
              <label>
                {t("admin.clients.group_name")}
                <input name="name" type="text" maxLength={120} required placeholder={t("admin.clients.group_name_placeholder")} />
              </label>
              <label>
                {t("admin.clients.code_optional")}
                <input name="code" type="text" maxLength={80} placeholder={t("admin.clients.group_code_placeholder")} />
              </label>
              <label className="checkline">
                <input type="checkbox" name="active" defaultChecked />
                {t("admin.clients.group_active")}
              </label>
              <div className="row">
                <button type="submit">{t("admin.clients.create_group")}</button>
              </div>
            </form>
          </section>

          <section className="card table-wrap admin-table-card-wrap">
            <h2>{t("admin.clients.existing_groups")}</h2>
            <table className="data-table admin-responsive-table">
              <thead>
                <tr>
                  <th>{t("admin.clients.group_name")}</th>
                  <th>{t("admin.clients.code_optional")}</th>
                  <th>{uiText(language, "common.status")}</th>
                  <th>{t("admin.clients.members_count")}</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((group) => (
                  <tr key={group.id}>
                    <td className="mobile-row-primary" data-mobile-label={t("admin.clients.group_name")}>{group.name}</td>
                    <td data-mobile-label={t("admin.clients.code_optional")}>{group.code || "-"}</td>
                    <td data-mobile-label={uiText(language, "common.status")}>
                      <span className={`status-pill ${group.active ? "status-ok" : "status-off"}`}>{group.active ? statusLabel("ACTIVE", language) : statusLabel("INACTIVE", language)}</span>
                    </td>
                    <td data-mobile-label={t("admin.clients.members_count")}>{group.members_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}

      {openCreateModal ? (
        <section className="modal-overlay">
          <article className="modal-panel client-create-modal">
            <Link className="modal-close-x" href={closeHref} aria-label={uiText(language, "common.close")}>
              ×
            </Link>
            <header className="activity-modal-header">
              <h2 className="modal-title">{t("admin.clients.new_client_title")}</h2>
              <p className="muted">{t("admin.clients.new_client_subtitle")}</p>
            </header>

            <section className="card modal-card">
              <form id="create-client-form" action={createAdminClientAction} className="grid cols-3 config-form-grid">
                <input type="hidden" name="return_to" value={closeHref} />
                <ClientKindCreateSync formId="create-client-form" />

                <label>
                  {t("admin.clients.email_optional")}
                  <input type="email" name="email" />
                </label>
                <label>
                  {uiText(language, "client.first_name_label")} <span className="required-star">*</span>
                  <input type="text" name="first_name" required maxLength={100} />
                </label>
                <label>
                  {uiText(language, "client.last_name_label")} <span className="required-star">*</span>
                  <input type="text" name="last_name" required maxLength={100} />
                </label>

                <label>
                  {t("admin.clients.client_type")}
                  <select name="client_kind" defaultValue="ADULT">
                    <option value="ADULT">{uiText(language, "client.adult")}</option>
                    <option value="CHILD">{uiText(language, "client.child")}</option>
                  </select>
                </label>

                <label>
                  {uiText(language, "common.status")}
                  <select name="client_status" defaultValue="ACTIVE">
                    {CLIENT_STATUS_OPTIONS.map((statusValue) => (
                      <option key={statusValue} value={statusValue}>
                        {statusLabel(statusValue, language)}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Site
                  <select name="student_site" defaultValue="">
                    <option value="">Non renseigne</option>
                    {STUDENT_SITE_OPTIONS.map((siteValue) => (
                      <option key={siteValue} value={siteValue}>
                        {studentSiteLabel(siteValue)}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  {uiText(language, "client.mobile_phone_1")}
                  <input type="text" name="mobile_phone_1" maxLength={30} />
                </label>

                <label>
                  {uiText(language, "client.mobile_phone_2")}
                  <input type="text" name="mobile_phone_2" maxLength={30} />
                </label>
                <label>
                  {uiText(language, "client.home_phone_label")}
                  <input type="text" name="home_phone" maxLength={30} />
                </label>
                <label>
                  {t("admin.clients.birth_date")}
                  <input type="date" name="birth_date" />
                </label>

                <label className="span-2">
                  {uiText(language, "client.address_label")}
                  <input type="text" name="address_line" maxLength={255} />
                </label>
                <label>
                  {uiText(language, "client.postal_code_label")}
                  <input type="text" name="postal_code" maxLength={20} />
                </label>
                <label>
                  {uiText(language, "client.city_label")}
                  <input type="text" name="city" maxLength={120} />
                </label>
                <label>
                  {t("admin.clients.tax_country")} <span className="required-star">*</span>
                  <select name="address_country" defaultValue={DEFAULT_COUNTRY}>
                    {COUNTRY_OPTIONS.map((country) => (
                      <option key={country.value} value={country.value}>
                        {country.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  {uiText(language, "client.residence_country_label")}
                  <select name="residence_country" defaultValue={DEFAULT_COUNTRY}>
                    {COUNTRY_OPTIONS.map((country) => (
                      <option key={country.value} value={country.value}>
                        {country.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {uiText(language, "client.currency")}
                  <select name="preferred_currency" defaultValue={DEFAULT_CURRENCY}>
                    {CURRENCY_OPTIONS.map((currency) => (
                      <option key={currency.value} value={currency.value}>
                        {currency.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {uiText(language, "common.language")}
                  <select name="preferred_language" defaultValue="fr">
                    <option value="fr">{uiText(language, "common.french")}</option>
                    <option value="en">{uiText(language, "common.english")}</option>
                  </select>
                </label>
                <label>
                  {uiText(language, "client.timezone")}
                  <select name="timezone" defaultValue={DEFAULT_TIMEZONE}>
                    {TIMEZONE_OPTIONS.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="span-3">
                  {t("admin.clients.important_info")}
                  <textarea name="important_info" rows={3} maxLength={1000} />
                </label>

                <label className="span-3">
                  {t("admin.clients.private_note")}
                  <textarea name="private_note" rows={3} maxLength={5000} />
                </label>

                <fieldset className="span-3 config-payment-fieldset">
                  <legend>{t("admin.clients.communication_preferences")}</legend>
                  <label className="checkline">
                    <input type="checkbox" name="portal_contact_visible" defaultChecked />
                    {t("admin.clients.portal_contact_visible")}
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="email_opt_in" defaultChecked />
                    {t("admin.clients.email_info_opt_in")}
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="sms_opt_in" defaultChecked />
                    {t("admin.clients.sms_info_opt_in")}
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="lesson_reminder_email_opt_in" defaultChecked />
                    {t("admin.clients.email_reminders_opt_in")}
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="lesson_reminder_sms_opt_in" />
                    {t("admin.clients.sms_reminders_opt_in")}
                  </label>
                </fieldset>

                <article className="item span-3">
                  <h3>{t("admin.clients.family_option_title")}</h3>
                  <div className="grid cols-2">
                    <AdultLinkSelector language={language} />
                    <label className="checkline">
                      <input type="checkbox" name="existing_adult_billing_recipient" defaultChecked />
                      {t("admin.clients.existing_adult_billing_recipient")}
                    </label>
                    <label>
                      {t("admin.clients.relationship_label")}
                      <input type="text" name="relationship_label" maxLength={80} placeholder={t("admin.clients.relationship_placeholder")} />
                    </label>
                  </div>

                  <p className="muted">{t("admin.clients.create_and_link_new_adult")}</p>
                  <div className="grid cols-3">
                    <label>
                      {t("admin.clients.parent_email")}
                      <input type="email" name="adult_email" />
                    </label>
                    <label>
                      {t("admin.clients.parent_first_name")}
                      <input type="text" name="adult_first_name" maxLength={100} />
                    </label>
                    <label>
                      {t("admin.clients.parent_last_name")}
                      <input type="text" name="adult_last_name" maxLength={100} />
                    </label>

                    <label>
                      {t("admin.clients.parent_status")}
                      <select name="adult_client_status" defaultValue="RESPONSABLE">
                        {CLIENT_STATUS_OPTIONS.map((statusValue) => (
                          <option key={statusValue} value={statusValue}>
                            {statusLabel(statusValue, language)}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      {t("admin.clients.parent_mobile_phone_1")}
                      <input type="text" name="adult_mobile_phone_1" maxLength={30} />
                    </label>
                    <label>
                      {t("admin.clients.parent_mobile_phone_2")}
                      <input type="text" name="adult_mobile_phone_2" maxLength={30} />
                    </label>

                    <label>
                      {t("admin.clients.parent_home_phone")}
                      <input type="text" name="adult_home_phone" maxLength={30} />
                    </label>
                    <label className="span-2">
                      {t("admin.clients.parent_address")}
                      <input type="text" name="adult_address_line" maxLength={255} />
                    </label>
                    <label>
                      {t("admin.clients.parent_postal_code")}
                      <input type="text" name="adult_postal_code" maxLength={20} />
                    </label>
                    <label>
                      {t("admin.clients.parent_city")}
                      <input type="text" name="adult_city" maxLength={120} />
                    </label>
                    <label>
                      {t("admin.clients.parent_address_country")}
                      <select name="adult_address_country" defaultValue={DEFAULT_COUNTRY}>
                        {COUNTRY_OPTIONS.map((country) => (
                          <option key={country.value} value={country.value}>
                            {country.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      {t("admin.clients.parent_residence_country")}
                      <select name="adult_residence_country" defaultValue={DEFAULT_COUNTRY}>
                        {COUNTRY_OPTIONS.map((country) => (
                          <option key={country.value} value={country.value}>
                            {country.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      {t("admin.clients.parent_currency")}
                      <select name="adult_preferred_currency" defaultValue={DEFAULT_CURRENCY}>
                        {CURRENCY_OPTIONS.map((currency) => (
                          <option key={currency.value} value={currency.value}>
                            {currency.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      {t("admin.clients.parent_language")}
                      <select name="adult_preferred_language" defaultValue="fr">
                        <option value="fr">{uiText(language, "common.french")}</option>
                        <option value="en">{uiText(language, "common.english")}</option>
                      </select>
                    </label>
                    <label>
                      {t("admin.clients.parent_timezone")}
                      <select name="adult_timezone" defaultValue={DEFAULT_TIMEZONE}>
                        {TIMEZONE_OPTIONS.map((item) => (
                          <option key={item.value} value={item.value}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                </article>

                <div className="row span-3 modal-actions-end">
                  <button type="submit">{t("admin.clients.create_client")}</button>
                </div>
              </form>
            </section>
          </article>
        </section>
      ) : null}
    </section>
  );
}
