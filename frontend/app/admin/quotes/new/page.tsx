import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import QuoteWizardForm from "../../../../components/quote-wizard-form";
import { createQuoteDraftAction } from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import { normalizeUiLanguage, uiText } from "../../../../lib/ui-i18n";
import { resolveUiFlashMessage, withUiLanguage } from "../../../../lib/ui-messages";
import type {
  AdminActivityOut,
  AdminCatalogKitOut,
  AdminCatalogProductOut,
  AdminClientOut,
  AdminLegalEntityOut,
  LocationOut,
  UserOut,
} from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

type ProspectOut = {
  id: string;
  first_name: string | null;
  last_name: string | null;
  email: string;
};

type QuoteTypeOut = {
  id: string;
  name: string;
  default_expiry_days: number;
  formula_id: string | null;
  formula_name: string | null;
  school_year_label: string | null;
};

type PricingCatalogOut = {
  id: string;
  name: string;
};

type PaymentPlanOut = {
  id: string;
  name: string;
  payment_method: string;
};

type TermsTemplateOut = {
  id: string;
  name: string;
  language: string;
};

type QuoteTemplateV2Out = {
  id: string;
  name: string;
  language: string;
  is_default: boolean;
};

type SolfegeLevelRuleOut = {
  id: string;
  level_code: string;
  duration_minutes: number;
  allowed_weekdays: number[];
  allowed_time_slots: Array<Record<string, unknown>>;
  location_id: string | null;
  modality: string | null;
};

function readParam(params: SearchParams, key: string): string {
  const raw = params[key];
  if (Array.isArray(raw)) {
    return raw[0] ?? "";
  }
  return raw ?? "";
}

function displayName(firstName: string | null, lastName: string | null, fallback: string): string {
  const value = [firstName, lastName].filter(Boolean).join(" ").trim();
  return value || fallback;
}

