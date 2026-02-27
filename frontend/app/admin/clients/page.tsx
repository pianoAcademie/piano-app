import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import AdultLinkSelector from "../../../components/adult-link-selector";
import ClientBulkControls from "../../../components/client-bulk-controls";
import {
  bulkAdminClientsAction,
  createAdminClientAction,
  createAdminClientGroupAction,
} from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import {
  COUNTRY_OPTIONS,
  CURRENCY_OPTIONS,
  DEFAULT_COUNTRY,
  DEFAULT_CURRENCY,
  DEFAULT_TIMEZONE,
  TIMEZONE_OPTIONS,
} from "../../../lib/reference-data";
import type { AdminClientGroupOut, AdminClientOut } from "../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;
type SortColumn = "last_name" | "first_name" | "family_name" | "client_status" | "client_kind" | "next_session";
type SortDirection = "asc" | "desc";
type ClientsView = "students" | "groups";
type PerPage = 5 | 50;

const CLIENT_STATUS_OPTIONS = [
  { value: "ACTIVE", label: "ACTIF" },
  { value: "TRIAL", label: "ESSAI" },
  { value: "PENDING", label: "EN ATTENTE" },
  { value: "INACTIVE", label: "INACTIF" },
  { value: "ARCHIVED", label: "ARCHIVE" },
] as const;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString("fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function parseSortColumn(value: string): SortColumn {
  if (
    value === "last_name" ||
    value === "first_name" ||
    value === "family_name" ||
    value === "client_status" ||
    value === "client_kind" ||
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

function statusLabel(status: string): string {
  const normalized = status.toUpperCase();
  const row = CLIENT_STATUS_OPTIONS.find((option) => option.value === normalized);
  return row?.label ?? normalized;
}

function statusPillClass(status: string): string {
  const normalized = status.toUpperCase();
  if (normalized === "ACTIVE") {
    return "status-ok";
  }
  if (normalized === "TRIAL" || normalized === "PENDING") {
    return "status-warn";
  }
  return "status-off";
}

function clientTypeLabel(kind: string): string {
  return kind === "CHILD" ? "ENFANT" : "ADULTE";
}

function buildClientsHref(params: {
  search: string;
  status: string;
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
  groupId: string;
  sortBy: SortColumn;
  sortDir: SortDirection;
  view: ClientsView;
  page: number;
  perPage: PerPage;
}): string {
  return buildClientsHref(params);
}

function countByStatus(clients: AdminClientOut[]): Record<string, number> {
  const counts: Record<string, number> = {
    ACTIVE: 0,
    TRIAL: 0,
    PENDING: 0,
    INACTIVE: 0,
    ARCHIVED: 0,
  };

  for (const client of clients) {
    const status = (client.client_status || "").toUpperCase();
    if (status in counts) {
      counts[status] += 1;
    }
  }

  return counts;
}

function sortHref(params: {
  currentSortBy: SortColumn;
  currentSortDir: SortDirection;
  targetSortBy: SortColumn;
  search: string;
  status: string;
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

function displayAdultName(client: AdminClientOut): string {
  const fullName = `${client.first_name ?? ""} ${client.last_name ?? ""}`.trim();
  return fullName || client.email;
}

export default async function AdminClientsPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const search = readParam(searchParams, "search").trim();
  const selectedStatus = readParam(searchParams, "status") || "ALL";
  const selectedGroupId = readParam(searchParams, "group_id");
  const sortBy = parseSortColumn(readParam(searchParams, "sort_by"));
  const sortDir = parseSortDirection(readParam(searchParams, "sort_dir"));
  const view = parseView(readParam(searchParams, "view"));
  const perPage = parsePerPage(readParam(searchParams, "per_page"));
  const requestedPage = parsePage(readParam(searchParams, "page"));
  const openCreateModal = readParam(searchParams, "new_client") === "1";

  const includeArchived = selectedStatus === "ARCHIVED";
  const clientsQuery = new URLSearchParams();
  clientsQuery.set("limit", "1000");
  clientsQuery.set("sort_by", sortBy);
  clientsQuery.set("sort_dir", sortDir);
  clientsQuery.set("include_archived", includeArchived ? "true" : "false");
  if (search) {
    clientsQuery.set("search", search);
  }
  if (selectedStatus !== "ALL") {
    clientsQuery.set("client_status", selectedStatus);
  }
  if (selectedGroupId) {
    clientsQuery.set("group_id", selectedGroupId);
  }

  const [clientsResult, allClientsResult, groupsResult, adultCandidatesResult] = await Promise.all([
    backendRequest<AdminClientOut[]>(`/api/v1/admin/clients?${clientsQuery.toString()}`, {}, token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?limit=1000&include_archived=true", {}, token),
    backendRequest<AdminClientGroupOut[]>("/api/v1/admin/clients/groups?include_inactive=true", {}, token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?limit=1000&include_archived=false&sort_by=last_name&sort_dir=asc", {}, token),
  ]);

  const listedClientsRaw = clientsResult.ok ? clientsResult.data : [];
  const allClients = allClientsResult.ok ? allClientsResult.data : [];
  const groups = groupsResult.ok ? groupsResult.data : [];
  const adultCandidates = adultCandidatesResult.ok
    ? adultCandidatesResult.data.filter((client) => client.client_kind === "ADULT")
    : [];

  const counts = countByStatus(allClients);

  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error");

  const totalFiltered = listedClientsRaw.length;
  const totalPages = Math.max(1, Math.ceil(totalFiltered / perPage));
  const currentPage = Math.min(requestedPage, totalPages);
  const pageStart = (currentPage - 1) * perPage;
  const listedClients = listedClientsRaw.slice(pageStart, pageStart + perPage);

  const baseHref = buildClientsHref({
    search,
    status: selectedStatus,
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
    groupId: selectedGroupId,
    sortBy,
    sortDir,
    view,
    page: currentPage,
    perPage,
  });

  const adultPreviewCandidates = adultCandidates.map((adult) => ({
    id: adult.id,
    display_name: displayAdultName(adult),
    email: adult.email,
    mobile_phone_1: adult.mobile_phone_1,
    mobile_phone_2: adult.mobile_phone_2,
    home_phone: adult.home_phone,
    address_line: adult.address_line,
    postal_code: adult.postal_code,
    city: adult.city,
    address_country: adult.address_country,
    residence_country: adult.residence_country,
  }));

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread">
          <h2>Clients</h2>
          <Link className="mode-link" href={`${closeHref}${closeHref.includes("?") ? "&" : "?"}new_client=1`}>
            Ajouter nouveau
          </Link>
        </div>
        <p className="muted">Gestion des adherents, des groupes et des actions en masse.</p>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {!clientsResult.ok ? <section className="flash-err">Erreur backend clients: {clientsResult.message}</section> : null}
      {!groupsResult.ok ? <section className="flash-err">Erreur backend groupes: {groupsResult.message}</section> : null}

      <section className="card">
        <div className="row client-subtabs">
          <Link
            className={`mode-link ${view === "students" ? "mode-active" : ""}`}
            href={buildClientsHref({
              search,
              status: selectedStatus,
              groupId: selectedGroupId,
              sortBy,
              sortDir,
              view: "students",
              page: 1,
              perPage,
            })}
          >
            Etudiants
          </Link>
          <Link
            className={`mode-link ${view === "groups" ? "mode-active" : ""}`}
            href={buildClientsHref({
              search,
              status: selectedStatus,
              groupId: selectedGroupId,
              sortBy,
              sortDir,
              view: "groups",
              page: 1,
              perPage,
            })}
          >
            Etiquettes de groupe
          </Link>
        </div>
      </section>

      {view === "students" ? (
        <>
          <section className="card">
            <div className="row client-status-counts">
              <span>
                <strong>{counts.ACTIVE}</strong> Actif
              </span>
              <span>
                <strong>{counts.TRIAL}</strong> Essai
              </span>
              <span>
                <strong>{counts.PENDING}</strong> En attente
              </span>
              <span>
                <strong>{counts.INACTIVE}</strong> Inactif
              </span>
              <span>
                <strong>{counts.ARCHIVED}</strong> Archive
              </span>
            </div>
          </section>

          <section className="card">
            <h2>Filtres</h2>
            <form method="get" className="grid cols-4">
              <input type="hidden" name="view" value="students" />
              <input type="hidden" name="sort_by" value={sortBy} />
              <input type="hidden" name="sort_dir" value={sortDir} />
              <input type="hidden" name="page" value="1" />

              <label>
                Recherche (email, prenom, nom)
                <input type="text" name="search" defaultValue={search} placeholder="ex: marie, @example.com" />
              </label>

              <label>
                Statut adherent
                <select name="status" defaultValue={selectedStatus}>
                  <option value="ALL">Tous (hors archives)</option>
                  {CLIENT_STATUS_OPTIONS.map((statusOption) => (
                    <option key={statusOption.value} value={statusOption.value}>
                      {statusOption.label}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Groupe
                <select name="group_id" defaultValue={selectedGroupId}>
                  <option value="">Tous</option>
                  {groups.filter((group) => group.active).map((group) => (
                    <option key={group.id} value={group.id}>
                      {group.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Clients par page
                <select name="per_page" defaultValue={String(perPage)}>
                  <option value="5">5</option>
                  <option value="50">50</option>
                </select>
              </label>

              <div className="row">
                <button type="submit">Appliquer</button>
                <a className="reset-link" href="/admin/clients">
                  Reinitialiser
                </a>
              </div>
            </form>
          </section>

          <form id="clients-bulk-form" action={bulkAdminClientsAction} className="admin-page-grid">
            <input type="hidden" name="return_to" value={baseHref} />
            <input type="hidden" name="filter_search" value={search} />
            <input type="hidden" name="filter_status" value={selectedStatus !== "ALL" ? selectedStatus : ""} />
            <input type="hidden" name="filter_group_id" value={selectedGroupId} />
            <input type="hidden" name="filter_include_archived" value={includeArchived ? "true" : "false"} />
            <input type="hidden" name="filter_active_only" value="false" />
            {listedClientsRaw.map((client) => (
              <input key={`filtered-${client.id}`} type="hidden" name="filtered_client_ids" value={client.id} />
            ))}

            <section className="card">
              <ClientBulkControls
                groups={groups.filter((group) => group.active).map((group) => ({ id: group.id, name: group.name }))}
                pageCount={listedClients.length}
                filteredCount={listedClientsRaw.length}
              />
            </section>

            <section className="card table-wrap">
              <table className="data-table clients-table">
                <thead>
                  <tr>
                    <th style={{ width: "52px" }}>
                      <input type="checkbox" aria-label="Selectionner la page" data-role="select-page-toggle" />
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
                          groupId: selectedGroupId,
                          view,
                          page: currentPage,
                          perPage,
                        })}
                      >
                        Nom adherent {sortIndicator(sortBy, sortDir, "last_name")}
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
                          groupId: selectedGroupId,
                          view,
                          page: currentPage,
                          perPage,
                        })}
                      >
                        Prenom adherent {sortIndicator(sortBy, sortDir, "first_name")}
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
                          groupId: selectedGroupId,
                          view,
                          page: currentPage,
                          perPage,
                        })}
                      >
                        Famille adherent {sortIndicator(sortBy, sortDir, "family_name")}
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
                          groupId: selectedGroupId,
                          view,
                          page: currentPage,
                          perPage,
                        })}
                      >
                        Statut {sortIndicator(sortBy, sortDir, "client_status")}
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
                          groupId: selectedGroupId,
                          view,
                          page: currentPage,
                          perPage,
                        })}
                      >
                        Type {sortIndicator(sortBy, sortDir, "client_kind")}
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
                          groupId: selectedGroupId,
                          view,
                          page: currentPage,
                          perPage,
                        })}
                      >
                        Prochain cours {sortIndicator(sortBy, sortDir, "next_session")}
                      </Link>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {listedClients.map((client) => (
                    <tr key={client.id}>
                      <td>
                        <input type="checkbox" name="client_ids" value={client.id} aria-label={`Selection ${client.email}`} />
                      </td>
                      <td>
                        <Link className="client-name-link" href={`/admin/clients/${client.id}`}>
                          {client.last_name || "-"}
                        </Link>
                      </td>
                      <td>{client.first_name || "-"}</td>
                      <td>
                        <span>{client.family_name || "-"}</span>
                        {client.group_names.length > 0 ? <small className="muted row-inline">{client.group_names.join(" | ")}</small> : null}
                      </td>
                      <td>
                        <span className={`status-pill ${statusPillClass(client.client_status)}`}>{statusLabel(client.client_status)}</span>
                      </td>
                      <td>{clientTypeLabel(client.client_kind)}</td>
                      <td>{client.next_session_start_at_utc ? formatDate(client.next_session_start_at_utc) : "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {clientsResult.ok && totalFiltered > 0 ? (
                <div className="row spread clients-pagination">
                  <small className="muted">
                    Affichage {pageStart + 1}-{Math.min(pageStart + listedClients.length, totalFiltered)} sur {totalFiltered} adherent(s)
                  </small>
                  <div className="row">
                    {currentPage > 1 ? (
                      <Link
                        className="mode-link"
                        href={buildClientsHref({
                          search,
                          status: selectedStatus,
                          groupId: selectedGroupId,
                          sortBy,
                          sortDir,
                          view,
                          page: currentPage - 1,
                          perPage,
                        })}
                      >
                        ← Precedent
                      </Link>
                    ) : (
                      <span className="mode-link disabled-link">← Precedent</span>
                    )}
                    <span className="badge">
                      Page {currentPage}/{totalPages}
                    </span>
                    {currentPage < totalPages ? (
                      <Link
                        className="mode-link"
                        href={buildClientsHref({
                          search,
                          status: selectedStatus,
                          groupId: selectedGroupId,
                          sortBy,
                          sortDir,
                          view,
                          page: currentPage + 1,
                          perPage,
                        })}
                      >
                        Suivant →
                      </Link>
                    ) : (
                      <span className="mode-link disabled-link">Suivant →</span>
                    )}
                  </div>
                </div>
              ) : null}

              {clientsResult.ok && listedClients.length === 0 ? <p className="muted">Aucun client pour ces filtres.</p> : null}
            </section>
          </form>
        </>
      ) : (
        <>
          <section className="card">
            <h2>Nouveau groupe</h2>
            <form action={createAdminClientGroupAction} className="grid cols-4">
              <input type="hidden" name="return_to" value="/admin/clients?view=groups" />
              <label>
                Nom groupe
                <input name="name" type="text" maxLength={120} required placeholder="ex: collectif enfant" />
              </label>
              <label>
                Code (optionnel)
                <input name="code" type="text" maxLength={80} placeholder="COLLECTIF_ENFANT" />
              </label>
              <label className="checkline">
                <input type="checkbox" name="active" defaultChecked />
                Groupe actif
              </label>
              <div className="row">
                <button type="submit">Creer groupe</button>
              </div>
            </form>
          </section>

          <section className="card table-wrap">
            <h2>Groupes existants</h2>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Nom</th>
                  <th>Code</th>
                  <th>Statut</th>
                  <th>Membres</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((group) => (
                  <tr key={group.id}>
                    <td>{group.name}</td>
                    <td>{group.code}</td>
                    <td>
                      <span className={`status-pill ${group.active ? "status-ok" : "status-off"}`}>{group.active ? "ACTIF" : "INACTIF"}</span>
                    </td>
                    <td>{group.members_count}</td>
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
            <Link className="modal-close-x" href={closeHref} aria-label="Fermer">
              ×
            </Link>
            <header className="activity-modal-header">
              <h2 className="modal-title">Nouveau client</h2>
              <p className="muted">Creer un adherent et, si besoin, configurer son rattachement famille.</p>
            </header>

            <section className="card modal-card">
              <form action={createAdminClientAction} className="grid cols-3 config-form-grid">
                <input type="hidden" name="return_to" value={closeHref} />

                <label>
                  Email (optionnel)
                  <input type="email" name="email" />
                </label>
                <label>
                  Prenom <span className="required-star">*</span>
                  <input type="text" name="first_name" required maxLength={100} />
                </label>
                <label>
                  Nom <span className="required-star">*</span>
                  <input type="text" name="last_name" required maxLength={100} />
                </label>

                <label>
                  Type adherent
                  <select name="client_kind" defaultValue="ADULT">
                    <option value="ADULT">Adulte</option>
                    <option value="CHILD">Enfant</option>
                  </select>
                </label>

                <label>
                  Statut
                  <select name="client_status" defaultValue="ACTIVE">
                    {CLIENT_STATUS_OPTIONS.map((statusOption) => (
                      <option key={statusOption.value} value={statusOption.value}>
                        {statusOption.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Tel mob 1
                  <input type="text" name="mobile_phone_1" maxLength={30} />
                </label>

                <label>
                  Tel mob 2
                  <input type="text" name="mobile_phone_2" maxLength={30} />
                </label>
                <label>
                  Tel domicile
                  <input type="text" name="home_phone" maxLength={30} />
                </label>
                <label>
                  Date de naissance
                  <input type="date" name="birth_date" />
                </label>

                <label className="span-2">
                  Adresse postale
                  <input type="text" name="address_line" maxLength={255} />
                </label>
                <label>
                  Code postal
                  <input type="text" name="postal_code" maxLength={20} />
                </label>
                <label>
                  Ville
                  <input type="text" name="city" maxLength={120} />
                </label>
                <label>
                  Pays taxation <span className="required-star">*</span>
                  <select name="address_country" defaultValue={DEFAULT_COUNTRY}>
                    {COUNTRY_OPTIONS.map((country) => (
                      <option key={country.value} value={country.value}>
                        {country.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Pays residence
                  <select name="residence_country" defaultValue={DEFAULT_COUNTRY}>
                    {COUNTRY_OPTIONS.map((country) => (
                      <option key={country.value} value={country.value}>
                        {country.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Devise
                  <select name="preferred_currency" defaultValue={DEFAULT_CURRENCY}>
                    {CURRENCY_OPTIONS.map((currency) => (
                      <option key={currency.value} value={currency.value}>
                        {currency.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Fuseau horaire
                  <select name="timezone" defaultValue={DEFAULT_TIMEZONE}>
                    {TIMEZONE_OPTIONS.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="span-3">
                  Informations a connaitre (allergies, etc.)
                  <textarea name="important_info" rows={3} maxLength={1000} />
                </label>

                <label className="span-3">
                  Note privee interne
                  <textarea name="private_note" rows={3} maxLength={5000} />
                </label>

                <fieldset className="span-3 config-payment-fieldset">
                  <legend>Preferences communication</legend>
                  <label className="checkline">
                    <input type="checkbox" name="portal_contact_visible" defaultChecked />
                    Afficher dans les contacts du portail etudiant
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="email_opt_in" defaultChecked />
                    Recevoir les emails d information
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="sms_opt_in" defaultChecked />
                    Recevoir les SMS d information
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="lesson_reminder_email_opt_in" defaultChecked />
                    Recevoir les rappels de cours par email
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="lesson_reminder_sms_opt_in" />
                    Recevoir les rappels de cours par SMS
                  </label>
                </fieldset>

                <article className="item span-3">
                  <h3>Option Famille (activee si type ENFANT)</h3>
                  <div className="grid cols-2">
                    <AdultLinkSelector adults={adultPreviewCandidates} />
                    <label className="checkline">
                      <input type="checkbox" name="existing_adult_billing_recipient" defaultChecked />
                      Adulte existant destinataire facture
                    </label>
                    <label>
                      Lien de relation
                      <input type="text" name="relationship_label" maxLength={80} placeholder="ex: parent, pere, mere..." />
                    </label>
                  </div>

                  <p className="muted">Creer un nouvel adulte et le rattacher (optionnel)</p>
                  <div className="grid cols-3">
                    <label>
                      Email parent
                      <input type="email" name="adult_email" />
                    </label>
                    <label>
                      Prenom parent
                      <input type="text" name="adult_first_name" maxLength={100} />
                    </label>
                    <label>
                      Nom parent
                      <input type="text" name="adult_last_name" maxLength={100} />
                    </label>

                    <label>
                      Statut parent
                      <select name="adult_client_status" defaultValue="ACTIVE">
                        {CLIENT_STATUS_OPTIONS.map((statusOption) => (
                          <option key={statusOption.value} value={statusOption.value}>
                            {statusOption.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Tel mob 1 parent
                      <input type="text" name="adult_mobile_phone_1" maxLength={30} />
                    </label>
                    <label>
                      Tel mob 2 parent
                      <input type="text" name="adult_mobile_phone_2" maxLength={30} />
                    </label>

                    <label>
                      Tel domicile parent
                      <input type="text" name="adult_home_phone" maxLength={30} />
                    </label>
                    <label className="span-2">
                      Adresse parent
                      <input type="text" name="adult_address_line" maxLength={255} />
                    </label>
                    <label>
                      Code postal parent
                      <input type="text" name="adult_postal_code" maxLength={20} />
                    </label>
                    <label>
                      Ville parent
                      <input type="text" name="adult_city" maxLength={120} />
                    </label>
                    <label>
                      Pays adresse parent
                      <select name="adult_address_country" defaultValue={DEFAULT_COUNTRY}>
                        {COUNTRY_OPTIONS.map((country) => (
                          <option key={country.value} value={country.value}>
                            {country.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Pays residence parent
                      <select name="adult_residence_country" defaultValue={DEFAULT_COUNTRY}>
                        {COUNTRY_OPTIONS.map((country) => (
                          <option key={country.value} value={country.value}>
                            {country.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Devise parent
                      <select name="adult_preferred_currency" defaultValue={DEFAULT_CURRENCY}>
                        {CURRENCY_OPTIONS.map((currency) => (
                          <option key={currency.value} value={currency.value}>
                            {currency.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Fuseau parent
                      <select name="adult_timezone" defaultValue={DEFAULT_TIMEZONE}>
                        {TIMEZONE_OPTIONS.map((item) => (
                          <option key={item.value} value={item.value}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="checkline">
                      <input type="checkbox" name="new_adult_billing_recipient" />
                      Nouvel adulte destinataire facture
                    </label>
                  </div>
                </article>

                <div className="row span-3 modal-actions-end">
                  <button type="submit">Creer adherent</button>
                </div>
              </form>
            </section>
          </article>
        </section>
      ) : null}
    </section>
  );
}
