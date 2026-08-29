import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { createGeneratedReportAction, deleteGeneratedReportAction, deleteGeneratedReportsAction } from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import { GeneratedReportsTable } from "../../../components/generated-reports-table";
import { hasAdminPermission } from "../../../lib/admin-access";
import type { AdminLegalEntityOut, GeneratedReportOut, UserOut } from "../../../lib/types";
import { normalizeUiLanguage, uiText } from "../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

type ReportingPageProps = {
  searchParams: SearchParams;
};

type ReportType =
  | "intake-families"
  | "quote-families"
  | "expired-quotes"
  | "overdue-invoices"
  | "reservations"
  | "attendance"
  | "trial-courses"
  | "professor-statements"
  | "communications"
  | "payments"
  | "quotes"
  | "subscriptions"
  | "planning-fill"
  | "check-deposits"
  | "material-forecast"
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
    type: "expired-quotes",
    label: "Devis expires/refuses/annules",
    description: "Liste des devis sortis du cycle commercial sur une plage de dates.",
    filterHint: "Periode de sortie, annee scolaire, famille, enfant, statut de sortie.",
  },
  {
    type: "overdue-invoices",
    label: "Factures echues non payees",
    description: "Factures emises dont l echeance est atteinte et qui ne sont pas marquees payees.",
    filterHint: "Periode d echeance, client, email ou numero de facture.",
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
    type: "trial-courses",
    label: "Essais a venir",
    description: "Tous les essais collectifs et particuliers regroupes par jour, avec eleve, professeur, lieu et creneau.",
    filterHint: "Periode, professeur et lieu. Consultation detaillee et export Excel.",
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
    type: "material-forecast",
    label: "Approvisionnement partitions, cahiers et jeux de notes",
    description: "Partitions, cahiers de solfege et jeux de notes attendus a partir des devis approuves, separes Paris et Bar-le-Duc.",
    filterHint: "Annee scolaire, validations de devis, eleve ou famille. Export Excel avec attendu, stock et a commander.",
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

function reportFilterValue(searchParams: SearchParams, key: string, fallback = ""): string {
  return firstParam(searchParams, key) || fallback;
}

function currentReportingSchoolYear(): string {
  const now = new Date();
  const year = now.getFullYear();
  const startYear = now.getMonth() >= 6 ? year : year - 1;
  return `${startYear}-${startYear + 1}`;
}

function schoolYearOptions(selectedValue: string): string[] {
  const now = new Date();
  const year = now.getFullYear();
  const startYear = now.getMonth() >= 6 ? year : year - 1;
  const values = Array.from({ length: 7 }, (_, index) => {
    const firstYear = startYear - 2 + index;
    return `${firstYear}-${firstYear + 1}`;
  });
  return Array.from(new Set([selectedValue, ...values].filter(Boolean)));
}

function requiresSchoolYear(reportType: ReportType): boolean {
  return ["intake-families", "quote-families", "expired-quotes", "quotes", "subscriptions", "planning-fill", "material-forecast"].includes(reportType);
}

function requiresStatus(reportType: ReportType): boolean {
  return ["intake-families", "quote-families", "expired-quotes", "payments", "quotes", "subscriptions", "check-deposits", "communications"].includes(reportType);
}

const MONTH_OPTIONS = [
  { value: "1", label: "Janvier" },
  { value: "2", label: "Fevrier" },
  { value: "3", label: "Mars" },
  { value: "4", label: "Avril" },
  { value: "5", label: "Mai" },
  { value: "6", label: "Juin" },
  { value: "7", label: "Juillet" },
  { value: "8", label: "Aout" },
  { value: "9", label: "Septembre" },
  { value: "10", label: "Octobre" },
  { value: "11", label: "Novembre" },
  { value: "12", label: "Decembre" },
];

function yearOptions(selectedValue: string): string[] {
  const currentYear = new Date().getFullYear();
  const values = Array.from({ length: 5 }, (_, index) => String(currentYear + index));
  return Array.from(new Set([selectedValue, ...values].filter(Boolean)));
}

function normalizeName(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/gi, "")
    .toLowerCase();
}

function reportSearchToken(definition: ReportDefinition): string {
  if (definition.type === "material-forecast") {
    return normalizeName([
      definition.label,
      definition.description,
      definition.filterHint,
      uiText("en", "admin.reporting.material_forecast_label"),
      uiText("en", "admin.reporting.material_forecast_description"),
      uiText("en", "admin.reporting.material_forecast_filter_hint"),
    ].join(" "));
  }
  return normalizeName(`${definition.label} ${definition.description} ${definition.filterHint}`);
}

