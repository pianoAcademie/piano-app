import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import ColorHexInput from "../../../components/color-hex-input";
import RichMessageEditor from "../../../components/rich-message-editor";
import {
  createAdminCatalogCategoryAction,
  createAdminCatalogKitAction,
  createAdminCatalogProductAction,
  createAdminActivityAction,
  createAdminCreditTypeAction,
  deleteAdminCatalogCategoryAction,
  deleteAdminCatalogKitAction,
  deleteAdminCatalogProductAction,
  deleteAdminCreditTypeAction,
  disableAdminFormulaAction,
  duplicateAdminFormulaAction,
  updateAdminCatalogCategoryAction,
  updateAdminCatalogKitAction,
  updateAdminCatalogProductAction,
  updateAdminActivityAction,
  updateAdminCreditTypeAction,
  updateAdminConfigAccountAction,
  updateAdminConfigMessagingSettingsAction,
  updateAdminConfigInvoiceNumberingAction,
  updateAdminConfigInvoiceTemplateAction,
  updateAdminConfigProfessorDefaultGridAction,
  updateAdminConfigProductCategoriesAction,
  updateAdminConfigPaymentMethodsAction,
  updateAdminConfigPaymentProviderAction,
  updateAdminConfigSubscriptionsAction,
  deleteAdminConfigMessagingTemplateAction,
  resetAdminConfigPredefinedMessagingTemplateAction,
  saveAdminConfigMessagingTemplateAction,
} from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import type {
  AdminActivityOut,
  AdminCatalogCategoryOut,
  AdminCatalogKitOut,
  AdminCatalogProductOut,
  AdminCreditTypeOut,
  AdminConfigAccountOut,
  AdminFormulaOut,
  AdminMessagingSettingsOut,
  AdminMessagingTemplateOut,
  AdminInvoiceTemplateOut,
  AdminInvoiceNumberingOut,
  AdminPaymentProviderOut,
  AdminPaymentMethodsOut,
  AdminProductCategoriesOut,
  AdminProfessorDefaultGridOut,
  AdminSubscriptionSettingsOut,
} from "../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

type ConfigMainSection =
  | "params"
  | "formulas"
  | "activities"
  | "promo"
  | "products"
  | "payment-rules"
  | "integrations"
  | "purchase-link"
  | "credit-types";

type ConfigSection =
  | "params-account"
  | "params-subscriptions"
  | "params-payments"
  | "params-professor-default-grid"
  | "params-messaging"
  | "formulas"
  | "activities"
  | "promo"
  | "products"
  | "payment-rules"
  | "integrations"
  | "purchase-link"
  | "credit-types";

type MainNavItem = {
  key: ConfigMainSection;
  label: string;
  section: ConfigSection;
};

type SubNavItem = {
  key:
    | "params-account"
    | "params-subscriptions"
    | "params-payments"
    | "params-professor-default-grid"
    | "params-messaging";
  label: string;
};

const MAIN_NAV_ITEMS: MainNavItem[] = [
  { key: "params", label: "Parametres", section: "params-account" },
  { key: "formulas", label: "Les formules", section: "formulas" },
  { key: "activities", label: "Activites", section: "activities" },
  { key: "promo", label: "Code promo", section: "promo" },
  { key: "payment-rules", label: "Regles de paiement", section: "payment-rules" },
  { key: "integrations", label: "Integration", section: "integrations" },
  { key: "purchase-link", label: "Creer un lien d'achat", section: "purchase-link" },
  { key: "credit-types", label: "Types de credit", section: "credit-types" },
];

const PARAMS_SUBNAV_ITEMS: SubNavItem[] = [
  { key: "params-account", label: "Informations du compte" },
  { key: "params-subscriptions", label: "Parametrage des abonnements" },
  { key: "params-professor-default-grid", label: "Grille salaire professeurs" },
  { key: "params-payments", label: "Moyens de paiement" },
  { key: "params-messaging", label: "Messagerie" },
];

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function parseSection(raw: string): ConfigSection {
  const value = raw.trim();
  if (value === "params-client-password-email") {
    return "params-messaging";
  }
  if (
    value === "params-account" ||
    value === "params-subscriptions" ||
    value === "params-payments" ||
    value === "params-professor-default-grid" ||
    value === "params-messaging" ||
    value === "formulas" ||
    value === "activities" ||
    value === "promo" ||
    value === "products" ||
    value === "payment-rules" ||
    value === "integrations" ||
    value === "purchase-link" ||
    value === "credit-types"
  ) {
    return value;
  }
  return "params-account";
}

function toMainSection(section: ConfigSection): ConfigMainSection {
  switch (section) {
    case "params-account":
    case "params-subscriptions":
    case "params-payments":
    case "params-professor-default-grid":
    case "params-messaging":
      return "params";
    case "formulas":
    case "activities":
    case "promo":
    case "products":
    case "payment-rules":
    case "integrations":
    case "purchase-link":
    case "credit-types":
      return section;
  }
}

function buildConfigHref(section: ConfigSection, params: Record<string, string> = {}): string {
  const sp = new URLSearchParams();
  sp.set("section", section);
  for (const [key, value] of Object.entries(params)) {
    if (!value) {
      continue;
    }
    sp.set(key, value);
  }
  return `/admin/config?${sp.toString()}`;
}

function restrictionPeriodLabel(period: "DAY" | "WEEK" | "MONTH" | "ROLLING_MONTH" | "SEMESTER"): string {
  if (period === "DAY") {
    return "jour";
  }
  if (period === "WEEK") {
    return "semaine";
  }
  if (period === "MONTH") {
    return "mois";
  }
  if (period === "ROLLING_MONTH") {
    return "mois glissant";
  }
  return "semestre";
}

function formulaKindLabel(kind: "PACK" | "SUBSCRIPTION" | "FORFAIT"): string {
  if (kind === "PACK") {
    return "Carnet";
  }
  if (kind === "FORFAIT") {
    return "Forfait";
  }
  return "Abonnement";
}

function formulaPriceModeLabel(mode: "HT" | "TTC"): string {
  return mode === "TTC" ? "TTC" : "HT";
}

function activityModeLabel(mode: string): string {
  const normalized = mode.toUpperCase();
  if (normalized === "ONLINE") {
    return "En ligne";
  }
  if (normalized === "ONSITE") {
    return "Presentiel";
  }
  return "Tous";
}

function contractModeLabel(mode: string): string {
  const normalized = mode.trim().toUpperCase();
  if (normalized === "PRESENTIEL") {
    return "Presentiel";
  }
  if (normalized === "EN_LIGNE") {
    return "En ligne";
  }
  return "Autre";
}

function encodeHeadcountRules(
  rules: Array<{ min_students: number; max_students: number | null; hourly_rate: string }>,
): string {
  return rules
    .map((rule) => {
      const range = rule.max_students === null ? `${rule.min_students}+` : `${rule.min_students}-${rule.max_students}`;
      return `${range}:${rule.hourly_rate}`;
    })
    .join("; ");
}

