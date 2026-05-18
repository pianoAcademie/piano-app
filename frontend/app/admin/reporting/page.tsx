import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { createGeneratedReportAction, deleteGeneratedReportAction } from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import type {
  GeneratedReportOut,
  IntakeFamilyChildSummary,
  IntakeFamilySummaryRow,
  UserOut,
} from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

type ReportingPageProps = {
  searchParams: SearchParams;
};

type ReportType =
  | "intake-families"
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

const FAMILY_SUMMARY_ROWS: Array<{ key: keyof Pick<IntakeFamilyChildSummary, "course_1" | "course_2" | "solfege" | "masterclass" | "pass_recup">; labelKey: string }> = [
  { key: "course_1", labelKey: "admin.reporting.family_course_1" },
  { key: "course_2", labelKey: "admin.reporting.family_course_2" },
  { key: "solfege", labelKey: "admin.reporting.family_solfege" },
  { key: "masterclass", labelKey: "admin.reporting.family_masterclass" },
  { key: "pass_recup", labelKey: "admin.reporting.family_pass_recup" },
];

function firstParam(searchParams: SearchParams, key: string): string {
  const value = searchParams[key];
  return Array.isArray(value) ? String(value[0] || "") : String(value || "");
}

function selectedReportType(searchParams: SearchParams): ReportType {
  const raw = firstParam(searchParams, "type");
  return REPORT_DEFINITIONS.some((item) => item.type === raw) ? (raw as ReportType) : "intake-families";
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

function reportApiQuery(searchParams: SearchParams): string {
  const params = new URLSearchParams();
  for (const key of ["q", "school_year_label", "received_from", "received_to", "segment", "status", "min_children"]) {
    const value = firstParam(searchParams, key).trim();
    if (value) {
      params.set(key, value);
    }
  }
  params.set("limit", "5000");
  const query = params.toString();
  return query ? `?${query}` : "";
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
  const reportType = selectedReportType(searchParams);
  const reportDefinition = REPORT_DEFINITIONS.find((item) => item.type === reportType) || REPORT_DEFINITIONS[0];
  const printMode = firstParam(searchParams, "print") === "1";
  const reportHrefParams = {
    type: reportType,
    q: firstParam(searchParams, "q"),
    school_year_label: firstParam(searchParams, "school_year_label"),
    received_from: firstParam(searchParams, "received_from"),
    received_to: firstParam(searchParams, "received_to"),
    segment: firstParam(searchParams, "segment"),
    status: firstParam(searchParams, "status"),
    min_children: firstParam(searchParams, "min_children") || "2",
  };

  const intakeFamiliesResult = reportType === "intake-families"
    ? await backendRequest<IntakeFamilySummaryRow[]>(`/api/v1/admin/reports/intake-families${reportApiQuery(searchParams)}`, {}, token)
    : null;
  const generatedReportsResult = await backendRequest<GeneratedReportOut[]>("/api/v1/admin/reports/generated", {}, token);
  const generatedReports = generatedReportsResult.ok ? generatedReportsResult.data : [];
  const intakeFamilies = intakeFamiliesResult?.ok ? intakeFamiliesResult.data : [];
  const generatedAt = new Date().toISOString();

  return (
    <section className="admin-page-grid reporting-shell">
      <style
        dangerouslySetInnerHTML={{
          __html: `
            @media print {
              .admin-sidebar, .admin-header, .no-print { display: none !important; }
              .reporting-shell { display: block !important; padding: 0 !important; }
              .report-print-area { box-shadow: none !important; border: 0 !important; }
              .report-print-area table { break-inside: auto; }
              .report-print-area tr, .report-print-area article { break-inside: avoid; }
            }
          `,
        }}
      />
      {printMode ? (
        <script
          dangerouslySetInnerHTML={{
            __html: "setTimeout(function(){ window.print(); }, 300);",
          }}
        />
      ) : null}

      <section className="card no-print">
        <h2>{t("admin.reporting.title")}</h2>
        <p className="muted">{t("admin.reporting.subtitle")}</p>
      </section>

      <section className="grid cols-3 no-print">
        {REPORT_DEFINITIONS.map((definition) => {
          const active = definition.type === reportType;
          return (
            <article key={definition.type} className={active ? "card selected-card" : "card"}>
              <h3>{definition.label}</h3>
              <p className="muted">{definition.description}</p>
              <p className="muted">{definition.filterHint}</p>
              <Link className="button-link" href={withParams({ type: definition.type, min_children: "2" })}>
                {active ? "Selectionne" : "Choisir"}
              </Link>
            </article>
          );
        })}
      </section>

      <section className="card no-print">
        <h3>{t("admin.reporting.criteria_title")}</h3>
        <p className="muted">{reportDefinition.filterHint}</p>
        <form className="grid cols-4 config-form-grid top-gap-sm" action={createGeneratedReportAction}>
          <input type="hidden" name="report_type" value={reportType} />
          <input type="hidden" name="return_to" value={withParams(reportHrefParams)} />
          <label>
            {t("admin.reporting.period_from")}
            <input type="date" name="received_from" defaultValue={reportFilterValue(searchParams, "received_from")} />
          </label>
          <label>
            {t("admin.reporting.period_to")}
            <input type="date" name="received_to" defaultValue={reportFilterValue(searchParams, "received_to")} />
          </label>
          <label>
            {t("admin.reporting.school_year")}
            <input name="school_year_label" placeholder="2026-2027" defaultValue={reportFilterValue(searchParams, "school_year_label")} />
          </label>
          <label>
            {t("admin.reporting.student_or_prospect")}
            <input name="q" placeholder="Tardieu, Rossillon, email..." defaultValue={reportFilterValue(searchParams, "q")} />
          </label>
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
          <label>
            {t("admin.reporting.status")}
            <select name="status" defaultValue={reportFilterValue(searchParams, "status")}>
              <option value="">{t("admin.reporting.all")}</option>
              <option value="new">New</option>
              <option value="normalized">Normalized</option>
              <option value="matching_required">Matching required</option>
              <option value="ready_draft">Ready draft</option>
              <option value="blocked">Blocked</option>
              <option value="processed">Processed</option>
              <option value="ignored">Ignored</option>
            </select>
          </label>
          <label>
            {t("admin.reporting.min_children")}
            <input type="number" name="min_children" min="1" max="20" defaultValue={reportFilterValue(searchParams, "min_children", "2")} />
          </label>
          <label>
            Note
            <input name="note" placeholder="Note interne facultative" />
          </label>
          <div className="form-actions">
            <Link className="button-link" href={withParams(reportHrefParams)}>
              Visualiser
            </Link>
            <button type="submit">{t("admin.reporting.generate")}</button>
          </div>
        </form>
      </section>

      <section className="card no-print">
        <div className="section-title-row">
          <div>
            <h3>{t("admin.reporting.generated_reports_title")}</h3>
            <p className="muted">{t("admin.reporting.generated_reports_help")}</p>
          </div>
          <span className="status-pill status-info">{t("admin.reporting.rows_count", { count: generatedReports.length })}</span>
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
                            <input type="hidden" name="return_to" value={withParams(reportHrefParams)} />
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

      <section className="card report-print-area">
        <div className="section-title-row">
          <div>
            <h3>{reportDefinition.label}</h3>
            <p className="muted">
              {t("admin.reporting.generated_at", { date: formatDate(generatedAt, language) })}
            </p>
          </div>
          <p className="muted no-print">
            {intakeFamiliesResult?.ok ? t("admin.reporting.rows_count", { count: intakeFamilies.length }) : ""}
          </p>
        </div>
        {reportType === "intake-families" ? (
          intakeFamiliesResult?.ok ? (
            intakeFamilies.length > 0 ? (
              <div className="list top-gap-sm">
                {intakeFamilies.map((family) => (
                  <article key={family.family_key} className="item">
                    <strong>{family.family_label}</strong>
                    <p className="muted">
                      {t("admin.reporting.intake_family_meta", {
                        count: family.intake_count,
                        contact: family.parent_email || family.parent_phone || "-",
                      })}
                    </p>
                    <div className="table-wrap top-gap-sm">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>{t("admin.reporting.family_row")}</th>
                            {family.children.map((child) => (
                              <th key={child.intake_id}>
                                {child.child_name}
                                <br />
                                <span className="muted">{child.source_form_label || child.source_form_id}</span>
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {FAMILY_SUMMARY_ROWS.map((summaryRow) => (
                            <tr key={summaryRow.key}>
                              <th>{t(summaryRow.labelKey)}</th>
                              {family.children.map((child) => (
                                <td key={`${child.intake_id}-${summaryRow.key}`}>{child[summaryRow.key] || "-"}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="muted">{t("admin.reporting.no_intake_family")}</p>
            )
          ) : (
            <p className="muted">{t("admin.reporting.error_prefix", { message: intakeFamiliesResult?.message || t("admin.reporting.unable_to_load") })}</p>
          )
        ) : (
          <p className="muted">{t("admin.reporting.report_not_available")}</p>
        )}
      </section>
    </section>
  );
}