function sortedReportDefinitions(query: string): ReportDefinition[] {
  const normalizedQuery = normalizeName(query);
  return REPORT_DEFINITIONS
    .filter((definition) => !normalizedQuery || reportSearchToken(definition).includes(normalizedQuery))
    .slice()
    .sort((left, right) => left.label.localeCompare(right.label, "fr", { sensitivity: "base" }));
}

export default async function AdminReportingPage({ searchParams }: ReportingPageProps): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || !hasAdminPermission(meResult.data, "can_create_and_view_reports")) {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const reportLabel = (definition: ReportDefinition) => definition.type === "material-forecast"
    ? t("admin.reporting.material_forecast_label")
    : definition.label;
  const reportFilterHint = (definition: ReportDefinition) => definition.type === "material-forecast"
    ? t("admin.reporting.material_forecast_filter_hint")
    : definition.filterHint;
  const createMode = firstParam(searchParams, "create") === "1";
  const reportType = selectedReportType(searchParams);
  const reportDefinition = reportType ? REPORT_DEFINITIONS.find((item) => item.type === reportType) || null : null;
  const reportQuery = reportFilterValue(searchParams, "report_q");
  const reportSelectionOptions = sortedReportDefinitions(reportQuery);
  const selectedSchoolYear = reportFilterValue(searchParams, "school_year_label", currentReportingSchoolYear());
  const availableSchoolYears = schoolYearOptions(selectedSchoolYear);
  const selectedDepositMonth = reportFilterValue(searchParams, "month", String(new Date().getMonth() + 1));
  const selectedDepositYear = reportFilterValue(searchParams, "year", String(new Date().getFullYear()));
  const availableDepositYears = yearOptions(selectedDepositYear);

  const generatedReportsResult = await backendRequest<GeneratedReportOut[]>("/api/v1/admin/reports/generated", {}, token);
  const generatedReports = generatedReportsResult.ok ? generatedReportsResult.data : [];
  const legalEntitiesResult = reportType === "check-deposits"
    ? await backendRequest<AdminLegalEntityOut[]>("/api/v1/admin/legal-entities?include_inactive=false", {}, token)
    : null;
  const legalEntities = legalEntitiesResult?.ok ? legalEntitiesResult.data : [];
  const defaultLegalEntity = legalEntities.find((entity) => normalizeName(entity.name) === "pianoacademie") ?? legalEntities[0] ?? null;
  const selectedLegalEntityId = reportFilterValue(searchParams, "legal_entity_id", defaultLegalEntity?.id ?? "");

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
            <GeneratedReportsTable
              reports={generatedReports}
              language={language}
              deleteOneAction={deleteGeneratedReportAction}
              deleteManyAction={deleteGeneratedReportsAction}
              labels={{
                reportType: t("admin.reporting.report_type"),
                createdAt: t("admin.reporting.created_at"),
                format: t("admin.reporting.format"),
                reportPeriod: t("admin.reporting.report_period"),
                downloadPdf: t("admin.reporting.download_pdf"),
              }}
            />
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
                  {reportDefinition ? reportFilterHint(reportDefinition) : "Selectionnez le type de rapport a generer."}
                </p>
              </div>
            </header>

            <section className="card modal-card">
              {!reportDefinition ? (
                <form className="grid cols-2 config-form-grid" method="get" action="/admin/reporting">
                  <input type="hidden" name="create" value="1" />
                  <label className="span-2">
                    Rechercher un rapport
                    <input name="report_q" placeholder="Ex: cheques, factures, professeurs..." defaultValue={reportQuery} autoFocus />
                  </label>
                  <label className="span-2">
                    Type de rapport
                    <select name="type" defaultValue="">
                      <option value="">Selectionner...</option>
                      {reportSelectionOptions.map((definition) => (
                        <option key={definition.type} value={definition.type}>
                          {reportLabel(definition)}
                        </option>
                      ))}
                    </select>
                  </label>
                  {reportSelectionOptions.length === 0 ? (
                    <p className="muted span-2">Aucun rapport ne correspond a cette recherche.</p>
                  ) : null}
                  <div className="form-actions span-2">
                    <Link className="button-link" href="/admin/reporting">
                      Annuler
                    </Link>
                    {reportQuery ? (
                      <Link className="button-link" href={withParams({ create: "1" })}>
                        Reinitialiser
                      </Link>
                    ) : null}
                    <button type="submit">Continuer</button>
                  </div>
                </form>
              ) : reportDefinition.type === "trial-courses" ? (
                <div className="grid cols-2 config-form-grid">
                  <p className="muted span-2">
                    Ouvrez la liste des essais a venir, regroupes par jour, puis filtrez-la par date, professeur ou lieu.
                  </p>
                  <div className="form-actions span-2">
                    <Link className="button-link" href={withParams({ create: "1" })}>Retour</Link>
                    <Link className="button-link" href="/admin/reporting/trial-courses">Ouvrir le reporting</Link>
                  </div>
                </div>
              ) : reportDefinition.type === "check-deposits" ? (
                <form className="grid cols-2 config-form-grid" action={createGeneratedReportAction}>
                  <input type="hidden" name="report_type" value={reportDefinition.type} />
                  <input type="hidden" name="return_to" value="/admin/reporting" />
                  <label>
                    Mois de depot
                    <select name="month" defaultValue={selectedDepositMonth}>
                      {MONTH_OPTIONS.map((month) => (
                        <option key={month.value} value={month.value}>
                          {month.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Annee de depot
                    <select name="year" defaultValue={selectedDepositYear}>
                      {availableDepositYears.map((year) => (
                        <option key={year} value={year}>
                          {year}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Entite legale
                    <select name="legal_entity_id" defaultValue={selectedLegalEntityId} required>
                      {legalEntities.length > 0 ? (
                        legalEntities.map((entity) => (
                          <option key={entity.id} value={entity.id}>
                            {entity.name}
                          </option>
                        ))
                      ) : (
                        <option value="">Aucune entite disponible</option>
                      )}
                    </select>
                  </label>
                  <label>
                    Format
                    <select name="file_format" defaultValue={reportFilterValue(searchParams, "file_format", "pdf")}>
                      <option value="pdf">Fichier PDF</option>
                      <option value="xlsx">Fichier Excel</option>
                    </select>
                  </label>
                  {legalEntitiesResult && !legalEntitiesResult.ok ? (
                    <p className="muted span-2">{t("admin.reporting.error_prefix", { message: legalEntitiesResult.message })}</p>
                  ) : null}
                  <p className="muted span-2">
                    Colonnes exportees : responsable, eleve, date de reception, depot prevu, montant et date de depot banque a completer.
                  </p>
                  <div className="form-actions span-2">
                    <Link className="button-link" href={withParams({ create: "1" })}>
                      Retour
                    </Link>
                    <button type="submit" disabled={!selectedLegalEntityId}>
                      Generer
                    </button>
                  </div>
                </form>
              ) : reportDefinition.type === "material-forecast" ? (
                <form className="grid cols-2 config-form-grid" action={createGeneratedReportAction}>
                  <input type="hidden" name="report_type" value={reportDefinition.type} />
                  <input type="hidden" name="return_to" value="/admin/reporting" />
                  <input type="hidden" name="ui_language" value={language} />
                  <input type="hidden" name="status" value="approved" />
                  <input type="hidden" name="file_format" value="xlsx" />
                  <label>
                    {t("admin.reporting.school_year")}
                    <select name="school_year_label" defaultValue={selectedSchoolYear}>
                      {availableSchoolYears.map((schoolYear) => (
                        <option key={schoolYear} value={schoolYear}>
                          {schoolYear}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    {t("admin.reporting.student_or_prospect")}
                    <input name="q" placeholder={t("admin.reporting.material_forecast_search_placeholder")} defaultValue={reportFilterValue(searchParams, "q")} />
                  </label>
                  <label>
                    {t("admin.reporting.material_forecast_approved_from")}
                    <input type="date" name="received_from" defaultValue={reportFilterValue(searchParams, "received_from")} />
                  </label>
                  <label>
                    {t("admin.reporting.material_forecast_approved_to")}
                    <input type="date" name="received_to" defaultValue={reportFilterValue(searchParams, "received_to")} />
                  </label>
                  <label className="span-2">
                    {t("admin.reporting.material_forecast_note")}
                    <input name="note" placeholder={t("admin.reporting.material_forecast_note_placeholder")} />
                  </label>
                  <p className="muted span-2">
                    {t("admin.reporting.material_forecast_export_help")}
                  </p>
                  <div className="form-actions span-2">
                    <Link className="button-link" href={withParams({ create: "1" })}>
                      {t("common.back")}
                    </Link>
                    <button type="submit">{t("admin.reporting.generate")}</button>
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
                      <select name="school_year_label" defaultValue={selectedSchoolYear}>
                        {availableSchoolYears.map((schoolYear) => (
                          <option key={schoolYear} value={schoolYear}>
                            {schoolYear}
                          </option>
                        ))}
                      </select>
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
                  {reportDefinition.type === "expired-quotes" ? (
                    <label>
                      {t("admin.reporting.status")}
                      <select name="status" defaultValue={reportFilterValue(searchParams, "status")}>
                        <option value="">{t("admin.reporting.all")}</option>
                        <option value="expired">Expire</option>
                        <option value="rejected">Refuse par le client</option>
                        <option value="cancelled">Annule par l admin</option>
                      </select>
                    </label>
                  ) : requiresStatus(reportDefinition.type) ? (
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