function formatMoney(amountRaw: string | null, currency: string | null): string {
  if (!amountRaw) {
    return "-";
  }

  const amount = Number(amountRaw);
  const normalizedCurrency = currency || "EUR";
  if (!Number.isFinite(amount)) {
    return `${amountRaw} ${normalizedCurrency}`;
  }

  try {
    return new Intl.NumberFormat("fr-FR", {
      style: "currency",
      currency: normalizedCurrency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${normalizedCurrency}`;
  }
}

function yesNoLabel(value: boolean): string {
  return value ? "Oui" : "Non";
}

function catalogRequestStatusLabel(status: string): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "PROCESSING") {
    return "En cours";
  }
  if (normalized === "REJECTED") {
    return "Refusee";
  }
  if (normalized === "INVOICE_TO_SEND") {
    return "Facture a envoyer";
  }
  if (normalized === "TO_DELIVER") {
    return "A remettre";
  }
  if (normalized === "DELIVERED") {
    return "Remis";
  }
  return normalized || "-";
}

function catalogRequestSourceLabel(source: string): string {
  const normalized = source.trim().toUpperCase();
  if (normalized === "PROFESSOR") {
    return "Professeur";
  }
  if (normalized === "ADMIN") {
    return "Administration";
  }
  return normalized || "-";
}

function dateInputValue(value: string | null): string {
  if (!value) {
    return "";
  }
  return value.slice(0, 10);
}

export default async function AdminConfigPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const params = searchParams ?? {};
  const requestedSection = readParam(params, "section").trim();
  const section = parseSection(requestedSection);
  if (section === "products") {
    redirect("/admin/products");
  }
  const mainSection = toMainSection(section);
  const showInactiveFormulas = readParam(params, "show_inactive") === "1";

  const formulasEndpoint = showInactiveFormulas
    ? "/api/v1/admin/formulas?include_inactive=true"
    : "/api/v1/admin/formulas";

  const [
    accountResult,
    subscriptionsResult,
    paymentMethodsResult,
    productCategoriesResult,
    paymentProviderResult,
    messagingSettingsResult,
    invoiceTemplateResult,
    invoiceNumberingResult,
    emailPredefinedTemplatesResult,
    smsPredefinedTemplatesResult,
    customTemplatesResult,
    defaultProfessorGridResult,
    formulasResult,
    activitiesResult,
    creditTypesResult,
    catalogCategoriesResult,
    catalogProductsResult,
    catalogKitsResult,
  ] =
    await Promise.all([
    backendRequest<AdminConfigAccountOut>("/api/v1/admin/config/account", {}, token),
    backendRequest<AdminSubscriptionSettingsOut>("/api/v1/admin/config/subscriptions", {}, token),
    backendRequest<AdminPaymentMethodsOut>("/api/v1/admin/config/payment-methods", {}, token),
    backendRequest<AdminProductCategoriesOut>("/api/v1/admin/config/product-categories", {}, token),
    backendRequest<AdminPaymentProviderOut>("/api/v1/admin/config/payment-provider", {}, token),
    backendRequest<AdminMessagingSettingsOut>("/api/v1/admin/config/messaging-settings", {}, token),
    backendRequest<AdminInvoiceTemplateOut>("/api/v1/admin/config/invoice-template", {}, token),
    backendRequest<AdminInvoiceNumberingOut>("/api/v1/admin/config/invoice-numbering", {}, token),
    backendRequest<AdminMessagingTemplateOut[]>(
      "/api/v1/admin/config/messaging-templates?channel=EMAIL&kind=PREDEFINED",
      {},
      token,
    ),
    backendRequest<AdminMessagingTemplateOut[]>(
      "/api/v1/admin/config/messaging-templates?channel=SMS&kind=PREDEFINED",
      {},
      token,
    ),
    backendRequest<AdminMessagingTemplateOut[]>("/api/v1/admin/config/messaging-templates?kind=CUSTOM", {}, token),
    backendRequest<AdminProfessorDefaultGridOut>("/api/v1/admin/config/professor-default-grid", {}, token),
    backendRequest<AdminFormulaOut[]>(formulasEndpoint, {}, token),
    backendRequest<AdminActivityOut[]>("/api/v1/admin/activities?include_inactive=true", {}, token),
    backendRequest<AdminCreditTypeOut[]>("/api/v1/admin/credit-types?include_inactive=true", {}, token),
    backendRequest<AdminCatalogCategoryOut[]>("/api/v1/admin/config/catalog/categories?include_inactive=true", {}, token),
    backendRequest<AdminCatalogProductOut[]>("/api/v1/admin/config/catalog/products?include_inactive=true", {}, token),
    backendRequest<AdminCatalogKitOut[]>("/api/v1/admin/config/catalog/kits?include_inactive=true", {}, token),
  ]);

  const loadErrors: string[] = [];

  const account = accountResult.ok
    ? accountResult.data
    : (() => {
        loadErrors.push(`Informations du compte: ${accountResult.message}`);
        return null;
      })();

  const subscriptions = subscriptionsResult.ok
    ? subscriptionsResult.data
    : (() => {
        loadErrors.push(`Parametrage des abonnements: ${subscriptionsResult.message}`);
        return null;
      })();

  const paymentMethods = paymentMethodsResult.ok
    ? paymentMethodsResult.data.methods
    : (() => {
        loadErrors.push(`Moyens de paiement: ${paymentMethodsResult.message}`);
      return [] as AdminPaymentMethodsOut["methods"];
    })();

  const paymentProvider = paymentProviderResult.ok
    ? paymentProviderResult.data
    : (() => {
        loadErrors.push(`PSP: ${paymentProviderResult.message}`);
        return null;
      })();
  const productCategories = productCategoriesResult.ok
    ? productCategoriesResult.data
    : (() => {
        loadErrors.push(`Produits: ${productCategoriesResult.message}`);
        return { categories: [], updated_at: null } as AdminProductCategoriesOut;
      })();
  const messagingSettings = messagingSettingsResult.ok
    ? messagingSettingsResult.data
    : (() => {
        loadErrors.push(`Messagerie: ${messagingSettingsResult.message}`);
        return null;
      })();
  const invoiceTemplate = invoiceTemplateResult.ok
    ? invoiceTemplateResult.data
    : (() => {
        loadErrors.push(`Modele facture: ${invoiceTemplateResult.message}`);
        return null;
      })();
  const invoiceNumbering = invoiceNumberingResult.ok
    ? invoiceNumberingResult.data
    : (() => {
        loadErrors.push(`Numero facture: ${invoiceNumberingResult.message}`);
        return null;
      })();
  const emailPredefinedTemplates = emailPredefinedTemplatesResult.ok
    ? emailPredefinedTemplatesResult.data
    : (() => {
        loadErrors.push(`Modeles email predefinis: ${emailPredefinedTemplatesResult.message}`);
        return [] as AdminMessagingTemplateOut[];
      })();
  const smsPredefinedTemplates = smsPredefinedTemplatesResult.ok
    ? smsPredefinedTemplatesResult.data
    : (() => {
        loadErrors.push(`Modeles SMS predefinis: ${smsPredefinedTemplatesResult.message}`);
        return [] as AdminMessagingTemplateOut[];
      })();
  const customTemplates = customTemplatesResult.ok
    ? customTemplatesResult.data
    : (() => {
        loadErrors.push(`Modeles personnalises: ${customTemplatesResult.message}`);
        return [] as AdminMessagingTemplateOut[];
      })();
  const defaultProfessorGrid = defaultProfessorGridResult.ok
    ? defaultProfessorGridResult.data
    : (() => {
        loadErrors.push(`Grille salaire professeurs: ${defaultProfessorGridResult.message}`);
        return { lines: [], updated_at: null } as AdminProfessorDefaultGridOut;
      })();

  const formulas = formulasResult.ok
    ? formulasResult.data
    : (() => {
        loadErrors.push(`Formules: ${formulasResult.message}`);
        return [] as AdminFormulaOut[];
      })();

  const activities = activitiesResult.ok
    ? activitiesResult.data
    : (() => {
        loadErrors.push(`Activites: ${activitiesResult.message}`);
        return [] as AdminActivityOut[];
      })();
  const creditTypes = creditTypesResult.ok
    ? creditTypesResult.data
    : (() => {
        loadErrors.push(`Types de credit: ${creditTypesResult.message}`);
        return [] as AdminCreditTypeOut[];
      })();
  const catalogCategories = catalogCategoriesResult.ok
    ? catalogCategoriesResult.data
    : (() => {
        loadErrors.push(`Catalogue categories: ${catalogCategoriesResult.message}`);
        return [] as AdminCatalogCategoryOut[];
      })();
  const catalogProducts = catalogProductsResult.ok
    ? catalogProductsResult.data
    : (() => {
        loadErrors.push(`Catalogue produits: ${catalogProductsResult.message}`);
        return [] as AdminCatalogProductOut[];
      })();
  const catalogKits = catalogKitsResult.ok
    ? catalogKitsResult.data
    : (() => {
        loadErrors.push(`Catalogue kits: ${catalogKitsResult.message}`);
        return [] as AdminCatalogKitOut[];
      })();
  const activeCatalogCategories = catalogCategories.filter((row) => row.active);
  const activeCatalogProducts = catalogProducts.filter((row) => row.active);

  const accountAllowedCurrencies = account?.allowed_currencies?.length ? account.allowed_currencies : ["EUR", "USD"];
  const accountDefaultCurrency =
    account && accountAllowedCurrencies.includes(account.default_currency) ? account.default_currency : accountAllowedCurrencies[0] ?? "EUR";
  const createActivityModalOpen = readParam(params, "new_activity") === "1";
  const selectedActivityId = readParam(params, "activity_id");
  const selectedActivity = activities.find((activity) => activity.id === selectedActivityId) ?? null;
  const createCreditTypeModalOpen = readParam(params, "new_credit_type") === "1";
  const selectedCreditTypeId = readParam(params, "credit_type_id");
  const selectedCreditType = creditTypes.find((creditType) => creditType.id === selectedCreditTypeId) ?? null;
  const activeCreditTypes = creditTypes.filter((creditType) => creditType.active);
  const messagingModalMode = readParam(params, "messaging_modal");
  const newCustomTemplateChannelRaw = readParam(params, "new_template_channel").toUpperCase();
  const newCustomTemplateChannel = newCustomTemplateChannelRaw === "SMS" ? "SMS" : "EMAIL";
  const editingTemplateKind = readParam(params, "template_kind").toUpperCase();
  const editingTemplateCode = readParam(params, "template_code").toUpperCase();
  const editingTemplateId = readParam(params, "template_id");
  const editingTemplate =
    editingTemplateKind === "PREDEFINED"
      ? [...emailPredefinedTemplates, ...smsPredefinedTemplates].find((row) => row.code === editingTemplateCode) ?? null
      : editingTemplateKind === "CUSTOM"
      ? customTemplates.find((row) => row.id === editingTemplateId) ?? null
      : null;
  const createCustomMessagingTemplate = messagingModalMode === "new-custom";
  const customEmailTemplates = customTemplates.filter((template) => template.channel === "EMAIL");
  const customSmsTemplates = customTemplates.filter((template) => template.channel === "SMS");

  const paymentMethodLabelByCode = new Map(paymentMethods.map((method) => [method.code, method.label]));
  const activityById = new Map(activities.map((activity) => [activity.id, activity]));
  const defaultGridLineSlots = 16;

  const okMessage = readParam(params, "ok");
  const errorMessage = readParam(params, "error");

  const formulaBaseParams: Record<string, string> = {};
  if (showInactiveFormulas) {
    formulaBaseParams.show_inactive = "1";
  }
  const formulasListPath = buildConfigHref("formulas", formulaBaseParams);
  const messagingListPath = buildConfigHref("params-messaging");

  const placeholderTitleBySection: Record<
    Exclude<
      ConfigSection,
      | "params-account"
      | "params-subscriptions"
      | "params-payments"
      | "params-professor-default-grid"
      | "params-messaging"
      | "formulas"
      | "activities"
      | "credit-types"
    >,
    string
  > = {
    promo: "Code promo",
    products: "Les produits",
    "payment-rules": "Regles de paiement",
    integrations: "Integration",
    "purchase-link": "Creer un lien d'achat",
  };

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h2>Configuration</h2>
        <p className="muted">Parametres compte, abonnements, paiements et formules commerciales.</p>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {loadErrors.length > 0 ? (
        <section className="card">
          <h3>Erreurs de chargement</h3>
          <ul className="config-error-list">
            {loadErrors.map((message) => (
              <li key={message} className="flash-err">
                {message}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="config-layout">
        <aside className="card config-nav-panel">
          <nav className="config-main-nav">
            {MAIN_NAV_ITEMS.map((item) => {
              const isActive = mainSection === item.key;
              const href = item.key === "formulas" ? buildConfigHref(item.section, formulaBaseParams) : buildConfigHref(item.section);

              return (
                <Link key={item.key} className={`config-main-link ${isActive ? "active" : ""}`} href={href}>
                  {item.label}
                </Link>
              );
            })}
          </nav>

          {mainSection === "params" ? (
            <nav className="config-sub-nav">
              {PARAMS_SUBNAV_ITEMS.map((item) => (
                <Link
                  key={item.key}
                  className={`config-sub-link ${section === item.key ? "active" : ""}`}
                  href={buildConfigHref(item.key)}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          ) : null}
        </aside>

        <div className="config-main-content">
          {section === "params-account" ? (
            <section className="card">
              <h3>Informations du compte</h3>
              {!account ? (
                <p className="muted">Impossible de charger les informations du compte.</p>
              ) : (
                <form action={updateAdminConfigAccountAction} className="grid cols-2 config-form-grid" encType="multipart/form-data">
                  <label>
                    Prenom
                    <input type="text" name="contact_first_name" defaultValue={account.contact_first_name} maxLength={100} />
                  </label>
                  <label>
                    Nom
                    <input type="text" name="contact_last_name" defaultValue={account.contact_last_name} maxLength={100} />
                  </label>

                  <label>
                    Email
                    <input type="email" name="contact_email" defaultValue={account.contact_email} maxLength={255} />
                  </label>
                  <label>
                    Telephone
                    <input type="text" name="contact_phone" defaultValue={account.contact_phone} maxLength={40} />
                  </label>

                  <label>
                    Societe
                    <input type="text" name="company_name" defaultValue={account.company_name} maxLength={255} />
                  </label>
                  <label>
                    Nom du club
                    <input type="text" name="club_name" defaultValue={account.club_name} maxLength={255} />
                  </label>

                  <label>
                    SIRET
                    <input type="text" name="siret" defaultValue={account.siret} maxLength={30} />
                  </label>
                  <label>
                    TVA intracommunautaire
                    <input type="text" name="vat_number" defaultValue={account.vat_number} maxLength={50} />
                  </label>

                  <label>
                    Taux TVA par defaut
                    <input type="text" name="vat_default_rate" defaultValue={account.vat_default_rate} maxLength={20} />
                  </label>
                  <label>
                    Site web
                    <input type="text" name="website" defaultValue={account.website} maxLength={255} />
                  </label>

                  <input type="hidden" name="logo_data_url" value={account.logo_data_url || ""} />
                  <label className="span-2">
                    Logo societe (JPEG, max 1 Mo)
                    <input type="file" name="logo_file" accept="image/jpeg,image/jpg" />
                    {account.logo_data_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={account.logo_data_url}
                        alt="Logo societe"
                        style={{ marginTop: 10, maxHeight: 64, width: "auto", border: "1px solid #d8c8ab", borderRadius: 8, padding: 6, background: "#fff" }}
                      />
                    ) : (
                      <small className="muted">Aucun logo configure.</small>
                    )}
                  </label>
                  <label className="checkline span-2">
                    <input type="checkbox" name="clear_logo" value="on" />
                    Supprimer le logo actuel
                  </label>

                  <label className="span-2">
                    Adresse
                    <input type="text" name="address_line" defaultValue={account.address_line} maxLength={255} />
                  </label>

                  <label>
                    Code postal
                    <input type="text" name="postal_code" defaultValue={account.postal_code} maxLength={20} />
                  </label>
                  <label>
                    Ville
                    <input type="text" name="city" defaultValue={account.city} maxLength={120} />
                  </label>

                  <label className="span-2">
                    Pays
                    <input type="text" name="country" defaultValue={account.country} maxLength={120} />
                  </label>

                  <fieldset className="span-2 config-currency-fieldset">
                    <legend>Devises autorisees</legend>
                    <div className="row config-currency-checks">
                      {(["EUR", "USD"] as const).map((code) => (
                        <label key={code} className="checkline">
                          <input
                            type="checkbox"
                            name="allowed_currencies"
                            value={code}
                            defaultChecked={accountAllowedCurrencies.includes(code)}
                          />
                          {code}
                        </label>
                      ))}
                    </div>

                    <label>
                      Devise par defaut
                      <select name="default_currency" defaultValue={accountDefaultCurrency}>
                        {accountAllowedCurrencies.map((code) => (
                          <option key={code} value={code}>
                            {code}
                          </option>
                        ))}
                      </select>
                    </label>
                  </fieldset>

                  <label className="span-2">
                    Conditions generales de vente
                    <textarea name="legal_terms" defaultValue={account.legal_terms} rows={8} />
                  </label>

                  <div className="row span-2">
                    <button type="submit">Enregistrer</button>
                  </div>
                </form>
              )}
            </section>
          ) : null}

          {section === "params-subscriptions" ? (
            <section className="card">
              <h3>Parametrage des abonnements</h3>
              {!subscriptions ? (
                <p className="muted">Impossible de charger ce parametrage.</p>
              ) : (
                <form action={updateAdminConfigSubscriptionsAction} className="grid cols-2 config-form-grid">
                  <label>
                    Date de prelevement autorisee (1-28)
                    <input
                      type="number"
                      name="direct_debit_day"
                      min={1}
                      max={28}
                      defaultValue={subscriptions.direct_debit_day === null ? "" : String(subscriptions.direct_debit_day)}
                    />
                  </label>

                  <div className="config-note-box">
                    <strong>Note</strong>
                    <p className="muted">Ces options impactent le comportement global des abonnements.</p>
                  </div>

                  <label className="checkline span-2">
                    <input type="checkbox" name="allow_card_subscriptions" defaultChecked={subscriptions.allow_card_subscriptions} />
                    Autoriser les abonnements par carte bancaire
                  </label>
                  <label className="checkline span-2">
                    <input type="checkbox" name="add_contract_signature" defaultChecked={subscriptions.add_contract_signature} />
                    Ajouter la signature du contrat
                  </label>
                  <label className="checkline span-2">
                    <input
                      type="checkbox"
                      name="close_expired_subscriptions"
                      defaultChecked={subscriptions.close_expired_subscriptions}
                    />
                    Fermer les abonnements expires automatiquement
                  </label>
                  <label className="checkline span-2">
                    <input
                      type="checkbox"
                      name="allow_promotional_start_period"
                      defaultChecked={subscriptions.allow_promotional_start_period}
                    />
                    Autoriser une periode promotionnelle en debut d'abonnement
                  </label>
                  <label className="checkline span-2">
                    <input type="checkbox" name="allow_prorata_card" defaultChecked={subscriptions.allow_prorata_card} />
                    Autoriser le prorata sur CB
                  </label>
                  <label className="checkline span-2">
                    <input type="checkbox" name="allow_prorata_sepa" defaultChecked={subscriptions.allow_prorata_sepa} />
                    Autoriser le prorata sur SEPA
                  </label>
                  <label className="checkline span-2">
                    <input
                      type="checkbox"
                      name="online_resiliation_enabled"
                      defaultChecked={subscriptions.online_resiliation_enabled}
                    />
                    Resiliation en ligne active
                  </label>

                  <div className="row span-2">
                    <button type="submit">Enregistrer</button>
                  </div>
                </form>
              )}
            </section>
          ) : null}

          {section === "params-professor-default-grid" ? (
            <section className="card">
              <h3>Grille salariale par defaut (professeurs)</h3>
              <p className="muted">
                Cette grille s applique a tous les professeurs pour le calcul depuis le planning si aucune grille specifique collaborateur
                n est definie. Les parametrages au niveau du professeur restent prioritaires.
              </p>
              {defaultProfessorGrid.updated_at ? (
                <p className="muted">Derniere mise a jour: {new Date(defaultProfessorGrid.updated_at).toLocaleString("fr-FR")}</p>
              ) : null}

              <form action={updateAdminConfigProfessorDefaultGridAction} className="grid">
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Activite (planning)</th>
                        <th>Mode (derive)</th>
                        <th>Duree ref (min)</th>
                        <th>Taux default</th>
                        <th>Regles effectif</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Array.from({ length: defaultGridLineSlots }).map((_, index) => {
                        const line = defaultProfessorGrid.lines[index];
                        const activity = line ? activityById.get(line.course_type_id) : undefined;
                        const modeLabel = activity
                          ? contractModeLabel(activity.mode === "ONLINE" ? "EN_LIGNE" : activity.mode === "ONSITE" ? "PRESENTIEL" : "AUTRE")
                          : (line ? contractModeLabel(line.mode) : "-");
                        const duration = activity?.duration_minutes ?? line?.reference_duration_minutes ?? null;

                        return (
                          <tr key={`default-grid-line-${index}`}>
                            <td>
                              <select name={`line_course_type_id_${index}`} defaultValue={line?.course_type_id ?? ""}>
                                <option value="">Selectionner une activite</option>
                                {activities.map((activityRow) => (
                                  <option key={`default-grid-activity-${index}-${activityRow.id}`} value={activityRow.id}>
                                    {activityRow.name}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td>
                              <span className="muted">{modeLabel}</span>
                            </td>
                            <td>
                              <span className="muted">{duration ?? "-"}</span>
                            </td>
                            <td>
                              <input
                                type="number"
                                name={`line_default_rate_${index}`}
                                min="0"
                                step="0.01"
                                defaultValue={line?.default_hourly_rate ?? ""}
                                placeholder="ex: 35.00"
                              />
                            </td>
                            <td>
                              <input
                                type="text"
                                name={`line_rules_${index}`}
                                defaultValue={line ? encodeHeadcountRules(line.rules) : ""}
                                placeholder="0-3:35; 4-8:42; 9+:50"
                              />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <p className="muted">
                  Format regles effectif: <code>0-3:35; 4-8:42; 9+:50</code>. Si aucune regle ne matche, le taux default est utilise.
                </p>

                <div className="row">
                  <button type="submit">Enregistrer la grille par defaut</button>
                </div>
              </form>
            </section>
          ) : null}

          {section === "params-payments" ? (
            <>
              <section className="card">
                <h3>PSP et cles API</h3>
                {!paymentProvider ? (
                  <p className="muted">Impossible de charger la configuration PSP.</p>
                ) : (
                  <form action={updateAdminConfigPaymentProviderAction} className="grid cols-2 config-form-grid">
                    <label>
                      Prestataire de paiement
                      <select name="provider" defaultValue={paymentProvider.provider}>
                        <option value="PAYPLUG">Payplug</option>
                        <option value="MOLLIE">Mollie</option>
                      </select>
                    </label>
                    <label>
                      Environnement
                      <select name="mode" defaultValue={paymentProvider.mode}>
                        <option value="TEST">Test</option>
                        <option value="LIVE">Production</option>
                      </select>
                    </label>

                    <label className="span-2">
                      Payplug - cle test (sk_test_...)
                      <input type="password" name="payplug_test_secret" placeholder="Laisser vide pour conserver l'existante" autoComplete="new-password" />
                      <small className="muted">
                        Actuelle: {paymentProvider.payplug_test_secret_masked || "Non configuree"}
                      </small>
                    </label>

                    <label className="span-2">
                      Payplug - cle live (sk_live_...)
                      <input type="password" name="payplug_live_secret" placeholder="Laisser vide pour conserver l'existante" autoComplete="new-password" />
                      <small className="muted">
                        Actuelle: {paymentProvider.payplug_live_secret_masked || "Non configuree"}
                      </small>
                    </label>

                    <label className="span-2">
                      Mollie - cle test (test_...)
                      <input type="password" name="mollie_test_api_key" placeholder="Laisser vide pour conserver l'existante" autoComplete="new-password" />
                      <small className="muted">
                        Actuelle: {paymentProvider.mollie_test_api_key_masked || "Non configuree"}
                      </small>
                    </label>

                    <label className="span-2">
                      Mollie - cle live (live_...)
                      <input type="password" name="mollie_live_api_key" placeholder="Laisser vide pour conserver l'existante" autoComplete="new-password" />
                      <small className="muted">
                        Actuelle: {paymentProvider.mollie_live_api_key_masked || "Non configuree"}
                      </small>
                    </label>

                    <label className="span-2">
                      Secret webhook paiement (optionnel)
                      <input type="password" name="webhook_secret" placeholder="Laisser vide pour conserver l'existant" autoComplete="new-password" />
                      <small className="muted">
                        Actuel: {paymentProvider.webhook_secret_masked || "Non configure"}
                      </small>
                    </label>

                    <p className="muted span-2">
                      Capacites abonnement:{" "}
                      {paymentProvider.subscriptions_supported
                        ? paymentProvider.subscriptions_managed_by_psp
                          ? "gerees nativement par le PSP"
                          : "paiement recurrent possible, echeancier gere par l'application"
                        : "non pris en charge"}
                      . {paymentProvider.recommendation}
                    </p>

                    <div className="row span-2">
                      <button type="submit">Enregistrer la configuration PSP</button>
                    </div>
                  </form>
                )}
              </section>

              <section className="card">
                <h3>Moyens de paiement</h3>
                {!paymentMethodsResult.ok ? (
                  <p className="muted">Impossible de charger les moyens de paiement.</p>
                ) : (
                  <form action={updateAdminConfigPaymentMethodsAction} className="grid config-payment-grid">
                    {paymentMethods.map((method) => (
                      <label key={method.code} className="checkline config-payment-line">
                        <input type="checkbox" name="enabled_codes" value={method.code} defaultChecked={method.enabled} />
                        <span>
                          <strong>{method.label}</strong>
                          <small className="muted"> ({method.code})</small>
                        </span>
                      </label>
                    ))}

                    <div className="row">
                      <button type="submit">Enregistrer</button>
                    </div>
                  </form>
                )}
              </section>

              <section className="card">
                <h3>Parametres de facturation</h3>
                {!invoiceNumbering ? (
                  <p className="muted">Impossible de charger la numerotation des factures.</p>
                ) : (
                  <form action={updateAdminConfigInvoiceNumberingAction} className="grid config-form-grid">
                    <h4>Numero de facture</h4>
                    <label>
                      Format du numero
                      <input
                        type="text"
                        name="format_pattern"
                        defaultValue={invoiceNumbering.format_pattern}
                        maxLength={120}
                        required
                      />
                    </label>
                    <p className="muted">Variables: %YYYY% %YY% %MM% %DD% %NNNN% (ou %NNNNNN% pour plus de digits)</p>
                    <label>
                      Prochain numero
                      <input
                        type="number"
                        name="next_number"
                        defaultValue={String(invoiceNumbering.next_number)}
                        min={1}
                        step={1}
                        required
                      />
                    </label>
                    <p className="muted">Apercu: {invoiceNumbering.preview}</p>
                    {invoiceNumbering.updated_at ? (
                      <p className="muted">
                        Derniere mise a jour: {new Date(invoiceNumbering.updated_at).toLocaleString("fr-FR")}
                      </p>
                    ) : null}
                    <div className="row">
                      <button type="submit">Enregistrer la numerotation</button>
                    </div>
                  </form>
                )}
                <hr />
                {!invoiceTemplate ? (
                  <p className="muted">Impossible de charger le modele de facture.</p>
                ) : (
                  <form action={updateAdminConfigInvoiceTemplateAction} className="grid config-form-grid">
                    <p className="muted">Variables disponibles: {invoiceTemplate.variables_hint}</p>
                    <label>
                      Corps de facture
                      <textarea name="body" defaultValue={invoiceTemplate.body} rows={14} required />
                    </label>
                    {invoiceTemplate.updated_at ? (
                      <p className="muted">Derniere mise a jour: {new Date(invoiceTemplate.updated_at).toLocaleString("fr-FR")}</p>
                    ) : null}
                    <div className="row">
                      <button type="submit">Enregistrer le modele de facture</button>
                    </div>
                  </form>
                )}
              </section>
            </>
          ) : null}

          {requestedSection === "products" ? (
            <>
              <section className="card">
                <h3>Categories produits</h3>
                <p className="muted">Ces categories sont utilisees dans le catalogue, les demandes produits et la facturation manuelle.</p>
                <form action={createAdminCatalogCategoryAction} className="grid cols-4 config-form-grid">
                  <label>
                    Nom
                    <input type="text" name="name" required maxLength={120} placeholder="Partitions" />
                  </label>
                  <label className="span-2">
                    Description
                    <input type="text" name="description" maxLength={2000} placeholder="Categorie produits" />
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="active" defaultChecked />
                    Active
                  </label>
                  <div className="row span-4">
                    <button type="submit">Ajouter categorie</button>
                  </div>
                </form>

                {catalogCategories.length === 0 ? (
                  <p className="muted">Aucune categorie configuree.</p>
                ) : (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Nom</th>
                          <th>Description</th>
                          <th>Statut</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {catalogCategories.map((category) => (
                          <tr key={category.id}>
                            <td>{category.name}</td>
                            <td>{category.description || "-"}</td>
                            <td>{category.active ? "Active" : "Inactive"}</td>
                            <td>
                              <div className="row">
                                <details>
                                  <summary className="mode-link">Modifier</summary>
                                  <form action={updateAdminCatalogCategoryAction} className="grid top-gap-sm">
                                    <input type="hidden" name="category_id" value={category.id} />
                                    <label>
                                      Nom
                                      <input type="text" name="name" defaultValue={category.name} required maxLength={120} />
                                    </label>
                                    <label>
                                      Description
                                      <input type="text" name="description" defaultValue={category.description || ""} maxLength={2000} />
                                    </label>
                                    <label className="checkline">
                                      <input type="checkbox" name="active" defaultChecked={category.active} />
                                      Active
                                    </label>
                                    <div className="row">
                                      <button type="submit">Sauvegarder</button>
                                    </div>
                                  </form>
                                </details>
                                <form action={deleteAdminCatalogCategoryAction}>
                                  <input type="hidden" name="category_id" value={category.id} />
                                  <button type="submit" className="danger ghost">
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
                )}

                <div className="config-products-preview">
                  <strong>Synchronisation categories legacy ({productCategories.categories.length})</strong>
                  {productCategories.updated_at ? (
                    <p className="muted">Derniere mise a jour: {new Date(productCategories.updated_at).toLocaleString("fr-FR")}</p>
                  ) : null}
                  <form action={updateAdminConfigProductCategoriesAction} className="grid config-form-grid">
                    <label>
                      Categories (une par ligne, ou separees par virgules/points-virgules)
                      <textarea
                        name="categories"
                        rows={6}
                        defaultValue={productCategories.categories.join("\n")}
                        placeholder={"Partitions\nSolfege\nConcert"}
                      />
                    </label>
                    <div className="row">
                      <button type="submit">Synchroniser</button>
                    </div>
                  </form>
                </div>
              </section>

              <section className="card">
                <h3>Produits catalogue</h3>
                <form action={createAdminCatalogProductAction} className="grid cols-4 config-form-grid">
                  <label className="span-2">
                    Titre
                    <input type="text" name="title" required maxLength={255} placeholder="Partition Niveau 1" />
                  </label>
                  <label>
                    Categorie
                    <select name="category_id" defaultValue="">
                      <option value="">-</option>
                      {activeCatalogCategories.map((category) => (
                        <option key={category.id} value={category.id}>
                          {category.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Code-barres
                    <input type="text" name="barcode" maxLength={120} />
                  </label>
                  <label>
                    Tarif HT
                    <input type="number" name="price_excl_vat" min="0" step="0.01" defaultValue="0.00" required />
                  </label>
                  <label>
                    Tarif TTC
                    <input type="number" name="price_incl_vat" min="0" step="0.01" defaultValue="0.00" required />
                  </label>
                  <label>
                    TVA (%)
                    <input type="number" name="vat_rate" min="0" max="100" step="0.001" defaultValue="20.000" required />
                  </label>
                  <label>
                    Lien web
                    <input type="url" name="web_link" />
                  </label>
                  <fieldset className="span-2">
                    <legend>Type de produit</legend>
                    <label className="checkline">
                      <input type="radio" name="is_virtual" value="false" defaultChecked />
                      Physique (stock gere)
                    </label>
                    <label className="checkline">
                      <input type="radio" name="is_virtual" value="true" />
                      Virtuel (pas de stock)
                    </label>
                  </fieldset>
                  <label className="span-2">
                    Visuel (URL)
                    <input type="url" name="image_url" />
                  </label>
                  <label className="span-2">
                    Description courte
                    <input type="text" name="short_description" maxLength={500} />
                  </label>
                  <label className="span-4">
                    Description longue
                    <textarea name="long_description" rows={3} maxLength={12000} />
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="purchasable_online" />
                    Achetable en ligne
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="is_public" defaultChecked />
                    Public (visible client)
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="active" defaultChecked />
                    Actif
                  </label>
                  <div className="row span-4">
                    <button type="submit">Ajouter produit</button>
                  </div>
                </form>

                {catalogProducts.length === 0 ? (
                  <p className="muted">Aucun produit catalogue.</p>
                ) : (
                  <div className="list">
                    {catalogProducts.map((product) => (
                      <article key={product.id} className="item">
                        <div className="row spread">
                          <div>
                            <strong>{product.title}</strong>
                            <p className="muted">
                              {product.category_name || "Sans categorie"} | TTC {formatMoney(product.price_incl_vat, "EUR")} | Stock global{" "}
                              {product.is_virtual ? "n/a (virtuel)" : product.stock_global_quantity}
                            </p>
                          </div>
                          <div className="row">
                            <span className="badge">Virtuel: {yesNoLabel(product.is_virtual)}</span>
                            <span className="badge">Online: {yesNoLabel(product.purchasable_online)}</span>
                            <span className="badge">Public: {yesNoLabel(product.is_public)}</span>
                            <span className="badge">Actif: {yesNoLabel(product.active)}</span>
                          </div>
                        </div>
                        <details>
                          <summary className="mode-link">Modifier le produit</summary>
                          <form action={updateAdminCatalogProductAction} className="grid cols-4 config-form-grid top-gap-sm">
                            <input type="hidden" name="product_id" value={product.id} />
                            <label className="span-2">
                              Titre
                              <input type="text" name="title" defaultValue={product.title} required maxLength={255} />
                            </label>
                            <label>
                              Categorie
                              <select name="category_id" defaultValue={product.category_id ?? ""}>
                                <option value="">-</option>
                                {catalogCategories.map((category) => (
                                  <option key={category.id} value={category.id}>
                                    {category.name}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label>
                              Code-barres
                              <input type="text" name="barcode" defaultValue={product.barcode || ""} maxLength={120} />
                            </label>
                            <label>
                              Tarif HT
                              <input type="number" name="price_excl_vat" min="0" step="0.01" defaultValue={product.price_excl_vat} required />
                            </label>
                            <label>
                              Tarif TTC
                              <input type="number" name="price_incl_vat" min="0" step="0.01" defaultValue={product.price_incl_vat} required />
                            </label>
                            <label>
                              TVA (%)
                              <input type="number" name="vat_rate" min="0" max="100" step="0.001" defaultValue={product.vat_rate} required />
                            </label>
                            <label>
                              Lien web
                              <input type="url" name="web_link" defaultValue={product.web_link || ""} />
                            </label>
                            <fieldset className="span-2">
                              <legend>Type de produit</legend>
                              <label className="checkline">
                                <input type="radio" name="is_virtual" value="false" defaultChecked={!product.is_virtual} />
                                Physique (stock gere)
                              </label>
                              <label className="checkline">
                                <input type="radio" name="is_virtual" value="true" defaultChecked={product.is_virtual} />
                                Virtuel (pas de stock)
                              </label>
                            </fieldset>
                            <label className="span-2">
                              Visuel (URL)
                              <input type="url" name="image_url" defaultValue={product.image_url || ""} />
                            </label>
                            <label className="span-2">
                              Description courte
                              <input type="text" name="short_description" defaultValue={product.short_description || ""} maxLength={500} />
                            </label>
                            <label className="span-4">
                              Description longue
                              <textarea name="long_description" rows={3} maxLength={12000} defaultValue={product.long_description || ""} />
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="purchasable_online" defaultChecked={product.purchasable_online} />
                              Achetable en ligne
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="is_public" defaultChecked={product.is_public} />
                              Public
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="active" defaultChecked={product.active} />
                              Actif
                            </label>
                            <div className="row span-4">
                              <button type="submit">Enregistrer</button>
                            </div>
                          </form>
                          <form action={deleteAdminCatalogProductAction} className="row top-gap-sm">
                            <input type="hidden" name="product_id" value={product.id} />
                            <button type="submit" className="danger">
                              Supprimer
                            </button>
                          </form>
                        </details>
                      </article>
                    ))}
                  </div>
                )}
              </section>

              <section className="card">
                <h3>Kits</h3>
                <p className="muted">
                  Un kit assemble plusieurs produits. Le prix calcule est derive des composants (prix TTC des produits * quantites).
                </p>

                <form action={createAdminCatalogKitAction} className="grid cols-4 config-form-grid">
                  <label className="span-2">
                    Titre
                    <input type="text" name="title" required maxLength={255} />
                  </label>
                  <label>
                    Categorie
                    <select name="category_id" defaultValue="">
                      <option value="">-</option>
                      {activeCatalogCategories.map((category) => (
                        <option key={category.id} value={category.id}>
                          {category.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Tarif TTC
                    <input type="number" name="price_incl_vat" min="0" step="0.01" defaultValue="0.00" required />
                  </label>
                  <label>
                    TVA (%)
                    <input type="number" name="vat_rate" min="0" max="100" step="0.001" defaultValue="20.000" required />
                  </label>
                  <label>
                    Visuel (URL)
                    <input type="url" name="image_url" />
                  </label>
                  <label className="span-2">
                    Description courte
                    <input type="text" name="short_description" maxLength={500} />
                  </label>
                  <label className="span-4">
                    Description longue
                    <textarea name="long_description" rows={3} />
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="purchasable_online" />
                    Achetable en ligne
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="is_public" defaultChecked />
                    Public
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="active" defaultChecked />
                    Actif
                  </label>
                  <div className="span-4">
                    <strong>Composants du kit</strong>
                    <div className="catalog-kit-grid">
                      {Array.from({ length: 6 }).map((_, index) => (
                        <div key={`new-kit-item-${index}`} className="catalog-kit-grid-row">
                          <select name={`item_product_id_${index}`} defaultValue="">
                            <option value="">Produit #{index + 1}</option>
                            {activeCatalogProducts.map((product) => (
                              <option key={product.id} value={product.id}>
                                {product.title}
                              </option>
                            ))}
                          </select>
                          <input type="number" name={`item_quantity_${index}`} min={1} step={1} defaultValue={1} />
                          <input type="number" name={`item_order_${index}`} min={0} step={1} defaultValue={index} />
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="row span-4">
                    <button type="submit">Ajouter kit</button>
                  </div>
                </form>

                {catalogKits.length === 0 ? (
                  <p className="muted">Aucun kit configure.</p>
                ) : (
                  <div className="list">
                    {catalogKits.map((kit) => (
                      <article key={kit.id} className="item">
                        <div className="row spread">
                          <div>
                            <strong>{kit.title}</strong>
                            <p className="muted">
                              Categorie: {kit.category_name || "-"} | Prix saisi {formatMoney(kit.price_incl_vat, "EUR")} | Prix calcule{" "}
                              {formatMoney(kit.computed_price_incl_vat, "EUR")}
                            </p>
                          </div>
                          <div className="row">
                            <span className="badge">Items: {kit.items.length}</span>
                            <span className="badge">Public: {yesNoLabel(kit.is_public)}</span>
                            <span className="badge">Online: {yesNoLabel(kit.purchasable_online)}</span>
                          </div>
                        </div>
                        {kit.items.length > 0 ? (
                          <div className="table-wrap">
                            <table className="data-table">
                              <thead>
                                <tr>
                                  <th>Produit</th>
                                  <th>Qt</th>
                                  <th>PU TTC</th>
                                  <th>Total TTC</th>
                                </tr>
                              </thead>
                              <tbody>
                                {kit.items.map((item) => (
                                  <tr key={`${kit.id}-${item.product_id}`}>
                                    <td>{item.product_title}</td>
                                    <td>{item.quantity}</td>
                                    <td>{formatMoney(item.unit_price_incl_vat, "EUR")}</td>
                                    <td>{formatMoney(item.line_total_incl_vat, "EUR")}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : null}

                        <details>
                          <summary className="mode-link">Modifier le kit</summary>
                          <form action={updateAdminCatalogKitAction} className="grid cols-4 config-form-grid top-gap-sm">
                            <input type="hidden" name="kit_id" value={kit.id} />
                            <label className="span-2">
                              Titre
                              <input type="text" name="title" defaultValue={kit.title} required maxLength={255} />
                            </label>
                            <label>
                              Categorie
                              <select name="category_id" defaultValue={kit.category_id ?? ""}>
                                <option value="">-</option>
                                {catalogCategories.map((category) => (
                                  <option key={category.id} value={category.id}>
                                    {category.name}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label>
                              Tarif TTC
                              <input type="number" name="price_incl_vat" min="0" step="0.01" defaultValue={kit.price_incl_vat} required />
                            </label>
                            <label>
                              TVA (%)
                              <input type="number" name="vat_rate" min="0" max="100" step="0.001" defaultValue={kit.vat_rate} required />
                            </label>
                            <label>
                              Visuel (URL)
                              <input type="url" name="image_url" defaultValue={kit.image_url || ""} />
                            </label>
                            <label className="span-2">
                              Description courte
                              <input type="text" name="short_description" maxLength={500} defaultValue={kit.short_description || ""} />
                            </label>
                            <label className="span-4">
                              Description longue
                              <textarea name="long_description" rows={3} defaultValue={kit.long_description || ""} />
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="purchasable_online" defaultChecked={kit.purchasable_online} />
                              Achetable en ligne
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="is_public" defaultChecked={kit.is_public} />
                              Public
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="active" defaultChecked={kit.active} />
                              Actif
                            </label>
                            <div className="span-4">
                              <strong>Composants du kit</strong>
                              <div className="catalog-kit-grid">
                                {Array.from({ length: 6 }).map((_, index) => {
                                  const item = kit.items[index];
                                  return (
                                    <div key={`${kit.id}-item-${index}`} className="catalog-kit-grid-row">
                                      <select name={`item_product_id_${index}`} defaultValue={item?.product_id ?? ""}>
                                        <option value="">Produit #{index + 1}</option>
                                        {catalogProducts.map((product) => (
                                          <option key={product.id} value={product.id}>
                                            {product.title}
                                          </option>
                                        ))}
                                      </select>
                                      <input
                                        type="number"
                                        name={`item_quantity_${index}`}
                                        min={1}
                                        step={1}
                                        defaultValue={item?.quantity ?? 1}
                                      />
                                      <input
                                        type="number"
                                        name={`item_order_${index}`}
                                        min={0}
                                        step={1}
                                        defaultValue={item?.display_order ?? index}
                                      />
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                            <div className="row span-4">
                              <button type="submit">Enregistrer</button>
                            </div>
                          </form>
                          <form action={deleteAdminCatalogKitAction} className="row top-gap-sm">
                            <input type="hidden" name="kit_id" value={kit.id} />
                            <button type="submit" className="danger">
                              Supprimer
                            </button>
                          </form>
                        </details>
                      </article>
                    ))}
                  </div>
                )}
              </section>

              <section className="card">
                <h3>Gestion operationnelle des produits</h3>
                <p className="muted">
                  Les stocks par local et les demandes produits eleves sont desormais geres dans le menu dedie{" "}
                  <Link href="/admin/products">Produits</Link>.
                </p>
              </section>
            </>
          ) : null}

          {section === "params-messaging" ? (
            <>
              <section className="card">
                <h3>Parametres de messagerie</h3>
                {!messagingSettings ? (
                  <p className="muted">Impossible de charger les parametres de messagerie.</p>
                ) : (
                  <form action={updateAdminConfigMessagingSettingsAction} className="grid cols-2 config-form-grid">
                    <label className="span-2">
                      Courriel du studio
                      <input type="email" name="studio_email" defaultValue={messagingSettings.studio_email} maxLength={255} />
                    </label>

                    <label>
                      Expediteur studio (nom affiche)
                      <input
                        type="text"
                        name="studio_sender_name"
                        defaultValue={messagingSettings.studio_sender_name}
                        maxLength={120}
                      />
                    </label>
                    <label>
                      Expediteur enseignant (nom affiche)
                      <input
                        type="text"
                        name="teacher_sender_name"
                        defaultValue={messagingSettings.teacher_sender_name}
                        maxLength={120}
                      />
                    </label>

                    <label className="checkline span-2">
                      <input
                        type="checkbox"
                        name="use_studio_name_as_default_sender"
                        defaultChecked={messagingSettings.use_studio_name_as_default_sender}
                      />
                      Utiliser le nom du studio comme expediteur par defaut
                    </label>
                    <label className="checkline span-2">
                      <input
                        type="checkbox"
                        name="use_studio_email_for_reminders"
                        defaultChecked={messagingSettings.use_studio_email_for_reminders}
                      />
                      Utiliser le courriel du studio pour les rappels
                    </label>
                    <label className="checkline span-2">
                      <input
                        type="checkbox"
                        name="use_studio_email_for_lesson_notes"
                        defaultChecked={messagingSettings.use_studio_email_for_lesson_notes}
                      />
                      Utiliser le courriel du studio pour les notes de lecons
                    </label>
                    <label className="checkline span-2">
                      <input type="checkbox" name="send_birthday_emails" defaultChecked={messagingSettings.send_birthday_emails} />
                      Envoyer les courriels d anniversaire automatiques
                    </label>

                    <div className="span-2 config-note-box">
                      <strong>Etat technique</strong>
                      <p className="muted">
                        SPF/DKIM se valident dans Brevo (ou votre SMTP). Ici, vous pilotez les adresses et modeles utilises par
                        l application.
                      </p>
                      <p className="muted">
                        De: <strong>{messagingSettings.studio_sender_name || "Studio"}</strong> &lt;{messagingSettings.studio_email}&gt;
                      </p>
                      <p className="muted">
                        De (enseignant): <strong>{messagingSettings.teacher_sender_name || "Enseignant"}</strong> &lt;
                        {messagingSettings.studio_email}&gt;
                      </p>
                      {messagingSettings.updated_at ? (
                        <p className="muted">
                          Derniere mise a jour: {new Date(messagingSettings.updated_at).toLocaleString("fr-FR")}
                        </p>
                      ) : null}
                    </div>

                    <div className="row span-2">
                      <button type="submit">Sauvegarder les modifications</button>
                    </div>
                  </form>
                )}
              </section>

              <section className="card">
                <h3>Modeles de courriels predefinis</h3>
                {emailPredefinedTemplates.length === 0 ? (
                  <p className="muted">Aucun modele predefini.</p>
                ) : (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Nom</th>
                          <th>Objet</th>
                          <th>Actif</th>
                          <th aria-label="Actions" />
                        </tr>
                      </thead>
                      <tbody>
                        {emailPredefinedTemplates.map((template) => (
                          <tr key={template.id}>
                            <td>{template.name}</td>
                            <td>{template.subject || "-"}</td>
                            <td>{template.active ? "Oui" : "Non"}</td>
                            <td>
                              <Link
                                className="icon-link"
                                title="Modifier"
                                href={buildConfigHref("params-messaging", {
                                  messaging_modal: "edit",
                                  template_kind: "PREDEFINED",
                                  template_code: template.code || "",
                                })}
                              >
                                ✎
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <section className="card">
                <h3>Modeles de SMS predefinis</h3>
                {smsPredefinedTemplates.length === 0 ? (
                  <p className="muted">Aucun modele predefini.</p>
                ) : (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Nom</th>
                          <th>Contenu</th>
                          <th>Actif</th>
                          <th aria-label="Actions" />
                        </tr>
                      </thead>
                      <tbody>
                        {smsPredefinedTemplates.map((template) => (
                          <tr key={template.id}>
                            <td>{template.name}</td>
                            <td>{template.body.slice(0, 90)}{template.body.length > 90 ? "..." : ""}</td>
                            <td>{template.active ? "Oui" : "Non"}</td>
                            <td>
                              <Link
                                className="icon-link"
                                title="Modifier"
                                href={buildConfigHref("params-messaging", {
                                  messaging_modal: "edit",
                                  template_kind: "PREDEFINED",
                                  template_code: template.code || "",
                                })}
                              >
                                ✎
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <section className="card">
                <div className="row spread">
                  <h3>Modeles des courriels personnalises</h3>
                  <Link
                    className="mode-link"
                    href={buildConfigHref("params-messaging", {
                      messaging_modal: "new-custom",
                      new_template_channel: "EMAIL",
                    })}
                  >
                    + Ajouter nouveau
                  </Link>
                </div>
                {customEmailTemplates.length === 0 ? (
                  <p className="muted">Aucun modele personnalise.</p>
                ) : (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Nom</th>
                          <th>Objet</th>
                          <th>Actif</th>
                          <th aria-label="Actions" />
                        </tr>
                      </thead>
                      <tbody>
                        {customEmailTemplates.map((template) => (
                          <tr key={template.id}>
                            <td>{template.name}</td>
                            <td>{template.subject || "-"}</td>
                            <td>{template.active ? "Oui" : "Non"}</td>
                            <td>
                              <div className="row">
                                <Link
                                  className="icon-link"
                                  title="Modifier"
                                  href={buildConfigHref("params-messaging", {
                                    messaging_modal: "edit",
                                    template_kind: "CUSTOM",
                                    template_id: template.id,
                                  })}
                                >
                                  ✎
                                </Link>
                                <form action={deleteAdminConfigMessagingTemplateAction}>
                                  <input type="hidden" name="template_id" value={template.id} />
                                  <button type="submit" className="icon-link danger-link" title="Supprimer">
                                    🗑
                                  </button>
                                </form>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <section className="card">
                <div className="row spread">
                  <h3>Modeles de SMS personnalises</h3>
                  <Link
                    className="mode-link"
                    href={buildConfigHref("params-messaging", {
                      messaging_modal: "new-custom",
                      new_template_channel: "SMS",
                    })}
                  >
                    + Ajouter nouveau
                  </Link>
                </div>
                {customSmsTemplates.length === 0 ? (
                  <p className="muted">Aucun modele personnalise.</p>
                ) : (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Nom</th>
                          <th>Contenu</th>
                          <th>Actif</th>
                          <th aria-label="Actions" />
                        </tr>
                      </thead>
                      <tbody>
                        {customSmsTemplates.map((template) => (
                          <tr key={template.id}>
                            <td>{template.name}</td>
                            <td>
                              {template.body.slice(0, 90)}
                              {template.body.length > 90 ? "..." : ""}
                            </td>
                            <td>{template.active ? "Oui" : "Non"}</td>
                            <td>
                              <div className="row">
                                <Link
                                  className="icon-link"
                                  title="Modifier"
                                  href={buildConfigHref("params-messaging", {
                                    messaging_modal: "edit",
                                    template_kind: "CUSTOM",
                                    template_id: template.id,
                                  })}
                                >
                                  ✎
                                </Link>
                                <form action={deleteAdminConfigMessagingTemplateAction}>
                                  <input type="hidden" name="template_id" value={template.id} />
                                  <button type="submit" className="icon-link danger-link" title="Supprimer">
                                    🗑
                                  </button>
                                </form>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              {editingTemplate || createCustomMessagingTemplate ? (
                <section className="modal-overlay">
                  <article className="modal-panel activity-modal-panel messaging-template-modal">
                    <Link className="modal-close-x" href={messagingListPath} aria-label="Fermer">
                      ×
                    </Link>
                    <header className="activity-modal-header messaging-template-modal-header">
                      <div>
                        <h3 className="messaging-template-modal-title">
                          {editingTemplate?.kind === "PREDEFINED" && editingTemplate.channel === "EMAIL"
                            ? "Modifier le modele de courriel systeme"
                            : editingTemplate?.kind === "PREDEFINED" && editingTemplate.channel === "SMS"
                            ? "Modifier le modele de SMS systeme"
                            : editingTemplate
                            ? `Modifier le modele personnalise (${editingTemplate.channel})`
                            : `Nouveau modele personnalise (${newCustomTemplateChannel === "SMS" ? "SMS" : "Email"})`}
                        </h3>
                        <p className="muted">
                          {editingTemplate
                            ? "Mettez a jour l objet et le contenu du modele."
                            : "Configurez un nouveau modele reutilisable."}
                        </p>
                      </div>
                    </header>

                    <section className="card modal-card messaging-template-modal-card">
                      <form action={saveAdminConfigMessagingTemplateAction} className="grid config-form-grid messaging-template-form">
                        {editingTemplate ? (
                          <>
                            <input type="hidden" name="template_kind" value={editingTemplate.kind} />
                            <input type="hidden" name="template_channel" value={editingTemplate.channel} />
                            {editingTemplate.code ? <input type="hidden" name="template_code" value={editingTemplate.code} /> : null}
                            {editingTemplate.kind === "CUSTOM" ? (
                              <input type="hidden" name="template_id" value={editingTemplate.id} />
                            ) : null}

                            {editingTemplate.kind === "CUSTOM" ? (
                              <label>
                                Nom
                                <input type="text" name="name" defaultValue={editingTemplate.name} maxLength={180} required />
                              </label>
                            ) : (
                              <p className="messaging-template-title-line">
                                <strong>Titre :</strong> {editingTemplate.name}
                              </p>
                            )}

                            {editingTemplate.channel === "EMAIL" ? (
                              <label>
                                Objet du courriel
                                <input type="text" name="subject" defaultValue={editingTemplate.subject ?? ""} maxLength={255} required />
                              </label>
                            ) : null}

                            <label className="messaging-editor-label">
                              Message
                              <RichMessageEditor
                                name="body"
                                formatName="body_format"
                                defaultValue={editingTemplate.body}
                                defaultFormat={editingTemplate.body_format}
                                rows={20}
                                maxLength={12000}
                              />
                            </label>

                            <label className="checkline">
                              <input type="checkbox" name="active" defaultChecked={editingTemplate.active} />
                              Modele actif
                            </label>
                          </>
                        ) : (
                          <>
                            <input type="hidden" name="template_kind" value="CUSTOM" />
                            <label>
                              Nom
                              <input type="text" name="name" maxLength={180} required />
                            </label>
                            <label>
                              Canal
                              <select name="template_channel" defaultValue={newCustomTemplateChannel}>
                                <option value="EMAIL">Email</option>
                                <option value="SMS">SMS</option>
                              </select>
                            </label>
                            <label>
                              Objet (email uniquement)
                              <input type="text" name="subject" maxLength={255} />
                            </label>
                            <label className="messaging-editor-label">
                              Message
                              <RichMessageEditor name="body" formatName="body_format" rows={20} maxLength={12000} />
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="active" defaultChecked />
                              Modele actif
                            </label>
                          </>
                        )}

                        {editingTemplate?.variables_hint ? (
                          <p className="muted">Variables: {editingTemplate.variables_hint}</p>
                        ) : null}

                        <div className="row spread messaging-template-actions">
                          <div className="row">
                            {editingTemplate?.kind === "PREDEFINED" && editingTemplate.code ? (
                              <button
                                type="submit"
                                formAction={resetAdminConfigPredefinedMessagingTemplateAction}
                                className="ghost"
                              >
                                Retablir le modele par defaut
                              </button>
                            ) : null}
                          </div>
                          <button type="submit">Sauvegarder</button>
                        </div>
                      </form>
                    </section>
                  </article>
                </section>
              ) : null}
            </>
          ) : null}

          {section === "formulas" ? (
            <>
              <section className="card">
                <div className="row spread">
                  <div>
                    <h3>Formules et carnets</h3>
                    <p className="muted">Le bouton Modifier ouvre une fenetre d'edition dediee.</p>
                  </div>

                  <div className="row quick-actions-row">
                    <form method="get" className="row quick-actions-row">
                      <input type="hidden" name="section" value="formulas" />
                      <label className="checkline">
                        <input type="checkbox" name="show_inactive" value="1" defaultChecked={showInactiveFormulas} />
                        Afficher les offres desactivees
                      </label>
                      <button className="ghost small-btn" type="submit">
                        Appliquer
                      </button>
                    </form>

                    <Link className="mode-link" href={`/admin/config/formulas/new?back=${encodeURIComponent(formulasListPath)}`}>
                      Nouvelle formule
                    </Link>
                  </div>
                </div>
              </section>

              <section className="card">
                <h3>Liste des formules</h3>
                {formulas.length === 0 ? (
                  <p className="muted">Aucune formule pour ce filtre.</p>
                ) : (
                  <div className="table-wrap">
                    <table className="data-table config-formula-table">
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Offre</th>
                          <th>Type</th>
                          <th>Informations</th>
                          <th>Paiements</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {formulas.map((formula, index) => {
                          const editHref = `/admin/config/formulas/${formula.id}?back=${encodeURIComponent(formulasListPath)}`;
                          return (
                            <tr key={formula.id}>
                              <td>{index + 1}</td>
                              <td>
                                <strong>{formula.name}</strong>
                                <div className="row formula-tag-row">
                                  <span className={`status-pill ${formula.active ? "status-ok" : "status-off"}`}>
                                    {formula.active ? "Active" : "Desactivee"}
                                  </span>
                                  {formula.is_private ? <span className="status-pill status-warn">Privee</span> : null}
                                  <span className="badge">{formula.code}</span>
                                </div>
                                {formula.description ? <p className="muted">{formula.description}</p> : null}
                              </td>
                              <td>
                                <p>{formulaKindLabel(formula.kind)}</p>
                                {formula.kind === "PACK" ? (
                                  <div className="formula-info-col">
                                    <small className="muted">Credits totaux: {formula.credits_count ?? 0}</small>
                                    <small className="muted">Validite: {formula.pack_validity_months ?? 12} mois</small>
                                    {formula.credit_grants.length > 0 ? (
                                      <small className="muted">
                                        {formula.credit_grants
                                          .map(
                                            (grant) =>
                                              `${grant.credit_type_name || grant.credit_type_code || grant.credit_type_id}: ${grant.credits_count}`,
                                          )
                                          .join(" | ")}
                                      </small>
                                    ) : (
                                      <small className="muted">Aucun type de credit associe</small>
                                    )}
                                  </div>
                                ) : formula.kind === "FORFAIT" ? (
                                  <small className="muted">Facturation au reel sur les cours planifies</small>
                                ) : (
                                  <small className="muted">Illimite mensuel</small>
                                )}
                              </td>
                              <td>
                                <div className="formula-info-col">
                                  <small className="muted">
                                    Cours accessibles: {formula.entitlement_course_type_names.join(", ") || "Aucun"}
                                  </small>
                                  <small className="muted">
                                    Restrictions: {formula.restrictions.length === 0 ? "Aucune" : ""}
                                  </small>
                                  {formula.restrictions.length > 0 ? (
                                    <ul className="formula-restrictions-list">
                                      {formula.restrictions.map((restriction) => (
                                        <li key={restriction.id}>
                                          {restriction.max_bookings} cours / {restrictionPeriodLabel(restriction.period)}
                                          {restriction.course_type_names.length > 0
                                            ? ` (${restriction.course_type_names.join(", ")})`
                                            : " (tous types)"}
                                        </li>
                                      ))}
                                    </ul>
                                  ) : null}
                                </div>
                              </td>
                              <td>
                                <div className="formula-info-col">
                                  <small>
                                    Tarif {formulaPriceModeLabel(formula.price_tax_mode)}:{" "}
                                    {formula.kind === "FORFAIT" && formula.monthly_price_value == null && formula.monthly_price_excl_vat == null
                                      ? "Calcule au reel"
                                      : formatMoney(
                                          formula.monthly_price_value ?? formula.monthly_price_excl_vat,
                                          formula.currency_code ?? "EUR",
                                        )}
                                  </small>
                                  <small>
                                    Frais de dossier {formulaPriceModeLabel(formula.price_tax_mode)}:{" "}
                                    {formatMoney(
                                      formula.signup_fee_value ?? formula.signup_fee_excl_vat,
                                      formula.currency_code ?? "EUR",
                                    )}
                                  </small>
                                  <small>
                                    Moyens: {formula.payment_methods.map((code) => paymentMethodLabelByCode.get(code) ?? code).join(", ") || "-"}
                                  </small>
                                </div>
                              </td>
                              <td>
                                <div className="formula-actions-cell">
                                  <Link className="mode-link" href={editHref} target="_blank" rel="noreferrer">
                                    Modifier
                                  </Link>

                                  <form action={duplicateAdminFormulaAction}>
                                    <input type="hidden" name="formula_id" value={formula.id} />
                                    <input type="hidden" name="return_to" value={formulasListPath} />
                                    <button type="submit" className="ghost small-btn">
                                      Dupliquer
                                    </button>
                                  </form>

                                  <form action={disableAdminFormulaAction}>
                                    <input type="hidden" name="formula_id" value={formula.id} />
                                    <input type="hidden" name="return_to" value={formulasListPath} />
                                    <button type="submit" className="danger small-btn" disabled={!formula.active}>
                                      Desactiver
                                    </button>
                                  </form>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          ) : null}

          {section === "activities" ? (
            <>
              <section className="card">
                <div className="row between">
                  <h3>Referentiel des activites</h3>
                  <Link className="mode-link" href={buildConfigHref("activities", { new_activity: "1" })}>
                    Ajouter une activite
                  </Link>
                </div>
                <p className="muted">
                  Une activite definit le titre, la description, la duree, la couleur, la capacite maximum et le tarif
                  (horaire TTC ou par cours TTC).
                </p>
                {activeCreditTypes.length === 0 ? (
                  <p className="flash-err">Aucun type de credit actif: ajoutez/activez d abord un type de credit.</p>
                ) : null}
              </section>

              <section className="card">
                <div className="row between">
                  <h3>Activites existantes</h3>
                  <small className="muted">{activities.length} activite(s)</small>
                </div>
                <p className="muted">Cliquez une activite pour ouvrir sa fiche de modification.</p>
                {activities.length === 0 ? (
                  <p className="muted">Aucune activite dans le referentiel.</p>
                ) : (
                  <div className="list activity-list">
                    {activities.map((activity) => (
                      <Link
                        key={activity.id}
                        href={buildConfigHref("activities", { activity_id: activity.id })}
                        className="activity-row-link"
                      >
                        <span className="activity-row-color" style={{ backgroundColor: activity.color_hex }} aria-hidden />
                        <div className="activity-row-main">
                          <strong>{activity.name}</strong>
                          <small className="muted">{activity.description || "Sans description"}</small>
                        </div>
                        <div className="activity-row-meta">
                          <span className="status-pill status-off">{activity.code}</span>
                          <span className="status-pill status-off">{activity.credit_type_name ?? "Type credit non mappe"}</span>
                          <span className="status-pill status-warn">{activityModeLabel(activity.mode)}</span>
                          <span className="status-pill status-ok">{activity.duration_minutes} min</span>
                          <span className="status-pill status-warn">
                            {activity.default_course_rate_ttc
                              ? `${activity.default_course_rate_ttc} ${accountDefaultCurrency}/cours TTC`
                              : activity.default_hourly_rate
                                ? `${activity.default_hourly_rate} ${accountDefaultCurrency}/h TTC`
                                : "Tarif TTC non defini"}
                          </span>
                          <span className="status-pill status-off">Cap. max {activity.default_capacity}</span>
                          <span className={`status-pill ${activity.active ? "status-ok" : "status-warn"}`}>
                            {activity.active ? "Active" : "Inactive"}
                          </span>
                        </div>
                        <span className="mode-link">Modifier</span>
                      </Link>
                    ))}
                  </div>
                )}
              </section>

              {createActivityModalOpen ? (
                <section className="modal-overlay">
                  <article className="modal-panel activity-modal-panel">
                    <Link className="modal-close-x" href={buildConfigHref("activities")} aria-label="Fermer">
                      ×
                    </Link>
                    <header className="activity-modal-header">
                      <div>
                        <h3>Nouvelle activite</h3>
                        <p className="muted">Saisir les informations de l activite puis enregistrer.</p>
                      </div>
                    </header>

                    <section className="card modal-card">
                      {activeCreditTypes.length === 0 ? (
                        <p className="flash-err">Impossible de creer une activite sans type de credit actif.</p>
                      ) : (
                      <form action={createAdminActivityAction} className="grid cols-4 config-form-grid activity-modal-grid">
                        <label className="span-2">
                          Nom de l activite
                          <input type="text" name="name" required maxLength={255} />
                        </label>
                        <label>
                          Code (optionnel)
                          <input type="text" name="code" maxLength={80} placeholder="auto-genere si vide" />
                        </label>
                        <label>
                          Service code
                          <input type="text" name="service_code" defaultValue="ACTIVITY" maxLength={80} />
                        </label>

                        <label>
                          Mode
                          <select name="mode" defaultValue="ANY">
                            <option value="ANY">Tous</option>
                            <option value="ONSITE">Presentiel</option>
                            <option value="ONLINE">En ligne</option>
                          </select>
                        </label>
                        <label>
                          Type de credit
                          <select name="credit_type_id" defaultValue={activeCreditTypes[0]?.id ?? ""} required>
                            <option value="" disabled>
                              Selectionner
                            </option>
                            {activeCreditTypes.map((creditType) => (
                              <option key={creditType.id} value={creditType.id}>
                                {creditType.name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Duree (minutes)
                          <input type="number" name="duration_minutes" min={5} max={600} defaultValue={60} required />
                        </label>
                        <label>
                          Capacite maximum
                          <input type="number" name="default_capacity" min={1} max={500} defaultValue={8} required />
                        </label>
                        <label>
                          Tarif horaire TTC
                          <input
                            type="number"
                            name="default_hourly_rate"
                            min={0}
                            step="0.01"
                            placeholder="ex: 35.00"
                          />
                        </label>
                        <label>
                          Tarif par cours TTC
                          <input
                            type="number"
                            name="default_course_rate_ttc"
                            min={0}
                            step="0.01"
                            placeholder="ex: 200.00"
                          />
                        </label>
                        <label>
                          Couleur
                          <ColorHexInput name="color_hex" defaultValue="#94C973" />
                        </label>
                        <label className="checkline">
                          <input type="checkbox" name="active" defaultChecked />
                          Active
                        </label>

                        <label className="span-3">
                          Description
                          <textarea name="description" rows={3} />
                        </label>
                        <div className="row">
                          <button type="submit">Ajouter l activite</button>
                        </div>
                      </form>
                      )}
                    </section>
                  </article>
                </section>
              ) : null}

              {selectedActivity ? (
                <section className="modal-overlay">
                  <article className="modal-panel activity-modal-panel">
                    <Link className="modal-close-x" href={buildConfigHref("activities")} aria-label="Fermer">
                      ×
                    </Link>
                    <header className="activity-modal-header">
                      <div>
                        <h3>{selectedActivity.name}</h3>
                        <p className="muted">Modifier les informations de l activite.</p>
                      </div>
                    </header>

                    <section className="card modal-card">
                      {activeCreditTypes.length === 0 ? (
                        <p className="flash-err">Impossible de modifier cette activite sans type de credit actif.</p>
                      ) : (
                      <form action={updateAdminActivityAction} className="grid cols-4 config-form-grid activity-modal-grid">
                        <input type="hidden" name="activity_id" value={selectedActivity.id} />

                        <label className="span-2">
                          Nom de l activite
                          <input type="text" name="name" defaultValue={selectedActivity.name} required maxLength={255} />
                        </label>
                        <label>
                          Code
                          <input type="text" name="code" defaultValue={selectedActivity.code} maxLength={80} />
                        </label>
                        <label>
                          Service code
                          <input type="text" name="service_code" defaultValue={selectedActivity.service_code} maxLength={80} />
                        </label>
                        <label>
                          Mode
                          <select name="mode" defaultValue={selectedActivity.mode}>
                            <option value="ANY">Tous</option>
                            <option value="ONSITE">Presentiel</option>
                            <option value="ONLINE">En ligne</option>
                          </select>
                        </label>

                        <label>
                          Type de credit
                          <select name="credit_type_id" defaultValue={selectedActivity.credit_type_id ?? ""} required>
                            <option value="" disabled>
                              Selectionner
                            </option>
                            {activeCreditTypes.map((creditType) => (
                              <option key={creditType.id} value={creditType.id}>
                                {creditType.name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Duree (minutes)
                          <input
                            type="number"
                            name="duration_minutes"
                            min={5}
                            max={600}
                            defaultValue={selectedActivity.duration_minutes}
                            required
                          />
                        </label>
                        <label>
                          Capacite maximum
                          <input
                            type="number"
                            name="default_capacity"
                            min={1}
                            max={500}
                            defaultValue={selectedActivity.default_capacity}
                            required
                          />
                        </label>
                        <label>
                          Tarif horaire TTC
                          <input
                            type="number"
                            name="default_hourly_rate"
                            min={0}
                            step="0.01"
                            defaultValue={selectedActivity.default_hourly_rate ?? ""}
                            placeholder="ex: 35.00"
                          />
                        </label>
                        <label>
                          Tarif par cours TTC
                          <input
                            type="number"
                            name="default_course_rate_ttc"
                            min={0}
                            step="0.01"
                            defaultValue={selectedActivity.default_course_rate_ttc ?? ""}
                            placeholder="ex: 200.00"
                          />
                        </label>
                        <label>
                          Couleur
                          <ColorHexInput name="color_hex" defaultValue={selectedActivity.color_hex} />
                        </label>
                        <label className="checkline">
                          <input type="checkbox" name="active" defaultChecked={selectedActivity.active} />
                          Active
                        </label>

                        <label className="span-3">
                          Description
                          <textarea name="description" rows={3} defaultValue={selectedActivity.description ?? ""} />
                        </label>
                        <div className="row">
                          <button type="submit">Enregistrer</button>
                        </div>
                      </form>
                      )}
                    </section>
                  </article>
                </section>
              ) : null}
            </>
          ) : null}

          {section === "credit-types" ? (
            <>
              <section className="card">
                <div className="row between">
                  <div>
                    <h3>Types de credit</h3>
                    <p className="muted">
                      Mapping strict backend entre type de credit et activites. Les carnets debitent uniquement les credits du type associe.
                    </p>
                  </div>
                  <Link className="mode-link" href={buildConfigHref("credit-types", { new_credit_type: "1" })}>
                    Ajouter un type de credit
                  </Link>
                </div>
              </section>

              <section className="card">
                <h3>Referentiel credits</h3>
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Code</th>
                        <th>Type de credit</th>
                        <th>Activites associees</th>
                        <th>Statut</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {creditTypes.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="muted">
                            Aucun type de credit charge.
                          </td>
                        </tr>
                      ) : null}
                      {creditTypes.map((creditType) => (
                        <tr key={creditType.id}>
                          <td>
                            <span className="badge">{creditType.code}</span>
                          </td>
                          <td>
                            <strong>{creditType.name}</strong>
                            {creditType.description ? <p className="muted">{creditType.description}</p> : null}
                          </td>
                          <td>
                            {creditType.activity_names.length === 0 ? (
                              <span className="muted">Aucune activite associee</span>
                            ) : (
                              <div className="formula-tag-row">
                                {creditType.activity_names.map((activityName) => (
                                  <span key={`${creditType.id}-${activityName}`} className="status-pill status-off">
                                    {activityName}
                                  </span>
                                ))}
                              </div>
                            )}
                          </td>
                          <td>
                            <span className={`status-pill ${creditType.active ? "status-ok" : "status-warn"}`}>
                              {creditType.active ? "Actif" : "Inactif"}
                            </span>
                            <span className={`status-pill ${creditType.activity_count > 0 ? "status-ok" : "status-warn"}`}>
                              {creditType.activity_count > 0 ? `${creditType.activity_count} activite(s)` : "A configurer"}
                            </span>
                          </td>
                          <td>
                            <div className="formula-actions-cell">
                              <Link className="mode-link" href={buildConfigHref("credit-types", { credit_type_id: creditType.id })}>
                                Modifier
                              </Link>
                              <form action={deleteAdminCreditTypeAction}>
                                <input type="hidden" name="credit_type_id" value={creditType.id} />
                                <button type="submit" className="danger small-btn" disabled={creditType.activity_count > 0}>
                                  Supprimer
                                </button>
                              </form>
                            </div>
                            {creditType.activity_count > 0 ? (
                              <small className="muted">Supprimer indisponible: type utilise par des activites.</small>
                            ) : null}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              {createCreditTypeModalOpen ? (
                <section className="modal-overlay">
                  <article className="modal-panel activity-modal-panel">
                    <Link className="modal-close-x" href={buildConfigHref("credit-types")} aria-label="Fermer">
                      ×
                    </Link>
                    <header className="activity-modal-header">
                      <div>
                        <h3>Nouveau type de credit</h3>
                        <p className="muted">Ajouter un type de credit utilisable dans les formules et activites.</p>
                      </div>
                    </header>

                    <section className="card modal-card">
                      <form action={createAdminCreditTypeAction} className="grid cols-2 config-form-grid">
                        <label>
                          Nom du type de credit
                          <input type="text" name="name" required maxLength={255} />
                        </label>
                        <label>
                          Code (optionnel)
                          <input type="text" name="code" maxLength={80} placeholder="auto-genere si vide" />
                        </label>

                        <label className="span-2">
                          Description
                          <textarea name="description" rows={3} />
                        </label>
                        <label className="checkline">
                          <input type="checkbox" name="active" defaultChecked />
                          Active
                        </label>

                        <div className="row span-2">
                          <button type="submit">Ajouter le type de credit</button>
                        </div>
                      </form>
                    </section>
                  </article>
                </section>
              ) : null}

              {selectedCreditType ? (
                <section className="modal-overlay">
                  <article className="modal-panel activity-modal-panel">
                    <Link className="modal-close-x" href={buildConfigHref("credit-types")} aria-label="Fermer">
                      ×
                    </Link>
                    <header className="activity-modal-header">
                      <div>
                        <h3>{selectedCreditType.name}</h3>
                        <p className="muted">Modifier les informations du type de credit.</p>
                      </div>
                    </header>

                    <section className="card modal-card">
                      <form action={updateAdminCreditTypeAction} className="grid cols-2 config-form-grid">
                        <input type="hidden" name="credit_type_id" value={selectedCreditType.id} />

                        <label>
                          Nom du type de credit
                          <input type="text" name="name" defaultValue={selectedCreditType.name} required maxLength={255} />
                        </label>
                        <label>
                          Code
                          <input type="text" name="code" defaultValue={selectedCreditType.code} maxLength={80} />
                        </label>

                        <label className="span-2">
                          Description
                          <textarea name="description" rows={3} defaultValue={selectedCreditType.description ?? ""} />
                        </label>
                        <label className="checkline">
                          <input type="checkbox" name="active" defaultChecked={selectedCreditType.active} />
                          Active
                        </label>

                        <div className="row span-2">
                          <button type="submit">Enregistrer</button>
                        </div>
                      </form>

                      <div className="row top-gap-sm">
                        <form action={deleteAdminCreditTypeAction}>
                          <input type="hidden" name="credit_type_id" value={selectedCreditType.id} />
                          <button
                            type="submit"
                            className="danger"
                            disabled={selectedCreditType.activity_count > 0}
                            title={
                              selectedCreditType.activity_count > 0
                                ? "Supprimez ou remappez les activites associees avant suppression"
                                : undefined
                            }
                          >
                            Supprimer ce type de credit
                          </button>
                        </form>
                      </div>

                      {selectedCreditType.activity_count > 0 ? (
                        <p className="muted top-gap-sm">
                          Suppression bloquee: {selectedCreditType.activity_count} activite(s) sont encore associees a ce type de credit.
                        </p>
                      ) : null}
                    </section>
                  </article>
                </section>
              ) : null}
            </>
          ) : null}

          {section !== "params-account" &&
          section !== "params-subscriptions" &&
          section !== "params-payments" &&
          section !== "params-professor-default-grid" &&
          section !== "params-messaging" &&
          section !== "formulas" &&
          section !== "activities" &&
          section !== "credit-types" ? (
            <section className="card config-placeholder-card">
              <h3>{placeholderTitleBySection[section]}</h3>
              <p className="muted">Cette section est reservee pour un prochain ticket (V2), avec ecran detaille.</p>
              <p className="muted">Decision V1: la navigation est en place pour stabiliser l'ergonomie et preparer les sous-menus.</p>
            </section>
          ) : null}
        </div>
      </section>
    </section>
  );
}
