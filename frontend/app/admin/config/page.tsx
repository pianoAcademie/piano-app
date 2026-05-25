import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import AdminIntegrationPlanningEmbed from "../../../components/admin-integration-planning-embed";
import ActivityContentAssignmentsPicker, {
  ActivityModalTabs,
} from "../../../components/activity-content-assignment-picker";
import ColorHexInput from "../../../components/color-hex-input";
import RichMessageEditor from "../../../components/rich-message-editor";
import {
  createAdminCatalogCategoryAction,
  createAdminCatalogKitAction,
  createAdminCatalogProductAction,
  createAdminActivityAction,
  createAdminCreditTypeAction,
  createAdminLegalEntityAction,
  deleteAdminCatalogCategoryAction,
  deleteAdminCatalogKitAction,
  deleteAdminCatalogProductAction,
  deleteAdminCreditTypeAction,
  disableAdminLegalEntityAction,
  updateAdminCatalogCategoryAction,
  updateAdminCatalogKitAction,
  updateAdminCatalogProductAction,
  updateAdminActivityAction,
  updateAdminCreditTypeAction,
  updateAdminLegalEntityAction,
  updateAdminConfigAccountAction,
  updateAdminConfigExternalContentSettingsAction,
  updateAdminConfigMessagingSettingsAction,
  updateAdminConfigInvoiceNumberingAction,
  updateAdminConfigInvoiceTemplateAction,
  updateAdminConfigProductCategoriesAction,
  updateAdminConfigPaymentMethodsAction,
  updateAdminConfigPaymentProviderAction,
  updateAdminConfigReferralProgramAction,
  updateAdminConfigSubscriptionsAction,
  deleteAdminConfigMessagingTemplateAction,
  resetAdminConfigPredefinedMessagingTemplateAction,
  saveAdminConfigMessagingTemplateAction,
  syncAdminExternalContentCatalogAction,
} from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import type {
  AdminActivityOut,
  AdminCatalogCategoryOut,
  AdminCatalogKitOut,
  AdminCatalogProductOut,
  AdminCreditTypeOut,
  AdminLegalEntityOut,
  AdminPlanningActivitiesOut,
  AdminConfigAccountOut,
  AdminExternalContentCourseOut,
  AdminExternalContentSettingsOut,
  AdminMessagingSettingsOut,
  AdminMessagingTemplateOut,
  AdminInvoiceTemplateOut,
  AdminInvoiceNumberingOut,
  LocationOut,
  AdminPaymentProviderOut,
  AdminPaymentMethodsOut,
  AdminProductCategoriesOut,
  AdminReferralProgramSettingsOut,
  AdminSubscriptionSettingsOut,
  UserOut,
  QuoteTemplateVariableOut,
} from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

type ConfigMainSection =
  | "params"
  | "formulas"
  | "quotes"
  | "calendars"
  | "activities"
  | "legal-entities"
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
  | "params-referrals"
  | "params-messaging"
  | "formulas"
  | "quotes"
  | "calendars"
  | "activities"
  | "legal-entities"
  | "promo"
  | "products"
  | "payment-rules"
  | "integrations"
  | "purchase-link"
  | "credit-types";

type MainNavItem = {
  key: ConfigMainSection;
  label: string;
  labelKey?: string;
  descriptionKey?: string;
  section: ConfigSection;
};

type MainNavGroup = {
  titleKey: string;
  descriptionKey: string;
  items: MainNavItem[];
};

type SubNavItem = {
  key:
    | "params-account"
    | "params-subscriptions"
    | "params-payments"
    | "params-referrals"
    | "params-messaging";
  label: string;
  labelKey?: string;
};

type MessagingTab =
  | "settings"
  | "scheduled"
  | "predefined-email"
  | "predefined-sms"
  | "custom-email"
  | "custom-sms"
  | "group-notes";

type MessagingTabItem = {
  key: MessagingTab;
  label: string;
  labelKey?: string;
};

const MAIN_NAV_ITEMS: MainNavItem[] = [
  { key: "params", label: "", labelKey: "admin.config.main.params", descriptionKey: "admin.config.nav.params_desc", section: "params-account" },
  { key: "legal-entities", label: "", labelKey: "admin.breadcrumb.legal_entities", descriptionKey: "admin.config.nav.legal_entities_desc", section: "legal-entities" },
  { key: "integrations", label: "", labelKey: "admin.breadcrumb.integrations", descriptionKey: "admin.config.nav.integrations_desc", section: "integrations" },
  { key: "activities", label: "", labelKey: "admin.breadcrumb.activities", descriptionKey: "admin.config.nav.activities_desc", section: "activities" },
  { key: "formulas", label: "", labelKey: "admin.breadcrumb.formulas", descriptionKey: "admin.config.nav.formulas_desc", section: "formulas" },
  { key: "credit-types", label: "", labelKey: "admin.breadcrumb.credit_types", descriptionKey: "admin.config.nav.credit_types_desc", section: "credit-types" },
  { key: "calendars", label: "", labelKey: "admin.breadcrumb.school_calendars", descriptionKey: "admin.config.nav.calendars_desc", section: "calendars" },
  { key: "quotes", label: "", labelKey: "admin.breadcrumb.quotes", descriptionKey: "admin.config.nav.quotes_desc", section: "quotes" },
  { key: "payment-rules", label: "", labelKey: "admin.breadcrumb.payment_rules", descriptionKey: "admin.config.nav.payment_rules_desc", section: "payment-rules" },
  { key: "promo", label: "", labelKey: "admin.breadcrumb.promo", descriptionKey: "admin.config.nav.promo_desc", section: "promo" },
  { key: "purchase-link", label: "", labelKey: "admin.breadcrumb.purchase_link", descriptionKey: "admin.config.nav.purchase_link_desc", section: "purchase-link" },
];

const MAIN_NAV_GROUPS: MainNavGroup[] = [
  {
    titleKey: "admin.config.nav.group_admin",
    descriptionKey: "admin.config.nav.group_admin_desc",
    items: MAIN_NAV_ITEMS.filter((item) => item.key === "params" || item.key === "legal-entities" || item.key === "integrations"),
  },
  {
    titleKey: "admin.config.nav.group_offer",
    descriptionKey: "admin.config.nav.group_offer_desc",
    items: MAIN_NAV_ITEMS.filter((item) => item.key === "activities" || item.key === "formulas" || item.key === "credit-types" || item.key === "calendars"),
  },
  {
    titleKey: "admin.config.nav.group_sales",
    descriptionKey: "admin.config.nav.group_sales_desc",
    items: MAIN_NAV_ITEMS.filter((item) => item.key === "quotes" || item.key === "payment-rules" || item.key === "promo" || item.key === "purchase-link"),
  },
];

const PARAMS_SUBNAV_ITEMS: SubNavItem[] = [
  { key: "params-account", label: "", labelKey: "admin.breadcrumb.account_info" },
  { key: "params-subscriptions", label: "", labelKey: "admin.breadcrumb.subscription_settings" },
  { key: "params-payments", label: "", labelKey: "admin.breadcrumb.payment_methods" },
  { key: "params-referrals", label: "", labelKey: "admin.config.referrals" },
  { key: "params-messaging", label: "", labelKey: "admin.config.messaging" },
];

const MESSAGING_TAB_ITEMS: MessagingTabItem[] = [
  { key: "settings", label: "", labelKey: "admin.messaging_settings.tab.settings" },
  { key: "scheduled", label: "", labelKey: "admin.messaging_settings.tab.scheduled" },
  { key: "predefined-email", label: "", labelKey: "admin.messaging_settings.tab.predefined_email" },
  { key: "predefined-sms", label: "", labelKey: "admin.messaging_settings.tab.predefined_sms" },
  { key: "custom-email", label: "", labelKey: "admin.messaging_settings.tab.custom_email" },
  { key: "custom-sms", label: "", labelKey: "admin.messaging_settings.tab.custom_sms" },
  { key: "group-notes", label: "", labelKey: "admin.messaging_settings.tab.group_notes" },
];

const REMINDER_OFFSET_OPTIONS: Array<{ value: string; labelKey: string }> = [
  { value: "global", labelKey: "admin.activity_modal.reminder_global" },
  { value: "0", labelKey: "admin.activity_modal.reminder_none" },
  { value: "1", labelKey: "admin.activity_modal.reminder_1_hour" },
  { value: "2", labelKey: "admin.activity_modal.reminder_2_hours" },
  { value: "3", labelKey: "admin.activity_modal.reminder_3_hours" },
  { value: "24", labelKey: "admin.activity_modal.reminder_1_day" },
  { value: "48", labelKey: "admin.activity_modal.reminder_2_days" },
];

const QUOTE_TEMPLATE_USAGE_CONTEXTS = [
  { value: "QUOTE_SEND", labelKey: "admin.messaging_templates.usage_send" },
  { value: "QUOTE_REMINDER", labelKey: "admin.messaging_templates.usage_reminder" },
  { value: "QUOTE_CANCEL", labelKey: "admin.messaging_templates.usage_cancel" },
  { value: "QUOTE_EXPIRED", labelKey: "admin.messaging_templates.usage_expired" },
  { value: "QUOTE_APPROVED", labelKey: "admin.messaging_templates.usage_approved" },
  { value: "QUOTE_REJECTED", labelKey: "admin.messaging_templates.usage_rejected" },
  { value: "QUOTE_CHANGE_REQUESTED", labelKey: "admin.messaging_templates.usage_change_requested" },
  { value: "INVOICE_SEND", labelKey: "admin.messaging_templates.usage_invoice_send" },
  { value: "INVOICE_REMINDER", labelKey: "admin.messaging_templates.usage_invoice_reminder" },
] as const;

type ActivityModalSectionProps = {
  title: string;
  description: string;
  children: ReactNode;
  accent?: boolean;
};

type ActivityToggleCardProps = {
  name: string;
  label: string;
  description: string;
  defaultChecked?: boolean;
  emphasized?: boolean;
};

type ActivityPlanningLocationOption = {
  locationId: string;
  locationName: string;
  selectedActivityCount: number;
  selectedForCurrentActivity: boolean;
};

function ActivityModalSection({ title, description, children, accent = false }: ActivityModalSectionProps) {
  return (
    <section className={`activity-modal-section${accent ? " is-accent" : ""}`}>
      <header className="activity-modal-section-header">
        <h4>{title}</h4>
        <p>{description}</p>
      </header>
      {children}
    </section>
  );
}

function ActivityToggleCard({
  name,
  label,
  description,
  defaultChecked = false,
  emphasized = false,
}: ActivityToggleCardProps) {
  return (
    <label className={`activity-toggle-card${emphasized ? " is-emphasis" : ""}`}>
      <span className="activity-toggle-checkbox">
        <input type="checkbox" name={name} defaultChecked={defaultChecked} />
      </span>
      <span className="activity-toggle-copy">
        <strong>{label}</strong>
        <small>{description}</small>
      </span>
    </label>
  );
}

function ActivityPlanningAssignments({
  locations,
  defaultSelectedLocationIds,
  language,
}: {
  locations: ActivityPlanningLocationOption[];
  defaultSelectedLocationIds: string[];
  language: UiLanguage;
}) {
  const defaultSelected = new Set(defaultSelectedLocationIds);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  if (locations.length === 0) {
    return <p className="muted">{t("admin.activity_modal.no_active_planning")}</p>;
  }

  return (
    <div className="activity-planning-grid">
      {locations.map((location) => (
        <label key={location.locationId} className="activity-planning-card">
          <input type="hidden" name="planning_scope_location_ids" value={location.locationId} />
          <span className="activity-planning-checkbox">
            <input
              type="checkbox"
              name="planning_location_ids"
              value={location.locationId}
              defaultChecked={defaultSelected.has(location.locationId)}
            />
          </span>
          <span className="activity-planning-copy">
            <strong>{location.locationName}</strong>
            <small>{t("admin.activity_modal.planning_visible_activities", { count: location.selectedActivityCount })}</small>
          </span>
        </label>
      ))}
    </div>
  );
}

function quoteUsageContextLabel(language: UiLanguage, value: string): string {
  const match = QUOTE_TEMPLATE_USAGE_CONTEXTS.find((item) => item.value === value);
  return match?.labelKey ? uiText(language, match.labelKey) : value;
}

function messagingTemplateRef(template: AdminMessagingTemplateOut): string {
  if (template.kind === "PREDEFINED") {
    return `predefined:${template.code || ""}`;
  }
  return `custom:${template.id}`;
}

function messagingTemplateOptionLabel(language: UiLanguage, template: AdminMessagingTemplateOut): string {
  const suffix =
    template.kind === "PREDEFINED"
      ? uiText(language, "admin.quote_detail.template_system")
      : uiText(language, "admin.quote_detail.template_custom");
  return `${template.name} · ${suffix}`;
}

function messagingTemplateLabelByRef(
  language: UiLanguage,
  templates: AdminMessagingTemplateOut[],
  templateRef: string | null | undefined,
): string {
  const normalizedRef = String(templateRef || "").trim();
  if (!normalizedRef) {
    return uiText(language, "admin.messaging_schedule.no_template");
  }
  const match = templates.find((template) => messagingTemplateRef(template) === normalizedRef);
  return match ? messagingTemplateOptionLabel(language, match) : normalizedRef;
}

function messagingChannelLabel(language: UiLanguage, channel: string): string {
  if (channel === "SMS") {
    return uiText(language, "admin.messaging_templates.channel_sms");
  }
  if (channel === "GROUP_NOTE") {
    return uiText(language, "admin.messaging_templates.channel_group_note");
  }
  return uiText(language, "admin.messaging_templates.channel_email");
}

function formatQuoteReminderDelay(hours: number): string {
  if (hours > 0 && hours % 24 === 0) {
    return `J-${hours / 24}`;
  }
  return `${hours} h`;
}

