"use client";

import { useMemo, useState } from "react";

type QuoteSession = {
  date: string;
  start_time: string;
  end_time: string;
  activity_label: string;
  location_label: string;
  modality: string;
};

type QuoteSessionsViewerProps = {
  quoteNumber: string;
  sessions: QuoteSession[];
};

function modalityLabel(value: string): string {
  const normalized = value.trim().toUpperCase();
  if (normalized === "ONLINE") {
    return "En ligne";
  }
  if (normalized === "ONSITE") {
    return "Presentiel";
  }
  return normalized || "-";
}

function csvEscapeCell(value: string): string {
  const normalized = value.replaceAll('"', '""');
  return `"${normalized}"`;
}

function toCsv(sessions: QuoteSession[]): string {
  const header = ["Date", "Heure debut", "Heure fin", "Activite", "Lieu", "Modalite"];
  const lines = sessions.map((row) => [
    row.date,
    row.start_time,
    row.end_time,
    row.activity_label,
    row.location_label,
    modalityLabel(row.modality),
  ]);
  return [header, ...lines]
    .map((line) => line.map((item) => csvEscapeCell(String(item))).join(";"))
    .join("\n");
}

function safeFileNamePart(value: string): string {
  const normalized = value.trim().toLowerCase().replaceAll(/[^a-z0-9_-]+/g, "-").replaceAll(/-+/g, "-");
  return normalized.replaceAll(/^-|-$/g, "") || "devis";
}

export default function QuoteSessionsViewer({ quoteNumber, sessions }: QuoteSessionsViewerProps): JSX.Element {
  const [open, setOpen] = useState(false);

  const normalized = useMemo(
    () =>
      [...sessions]
        .map((row) => ({
          ...row,
          date: String(row.date || "").trim(),
          start_time: String(row.start_time || "").trim(),
          end_time: String(row.end_time || "").trim(),
          activity_label: String(row.activity_label || "Activite"),
          location_label: String(row.location_label || "Lieu non defini"),
          modality: String(row.modality || ""),
        }))
        .sort((a, b) => {
          if (a.date < b.date) return -1;
          if (a.date > b.date) return 1;
          if (a.start_time < b.start_time) return -1;
          if (a.start_time > b.start_time) return 1;
          return 0;
        }),
    [sessions],
  );

  const csvHref = useMemo(() => {
    const csv = toCsv(normalized);
    return `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`;
  }, [normalized]);

  const downloadName = `devis-${safeFileNamePart(quoteNumber)}-seances.csv`;

  if (normalized.length === 0) {
    return <p className="muted top-gap-sm">Aucune seance detaillee.</p>;
  }

  return (
    <>
      <div className="row wrap gap-sm top-gap-sm">
        <button type="button" className="ghost" onClick={() => setOpen(true)}>
          Voir le detail ({normalized.length} seances)
        </button>
        <a className="ghost" href={csvHref} download={downloadName}>
          Telecharger CSV
        </a>
      </div>

      {open ? (
        <section className="modal-overlay modal-overlay-front" role="dialog" aria-modal="true" aria-label="Detail des seances">
          <article className="modal-panel quote-sessions-modal">
            <div className="row spread wrap gap-sm">
              <h3 className="modal-title">Detail des seances ({normalized.length})</h3>
              <button type="button" className="modal-close-x" onClick={() => setOpen(false)} aria-label="Fermer">
                x
              </button>
            </div>

            <div className="quote-public-lines top-gap-sm quote-sessions-modal-list">
              {normalized.map((session, index) => (
                <article key={`${session.date}-${session.start_time}-${session.activity_label}-${index}`} className="quote-public-line-item">
                  <strong>{session.date}</strong>
                  <span>{session.start_time} - {session.end_time}</span>
                  <small className="muted">
                    {session.activity_label}
                    {" · "}
                    {session.location_label}
                    {" · "}
                    {modalityLabel(session.modality)}
                  </small>
                </article>
              ))}
            </div>

            <div className="row wrap gap-sm top-gap-sm">
              <a className="ghost" href={csvHref} download={downloadName}>
                Telecharger CSV
              </a>
              <button type="button" className="ghost" onClick={() => setOpen(false)}>
                Fermer
              </button>
            </div>
          </article>
        </section>
      ) : null}
    </>
  );
}
