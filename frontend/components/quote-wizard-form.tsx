"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import ConfirmSubmitButton from "./confirm-submit-button";
import { localeForUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";

type ProspectOption = {
  id: string;
  label: string;
  email: string;
};

type ClientOption = {
  id: string;
  label: string;
  email: string;
};

type SearchablePersonOption = {
  id: string;
  label: string;
  email: string;
};

type QuoteTypeOption = {
  id: string;
  name: string;
  default_expiry_days: number;
  formula_id: string | null;
  formula_name: string | null;
  school_year_label: string | null;
};

type CatalogOption = {
  id: string;
  name: string;
};

type PaymentPlanOption = {
  id: string;
  name: string;
  payment_method: string;
};

type TermsTemplateOption = {
  id: string;
  name: string;
  language: string;
};

type LegalEntityOption = {
  id: string;
  name: string;
};

type QuoteTemplateOption = {
  id: string;
  code: string;
  name: string;
  language: string;
  is_default: boolean;
};

type LocationOption = {
  id: string;
  name: string;
  city: string | null;
};

type ActivityOption = {
  id: string;
  name: string;
  code?: string;
  service_code?: string;
  duration_minutes: number;
  default_course_rate_ttc: string | null;
};

type ProductOption = {
  id: string;
  title: string;
  price_incl_vat: string;
};

type KitOption = {
  id: string;
  title: string;
  effective_price_ttc: string;
};

type SolfegeRule = {
  id: string;
  level_code: string;
  duration_minutes: number;
  allowed_weekdays: number[];
  allowed_time_slots: Array<Record<string, unknown>>;
  location_id: string | null;
  modality: string | null;
};

type PlanningBlock = {
  uid: string;
  activity_id: string;
  location_id: string;
  weekday: number;
  recurrence_frequency: "weekly" | "biweekly" | "monthly";
  start_date: string;
  end_date: string;
  start_time: string;
  end_time: string;
  modality: string;
};

type SolfegeSlotOption = {
  key: string;
  weekday: number;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  location_id: string | null;
  modality: string | null;
  label: string;
};

function normalizeLang(value: string | null | undefined): UiLanguage {
  return String(value || "").trim().toLowerCase() === "en" ? "en" : "fr";
}

type QuoteWizardFormProps = {
  returnTo: string;
  newProspectHref: string;
  prospects: ProspectOption[];
  clients: ClientOption[];
  quoteTypes: QuoteTypeOption[];
  catalogs: CatalogOption[];
  paymentPlans: PaymentPlanOption[];
  termsTemplates: TermsTemplateOption[];
  legalEntities: LegalEntityOption[];
  quoteTemplates: QuoteTemplateOption[];
  locations: LocationOption[];
  activities: ActivityOption[];
  products: ProductOption[];
  kits: KitOption[];
  solfegeRules: SolfegeRule[];
  defaultProspectId: string;
  createAction: (formData: FormData) => Promise<void>;
  uiLanguage?: UiLanguage;
};

type LineKind = "activity" | "product" | "kit" | "discount" | "surcharge";

type WizardLine = {
  uid: string;
  kind: LineKind;
  refId: string;
  title: string;
  quantity: string;
  unitPrice: string;
};

const WEEKDAY_UNSET = -1;
const DEFAULT_QUOTE_SCHOOL_YEAR = "2026-2027";
const DEFAULT_EXPIRY_DAYS = "7";
const PARIS_DEFAULT_EXPIRY_DAYS = "5";
const DEFAULT_QUOTE_TEMPLATE_CODE = "TEMPLATE_COURS_COLLECTIF_ENFANT";
const DEFAULT_QUOTE_TEMPLATE_NAME = "Template cours collectif enfant";
const WEEKDAY_SHORT_LABELS: Record<UiLanguage, string[]> = {
  fr: ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
  en: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
};

function toMoney(value: string, currency = "EUR", language: UiLanguage = "fr"): string {
  const n = Number(value);
  const normalizedCurrency = (currency || "EUR").toUpperCase();
  if (!Number.isFinite(n)) {
    try {
      return new Intl.NumberFormat(localeForUiLanguage(language), { style: "currency", currency: normalizedCurrency }).format(0);
    } catch {
      return `0.00 ${normalizedCurrency}`;
    }
  }
  try {
    return new Intl.NumberFormat(localeForUiLanguage(language), { style: "currency", currency: normalizedCurrency }).format(n);
  } catch {
    return `${n.toFixed(2)} ${normalizedCurrency}`;
  }
}

function lineAmount(line: WizardLine): number {
  const qty = Number(line.quantity);
  const price = Number(line.unitPrice);
  if (!Number.isFinite(qty) || !Number.isFinite(price)) {
    return 0;
  }
  return qty * price;
}

function buildLinePayload(line: WizardLine, index: number, quoteLanguage: UiLanguage): Record<string, unknown> {
  if (line.kind === "discount") {
    return {
      line_category: "product",
      line_type: "discount",
      master_item_type: "discount_rule",
      title: line.title || uiText(quoteLanguage, "admin.quote_new.line_title_discount"),
      quantity: line.quantity || "1",
      unit_price_ttc: String(Math.abs(Number(line.unitPrice || "0"))),
      sort_order: index,
    };
  }
  if (line.kind === "surcharge") {
    return {
      line_category: "product",
      line_type: "surcharge",
      master_item_type: "surcharge_rule",
      title: line.title || uiText(quoteLanguage, "admin.quote_new.line_title_surcharge"),
      quantity: line.quantity || "1",
      unit_price_ttc: String(Math.abs(Number(line.unitPrice || "0"))),
      sort_order: index,
    };
  }
  if (line.kind === "activity") {
    return {
      line_category: "service",
      line_type: "item",
      master_item_type: "activity",
      activity_id: line.refId || null,
      title: line.title || uiText(quoteLanguage, "admin.quote_new.line_title_activity"),
      quantity: line.quantity || "1",
      unit_price_ttc: line.unitPrice || "0",
      sort_order: index,
    };
  }
  if (line.kind === "product") {
    return {
      line_category: "product",
      line_type: "item",
      master_item_type: "product",
      product_id: line.refId || null,
      title: line.title || uiText(quoteLanguage, "admin.quote_new.line_title_product"),
      quantity: line.quantity || "1",
      unit_price_ttc: line.unitPrice || "0",
      sort_order: index,
    };
  }
  return {
    line_category: "product",
    line_type: "item",
    master_item_type: "kit",
    kit_id: line.refId || null,
    title: line.title || uiText(quoteLanguage, "admin.quote_new.line_title_kit"),
    quantity: line.quantity || "1",
    unit_price_ttc: line.unitPrice || "0",
    sort_order: index,
  };
}

function countEstimatedSessions(
  startDate: string,
  endDate: string,
  weekdays: number[],
  recurrenceFrequency: PlanningBlock["recurrence_frequency"],
): number {
  if (!startDate || !endDate || weekdays.length === 0) {
    return 0;
  }
  const start = new Date(`${startDate}T00:00:00Z`);
  const end = new Date(`${endDate}T00:00:00Z`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) {
    return 0;
  }
  const set = new Set(weekdays);
  const matchedDates: Date[] = [];
  for (let d = new Date(start.getTime()); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
    const jsDay = d.getUTCDay();
    const mapped = (jsDay + 6) % 7;
    if (set.has(mapped)) {
      matchedDates.push(new Date(d.getTime()));
    }
  }
  if (recurrenceFrequency === "weekly") {
    return matchedDates.length;
  }
  if (recurrenceFrequency === "biweekly") {
    const firstByWeekday = new Map<number, Date>();
    let count = 0;
    for (const row of matchedDates) {
      const weekday = (row.getUTCDay() + 6) % 7;
      const first = firstByWeekday.get(weekday);
      if (!first) {
        firstByWeekday.set(weekday, row);
        count += 1;
        continue;
      }
      const deltaDays = Math.floor((row.getTime() - first.getTime()) / 86_400_000);
      if (deltaDays % 14 === 0) {
        count += 1;
      }
    }
    return count;
  }
  const firstMonthByWeekday = new Set<string>();
  let count = 0;
  for (const row of matchedDates) {
    const weekday = (row.getUTCDay() + 6) % 7;
    const key = `${row.getUTCFullYear()}-${row.getUTCMonth() + 1}-${weekday}`;
    if (firstMonthByWeekday.has(key)) {
      continue;
    }
    firstMonthByWeekday.add(key);
    count += 1;
  }
  return count;
}

function addMinutesToTime(startTime: string, deltaMinutes: number): string {
  const match = startTime.trim().match(/^(\d{2}):(\d{2})$/);
  if (!match) {
    return startTime;
  }
  const hours = Number.parseInt(match[1], 10);
  const minutes = Number.parseInt(match[2], 10);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
    return startTime;
  }
  const total = (hours * 60 + minutes + Math.max(0, deltaMinutes)) % (24 * 60);
  const outHours = Math.floor(total / 60)
    .toString()
    .padStart(2, "0");
  const outMinutes = (total % 60).toString().padStart(2, "0");
  return `${outHours}:${outMinutes}`;
}

