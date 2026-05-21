import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { createGeneratedReportAction, deleteGeneratedReportAction } from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import type { GeneratedReportOut, UserOut } from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

type ReportingPageProps = {
  searchParams: SearchParams;
};

type ReportType =
  | "intake-families"
  | "quote-families"
  | "reservations"
  | "attendance"
  | "professor-statements"
  | "communications"
  | "payments"
  | "quotes"
  | "subscriptions"
  | "planning-fill"
  | "check-deposits"
  | "referrals"
  | "teacher-payments";

type ReportDefinition = {
  type: ReportType;
  label: string;
  description: string;
  filterHint: string;
};

const REPORT_DEFINITIONS: ReportDefinition[] = [
  {
    type: "intake-families",
    label: "Synthese intakes par famille",
    description: "Demandes Typeform regroupees par famille, avec une colonne par enfant.",
    filterHint: "Periode, annee scolaire, famille, enfant, segment, statut.",
  },
  {
    type: "quote-families",
    label: "Synthese devis par famille",
    description: "Devis regroupes par famille, avec une colonne par enfant pour comparer avant envoi.",
    filterHint: "Periode de creation, annee scolaire, famille, enfant, statut commercial.",
  },
  {
    type: "reservations",
    label: "Reservations",
    description: "Liste des reservations et prestations planifiees.",
    filterHint: "Periode, lieu, professeur, eleve, statut.",
  },
  {
    type: "attendance",
    label: "Presence eleves",
    description: "Suivi des presents, absences excusees et no-shows.",
    filterHint: "Periode, eleve, professeur, type de cours.",
  },
  {
    type: "professor-statements",
    label: "Releves professeurs",
    description: "Synthese des heures, montants et statuts de paiement professeurs.",
    filterHint: "Mois, professeur, statut, type de cours.",
  },
  {
    type: "communications",
    label: "Communications",
    description: "Emails et SMS envoyes, statuts de livraison et renvois.",
    filterHint: "Periode, canal, type, destinataire, statut.",
  },
  {
    type: "payments",
    label: "Paiements clients",
    description: "Encaissements, echeances, impayes et transactions manuelles.",
    filterHint: "Periode, client, statut, mode de paiement.",
  },
  {
    type: "quotes",
    label: "Devis",
    description: "Suivi commercial des devis, validations et transformations.",
    filterHint: "Periode, statut, formule, lieu, commercial.",
  },
  {
    type: "subscriptions",
    label: "Abonnements",
    description: "Etat des forfaits, consommations, renouvellements et arrets.",
    filterHint: "Periode, client, formule, statut.",
  },
  {
    type: "planning-fill",
    label: "Remplissage planning",
    description: "Taux de remplissage par lieu, jour, creneau et type de cours.",
    filterHint: "Periode, lieu, type de cours, professeur.",
  },
  {
    type: "check-deposits",
    label: "Depots de cheques",
    description: "Lots de cheques, montants et rapprochements.",
    filterHint: "Periode, statut, lot, client.",
  },
  {
    type: "referrals",
    label: "Parrainages",
    description: "Demandes recommandees, parrains et avantages associes.",
    filterHint: "Periode, parrain, filleul, statut.",
  },
  {
    type: "teacher-payments",
    label: "Paiement des salaires",
    description: "Synthese des paiements professeurs et restes a traiter.",
    filterHint: "Mois, professeur, statut de paiement.",
  },
];

function firstParam(searchParams: SearchParams, key: string): string {
  const value = searchParams[key];
  return Array.isArray(value) ? String(value[0] || "") : String(value || "");
}

function selectedReportType(searchParams: SearchParams): ReportType | null {
  const raw = firstParam(searchParams, "type");
  return REPORT_DEFINITIONS.some((item) => item.type === raw) ? (raw as ReportType) : null;
}

function withParams(values: Record<string, string | number | null | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value === null || value === undefined) {
      continue;
    }
    const normalized = String(value).trim();
    if (normalized) {
      params.set(key, normalized);
    }
  }
  const query = params.toString();
  return query ? `/admin/reporting?${query}` : "/admin/reporting";
}

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

function reportFilterValue(searchParams: SearchParams, key: string, fallback = ""): string {
  return firstParam(searchParams, key) || fallback;
}

function requiresSchoolYear(reportType: ReportType): boolean {
  return ["intake-families", "quote-families", "quotes", "subscriptions", "planning-fill"].includes(reportType);
}

function requiresStatus(reportType: ReportType): boolean {
  return ["intake-families", "quote-families", "payments", "quotes", "subscriptions", "check-deposits", "communications"].includes(reportType);
}

