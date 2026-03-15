import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { resendCommunicationAction } from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import type {
  CommunicationFiltersOut,
  CommunicationPeriod,
  CommunicationReportPageOut,
  CommunicationReportRow,
} from "../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;
type ChannelFilter = "ALL" | "EMAIL" | "SMS";
type PerPage = 25 | 50 | 100;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function parseChannel(value: string): ChannelFilter {
  if (value === "EMAIL" || value === "SMS") {
    return value;
  }
  return "ALL";
}

function parsePeriod(value: string): CommunicationPeriod {
  if (
    value === "TODAY" ||
    value === "WEEK" ||
    value === "MONTH" ||
    value === "SEMESTER" ||
    value === "YEAR" ||
    value === "ALL"
  ) {
    return value;
  }
  return "TODAY";
}

function parsePerPage(value: string): PerPage {
  if (value === "25") {
    return 25;
  }
  if (value === "100") {
    return 100;
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

function deliveryLabel(value: CommunicationReportRow["delivery_status"]): string {
  if (value === "DELIVERED") {
    return "Livre";
  }
  if (value === "SENT") {
    return "Envoye";
  }
  if (value === "FAILED") {
    return "Echec";
  }
  if (value === "PENDING") {
    return "En attente";
  }
  if (value === "SKIPPED") {
    return "Ignore";
  }
  return "Inconnu";
}

function senderCategoryLabel(value: CommunicationReportRow["sender_category"]): string {
  if (value === "PROFESSOR") {
    return "Professeur";
  }
  if (value === "SYSTEM") {
    return "Systeme";
  }
  return "Autre utilisateur";
}

function channelLabel(value: CommunicationReportRow["channel"]): string {
  return value === "SMS" ? "SMS" : "Email";
}

function periodLabel(value: CommunicationPeriod): string {
  if (value === "TODAY") {
    return "du jour";
  }
  if (value === "WEEK") {
    return "des 7 derniers jours";
  }
  if (value === "MONTH") {
    return "des 30 derniers jours";
  }
  if (value === "SEMESTER") {
    return "des 6 derniers mois";
  }
  if (value === "YEAR") {
    return "de la derniere annee";
  }
  return "depuis origine";
}

type CommunicationFiltersState = {
  channel: ChannelFilter;
  q: string;
  communicationType: string;
  period: CommunicationPeriod;
  professorId: string;
  messageId: string;
  page: number;
  perPage: PerPage;
};

function buildHref(filters: CommunicationFiltersState, overrides?: Partial<CommunicationFiltersState>): string {
  const next: CommunicationFiltersState = { ...filters, ...(overrides ?? {}) };
  const params = new URLSearchParams();
  if (next.channel !== "ALL") {
    params.set("channel", next.channel);
  }
  if (next.q) {
    params.set("q", next.q);
  }
  if (next.communicationType) {
    params.set("communication_type", next.communicationType);
  }
  if (next.period !== "TODAY") {
    params.set("period", next.period);
  }
  if (next.professorId) {
    params.set("professor_id", next.professorId);
  }
  if (next.messageId) {
    params.set("message_id", next.messageId);
  }
  if (next.page > 1) {
    params.set("page", String(next.page));
  }
  if (next.perPage !== 50) {
    params.set("per_page", String(next.perPage));
  }
  const query = params.toString();
  return query ? `/admin/communications?${query}` : "/admin/communications";
}

function buildApiHref(filters: CommunicationFiltersState): string {
  const params = new URLSearchParams();
  if (filters.channel !== "ALL") {
    params.set("channel", filters.channel);
  }
  params.set("period", filters.period);
  params.set("page", String(filters.page));
  params.set("per_page", String(filters.perPage));
  if (filters.q) {
    params.set("q", filters.q);
  }
  if (filters.communicationType) {
    params.set("communication_type", filters.communicationType);
  }
  if (filters.professorId) {
    params.set("professor_id", filters.professorId);
  }
  return `/api/v1/admin/reports/communications?${params.toString()}`;
}

export default async function AdminCommunicationsPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const channel = parseChannel(readParam(searchParams, "channel"));
  const selectedMessageId = readParam(searchParams, "message_id");
  const q = readParam(searchParams, "q");
  const communicationType = readParam(searchParams, "communication_type");
  const period = parsePeriod(readParam(searchParams, "period"));
  const professorId = readParam(searchParams, "professor_id");
  const page = parsePage(readParam(searchParams, "page"));
  const perPage = parsePerPage(readParam(searchParams, "per_page"));

  const filters: CommunicationFiltersState = {
    channel,
    q,
    communicationType,
    period,
    professorId,
    messageId: selectedMessageId,
    page,
    perPage,
  };

  const dataResult = await backendRequest<CommunicationReportPageOut>(buildApiHref(filters), {}, token);
  const filterQuery = new URLSearchParams();
  if (channel !== "ALL") {
    filterQuery.set("channel", channel);
  }
  const filtersResult = await backendRequest<CommunicationFiltersOut>(
    `/api/v1/admin/reports/communications/filters?${filterQuery.toString()}`,
    {},
    token,
  );

  const pageData: CommunicationReportPageOut = dataResult.ok
    ? dataResult.data
    : { items: [], page: 1, per_page: perPage, total: 0, total_pages: 1 };
  const rows = pageData.items;
  const selected = selectedMessageId ? rows.find((row) => row.id === selectedMessageId) ?? null : null;
  const closeDetailHref = buildHref(filters, { messageId: "" });
  const resetHref = buildHref({
    ...filters,
    channel: "ALL",
    q: "",
    communicationType: "",
    period: "TODAY",
    professorId: "",
    messageId: "",
    page: 1,
    perPage: 50,
  });
  const communicationTypeOptions = filtersResult.ok ? filtersResult.data.communication_types : [];
  const professorOptions = filtersResult.ok ? filtersResult.data.professors : [];

  const previousPageHref = buildHref(filters, { page: Math.max(1, pageData.page - 1), messageId: "" });
  const nextPageHref = buildHref(filters, { page: Math.min(pageData.total_pages, pageData.page + 1), messageId: "" });

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h2>Suivi des communications</h2>
        <p className="muted">Journal unifie persistant: emetteur, destinataire, date, canal, type, sujet et etat de livraison.</p>
      </section>

      <section className="card">
        {!dataResult.ok ? <p className="flash-err top-gap-sm">Erreur backend: {dataResult.message}</p> : null}
        {!filtersResult.ok ? <p className="flash-err top-gap-sm">Erreur filtres: {filtersResult.message}</p> : null}
      </section>

      <section className="card">
        <form method="get" className="grid cols-4">
          <label className="stack-sm">
            Recherche libre
            <input type="text" name="q" defaultValue={q} placeholder="Sujet, destinataire, contenu..." />
          </label>
          <label className="stack-sm">
            Canal
            <select name="channel" defaultValue={channel}>
              <option value="ALL">Tous</option>
              <option value="EMAIL">Emails</option>
              <option value="SMS">SMS</option>
            </select>
          </label>
          <label className="stack-sm">
            Type communication
            <select name="communication_type" defaultValue={communicationType || ""}>
              <option value="">Tous</option>
              {communicationTypeOptions.map((option) => (
                <option key={option.code} value={option.code}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="stack-sm">
            Periode
            <select name="period" defaultValue={period}>
              <option value="TODAY">Jour</option>
              <option value="WEEK">Semaine (7 jours)</option>
              <option value="MONTH">Dernier mois</option>
              <option value="SEMESTER">Dernier semestre</option>
              <option value="YEAR">Derniere annee</option>
              <option value="ALL">Depuis origine</option>
            </select>
          </label>
          <label className="stack-sm">
            Professeur
            <select name="professor_id" defaultValue={professorId || ""}>
              <option value="">Tous</option>
              {professorOptions.map((professor) => (
                <option key={professor.id} value={professor.id}>
                  {professor.label}
                </option>
              ))}
            </select>
          </label>
          <label className="stack-sm">
            Messages / page
            <select name="per_page" defaultValue={String(perPage)}>
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
          </label>
          <input type="hidden" name="page" value="1" />
          <div className="row">
            <button type="submit">Filtrer</button>
            <a className="mode-link" href={resetHref}>
              Reinitialiser
            </a>
          </div>
        </form>
        <p className="muted">
          Affichage par defaut: communications du jour. Archive automatique des messages de plus d&apos;un an.
        </p>
      </section>

      <section className="card row" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <p className="muted">
          {pageData.total} message(s) {periodLabel(period)}.
        </p>
        <div className="row">
          <a className={`mode-link ${pageData.page <= 1 ? "disabled" : ""}`} href={pageData.page <= 1 ? "#" : previousPageHref}>
            ← Precedent
          </a>
          <span className="muted">
            Page {pageData.page} / {pageData.total_pages}
          </span>
          <a
            className={`mode-link ${pageData.page >= pageData.total_pages ? "disabled" : ""}`}
            href={pageData.page >= pageData.total_pages ? "#" : nextPageHref}
          >
            Suivant →
          </a>
        </div>
      </section>

      <section className="card table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Date & heure</th>
              <th>Canal</th>
              <th>Envoye par</th>
              <th>Type communication</th>
              <th>Sujet</th>
              <th>Destinataire</th>
              <th>Etat livraison</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={8}>
                  <p className="muted">Aucune communication pour les filtres selectionnes.</p>
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.id}>
                  <td>{formatDate(row.occurred_at)}</td>
                  <td>{channelLabel(row.channel)}</td>
                  <td>
                    <strong>{row.sender_label}</strong>
                    <div className="muted">{senderCategoryLabel(row.sender_category)}</div>
                  </td>
                  <td>{row.communication_type_label}</td>
                  <td>{row.subject}</td>
                  <td>{row.recipient}</td>
                  <td>
                    <span className="badge">{deliveryLabel(row.delivery_status)}</span>
                  </td>
                  <td>
                    <div className="row wrap gap-sm">
                      <a className="mode-link" href={buildHref(filters, { messageId: row.id })}>
                        Voir
                      </a>
                      {row.channel === "EMAIL" ? (
                        <form action={resendCommunicationAction}>
                          <input type="hidden" name="communication_id" value={row.id} />
                          <input type="hidden" name="recipient_email" value={row.recipient} />
                          <input type="hidden" name="return_to" value={buildHref(filters, { messageId: row.id })} />
                          <button type="submit" className="ghost">Renvoyer</button>
                        </form>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      {selected ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <a className="modal-close-x" href={closeDetailHref} aria-label="Fermer">
              ×
            </a>
            <h2 className="modal-title">Detail communication</h2>
            <p className="muted">
              {selected.channel} | {selected.source}
            </p>
            <p>
              <strong>Date:</strong> {formatDate(selected.occurred_at)}
            </p>
            <p>
              <strong>Envoye par:</strong> {selected.sender_label} ({senderCategoryLabel(selected.sender_category)})
            </p>
            <p>
              <strong>Type:</strong> {selected.communication_type_label}
            </p>
            <p>
              <strong>Destinataire:</strong> {selected.recipient}
            </p>
            <p>
              <strong>Sujet:</strong> {selected.subject}
            </p>
            <p>
              <strong>Etat:</strong> {deliveryLabel(selected.delivery_status)}
            </p>
            {selected.provider ? (
              <p>
                <strong>Provider:</strong> {selected.provider}
              </p>
            ) : null}
            {selected.provider_message_id ? (
              <p>
                <strong>Provider message id:</strong> {selected.provider_message_id}
              </p>
            ) : null}
            {selected.error_message ? (
              <p>
                <strong>Erreur provider:</strong> {selected.error_message}
              </p>
            ) : null}

            {selected.channel === "EMAIL" ? (
              <div className="row wrap gap-sm top-gap-sm">
                <form action={resendCommunicationAction} className="row wrap gap-sm">
                  <input type="hidden" name="communication_id" value={selected.id} />
                  <input type="hidden" name="return_to" value={buildHref(filters, { messageId: selected.id })} />
                  <input type="email" name="recipient_email" defaultValue={selected.recipient} />
                  <button type="submit">Renvoyer cet email</button>
                </form>
              </div>
            ) : null}

            <h3>Contenu</h3>
            {selected.content_format === "HTML" ? (
              <div className="card modal-card">
                <div dangerouslySetInnerHTML={{ __html: selected.content }} />
              </div>
            ) : (
              <pre className="message-body-preview">{selected.content}</pre>
            )}
          </article>
        </section>
      ) : null}
    </section>
  );
}