function weekdayLabel(weekday: number, language: UiLanguage): string {
  if (weekday === WEEKDAY_UNSET) {
    return uiText(language, "admin.quote_new.selection_pending");
  }
  return WEEKDAY_SHORT_LABELS[language][weekday] ?? String(weekday);
}

function planningWeekdayOptions(language: UiLanguage): Array<{ value: number; label: string }> {
  return [
    { value: WEEKDAY_UNSET, label: uiText(language, "admin.quote_new.selection_pending") },
    ...WEEKDAY_SHORT_LABELS[language].map((label, index) => ({ value: index, label })),
  ];
}

function recurrenceOptions(language: UiLanguage): Array<{ value: PlanningBlock["recurrence_frequency"]; label: string }> {
  return [
    { value: "weekly", label: uiText(language, "admin.quote_new.recurrence_weekly") },
    { value: "biweekly", label: uiText(language, "admin.quote_new.recurrence_biweekly") },
    { value: "monthly", label: uiText(language, "admin.quote_new.recurrence_monthly") },
  ];
}

function timeSlotParts(slot: Record<string, unknown>): { start: string; end: string } | null {
  const start = typeof slot.start_time === "string" ? slot.start_time : typeof slot.start === "string" ? slot.start : "";
  const end = typeof slot.end_time === "string" ? slot.end_time : typeof slot.end === "string" ? slot.end : "";
  if (!start || !end) {
    return null;
  }
  return { start, end };
}

function slotOptionsFromRule(rule: SolfegeRule | null | undefined, language: UiLanguage): SolfegeSlotOption[] {
  if (!rule) {
    return [];
  }
  const options: SolfegeSlotOption[] = [];
  const hasStructuredWeekdays = rule.allowed_time_slots.some((slot) => {
    const weekday = Number.parseInt(String(slot.weekday ?? ""), 10);
    return Number.isFinite(weekday) && weekday >= 0 && weekday <= 6;
  });

  if (hasStructuredWeekdays) {
    for (const slot of rule.allowed_time_slots) {
      const parts = timeSlotParts(slot);
      if (!parts) {
        continue;
      }
      const weekday = Number.parseInt(String(slot.weekday ?? ""), 10);
      if (!Number.isFinite(weekday) || weekday < 0 || weekday > 6) {
        continue;
      }
      options.push({
        key: `${weekday}|${parts.start}|${parts.end}`,
        weekday,
        start_time: parts.start,
        end_time: parts.end,
        duration_minutes: rule.duration_minutes,
        location_id: rule.location_id,
        modality: rule.modality,
        label: `${weekdayLabel(weekday, language)} ${parts.start}-${parts.end}`,
      });
    }
    return options;
  }

  const weekdays = rule.allowed_weekdays.length > 0
    ? rule.allowed_weekdays.filter((day) => Number.isFinite(day) && day >= 0 && day <= 6)
    : [0, 1, 2, 3, 4, 5, 6];

  for (const weekday of weekdays) {
    for (const slot of rule.allowed_time_slots) {
      const parts = timeSlotParts(slot);
      if (!parts) {
        continue;
      }
      options.push({
        key: `${weekday}|${parts.start}|${parts.end}`,
        weekday,
        start_time: parts.start,
        end_time: parts.end,
        duration_minutes: rule.duration_minutes,
        location_id: rule.location_id,
        modality: rule.modality,
        label: `${weekdayLabel(weekday, language)} ${parts.start}-${parts.end}`,
      });
    }
  }
  return options;
}

function paymentMethodLabel(methodCode: string, language: UiLanguage): string {
  const normalized = String(methodCode || "").trim().toUpperCase();
  if (normalized === "CARD") return uiText(language, "admin.quote_detail.payment_method_card");
  if (normalized === "CARD_MONTHLY") return uiText(language, "admin.quote_detail.payment_method_card_monthly");
  if (normalized === "CARD_MONTHLY_FIXED") return uiText(language, "admin.quote_detail.payment_method_card_monthly_fixed");
  if (normalized === "CHECK") return uiText(language, "admin.quote_detail.payment_method_check");
  if (normalized === "BANK_TRANSFER") return uiText(language, "admin.quote_detail.payment_method_bank_transfer");
  if (normalized === "CASH") return uiText(language, "admin.quote_detail.payment_method_cash");
  if (normalized === "CARD_4X_FEES") return uiText(language, "admin.quote_detail.payment_method_card_4x_fees");
  if (!normalized) return uiText(language, "admin.quote_new.none");
  return normalized;
}

