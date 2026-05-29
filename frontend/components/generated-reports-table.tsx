"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import type { GeneratedReportOut } from "../lib/types";
import { localeForUiLanguage, type UiLanguage } from "../lib/ui-i18n";

type ReportAction = (formData: FormData) => void | Promise<void>;

type GeneratedReportsTableProps = {
  reports: GeneratedReportOut[];
  language: UiLanguage;
  deleteOneAction: ReportAction;
  deleteManyAction: ReportAction;
  labels: {
    reportType: string;
    createdAt: string;
    format: string;
    reportPeriod: string;
    downloadPdf: string;
  };
};

const REPORTS_PER_PAGE = 50;

function formatDate(value: string, language: UiLanguage): string {
  return new Date(value).toLocaleString(localeForUiLanguage(language), {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function formatDateOnly(value: string | null, language: UiLanguage): string {
  if (!value) {
    return "-";
  }
  return new Date(`${value}T00:00:00`).toLocaleDateString(localeForUiLanguage(language));
}

function reportPeriod(row: GeneratedReportOut, language: UiLanguage): string {
  if (row.period_start && row.period_end) {
    return `${formatDateOnly(row.period_start, language)} - ${formatDateOnly(row.period_end, language)}`;
  }
  if (row.period_start) {
    return `Depuis ${formatDateOnly(row.period_start, language)}`;
  }
  if (row.period_end) {
    return `Jusqu au ${formatDateOnly(row.period_end, language)}`;
  }
  return "-";
}

export function GeneratedReportsTable({
  reports,
  language,
  deleteOneAction,
  deleteManyAction,
  labels,
}: GeneratedReportsTableProps): JSX.Element {
  const totalPages = Math.max(1, Math.ceil(reports.length / REPORTS_PER_PAGE));
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const selectAllRef = useRef<HTMLInputElement | null>(null);
  const currentPage = Math.min(page, totalPages);
  const startIndex = (currentPage - 1) * REPORTS_PER_PAGE;
  const pageReports = useMemo(
    () => reports.slice(startIndex, startIndex + REPORTS_PER_PAGE),
    [reports, startIndex],
  );
  const allSelected = reports.length > 0 && selectedIds.size === reports.length;
  const partiallySelected = selectedIds.size > 0 && !allSelected;
  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = partiallySelected;
    }
  }, [partiallySelected]);

  const toggleAll = (): void => {
    setSelectedIds((current) => {
      if (current.size === reports.length) {
        return new Set();
      }
      return new Set(reports.map((report) => report.id));
    });
  };

  const toggleReport = (reportId: string): void => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(reportId)) {
        next.delete(reportId);
      } else {
        next.add(reportId);
      }
      return next;
    });
  };

  const preventEmptyBulkDelete = (event: FormEvent<HTMLFormElement>): void => {
    if (selectedIds.size === 0) {
      event.preventDefault();
    }
  };

  return (
    <>
      <form action={deleteManyAction} onSubmit={preventEmptyBulkDelete} className="form-actions top-gap-sm">
        <input type="hidden" name="return_to" value="/admin/reporting" />
        {Array.from(selectedIds).map((reportId) => (
          <input key={reportId} type="hidden" name="report_ids" value={reportId} />
        ))}
        <button className="danger-button" type="submit" disabled={selectedIds.size === 0}>
          Supprimer la selection
        </button>
      </form>
      <div className="table-wrap top-gap-sm">
        <table className="data-table">
          <thead>
            <tr>
              <th>
                <label className="row gap-sm">
                  <input
                    ref={selectAllRef}
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleAll}
                    aria-label="Selectionner tous les rapports"
                  />
                  Selection
                </label>
              </th>
              <th>{labels.reportType}</th>
              <th>{labels.createdAt}</th>
              <th>{labels.format}</th>
              <th>{labels.reportPeriod}</th>
              <th>Note</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {pageReports.map((row) => (
              <tr key={row.id}>
                <td>
                  <input
                    type="checkbox"
                    checked={selectedIds.has(row.id)}
                    onChange={() => toggleReport(row.id)}
                    aria-label={`Selectionner ${row.report_label}`}
                  />
                </td>
                <td>{row.report_label}</td>
                <td>{formatDate(row.created_at, language)}</td>
                <td>{row.file_format}</td>
                <td>{reportPeriod(row, language)}</td>
                <td>{row.note || "-"}</td>
                <td>
                  <div className="form-actions">
                    {row.file_format.toUpperCase() === "PDF" ? (
                      <Link
                        className="button-link"
                        href={`/admin/reporting/generated/${encodeURIComponent(row.id)}/pdf?inline=1`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Visualiser
                      </Link>
                    ) : null}
                    <Link className="button-link" href={`/admin/reporting/generated/${encodeURIComponent(row.id)}/download`}>
                      {row.file_format.toUpperCase() === "XLSX" ? "Telecharger Excel" : labels.downloadPdf}
                    </Link>
                    <form action={deleteOneAction}>
                      <input type="hidden" name="return_to" value="/admin/reporting" />
                      <input type="hidden" name="report_id" value={row.id} />
                      <button className="danger-button" type="submit">
                        Supprimer
                      </button>
                    </form>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row spread wrap clients-pagination top-gap-sm">
        <span>
          {startIndex + 1}-{Math.min(startIndex + pageReports.length, reports.length)} / {reports.length} rapport(s)
        </span>
        <div className="form-actions">
          <button className="button-link" type="button" disabled={currentPage <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>
            Precedent
          </button>
          <span>
            Page {currentPage} / {totalPages}
          </span>
          <button
            className="button-link"
            type="button"
            disabled={currentPage >= totalPages}
            onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
          >
            Suivant
          </button>
        </div>
      </div>
    </>
  );
}
