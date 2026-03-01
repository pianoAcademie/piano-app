import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest } from "../../../lib/backend";
import type { CommunicationReportRow } from "../../../lib/types";

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

function buildHref(channel: "EMAIL" | "SMS", messageId = ""): string {
  const params = new URLSearchParams();
  params.set("channel", channel);
  if (messageId) {
    params.set("message_id", messageId);
  }
  return `/admin/communications?${params.toString()}`;
}

export default async function AdminCommunicationsPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const channel = parseChannel(readParam(searchParams, "channel"));
  const selectedMessageId = readParam(searchParams, "message_id");
  const dataResult = await backendRequest<CommunicationReportRow[]>(
    `/api/v1/admin/reports/communications?channel=${encodeURIComponent(channel)}&limit=500`,
    {},
    token,
  );

  const rows = dataResult.ok ? dataResult.data : [];
  const selected = selectedMessageId ? rows.find((row) => row.id === selectedMessageId) ?? null : null;
  const closeDetailHref = buildHref(channel);

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h2>Suivi des communications</h2>
        <p className="muted">Journal des messages du systeme: emetteur, destinataire, date, sujet et etat de livraison.</p>
      </section>

      <section className="card">
        <div className="row">
          <a className={`mode-link ${channel === "EMAIL" ? "mode-active" : ""}`} href={buildHref("EMAIL")}>
            Mails
          </a>
          <a className={`mode-link ${channel === "SMS" ? "mode-active" : ""}`} href={buildHref("SMS")}>
            SMS
          </a>
        </div>
        {!dataResult.ok ? <p className="flash-err top-gap-sm">Erreur backend: {dataResult.message}</p> : null}
      </section>

      <section className="card table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Date & heure</th>
              <th>Envoye par</th>
              <th>Sujet</th>
              <th>Destinataire</th>
              <th>Etat livraison</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6}>
                  <p className="muted">Aucune communication {channel === "EMAIL" ? "mail" : "SMS"} disponible.</p>
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
                  <td>{row.subject}</td>
                  <td>{row.recipient}</td>
                  <td>
                    <span className="badge">{deliveryLabel(row.delivery_status)}</span>
                  </td>
                  <td>
                    <a className="mode-link" href={buildHref(channel, row.id)}>
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
              <strong>Destinataire:</strong> {selected.recipient}
            </p>
            <p>
              <strong>Sujet:</strong> {selected.subject}
            </p>
            <p>
              <strong>Etat:</strong> {deliveryLabel(selected.delivery_status)}
            </p>
            {selected.provider_message_id ? (
              <p>
                <strong>Provider message id:</strong> {selected.provider_message_id}
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