function formatQuoteReminderDelayList(values: number[] | null | undefined, fallbackHours: number): string {
  const normalized = Array.from(
    new Set(
      (values || [])
        .map((value) => Number(value))
        .filter((value) => Number.isFinite(value) && value > 0),
    ),
  ).sort((left, right) => right - left);
  if (normalized.length === 0) {
    normalized.push(fallbackHours);
  }
  return normalized.map((value) => formatQuoteReminderDelay(value)).join(", ");
}

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function isVacationServiceCode(serviceCode: string | null | undefined): boolean {
  return (serviceCode ?? "").trim().toUpperCase().startsWith("VACATION");
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
    value === "params-referrals" ||
    value === "params-messaging" ||
    value === "formulas" ||
    value === "quotes" ||
    value === "calendars" ||
    value === "activities" ||
    value === "legal-entities" ||
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
    case "params-referrals":
    case "params-messaging":
      return "params";
    case "formulas":
    case "quotes":
    case "calendars":
    case "activities":
    case "legal-entities":
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

function parseMessagingTab(raw: string): MessagingTab {
  const value = raw.trim().toLowerCase();
  if (
    value === "settings" ||
    value === "scheduled" ||
    value === "predefined-email" ||
    value === "predefined-sms" ||
    value === "custom-email" ||
    value === "custom-sms" ||
    value === "group-notes"
  ) {
    return value;
  }
  return "settings";
}

function activityModeLabel(mode: string, language: UiLanguage): string {
  const normalized = mode.trim().toUpperCase();
  if (normalized === "ONLINE") {
    return uiText(language, "admin.professor_detail.mode_online");
  }
  if (normalized === "ONSITE") {
    return uiText(language, "admin.professor_detail.mode_onsite");
  }
  return uiText(language, "admin.professor_detail.mode_all");
}

function formatMoney(amountRaw: string | null, currency: string | null, locale: string): string {
  if (!amountRaw) {
    return "-";
  }

  const amount = Number(amountRaw);
  const normalizedCurrency = currency || "EUR";
  if (!Number.isFinite(amount)) {
    return `${amountRaw} ${normalizedCurrency}`;
  }

  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: normalizedCurrency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${normalizedCurrency}`;
  }
}

function yesNoLabel(language: UiLanguage, value: boolean): string {
  return uiText(language, value ? "common.yes" : "common.no");
}

function pickText(language: UiLanguage, fr: string, en: string): string {
  return language === "en" ? en : fr;
}

const REFERRAL_CONFIG_TEXT: Record<UiLanguage, Record<string, string>> = {
  fr: {
    load_error: "Parametres de parrainage indisponibles : {message}",
    title: "Parrainage",
    load_unavailable: "Impossible de charger les parametres de parrainage.",
    enabled: "Activer le programme de parrainage",
    currency: "Devise",
    threshold: "Seuil d'encaissement",
    threshold_help: "0.50 = avoir genere lorsque 50% de la facture annuelle est encaisse.",
    announcement_email: "Email d'information au parrain",
    credit_email: "Email lors de la generation de l'avoir",
    category: "Categorie",
    label: "Libelle",
    amount: "Montant",
    active: "Actif",
    category_online: "En ligne",
    category_home: "Domicile",
    help: "Paris regroupe Richelieu, Assas, Pompe et Scheffer. Les inscriptions a domicile, en ligne et Bar-le-Duc peuvent avoir un montant distinct.",
  },
  en: {
    load_error: "Referral settings unavailable: {message}",
    title: "Referrals",
    load_unavailable: "Unable to load referral settings.",
    enabled: "Enable referral program",
    currency: "Currency",
    threshold: "Cashing threshold",
    threshold_help: "0.50 = credit is generated once 50% of the annual invoice has been cashed.",
    announcement_email: "Information email to the referrer",
    credit_email: "Email when the credit is generated",
    category: "Category",
    label: "Label",
    amount: "Amount",
    active: "Active",
    category_online: "Online",
    category_home: "Home",
    help: "Paris includes Richelieu, Assas, Pompe, and Scheffer. Home, online, and Bar-le-Duc registrations can each have a distinct amount.",
  },
};

function referralConfigText(language: UiLanguage, key: string, values?: Record<string, string | number>): string {
  const template = REFERRAL_CONFIG_TEXT[language][key] || REFERRAL_CONFIG_TEXT.fr[key] || key;
  if (!values) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (_match, token) => String(values[token] ?? ""));
}

function catalogRequestStatusLabel(status: string, language: UiLanguage): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "PROCESSING") {
    return uiText(language, "admin.products.request_status_processing");
  }
  if (normalized === "REJECTED") {
    return uiText(language, "admin.products.request_status_rejected");
  }
  if (normalized === "INVOICE_TO_SEND") {
    return uiText(language, "admin.products.request_status_invoice_to_send");
  }
  if (normalized === "TO_DELIVER") {
    return uiText(language, "admin.products.request_status_to_deliver");
  }
  if (normalized === "DELIVERED") {
    return uiText(language, "admin.products.request_status_delivered");
  }
  return normalized || "-";
}

function catalogRequestSourceLabel(source: string, language: UiLanguage): string {
  const normalized = source.trim().toUpperCase();
  if (normalized === "PROFESSOR") {
    return uiText(language, "admin.products.request_source_professor");
  }
  if (normalized === "ADMIN") {
    return uiText(language, "admin.products.request_source_admin");
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
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const params = searchParams ?? {};
  const requestedSection = readParam(params, "section").trim();
  if (requestedSection === "params-professor-default-grid") {
    const redirectParams = new URLSearchParams();
    const gridPeriod = readParam(params, "grid_period").trim();
    const ok = readParam(params, "ok").trim();
    const error = readParam(params, "error").trim();
    if (gridPeriod) {
      redirectParams.set("grid_period", gridPeriod);
    }
    if (ok) {
      redirectParams.set("ok", ok);
    }
    if (error) {
      redirectParams.set("error", error);
    }
    const suffix = redirectParams.toString();
    redirect(suffix ? `/admin/teacher-invoicing/salary-grid?${suffix}` : "/admin/teacher-invoicing/salary-grid");
  }
  const section = parseSection(requestedSection);
  if (section === "products") {
    redirect("/admin/products");
  }
  if (section === "formulas") {
    const redirectParams = new URLSearchParams();
    const ok = readParam(params, "ok").trim();
    const error = readParam(params, "error").trim();
    if (ok) {
      redirectParams.set("ok", ok);
    }
    if (error) {
      redirectParams.set("error", error);
    }
    const suffix = redirectParams.toString();
    redirect(suffix ? `/admin/config/formulas?${suffix}` : "/admin/config/formulas");
  }
  if (section === "quotes") {
    const redirectParams = new URLSearchParams();
    const tab = readParam(params, "tab").trim();
    const ok = readParam(params, "ok").trim();
    const error = readParam(params, "error").trim();
    if (tab) {
      redirectParams.set("tab", tab);
    }
    if (ok) {
      redirectParams.set("ok", ok);
    }
    if (error) {
      redirectParams.set("error", error);
    }
    const suffix = redirectParams.toString();
    if (tab.toLowerCase() === "calendars") {
      redirect(suffix ? `/admin/config/calendars?${suffix}` : "/admin/config/calendars");
    }
    redirect(suffix ? `/admin/config/quotes?${suffix}` : "/admin/config/quotes");
  }
  if (section === "calendars") {
    const redirectParams = new URLSearchParams();
    const ok = readParam(params, "ok").trim();
    const error = readParam(params, "error").trim();
    if (ok) {
      redirectParams.set("ok", ok);
    }
    if (error) {
      redirectParams.set("error", error);
    }
    const suffix = redirectParams.toString();
    redirect(suffix ? `/admin/config/calendars?${suffix}` : "/admin/config/calendars");
  }
  const mainSection = toMainSection(section);

  const [
    meResult,
    accountResult,
    subscriptionsResult,
    paymentMethodsResult,
    productCategoriesResult,
    referralProgramResult,
    paymentProviderResult,
    messagingSettingsResult,
    invoiceTemplateResult,
    invoiceNumberingResult,
    emailPredefinedTemplatesResult,
    smsPredefinedTemplatesResult,
    customTemplatesResult,
    quoteTemplateVariablesResult,
    activitiesResult,
    legalEntitiesResult,
    creditTypesResult,
    externalContentSettingsResult,
    externalContentCoursesResult,
    catalogCategoriesResult,
    catalogProductsResult,
    catalogKitsResult,
  ] =
    await Promise.all([
    backendRequest<UserOut>("/api/v1/auth/me", {}, token),
    backendRequest<AdminConfigAccountOut>("/api/v1/admin/config/account", {}, token),
    backendRequest<AdminSubscriptionSettingsOut>("/api/v1/admin/config/subscriptions", {}, token),
    backendRequest<AdminPaymentMethodsOut>("/api/v1/admin/config/payment-methods", {}, token),
    backendRequest<AdminProductCategoriesOut>("/api/v1/admin/config/product-categories", {}, token),
    backendRequest<AdminReferralProgramSettingsOut>("/api/v1/admin/config/referral-program", {}, token),
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
    backendRequest<QuoteTemplateVariableOut[]>("/api/v1/quote-template-variables", {}, token),
    backendRequest<AdminActivityOut[]>("/api/v1/admin/activities?include_inactive=true", {}, token),
    backendRequest<AdminLegalEntityOut[]>("/api/v1/admin/legal-entities?include_inactive=true", {}, token),
    backendRequest<AdminCreditTypeOut[]>("/api/v1/admin/credit-types?include_inactive=true", {}, token),
    backendRequest<AdminExternalContentSettingsOut>("/api/v1/admin/config/external-content/wordpress-learndash", {}, token),
    backendRequest<AdminExternalContentCourseOut[]>("/api/v1/admin/external-content/courses", {}, token),
    backendRequest<AdminCatalogCategoryOut[]>("/api/v1/admin/config/catalog/categories?include_inactive=true", {}, token),
    backendRequest<AdminCatalogProductOut[]>("/api/v1/admin/config/catalog/products?include_inactive=true", {}, token),
    backendRequest<AdminCatalogKitOut[]>("/api/v1/admin/config/catalog/kits?include_inactive=true", {}, token),
  ]);

  const language = meResult.ok ? normalizeUiLanguage(meResult.data.preferred_language) : "fr";
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const locale = localeForUiLanguage(language);
  const configNavLabel = (fallback: string, labelKey?: string): string => (labelKey ? t(labelKey) : fallback);
  const loadErrors: string[] = [];

  let planningLocations: LocationOut[] = [];
  let integrationLocations: LocationOut[] = [];
  const planningActivitiesByLocationId = new Map<string, AdminPlanningActivitiesOut>();

  if (mainSection === "activities" || mainSection === "integrations") {
    const locationsResult = await backendRequest<LocationOut[]>("/api/v1/locations?active=true", {}, token);
    if (locationsResult.ok) {
      integrationLocations = [...locationsResult.data].sort((left, right) => left.name.localeCompare(right.name, "fr"));
      if (mainSection === "activities") {
        planningLocations = integrationLocations;
        const planningActivityResults = await Promise.all(
          planningLocations.map((location) =>
            backendRequest<AdminPlanningActivitiesOut>(`/api/v1/admin/plannings/${location.id}/activities`, {}, token),
          ),
        );
        planningActivityResults.forEach((result, index) => {
          const location = planningLocations[index];
          if (result.ok) {
            planningActivitiesByLocationId.set(location.id, result.data);
            return;
          }
          loadErrors.push(t("admin.config.load_planning_activities", { name: location.name, message: result.message }));
        });
      }
    } else {
      loadErrors.push(t("admin.config.load_locations", { message: locationsResult.message }));
    }
  }

  const account = accountResult.ok
    ? accountResult.data
    : (() => {
        loadErrors.push(t("admin.config.load_account_info", { message: accountResult.message }));
        return null;
      })();

  const subscriptions = subscriptionsResult.ok
    ? subscriptionsResult.data
    : (() => {
        loadErrors.push(t("admin.config.load_subscription_settings", { message: subscriptionsResult.message }));
        return null;
      })();

  const paymentMethods = paymentMethodsResult.ok
    ? paymentMethodsResult.data.methods
    : (() => {
        loadErrors.push(t("admin.formulas.load_payment_methods", { message: paymentMethodsResult.message }));
        return [] as AdminPaymentMethodsOut["methods"];
    })();

  const paymentProvider = paymentProviderResult.ok
    ? paymentProviderResult.data
    : (() => {
        loadErrors.push(t("admin.config.load_payment_provider", { message: paymentProviderResult.message }));
        return null;
      })();
  const referralProgram = referralProgramResult.ok
    ? referralProgramResult.data
    : (() => {
        loadErrors.push(referralConfigText(language, "load_error", { message: referralProgramResult.message }));
        return null;
      })();
  const productCategories = productCategoriesResult.ok
    ? productCategoriesResult.data
    : (() => {
        loadErrors.push(t("admin.products.load_legacy_categories_error", { message: productCategoriesResult.message }));
        return { categories: [], updated_at: null } as AdminProductCategoriesOut;
      })();
  const messagingSettings = messagingSettingsResult.ok
    ? messagingSettingsResult.data
    : (() => {
        loadErrors.push(t("admin.messaging_settings.load_settings", { message: messagingSettingsResult.message }));
        return null;
      })();
  const invoiceTemplate = invoiceTemplateResult.ok
    ? invoiceTemplateResult.data
    : (() => {
        loadErrors.push(t("admin.billing.load_invoice_template", { message: invoiceTemplateResult.message }));
        return null;
      })();
  const invoiceNumbering = invoiceNumberingResult.ok
    ? invoiceNumberingResult.data
    : (() => {
        loadErrors.push(t("admin.billing.load_invoice_numbering", { message: invoiceNumberingResult.message }));
        return null;
      })();
  const emailPredefinedTemplates = emailPredefinedTemplatesResult.ok
    ? emailPredefinedTemplatesResult.data
    : (() => {
        loadErrors.push(t("admin.messaging_settings.load_predefined_email", { message: emailPredefinedTemplatesResult.message }));
        return [] as AdminMessagingTemplateOut[];
      })();
  const smsPredefinedTemplates = smsPredefinedTemplatesResult.ok
    ? smsPredefinedTemplatesResult.data
    : (() => {
        loadErrors.push(t("admin.messaging_settings.load_predefined_sms", { message: smsPredefinedTemplatesResult.message }));
        return [] as AdminMessagingTemplateOut[];
      })();
  const customTemplates = customTemplatesResult.ok
    ? customTemplatesResult.data
    : (() => {
        loadErrors.push(t("admin.messaging_settings.load_custom_templates", { message: customTemplatesResult.message }));
        return [] as AdminMessagingTemplateOut[];
      })();
  const quoteTemplateVariables = quoteTemplateVariablesResult.ok
    ? quoteTemplateVariablesResult.data
    : (() => {
        loadErrors.push(t("admin.messaging_settings.load_quote_variables", { message: quoteTemplateVariablesResult.message }));
        return [] as QuoteTemplateVariableOut[];
      })();

  const activities = activitiesResult.ok
    ? activitiesResult.data
    : (() => {
        loadErrors.push(t("admin.config.load_activities", { message: activitiesResult.message }));
        return [] as AdminActivityOut[];
      })();
  const legalEntities = legalEntitiesResult.ok
    ? legalEntitiesResult.data
    : (() => {
        loadErrors.push(t("admin.legal_entities.load", { message: legalEntitiesResult.message }));
        return [] as AdminLegalEntityOut[];
      })();
  const creditTypes = creditTypesResult.ok
    ? creditTypesResult.data
    : (() => {
        loadErrors.push(t("admin.formulas.load_credit_types", { message: creditTypesResult.message }));
        return [] as AdminCreditTypeOut[];
      })();
  const externalContentSettings = externalContentSettingsResult.ok
    ? externalContentSettingsResult.data
    : (() => {
        loadErrors.push(
          t("admin.config.load_external_content_settings", { message: externalContentSettingsResult.message }),
        );
        return {
          base_url: "",
          courses_endpoint: "",
          resolved_endpoint_url: null,
          bearer_token_configured: false,
          bearer_token_masked: "",
          timeout_seconds: 20,
          updated_at: null,
        } as AdminExternalContentSettingsOut;
      })();
  const externalContentCourses = externalContentCoursesResult.ok
    ? externalContentCoursesResult.data
    : (() => {
        loadErrors.push(t("admin.config.load_external_content_courses", { message: externalContentCoursesResult.message }));
        return [] as AdminExternalContentCourseOut[];
      })();
  const catalogCategories = catalogCategoriesResult.ok
    ? catalogCategoriesResult.data
    : (() => {
        loadErrors.push(t("admin.products.load_catalog_categories_error", { message: catalogCategoriesResult.message }));
        return [] as AdminCatalogCategoryOut[];
      })();
  const catalogProducts = catalogProductsResult.ok
    ? catalogProductsResult.data
    : (() => {
        loadErrors.push(t("admin.products.load_catalog_products_error", { message: catalogProductsResult.message }));
        return [] as AdminCatalogProductOut[];
      })();
  const catalogKits = catalogKitsResult.ok
    ? catalogKitsResult.data
    : (() => {
        loadErrors.push(t("admin.catalog.load_kits_error", { message: catalogKitsResult.message }));
        return [] as AdminCatalogKitOut[];
      })();
  const activeCatalogCategories = catalogCategories.filter((row) => row.active);
  const activeCatalogProducts = catalogProducts.filter((row) => row.active);
  const activityStats = {
    total: activities.length,
    active: activities.filter((activity) => activity.active).length,
    online: activities.filter((activity) => activity.mode === "ONLINE").length,
    unpriced: activities.filter((activity) => !activity.default_course_rate_ttc && !activity.default_hourly_rate).length,
  };

  const accountAllowedCurrencies = account?.allowed_currencies?.length ? account.allowed_currencies : ["EUR", "USD"];
  const accountDefaultCurrency =
    account && accountAllowedCurrencies.includes(account.default_currency) ? account.default_currency : accountAllowedCurrencies[0] ?? "EUR";
  const accountClientBalanceDefaultDateMode =
    account?.client_balance_default_date_mode === "PACKAGE_END" ? "PACKAGE_END" : "TODAY";
  const createActivityModalOpen = readParam(params, "new_activity") === "1";
  const selectedActivityId = readParam(params, "activity_id");
  const selectedActivity = activities.find((activity) => activity.id === selectedActivityId) ?? null;
  const selectedActivityIsVacation = isVacationServiceCode(selectedActivity?.service_code);
  const selectedActivityIsStudentless = selectedActivity ? !selectedActivity.allows_student_bookings : false;
  const activityPlanningCountById = new Map<string, number>();
  planningActivitiesByLocationId.forEach((planning) => {
    planning.selected_activity_ids.forEach((activityId) => {
      activityPlanningCountById.set(activityId, (activityPlanningCountById.get(activityId) ?? 0) + 1);
    });
  });
  const manageablePlanningLocations = planningLocations.filter((location) => planningActivitiesByLocationId.has(location.id));
  const activityPlanningLocations = manageablePlanningLocations.map((location) => {
    const planning = planningActivitiesByLocationId.get(location.id);
    const selectedIds = planning?.selected_activity_ids ?? [];
    return {
      locationId: location.id,
      locationName: location.name,
      selectedActivityCount: selectedIds.length,
      selectedForCurrentActivity: selectedActivity ? selectedIds.includes(selectedActivity.id) : false,
    } satisfies ActivityPlanningLocationOption;
  });
  const createActivityDefaultPlanningLocationIds = activityPlanningLocations.map((location) => location.locationId);
  const selectedActivityPlanningLocationIds = activityPlanningLocations
    .filter((location) => location.selectedForCurrentActivity)
    .map((location) => location.locationId);
  const selectedActivityContentCourseIds = selectedActivity?.content_course_ids ?? [];
  const createLegalEntityModalOpen = readParam(params, "new_legal_entity") === "1";
  const selectedLegalEntityId = readParam(params, "legal_entity_id");
  const selectedLegalEntity = legalEntities.find((entity) => entity.id === selectedLegalEntityId) ?? null;
  const activeLegalEntities = legalEntities.filter((entity) => entity.is_active);
  const legalEntityStats = {
    total: legalEntities.length,
    active: activeLegalEntities.length,
  };
  const createCreditTypeModalOpen = readParam(params, "new_credit_type") === "1";
  const selectedCreditTypeId = readParam(params, "credit_type_id");
  const selectedCreditType = creditTypes.find((creditType) => creditType.id === selectedCreditTypeId) ?? null;
  const activeCreditTypes = creditTypes.filter((creditType) => creditType.active);
  const creditTypeStats = {
    total: creditTypes.length,
    active: activeCreditTypes.length,
    unlinked: creditTypes.filter((creditType) => creditType.activity_count === 0).length,
  };
  const messagingTab = parseMessagingTab(readParam(params, "messaging_tab"));
  const messagingModalMode = readParam(params, "messaging_modal");
  const newCustomTemplateChannelRaw = readParam(params, "new_template_channel").toUpperCase();
  const newCustomTemplateChannel =
    newCustomTemplateChannelRaw === "SMS"
      ? "SMS"
      : newCustomTemplateChannelRaw === "GROUP_NOTE"
      ? "GROUP_NOTE"
      : "EMAIL";
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
  const customGroupNoteTemplates = customTemplates.filter((template) => template.channel === "GROUP_NOTE");
  const activeEmailTemplates = [...emailPredefinedTemplates, ...customEmailTemplates]
    .filter((template) => template.active)
    .sort((left, right) => left.name.localeCompare(right.name, "fr"));
  const activeSmsTemplates = [...smsPredefinedTemplates, ...customSmsTemplates]
    .filter((template) => template.active)
    .sort((left, right) => left.name.localeCompare(right.name, "fr"));
  const quoteSendTemplates = activeEmailTemplates.filter((template) => template.usage_contexts.includes("QUOTE_SEND"));
  const quoteReminderTemplates = activeEmailTemplates.filter((template) => template.usage_contexts.includes("QUOTE_REMINDER"));
  const quoteCancelTemplates = activeEmailTemplates.filter((template) => template.usage_contexts.includes("QUOTE_CANCEL"));
  const quoteExpiredTemplates = activeEmailTemplates.filter((template) => template.usage_contexts.includes("QUOTE_EXPIRED"));
  const quoteApprovedTemplates = activeEmailTemplates.filter((template) => template.usage_contexts.includes("QUOTE_APPROVED"));
  const quoteRejectedTemplates = activeEmailTemplates.filter((template) => template.usage_contexts.includes("QUOTE_REJECTED"));
  const quoteChangeRequestedTemplates = activeEmailTemplates.filter((template) =>
    template.usage_contexts.includes("QUOTE_CHANGE_REQUESTED")
  );
  const quoteSendSmsTemplates = activeSmsTemplates.filter((template) => template.usage_contexts.includes("QUOTE_SEND"));
  const quoteReminderSmsTemplates = activeSmsTemplates.filter((template) => template.usage_contexts.includes("QUOTE_REMINDER"));
  const quoteCancelSmsTemplates = activeSmsTemplates.filter((template) => template.usage_contexts.includes("QUOTE_CANCEL"));
  const quoteExpiredSmsTemplates = activeSmsTemplates.filter((template) => template.usage_contexts.includes("QUOTE_EXPIRED"));
  const allMessagingTemplates = [...emailPredefinedTemplates, ...smsPredefinedTemplates, ...customTemplates];
  const scheduledMessagingGroups = messagingSettings
    ? [
        {
          theme: t("admin.messaging_schedule.theme_quotes"),
          rows: [
            {
              name: t("admin.messaging_schedule.quote_reminder"),
              trigger: t("admin.messaging_schedule.quote_reminder_trigger", {
                delay: formatQuoteReminderDelayList(
                  messagingSettings.quote_reminder_lead_hours_values,
                  messagingSettings.quote_reminder_lead_hours,
                ),
                time: messagingSettings.quote_daily_job_local_time || "07:00",
              }),
              channel: "EMAIL",
              active: messagingSettings.quote_reminder_enabled,
              template: messagingTemplateLabelByRef(language, allMessagingTemplates, messagingSettings.quote_reminder_template_ref),
            },
            {
              name: t("admin.messaging_schedule.quote_reminder"),
              trigger: t("admin.messaging_schedule.quote_reminder_trigger", {
                delay: formatQuoteReminderDelayList(
                  messagingSettings.quote_reminder_lead_hours_values,
                  messagingSettings.quote_reminder_lead_hours,
                ),
                time: messagingSettings.quote_daily_job_local_time || "07:00",
              }),
              channel: "SMS",
              active: messagingSettings.quote_reminder_sms_enabled,
              template: messagingTemplateLabelByRef(language, allMessagingTemplates, messagingSettings.quote_reminder_sms_template_ref),
            },
            {
              name: t("admin.messaging_schedule.quote_expired"),
              trigger: t("admin.messaging_schedule.quote_expired_trigger", {
                time: messagingSettings.quote_daily_job_local_time || "07:00",
              }),
              channel: "EMAIL",
              active: messagingSettings.quote_expired_notification_enabled,
              template: messagingTemplateLabelByRef(language, allMessagingTemplates, messagingSettings.quote_expired_template_ref),
            },
            {
              name: t("admin.messaging_schedule.quote_expired"),
              trigger: t("admin.messaging_schedule.quote_expired_trigger", {
                time: messagingSettings.quote_daily_job_local_time || "07:00",
              }),
              channel: "SMS",
              active: messagingSettings.quote_expired_sms_notification_enabled,
              template: messagingTemplateLabelByRef(language, allMessagingTemplates, messagingSettings.quote_expired_sms_template_ref),
            },
            {
              name: t("admin.messaging_schedule.quote_auto_cancel"),
              trigger: t("admin.messaging_schedule.quote_auto_cancel_trigger", {
                delay: messagingSettings.quote_auto_cancel_delay_hours,
              }),
              channel: "EMAIL",
              active: messagingSettings.quote_auto_cancel_enabled && messagingSettings.quote_cancel_notification_enabled,
              template: messagingTemplateLabelByRef(language, allMessagingTemplates, messagingSettings.quote_cancel_template_ref),
            },
            {
              name: t("admin.messaging_schedule.quote_auto_cancel"),
              trigger: t("admin.messaging_schedule.quote_auto_cancel_trigger", {
                delay: messagingSettings.quote_auto_cancel_delay_hours,
              }),
              channel: "SMS",
              active: messagingSettings.quote_auto_cancel_enabled && messagingSettings.quote_cancel_sms_notification_enabled,
              template: messagingTemplateLabelByRef(language, allMessagingTemplates, messagingSettings.quote_cancel_sms_template_ref),
            },
          ],
        },
        {
          theme: t("admin.messaging_schedule.theme_invoices"),
          rows: [
            {
              name: t("admin.messaging_schedule.invoice_due_reminder"),
              trigger: t("admin.messaging_schedule.invoice_due_reminder_trigger"),
              channel: "EMAIL",
              active: true,
              template: messagingTemplateLabelByRef(language, allMessagingTemplates, "predefined:INVOICE_REMINDER"),
            },
            {
              name: t("admin.messaging_schedule.invoice_sms"),
              trigger: t("admin.messaging_schedule.invoice_sms_trigger"),
              channel: "SMS",
              active: false,
              statusLabel: t("admin.messaging_schedule.status_manual"),
              template: messagingTemplateLabelByRef(language, allMessagingTemplates, "predefined:SMS_INVOICE_REMINDER"),
            },
          ],
        },
      ]
    : [];
  const quoteTemplateVariablesByCategory = quoteTemplateVariables.reduce<Record<string, QuoteTemplateVariableOut[]>>((acc, item) => {
    const key = item.category || t("admin.messaging_settings.variables_other");
    if (!acc[key]) {
      acc[key] = [];
    }
    acc[key].push(item);
    return acc;
  }, {});

  const activityById = new Map(activities.map((activity) => [activity.id, activity]));

  const okMessage = readParam(params, "ok");
  const errorMessage = readParam(params, "error");
  const selectedIntegrationActivityId = readParam(params, "integration_course_type_id").trim();
  const selectedIntegrationLocationId = readParam(params, "integration_location_id").trim();
  const selectedIntegrationDate = readParam(params, "integration_date").trim();

  const messagingListPath = buildConfigHref("params-messaging", { messaging_tab: messagingTab });

  const placeholderTitleKeyBySection: Record<
    Exclude<
      ConfigSection,
      | "params-account"
      | "params-subscriptions"
      | "params-payments"
      | "params-referrals"
      | "params-messaging"
      | "formulas"
      | "quotes"
      | "calendars"
      | "activities"
      | "legal-entities"
      | "credit-types"
    >,
    string
  > = {
    promo: "admin.breadcrumb.promo",
    products: "admin.breadcrumb.products",
    "payment-rules": "admin.breadcrumb.payment_rules",
    integrations: "admin.breadcrumb.integrations",
    "purchase-link": "admin.breadcrumb.purchase_link",
  };

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h2>{t("admin.nav.config")}</h2>
        <p className="muted">{t("admin.config.page_subtitle")}</p>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {loadErrors.length > 0 ? (
        <section className="card">
          <h3>{t("admin.config.loading_errors")}</h3>
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
            {MAIN_NAV_GROUPS.map((group) => (
              <section key={group.titleKey} className="config-nav-group">
                <div className="config-nav-group-head">
                  <strong>{t(group.titleKey)}</strong>
                  <small>{t(group.descriptionKey)}</small>
                </div>
                <div className="config-nav-group-links">
                  {group.items.map((item) => {
                    const isActive = mainSection === item.key;
                    const href =
                      item.key === "formulas"
                        ? "/admin/config/formulas"
                        : item.key === "quotes"
                        ? "/admin/config/quotes"
                        : item.key === "calendars"
                        ? "/admin/config/calendars"
                        : buildConfigHref(item.section);

                    return (
                      <Link key={item.key} className={`config-main-link ${isActive ? "active" : ""}`} href={href}>
                        <span>{configNavLabel(item.label, item.labelKey)}</span>
                        {item.descriptionKey ? <small>{t(item.descriptionKey)}</small> : null}
                      </Link>
                    );
                  })}
                </div>
              </section>
            ))}
          </nav>

          {mainSection === "params" ? (
            <nav className="config-sub-nav" aria-label={t("admin.config.nav.params_submenu")}>
              <strong className="config-sub-nav-title">{t("admin.config.nav.params_submenu")}</strong>
              {PARAMS_SUBNAV_ITEMS.map((item) => (
                <Link
                  key={item.key}
                  className={`config-sub-link ${section === item.key ? "active" : ""}`}
                  href={buildConfigHref(
                    item.key,
                    item.key === "params-messaging" ? { messaging_tab: messagingTab } : {},
                  )}
                >
                  {configNavLabel(item.label, item.labelKey)}
                </Link>
              ))}
            </nav>
          ) : null}
        </aside>

        <div className="config-main-content">
          {section === "params-account" ? (
            <section className="card">
              <h3>{t("admin.breadcrumb.account_info")}</h3>
              {!account ? (
                <p className="muted">{t("admin.config.account.load_error")}</p>
              ) : (
                <form action={updateAdminConfigAccountAction} className="grid cols-2 config-form-grid" encType="multipart/form-data">
                  <label>
                    {t("admin.config.account.contact_first_name")}
                    <input type="text" name="contact_first_name" defaultValue={account.contact_first_name} maxLength={100} />
                  </label>
                  <label>
                    {t("admin.config.account.contact_last_name")}
                    <input type="text" name="contact_last_name" defaultValue={account.contact_last_name} maxLength={100} />
                  </label>

                  <label>
                    {t("common.email")}
                    <input type="email" name="contact_email" defaultValue={account.contact_email} maxLength={255} />
                  </label>
                  <label>
                    {t("admin.config.account.contact_phone")}
                    <input type="text" name="contact_phone" defaultValue={account.contact_phone} maxLength={40} />
                  </label>

                  <label>
                    {t("admin.config.account.company_name")}
                    <input type="text" name="company_name" defaultValue={account.company_name} maxLength={255} />
                  </label>
                  <label>
                    {t("admin.config.account.club_name")}
                    <input type="text" name="club_name" defaultValue={account.club_name} maxLength={255} />
                  </label>

                  <label>
                    {t("admin.config.account.siret")}
                    <input type="text" name="siret" defaultValue={account.siret} maxLength={30} />
                  </label>
                  <label>
                    {t("admin.config.account.vat_number")}
                    <input type="text" name="vat_number" defaultValue={account.vat_number} maxLength={50} />
                  </label>

                  <label>
                    {t("admin.config.account.vat_default_rate")}
                    <input type="text" name="vat_default_rate" defaultValue={account.vat_default_rate} maxLength={20} />
                  </label>
                  <label>
                    {t("admin.config.account.website")}
                    <input type="text" name="website" defaultValue={account.website} maxLength={255} />
                  </label>

                  <input type="hidden" name="logo_data_url" value={account.logo_data_url || ""} />
                  <label className="span-2">
                    {t("admin.config.account.logo_label")}
                    <input type="file" name="logo_file" accept="image/jpeg,image/jpg" />
                    {account.logo_data_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={account.logo_data_url}
                        alt={t("admin.config.account.logo_alt")}
                        style={{ marginTop: 10, maxHeight: 64, width: "auto", border: "1px solid #d8c8ab", borderRadius: 8, padding: 6, background: "#fff" }}
                      />
                    ) : (
                      <small className="muted">{t("admin.config.account.logo_empty")}</small>
                    )}
                  </label>
                  <label className="checkline span-2">
                    <input type="checkbox" name="clear_logo" value="on" />
                    {t("admin.config.account.clear_logo")}
                  </label>

                  <label className="span-2">
                    {t("admin.config.account.address")}
                    <input type="text" name="address_line" defaultValue={account.address_line} maxLength={255} />
                  </label>

                  <label>
                    {t("admin.config.account.postal_code")}
                    <input type="text" name="postal_code" defaultValue={account.postal_code} maxLength={20} />
                  </label>
                  <label>
                    {t("admin.config.account.city")}
                    <input type="text" name="city" defaultValue={account.city} maxLength={120} />
                  </label>

                  <label className="span-2">
                    {t("admin.config.account.country")}
                    <input type="text" name="country" defaultValue={account.country} maxLength={120} />
                  </label>

                  <label className="span-2">
                    {t("admin.config.account.client_balance_default_date_mode")}
                    <select name="client_balance_default_date_mode" defaultValue={accountClientBalanceDefaultDateMode}>
                      <option value="TODAY">{t("admin.config.account.client_balance_default_date_today")}</option>
                      <option value="PACKAGE_END">{t("admin.config.account.client_balance_default_date_package_end")}</option>
                    </select>
                    <small className="muted">{t("admin.config.account.client_balance_default_date_help")}</small>
                  </label>

                  <label className="span-2">
                    Titulaire du compte virement
                    <input type="text" name="bank_transfer_account_holder" defaultValue={account.bank_transfer_account_holder} maxLength={255} />
                  </label>
                  <label className="span-2">
                    IBAN virement
                    <input type="text" name="bank_transfer_iban" defaultValue={account.bank_transfer_iban} maxLength={80} />
                  </label>
                  <label>
                    BIC virement
                    <input type="text" name="bank_transfer_bic" defaultValue={account.bank_transfer_bic} maxLength={40} />
                  </label>

                  <fieldset className="span-2 config-currency-fieldset">
                    <legend>{t("admin.config.account.allowed_currencies")}</legend>
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
                      {t("admin.config.account.default_currency")}
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
                    {t("admin.config.account.legal_terms")}
                    <textarea name="legal_terms" defaultValue={account.legal_terms} rows={8} />
                  </label>

                  <div className="row span-2">
                    <button type="submit">{t("common.save")}</button>
                  </div>
                </form>
              )}
            </section>
          ) : null}

          {section === "params-subscriptions" ? (
            <section className="card">
              <h3>{t("admin.breadcrumb.subscription_settings")}</h3>
              {!subscriptions ? (
                <p className="muted">{t("admin.config.subscriptions.load_error")}</p>
              ) : (
                <form action={updateAdminConfigSubscriptionsAction} className="grid cols-2 config-form-grid">
                  <label>
                    {t("admin.config.subscriptions.direct_debit_day")}
                    <input
                      type="number"
                      name="direct_debit_day"
                      min={1}
                      max={28}
                      defaultValue={subscriptions.direct_debit_day === null ? "" : String(subscriptions.direct_debit_day)}
                    />
                  </label>
                  <label>
                    {t("admin.config.subscriptions.retry_first_delay_days")}
                    <input
                      type="number"
                      name="retry_first_delay_days"
                      min={1}
                      max={30}
                      defaultValue={String(subscriptions.retry_first_delay_days)}
                    />
                  </label>
                  <label>
                    {t("admin.config.subscriptions.retry_max_auto_attempts")}
                    <input
                      type="number"
                      name="retry_max_auto_attempts"
                      min={1}
                      max={10}
                      defaultValue={String(subscriptions.retry_max_auto_attempts)}
                    />
                  </label>
                  <label>
                    {t("admin.config.subscriptions.pre_termination_after_failed_attempts")}
                    <input
                      type="number"
                      name="retry_move_to_pre_termination_after_failed_attempts"
                      min={1}
                      max={10}
                      defaultValue={String(subscriptions.retry_move_to_pre_termination_after_failed_attempts)}
                    />
                  </label>

                  <div className="config-note-box">
                    <strong>{t("admin.config.subscriptions.note_title")}</strong>
                    <p className="muted">{t("admin.config.subscriptions.note_help")}</p>
                  </div>

                  <label className="checkline span-2">
                    <input type="checkbox" name="allow_card_subscriptions" defaultChecked={subscriptions.allow_card_subscriptions} />
                    {t("admin.config.subscriptions.allow_card_subscriptions")}
                  </label>
                  <label className="checkline span-2">
                    <input type="checkbox" name="add_contract_signature" defaultChecked={subscriptions.add_contract_signature} />
                    {t("admin.config.subscriptions.add_contract_signature")}
                  </label>
                  <label className="checkline span-2">
                    <input
                      type="checkbox"
                      name="close_expired_subscriptions"
                      defaultChecked={subscriptions.close_expired_subscriptions}
                    />
                    {t("admin.config.subscriptions.close_expired_subscriptions")}
                  </label>
                  <label className="checkline span-2">
                    <input
                      type="checkbox"
                      name="allow_promotional_start_period"
                      defaultChecked={subscriptions.allow_promotional_start_period}
                    />
                    {t("admin.config.subscriptions.allow_promotional_start_period")}
                  </label>
                  <label className="checkline span-2">
                    <input type="checkbox" name="allow_prorata_card" defaultChecked={subscriptions.allow_prorata_card} />
                    {t("admin.config.subscriptions.allow_prorata_card")}
                  </label>
                  <label className="checkline span-2">
                    <input type="checkbox" name="allow_prorata_sepa" defaultChecked={subscriptions.allow_prorata_sepa} />
                    {t("admin.config.subscriptions.allow_prorata_sepa")}
                  </label>
                  <label className="checkline span-2">
                    <input
                      type="checkbox"
                      name="online_resiliation_enabled"
                      defaultChecked={subscriptions.online_resiliation_enabled}
                    />
                    {t("admin.config.subscriptions.online_resiliation_enabled")}
                  </label>
                  <label className="checkline span-2">
                    <input
                      type="checkbox"
                      name="allow_booking_during_payment_alert"
                      defaultChecked={subscriptions.allow_booking_during_payment_alert}
                    />
                    {t("admin.config.subscriptions.allow_booking_during_payment_alert")}
                  </label>

                  <fieldset className="span-2 config-subsection">
                    <legend>{t("admin.config.subscriptions.notifications_fieldset")}</legend>
                    <label className="checkline">
                      <input
                        type="checkbox"
                        name="notify_success_customer_enabled"
                        defaultChecked={subscriptions.notify_success_customer_enabled}
                      />
                      {t("admin.config.subscriptions.notify_success_customer")}
                    </label>
                    <label className="checkline">
                      <input
                        type="checkbox"
                        name="notify_success_admin_enabled"
                        defaultChecked={subscriptions.notify_success_admin_enabled}
                      />
                      {t("admin.config.subscriptions.notify_success_admin")}
                    </label>
                    <label className="checkline">
                      <input
                        type="checkbox"
                        name="notify_first_failure_customer_enabled"
                        defaultChecked={subscriptions.notify_first_failure_customer_enabled}
                      />
                      {t("admin.config.subscriptions.notify_first_failure_customer")}
                    </label>
                    <label className="checkline">
                      <input
                        type="checkbox"
                        name="notify_first_failure_admin_enabled"
                        defaultChecked={subscriptions.notify_first_failure_admin_enabled}
                      />
                      {t("admin.config.subscriptions.notify_first_failure_admin")}
                    </label>
                    <label className="checkline">
                      <input
                        type="checkbox"
                        name="notify_final_failure_customer_enabled"
                        defaultChecked={subscriptions.notify_final_failure_customer_enabled}
                      />
                      {t("admin.config.subscriptions.notify_final_failure_customer")}
                    </label>
                    <label className="checkline">
                      <input
                        type="checkbox"
                        name="notify_final_failure_admin_enabled"
                        defaultChecked={subscriptions.notify_final_failure_admin_enabled}
                      />
                      {t("admin.config.subscriptions.notify_final_failure_admin")}
                    </label>
                  </fieldset>

                  <div className="row span-2">
                    <button type="submit">{t("common.save")}</button>
                  </div>
                </form>
              )}
            </section>
          ) : null}

          {section === "params-payments" ? (
            <>
              <section className="card">
                <h3>{t("admin.payments.psp_title")}</h3>
                {!paymentProvider ? (
                  <p className="muted">{t("admin.payments.psp_load_error")}</p>
                ) : (
                  <form action={updateAdminConfigPaymentProviderAction} className="grid cols-2 config-form-grid">
                    <label>
                      {t("admin.payments.provider")}
                      <select name="provider" defaultValue={paymentProvider.provider}>
                        <option value="PAYPLUG">Payplug</option>
                        <option value="MOLLIE">Mollie</option>
                        <option value="STRIPE">Stripe</option>
                      </select>
                    </label>
                    <label>
                      {t("admin.payments.environment")}
                      <select name="mode" defaultValue={paymentProvider.mode}>
                        <option value="TEST">{t("admin.payments.environment_test")}</option>
                        <option value="LIVE">{t("admin.payments.environment_live")}</option>
                      </select>
                    </label>

                    <label className="span-2">
                      {t("admin.payments.payplug_test_secret")}
                      <input
                        type="password"
                        name="payplug_test_secret"
                        placeholder={t("admin.payments.keep_existing_f")}
                        autoComplete="new-password"
                      />
                      <small className="muted">
                        {t("admin.payments.current_f", {
                          value: paymentProvider.payplug_test_secret_masked || t("admin.payments.not_configured_f"),
                        })}
                      </small>
                    </label>

                    <label className="span-2">
                      {t("admin.payments.payplug_live_secret")}
                      <input
                        type="password"
                        name="payplug_live_secret"
                        placeholder={t("admin.payments.keep_existing_f")}
                        autoComplete="new-password"
                      />
                      <small className="muted">
                        {t("admin.payments.current_f", {
                          value: paymentProvider.payplug_live_secret_masked || t("admin.payments.not_configured_f"),
                        })}
                      </small>
                    </label>

                    <label className="span-2">
                      {t("admin.payments.mollie_test_api_key")}
                      <input
                        type="password"
                        name="mollie_test_api_key"
                        placeholder={t("admin.payments.keep_existing_f")}
                        autoComplete="new-password"
                      />
                      <small className="muted">
                        {t("admin.payments.current_f", {
                          value: paymentProvider.mollie_test_api_key_masked || t("admin.payments.not_configured_f"),
                        })}
                      </small>
                    </label>

                    <label className="span-2">
                      {t("admin.payments.mollie_live_api_key")}
                      <input
                        type="password"
                        name="mollie_live_api_key"
                        placeholder={t("admin.payments.keep_existing_f")}
                        autoComplete="new-password"
                      />
                      <small className="muted">
                        {t("admin.payments.current_f", {
                          value: paymentProvider.mollie_live_api_key_masked || t("admin.payments.not_configured_f"),
                        })}
                      </small>
                    </label>

                    <label className="span-2">
                      {t("admin.payments.stripe_test_secret")}
                      <input
                        type="password"
                        name="stripe_test_secret"
                        placeholder={t("admin.payments.keep_existing_f")}
                        autoComplete="new-password"
                      />
                      <small className="muted">
                        {t("admin.payments.current_f", {
                          value: paymentProvider.stripe_test_secret_masked || t("admin.payments.not_configured_f"),
                        })}
                      </small>
                    </label>

                    <label className="span-2">
                      {t("admin.payments.stripe_live_secret")}
                      <input
                        type="password"
                        name="stripe_live_secret"
                        placeholder={t("admin.payments.keep_existing_f")}
                        autoComplete="new-password"
                      />
                      <small className="muted">
                        {t("admin.payments.current_f", {
                          value: paymentProvider.stripe_live_secret_masked || t("admin.payments.not_configured_f"),
                        })}
                      </small>
                    </label>

                    <label className="span-2">
                      {t("admin.payments.webhook_secret")}
                      <input
                        type="password"
                        name="webhook_secret"
                        placeholder={t("admin.payments.keep_existing_m")}
                        autoComplete="new-password"
                      />
                      <small className="muted">
                        {t("admin.payments.current_m", {
                          value: paymentProvider.webhook_secret_masked || t("admin.payments.not_configured_m"),
                        })}
                      </small>
                    </label>

                    <p className="muted span-2">
                      {t("admin.payments.subscription_capabilities")}{" "}
                      {paymentProvider.subscriptions_supported
                        ? paymentProvider.subscriptions_managed_by_psp
                          ? t("admin.payments.subscription_native")
                          : t("admin.payments.subscription_app_schedule")
                        : t("admin.payments.subscription_unsupported")}
                      . {paymentProvider.recommendation}
                    </p>

                    <div className="row span-2">
                      <button type="submit">{t("admin.payments.save_psp")}</button>
                    </div>
                  </form>
                )}
              </section>

              <section className="card">
                <h3>{t("admin.breadcrumb.payment_methods")}</h3>
                {!paymentMethodsResult.ok ? (
                  <p className="muted">{t("admin.payments.methods_load_error")}</p>
                ) : (
                  <form action={updateAdminConfigPaymentMethodsAction} className="grid config-payment-grid">
                    {paymentMethods.map((method) => (
                      <div key={method.code} className="config-payment-line">
                        <label className="checkline">
                          <input type="checkbox" name="enabled_codes" value={method.code} defaultChecked={method.enabled} />
                          <span>
                            <strong>{method.label}</strong>
                            <small className="muted"> ({method.code})</small>
                          </span>
                        </label>
                        {method.code === "BANK_TRANSFER" || method.code === "CHECK" || method.code === "CASH" ? (
                          <label>
                            {t("admin.payments.default_legal_entity")}
                            <select name={`legal_entity_for_${method.code}`} defaultValue={method.default_legal_entity_id ?? ""}>
                              <option value="">{t("admin.payments.no_legal_entity")}</option>
                              {activeLegalEntities.map((entity) => (
                                <option key={`${method.code}-${entity.id}`} value={entity.id}>
                                  {entity.name}
                                </option>
                              ))}
                            </select>
                          </label>
                        ) : null}
                      </div>
                    ))}

                    <div className="row">
                      <button type="submit">{t("common.save")}</button>
                    </div>
                  </form>
                )}
              </section>

              <section className="card">
                <h3>{t("admin.billing.title")}</h3>
                {!invoiceNumbering ? (
                  <p className="muted">{t("admin.billing.numbering_load_error")}</p>
                ) : (
                  <form action={updateAdminConfigInvoiceNumberingAction} className="grid config-form-grid">
                    <h4>{t("admin.billing.invoice_number_title")}</h4>
                    <label>
                      {t("admin.billing.number_format")}
                      <input
                        type="text"
                        name="format_pattern"
                        defaultValue={invoiceNumbering.format_pattern}
                        maxLength={120}
                        required
                      />
                    </label>
                    <p className="muted">{t("admin.billing.number_variables")}</p>
                    <label>
                      {t("admin.billing.next_number")}
                      <input
                        type="number"
                        name="next_number"
                        defaultValue={String(invoiceNumbering.next_number)}
                        min={1}
                        step={1}
                        required
                      />
                    </label>
                    <p className="muted">{t("admin.billing.preview", { value: invoiceNumbering.preview })}</p>
                    {invoiceNumbering.updated_at ? (
                      <p className="muted">
                        {t("admin.billing.updated_at", {
                          value: new Date(invoiceNumbering.updated_at).toLocaleString(locale),
                        })}
                      </p>
                    ) : null}
                    <div className="row">
                      <button type="submit">{t("admin.billing.save_numbering")}</button>
                    </div>
                  </form>
                )}
                <hr />
                {!invoiceTemplate ? (
                  <p className="muted">{t("admin.billing.template_load_error")}</p>
                ) : (
                  <form action={updateAdminConfigInvoiceTemplateAction} className="grid config-form-grid">
                    <p className="muted">{t("admin.billing.available_variables", { value: invoiceTemplate.variables_hint })}</p>
                    <label>
                      {t("admin.billing.invoice_body")}
                      <textarea name="body" defaultValue={invoiceTemplate.body} rows={14} required />
                    </label>
                    {invoiceTemplate.updated_at ? (
                      <p className="muted">
                        {t("admin.billing.updated_at", {
                          value: new Date(invoiceTemplate.updated_at).toLocaleString(locale),
                        })}
                      </p>
                    ) : null}
                    <div className="row">
                      <button type="submit">{t("admin.billing.save_template")}</button>
                    </div>
                  </form>
                )}
              </section>
            </>
          ) : null}

          {section === "params-referrals" ? (
            <section className="card">
              <h3>{referralConfigText(language, "title")}</h3>
              {!referralProgram ? (
                <p className="muted">{referralConfigText(language, "load_unavailable")}</p>
              ) : (
                <form action={updateAdminConfigReferralProgramAction} className="grid cols-2 config-form-grid">
                  <label className="checkline span-2">
                    <input type="checkbox" name="enabled" defaultChecked={referralProgram.enabled} />
                    <span>{referralConfigText(language, "enabled")}</span>
                  </label>
                  <label>
                    {referralConfigText(language, "currency")}
                    <input type="text" name="currency" defaultValue={referralProgram.currency || "EUR"} maxLength={3} required />
                  </label>
                  <label>
                    {referralConfigText(language, "threshold")}
                    <input
                      type="number"
                      name="trigger_ratio"
                      defaultValue={referralProgram.trigger_ratio || "0.50"}
                      min="0.01"
                      max="1"
                      step="0.01"
                      required
                    />
                    <small className="muted">{referralConfigText(language, "threshold_help")}</small>
                  </label>
                  <label className="checkline">
                    <input
                      type="checkbox"
                      name="announcement_email_enabled"
                      defaultChecked={referralProgram.announcement_email_enabled}
                    />
                    <span>{referralConfigText(language, "announcement_email")}</span>
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="credit_email_enabled" defaultChecked={referralProgram.credit_email_enabled} />
                    <span>{referralConfigText(language, "credit_email")}</span>
                  </label>

                  <div className="table-wrap span-2">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>{referralConfigText(language, "category")}</th>
                          <th>{referralConfigText(language, "label")}</th>
                          <th>{referralConfigText(language, "amount")}</th>
                          <th>{referralConfigText(language, "active")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[
                          ["PARIS", "Paris"],
                          ["BAR_LE_DUC", "Bar-le-Duc"],
                          ["ONLINE", referralConfigText(language, "category_online")],
                          ["DOMICILE", referralConfigText(language, "category_home")],
                        ].map(([code, fallbackLabel]) => {
                          const category = referralProgram.categories[code];
                          return (
                            <tr key={`referral-program-${code}`}>
                              <td>{fallbackLabel}</td>
                              <td>
                                <input
                                  type="text"
                                  name={`category_label_${code}`}
                                  defaultValue={category?.label || fallbackLabel}
                                  maxLength={80}
                                />
                              </td>
                              <td>
                                <input
                                  type="number"
                                  name={`category_amount_${code}`}
                                  defaultValue={category?.amount || "50.00"}
                                  min="0"
                                  step="0.01"
                                  required
                                />
                              </td>
                              <td>
                                <input type="checkbox" name={`category_active_${code}`} defaultChecked={category?.active ?? true} />
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  <p className="muted span-2">
                    {referralConfigText(language, "help")}
                  </p>
                  <div className="row span-2">
                    <button type="submit">{t("common.save")}</button>
                  </div>
                </form>
              )}
            </section>
          ) : null}

          {requestedSection === "products" ? (
            <>
              <section className="card">
                <h3>{t("admin.products.categories_title")}</h3>
                <p className="muted">{t("admin.products.categories_subtitle")}</p>
                <form action={createAdminCatalogCategoryAction} className="grid cols-4 config-form-grid">
                  <label>
                    {t("common.name")}
                    <input type="text" name="name" required maxLength={120} placeholder={t("admin.products.categories_name_placeholder")} />
                  </label>
                  <label className="span-2">
                    {t("common.description")}
                    <input
                      type="text"
                      name="description"
                      maxLength={2000}
                      placeholder={t("admin.products.categories_description_placeholder")}
                    />
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="active" defaultChecked />
                    {t("common.active")}
                  </label>
                  <label className="checkline span-2">
                    <input type="checkbox" name="can_be_requested_by_professor" defaultChecked />
                    {t("admin.products.categories_requestable")}
                  </label>
                  <div className="row span-4">
                    <button type="submit">{t("admin.products.categories_add")}</button>
                  </div>
                </form>

                {catalogCategories.length === 0 ? (
                  <p className="muted">{t("admin.products.categories_empty")}</p>
                ) : (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>{t("common.name")}</th>
                          <th>{t("common.description")}</th>
                          <th>{t("common.status")}</th>
                          <th>{t("admin.products.categories_teachers")}</th>
                          <th>{t("common.actions")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {catalogCategories.map((category) => (
                          <tr key={category.id}>
                            <td>{category.name}</td>
                            <td>{category.description || "-"}</td>
                            <td>{category.active ? t("common.active") : t("common.inactive")}</td>
                            <td>
                              {category.can_be_requested_by_professor
                                ? t("admin.products.categories_requestable_short")
                                : t("admin.products.categories_hidden")}
                            </td>
                            <td>
                              <div className="row">
                                <details>
                                  <summary className="mode-link">{t("common.edit")}</summary>
                                  <form action={updateAdminCatalogCategoryAction} className="grid top-gap-sm">
                                    <input type="hidden" name="category_id" value={category.id} />
                                    <label>
                                      {t("common.name")}
                                      <input type="text" name="name" defaultValue={category.name} required maxLength={120} />
                                    </label>
                                    <label>
                                      {t("common.description")}
                                      <input type="text" name="description" defaultValue={category.description || ""} maxLength={2000} />
                                    </label>
                                    <label className="checkline">
                                      <input type="checkbox" name="active" defaultChecked={category.active} />
                                      {t("common.active")}
                                    </label>
                                    <label className="checkline">
                                      <input
                                        type="checkbox"
                                        name="can_be_requested_by_professor"
                                        defaultChecked={category.can_be_requested_by_professor}
                                      />
                                      {t("admin.products.categories_requestable")}
                                    </label>
                                    <div className="row">
                                      <button type="submit">{t("common.save")}</button>
                                    </div>
                                  </form>
                                </details>
                                <form action={deleteAdminCatalogCategoryAction}>
                                  <input type="hidden" name="category_id" value={category.id} />
                                  <button type="submit" className="danger ghost">
                                    {t("common.delete")}
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
                  <strong>{t("admin.products.categories_legacy_sync", { count: productCategories.categories.length })}</strong>
                  {productCategories.updated_at ? (
                    <p className="muted">
                      {t("admin.billing.updated_at", {
                        value: new Date(productCategories.updated_at).toLocaleString(locale),
                      })}
                    </p>
                  ) : null}
                  <form action={updateAdminConfigProductCategoriesAction} className="grid config-form-grid">
                    <label>
                      {t("admin.products.categories_legacy_label")}
                      <textarea
                        name="categories"
                        rows={6}
                        defaultValue={productCategories.categories.join("\n")}
                        placeholder={t("admin.products.categories_legacy_placeholder")}
                      />
                    </label>
                    <div className="row">
                      <button type="submit">{t("admin.products.categories_sync")}</button>
                    </div>
                  </form>
                </div>
              </section>

              <section className="card">
                <h3>{t("admin.products.catalog_products_title")}</h3>
                <form action={createAdminCatalogProductAction} className="grid cols-4 config-form-grid">
                  <label className="span-2">
                    {t("admin.products.title_label")}
                    <input type="text" name="title" required maxLength={255} placeholder={t("admin.products.product_title_placeholder")} />
                  </label>
                  <label>
                    {t("admin.products.category_label")}
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
                    {t("admin.products.barcode")}
                    <input type="text" name="barcode" maxLength={120} />
                  </label>
                  <label>
                    {t("admin.products.price_excl_label")}
                    <input type="number" name="price_excl_vat" min="0" step="0.01" defaultValue="0.00" required />
                  </label>
                  <label>
                    {t("admin.products.price_incl_label")}
                    <input type="number" name="price_incl_vat" min="0" step="0.01" defaultValue="0.00" required />
                  </label>
                  <label>
                    {t("admin.products.vat_label")}
                    <input type="number" name="vat_rate" min="0" max="100" step="0.001" defaultValue="20.000" required />
                  </label>
                  <label>
                    {t("admin.products.web_link_label")}
                    <input type="url" name="web_link" />
                  </label>
                  <fieldset className="span-2">
                    <legend>{t("admin.products.product_type")}</legend>
                    <label className="checkline">
                      <input type="radio" name="is_virtual" value="false" defaultChecked />
                      {t("admin.products.product_physical")}
                    </label>
                    <label className="checkline">
                      <input type="radio" name="is_virtual" value="true" />
                      {t("admin.products.product_virtual")}
                    </label>
                  </fieldset>
                  <label className="span-2">
                    {t("admin.products.image_url_optional")}
                    <input type="url" name="image_url" />
                  </label>
                  <label className="span-2">
                    {t("admin.products.short_description_label")}
                    <input type="text" name="short_description" maxLength={500} />
                  </label>
                  <label className="span-4">
                    {t("admin.products.long_description_label")}
                    <textarea name="long_description" rows={3} maxLength={12000} />
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="purchasable_online" />
                    {t("admin.products.purchasable_online")}
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="is_public" defaultChecked />
                    {t("admin.products.public_visible_client")}
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="active" defaultChecked />
                    {t("common.active")}
                  </label>
                  <div className="row span-4">
                    <button type="submit">{t("admin.products.add_product")}</button>
                  </div>
                </form>

                {catalogProducts.length === 0 ? (
                  <p className="muted">{t("admin.products.no_catalog_products")}</p>
                ) : (
                  <div className="list">
                    {catalogProducts.map((product) => (
                      <article key={product.id} className="item">
                        <div className="row spread">
                          <div>
                            <strong>{product.title}</strong>
                            <p className="muted">
                              {t("admin.products.catalog_product_summary", {
                                category: product.category_name || t("admin.products.no_category"),
                                price: formatMoney(product.price_incl_vat, "EUR", locale),
                                stock: product.is_virtual
                                  ? t("admin.products.stock_virtual_short")
                                  : product.stock_global_quantity,
                              })}
                            </p>
                          </div>
                          <div className="row">
                            <span className="badge">
                              {t("admin.products.badge_virtual")}: {yesNoLabel(language, product.is_virtual)}
                            </span>
                            <span className="badge">
                              {t("admin.products.badge_online")}: {yesNoLabel(language, product.purchasable_online)}
                            </span>
                            <span className="badge">
                              {t("admin.products.badge_public")}: {yesNoLabel(language, product.is_public)}
                            </span>
                            <span className="badge">
                              {t("admin.products.badge_active")}: {yesNoLabel(language, product.active)}
                            </span>
                          </div>
                        </div>
                        <details>
                          <summary className="mode-link">{t("admin.products.edit_product_modal_title")}</summary>
                          <form action={updateAdminCatalogProductAction} className="grid cols-4 config-form-grid top-gap-sm">
                            <input type="hidden" name="product_id" value={product.id} />
                            <label className="span-2">
                              {t("admin.products.title_label")}
                              <input type="text" name="title" defaultValue={product.title} required maxLength={255} />
                            </label>
                            <label>
                              {t("admin.products.category_label")}
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
                              {t("admin.products.barcode")}
                              <input type="text" name="barcode" defaultValue={product.barcode || ""} maxLength={120} />
                            </label>
                            <label>
                              {t("admin.products.price_excl_label")}
                              <input type="number" name="price_excl_vat" min="0" step="0.01" defaultValue={product.price_excl_vat} required />
                            </label>
                            <label>
                              {t("admin.products.price_incl_label")}
                              <input type="number" name="price_incl_vat" min="0" step="0.01" defaultValue={product.price_incl_vat} required />
                            </label>
                            <label>
                              {t("admin.products.vat_label")}
                              <input type="number" name="vat_rate" min="0" max="100" step="0.001" defaultValue={product.vat_rate} required />
                            </label>
                            <label>
                              {t("admin.products.web_link_label")}
                              <input type="url" name="web_link" defaultValue={product.web_link || ""} />
                            </label>
                            <fieldset className="span-2">
                              <legend>{t("admin.products.product_type")}</legend>
                              <label className="checkline">
                                <input type="radio" name="is_virtual" value="false" defaultChecked={!product.is_virtual} />
                                {t("admin.products.product_physical")}
                              </label>
                              <label className="checkline">
                                <input type="radio" name="is_virtual" value="true" defaultChecked={product.is_virtual} />
                                {t("admin.products.product_virtual")}
                              </label>
                            </fieldset>
                            <label className="span-2">
                              {t("admin.products.image_url_label")}
                              <input type="url" name="image_url" defaultValue={product.image_url || ""} />
                            </label>
                            <label className="span-2">
                              {t("admin.products.short_description_label")}
                              <input type="text" name="short_description" defaultValue={product.short_description || ""} maxLength={500} />
                            </label>
                            <label className="span-4">
                              {t("admin.products.long_description_label")}
                              <textarea name="long_description" rows={3} maxLength={12000} defaultValue={product.long_description || ""} />
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="purchasable_online" defaultChecked={product.purchasable_online} />
                              {t("admin.products.purchasable_online")}
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="is_public" defaultChecked={product.is_public} />
                              {t("admin.products.public_visible_client")}
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="active" defaultChecked={product.active} />
                              {t("common.active")}
                            </label>
                            <div className="row span-4">
                              <button type="submit">{t("common.save")}</button>
                            </div>
                          </form>
                          <form action={deleteAdminCatalogProductAction} className="row top-gap-sm">
                            <input type="hidden" name="product_id" value={product.id} />
                            <button type="submit" className="danger">
                              {t("common.delete")}
                            </button>
                          </form>
                        </details>
                      </article>
                    ))}
                  </div>
                )}
              </section>

              <section className="card">
                <h3>{t("admin.catalog.kits_title")}</h3>
                <p className="muted">{t("admin.catalog.kits_subtitle")}</p>

                <form action={createAdminCatalogKitAction} className="grid cols-4 config-form-grid">
                  <label className="span-2">
                    {t("admin.products.title_label")}
                    <input type="text" name="title" required maxLength={255} />
                  </label>
                  <label>
                    {t("admin.products.category_label")}
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
                    {t("admin.products.price_incl_label")}
                    <input type="number" name="price_incl_vat" min="0" step="0.01" defaultValue="0.00" required />
                  </label>
                  <label>
                    {t("admin.products.vat_label")}
                    <input type="number" name="vat_rate" min="0" max="100" step="0.001" defaultValue="20.000" required />
                  </label>
                  <label>
                    {t("admin.products.image_url_optional")}
                    <input type="url" name="image_url" />
                  </label>
                  <label className="span-2">
                    {t("admin.products.short_description_label")}
                    <input type="text" name="short_description" maxLength={500} />
                  </label>
                  <label className="span-4">
                    {t("admin.products.long_description_label")}
                    <textarea name="long_description" rows={3} />
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="purchasable_online" />
                    {t("admin.catalog.purchasable_online")}
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="is_public" defaultChecked />
                    {t("admin.products.badge_public")}
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="active" defaultChecked />
                    {t("common.active")}
                  </label>
                  <div className="span-4">
                    <strong>{t("admin.catalog.composition_title")}</strong>
                    <div className="catalog-kit-grid">
                      {Array.from({ length: 6 }).map((_, index) => (
                        <div key={`new-kit-item-${index}`} className="catalog-kit-grid-row">
                          <select name={`item_product_id_${index}`} defaultValue="">
                            <option value="">{t("admin.catalog.product_option", { number: index + 1 })}</option>
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
                    <button type="submit">{t("admin.catalog.add_kit")}</button>
                  </div>
                </form>

                {catalogKits.length === 0 ? (
                  <p className="muted">{t("admin.catalog.no_configured_kits")}</p>
                ) : (
                  <div className="list">
                    {catalogKits.map((kit) => (
                      <article key={kit.id} className="item">
                        <div className="row spread">
                          <div>
                            <strong>{kit.title}</strong>
                            <p className="muted">
                              {t("admin.catalog.kit_summary", {
                                category: kit.category_name || "-",
                                billed: formatMoney(kit.price_incl_vat, "EUR", locale),
                                computed: formatMoney(kit.computed_price_incl_vat, "EUR", locale),
                              })}
                            </p>
                          </div>
                          <div className="row">
                            <span className="badge">{t("admin.catalog.items_count_badge", { count: kit.items.length })}</span>
                            <span className="badge">
                              {t("admin.products.badge_public")}: {yesNoLabel(language, kit.is_public)}
                            </span>
                            <span className="badge">
                              {t("admin.products.badge_online")}: {yesNoLabel(language, kit.purchasable_online)}
                            </span>
                          </div>
                        </div>
                        {kit.items.length > 0 ? (
                          <div className="table-wrap">
                            <table className="data-table">
                              <thead>
                                <tr>
                                  <th>{t("admin.catalog.product_column")}</th>
                                  <th>{t("admin.products.quantity_short_header")}</th>
                                  <th>{t("admin.catalog.unit_price_ttc")}</th>
                                  <th>{t("admin.catalog.total_price_ttc")}</th>
                                </tr>
                              </thead>
                              <tbody>
                                {kit.items.map((item) => (
                                  <tr key={`${kit.id}-${item.product_id}`}>
                                    <td>{item.product_title}</td>
                                    <td>{item.quantity}</td>
                                    <td>{formatMoney(item.unit_price_incl_vat, "EUR", locale)}</td>
                                    <td>{formatMoney(item.line_total_incl_vat, "EUR", locale)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : null}

                        <details>
                          <summary className="mode-link">{t("admin.catalog.edit_kit_title")}</summary>
                          <form action={updateAdminCatalogKitAction} className="grid cols-4 config-form-grid top-gap-sm">
                            <input type="hidden" name="kit_id" value={kit.id} />
                            <label className="span-2">
                              {t("admin.products.title_label")}
                              <input type="text" name="title" defaultValue={kit.title} required maxLength={255} />
                            </label>
                            <label>
                              {t("admin.products.category_label")}
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
                              {t("admin.products.price_incl_label")}
                              <input type="number" name="price_incl_vat" min="0" step="0.01" defaultValue={kit.price_incl_vat} required />
                            </label>
                            <label>
                              {t("admin.products.vat_label")}
                              <input type="number" name="vat_rate" min="0" max="100" step="0.001" defaultValue={kit.vat_rate} required />
                            </label>
                            <label>
                              {t("admin.products.image_url_label")}
                              <input type="url" name="image_url" defaultValue={kit.image_url || ""} />
                            </label>
                            <label className="span-2">
                              {t("admin.products.short_description_label")}
                              <input type="text" name="short_description" maxLength={500} defaultValue={kit.short_description || ""} />
                            </label>
                            <label className="span-4">
                              {t("admin.products.long_description_label")}
                              <textarea name="long_description" rows={3} defaultValue={kit.long_description || ""} />
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="purchasable_online" defaultChecked={kit.purchasable_online} />
                              {t("admin.catalog.purchasable_online")}
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="is_public" defaultChecked={kit.is_public} />
                              {t("admin.products.badge_public")}
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="active" defaultChecked={kit.active} />
                              {t("common.active")}
                            </label>
                            <div className="span-4">
                              <strong>{t("admin.catalog.composition_title")}</strong>
                              <div className="catalog-kit-grid">
                                {Array.from({ length: 6 }).map((_, index) => {
                                  const item = kit.items[index];
                                  return (
                                    <div key={`${kit.id}-item-${index}`} className="catalog-kit-grid-row">
                                      <select name={`item_product_id_${index}`} defaultValue={item?.product_id ?? ""}>
                                        <option value="">{t("admin.catalog.product_option", { number: index + 1 })}</option>
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
                              <button type="submit">{t("common.save")}</button>
                            </div>
                          </form>
                          <form action={deleteAdminCatalogKitAction} className="row top-gap-sm">
                            <input type="hidden" name="kit_id" value={kit.id} />
                            <button type="submit" className="danger">
                              {t("common.delete")}
                            </button>
                          </form>
                        </details>
                      </article>
                    ))}
                  </div>
                )}
              </section>

              <section className="card">
                <h3>{t("admin.products.operations_title")}</h3>
                <p className="muted">
                  {t("admin.products.operations_note_prefix")} <Link href="/admin/products">{t("admin.breadcrumb.products")}</Link>.
                </p>
              </section>
            </>
          ) : null}

          {section === "params-messaging" ? (
            <>
              <section className="card">
                <nav className="config-sub-nav">
                  {MESSAGING_TAB_ITEMS.map((item) => (
                    <Link
                      key={item.key}
                      className={`config-sub-link ${messagingTab === item.key ? "active" : ""}`}
                      href={buildConfigHref("params-messaging", { messaging_tab: item.key })}
                    >
                      {configNavLabel(item.label, item.labelKey)}
                    </Link>
                  ))}
                </nav>
              </section>

              {messagingTab === "settings" ? (
              <section className="card">
                <h3>{t("admin.messaging_settings.title")}</h3>
                {!messagingSettings ? (
                  <p className="muted">{t("admin.messaging_settings.settings_load_error")}</p>
                ) : (
                  <form action={updateAdminConfigMessagingSettingsAction} className="grid cols-2 config-form-grid">
                    <input type="hidden" name="messaging_tab" value={messagingTab} />
                    <fieldset className="span-2 config-subsection">
                      <legend>{t("admin.messaging_settings.sender_profile")}</legend>
                      <label className="span-2">
                        {t("admin.messaging_settings.studio_email")}
                        <input type="email" name="studio_email" defaultValue={messagingSettings.studio_email} maxLength={255} />
                      </label>

                      <label>
                        {t("admin.messaging_settings.studio_sender_name")}
                        <input
                          type="text"
                          name="studio_sender_name"
                          defaultValue={messagingSettings.studio_sender_name}
                          maxLength={120}
                        />
                      </label>
                      <label>
                        {t("admin.messaging_settings.teacher_sender_name")}
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
                        {t("admin.messaging_settings.use_studio_name_as_default_sender")}
                      </label>
                      <label className="checkline span-2">
                        <input
                          type="checkbox"
                          name="use_studio_email_for_reminders"
                          defaultChecked={messagingSettings.use_studio_email_for_reminders}
                        />
                        {t("admin.messaging_settings.use_studio_email_for_reminders")}
                      </label>
                      <label className="checkline span-2">
                        <input
                          type="checkbox"
                          name="use_studio_email_for_lesson_notes"
                          defaultChecked={messagingSettings.use_studio_email_for_lesson_notes}
                        />
                        {t("admin.messaging_settings.use_studio_email_for_lesson_notes")}
                      </label>
                      <label className="checkline span-2">
                        <input type="checkbox" name="send_birthday_emails" defaultChecked={messagingSettings.send_birthday_emails} />
                        {t("admin.messaging_settings.send_birthday_emails")}
                      </label>
                    </fieldset>

                    <fieldset className="span-2 config-subsection">
                      <legend>{t("admin.messaging_settings.email_transport")}</legend>
                      <label>
                        {t("admin.messaging_settings.provider")}
                        <select name="email_provider" defaultValue={messagingSettings.email_provider}>
                          <option value="LOG">{t("admin.messaging_settings.provider_log")}</option>
                          <option value="SMTP">{t("admin.messaging_settings.provider_smtp")}</option>
                          <option value="BREVO">{t("admin.messaging_settings.provider_brevo")}</option>
                        </select>
                      </label>
                      <label>
                        {t("admin.messaging_settings.reply_to")}
                        <input
                          type="email"
                          name="email_reply_to"
                          defaultValue={messagingSettings.email_reply_to}
                          maxLength={255}
                        />
                      </label>
                      <label>
                        {t("admin.messaging_settings.subject_prefix")}
                        <input
                          type="text"
                          name="email_subject_prefix"
                          defaultValue={messagingSettings.email_subject_prefix}
                          maxLength={120}
                        />
                      </label>
                      <label>
                        {t("admin.messaging_settings.frontend_base_url")}
                        <input
                          type="url"
                          name="frontend_base_url"
                          defaultValue={messagingSettings.frontend_base_url}
                          maxLength={255}
                        />
                      </label>
                      <label>
                        {t("admin.messaging_settings.smtp_host")}
                        <input type="text" name="smtp_host" defaultValue={messagingSettings.smtp_host} maxLength={255} />
                      </label>
                      <label>
                        {t("admin.messaging_settings.smtp_port")}
                        <input type="number" name="smtp_port" defaultValue={messagingSettings.smtp_port} min={1} max={65535} />
                      </label>
                      <label>
                        {t("admin.messaging_settings.smtp_username")}
                        <input
                          type="text"
                          name="smtp_username"
                          defaultValue={messagingSettings.smtp_username}
                          maxLength={255}
                          autoComplete="off"
                        />
                      </label>
                      <label>
                        {t("admin.messaging_settings.smtp_password")}
                        <input type="password" name="smtp_password" defaultValue="" maxLength={255} autoComplete="new-password" />
                        <span className="muted">
                          {messagingSettings.smtp_password_configured
                            ? t("admin.messaging_settings.smtp_password_configured", {
                                value: messagingSettings.smtp_password_masked || t("admin.messaging_settings.masked_fallback"),
                              })
                            : t("admin.messaging_settings.smtp_password_missing")}
                        </span>
                      </label>
                      <label>
                        {t("admin.messaging_settings.smtp_timeout_seconds")}
                        <input
                          type="number"
                          name="smtp_timeout_seconds"
                          defaultValue={messagingSettings.smtp_timeout_seconds}
                          min={1}
                          max={120}
                        />
                      </label>
                      <div className="span-2 row" style={{ gap: 16, alignItems: "center" }}>
                        <label className="checkline" style={{ margin: 0 }}>
                          <input type="checkbox" name="smtp_use_tls" defaultChecked={messagingSettings.smtp_use_tls} />
                          {t("admin.messaging_settings.smtp_use_tls")}
                        </label>
                        <label className="checkline" style={{ margin: 0 }}>
                          <input type="checkbox" name="smtp_use_ssl" defaultChecked={messagingSettings.smtp_use_ssl} />
                          {t("admin.messaging_settings.smtp_use_ssl")}
                        </label>
                      </div>
                    </fieldset>

                    <fieldset className="span-2 config-subsection">
                      <legend>{t("admin.messaging_settings.sms_transport")}</legend>
                      <label>
                        {t("admin.messaging_settings.sms_provider")}
                        <select name="sms_provider" defaultValue={messagingSettings.sms_provider}>
                          <option value="LOG">{t("admin.messaging_settings.provider_log")}</option>
                          <option value="BREVO">{t("admin.messaging_settings.provider_brevo_sms")}</option>
                        </select>
                      </label>
                      <label>
                        {t("admin.messaging_settings.sms_sender")}
                        <input type="text" name="sms_sender" defaultValue={messagingSettings.sms_sender} maxLength={32} />
                        <span className="muted">{t("admin.messaging_settings.sms_sender_hint")}</span>
                      </label>
                      <label className="span-2">
                        {t("admin.messaging_settings.brevo_sms_api_key")}
                        <input type="password" name="brevo_sms_api_key" defaultValue="" maxLength={255} autoComplete="new-password" />
                        <span className="muted">
                          {messagingSettings.brevo_sms_api_key_configured
                            ? t("admin.messaging_settings.brevo_sms_api_key_configured", {
                                value: messagingSettings.brevo_sms_api_key_masked || t("admin.messaging_settings.masked_fallback_f"),
                              })
                            : t("admin.messaging_settings.brevo_sms_api_key_missing")}
                        </span>
                      </label>
                    </fieldset>

                    <fieldset className="span-2 config-subsection">
                      <legend>{t("admin.messaging_settings.quote_lifecycle")}</legend>
                      <p className="muted">
                        {t("admin.messaging_settings.quote_lifecycle_note", { syntax: "{{variable}}" })}
                      </p>
                      <label>
                        {t("admin.messaging_settings.quote_send_template")}
                        <select name="quote_send_template_ref" defaultValue={messagingSettings.quote_send_template_ref}>
                          {quoteSendTemplates.map((template) => (
                            <option key={`send-${template.id}`} value={messagingTemplateRef(template)}>
                              {messagingTemplateOptionLabel(language, template)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        {t("admin.messaging_settings.quote_send_sms_template")}
                        <select name="quote_send_sms_template_ref" defaultValue={messagingSettings.quote_send_sms_template_ref}>
                          {quoteSendSmsTemplates.map((template) => (
                            <option key={`send-sms-${template.id}`} value={messagingTemplateRef(template)}>
                              {messagingTemplateOptionLabel(language, template)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        {t("admin.messaging_settings.quote_reminder_template")}
                        <select name="quote_reminder_template_ref" defaultValue={messagingSettings.quote_reminder_template_ref}>
                          {quoteReminderTemplates.map((template) => (
                            <option key={`reminder-${template.id}`} value={messagingTemplateRef(template)}>
                              {messagingTemplateOptionLabel(language, template)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        {t("admin.messaging_settings.quote_reminder_sms_template")}
                        <select name="quote_reminder_sms_template_ref" defaultValue={messagingSettings.quote_reminder_sms_template_ref}>
                          {quoteReminderSmsTemplates.map((template) => (
                            <option key={`reminder-sms-${template.id}`} value={messagingTemplateRef(template)}>
                              {messagingTemplateOptionLabel(language, template)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        {t("admin.messaging_settings.quote_cancel_template")}
                        <select name="quote_cancel_template_ref" defaultValue={messagingSettings.quote_cancel_template_ref}>
                          {quoteCancelTemplates.map((template) => (
                            <option key={`cancel-${template.id}`} value={messagingTemplateRef(template)}>
                              {messagingTemplateOptionLabel(language, template)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        {t("admin.messaging_settings.quote_expired_template")}
                        <select name="quote_expired_template_ref" defaultValue={messagingSettings.quote_expired_template_ref}>
                          {quoteExpiredTemplates.map((template) => (
                            <option key={`expired-${template.id}`} value={messagingTemplateRef(template)}>
                              {messagingTemplateOptionLabel(language, template)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        {t("admin.messaging_settings.quote_approved_template")}
                        <select name="quote_approved_template_ref" defaultValue={messagingSettings.quote_approved_template_ref}>
                          {quoteApprovedTemplates.map((template) => (
                            <option key={`approved-${template.id}`} value={messagingTemplateRef(template)}>
                              {messagingTemplateOptionLabel(language, template)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        {t("admin.messaging_settings.quote_rejected_template")}
                        <select name="quote_rejected_template_ref" defaultValue={messagingSettings.quote_rejected_template_ref}>
                          {quoteRejectedTemplates.map((template) => (
                            <option key={`rejected-${template.id}`} value={messagingTemplateRef(template)}>
                              {messagingTemplateOptionLabel(language, template)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="span-2">
                        {t("admin.messaging_settings.quote_change_requested_template")}
                        <select
                          name="quote_change_requested_template_ref"
                          defaultValue={messagingSettings.quote_change_requested_template_ref}
                        >
                          {quoteChangeRequestedTemplates.map((template) => (
                            <option key={`change-requested-${template.id}`} value={messagingTemplateRef(template)}>
                              {messagingTemplateOptionLabel(language, template)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        {t("admin.messaging_settings.quote_cancel_sms_template")}
                        <select name="quote_cancel_sms_template_ref" defaultValue={messagingSettings.quote_cancel_sms_template_ref}>
                          {quoteCancelSmsTemplates.map((template) => (
                            <option key={`cancel-sms-${template.id}`} value={messagingTemplateRef(template)}>
                              {messagingTemplateOptionLabel(language, template)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        {t("admin.messaging_settings.quote_expired_sms_template")}
                        <select name="quote_expired_sms_template_ref" defaultValue={messagingSettings.quote_expired_sms_template_ref}>
                          {quoteExpiredSmsTemplates.map((template) => (
                            <option key={`expired-sms-${template.id}`} value={messagingTemplateRef(template)}>
                              {messagingTemplateOptionLabel(language, template)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        {t("admin.messaging_settings.quote_daily_job_local_time")}
                        <input
                          type="time"
                          name="quote_daily_job_local_time"
                          defaultValue={messagingSettings.quote_daily_job_local_time || "07:00"}
                        />
                        <span className="muted">{t("admin.messaging_settings.quote_daily_job_hint")}</span>
                      </label>
                      <label className="checkline span-2">
                        <input
                          type="checkbox"
                          name="quote_reminder_enabled"
                          defaultChecked={messagingSettings.quote_reminder_enabled}
                        />
                        {t("admin.messaging_settings.quote_reminder_enabled")}
                      </label>
                      <label className="checkline span-2">
                        <input
                          type="checkbox"
                          name="quote_reminder_sms_enabled"
                          defaultChecked={messagingSettings.quote_reminder_sms_enabled}
                        />
                        {t("admin.messaging_settings.quote_reminder_sms_enabled")}
                      </label>
                      <label>
                        {t("admin.messaging_settings.quote_reminder_lead_hours")}
                        <input
                          type="text"
                          name="quote_reminder_lead_hours_csv"
                          defaultValue={messagingSettings.quote_reminder_lead_hours_csv || String(messagingSettings.quote_reminder_lead_hours)}
                          placeholder={t("admin.messaging_settings.quote_reminder_lead_hours_placeholder")}
                        />
                        <input type="hidden" name="quote_reminder_lead_hours" value={messagingSettings.quote_reminder_lead_hours} />
                        <span className="muted">{t("admin.messaging_settings.quote_reminder_lead_hours_hint", { example: "120,24" })}</span>
                      </label>
                      <label className="checkline">
                        <input
                          type="checkbox"
                          name="quote_auto_cancel_enabled"
                          defaultChecked={messagingSettings.quote_auto_cancel_enabled}
                        />
                        {t("admin.messaging_settings.quote_auto_cancel_enabled")}
                      </label>
                      <label>
                        {t("admin.messaging_settings.quote_auto_cancel_delay_hours")}
                        <input
                          type="number"
                          name="quote_auto_cancel_delay_hours"
                          min={1}
                          max={720}
                          defaultValue={messagingSettings.quote_auto_cancel_delay_hours}
                        />
                        <span className="muted">{t("admin.messaging_settings.quote_auto_cancel_delay_hours_hint", { example: 24 })}</span>
                      </label>
                      <label className="checkline span-2">
                        <input
                          type="checkbox"
                          name="quote_cancel_notification_enabled"
                          defaultChecked={messagingSettings.quote_cancel_notification_enabled}
                        />
                        {t("admin.messaging_settings.quote_cancel_notification_enabled")}
                      </label>
                      <label className="checkline span-2">
                        <input
                          type="checkbox"
                          name="quote_cancel_sms_notification_enabled"
                          defaultChecked={messagingSettings.quote_cancel_sms_notification_enabled}
                        />
                        {t("admin.messaging_settings.quote_cancel_sms_notification_enabled")}
                      </label>
                      <label className="checkline span-2">
                        <input
                          type="checkbox"
                          name="quote_expired_notification_enabled"
                          defaultChecked={messagingSettings.quote_expired_notification_enabled}
                        />
                        {t("admin.messaging_settings.quote_expired_notification_enabled")}
                      </label>
                      <label className="checkline span-2">
                        <input
                          type="checkbox"
                          name="quote_expired_sms_notification_enabled"
                          defaultChecked={messagingSettings.quote_expired_sms_notification_enabled}
                        />
                        {t("admin.messaging_settings.quote_expired_sms_notification_enabled")}
                      </label>
                    </fieldset>

                    <div className="span-2 config-note-box">
                      <strong>{t("admin.messaging_settings.technical_state")}</strong>
                      <p className="muted">
                        {messagingSettings.delivery_enabled
                          ? t("admin.messaging_settings.email_delivery_active", { provider: messagingSettings.email_provider })
                          : messagingSettings.delivery_error_message || t("admin.messaging_settings.email_delivery_unavailable")}
                      </p>
                      <p className="muted">
                        {messagingSettings.sms_delivery_enabled
                          ? t("admin.messaging_settings.sms_delivery_active", { provider: messagingSettings.sms_provider })
                          : messagingSettings.sms_delivery_error_message || t("admin.messaging_settings.sms_delivery_unavailable")}
                      </p>
                      <p className="muted">
                        {t("admin.messaging_settings.from_studio")}{" "}
                        <strong>{messagingSettings.studio_sender_name || t("admin.messaging_settings.studio_fallback")}</strong> &lt;
                        {messagingSettings.studio_email}&gt;
                      </p>
                      <p className="muted">
                        {t("admin.messaging_settings.from_teacher")}{" "}
                        <strong>{messagingSettings.teacher_sender_name || t("admin.messaging_settings.teacher_fallback")}</strong> &lt;
                        {messagingSettings.studio_email}&gt;
                      </p>
                      <p className="muted">
                        {t("admin.messaging_settings.public_links")} <strong>{messagingSettings.frontend_base_url}</strong>
                      </p>
                      <p className="muted">
                        {t("admin.messaging_settings.sms_sender_value")} <strong>{messagingSettings.sms_sender || "-"}</strong>
                      </p>
                      <p className="muted">
                        {t("admin.messaging_settings.quote_daily_job_prefix")}{" "}
                        <strong>{messagingSettings.quote_daily_job_local_time}</strong> {t("admin.messaging_settings.quote_daily_job_timezone")}
                        {" "}
                        {t(
                          messagingSettings.quote_reminder_enabled
                            ? "admin.messaging_settings.quote_reminder_summary_active"
                            : "admin.messaging_settings.quote_reminder_summary_disabled",
                          {
                            delay: formatQuoteReminderDelayList(
                              messagingSettings.quote_reminder_lead_hours_values,
                              messagingSettings.quote_reminder_lead_hours,
                            ),
                          },
                        )}
                        {" · "}
                        {t(
                          messagingSettings.quote_reminder_sms_enabled
                            ? "admin.messaging_settings.quote_reminder_sms_summary_active"
                            : "admin.messaging_settings.quote_reminder_sms_summary_disabled",
                        )}
                        {" · "}
                        {t(
                          messagingSettings.quote_auto_cancel_enabled
                            ? "admin.messaging_settings.quote_auto_cancel_summary_active"
                            : "admin.messaging_settings.quote_auto_cancel_summary_disabled",
                          {
                            delay: messagingSettings.quote_auto_cancel_delay_hours,
                          },
                        )}
                        {" · "}
                        {t(
                          messagingSettings.quote_cancel_sms_notification_enabled
                            ? "admin.messaging_settings.quote_cancel_sms_summary_active"
                            : "admin.messaging_settings.quote_cancel_sms_summary_disabled",
                        )}
                      </p>
                      {messagingSettings.email_provider === "BREVO" ? (
                        <>
                          <p className="muted">
                            {t("admin.messaging_settings.brevo_email_webhook_hint")}{" "}
                            <strong>{messagingSettings.brevo_email_webhook_url}</strong>
                          </p>
                          <label className="stack-sm top-gap-sm">
                            {t("admin.messaging_settings.brevo_email_webhook_label")}
                            <input type="text" value={messagingSettings.brevo_email_webhook_url} readOnly />
                          </label>
                          <p className="muted">
                            {t("admin.messaging_settings.brevo_email_webhook_events")}
                          </p>
                          <p className="muted">
                            {t("admin.messaging_settings.brevo_sms_webhook_hint")}{" "}
                            <strong>{messagingSettings.brevo_sms_webhook_url}</strong>
                          </p>
                          <label className="stack-sm top-gap-sm">
                            {t("admin.messaging_settings.brevo_sms_webhook_label")}
                            <input type="text" value={messagingSettings.brevo_sms_webhook_url} readOnly />
                          </label>
                        </>
                      ) : null}
                      <p className="muted">
                        {t("admin.messaging_settings.spf_dkim_note")}
                      </p>
                      {messagingSettings.updated_at ? (
                        <p className="muted">
                          {t("admin.billing.updated_at", {
                            value: new Date(messagingSettings.updated_at).toLocaleString(locale),
                          })}
                        </p>
                      ) : null}
                    </div>

                    <div className="span-2 config-note-box">
                      <strong>{t("admin.messaging_settings.quote_variables_title")}</strong>
                      <p className="muted">
                        {t("admin.messaging_settings.quote_variables_note", {
                          quoteNumber: "{{quote_number}}",
                          recipientEmail: "{{recipient_email}}",
                          expiresAt: "{{expires_at_local}}",
                        })}
                      </p>
                      {Object.entries(quoteTemplateVariablesByCategory).length === 0 ? (
                        <p className="muted">{t("admin.messaging_settings.no_quote_variables")}</p>
                      ) : (
                        <div className="grid cols-2 top-gap-sm" style={{ alignItems: "start" }}>
                          {Object.entries(quoteTemplateVariablesByCategory).map(([category, items]) => (
                            <article key={category} className="item">
                              <h4>{category}</h4>
                              <div className="top-gap-sm">
                                {items.map((item) => (
                                  <div key={item.key} className="top-gap-sm">
                                    <div className="row wrap gap-sm" style={{ alignItems: "center" }}>
                                      <code>{"{{"}{item.key}{"}}"}</code>
                                      <span className="badge">{item.label}</span>
                                    </div>
                                    <small className="muted">
                                      {item.description}
                                      {item.example ? ` · ${t("admin.messaging_settings.example", { value: item.example })}` : ""}
                                    </small>
                                  </div>
                                ))}
                              </div>
                            </article>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="row span-2">
                      <button type="submit">{t("admin.messaging_settings.save_changes")}</button>
                    </div>
                  </form>
                )}
              </section>
              ) : null}

              {messagingTab === "scheduled" ? (
              <section className="card">
                <h3>{t("admin.messaging_schedule.title")}</h3>
                <p className="muted">{t("admin.messaging_schedule.description")}</p>
                {!messagingSettings ? (
                  <p className="muted">{t("admin.messaging_settings.settings_load_error")}</p>
                ) : (
                  <div className="stack-lg">
                    {scheduledMessagingGroups.map((group) => (
                      <section key={group.theme} className="config-subsection">
                        <h4>{group.theme}</h4>
                        <div className="table-wrap">
                          <table className="data-table">
                            <thead>
                              <tr>
                                <th>{t("admin.messaging_schedule.column_event")}</th>
                                <th>{t("admin.messaging_schedule.column_channel")}</th>
                                <th>{t("admin.messaging_schedule.column_trigger")}</th>
                                <th>{t("admin.messaging_schedule.column_template")}</th>
                                <th>{t("common.status")}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {group.rows.map((row) => (
                                <tr key={`${group.theme}-${row.name}-${row.channel}`}>
                                  <td>{row.name}</td>
                                  <td>{messagingChannelLabel(language, row.channel)}</td>
                                  <td>{row.trigger}</td>
                                  <td>{row.template}</td>
                                  <td>
                                    <span className={`status-pill ${row.active ? "status-ok" : "status-off"}`}>
                                      {"statusLabel" in row && row.statusLabel
                                        ? row.statusLabel
                                        : row.active
                                        ? t("admin.messaging_schedule.status_active")
                                        : t("admin.messaging_schedule.status_inactive")}
                                    </span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </section>
                    ))}
                  </div>
                )}
              </section>
              ) : null}

              {messagingTab === "predefined-email" ? (
              <section className="card">
                <h3>{t("admin.messaging_templates.predefined_email_title")}</h3>
                {emailPredefinedTemplates.length === 0 ? (
                  <p className="muted">{t("admin.messaging_templates.empty_predefined")}</p>
                ) : (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>{t("common.name")}</th>
                          <th>{t("common.subject")}</th>
                          <th>{t("admin.messaging_templates.usage_column")}</th>
                          <th>{t("common.active")}</th>
                          <th aria-label={t("common.actions")} />
                        </tr>
                      </thead>
                      <tbody>
                        {emailPredefinedTemplates.map((template) => (
                          <tr key={template.id}>
                            <td>{template.name}</td>
                            <td>{template.subject || "-"}</td>
                            <td>
                              <div className="row wrap gap-sm">
                                {template.usage_contexts.length === 0 ? (
                                  <span className="status-pill status-off">{t("admin.messaging_templates.no_usage_assigned")}</span>
                                ) : (
                                  template.usage_contexts.map((usageContext) => (
                                    <span key={`${template.id}-${usageContext}`} className="badge">
                                      {quoteUsageContextLabel(language, usageContext)}
                                    </span>
                                  ))
                                )}
                              </div>
                            </td>
                            <td>{yesNoLabel(language, template.active)}</td>
                            <td>
                              <Link
                                className="icon-link"
                                title={t("common.edit")}
                                href={buildConfigHref("params-messaging", {
                                  messaging_tab: messagingTab,
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
              ) : null}

              {messagingTab === "predefined-sms" ? (
              <section className="card">
                <h3>{t("admin.messaging_templates.predefined_sms_title")}</h3>
                {smsPredefinedTemplates.length === 0 ? (
                  <p className="muted">{t("admin.messaging_templates.empty_predefined")}</p>
                ) : (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>{t("common.name")}</th>
                          <th>{t("admin.messaging_templates.content_column")}</th>
                          <th>{t("admin.messaging_templates.usage_column")}</th>
                          <th>{t("common.active")}</th>
                          <th aria-label={t("common.actions")} />
                        </tr>
                      </thead>
                      <tbody>
                        {smsPredefinedTemplates.map((template) => (
                          <tr key={template.id}>
                            <td>{template.name}</td>
                            <td>{template.body.slice(0, 90)}{template.body.length > 90 ? "..." : ""}</td>
                            <td>
                              <div className="row wrap gap-sm">
                                {template.usage_contexts.length === 0 ? (
                                  <span className="status-pill status-off">{t("admin.messaging_templates.no_usage_assigned")}</span>
                                ) : (
                                  template.usage_contexts.map((usageContext) => (
                                    <span key={`${template.id}-${usageContext}`} className="badge">
                                      {quoteUsageContextLabel(language, usageContext)}
                                    </span>
                                  ))
                                )}
                              </div>
                            </td>
                            <td>{yesNoLabel(language, template.active)}</td>
                            <td>
                              <Link
                                className="icon-link"
                                title={t("common.edit")}
                                href={buildConfigHref("params-messaging", {
                                  messaging_tab: messagingTab,
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
              ) : null}

              {messagingTab === "custom-email" ? (
              <section className="card">
                <div className="row spread">
                  <h3>{t("admin.messaging_templates.custom_email_title")}</h3>
                  <Link
                    className="mode-link"
                    href={buildConfigHref("params-messaging", {
                      messaging_tab: messagingTab,
                      messaging_modal: "new-custom",
                      new_template_channel: "EMAIL",
                    })}
                  >
                    + {t("admin.messaging_templates.add_new")}
                  </Link>
                </div>
                {customEmailTemplates.length === 0 ? (
                  <p className="muted">{t("admin.messaging_templates.empty_custom")}</p>
                ) : (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>{t("common.name")}</th>
                          <th>{t("common.subject")}</th>
                          <th>{t("admin.messaging_templates.usage_column")}</th>
                          <th>{t("common.active")}</th>
                          <th aria-label={t("common.actions")} />
                        </tr>
                      </thead>
                      <tbody>
                        {customEmailTemplates.map((template) => (
                          <tr key={template.id}>
                            <td>{template.name}</td>
                            <td>{template.subject || "-"}</td>
                            <td>
                              <div className="row wrap gap-sm">
                                {template.usage_contexts.length === 0 ? (
                                  <span className="status-pill status-off">{t("admin.messaging_templates.no_usage_assigned")}</span>
                                ) : (
                                  template.usage_contexts.map((usageContext) => (
                                    <span key={`${template.id}-${usageContext}`} className="badge">
                                      {quoteUsageContextLabel(language, usageContext)}
                                    </span>
                                  ))
                                )}
                              </div>
                            </td>
                            <td>{yesNoLabel(language, template.active)}</td>
                            <td>
                              <div className="row">
                                <Link
                                  className="icon-link"
                                  title={t("common.edit")}
                                  href={buildConfigHref("params-messaging", {
                                    messaging_tab: messagingTab,
                                    messaging_modal: "edit",
                                    template_kind: "CUSTOM",
                                    template_id: template.id,
                                  })}
                                >
                                  ✎
                                </Link>
                                <form action={deleteAdminConfigMessagingTemplateAction}>
                                  <input type="hidden" name="template_id" value={template.id} />
                                  <input type="hidden" name="messaging_tab" value={messagingTab} />
                                  <button type="submit" className="icon-link danger-link" title={t("common.delete")}>
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
              ) : null}

              {messagingTab === "custom-sms" ? (
              <section className="card">
                <div className="row spread">
                  <h3>{t("admin.messaging_templates.custom_sms_title")}</h3>
                  <Link
                    className="mode-link"
                    href={buildConfigHref("params-messaging", {
                      messaging_tab: messagingTab,
                      messaging_modal: "new-custom",
                      new_template_channel: "SMS",
                    })}
                  >
                    + {t("admin.messaging_templates.add_new")}
                  </Link>
                </div>
                {customSmsTemplates.length === 0 ? (
                  <p className="muted">{t("admin.messaging_templates.empty_custom")}</p>
                ) : (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>{t("common.name")}</th>
                          <th>{t("admin.messaging_templates.content_column")}</th>
                          <th>{t("admin.messaging_templates.usage_column")}</th>
                          <th>{t("common.active")}</th>
                          <th aria-label={t("common.actions")} />
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
                            <td>
                              <div className="row wrap gap-sm">
                                {template.usage_contexts.length === 0 ? (
                                  <span className="status-pill status-off">{t("admin.messaging_templates.no_usage_assigned")}</span>
                                ) : (
                                  template.usage_contexts.map((usageContext) => (
                                    <span key={`${template.id}-${usageContext}`} className="badge">
                                      {quoteUsageContextLabel(language, usageContext)}
                                    </span>
                                  ))
                                )}
                              </div>
                            </td>
                            <td>{yesNoLabel(language, template.active)}</td>
                            <td>
                              <div className="row">
                                <Link
                                  className="icon-link"
                                  title={t("common.edit")}
                                  href={buildConfigHref("params-messaging", {
                                    messaging_tab: messagingTab,
                                    messaging_modal: "edit",
                                    template_kind: "CUSTOM",
                                    template_id: template.id,
                                  })}
                                >
                                  ✎
                                </Link>
                                <form action={deleteAdminConfigMessagingTemplateAction}>
                                  <input type="hidden" name="template_id" value={template.id} />
                                  <input type="hidden" name="messaging_tab" value={messagingTab} />
                                  <button type="submit" className="icon-link danger-link" title={t("common.delete")}>
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
              ) : null}

              {messagingTab === "group-notes" ? (
                <section className="card">
                  <div className="row spread">
                    <h3>{t("admin.messaging_templates.group_notes_title")}</h3>
                    <Link
                      className="mode-link"
                      href={buildConfigHref("params-messaging", {
                        messaging_tab: messagingTab,
                        messaging_modal: "new-custom",
                        new_template_channel: "GROUP_NOTE",
                      })}
                    >
                      + {t("admin.messaging_templates.add_new")}
                    </Link>
                  </div>
                  {customGroupNoteTemplates.length === 0 ? (
                    <p className="muted">{t("admin.messaging_templates.empty_custom")}</p>
                  ) : (
                    <div className="table-wrap">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>{t("common.name")}</th>
                            <th>{t("admin.messaging_templates.content_column")}</th>
                            <th>{t("common.active")}</th>
                            <th aria-label={t("common.actions")} />
                          </tr>
                        </thead>
                        <tbody>
                          {customGroupNoteTemplates.map((template) => (
                            <tr key={template.id}>
                              <td>{template.name}</td>
                              <td>
                                {template.body.slice(0, 90)}
                                {template.body.length > 90 ? "..." : ""}
                              </td>
                              <td>{yesNoLabel(language, template.active)}</td>
                              <td>
                                <div className="row">
                                  <Link
                                    className="icon-link"
                                    title={t("common.edit")}
                                    href={buildConfigHref("params-messaging", {
                                      messaging_tab: messagingTab,
                                      messaging_modal: "edit",
                                      template_kind: "CUSTOM",
                                      template_id: template.id,
                                    })}
                                  >
                                    ✎
                                  </Link>
                                  <form action={deleteAdminConfigMessagingTemplateAction}>
                                    <input type="hidden" name="template_id" value={template.id} />
                                    <input type="hidden" name="messaging_tab" value={messagingTab} />
                                    <button type="submit" className="icon-link danger-link" title={t("common.delete")}>
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
              ) : null}

              {editingTemplate || createCustomMessagingTemplate ? (
                <section className="modal-overlay">
                  <article className="modal-panel activity-modal-panel messaging-template-modal">
                    <Link className="modal-close-x" href={messagingListPath} aria-label={t("common.close")}>
                      ×
                    </Link>
                    <header className="activity-modal-header messaging-template-modal-header">
                      <div>
                        <h3 className="messaging-template-modal-title">
                          {editingTemplate?.kind === "PREDEFINED" && editingTemplate.channel === "EMAIL"
                            ? t("admin.messaging_templates.edit_system_email_title")
                            : editingTemplate?.kind === "PREDEFINED" && editingTemplate.channel === "SMS"
                            ? t("admin.messaging_templates.edit_system_sms_title")
                            : editingTemplate
                            ? t("admin.messaging_templates.edit_custom_title", {
                                channel: messagingChannelLabel(language, editingTemplate.channel),
                              })
                            : t("admin.messaging_templates.new_custom_title", {
                                channel: messagingChannelLabel(language, newCustomTemplateChannel),
                              })}
                        </h3>
                        <p className="muted">
                          {editingTemplate
                            ? t("admin.messaging_templates.edit_desc")
                            : t("admin.messaging_templates.new_desc")}
                        </p>
                      </div>
                    </header>

                    <section className="card modal-card messaging-template-modal-card">
                      <form action={saveAdminConfigMessagingTemplateAction} className="grid config-form-grid messaging-template-form">
                        <input type="hidden" name="messaging_tab" value={messagingTab} />
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
                                {t("common.name")}
                                <input type="text" name="name" defaultValue={editingTemplate.name} maxLength={180} required />
                              </label>
                            ) : (
                              <p className="messaging-template-title-line">
                                <strong>{t("admin.messaging_templates.title_label")}</strong> {editingTemplate.name}
                              </p>
                            )}

                            {editingTemplate.channel === "EMAIL" ? (
                              <>
                                <label>
                                  {t("admin.messaging_templates.email_subject_fr")}
                                  <input
                                    type="text"
                                    name="subject_fr"
                                    defaultValue={editingTemplate.subject_translations.fr ?? editingTemplate.subject ?? ""}
                                    maxLength={255}
                                    required
                                  />
                                </label>
                                <label>
                                  {t("admin.messaging_templates.email_subject_en")}
                                  <input
                                    type="text"
                                    name="subject_en"
                                    defaultValue={editingTemplate.subject_translations.en ?? ""}
                                    maxLength={255}
                                  />
                                </label>
                              </>
                            ) : null}

                            {editingTemplate.channel !== "GROUP_NOTE" ? (
                              editingTemplate.kind === "CUSTOM" ? (
                                <fieldset className="span-2 config-subsection">
                                  <legend>{t("admin.messaging_templates.allowed_usage")}</legend>
                                  <div className="row wrap gap-sm">
                                    {QUOTE_TEMPLATE_USAGE_CONTEXTS.map((usageContext) => (
                                      <label key={`${editingTemplate.id}-${usageContext.value}`} className="checkline">
                                        <input
                                          type="checkbox"
                                          name="usage_contexts"
                                          value={usageContext.value}
                                          defaultChecked={editingTemplate.usage_contexts.includes(usageContext.value)}
                                        />
                                        {t(usageContext.labelKey)}
                                      </label>
                                    ))}
                                  </div>
                                </fieldset>
                              ) : (
                                <div className="span-2 row wrap gap-sm">
                                  {editingTemplate.usage_contexts.map((usageContext) => (
                                    <span key={`${editingTemplate.id}-${usageContext}`} className="badge">
                                      {quoteUsageContextLabel(language, usageContext)}
                                    </span>
                                  ))}
                                </div>
                              )
                            ) : null}

                            <label className="messaging-editor-label">
                              {t("admin.messaging_templates.message_fr")}
                              <RichMessageEditor
                                name="body_fr"
                                formatName="body_format"
                                defaultValue={editingTemplate.body_translations.fr ?? editingTemplate.body}
                                defaultFormat={editingTemplate.body_format}
                                rows={20}
                                maxLength={12000}
                              />
                            </label>

                            <label className="messaging-editor-label">
                              {t("admin.messaging_templates.message_en")}
                              <RichMessageEditor
                                name="body_en"
                                formatName="body_format_en"
                                defaultValue={editingTemplate.body_translations.en ?? ""}
                                defaultFormat={editingTemplate.body_format}
                                rows={20}
                                maxLength={12000}
                              />
                            </label>

                            <label className="checkline">
                              <input type="checkbox" name="active" defaultChecked={editingTemplate.active} />
                              {t("admin.messaging_templates.template_active")}
                            </label>
                          </>
                        ) : (
                          <>
                            <input type="hidden" name="template_kind" value="CUSTOM" />
                            <label>
                              {t("common.name")}
                              <input type="text" name="name" maxLength={180} required />
                            </label>
                            <label>
                              {t("admin.messaging_templates.channel")}
                              <select name="template_channel" defaultValue={newCustomTemplateChannel}>
                                <option value="EMAIL">{t("admin.messaging_templates.channel_email")}</option>
                                <option value="SMS">{t("admin.messaging_templates.channel_sms")}</option>
                                <option value="GROUP_NOTE">{t("admin.messaging_templates.channel_group_note")}</option>
                              </select>
                            </label>
                            <label>
                              {t("admin.messaging_templates.email_subject_optional")}
                              <input type="text" name="subject_fr" maxLength={255} />
                            </label>
                            <label>
                              {t("admin.messaging_templates.email_subject_en")}
                              <input type="text" name="subject_en" maxLength={255} />
                            </label>
                            {newCustomTemplateChannel !== "GROUP_NOTE" ? (
                              <fieldset className="span-2 config-subsection">
                                <legend>{t("admin.messaging_templates.allowed_usage")}</legend>
                                <div className="row wrap gap-sm">
                                  {QUOTE_TEMPLATE_USAGE_CONTEXTS.map((usageContext) => (
                                    <label key={`new-${usageContext.value}`} className="checkline">
                                      <input type="checkbox" name="usage_contexts" value={usageContext.value} />
                                      {t(usageContext.labelKey)}
                                    </label>
                                  ))}
                                </div>
                              </fieldset>
                            ) : null}
                            <label className="messaging-editor-label">
                              {t("admin.messaging_templates.message_fr")}
                              <RichMessageEditor name="body_fr" formatName="body_format" rows={20} maxLength={12000} />
                            </label>
                            <label className="messaging-editor-label">
                              {t("admin.messaging_templates.message_en")}
                              <RichMessageEditor name="body_en" formatName="body_format_en" rows={20} maxLength={12000} />
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="active" defaultChecked />
                              {t("admin.messaging_templates.template_active")}
                            </label>
                          </>
                        )}

                        {editingTemplate?.variables_hint ? (
                          <p className="muted">{t("admin.messaging_templates.variables_hint", { value: editingTemplate.variables_hint })}</p>
                        ) : null}
                        {(editingTemplate?.channel !== "GROUP_NOTE" || (createCustomMessagingTemplate && newCustomTemplateChannel !== "GROUP_NOTE")) && quoteTemplateVariables.length > 0 ? (
                          <div className="span-2 item">
                            <strong>{t("admin.messaging_templates.available_quote_variables")}</strong>
                            <div className="row wrap gap-sm top-gap-sm">
                              {quoteTemplateVariables.map((item) => (
                                <span key={item.key} className="badge" title={item.description}>
                                  {"{{"}{item.key}{"}}"}
                                </span>
                              ))}
                            </div>
                          </div>
                        ) : null}

                        <div className="row spread messaging-template-actions">
                          <div className="row">
                            {editingTemplate?.kind === "PREDEFINED" && editingTemplate.code ? (
                              <button type="submit" formAction={resetAdminConfigPredefinedMessagingTemplateAction} className="ghost">
                                {t("admin.messaging_templates.reset_default")}
                              </button>
                            ) : null}
                          </div>
                          <button type="submit">{t("common.save")}</button>
                        </div>
                      </form>
                    </section>
                  </article>
                </section>
              ) : null}
            </>
          ) : null}

          {section === "activities" ? (
            <>
              <section className="card">
                <div className="row between">
                  <h3>{t("admin.activities.catalog_title")}</h3>
                  <div className="row wrap gap-sm">
                    <form action={syncAdminExternalContentCatalogAction}>
                      <button type="submit" className="ghost">
                        {t("admin.activities.sync_learndash")}
                      </button>
                    </form>
                    <Link className="mode-link" href={buildConfigHref("activities", { new_activity: "1" })}>
                      {t("admin.activity_modal.add_activity")}
                    </Link>
                  </div>
                </div>
                <p className="muted">{t("admin.activities.catalog_help")}</p>
                <p className="muted">
                  <strong>{externalContentCourses.length}</strong> {t("admin.activities.synced_catalog_suffix")}
                </p>
                <div className="config-metric-grid">
                  <article>
                    <span>{t("admin.config.metrics.total")}</span>
                    <strong>{activityStats.total}</strong>
                  </article>
                  <article>
                    <span>{t("common.active")}</span>
                    <strong>{activityStats.active}</strong>
                  </article>
                  <article>
                    <span>{t("admin.professor_detail.mode_online")}</span>
                    <strong>{activityStats.online}</strong>
                  </article>
                  <article className={activityStats.unpriced > 0 ? "is-warning" : ""}>
                    <span>{t("admin.config.metrics.unpriced")}</span>
                    <strong>{activityStats.unpriced}</strong>
                  </article>
                </div>
                {activeCreditTypes.length === 0 ? <p className="flash-err">{t("admin.credit_types.no_active_for_activities")}</p> : null}
                {activeLegalEntities.length === 0 ? (
                  <p className="flash-err">{t("admin.legal_entities.no_active_for_activities")}</p>
                ) : null}
              </section>

              <section className="card">
                <div className="row between">
                  <h3>{t("admin.activities.existing_title")}</h3>
                  <small className="muted">{t("admin.credit_types.activity_count", { count: activities.length })}</small>
                </div>
                <p className="muted">{t("admin.activities.list_help")}</p>
                {activities.length === 0 ? (
                  <p className="muted">{t("admin.activities.empty")}</p>
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
                          <small className="muted">
                            {activity.credit_type_name ?? t("admin.activities.unmapped_credit_type")} ·{" "}
                            {activityModeLabel(activity.mode, language)} · {activity.duration_minutes} min
                          </small>
                          <small className="muted">
                            {t("admin.planning.teacher_badge", {
                              value: activity.requires_professor
                                ? t("admin.activities.teacher_required_short")
                                : t("admin.planning.no_teacher_required"),
                            })}{" "}
                            · {activity.allows_student_bookings ? t("admin.planning.with_students") : t("admin.planning.without_students")}
                          </small>
                          <small className="muted">
                            {t("admin.activities.recurrence_badge", {
                              holidays: activity.exclude_holidays_in_recurrence
                                ? t("admin.activities.holidays_excluded")
                                : t("admin.activities.holidays_included"),
                              vacations: activity.exclude_school_vacations_in_recurrence
                                ? t("admin.activities.vacations_excluded")
                                : t("admin.activities.vacations_included"),
                            })}
                          </small>
                          <small className="muted">
                            {t("admin.activities.legal_entity_badge", {
                              value: activity.seller_legal_entity_name ?? t("admin.activities.not_defined"),
                            })}
                          </small>
                          <small className="muted">
                            {t("admin.activities.student_content_badge", {
                              value:
                                activity.content_course_titles.length > 0
                                  ? activity.content_course_titles.join(", ")
                                  : t("admin.activities.no_content_attachment"),
                            })}
                          </small>
                          {activityPlanningLocations.length > 0 ? (
                            <small className="muted">
                              {t("admin.activities.plannings_badge", {
                                assigned: activityPlanningCountById.get(activity.id) ?? 0,
                                total: activityPlanningLocations.length,
                              })}
                            </small>
                          ) : null}
                          <small className="muted">{activity.description || t("admin.activities.no_description")}</small>
                        </div>
                        <div className="activity-row-meta">
                          <span className="status-pill status-warn">
                            {activity.default_course_rate_ttc
                              ? t("admin.activities.course_rate_badge", {
                                  amount: activity.default_course_rate_ttc,
                                  currency: accountDefaultCurrency,
                                })
                              : activity.default_hourly_rate
                                ? t("admin.activities.hourly_rate_badge", {
                                    amount: activity.default_hourly_rate,
                                    currency: accountDefaultCurrency,
                                  })
                                : t("admin.activities.rate_not_defined")}
                          </span>
                          <span className={`status-pill ${activity.active ? "status-ok" : "status-warn"}`}>
                            {activity.active ? t("admin.activities.status_active") : t("admin.activities.status_inactive")}
                          </span>
                        </div>
                        <span className="mode-link">{t("common.edit")}</span>
                      </Link>
                    ))}
                  </div>
                )}
              </section>

              <details className="card config-technical-details">
                <summary>
                  <span>
                    <strong>{t("admin.activities.wordpress_title")}</strong>
                    <small className="muted">{t("admin.activities.wordpress_help")}</small>
                  </span>
                  <span className="status-pill status-info">
                    {externalContentSettings.bearer_token_configured
                      ? t("admin.activities.token_configured")
                      : t("admin.activities.token_not_configured")}
                  </span>
                </summary>
                <form action={updateAdminConfigExternalContentSettingsAction} className="grid cols-2 config-form-grid top-gap-sm">
                  <label>
                    {t("admin.activities.wordpress_site_url")}
                    <input
                      type="url"
                      name="base_url"
                      defaultValue={externalContentSettings.base_url}
                      placeholder={t("admin.activities.wordpress_site_placeholder")}
                    />
                  </label>
                  <label>
                    {t("admin.activities.courses_endpoint")}
                    <input
                      type="url"
                      name="courses_endpoint"
                      defaultValue={externalContentSettings.courses_endpoint}
                      placeholder={t("admin.activities.courses_endpoint_placeholder")}
                    />
                    <small className="muted">{t("admin.activities.endpoint_fallback_help")}</small>
                  </label>
                  <label>
                    {t("admin.activities.bearer_token")}
                    <input type="password" name="bearer_token" placeholder={t("admin.activities.bearer_token_placeholder")} />
                    <small className="muted">
                      {externalContentSettings.bearer_token_configured
                        ? t("admin.activities.current_token", { token: externalContentSettings.bearer_token_masked })
                        : t("admin.activities.no_token")}
                    </small>
                  </label>
                  <label>
                    {t("admin.activities.timeout_seconds")}
                    <input
                      type="number"
                      name="timeout_seconds"
                      min={5}
                      max={120}
                      defaultValue={externalContentSettings.timeout_seconds}
                      required
                    />
                  </label>
                  <label className="row center gap-sm">
                    <input type="checkbox" name="clear_bearer_token" />
                    <span>{t("admin.activities.clear_token")}</span>
                  </label>
                  <div className="item">
                    <strong>{t("admin.activities.endpoint_used")}</strong>
                    <p className="muted top-gap-sm">{externalContentSettings.resolved_endpoint_url ?? t("admin.activities.endpoint_missing")}</p>
                    <p className="muted">
                      {t("admin.activities.wordpress_plugin")} <code>wordpress/plugins/piano-academie-learndash-bridge</code>
                    </p>
                  </div>
                  <div className="span-2 row end">
                    <button type="submit">{t("admin.activities.save_connection")}</button>
                  </div>
                </form>
              </details>

              {createActivityModalOpen ? (
                <section className="modal-overlay">
                  <article className="modal-panel activity-modal-panel">
                    <Link className="modal-close-x" href={buildConfigHref("activities")} aria-label={t("common.close")}>
                      ×
                    </Link>
                    <header className="activity-modal-header">
                      <div>
                        <h3>{t("admin.activity_modal.new_activity")}</h3>
                        <p className="muted">{t("admin.activity_modal.new_activity_desc")}</p>
                      </div>
                    </header>

                    <section className="card modal-card">
                      {activeLegalEntities.length === 0 ? (
                        <p className="flash-err">{t("admin.activity_modal.no_legal_entity_create")}</p>
                      ) : (
                      <form action={createAdminActivityAction} className="activity-modal-form">
                        <input type="hidden" name="service_code" value="ACTIVITY" />
                        <ActivityModalTabs
                          language={language}
                          activityContent={
                            <>
                              <ActivityModalSection
                                title={t("admin.activity_modal.identity_title")}
                                description={t("admin.activity_modal.identity_desc")}
                              >
                                <div className="grid cols-2 config-form-grid">
                                  <label className="span-2">
                                    {t("admin.activity_modal.activity_name")}
                                    <input type="text" name="name" required maxLength={255} />
                                  </label>
                                  <label>
                                    {t("admin.activity_modal.seller_legal_entity")}
                                    <select name="seller_legal_entity_id" defaultValue={activeLegalEntities[0]?.id ?? ""} required>
                                      <option value="" disabled>
                                        {t("common.select")}
                                      </option>
                                      {activeLegalEntities.map((entity) => (
                                        <option key={entity.id} value={entity.id}>
                                          {entity.name} ({entity.invoice_prefix})
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                  <label>
                                    {t("admin.activity_modal.payor_legal_entity")}
                                    <select name="payor_legal_entity_id" defaultValue={activeLegalEntities[0]?.id ?? ""} required>
                                      <option value="" disabled>
                                        {t("common.select")}
                                      </option>
                                      {activeLegalEntities.map((entity) => (
                                        <option key={`create-payor-entity-${entity.id}`} value={entity.id}>
                                          {entity.name} ({entity.invoice_prefix})
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                </div>
                              </ActivityModalSection>

                              <ActivityModalSection
                                title={t("admin.activity_modal.plannings_title")}
                                description={t("admin.activity_modal.plannings_desc_create")}
                              >
                                <ActivityPlanningAssignments
                                  locations={activityPlanningLocations}
                                  defaultSelectedLocationIds={createActivityDefaultPlanningLocationIds}
                                  language={language}
                                />
                              </ActivityModalSection>

                              <div className="grid cols-2 activity-modal-zone-grid">
                                <ActivityModalSection
                                  title={t("admin.activity_modal.usage_title")}
                                  description={t("admin.activity_modal.usage_desc")}
                                  accent
                                >
                                  <div className="grid cols-2 config-form-grid">
                                    <label>
                                      {t("admin.professor_detail.mode")}
                                      <select name="mode" defaultValue="ANY">
                                        <option value="ANY">{t("admin.professor_detail.mode_all")}</option>
                                        <option value="ONSITE">{t("admin.professor_detail.mode_onsite")}</option>
                                        <option value="ONLINE">{t("admin.professor_detail.mode_online")}</option>
                                      </select>
                                    </label>
                                    <label>
                                      {t("admin.formulas.editor_credit_type")}
                                      <select name="credit_type_id" defaultValue="">
                                        <option value="">{t("admin.activity_modal.no_credit_type")}</option>
                                        {activeCreditTypes.map((creditType) => (
                                          <option key={creditType.id} value={creditType.id}>
                                            {creditType.name}
                                          </option>
                                        ))}
                                      </select>
                                    </label>
                                  </div>
                                  <div className="activity-toggle-grid">
                                    <ActivityToggleCard
                                      name="without_students"
                                      label={t("admin.activity_modal.without_students")}
                                      description={t("admin.activity_modal.without_students_desc")}
                                      emphasized
                                    />
                                    <ActivityToggleCard
                                      name="requires_professor"
                                      label={t("admin.activity_modal.requires_professor")}
                                      description={t("admin.activity_modal.requires_professor_desc")}
                                      defaultChecked
                                    />
                                    <ActivityToggleCard
                                      name="supports_student_time_overrides"
                                      label={pickText(language, "Horaires eleves decales", "Staggered student times")}
                                      description={pickText(
                                        language,
                                        "Permet de definir un horaire par eleve a l interieur du creneau professeur.",
                                        "Allow a per-student time inside the teacher slot.",
                                      )}
                                    />
                                    <ActivityToggleCard
                                      name="exclude_holidays_in_recurrence"
                                      label={t("admin.activity_modal.exclude_holidays")}
                                      description={t("admin.activity_modal.exclude_holidays_desc")}
                                      defaultChecked
                                    />
                                    <ActivityToggleCard
                                      name="exclude_school_vacations_in_recurrence"
                                      label={t("admin.activity_modal.exclude_vacations")}
                                      description={t("admin.activity_modal.exclude_vacations_desc")}
                                      defaultChecked
                                    />
                                    <ActivityToggleCard
                                      name="active"
                                      label={t("admin.activity_modal.active")}
                                      description={t("admin.activity_modal.active_desc")}
                                      defaultChecked
                                    />
                                  </div>
                                  <p className="activity-modal-note">{t("admin.activity_modal.without_students_note_create")}</p>
                                </ActivityModalSection>

                                <ActivityModalSection
                                  title={t("admin.activity_modal.slot_settings_title")}
                                  description={t("admin.activity_modal.slot_settings_desc")}
                                >
                                  <div className="grid cols-2 config-form-grid">
                                    <label>
                                      {t("admin.activity_modal.duration_minutes")}
                                      <input
                                        type="number"
                                        name="duration_minutes"
                                        min={5}
                                        max={1440}
                                        defaultValue={60}
                                        required
                                      />
                                    </label>
                                    <label>
                                      {t("admin.activity_modal.max_capacity")}
                                      <input type="number" name="default_capacity" min={0} max={500} defaultValue={8} required />
                                      <small className="muted">{t("admin.activity_modal.capacity_auto_zero")}</small>
                                    </label>
                                  </div>
                                </ActivityModalSection>
                              </div>

                              <div className="grid cols-2 activity-modal-zone-grid">
                                <ActivityModalSection
                                  title={t("admin.activity_modal.reminders_title")}
                                  description={t("admin.activity_modal.reminders_desc")}
                                >
                                  <div className="grid cols-2 config-form-grid">
                                    <label>
                                      {t("admin.activity_modal.email_reminders")}
                                      <select name="email_reminder_hours_before_start" defaultValue="global">
                                        {REMINDER_OFFSET_OPTIONS.map((option) => (
                                          <option key={`activity-email-reminder-create-${option.value}`} value={option.value}>
                                            {t(option.labelKey)}
                                          </option>
                                        ))}
                                      </select>
                                    </label>
                                    <label>
                                      {t("admin.activity_modal.sms_reminders")}
                                      <select name="sms_reminder_hours_before_start" defaultValue="global">
                                        {REMINDER_OFFSET_OPTIONS.map((option) => (
                                          <option key={`activity-sms-reminder-create-${option.value}`} value={option.value}>
                                            {t(option.labelKey)}
                                          </option>
                                        ))}
                                      </select>
                                    </label>
                                    <label>
                                      {t("admin.activity_modal.min_booking_notice")}
                                      <input
                                        type="number"
                                        name="min_booking_notice_hours_override"
                                        min={0}
                                        step="1"
                                        placeholder={t("admin.activity_modal.planning_placeholder")}
                                      />
                                    </label>
                                    <label>
                                      {t("admin.activity_modal.cancellation_deadline")}
                                      <input
                                        type="number"
                                        name="cancellation_deadline_hours_override"
                                        min={0}
                                        step="1"
                                        placeholder={t("admin.activity_modal.planning_placeholder")}
                                      />
                                    </label>
                                    <label>
                                      {t("admin.activity_modal.auto_cancel_less_than")} {"<"}
                                      <input
                                        type="number"
                                        name="auto_cancel_if_booked_less_than_override"
                                        min={0}
                                        step="1"
                                        placeholder={t("admin.activity_modal.planning_placeholder")}
                                      />
                                    </label>
                                    <label>
                                      {t("admin.activity_modal.auto_cancel_before_start")}
                                      <input
                                        type="number"
                                        name="auto_cancel_hours_before_start_override"
                                        min={0}
                                        step="1"
                                        placeholder={t("admin.activity_modal.planning_placeholder")}
                                      />
                                    </label>
                                  </div>
                                </ActivityModalSection>

                                <ActivityModalSection
                                  title={t("admin.activity_modal.pricing_title")}
                                  description={t("admin.activity_modal.pricing_desc")}
                                >
                                  <div className="grid cols-2 config-form-grid">
                                    <label>
                                      {t("admin.activity_modal.hourly_rate_ttc")}
                                      <input
                                        type="number"
                                        name="default_hourly_rate"
                                        min={0}
                                        step="0.01"
                                        placeholder="ex: 35.00"
                                      />
                                    </label>
                                    <label>
                                      {t("admin.activity_modal.course_rate_ttc")}
                                      <input
                                        type="number"
                                        name="default_course_rate_ttc"
                                        min={0}
                                        step="0.01"
                                        placeholder="ex: 200.00"
                                      />
                                    </label>
                                    <label className="span-2">
                                      {t("admin.activity_modal.color")}
                                      <ColorHexInput name="color_hex" defaultValue="#94C973" />
                                    </label>
                                  </div>
                                </ActivityModalSection>
                              </div>

                              <ActivityModalSection
                                title={t("admin.activity_modal.internal_description_title")}
                                description={t("admin.activity_modal.internal_description_desc")}
                              >
                                <label>
                                  {t("common.description")}
                                  <textarea name="description" rows={4} />
                                </label>
                              </ActivityModalSection>
                            </>
                          }
                          contentContent={
                            <ActivityModalSection
                              title={t("admin.activity_modal.online_content_title")}
                              description={t("admin.activity_modal.online_content_desc_create")}
                            >
                              <ActivityContentAssignmentsPicker
                                courses={externalContentCourses}
                                defaultSelectedCourseIds={[]}
                                language={language}
                              />
                            </ActivityModalSection>
                          }
                        />

                        <div className="activity-modal-footer">
                          <p className="muted">{t("admin.activity_modal.technical_codes_note")}</p>
                          <div className="row">
                            <button type="submit">{t("admin.activity_modal.add_activity")}</button>
                          </div>
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
                    <Link className="modal-close-x" href={buildConfigHref("activities")} aria-label={t("common.close")}>
                      ×
                    </Link>
                    <header className="activity-modal-header">
                      <div>
                        <h3>{selectedActivity.name}</h3>
                        <p className="muted">{t("admin.activity_modal.edit_activity_desc")}</p>
                      </div>
                    </header>

                    <section className="card modal-card">
                      {activeLegalEntities.length === 0 ? (
                        <p className="flash-err">{t("admin.activity_modal.no_legal_entity_edit")}</p>
                      ) : (
                      <form action={updateAdminActivityAction} className="activity-modal-form">
                        <input type="hidden" name="activity_id" value={selectedActivity.id} />
                        <input type="hidden" name="service_code" value={selectedActivity.service_code} />
                        <ActivityModalTabs
                          language={language}
                          activityContent={
                            <>
                              <ActivityModalSection
                                title={t("admin.activity_modal.identity_title")}
                                description={t("admin.activity_modal.identity_desc")}
                              >
                                <div className="grid cols-2 config-form-grid">
                                  <label className="span-2">
                                    {t("admin.activity_modal.activity_name")}
                                    <input type="text" name="name" defaultValue={selectedActivity.name} required maxLength={255} />
                                  </label>
                                  <label>
                                    {t("admin.activity_modal.seller_legal_entity")}
                                    <select
                                      name="seller_legal_entity_id"
                                      defaultValue={selectedActivity.seller_legal_entity_id ?? activeLegalEntities[0]?.id ?? ""}
                                      required
                                    >
                                      <option value="" disabled>
                                        {t("common.select")}
                                      </option>
                                      {activeLegalEntities.map((entity) => (
                                        <option key={entity.id} value={entity.id}>
                                          {entity.name} ({entity.invoice_prefix})
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                  <label>
                                    {t("admin.activity_modal.payor_legal_entity")}
                                    <select
                                      name="payor_legal_entity_id"
                                      defaultValue={
                                        selectedActivity.payor_legal_entity_id ??
                                        selectedActivity.seller_legal_entity_id ??
                                        activeLegalEntities[0]?.id ??
                                        ""
                                      }
                                      required
                                    >
                                      <option value="" disabled>
                                        {t("common.select")}
                                      </option>
                                      {activeLegalEntities.map((entity) => (
                                        <option key={`edit-payor-entity-${entity.id}`} value={entity.id}>
                                          {entity.name} ({entity.invoice_prefix})
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                </div>
                              </ActivityModalSection>

                              <ActivityModalSection
                                title={t("admin.activity_modal.plannings_title")}
                                description={t("admin.activity_modal.plannings_desc_edit")}
                              >
                                <ActivityPlanningAssignments
                                  locations={activityPlanningLocations}
                                  defaultSelectedLocationIds={selectedActivityPlanningLocationIds}
                                  language={language}
                                />
                              </ActivityModalSection>

                              <div className="grid cols-2 activity-modal-zone-grid">
                                <ActivityModalSection
                                  title={t("admin.activity_modal.usage_title")}
                                  description={t("admin.activity_modal.usage_desc")}
                                  accent
                                >
                                  <div className="grid cols-2 config-form-grid">
                                    <label>
                                      {t("admin.professor_detail.mode")}
                                      <select name="mode" defaultValue={selectedActivity.mode}>
                                        <option value="ANY">{t("admin.professor_detail.mode_all")}</option>
                                        <option value="ONSITE">{t("admin.professor_detail.mode_onsite")}</option>
                                        <option value="ONLINE">{t("admin.professor_detail.mode_online")}</option>
                                      </select>
                                    </label>
                                    <label>
                                      {t("admin.formulas.editor_credit_type")}
                                      <select name="credit_type_id" defaultValue={selectedActivity.credit_type_id ?? ""}>
                                        <option value="">{t("admin.activity_modal.no_credit_type")}</option>
                                        {activeCreditTypes.map((creditType) => (
                                          <option key={creditType.id} value={creditType.id}>
                                            {creditType.name}
                                          </option>
                                        ))}
                                      </select>
                                    </label>
                                  </div>
                                  <div className="activity-toggle-grid">
                                    <ActivityToggleCard
                                      name="without_students"
                                      label={t("admin.activity_modal.without_students")}
                                      description={t("admin.activity_modal.without_students_desc")}
                                      defaultChecked={selectedActivityIsStudentless}
                                      emphasized={selectedActivityIsStudentless}
                                    />
                                    <ActivityToggleCard
                                      name="requires_professor"
                                      label={t("admin.activity_modal.requires_professor")}
                                      description={t("admin.activity_modal.requires_professor_desc")}
                                      defaultChecked={selectedActivity.requires_professor}
                                    />
                                    <ActivityToggleCard
                                      name="supports_student_time_overrides"
                                      label={pickText(language, "Horaires eleves decales", "Staggered student times")}
                                      description={pickText(
                                        language,
                                        "Permet de definir un horaire par eleve a l interieur du creneau professeur.",
                                        "Allow a per-student time inside the teacher slot.",
                                      )}
                                      defaultChecked={selectedActivity.supports_student_time_overrides}
                                    />
                                    <ActivityToggleCard
                                      name="exclude_holidays_in_recurrence"
                                      label={t("admin.activity_modal.exclude_holidays")}
                                      description={t("admin.activity_modal.exclude_holidays_desc")}
                                      defaultChecked={selectedActivity.exclude_holidays_in_recurrence}
                                    />
                                    <ActivityToggleCard
                                      name="exclude_school_vacations_in_recurrence"
                                      label={t("admin.activity_modal.exclude_vacations")}
                                      description={t("admin.activity_modal.exclude_vacations_desc")}
                                      defaultChecked={selectedActivity.exclude_school_vacations_in_recurrence}
                                    />
                                    <ActivityToggleCard
                                      name="active"
                                      label={t("admin.activity_modal.active")}
                                      description={t("admin.activity_modal.active_desc")}
                                      defaultChecked={selectedActivity.active}
                                    />
                                  </div>
                                  <p className="activity-modal-note">
                                    {selectedActivityIsStudentless
                                      ? t("admin.activity_modal.without_students_note_active")
                                      : t("admin.activity_modal.without_students_note_edit")}
                                  </p>
                                </ActivityModalSection>

                                <ActivityModalSection
                                  title={t("admin.activity_modal.slot_settings_title")}
                                  description={t("admin.activity_modal.slot_settings_desc")}
                                >
                                  <div className="grid cols-2 config-form-grid">
                                    <label>
                                      {t("admin.activity_modal.duration_minutes")}
                                      <input
                                        type="number"
                                        name="duration_minutes"
                                        min={selectedActivityIsVacation ? 600 : 5}
                                        max={1440}
                                        defaultValue={selectedActivity.duration_minutes}
                                        required
                                      />
                                    </label>
                                    {selectedActivityIsStudentless ? (
                                      <label>
                                        {t("admin.activity_modal.max_capacity")}
                                        <input type="number" value={0} disabled readOnly />
                                        <small className="muted">{t("admin.activity_modal.capacity_forced_zero")}</small>
                                      </label>
                                    ) : (
                                      <label>
                                        {t("admin.activity_modal.max_capacity")}
                                        <input
                                          type="number"
                                          name="default_capacity"
                                          min={0}
                                          max={500}
                                          defaultValue={selectedActivity.default_capacity}
                                          required
                                        />
                                        <small className="muted">{t("admin.activity_modal.capacity_auto_zero")}</small>
                                      </label>
                                    )}
                                  </div>
                                </ActivityModalSection>
                              </div>

                              <div className="grid cols-2 activity-modal-zone-grid">
                                <ActivityModalSection
                                  title={t("admin.activity_modal.reminders_title")}
                                  description={t("admin.activity_modal.reminders_desc")}
                                >
                                  <div className="grid cols-2 config-form-grid">
                                    <label>
                                      {t("admin.activity_modal.email_reminders")}
                                      <select
                                        name="email_reminder_hours_before_start"
                                        defaultValue={
                                          selectedActivity.email_reminder_hours_before_start === null
                                            ? "global"
                                            : String(selectedActivity.email_reminder_hours_before_start)
                                        }
                                      >
                                        {selectedActivity.email_reminder_hours_before_start !== null &&
                                        !REMINDER_OFFSET_OPTIONS.some(
                                          (option) => option.value === String(selectedActivity.email_reminder_hours_before_start),
                                        ) ? (
                                          <option value={String(selectedActivity.email_reminder_hours_before_start)}>
                                            {t("admin.activity_modal.custom_hours_before", {
                                              count: selectedActivity.email_reminder_hours_before_start,
                                            })}
                                          </option>
                                        ) : null}
                                        {REMINDER_OFFSET_OPTIONS.map((option) => (
                                          <option key={`activity-email-reminder-update-${option.value}`} value={option.value}>
                                            {t(option.labelKey)}
                                          </option>
                                        ))}
                                      </select>
                                    </label>
                                    <label>
                                      {t("admin.activity_modal.sms_reminders")}
                                      <select
                                        name="sms_reminder_hours_before_start"
                                        defaultValue={
                                          selectedActivity.sms_reminder_hours_before_start === null
                                            ? "global"
                                            : String(selectedActivity.sms_reminder_hours_before_start)
                                        }
                                      >
                                        {selectedActivity.sms_reminder_hours_before_start !== null &&
                                        !REMINDER_OFFSET_OPTIONS.some(
                                          (option) => option.value === String(selectedActivity.sms_reminder_hours_before_start),
                                        ) ? (
                                          <option value={String(selectedActivity.sms_reminder_hours_before_start)}>
                                            {t("admin.activity_modal.custom_hours_before", {
                                              count: selectedActivity.sms_reminder_hours_before_start,
                                            })}
                                          </option>
                                        ) : null}
                                        {REMINDER_OFFSET_OPTIONS.map((option) => (
                                          <option key={`activity-sms-reminder-update-${option.value}`} value={option.value}>
                                            {t(option.labelKey)}
                                          </option>
                                        ))}
                                      </select>
                                    </label>
                                    <label>
                                      {t("admin.activity_modal.min_booking_notice")}
                                      <input
                                        type="number"
                                        name="min_booking_notice_hours_override"
                                        min={0}
                                        step="1"
                                        defaultValue={selectedActivity.min_booking_notice_hours_override ?? ""}
                                        placeholder={t("admin.activity_modal.planning_placeholder")}
                                      />
                                    </label>
                                    <label>
                                      {t("admin.activity_modal.cancellation_deadline")}
                                      <input
                                        type="number"
                                        name="cancellation_deadline_hours_override"
                                        min={0}
                                        step="1"
                                        defaultValue={selectedActivity.cancellation_deadline_hours_override ?? ""}
                                        placeholder={t("admin.activity_modal.planning_placeholder")}
                                      />
                                    </label>
                                    <label>
                                      {t("admin.activity_modal.auto_cancel_less_than")} {"<"}
                                      <input
                                        type="number"
                                        name="auto_cancel_if_booked_less_than_override"
                                        min={0}
                                        step="1"
                                        defaultValue={selectedActivity.auto_cancel_if_booked_less_than_override ?? ""}
                                        placeholder={t("admin.activity_modal.planning_placeholder")}
                                      />
                                    </label>
                                    <label>
                                      {t("admin.activity_modal.auto_cancel_before_start")}
                                      <input
                                        type="number"
                                        name="auto_cancel_hours_before_start_override"
                                        min={0}
                                        step="1"
                                        defaultValue={selectedActivity.auto_cancel_hours_before_start_override ?? ""}
                                        placeholder={t("admin.activity_modal.planning_placeholder")}
                                      />
                                    </label>
                                  </div>
                                </ActivityModalSection>

                                <ActivityModalSection
                                  title={t("admin.activity_modal.pricing_title")}
                                  description={t("admin.activity_modal.pricing_desc")}
                                >
                                  <div className="grid cols-2 config-form-grid">
                                    <label>
                                      {t("admin.activity_modal.hourly_rate_ttc")}
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
                                      {t("admin.activity_modal.course_rate_ttc")}
                                      <input
                                        type="number"
                                        name="default_course_rate_ttc"
                                        min={0}
                                        step="0.01"
                                        defaultValue={selectedActivity.default_course_rate_ttc ?? ""}
                                        placeholder="ex: 200.00"
                                      />
                                    </label>
                                    <label className="span-2">
                                      {t("admin.activity_modal.color")}
                                      <ColorHexInput name="color_hex" defaultValue={selectedActivity.color_hex} />
                                    </label>
                                  </div>
                                </ActivityModalSection>
                              </div>

                              <ActivityModalSection
                                title={t("admin.activity_modal.internal_description_title")}
                                description={t("admin.activity_modal.internal_description_desc")}
                              >
                                <label>
                                  {t("common.description")}
                                  <textarea name="description" rows={4} defaultValue={selectedActivity.description ?? ""} />
                                </label>
                              </ActivityModalSection>
                            </>
                          }
                          contentContent={
                            <ActivityModalSection
                              title={t("admin.activity_modal.online_content_title")}
                              description={t("admin.activity_modal.online_content_desc_edit")}
                            >
                              <ActivityContentAssignmentsPicker
                                courses={externalContentCourses}
                                defaultSelectedCourseIds={selectedActivityContentCourseIds}
                                language={language}
                              />
                            </ActivityModalSection>
                          }
                        />

                        <div className="activity-modal-footer">
                          <p className="muted">{t("admin.activity_modal.technical_codes_note")}</p>
                          <div className="row">
                            <button type="submit">{t("common.save")}</button>
                          </div>
                        </div>
                      </form>
                      )}
                    </section>
                  </article>
                </section>
              ) : null}
            </>
          ) : null}

          {section === "legal-entities" ? (
            <>
              <section className="card">
                <div className="row between">
                  <div>
                    <h3>{t("admin.legal_entities.title")}</h3>
                    <p className="muted">{t("admin.legal_entities.intro")}</p>
                  </div>
                  <Link className="mode-link" href={buildConfigHref("legal-entities", { new_legal_entity: "1" })}>
                    {t("admin.legal_entities.add")}
                  </Link>
                </div>
                <div className="config-metric-grid">
                  <article>
                    <span>{t("admin.config.metrics.total")}</span>
                    <strong>{legalEntityStats.total}</strong>
                  </article>
                  <article>
                    <span>{t("common.active")}</span>
                    <strong>{legalEntityStats.active}</strong>
                  </article>
                  <article className={legalEntityStats.active === 0 ? "is-warning" : ""}>
                    <span>{t("admin.config.metrics.ready_for_billing")}</span>
                    <strong>{legalEntityStats.active > 0 ? t("common.yes") : t("common.no")}</strong>
                  </article>
                </div>
              </section>

              <section className="card">
                <h3>{t("admin.legal_entities.registry_title")}</h3>
                {legalEntities.length === 0 ? (
                  <p className="muted">{t("admin.legal_entities.empty")}</p>
                ) : (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>{t("admin.legal_entities.entity")}</th>
                          <th>{t("admin.legal_entities.identifiers")}</th>
                          <th>{t("admin.legal_entities.default_psp")}</th>
                          <th>{t("admin.legal_entities.numbering")}</th>
                          <th>{t("common.status")}</th>
                          <th>{t("common.actions")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {legalEntities.map((entity) => (
                          <tr key={entity.id}>
                            <td>
                              <div>
                                <strong>{entity.name}</strong>
                                <small className="muted">{entity.country_code}</small>
                                <small>
                                  {[
                                    entity.legal_form,
                                    entity.share_capital
                                      ? t("admin.legal_entities.share_capital_value", { value: entity.share_capital })
                                      : null,
                                  ]
                                    .filter((value): value is string => Boolean(value))
                                    .join(" | ") || "-"}
                                </small>
                              </div>
                            </td>
                            <td>
                              <div>
                                <small>{t("admin.legal_entities.siren_value", { value: entity.siren || "-" })}</small>
                                <small>{t("admin.legal_entities.siret_value", { value: entity.siret || "-" })}</small>
                                <small>{t("admin.legal_entities.vat_value", { value: entity.vat_number || "-" })}</small>
                              </div>
                            </td>
                            <td>
                              <span className="badge">{entity.default_payment_provider || "PAYPLUG"}</span>
                              <small>{t("admin.legal_entities.accounting_value", { value: entity.accounting_email || "-" })}</small>
                              <small>{t("admin.legal_entities.phone_value", { value: entity.phone || "-" })}</small>
                            </td>
                            <td>
                              <div>
                                <small>{t("admin.legal_entities.invoice_prefix_value", { value: entity.invoice_prefix })}</small>
                                <small>{t("admin.legal_entities.next_number_value", { value: entity.invoice_next_number })}</small>
                              </div>
                            </td>
                            <td>
                              <span className={`status-pill ${entity.is_active ? "status-ok" : "status-warn"}`}>
                                {entity.is_active ? t("common.active") : t("common.inactive")}
                              </span>
                            </td>
                            <td>
                              <div className="row gap-xs">
                                <Link className="small-btn" href={buildConfigHref("legal-entities", { legal_entity_id: entity.id })}>
                                  {t("common.edit")}
                                </Link>
                                <form action={disableAdminLegalEntityAction}>
                                  <input type="hidden" name="legal_entity_id" value={entity.id} />
                                  <button type="submit" className="danger small-btn" disabled={!entity.is_active}>
                                    {t("admin.legal_entities.disable")}
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

              {createLegalEntityModalOpen ? (
                <section className="modal-overlay">
                  <article className="modal-panel activity-modal-panel">
                    <Link className="modal-close-x" href={buildConfigHref("legal-entities")} aria-label={t("common.close")}>
                      ×
                    </Link>
                    <header className="activity-modal-header">
                      <div>
                        <h3>{t("admin.legal_entities.new_title")}</h3>
                        <p className="muted">{t("admin.legal_entities.new_desc")}</p>
                      </div>
                    </header>

                    <section className="card modal-card">
                      <form action={createAdminLegalEntityAction} className="grid cols-4 config-form-grid activity-modal-grid">
                        <label className="span-2">
                          {t("admin.legal_entities.legal_name")}
                          <input type="text" name="name" required maxLength={255} />
                        </label>
                        <label>
                          {t("admin.legal_entities.invoice_prefix")}
                          <input
                            type="text"
                            name="invoice_prefix"
                            required
                            maxLength={20}
                            placeholder={t("admin.legal_entities.invoice_prefix_placeholder")}
                          />
                        </label>
                        <label>
                          {t("admin.billing.next_number")}
                          <input type="number" name="invoice_next_number" min={1} step="1" defaultValue={1} required />
                        </label>
                        <label>
                          {t("admin.legal_entities.default_psp")}
                          <select name="default_payment_provider" defaultValue="PAYPLUG" required>
                            <option value="PAYPLUG">Payplug</option>
                            <option value="MOLLIE">Mollie</option>
                            <option value="STRIPE">Stripe</option>
                          </select>
                        </label>

                        <label>
                          {t("admin.legal_entities.siren")}
                          <input type="text" name="siren" maxLength={64} />
                        </label>
                        <label>
                          {t("admin.legal_entities.siret")}
                          <input type="text" name="siret" maxLength={64} />
                        </label>
                        <label>
                          {t("admin.legal_entities.vat_number")}
                          <input type="text" name="vat_number" maxLength={64} />
                        </label>
                        <label>
                          {t("admin.legal_entities.accounting_email")}
                          <input type="email" name="accounting_email" maxLength={320} />
                        </label>
                        <label>
                          {t("admin.legal_entities.phone")}
                          <input type="tel" name="phone" maxLength={30} />
                        </label>
                        <label>
                          {t("admin.legal_entities.legal_form")}
                          <select name="legal_form" defaultValue="">
                            <option value="">{t("common.select")}</option>
                            <option value="SAS">SAS</option>
                            <option value="SA">SA</option>
                            <option value="SARL">SARL</option>
                            <option value="EURL">EURL</option>
                          </select>
                        </label>
                        <label>
                          {t("admin.legal_entities.share_capital")}
                          <input
                            type="text"
                            name="share_capital"
                            maxLength={120}
                            placeholder={t("admin.legal_entities.share_capital_placeholder")}
                          />
                        </label>
                        <label>
                          {t("admin.legal_entities.country_code")}
                          <input type="text" name="country_code" defaultValue="FR" minLength={2} maxLength={2} required />
                        </label>
                        <label className="checkline">
                          <input type="checkbox" name="is_active" defaultChecked />
                          {t("common.active")}
                        </label>

                        <label className="span-3">
                          {t("admin.legal_entities.invoice_address")}
                          <textarea name="address_text" rows={3} />
                        </label>
                        <div className="row">
                          <button type="submit">{t("admin.legal_entities.add_submit")}</button>
                        </div>
                      </form>
                    </section>
                  </article>
                </section>
              ) : null}

              {selectedLegalEntity ? (
                <section className="modal-overlay">
                  <article className="modal-panel activity-modal-panel">
                    <Link className="modal-close-x" href={buildConfigHref("legal-entities")} aria-label={t("common.close")}>
                      ×
                    </Link>
                    <header className="activity-modal-header">
                      <div>
                        <h3>{selectedLegalEntity.name}</h3>
                        <p className="muted">{t("admin.legal_entities.edit_desc")}</p>
                      </div>
                    </header>

                    <section className="card modal-card">
                      <form action={updateAdminLegalEntityAction} className="grid cols-4 config-form-grid activity-modal-grid">
                        <input type="hidden" name="legal_entity_id" value={selectedLegalEntity.id} />

                        <label className="span-2">
                          {t("admin.legal_entities.legal_name")}
                          <input type="text" name="name" defaultValue={selectedLegalEntity.name} required maxLength={255} />
                        </label>
                        <label>
                          {t("admin.legal_entities.invoice_prefix")}
                          <input type="text" name="invoice_prefix" defaultValue={selectedLegalEntity.invoice_prefix} required maxLength={20} />
                        </label>
                        <label>
                          {t("admin.billing.next_number")}
                          <input
                            type="number"
                            name="invoice_next_number"
                            min={1}
                            step="1"
                            defaultValue={selectedLegalEntity.invoice_next_number}
                            required
                          />
                        </label>
                        <label>
                          {t("admin.legal_entities.default_psp")}
                          <select
                            name="default_payment_provider"
                            defaultValue={selectedLegalEntity.default_payment_provider || "PAYPLUG"}
                            required
                          >
                            <option value="PAYPLUG">Payplug</option>
                            <option value="MOLLIE">Mollie</option>
                            <option value="STRIPE">Stripe</option>
                          </select>
                        </label>

                        <label>
                          {t("admin.legal_entities.siren")}
                          <input type="text" name="siren" defaultValue={selectedLegalEntity.siren ?? ""} maxLength={64} />
                        </label>
                        <label>
                          {t("admin.legal_entities.siret")}
                          <input type="text" name="siret" defaultValue={selectedLegalEntity.siret ?? ""} maxLength={64} />
                        </label>
                        <label>
                          {t("admin.legal_entities.vat_number")}
                          <input type="text" name="vat_number" defaultValue={selectedLegalEntity.vat_number ?? ""} maxLength={64} />
                        </label>
                        <label>
                          {t("admin.legal_entities.accounting_email")}
                          <input
                            type="email"
                            name="accounting_email"
                            defaultValue={selectedLegalEntity.accounting_email ?? ""}
                            maxLength={320}
                          />
                        </label>
                        <label>
                          {t("admin.legal_entities.phone")}
                          <input type="tel" name="phone" defaultValue={selectedLegalEntity.phone ?? ""} maxLength={30} />
                        </label>
                        <label>
                          {t("admin.legal_entities.legal_form")}
                          <select name="legal_form" defaultValue={selectedLegalEntity.legal_form ?? ""}>
                            <option value="">{t("common.select")}</option>
                            <option value="SAS">SAS</option>
                            <option value="SA">SA</option>
                            <option value="SARL">SARL</option>
                            <option value="EURL">EURL</option>
                          </select>
                        </label>
                        <label>
                          {t("admin.legal_entities.share_capital")}
                          <input
                            type="text"
                            name="share_capital"
                            defaultValue={selectedLegalEntity.share_capital ?? ""}
                            maxLength={120}
                            placeholder={t("admin.legal_entities.share_capital_placeholder")}
                          />
                        </label>
                        <label>
                          {t("admin.legal_entities.country_code")}
                          <input
                            type="text"
                            name="country_code"
                            defaultValue={selectedLegalEntity.country_code}
                            minLength={2}
                            maxLength={2}
                            required
                          />
                        </label>
                        <label className="checkline">
                          <input type="checkbox" name="is_active" defaultChecked={selectedLegalEntity.is_active} />
                          {t("common.active")}
                        </label>

                        <label className="span-3">
                          {t("admin.legal_entities.invoice_address")}
                          <textarea name="address_text" rows={3} defaultValue={selectedLegalEntity.address_text ?? ""} />
                        </label>
                        <div className="row">
                          <button type="submit">{t("common.save")}</button>
                        </div>
                      </form>
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
                    <h3>{t("admin.breadcrumb.credit_types")}</h3>
                    <p className="muted">{t("admin.credit_types.intro")}</p>
                  </div>
                  <Link className="mode-link" href={buildConfigHref("credit-types", { new_credit_type: "1" })}>
                    {t("admin.credit_types.add")}
                  </Link>
                </div>
                <div className="config-metric-grid">
                  <article>
                    <span>{t("admin.config.metrics.total")}</span>
                    <strong>{creditTypeStats.total}</strong>
                  </article>
                  <article>
                    <span>{t("common.active")}</span>
                    <strong>{creditTypeStats.active}</strong>
                  </article>
                  <article className={creditTypeStats.unlinked > 0 ? "is-warning" : ""}>
                    <span>{t("admin.config.metrics.unlinked")}</span>
                    <strong>{creditTypeStats.unlinked}</strong>
                  </article>
                </div>
              </section>

              <section className="card">
                <h3>{t("admin.credit_types.registry_title")}</h3>
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>{t("common.code")}</th>
                        <th>{t("admin.credit_types.credit_type")}</th>
                        <th>{t("admin.credit_types.linked_activities")}</th>
                        <th>{t("common.status")}</th>
                        <th>{t("common.actions")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {creditTypes.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="muted">
                            {t("admin.credit_types.empty")}
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
                              <span className="muted">{t("admin.credit_types.no_linked_activity")}</span>
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
                              {creditType.active ? t("common.active") : t("common.inactive")}
                            </span>
                            <span className={`status-pill ${creditType.activity_count > 0 ? "status-ok" : "status-warn"}`}>
                              {creditType.activity_count > 0
                                ? t("admin.credit_types.activity_count", { count: creditType.activity_count })
                                : t("admin.credit_types.to_configure")}
                            </span>
                          </td>
                          <td>
                            <div className="formula-actions-cell">
                              <Link className="mode-link" href={buildConfigHref("credit-types", { credit_type_id: creditType.id })}>
                                {t("common.edit")}
                              </Link>
                              <form action={deleteAdminCreditTypeAction}>
                                <input type="hidden" name="credit_type_id" value={creditType.id} />
                                <button type="submit" className="danger small-btn" disabled={creditType.activity_count > 0}>
                                  {t("common.delete")}
                                </button>
                              </form>
                            </div>
                            {creditType.activity_count > 0 ? (
                              <small className="muted">{t("admin.credit_types.delete_unavailable")}</small>
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
                    <Link className="modal-close-x" href={buildConfigHref("credit-types")} aria-label={t("common.close")}>
                      ×
                    </Link>
                    <header className="activity-modal-header">
                      <div>
                        <h3>{t("admin.credit_types.new_title")}</h3>
                        <p className="muted">{t("admin.credit_types.new_desc")}</p>
                      </div>
                    </header>

                    <section className="card modal-card">
                      <form action={createAdminCreditTypeAction} className="grid cols-2 config-form-grid">
                        <label>
                          {t("admin.credit_types.name_label")}
                          <input type="text" name="name" required maxLength={255} />
                        </label>
                        <label>
                          {t("admin.credit_types.code_optional")}
                          <input type="text" name="code" maxLength={80} placeholder={t("admin.credit_types.code_auto_placeholder")} />
                        </label>

                        <label className="span-2">
                          {t("common.description")}
                          <textarea name="description" rows={3} />
                        </label>
                        <label className="checkline">
                          <input type="checkbox" name="active" defaultChecked />
                          {t("common.active")}
                        </label>

                        <div className="row span-2">
                          <button type="submit">{t("admin.credit_types.add_submit")}</button>
                        </div>
                      </form>
                    </section>
                  </article>
                </section>
              ) : null}

              {selectedCreditType ? (
                <section className="modal-overlay">
                  <article className="modal-panel activity-modal-panel">
                    <Link className="modal-close-x" href={buildConfigHref("credit-types")} aria-label={t("common.close")}>
                      ×
                    </Link>
                    <header className="activity-modal-header">
                      <div>
                        <h3>{selectedCreditType.name}</h3>
                        <p className="muted">{t("admin.credit_types.edit_desc")}</p>
                      </div>
                    </header>

                    <section className="card modal-card">
                      <form action={updateAdminCreditTypeAction} className="grid cols-2 config-form-grid">
                        <input type="hidden" name="credit_type_id" value={selectedCreditType.id} />

                        <label>
                          {t("admin.credit_types.name_label")}
                          <input type="text" name="name" defaultValue={selectedCreditType.name} required maxLength={255} />
                        </label>
                        <label>
                          {t("common.code")}
                          <input type="text" name="code" defaultValue={selectedCreditType.code} maxLength={80} />
                        </label>

                        <label className="span-2">
                          {t("common.description")}
                          <textarea name="description" rows={3} defaultValue={selectedCreditType.description ?? ""} />
                        </label>
                        <label className="checkline">
                          <input type="checkbox" name="active" defaultChecked={selectedCreditType.active} />
                          {t("common.active")}
                        </label>

                        <div className="row span-2">
                          <button type="submit">{t("common.save")}</button>
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
                                ? t("admin.credit_types.delete_disabled_title")
                                : undefined
                            }
                          >
                            {t("admin.credit_types.delete_submit")}
                          </button>
                        </form>
                      </div>

                      {selectedCreditType.activity_count > 0 ? (
                        <p className="muted top-gap-sm">
                          {t("admin.credit_types.delete_blocked", { count: selectedCreditType.activity_count })}
                        </p>
                      ) : null}
                    </section>
                  </article>
                </section>
              ) : null}
            </>
          ) : null}

          {section === "integrations" ? (
            <AdminIntegrationPlanningEmbed
              accountWebsite={account?.website ?? ""}
              activities={activities}
              locations={integrationLocations}
              selectedActivityId={selectedIntegrationActivityId}
              selectedLocationId={selectedIntegrationLocationId}
              selectedDisplayDate={selectedIntegrationDate}
              language={language}
            />
          ) : null}

          {section !== "params-account" &&
          section !== "params-subscriptions" &&
          section !== "params-payments" &&
          section !== "params-referrals" &&
          section !== "params-messaging" &&
          section !== "activities" &&
          section !== "legal-entities" &&
          section !== "credit-types" &&
          section !== "integrations" ? (
            <section className="card config-placeholder-card">
              <h3>{t(placeholderTitleKeyBySection[section])}</h3>
              <p className="muted">{t("admin.config.placeholder_pending")}</p>
              <p className="muted">{t("admin.config.placeholder_v1_note")}</p>
            </section>
          ) : null}
        </div>
      </section>
    </section>
  );
}
