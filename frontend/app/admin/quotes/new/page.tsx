import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import QuoteWizardForm from "../../../../components/quote-wizard-form";
import { createQuoteDraftAction } from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import type { AdminActivityOut, AdminCatalogKitOut, AdminCatalogProductOut, AdminClientOut, LocationOut } from "../../../../lib/types";

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

type CgvVersionOut = {
  id: string;
  version_label: string;
};

type QuoteTemplateOut = {
  id: string;
  code: string;
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
    redirect("/login?error=Session%20expiree");
  }

  const selectedProspectId = readParam(searchParams, "prospect_id");
  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");

  const [
    prospectsResult,
    clientsResult,
    quoteTypesResult,
    catalogsResult,
    paymentPlansResult,
    cgvVersionsResult,
    quoteTemplatesResult,
    locationsResult,
    activitiesResult,
    productsResult,
    kitsResult,
    solfegeRulesResult,
  ] = await Promise.all([
    backendRequest<ProspectOut[]>("/api/v1/prospects?limit=1000", {}, token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?limit=800&include_archived=false", {}, token),
    backendRequest<QuoteTypeOut[]>("/api/v1/quote-types", {}, token),
    backendRequest<PricingCatalogOut[]>("/api/v1/pricing-catalogs", {}, token),
    backendRequest<PaymentPlanOut[]>("/api/v1/payment-plans", {}, token),
    backendRequest<CgvVersionOut[]>("/api/v1/cgv-versions", {}, token),
    backendRequest<QuoteTemplateOut[]>("/api/v1/quote-templates?active_only=true", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=false", {}, token),
    backendRequest<AdminActivityOut[]>("/api/v1/admin/activities?include_inactive=true", {}, token),
    backendRequest<AdminCatalogProductOut[]>("/api/v1/admin/config/catalog/products?include_inactive=true", {}, token),
    backendRequest<AdminCatalogKitOut[]>("/api/v1/admin/config/catalog/kits?include_inactive=true", {}, token),
    backendRequest<SolfegeLevelRuleOut[]>("/api/v1/solfege-level-rules", {}, token),
  ]);

  const prospects = prospectsResult.ok ? prospectsResult.data : [];
  const clients = clientsResult.ok ? clientsResult.data : [];
  const quoteTypes = quoteTypesResult.ok ? quoteTypesResult.data : [];
  const catalogs = catalogsResult.ok ? catalogsResult.data : [];
  const paymentPlans = paymentPlansResult.ok ? paymentPlansResult.data : [];
  const cgvVersions = cgvVersionsResult.ok ? cgvVersionsResult.data : [];
  const quoteTemplates = quoteTemplatesResult.ok ? quoteTemplatesResult.data : [];
  const locations = locationsResult.ok ? locationsResult.data : [];
  const activities = activitiesResult.ok ? activitiesResult.data : [];
  const products = productsResult.ok ? productsResult.data : [];
  const kits = kitsResult.ok ? kitsResult.data : [];
  const solfegeRules = solfegeRulesResult.ok ? solfegeRulesResult.data : [];

  const loadErrors: string[] = [];
  if (!prospectsResult.ok) loadErrors.push(`Prospects: ${prospectsResult.message}`);
  if (!clientsResult.ok) loadErrors.push(`Clients: ${clientsResult.message}`);
  if (!quoteTypesResult.ok) loadErrors.push(`Types de devis: ${quoteTypesResult.message}`);
  if (!catalogsResult.ok) loadErrors.push(`Catalogues: ${catalogsResult.message}`);
  if (!paymentPlansResult.ok) loadErrors.push(`Plans de paiement: ${paymentPlansResult.message}`);
  if (!cgvVersionsResult.ok) loadErrors.push(`CGV: ${cgvVersionsResult.message}`);
  if (!quoteTemplatesResult.ok) loadErrors.push(`Templates: ${quoteTemplatesResult.message}`);
  if (!locationsResult.ok) loadErrors.push(`Lieux: ${locationsResult.message}`);
  if (!activitiesResult.ok) loadErrors.push(`Activites: ${activitiesResult.message}`);
  if (!productsResult.ok) loadErrors.push(`Produits: ${productsResult.message}`);
  if (!kitsResult.ok) loadErrors.push(`Kits: ${kitsResult.message}`);
  if (!solfegeRulesResult.ok) loadErrors.push(`Solfege: ${solfegeRulesResult.message}`);

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>Nouveau devis</h2>
            <p className="muted">Creation du devis sans melanger la liste historique ni la gestion des prospects.</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href="/admin/prospects/new?return_to=/admin/quotes/new">
              Nouveau prospect
            </Link>
            <Link className="ghost" href="/admin/quotes">
              Retour liste devis
            </Link>
          </div>
        </div>
      </section>

      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}
      {loadErrors.length > 0 ? (
        <section className="card">
          <h3>Erreurs de chargement</h3>
          <ul className="config-error-list">
            {loadErrors.map((message) => (
              <li key={message} className="flash-err">{message}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <QuoteWizardForm
        returnTo="/admin/quotes/new"
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
        quoteTypes={quoteTypes.map((row) => ({ id: row.id, name: row.name }))}
        catalogs={catalogs.map((row) => ({ id: row.id, name: row.name }))}
        paymentPlans={paymentPlans.map((row) => ({ id: row.id, name: row.name, payment_method: row.payment_method }))}
        cgvVersions={cgvVersions.map((row) => ({ id: row.id, version_label: row.version_label }))}
        quoteTemplates={quoteTemplates.map((row) => ({
          id: row.id,
          code: row.code,
          name: row.name,
          language: row.language,
          is_default: row.is_default,
        }))}
        locations={locations.map((row) => ({ id: row.id, name: row.name }))}
        activities={activities.map((row) => ({
          id: row.id,
          name: row.name,
          duration_minutes: row.duration_minutes,
          default_course_rate_ttc: row.default_course_rate_ttc,
        }))}
        products={products.map((row) => ({ id: row.id, title: row.title, price_incl_vat: row.price_incl_vat }))}
        kits={kits.map((row) => ({ id: row.id, title: row.title, effective_price_ttc: row.price_effective_incl_vat }))}
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
      />
    </section>
  );
}