export default async function AdminReportingPage({ searchParams }: ReportingPageProps): Promise<JSX.Element> {
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
  const createMode = firstParam(searchParams, "create") === "1";
  const reportType = selectedReportType(searchParams);
  const reportDefinition = reportType ? REPORT_DEFINITIONS.find((item) => item.type === reportType) || null : null;

  const generatedReportsResult = await backendRequest<GeneratedReportOut[]>("/api/v1/admin/reports/generated", {}, token);
  const generatedReports = generatedReportsResult.ok ? generatedReportsResult.data : [];

  return (
    <section className="admin-page-grid reporting-shell">
      <section className="card">
        <div className="section-title-row">
          <div>
            <h2>{t("admin.reporting.title")}</h2>
            <p className="muted">{t("admin.reporting.generated_reports_help")}</p>
          </div>
          <Link className="button-link" href={withParams({ create: "1" })}>
            Creer un rapport
          </Link>
        </div>
      </section>

      <section className="card">
        <div className="section-title-row">
          <div>
            <h3>{t("admin.reporting.generated_reports_title")}</h3>
            <p className="muted">{t("admin.reporting.rows_count", { count: generatedReports.length })}</p>
          </div>
        </div>
        {generatedReportsResult.ok ? (
          generatedReports.length > 0 ? (
            <div className="table-wrap top-gap-sm">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t("admin.reporting.report_type")}</th>
                    <th>{t("admin.reporting.created_at")}</th>
                    <th>{t("admin.reporting.format")}</th>
                    <th>{t("admin.reporting.report_period")}</th>
                    <th>Note</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {generatedReports.map((row) => (
                    <tr key={row.id}>
                      <td>{row.report_label}</td>
                      <td>{formatDate(row.created_at, language)}</td>
                      <td>{row.file_format}</td>
                      <td>{reportPeriod(row, language)}</td>
                      <td>{row.note || "-"}</td>
                      <td>
                        <div className="form-actions">
                          <Link className="button-link" href={`/admin/reporting/generated/${encodeURIComponent(row.id)}/pdf`}>
                            {t("admin.reporting.download_pdf")}
                          </Link>
                          <form action={deleteGeneratedReportAction}>
                            <input type="hidden" name="report_id" value={row.id} />
                            <input type="hidden" name="return_to" value="/admin/reporting" />
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
          ) : (
            <p className="muted">{t("admin.reporting.no_generated_report")}</p>
          )
        ) : (
          <p className="muted">{t("admin.reporting.error_prefix", { message: generatedReportsResult.message })}</p>
        )}
      </section>

      {createMode ? (
        <section className="modal-overlay">
          <article className="modal-panel activity-modal-panel">
            <Link className="modal-close-x" href="/admin/reporting" aria-label={t("common.close")}>
              ×
            </Link>
            <header className="activity-modal-header">
              <div>
                <h2 className="modal-title">Creer un rapport</h2>
                <p className="muted">
                  {reportDefinition ? reportDefinition.filterHint : "Selectionnez le type de rapport a generer."}
                </p>
              </div>
            </header>

            <section className="card modal-card">
              {!reportDefinition ? (
                <form className="grid cols-2 config-form-grid" method="get" action="/admin/reporting">
                  <input type="hidden" name="create" value="1" />
                  <label className="span-2">
                    Type de rapport
                    <select name="type" defaultValue="">
                      <option value="">Selectionner...</option>
                      {REPORT_DEFINITIONS.map((definition) => (
                        <option key={definition.type} value={definition.type}>
                          {definition.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="form-actions span-2">
                    <Link className="button-link" href="/admin/reporting">
                      Annuler
                    </Link>
                    <button type="submit">Continuer</button>
                  </div>
                </form>
              ) : (
                <form className="grid cols-2 config-form-grid" action={createGeneratedReportAction}>
                  <input type="hidden" name="report_type" value={reportDefinition.type} />
                  <input type="hidden" name="return_to" value="/admin/reporting" />
                  <label>
                    {t("admin.reporting.period_from")}
                    <input type="date" name="received_from" defaultValue={reportFilterValue(searchParams, "received_from")} />
                  </label>
                  <label>
                    {t("admin.reporting.period_to")}
                    <input type="date" name="received_to" defaultValue={reportFilterValue(searchParams, "received_to")} />
                  </label>
                  {requiresSchoolYear(reportDefinition.type) ? (
                    <label>
                      {t("admin.reporting.school_year")}
                      <input name="school_year_label" placeholder="2026-2027" defaultValue={reportFilterValue(searchParams, "school_year_label")} />
                    </label>
                  ) : null}
                  <label>
                    {t("admin.reporting.student_or_prospect")}
                    <input name="q" placeholder="Nom, email, professeur..." defaultValue={reportFilterValue(searchParams, "q")} />
                  </label>
                  {reportDefinition.type === "intake-families" ? (
                    <label>
                      {t("admin.reporting.segment")}
                      <select name="segment" defaultValue={reportFilterValue(searchParams, "segment")}>
                        <option value="">{t("admin.reporting.all")}</option>
                        <option value="eveil">Eveil</option>
                        <option value="child">Enfants</option>
                        <option value="teen">Ados</option>
                        <option value="adult">Adultes</option>
                      </select>
                    </label>
                  ) : null}
                  {requiresStatus(reportDefinition.type) ? (
                    <label>
                      {t("admin.reporting.status")}
                      <input name="status" placeholder="Statut" defaultValue={reportFilterValue(searchParams, "status")} />
                    </label>
                  ) : null}
                  {reportDefinition.type === "intake-families" || reportDefinition.type === "quote-families" ? (
                    <label>
                      {t("admin.reporting.min_children")}
                      <input type="number" name="min_children" min="1" max="20" defaultValue={reportFilterValue(searchParams, "min_children", "2")} />
                    </label>
                  ) : null}
                  <label className="span-2">
                    Note
                    <input name="note" placeholder="Note interne facultative" />
                  </label>
                  <div className="form-actions span-2">
                    <Link className="button-link" href={withParams({ create: "1" })}>
                      Retour
                    </Link>
                    <button type="submit">{t("admin.reporting.generate")}</button>
                  </div>
                </form>
              )}
            </section>
          </article>
        </section>
      ) : null}
    </section>
  );
}