function normalizeSearchValue(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function sortedPersonOptions<T extends SearchablePersonOption>(options: T[], language: UiLanguage): T[] {
  const collator = new Intl.Collator(localeForUiLanguage(language), { sensitivity: "base" });
  return options
    .slice()
    .sort((left, right) => {
      const byLabel = collator.compare(left.label, right.label);
      return byLabel || collator.compare(left.email, right.email);
    });
}

function filterPersonOptions<T extends SearchablePersonOption>(options: T[], normalizedQuery: string): T[] {
  if (!normalizedQuery) {
    return options.slice(0, 40);
  }
  const tokens = normalizedQuery.split(/\s+/).filter(Boolean);
  return options
    .filter((item) => {
      const haystack = normalizeSearchValue(`${item.label} ${item.email}`);
      return tokens.every((token) => haystack.includes(token));
    })
    .slice(0, 40);
}

function isDefaultQuoteTypeCandidate(item: QuoteTypeOption): boolean {
  const name = normalizeSearchValue(item.name);
  const schoolYear = normalizeSearchValue(item.school_year_label ?? "");
  return name.includes("forfait") && (name.includes(DEFAULT_QUOTE_SCHOOL_YEAR) || schoolYear === DEFAULT_QUOTE_SCHOOL_YEAR);
}

function isParisLocation(item: LocationOption | null | undefined): boolean {
  return normalizeSearchValue(item?.city ?? "") === "paris";
}

function expiryDaysForContext(quoteType: QuoteTypeOption | null | undefined, location: LocationOption | null | undefined): string {
  if (isParisLocation(location)) {
    return PARIS_DEFAULT_EXPIRY_DAYS;
  }
  return String(quoteType?.default_expiry_days ?? DEFAULT_EXPIRY_DAYS);
}

function isCardPaymentPlan(item: PaymentPlanOption): boolean {
  const method = String(item.payment_method || "").trim().toUpperCase();
  const name = normalizeSearchValue(item.name);
  return method === "CARD" && name === "carte bancaire";
}

function isDefaultQuoteTemplateCandidate(item: QuoteTemplateOption): boolean {
  return item.code === DEFAULT_QUOTE_TEMPLATE_CODE || normalizeSearchValue(item.name) === normalizeSearchValue(DEFAULT_QUOTE_TEMPLATE_NAME);
}

function SearchablePersonSelect({
  name,
  label,
  placeholder,
  emptyLabel,
  selectPlaceholder,
  options,
  value,
  query,
  language,
  onChange,
  onQueryChange,
  emptyActionHref,
  emptyActionLabel,
  alternateOptions,
  alternateActionLabel,
  onAlternateAction,
}: {
  name: string;
  label: string;
  placeholder: string;
  emptyLabel: string;
  selectPlaceholder: string;
  options: SearchablePersonOption[];
  value: string;
  query: string;
  language: UiLanguage;
  onChange: (value: string) => void;
  onQueryChange: (value: string) => void;
  emptyActionHref?: string;
  emptyActionLabel?: string;
  alternateOptions?: SearchablePersonOption[];
  alternateActionLabel?: string | ((count: number) => string);
  onAlternateAction?: () => void;
}): JSX.Element {
  const sortedOptions = useMemo(() => sortedPersonOptions(options, language), [options, language]);
  const sortedAlternateOptions = useMemo(
    () => sortedPersonOptions(alternateOptions ?? [], language),
    [alternateOptions, language],
  );
  const normalizedQuery = normalizeSearchValue(query);
  const filteredOptions = useMemo(() => {
    return filterPersonOptions(sortedOptions, normalizedQuery);
  }, [normalizedQuery, sortedOptions]);
  const alternateFilteredOptions = useMemo(() => {
    return normalizedQuery ? filterPersonOptions(sortedAlternateOptions, normalizedQuery) : [];
  }, [normalizedQuery, sortedAlternateOptions]);
  const selectedOption = value ? sortedOptions.find((item) => item.id === value) ?? null : null;
  const visibleOptions =
    selectedOption && !filteredOptions.some((item) => item.id === selectedOption.id)
      ? [selectedOption, ...filteredOptions]
      : filteredOptions;
  const alternateLabel =
    typeof alternateActionLabel === "function"
      ? alternateActionLabel(alternateFilteredOptions.length)
      : alternateActionLabel;

  return (
    <div className="top-gap-sm stack gap-xs">
      <label>
        {label}
        <input
          type="search"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder={placeholder}
          autoComplete="off"
        />
      </label>
      <select name={name} value={value} onChange={(event) => onChange(event.target.value)} required>
        <option value="">{selectPlaceholder}</option>
        {visibleOptions.map((item) => (
          <option key={item.id} value={item.id}>
            {item.label} - {item.email}
          </option>
        ))}
      </select>
      {visibleOptions.length === 0 ? (
        <div className="row wrap gap-sm">
          <small className="muted">{emptyLabel}</small>
          {emptyActionHref && emptyActionLabel ? (
            <Link className="ghost" href={emptyActionHref}>
              {emptyActionLabel}
            </Link>
          ) : null}
          {alternateFilteredOptions.length > 0 && alternateLabel && onAlternateAction ? (
            <button className="ghost" type="button" onClick={onAlternateAction}>
              {alternateLabel}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function modalityLabel(value: string | null | undefined, language: UiLanguage): string {
  const normalized = String(value || "").trim().toUpperCase();
  if (!normalized || normalized === "AUTO") {
    return "";
  }
  if (normalized === "ONLINE") {
    return uiText(language, "admin.quote_new.modality_online");
  }
  if (normalized === "ONSITE") {
    return uiText(language, "admin.quote_new.modality_onsite");
  }
  return normalized;
}

function solfegeLevelFromActivity(activity: ActivityOption | undefined): string | null {
  if (!activity) {
    return null;
  }
  const candidates = [activity.name, activity.code, activity.service_code]
    .filter(Boolean)
    .map((value) => String(value));
  for (const candidate of candidates) {
    const match = candidate.match(/niveau\s*([1-5])/i) || candidate.match(/SOLFEGE[_\-\s]*NIVEAU[_\-\s]*([1-5])/i);
    if (match?.[1]) {
      return match[1];
    }
  }
  return null;
}

function isSolfegeActivity(activity: ActivityOption | undefined): boolean {
  if (!activity) {
    return false;
  }
  const haystack = [activity.name, activity.code, activity.service_code].filter(Boolean).join(" ").toLowerCase();
  return haystack.includes("solfege");
}

function isCatalogKind(kind: LineKind): boolean {
  return kind === "activity" || kind === "product" || kind === "kit";
}

export default function QuoteWizardForm({
  returnTo,
  newProspectHref,
  prospects,
  clients,
  quoteTypes,
  catalogs,
  paymentPlans,
  termsTemplates,
  legalEntities,
  quoteTemplates,
  locations,
  activities,
  products,
  kits,
  solfegeRules,
  defaultProspectId,
  createAction,
  uiLanguage = "fr",
}: QuoteWizardFormProps): JSX.Element {
  const t = (key: string, values?: Record<string, string | number>) => uiText(uiLanguage, key, values);
  const createDraftFormId = "quote-wizard-create-draft-form";
  const defaultLegalEntity =
    legalEntities.find((item) => item.name.toUpperCase().includes("PIANO ACADEMIE")) ?? legalEntities[0] ?? null;
  const initialQuoteType = quoteTypes.find(isDefaultQuoteTypeCandidate) ?? quoteTypes[0] ?? null;
  const initialQuoteTypeId = initialQuoteType?.id ?? "";
  const defaultPaymentPlan = paymentPlans.find(isCardPaymentPlan) ?? paymentPlans[0] ?? null;
  const defaultQuoteTemplate = quoteTemplates.find(isDefaultQuoteTemplateCandidate) ?? null;
  const [contextType, setContextType] = useState<"acquisition" | "active_client">("acquisition");
  const [selectedProspectId, setSelectedProspectId] = useState<string>(defaultProspectId || "");
  const [selectedClientId, setSelectedClientId] = useState<string>("");
  const [recipientQuery, setRecipientQuery] = useState<string>("");
  const [selectedQuoteTypeId, setSelectedQuoteTypeId] = useState<string>(initialQuoteTypeId);
  const [expiryDaysInput, setExpiryDaysInput] = useState<string>(expiryDaysForContext(initialQuoteType, null));
  const [expiryDaysTouched, setExpiryDaysTouched] = useState<boolean>(false);
  const [schoolYearLabelInput, setSchoolYearLabelInput] = useState<string>(DEFAULT_QUOTE_SCHOOL_YEAR);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>(defaultQuoteTemplate?.id ?? "");
  const [selectedTermsTemplateId, setSelectedTermsTemplateId] = useState<string>("");
  const [language, setLanguage] = useState<UiLanguage>(normalizeLang(defaultQuoteTemplate?.language ?? uiLanguage));
  const [currency, setCurrency] = useState<string>("EUR");
  const [preRegistrationDepositEnabled, setPreRegistrationDepositEnabled] = useState<"no" | "yes">("no");
  const [preRegistrationDepositAmount, setPreRegistrationDepositAmount] = useState<string>("200.00");
  const [estimatedLevel, setEstimatedLevel] = useState<string>("");
  const [selectedSolfegeSlotKey, setSelectedSolfegeSlotKey] = useState<string>("");
  const [lines, setLines] = useState<WizardLine[]>([]);
  const [planningBlocks, setPlanningBlocks] = useState<PlanningBlock[]>([]);

  const sessionsCount = useMemo(
    () => planningBlocks.reduce((sum, block) => {
      if (block.weekday === WEEKDAY_UNSET) {
        return sum;
      }
      const blockCount = countEstimatedSessions(block.start_date, block.end_date, [block.weekday], block.recurrence_frequency);
      return sum + blockCount;
    }, 0),
    [planningBlocks],
  );

  const total = useMemo(() => lines.reduce((sum, line) => sum + lineAmount(line), 0), [lines]);

  const selectedSolfegeRule = useMemo(
    () => solfegeRules.find((rule) => String(rule.level_code) === String(estimatedLevel)),
    [solfegeRules, estimatedLevel],
  );

  const solfegeSlotOptions = useMemo<SolfegeSlotOption[]>(() => slotOptionsFromRule(selectedSolfegeRule, language), [selectedSolfegeRule, language]);

  const selectedSolfegeSlot = useMemo(
    () => solfegeSlotOptions.find((item) => item.key === selectedSolfegeSlotKey) ?? null,
    [solfegeSlotOptions, selectedSolfegeSlotKey],
  );
  const selectedQuoteType = useMemo(
    () => quoteTypes.find((item) => item.id === selectedQuoteTypeId) ?? null,
    [quoteTypes, selectedQuoteTypeId],
  );
  const selectedPlanningLocation = useMemo(() => {
    const firstLocationId = planningBlocks.map((block) => block.location_id).find(Boolean);
    return firstLocationId ? locations.find((item) => item.id === firstLocationId) ?? null : null;
  }, [locations, planningBlocks]);
  const languageTemplates = useMemo(
    () => quoteTemplates.filter((item) => normalizeLang(item.language) === normalizeLang(language)),
    [quoteTemplates, language],
  );
  const languageTermsTemplates = useMemo(
    () => termsTemplates.filter((item) => normalizeLang(item.language) === normalizeLang(language)),
    [termsTemplates, language],
  );

  const planningBlocksJson = useMemo(
    () =>
      JSON.stringify(
        planningBlocks.map((row) => {
          const activity = activities.find((item) => item.id === row.activity_id);
          const locationLabel = locations.find((item) => item.id === row.location_id)?.name || null;
          const selectionPending = row.weekday === WEEKDAY_UNSET;
          const pendingLevel =
            selectionPending && isSolfegeActivity(activity) ? solfegeLevelFromActivity(activity) : null;
          const pendingRule = pendingLevel
            ? solfegeRules.find((rule) => String(rule.level_code) === String(pendingLevel)) || null
            : null;
          const pendingSlotOptions =
            selectionPending && pendingLevel
              ? slotOptionsFromRule(pendingRule, language).map((slot) => ({
                  weekday: slot.weekday,
                  weekday_label: weekdayLabel(slot.weekday, language),
                  start_time: slot.start_time,
                  end_time: slot.end_time,
                  duration_minutes: slot.duration_minutes,
                  location_id: slot.location_id,
                  location_label: locationLabel,
                  modality: slot.modality,
                  label: slot.label,
                }))
              : [];
          return {
            activity_id: row.activity_id || null,
            activity_label: activity?.name || null,
            location_id: row.location_id || null,
            location_label: locationLabel,
            weekday: row.weekday,
            weekday_label: weekdayLabel(row.weekday, language),
            recurrence_frequency: row.recurrence_frequency,
            start_date: row.start_date,
            end_date: row.end_date,
            start_time: selectionPending ? "" : row.start_time,
            end_time: selectionPending ? "" : row.end_time,
            modality: row.modality || null,
            selection_pending: selectionPending,
            pending_solfege_level: pendingLevel,
            pending_slot_options: pendingSlotOptions,
          };
        }),
      ),
    [planningBlocks, activities, locations, solfegeRules, language],
  );

  const selectedSolfegeSlotJson = useMemo(
    () => (selectedSolfegeSlot ? JSON.stringify(selectedSolfegeSlot) : ""),
    [selectedSolfegeSlot],
  );

  const linesJson = useMemo(
    () => JSON.stringify(lines.map((line, index) => buildLinePayload(line, index, language))),
    [lines, language],
  );

  function addPlanningBlock(): void {
    const defaultActivityId = activities[0]?.id ?? "";
    const defaultDuration = activities[0]?.duration_minutes ?? 60;
    const startTime = "17:00";
    setPlanningBlocks((prev) => [
      ...prev,
      {
        uid: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        activity_id: defaultActivityId,
        location_id: locations[0]?.id ?? "",
        weekday: 0,
        recurrence_frequency: "weekly",
        start_date: "",
        end_date: "",
        start_time: startTime,
        end_time: addMinutesToTime(startTime, defaultDuration),
        modality: "",
      },
    ]);
  }

  function removePlanningBlock(uid: string): void {
    setPlanningBlocks((prev) => prev.filter((row) => row.uid !== uid));
  }

  function updatePlanningBlock(uid: string, patch: Partial<PlanningBlock>): void {
    setPlanningBlocks((prev) => prev.map((row) => (row.uid === uid ? { ...row, ...patch } : row)));
  }

  function syncPlanningActivity(uid: string, activityId: string, startTime: string): void {
    const activity = activities.find((item) => item.id === activityId);
    const duration = activity?.duration_minutes ?? 60;
    updatePlanningBlock(uid, {
      activity_id: activityId,
      end_time: addMinutesToTime(startTime, duration),
    });
  }

  function addLine(kind: LineKind): void {
    const uid = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setLines((prev) => [
      ...prev,
      {
        uid,
        kind,
        refId: "",
        title: "",
        quantity: "1",
        unitPrice: "0",
      },
    ]);
  }

  function removeLine(uid: string): void {
    setLines((prev) => prev.filter((line) => line.uid !== uid));
  }

  function updateLine(uid: string, patch: Partial<WizardLine>): void {
    setLines((prev) => prev.map((line) => (line.uid === uid ? { ...line, ...patch } : line)));
  }

  function applyRefToLine(uid: string, kind: LineKind, refId: string): void {
    if (!refId) {
      updateLine(uid, { refId: "", title: "", unitPrice: "0" });
      return;
    }
    if (kind === "activity") {
      const activity = activities.find((item) => item.id === refId);
      updateLine(uid, {
        refId,
        title: activity?.name ?? uiText(language, "admin.quote_new.line_title_activity"),
        unitPrice: activity?.default_course_rate_ttc ?? "0",
      });
      return;
    }
    if (kind === "product") {
      const product = products.find((item) => item.id === refId);
      updateLine(uid, {
        refId,
        title: product?.title ?? uiText(language, "admin.quote_new.line_title_product"),
        unitPrice: product?.price_incl_vat ?? "0",
      });
      return;
    }
    const kit = kits.find((item) => item.id === refId);
    updateLine(uid, {
      refId,
      title: kit?.title ?? uiText(language, "admin.quote_new.line_title_kit"),
      unitPrice: kit?.effective_price_ttc ?? "0",
    });
  }

  function selectableOptions(kind: LineKind): Array<{ id: string; label: string }> {
    if (kind === "activity") {
      return activities.map((item) => ({ id: item.id, label: item.name }));
    }
    if (kind === "product") {
      return products.map((item) => ({ id: item.id, label: item.title }));
    }
    if (kind === "kit") {
      return kits.map((item) => ({ id: item.id, label: item.title }));
    }
    return [];
  }

  const planningWeekdayChoices = useMemo(() => planningWeekdayOptions(uiLanguage), [uiLanguage]);
  const recurrenceChoices = useMemo(() => recurrenceOptions(uiLanguage), [uiLanguage]);
  const contextLabel = contextType === "acquisition" ? t("admin.quote_new.context_acquisition") : t("admin.quote_new.context_active_client");
  const quoteLanguageLabel = language === "en" ? t("common.english") : t("common.french");

  useEffect(() => {
    if (expiryDaysTouched) {
      return;
    }
    setExpiryDaysInput(expiryDaysForContext(selectedQuoteType, selectedPlanningLocation));
  }, [expiryDaysTouched, selectedPlanningLocation, selectedQuoteType]);

  function lineKindLabel(kind: LineKind): string {
    if (kind === "activity") return t("admin.quote_new.line_kind_activity");
    if (kind === "product") return t("admin.quote_new.line_kind_product");
    if (kind === "kit") return t("admin.quote_new.line_kind_kit");
    if (kind === "discount") return t("admin.quote_new.line_kind_discount");
    return t("admin.quote_new.line_kind_surcharge");
  }

  return (
    <form id={createDraftFormId} action={createAction} className="quote-wizard-layout">
      <input type="hidden" name="return_to" value={returnTo} />
      <input type="hidden" name="lines_json" value={linesJson} />
      <input type="hidden" name="planning_blocks_json" value={planningBlocksJson} />
      <input type="hidden" name="solfege_slot_json" value={selectedSolfegeSlotJson} />

      <section className="quote-wizard-main stack">
        <article className="card quote-wizard-card">
          <h3>{t("admin.quote_new.section_context_title")}</h3>
          <p className="muted">{t("admin.quote_new.section_context_subtitle")}</p>
          <div className="row wrap gap-sm top-gap-sm">
            <label className="row gap-xs">
              <input
                type="radio"
                name="context_type"
                value="acquisition"
                checked={contextType === "acquisition"}
                onChange={() => setContextType("acquisition")}
              />
              {t("admin.quote_new.context_acquisition")}
            </label>
            <label className="row gap-xs">
              <input
                type="radio"
                name="context_type"
                value="active_client"
                checked={contextType === "active_client"}
                onChange={() => setContextType("active_client")}
              />
              {t("admin.quote_new.context_active_client")}
            </label>
          </div>
          {contextType === "acquisition" ? (
            <SearchablePersonSelect
              name="prospect_id"
              label={t("admin.quote_new.prospect")}
              placeholder={t("admin.quote_new.search_prospect")}
              emptyLabel={t("admin.quote_new.no_prospect_results")}
              selectPlaceholder={t("admin.quote_new.select_prospect")}
              options={prospects}
              value={selectedProspectId}
              query={recipientQuery}
              language={language}
              onChange={setSelectedProspectId}
              onQueryChange={setRecipientQuery}
              emptyActionHref={newProspectHref}
              emptyActionLabel={t("admin.quote_new.new_prospect")}
              alternateOptions={clients}
              alternateActionLabel={(count) => t("admin.quote_new.matching_clients_found", { count })}
              onAlternateAction={() => {
                setSelectedProspectId("");
                setContextType("active_client");
              }}
            />
          ) : (
            <SearchablePersonSelect
              name="client_id"
              label={t("admin.quote_new.client")}
              placeholder={t("admin.quote_new.search_client")}
              emptyLabel={t("admin.quote_new.no_client_results")}
              selectPlaceholder={t("admin.quote_new.select_client")}
              options={clients}
              value={selectedClientId}
              query={recipientQuery}
              language={language}
              onChange={setSelectedClientId}
              onQueryChange={setRecipientQuery}
              alternateOptions={prospects}
              alternateActionLabel={(count) => t("admin.quote_new.matching_prospects_found", { count })}
              onAlternateAction={() => {
                setSelectedClientId("");
                setContextType("acquisition");
              }}
            />
          )}
        </article>

        <article className="card quote-wizard-card">
          <h3>{t("admin.quote_new.section_settings_title")}</h3>
          <div className="grid cols-2 top-gap-sm">
            <label>
              {t("admin.quote_new.quote_type")}
              <select
                name="quote_type_id"
                value={selectedQuoteTypeId}
                onChange={(event) => {
                  const nextQuoteTypeId = event.target.value;
                  setSelectedQuoteTypeId(nextQuoteTypeId);
                  const nextQuoteType = quoteTypes.find((item) => item.id === nextQuoteTypeId) ?? null;
                  setExpiryDaysTouched(false);
                  setExpiryDaysInput(expiryDaysForContext(nextQuoteType, selectedPlanningLocation));
                  setSchoolYearLabelInput(nextQuoteType?.school_year_label ?? "");
                }}
              >
                <option value="">{t("admin.quote_new.default_option")}</option>
                {quoteTypes.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
              {selectedQuoteType ? (
                <small className="muted">
                  {t("admin.quote_new.quote_type_hint", {
                    days: selectedQuoteType.default_expiry_days,
                    school_year: selectedQuoteType.school_year_label || "-",
                    formula: selectedQuoteType.formula_name || t("admin.quote_new.none"),
                  })}
                </small>
              ) : null}
            </label>
            <label>
              {t("admin.quote_new.pricing_catalog")}
              <select name="pricing_catalog_id" defaultValue={catalogs[0]?.id ?? ""}>
                <option value="">{t("admin.quote_new.none")}</option>
                {catalogs.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("admin.quote_new.linked_formula")}
              <input
                type="text"
                value={selectedQuoteType?.formula_name ?? t("admin.quote_new.none")}
                readOnly
                disabled
              />
            </label>
            <label>
              {t("admin.quote_new.quote_template")}
              <select name="quote_template_uuid" value={selectedTemplateId} onChange={(event) => {
                const nextId = event.target.value;
                setSelectedTemplateId(nextId);
                const template = quoteTemplates.find((item) => item.id === nextId);
                if (template?.language) {
                  setLanguage(normalizeLang(template.language));
                }
              }}>
                <option value="">{t("admin.quote_new.document_rule_auto")}</option>
                {languageTemplates.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
              <small className="muted">{t("admin.quote_new.document_rule_hint")}</small>
            </label>
            <label>
              {t("admin.quote_new.payment_plan")}
              <select name="payment_plan_id" defaultValue={defaultPaymentPlan?.id ?? ""}>
                <option value="">{t("admin.quote_new.none")}</option>
                {paymentPlans.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} ({paymentMethodLabel(item.payment_method, uiLanguage)})
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("admin.quote_new.legal_entity")}
              <select name="legal_entity_id" defaultValue={defaultLegalEntity?.id ?? ""}>
                <option value="">{t("admin.quote_new.none_feminine")}</option>
                {legalEntities.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("admin.quote_new.terms_template")}
              <select
                name="terms_template_id"
                value={selectedTermsTemplateId}
                onChange={(event) => {
                  const nextId = event.target.value;
                  setSelectedTermsTemplateId(nextId);
                  const template = termsTemplates.find((item) => item.id === nextId);
                  if (template?.language) {
                    setLanguage(normalizeLang(template.language));
                  }
                }}
              >
                <option value="">{t("admin.quote_new.document_rule_auto")}</option>
                {languageTermsTemplates.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} ({normalizeLang(item.language) === "en" ? t("common.english") : t("common.french")})
                  </option>
                ))}
              </select>
              <small className="muted">{t("admin.quote_new.document_rule_hint")}</small>
            </label>
            <label>
              {t("admin.quote_new.school_year")}
              <input
                type="text"
                name="school_year_label"
                placeholder={t("admin.quote_new.school_year_placeholder")}
                value={schoolYearLabelInput}
                onChange={(event) => setSchoolYearLabelInput(event.target.value)}
              />
            </label>
            <label>
              {t("admin.quote_new.currency")}
              <select name="currency" value={currency} onChange={(event) => setCurrency(event.target.value)}>
                <option value="EUR">EUR</option>
                <option value="USD">USD</option>
                <option value="GBP">GBP</option>
              </select>
            </label>
            <label>
              {t("common.language")}
              <select
                name="language"
                value={language}
                onChange={(event) => {
                  const nextLanguage = normalizeLang(event.target.value);
                  setLanguage(nextLanguage);
                  const currentTemplate = quoteTemplates.find((item) => item.id === selectedTemplateId);
                  if (currentTemplate && normalizeLang(currentTemplate.language) === nextLanguage) {
                    const currentTermsTemplate = termsTemplates.find((item) => item.id === selectedTermsTemplateId);
                    if (currentTermsTemplate && normalizeLang(currentTermsTemplate.language) === nextLanguage) {
                      return;
                    }
                  } else {
                    setSelectedTemplateId("");
                  }
                  const currentTermsTemplate = termsTemplates.find((item) => item.id === selectedTermsTemplateId);
                  if (!currentTermsTemplate || normalizeLang(currentTermsTemplate.language) !== nextLanguage) {
                    setSelectedTermsTemplateId("");
                  }
                }}
              >
                <option value="fr">{t("common.french")}</option>
                <option value="en">{t("common.english")}</option>
              </select>
            </label>
            <label>
              {t("admin.quote_new.expiry_days")}
              <input
                type="number"
                name="expiry_days"
                min={1}
                max={120}
                value={expiryDaysInput}
                onChange={(event) => {
                  setExpiryDaysTouched(true);
                  setExpiryDaysInput(event.target.value);
                }}
                required
              />
            </label>
            <label>
              {t("admin.quote_new.financial_adjustment")}
              <select name="financial_adjustment_type" defaultValue="none">
                <option value="none">{t("admin.quote_new.none")}</option>
                <option value="credit">{t("admin.quote_new.adjustment_credit")}</option>
                <option value="debt">{t("admin.quote_new.adjustment_debt")}</option>
              </select>
            </label>
            <label>
              {t("admin.quote_new.pass_recup")}
              <select name="pass_recup_mode" defaultValue="auto">
                <option value="auto">{t("admin.quote_new.pass_recup_auto")}</option>
                <option value="enabled">{t("admin.quote_new.pass_recup_enabled")}</option>
                <option value="disabled">{t("admin.quote_new.pass_recup_disabled")}</option>
              </select>
            </label>
            <label>
              {t("admin.quote_new.pre_registration_deposit")}
              <select
                name="pre_registration_deposit_enabled"
                value={preRegistrationDepositEnabled}
                onChange={(event) => {
                  const next = event.target.value === "yes" ? "yes" : "no";
                  setPreRegistrationDepositEnabled(next);
                  if (next === "yes" && !preRegistrationDepositAmount.trim()) {
                    setPreRegistrationDepositAmount("200.00");
                  }
                }}
              >
                <option value="no">{t("common.no")}</option>
                <option value="yes">{t("common.yes")}</option>
              </select>
            </label>
            <label>
              {t("admin.quote_new.adjustment_amount_ttc")}
              <input
                type="number"
                name="financial_adjustment_amount_ttc"
                min={0}
                step="0.01"
                placeholder={t("admin.quote_new.adjustment_amount_placeholder")}
              />
            </label>
            <label>
              {t("admin.quote_new.adjustment_date")}
              <input type="date" name="financial_adjustment_effective_date" />
            </label>
            <label>
              {t("admin.quote_new.deposit_amount_ttc")}
              <input
                type="number"
                name="pre_registration_deposit_amount_ttc"
                min={0}
                step="0.01"
                value={preRegistrationDepositAmount}
                onChange={(event) => setPreRegistrationDepositAmount(event.target.value)}
                placeholder={t("admin.quote_new.deposit_amount_placeholder")}
                disabled={preRegistrationDepositEnabled !== "yes"}
              />
              <small className="muted">{t("admin.quote_new.deposit_default_hint")}</small>
            </label>
            <label>
              {t("admin.quote_new.adjustment_label")}
              <input type="text" name="financial_adjustment_label" placeholder={t("admin.quote_new.adjustment_label_placeholder")} />
            </label>
          </div>
        </article>

        <article className="card quote-wizard-card">
          <h3>{t("admin.quote_new.section_planning_title")}</h3>
          <p className="muted">
            {t("admin.quote_new.section_planning_subtitle")}
          </p>
          <div className="row wrap gap-sm top-gap-sm">
            <button type="button" className="ghost" onClick={addPlanningBlock}>+ {t("admin.quote_new.add_planning_activity")}</button>
          </div>
          {planningBlocks.length === 0 ? <p className="muted top-gap-sm">{t("admin.quote_new.no_planning_block")}</p> : null}
          <div className="list top-gap-sm">
            {planningBlocks.map((block, index) => {
              const activity = activities.find((item) => item.id === block.activity_id);
              const selectionPending = block.weekday === WEEKDAY_UNSET;
              const blockSolfegeLevel = isSolfegeActivity(activity) ? solfegeLevelFromActivity(activity) : null;
              const pendingSlotOptions =
                selectionPending && blockSolfegeLevel
                  ? slotOptionsFromRule(
                      solfegeRules.find((rule) => String(rule.level_code) === String(blockSolfegeLevel)) || null,
                      language,
                    )
                  : [];
              return (
              <article key={block.uid} className="item">
                <div className="row spread wrap gap-sm">
                  <strong>{activity?.name || t("admin.quote_new.planning_activity_fallback", { index: index + 1 })}</strong>
                  <span className="badge">
                    {t("admin.quote_new.estimated_lessons_badge", {
                      count: selectionPending ? 0 : countEstimatedSessions(block.start_date, block.end_date, [block.weekday], block.recurrence_frequency),
                    })}
                  </span>
                  <button type="button" className="ghost small-btn" onClick={() => removePlanningBlock(block.uid)}>
                    {t("common.delete")}
                  </button>
                </div>
                <div className="grid cols-4 top-gap-sm">
                  <label>
                    {t("admin.quote_new.activity")}
                    <select
                      value={block.activity_id}
                      onChange={(event) => syncPlanningActivity(block.uid, event.target.value, block.start_time)}
                    >
                      <option value="">{t("admin.quote_new.select_option")}</option>
                      {activities.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name} ({item.duration_minutes} min)
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    {t("common.location")}
                    <select
                      value={block.location_id}
                      onChange={(event) => updatePlanningBlock(block.uid, { location_id: event.target.value })}
                    >
                      <option value="">{t("admin.quote_new.none")}</option>
                      {locations.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    {t("admin.quote_new.day")}
                    <select
                      value={String(block.weekday)}
                      onChange={(event) => {
                        const parsed = Number.parseInt(event.target.value, 10);
                        if (!Number.isFinite(parsed)) {
                          return;
                        }
                        if (parsed === WEEKDAY_UNSET) {
                          updatePlanningBlock(block.uid, {
                            weekday: WEEKDAY_UNSET,
                            start_time: "",
                            end_time: "",
                          });
                          return;
                        }
                        const duration = activity?.duration_minutes ?? 60;
                        const nextStart = block.start_time || "17:00";
                        updatePlanningBlock(block.uid, {
                          weekday: parsed,
                          start_time: nextStart,
                          end_time: addMinutesToTime(nextStart, duration),
                        });
                      }}
                    >
                      {planningWeekdayChoices.map((entry) => (
                        <option key={entry.value} value={entry.value}>
                          {entry.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    {t("admin.quote_new.modality")}
                    <select
                      value={block.modality}
                      onChange={(event) => updatePlanningBlock(block.uid, { modality: event.target.value })}
                    >
                      <option value="">{t("admin.quote_new.auto")}</option>
                      <option value="ONLINE">{t("admin.quote_new.modality_online")}</option>
                      <option value="ONSITE">{t("admin.quote_new.modality_onsite")}</option>
                    </select>
                  </label>
                  <label>
                    {t("admin.quote_new.frequency")}
                    <select
                      value={block.recurrence_frequency}
                      onChange={(event) => {
                        const next = event.target.value === "biweekly" || event.target.value === "monthly"
                          ? event.target.value
                          : "weekly";
                        updatePlanningBlock(block.uid, { recurrence_frequency: next });
                      }}
                    >
                      {recurrenceChoices.map((entry) => (
                        <option key={`${block.uid}-freq-${entry.value}`} value={entry.value}>
                          {entry.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    {t("admin.quote_new.start_date")}
                    <input type="date" value={block.start_date} onChange={(event) => updatePlanningBlock(block.uid, { start_date: event.target.value })} />
                  </label>
                  <label>
                    {t("admin.quote_new.end_date")}
                    <input type="date" value={block.end_date} onChange={(event) => updatePlanningBlock(block.uid, { end_date: event.target.value })} />
                  </label>
                  <label>
                    {t("admin.quote_new.start_time")}
                    <input
                      type="time"
                      value={block.start_time}
                      onChange={(event) => {
                        const nextStart = event.target.value;
                        const activity = activities.find((item) => item.id === block.activity_id);
                        const duration = activity?.duration_minutes ?? 60;
                        updatePlanningBlock(block.uid, {
                          start_time: nextStart,
                          end_time: addMinutesToTime(nextStart, duration),
                        });
                      }}
                      disabled={selectionPending}
                    />
                  </label>
                  <label>
                    {t("admin.quote_new.end_time_auto")}
                    <input type="time" value={block.end_time} readOnly />
                  </label>
                  {selectionPending ? (
                    <div className="cols-span-4">
                      <p className="muted">{t("admin.quote_new.pending_day_message")}</p>
                      {pendingSlotOptions.length > 0 ? (
                        <ul className="muted top-gap-sm">
                          {pendingSlotOptions.map((slot) => (
                            <li key={`${block.uid}-pending-${slot.key}`}>{slot.label}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="muted top-gap-sm">{t("admin.quote_new.no_slot_for_level")}</p>
                      )}
                    </div>
                  ) : null}
                  <p className="muted cols-span-4">
                    {t("admin.quote_new.planning_note")}
                  </p>
                </div>
              </article>
              );
            })}
          </div>
          <p className="muted top-gap-sm">{t("admin.quote_new.planning_summary", { count: sessionsCount })}</p>
        </article>

        <article className="card quote-wizard-card">
          <h3>{t("admin.quote_new.section_solfege_title")}</h3>
          <label className="top-gap-sm">
            {t("admin.quote_new.estimated_level")}
            <select name="estimated_solfege_level" value={estimatedLevel} onChange={(event) => setEstimatedLevel(event.target.value)}>
              <option value="">{t("admin.quote_new.not_applicable")}</option>
              {["1", "2", "3", "4", "5"].map((level) => (
                <option key={level} value={level}>
                  {t("admin.quote_new.level_option", { level })}
                </option>
              ))}
            </select>
          </label>
          {selectedSolfegeRule ? (
            <div className="quote-solfege-preview top-gap-sm">
              <p>
                {t("admin.quote_new.suggested_duration")}: <strong>{selectedSolfegeRule.duration_minutes} min</strong>
              </p>
              <p className="muted">
                {t("admin.quote_new.allowed_days")}: {selectedSolfegeRule.allowed_weekdays.length > 0 ? selectedSolfegeRule.allowed_weekdays.map((day) => weekdayLabel(day, language)).join(", ") : t("admin.quote_new.all_days")}
              </p>
              <p className="muted">{t("admin.quote_new.configured_slots", { count: solfegeSlotOptions.length })}</p>
              <label className="top-gap-sm">
                {t("admin.quote_new.proposed_slot")}
                <select value={selectedSolfegeSlotKey} onChange={(event) => setSelectedSolfegeSlotKey(event.target.value)}>
                  <option value="">{t("admin.quote_new.select_slot")}</option>
                  {solfegeSlotOptions.map((slot) => (
                    <option key={slot.key} value={slot.key}>
                      {slot.label}
                    </option>
                  ))}
                </select>
              </label>
              {selectedSolfegeSlot ? (
                <p className="muted top-gap-sm">
                  {t("admin.quote_new.selection_label")}: <strong>{selectedSolfegeSlot.label}</strong>
                  {selectedSolfegeSlot.modality ? ` · ${modalityLabel(selectedSolfegeSlot.modality, uiLanguage)}` : ""}
                </p>
              ) : null}
            </div>
          ) : (
            <p className="muted top-gap-sm">{t("admin.quote_new.select_level_hint")}</p>
          )}
        </article>

        <article className="card quote-wizard-card">
          <h3>{t("admin.quote_new.section_lines_title")}</h3>
          <div className="row wrap gap-sm top-gap-sm">
            <button type="button" className="ghost" onClick={() => addLine("activity")}>+ {t("admin.quote_new.add_line_activity")}</button>
            <button type="button" className="ghost" onClick={() => addLine("product")}>+ {t("admin.quote_new.add_line_product")}</button>
            <button type="button" className="ghost" onClick={() => addLine("kit")}>+ {t("admin.quote_new.add_line_kit")}</button>
            <button type="button" className="ghost" onClick={() => addLine("discount")}>+ {t("admin.quote_new.add_line_discount")}</button>
            <button type="button" className="ghost" onClick={() => addLine("surcharge")}>+ {t("admin.quote_new.add_line_surcharge")}</button>
          </div>
          {lines.length === 0 ? <p className="muted top-gap-sm">{t("admin.quote_new.no_lines")}</p> : null}
          <div className="quote-lines-list top-gap-sm">
            {lines.map((line) => (
              <article key={line.uid} className="quote-line-card">
                <div className="row spread wrap gap-sm">
                  <strong>{lineKindLabel(line.kind)}</strong>
                  <button type="button" className="ghost small-btn" onClick={() => removeLine(line.uid)}>
                    {t("common.delete")}
                  </button>
                </div>
                {(line.kind === "activity" || line.kind === "product" || line.kind === "kit") ? (
                  <label className="top-gap-sm">
                    {t("admin.quote_new.element")}
                    <select
                      value={line.refId}
                      onChange={(event) => applyRefToLine(line.uid, line.kind, event.target.value)}
                    >
                      <option value="">{t("admin.quote_new.select_option")}</option>
                      {selectableOptions(line.kind).map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
                <div className="grid cols-3 top-gap-sm">
                  <label className="cols-span-3">
                    {t("admin.quote_new.line_title")}
                    <input type="text" value={line.title} onChange={(event) => updateLine(line.uid, { title: event.target.value })} required />
                  </label>
                  <label>
                    {t("common.quantity")}
                    <input type="number" min={0.01} step="0.01" value={line.quantity} onChange={(event) => updateLine(line.uid, { quantity: event.target.value })} required />
                  </label>
                  <label>
                    {t("admin.quote_new.price_ttc")}
                    <input
                      type="number"
                      step="0.01"
                      value={line.unitPrice}
                      onChange={(event) => updateLine(line.uid, { unitPrice: event.target.value })}
                      required
                    />
                  </label>
                  <div className="quote-line-amount">
                    <span>{t("common.amount")}</span>
                    <strong>{toMoney(String(lineAmount(line)), currency, uiLanguage)}</strong>
                  </div>
                </div>
                {isCatalogKind(line.kind) ? (
                  <small className="muted">
                    {t("admin.quote_new.catalog_prefill_hint")}
                  </small>
                ) : null}
              </article>
            ))}
          </div>
        </article>

        <article className="card quote-wizard-card">
          <h3>{t("admin.quote_new.section_finalize_title")}</h3>
          <p className="muted">{t("admin.quote_new.section_finalize_subtitle")}</p>
          <div className="row wrap gap-sm top-gap-sm">
            <ConfirmSubmitButton
              formId={createDraftFormId}
              label={t("admin.quote_new.create_draft")}
              title={t("admin.quote_new.confirm_title")}
              description={t("admin.quote_new.confirm_description")}
              confirmLabel={t("admin.quote_new.confirm_execute")}
            />
            <a className="ghost" href={returnTo}>{t("common.cancel")}</a>
          </div>
        </article>
      </section>

      <aside className="quote-wizard-sticky">
        <article className="card quote-summary-card">
          <h3>{t("admin.quote_new.sticky_title")}</h3>
          <p className="muted">{t("admin.quote_new.sticky_context")}: <strong>{contextLabel}</strong></p>
          <p className="muted">{t("admin.quote_new.sticky_currency_language", { currency, language: quoteLanguageLabel })}</p>
          <p className="muted">{t("admin.quote_new.sticky_lines", { count: lines.length })}</p>
          <p className="muted">{t("admin.quote_new.sticky_planning_activities", { count: planningBlocks.length })}</p>
          <p className="muted">{t("admin.quote_new.sticky_estimated_sessions", { count: sessionsCount })}</p>
          {selectedSolfegeSlot ? <p className="muted">{t("admin.quote_new.sticky_solfege_slot")}: <strong>{selectedSolfegeSlot.label}</strong></p> : null}
          <p className="quote-total">{t("admin.quote_new.sticky_total")}: {toMoney(String(total), currency, uiLanguage)}</p>
        </article>
      </aside>
    </form>
  );
}
