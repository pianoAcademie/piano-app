import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import ColorHexInput from "../../../components/color-hex-input";
import {
  createAdminActivityAction,
  createAdminCreditTypeAction,
  deleteAdminCreditTypeAction,
  disableAdminFormulaAction,
  duplicateAdminFormulaAction,
  updateAdminActivityAction,
  updateAdminCreditTypeAction,
  updateAdminConfigAccountAction,
  updateAdminConfigMessagingSettingsAction,
  updateAdminConfigProfessorDefaultGridAction,
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
  AdminCreditTypeOut,
  AdminConfigAccountOut,
  AdminFormulaOut,
  AdminMessagingSettingsOut,
  AdminMessagingTemplateOut,
  AdminPaymentProviderOut,
  AdminPaymentMethodsOut,
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
  { key: "products", label: "Les produits", section: "products" },
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

function formulaKindLabel(kind: "PACK" | "SUBSCRIPTION"): string {
  return kind === "PACK" ? "Carnet" : "Abonnement";
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

export default async function AdminConfigPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const params = searchParams ?? {};
  const section = parseSection(readParam(params, "section"));
  const mainSection = toMainSection(section);
  const showInactiveFormulas = readParam(params, "show_inactive") === "1";

  const formulasEndpoint = showInactiveFormulas
    ? "/api/v1/admin/formulas?include_inactive=true"
    : "/api/v1/admin/formulas";

  const [
    accountResult,
    subscriptionsResult,
    paymentMethodsResult,
    paymentProviderResult,
    messagingSettingsResult,
    emailPredefinedTemplatesResult,
    smsPredefinedTemplatesResult,
    customTemplatesResult,
    defaultProfessorGridResult,
    formulasResult,
    activitiesResult,
    creditTypesResult,
  ] =
    await Promise.all([
    backendRequest<AdminConfigAccountOut>("/api/v1/admin/config/account", {}, token),
    backendRequest<AdminSubscriptionSettingsOut>("/api/v1/admin/config/subscriptions", {}, token),
    backendRequest<AdminPaymentMethodsOut>("/api/v1/admin/config/payment-methods", {}, token),
    backendRequest<AdminPaymentProviderOut>("/api/v1/admin/config/payment-provider", {}, token),
    backendRequest<AdminMessagingSettingsOut>("/api/v1/admin/config/messaging-settings", {}, token),
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
  const messagingSettings = messagingSettingsResult.ok
    ? messagingSettingsResult.data
    : (() => {
        loadErrors.push(`Messagerie: ${messagingSettingsResult.message}`);
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
                <form action={updateAdminConfigAccountAction} className="grid cols-2 config-form-grid">
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
                              <div className="messaging-editor-shell">
                                {editingTemplate.channel === "EMAIL" ? (
                                  <div className="messaging-editor-toolbar" aria-hidden>
                                    <span>B</span>
                                    <span>I</span>
                                    <span>U</span>
                                    <span>UL</span>
                                    <span>1.</span>
                                    <span>LNK</span>
                                    <span>IMG</span>
                                  </div>
                                ) : null}
                                <textarea
                                  className="messaging-editor-body"
                                  name="body"
                                  defaultValue={editingTemplate.body}
                                  rows={20}
                                  required
                                />
                              </div>
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
                              <div className="messaging-editor-shell">
                                <div className="messaging-editor-toolbar" aria-hidden>
                                  <span>B</span>
                                  <span>I</span>
                                  <span>U</span>
                                  <span>UL</span>
                                  <span>1.</span>
                                  <span>LNK</span>
                                  <span>IMG</span>
                                </div>
                                <textarea className="messaging-editor-body" name="body" rows={20} required />
                              </div>
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
                                    {formatMoney(
                                      formula.monthly_price_value ?? formula.monthly_price_excl_vat,
                                      formula.currency_code ?? "EUR",
                                    )}
                                  </small>
                                  <small>
                                    Frais inscription {formulaPriceModeLabel(formula.price_tax_mode)}:{" "}
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
                  Une activite definit le titre, la description, la duree, la couleur, la capacite maximum et le tarif horaire TTC.
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
                            {activity.default_hourly_rate ? `${activity.default_hourly_rate} ${accountDefaultCurrency}/h TTC` : "Tarif TTC non defini"}
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