export default async function AdminQuoteNewPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
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

  const selectedProspectId = readParam(searchParams, "prospect_id");
  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");
  const okMessage = resolveUiFlashMessage(searchParams, language, "ok") || ok;
  const errorMessage = resolveUiFlashMessage(searchParams, language, "error") || error;
  const quotesListHref = withUiLanguage("/admin/quotes", language);
  const quotesNewHref = withUiLanguage("/admin/quotes/new", language);
  const newProspectHref = withUiLanguage(`/admin/prospects/new?return_to=${encodeURIComponent(quotesNewHref)}`, language);

  const [
    prospectsResult,
    clientsResult,
    quoteTypesResult,
    catalogsResult,
    paymentPlansResult,
    termsTemplatesResult,
    quoteTemplatesResult,
    locationsResult,
    activitiesResult,
    productsResult,
    kitsResult,
    solfegeRulesResult,
    legalEntitiesResult,
  ] = await Promise.all([
    backendRequest<ProspectOut[]>("/api/v1/prospects?limit=1000", {}, token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?limit=5000&include_archived=true", {}, token),
    backendRequest<QuoteTypeOut[]>("/api/v1/quote-types", {}, token),
    backendRequest<PricingCatalogOut[]>("/api/v1/pricing-catalogs", {}, token),
    backendRequest<PaymentPlanOut[]>("/api/v1/payment-plans", {}, token),
    backendRequest<TermsTemplateOut[]>("/api/v1/terms-templates?active_only=true", {}, token),
    backendRequest<QuoteTemplateV2Out[]>("/api/v1/quote-templates-v2?active_only=true", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=false", {}, token),
    backendRequest<AdminActivityOut[]>("/api/v1/admin/activities?include_inactive=true", {}, token),
    backendRequest<AdminCatalogProductOut[]>("/api/v1/admin/config/catalog/products?include_inactive=true", {}, token),
    backendRequest<AdminCatalogKitOut[]>("/api/v1/admin/config/catalog/kits?include_inactive=true", {}, token),
    backendRequest<SolfegeLevelRuleOut[]>("/api/v1/solfege-level-rules", {}, token),
    backendRequest<AdminLegalEntityOut[]>("/api/v1/admin/legal-entities?include_inactive=false", {}, token),
  ]);

  const prospects = prospectsResult.ok ? prospectsResult.data : [];
  const clients = clientsResult.ok ? clientsResult.data : [];
  const quoteTypes = quoteTypesResult.ok ? quoteTypesResult.data : [];
  const catalogs = catalogsResult.ok ? catalogsResult.data : [];
  const paymentPlans = paymentPlansResult.ok ? paymentPlansResult.data : [];
  const termsTemplates = termsTemplatesResult.ok ? termsTemplatesResult.data : [];
  const quoteTemplates = quoteTemplatesResult.ok ? quoteTemplatesResult.data : [];
  const locations = locationsResult.ok ? locationsResult.data : [];
  const activities = activitiesResult.ok ? activitiesResult.data : [];
  const products = productsResult.ok ? productsResult.data : [];
  const kits = kitsResult.ok ? kitsResult.data : [];
  const manualBillingKits = kits.filter((row) => row.active && row.use_in_manual_billing);
  const solfegeRules = solfegeRulesResult.ok ? solfegeRulesResult.data : [];
  const legalEntities = legalEntitiesResult.ok ? legalEntitiesResult.data : [];

  const loadErrors: string[] = [];
  if (!prospectsResult.ok) loadErrors.push(`${t("admin.quote_new.load_prospects")}: ${prospectsResult.message}`);
  if (!clientsResult.ok) loadErrors.push(`${t("admin.quote_new.load_clients")}: ${clientsResult.message}`);
  if (!quoteTypesResult.ok) loadErrors.push(`${t("admin.quote_new.load_quote_types")}: ${quoteTypesResult.message}`);
  if (!catalogsResult.ok) loadErrors.push(`${t("admin.quote_new.load_catalogs")}: ${catalogsResult.message}`);
  if (!paymentPlansResult.ok) loadErrors.push(`${t("admin.quote_new.load_payment_plans")}: ${paymentPlansResult.message}`);
  if (!termsTemplatesResult.ok) loadErrors.push(`${t("admin.quote_new.load_terms_templates")}: ${termsTemplatesResult.message}`);
  if (!quoteTemplatesResult.ok) loadErrors.push(`${t("admin.quote_new.load_quote_templates")}: ${quoteTemplatesResult.message}`);
  if (!locationsResult.ok) loadErrors.push(`${t("admin.quote_new.load_locations")}: ${locationsResult.message}`);
  if (!activitiesResult.ok) loadErrors.push(`${t("admin.quote_new.load_activities")}: ${activitiesResult.message}`);
  if (!productsResult.ok) loadErrors.push(`${t("admin.quote_new.load_products")}: ${productsResult.message}`);
  if (!kitsResult.ok) loadErrors.push(`${t("admin.quote_new.load_kits")}: ${kitsResult.message}`);
  if (!solfegeRulesResult.ok) loadErrors.push(`${t("admin.quote_new.load_solfege")}: ${solfegeRulesResult.message}`);
  if (!legalEntitiesResult.ok) loadErrors.push(`${t("admin.quote_new.load_legal_entities")}: ${legalEntitiesResult.message}`);

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>{t("admin.quote_new.page_title")}</h2>
            <p className="muted">{t("admin.quote_new.page_subtitle")}</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href={newProspectHref}>
              {t("admin.quote_new.new_prospect")}
            </Link>
            <Link className="ghost" href={quotesListHref}>
              {t("admin.quote_new.back_to_quotes")}
            </Link>
          </div>
        </div>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {loadErrors.length > 0 ? (
        <section className="card">
          <h3>{t("admin.quote_new.loading_errors")}</h3>
          <ul className="config-error-list">
            {loadErrors.map((message) => (
              <li key={message} className="flash-err">{message}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <QuoteWizardForm
        returnTo={quotesNewHref}
        newProspectHref={newProspectHref}
        prospects={prospects.map((row) => ({
          id: row.id,
          label: displayName(row.first_name, row.last_name, row.email),
          email: row.email,
        }))}
        clients={clients.map((row) => ({
          id: row.id,
          label: displayName(row.first_name, row.last_name, row.email),
          email: row.email,
        }))}
        quoteTypes={quoteTypes.map((row) => ({
          id: row.id,
          name: row.name,
          default_expiry_days: row.default_expiry_days,
          formula_id: row.formula_id,
          formula_name: row.formula_name,
          school_year_label: row.school_year_label,
        }))}
        catalogs={catalogs.map((row) => ({ id: row.id, name: row.name }))}
        paymentPlans={paymentPlans.map((row) => ({ id: row.id, name: row.name, payment_method: row.payment_method }))}
        termsTemplates={termsTemplates.map((row) => ({ id: row.id, name: row.name, language: row.language }))}
        legalEntities={legalEntities.map((row) => ({ id: row.id, name: row.name }))}
        quoteTemplates={quoteTemplates.map((row) => ({
          id: row.id,
          name: row.name,
          language: row.language,
          is_default: row.is_default,
        }))}
        locations={locations.map((row) => ({ id: row.id, name: row.name }))}
        activities={activities.map((row) => ({
          id: row.id,
          name: row.name,
          code: row.code,
          service_code: row.service_code,
          duration_minutes: row.duration_minutes,
          default_course_rate_ttc: row.default_course_rate_ttc,
        }))}
        products={products.map((row) => ({ id: row.id, title: row.title, price_incl_vat: row.price_incl_vat }))}
        kits={manualBillingKits.map((row) => ({ id: row.id, title: row.title, effective_price_ttc: row.price_effective_incl_vat }))}
        solfegeRules={solfegeRules.map((row) => ({
          id: row.id,
          level_code: row.level_code,
          duration_minutes: row.duration_minutes,
          allowed_weekdays: row.allowed_weekdays,
          allowed_time_slots: row.allowed_time_slots,
          location_id: row.location_id,
          modality: row.modality,
        }))}
        defaultProspectId={selectedProspectId}
        createAction={createQuoteDraftAction}
        uiLanguage={language}
      />
    </section>
  );
}
