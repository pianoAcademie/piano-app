import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest } from "../../../lib/backend";
import type { CommunicationFiltersOut, CommunicationReportRow } from "../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function parseChannel(value: string): "EMAIL" | "SMS" {
  return value === "SMS" ? "SMS" : "EMAIL";
}

function todayIsoDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = `${now.getMonth() + 1}`.padStart(2, "0");
  const day = `${now.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return date.toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" });
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

type CommunicationFiltersState = {
  channel: "EMAIL" | "SMS";
  q: string;
  communicationType: string;
  occurredOn: string;
  professorId: string;
  messageId: string;
};

function buildHref(filters: CommunicationFiltersState, overrides?: Partial<CommunicationFiltersState>): string {
  const next: CommunicationFiltersState = { ...filters, ...(overrides ?? {}) };
  const params = new URLSearchParams();
  params.set("channel", next.channel);
  if (next.q) {
    params.set("q", next.q);
  }
  if (next.communicationType) {
    params.set("communication_type", next.communicationType);
  }
  if (next.occurredOn) {
    params.set("occurred_on", next.occurredOn);
  }
  if (next.professorId) {
    params.set("professor_id", next.professorId);
  }
  if (next.messageId) {
    params.set("message_id", next.messageId);
  }
  return `/admin/communications?${params.toString()}`;
}

function buildApiHref(filters: CommunicationFiltersState): string {
  const params = new URLSearchParams();
  params.set("channel", filters.channel);
  params.set("limit", "500");
  if (filters.q) {
    params.set("q", filters.q);
  }
  if (filters.communicationType) {
    params.set("communication_type", filters.communicationType);
  }
  if (filters.occurredOn) {
    params.set("occurred_on", filters.occurredOn);
  }
  if (filters.professorId) {
    params.set("professor_id", filters.professorId);
  }
  return `/api/v1/admin/reports/communications?${params.toString()}`;
}

export default async function AdminCommunicationsPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const channel = parseChannel(readParam(searchParams, "channel"));
  const selectedMessageId = readParam(searchParams, "message_id");
  const q = readParam(searchParams, "q");
  const communicationType = readParam(searchParams, "communication_type");
  const occurredOn = readParam(searchParams, "occurred_on") || todayIsoDate();
  const professorId = readParam(searchParams, "professor_id");

  const filters: CommunicationFiltersState = {
    channel,
    q,
    communicationType,
    occurredOn,
    professorId,
    messageId: selectedMessageId,
  };

  const dataResult = await backendRequest<CommunicationReportRow[]>(buildApiHref(filters), {}, token);
  const filtersResult = await backendRequest<CommunicationFiltersOut>(
    `/api/v1/admin/reports/communications/filters?channel=${encodeURIComponent(channel)}`,
    {},
    token,
  );

  const rows = dataResult.ok ? dataResult.data : [];
  const selected = selectedMessageId ? rows.find((row) => row.id === selectedMessageId) ?? null : null;
  const closeDetailHref = buildHref(filters, { messageId: "" });
  const resetHref = buildHref({ ...filters, q: "", communicationType: "", occurredOn: todayIsoDate(), professorId: "", messageId: "" });
  const communicationTypeOptions = filtersResult.ok ? filtersResult.data.communication_types : [];
  const professorOptions = filtersResult.ok ? filtersResult.data.professors : [];

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h2>Suivi des communications</h2>
        <p className="muted">Journal unifie persistant: emetteur, destinataire, date, type, sujet et etat de livraison.</p>
      </section>

      <section className="card">
        <div className="row">
          <a className={`mode-link ${channel === "EMAIL" ? "mode-active" : ""}`} href={buildHref(filters, { channel: "EMAIL", messageId: "" })}>
            Mails
          </a>
          <a className={`mode-link ${channel === "SMS" ? "mode-active" : ""}`} href={buildHref(filters, { channel: "SMS", messageId: "" })}>
            SMS
          </a>
        </div>
        {!dataResult.ok ? <p className="flash-err top-gap-sm">Erreur backend: {dataResult.message}</p> : null}
        {!filtersResult.ok ? <p className="flash-err top-gap-sm">Erreur filtres: {filtersResult.message}</p> : null}
      </section>

      <section className="card">
        <form method="get" className="grid cols-4">
          <input type="hidden" name="channel" value={channel} />
          <label className="stack-sm">
            Recherche libre
            <input type="text" name="q" defaultValue={q} placeholder="Sujet, destinataire, contenu..." />
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
            Date
            <input type="date" name="occurred_on" defaultValue={occurredOn} />
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
          <div className="row">
            <button type="submit">Filtrer</button>
            <a className="mode-link" href={resetHref}>
              Reinitialiser
            </a>
          </div>
        </form>
        <p className="muted">Affichage par defaut: communications du jour ({occurredOn}).</p>
      </section>

      <section className="card table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Date & heure</th>
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
                <td colSpan={7}>
                  <p className="muted">Aucune communication {channel === "EMAIL" ? "mail" : "SMS"} pour les filtres selectionnes.</p>
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.id}>
                  <td>{formatDate(row.occurred_at)}</td>
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
                    <a className="mode-link" href={buildHref(filters, { messageId: row.id })}>
                      Voir
                    </a>
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
