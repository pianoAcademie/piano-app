"use client";

import { useMemo, useState } from "react";

import { normalizeUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";

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
  language?: UiLanguage | string;
};

function modalityLabel(value: string, language: UiLanguage): string {
  const normalized = value.trim().toUpperCase();
  if (normalized === "ONLINE") {
    return uiText(language, "admin.quote_planning.modality_online");
  }
  if (normalized === "ONSITE") {
    return uiText(language, "admin.quote_planning.modality_onsite");
  }
  return normalized || "-";
}

function csvEscapeCell(value: string): string {
  const normalized = value.replaceAll('"', '""');
  return `"${normalized}"`;
}

function toCsv(sessions: QuoteSession[], language: UiLanguage): string {
  const header = [
    uiText(language, "common.date"),
    uiText(language, "admin.quote_planning.start_time"),
    uiText(language, "admin.quote_planning.end_time"),
    uiText(language, "admin.quote_lines.kind_activity"),
    uiText(language, "common.location"),
    uiText(language, "admin.quote_planning.modality"),
  ];
  const lines = sessions.map((row) => [
    row.date,
    row.start_time,
    row.end_time,
    row.activity_label,
    row.location_label,
    modalityLabel(row.modality, language),
  ]);
  return [header, ...lines]
    .map((line) => line.map((item) => csvEscapeCell(String(item))).join(";"))
    .join("\n");
}

function safeFileNamePart(value: string): string {
  const normalized = value.trim().toLowerCase().replaceAll(/[^a-z0-9_-]+/g, "-").replaceAll(/-+/g, "-");
  return normalized.replaceAll(/^-|-$/g, "") || "file";
}

export default function QuoteSessionsViewer({ quoteNumber, sessions, language: languageProp = "fr" }: QuoteSessionsViewerProps): JSX.Element {
  const language = normalizeUiLanguage(languageProp);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const [open, setOpen] = useState(false);

  const normalized = useMemo(
    () =>
      [...sessions]
        .map((row) => ({
          ...row,
          date: String(row.date || "").trim(),
          start_time: String(row.start_time || "").trim(),
          end_time: String(row.end_time || "").trim(),
          activity_label: String(row.activity_label || t("admin.quote_lines.kind_activity")),
          location_label: String(row.location_label || t("admin.quote_detail.location_not_defined")),
          modality: String(row.modality || ""),
        }))
        .sort((a, b) => {
          if (a.date < b.date) return -1;
          if (a.date > b.date) return 1;
          if (a.start_time < b.start_time) return -1;
          if (a.start_time > b.start_time) return 1;
          return 0;
        }),
    [sessions, language],
  );

  const csvHref = useMemo(() => {
    const csv = toCsv(normalized, language);
    return `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`;
  }, [normalized, language]);

  const downloadName = `${safeFileNamePart(t("admin.quote_sessions.file_prefix"))}-${safeFileNamePart(quoteNumber)}-${safeFileNamePart(t("admin.quote_sessions.file_suffix"))}.csv`;

  if (normalized.length === 0) {
    return <p className="muted top-gap-sm">{t("admin.quote_sessions.empty")}</p>;
  }

  return (
    <>
      <div className="row wrap gap-sm top-gap-sm">
        <button type="button" className="ghost" onClick={() => setOpen(true)}>
          {t("admin.quote_sessions.show_detail", { count: normalized.length })}
        </button>
        <a className="ghost" href={csvHref} download={downloadName}>
          {t("admin.quote_sessions.download_csv")}
        </a>
      </div>

      {open ? (
        <section className="modal-overlay modal-overlay-front" role="dialog" aria-modal="true" aria-label={t("admin.quote_sessions.detail_aria")}>
          <article className="modal-panel quote-sessions-modal">
            <div className="row spread wrap gap-sm">
              <h3 className="modal-title">{t("admin.quote_sessions.detail_title", { count: normalized.length })}</h3>
              <button type="button" className="modal-close-x" onClick={() => setOpen(false)} aria-label={t("common.close")}>
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
                    {modalityLabel(session.modality, language)}
                  </small>
                </article>
              ))}
            </div>

            <div className="row wrap gap-sm top-gap-sm">
              <a className="ghost" href={csvHref} download={downloadName}>
                {t("admin.quote_sessions.download_csv")}
              </a>
              <button type="button" className="ghost" onClick={() => setOpen(false)}>
                {t("common.close")}
              </button>
            </div>
          </article>
        </section>
      ) : null}
    </>
  );
}
