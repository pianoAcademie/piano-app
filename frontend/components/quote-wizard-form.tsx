"use client";

import { useMemo, useState } from "react";

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

type QuoteTypeOption = {
  id: string;
  name: string;
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

type CgvOption = {
  id: string;
  version_label: string;
};

type QuoteTemplateOption = {
  id: string;
  name: string;
  code: string;
  language: string;
  is_default: boolean;
};

type LocationOption = {
  id: string;
  name: string;
};

type ActivityOption = {
  id: string;
  name: string;
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

function normalizeLang(value: string | null | undefined): string {
  const normalized = String(value || "").trim().toLowerCase();
  return normalized || "fr";
}

type QuoteWizardFormProps = {
  returnTo: string;
  prospects: ProspectOption[];
  clients: ClientOption[];
  quoteTypes: QuoteTypeOption[];
  catalogs: CatalogOption[];
  paymentPlans: PaymentPlanOption[];
  cgvVersions: CgvOption[];
  quoteTemplates: QuoteTemplateOption[];
  locations: LocationOption[];
  activities: ActivityOption[];
  products: ProductOption[];
  kits: KitOption[];
  solfegeRules: SolfegeRule[];
  defaultProspectId: string;
  createAction: (formData: FormData) => Promise<void>;
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

const WEEKDAY_LABELS: Array<{ value: number; label: string }> = [
  { value: 0, label: "Lun" },
  { value: 1, label: "Mar" },
  { value: 2, label: "Mer" },
  { value: 3, label: "Jeu" },
  { value: 4, label: "Ven" },
  { value: 5, label: "Sam" },
  { value: 6, label: "Dim" },
];

function toMoney(value: string, currency = "EUR"): string {
  const n = Number(value);
  if (!Number.isFinite(n)) {
    return `0,00 ${(currency || "EUR").toUpperCase()}`;
  }
  try {
    return new Intl.NumberFormat("fr-FR", { style: "currency", currency: (currency || "EUR").toUpperCase() }).format(n);
  } catch {
    return `${n.toFixed(2)} ${(currency || "EUR").toUpperCase()}`;
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

function buildLinePayload(line: WizardLine, index: number): Record<string, unknown> {
  if (line.kind === "discount") {
    return {
      line_category: "product",
      line_type: "discount",
      master_item_type: "discount_rule",
      title: line.title || "Remise",
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
      title: line.title || "Supplement",
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
      title: line.title || "Activite",
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
      title: line.title || "Produit",
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
    title: line.title || "Kit",
    quantity: line.quantity || "1",
    unit_price_ttc: line.unitPrice || "0",
    sort_order: index,
  };
}

function countEstimatedSessions(startDate: string, endDate: string, weekdays: number[]): number {
  if (!startDate || !endDate || weekdays.length === 0) {
    return 0;
  }
  const start = new Date(`${startDate}T00:00:00Z`);
  const end = new Date(`${endDate}T00:00:00Z`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) {
    return 0;
  }
  const set = new Set(weekdays);
  let count = 0;
  for (let d = new Date(start.getTime()); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
    const jsDay = d.getUTCDay();
    const mapped = (jsDay + 6) % 7;
    if (set.has(mapped)) {
      count += 1;
    }
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

function weekdayLabel(weekday: number): string {
  const row = WEEKDAY_LABELS.find((item) => item.value === weekday);
  return row?.label ?? String(weekday);
}

function timeSlotParts(slot: Record<string, unknown>): { start: string; end: string } | null {
  const start = typeof slot.start_time === "string" ? slot.start_time : typeof slot.start === "string" ? slot.start : "";
  const end = typeof slot.end_time === "string" ? slot.end_time : typeof slot.end === "string" ? slot.end : "";
  if (!start || !end) {
    return null;
  }
  return { start, end };
}

function isCatalogKind(kind: LineKind): boolean {
  return kind === "activity" || kind === "product" || kind === "kit";
}

export default function QuoteWizardForm({
  returnTo,
  prospects,
  clients,
  quoteTypes,
  catalogs,
  paymentPlans,
  cgvVersions,
  quoteTemplates,
  locations,
  activities,
  products,
  kits,
  solfegeRules,
  defaultProspectId,
  createAction,
}: QuoteWizardFormProps): JSX.Element {
  const defaultTemplate = quoteTemplates.find((item) => item.is_default) ?? quoteTemplates[0] ?? null;
  const [contextType, setContextType] = useState<"acquisition" | "active_client">("acquisition");
  const [selectedProspectId, setSelectedProspectId] = useState<string>(defaultProspectId || "");
  const [selectedClientId, setSelectedClientId] = useState<string>("");
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>(defaultTemplate?.id ?? "");
  const [language, setLanguage] = useState<string>(normalizeLang(defaultTemplate?.language));
  const [currency, setCurrency] = useState<string>("EUR");
  const [tvaRate, setTvaRate] = useState<string>("20");
  const [estimatedLevel, setEstimatedLevel] = useState<string>("");
  const [selectedSolfegeSlotKey, setSelectedSolfegeSlotKey] = useState<string>("");
  const [lines, setLines] = useState<WizardLine[]>([]);
  const [planningBlocks, setPlanningBlocks] = useState<PlanningBlock[]>([]);

  const sessionsCount = useMemo(
    () => planningBlocks.reduce((sum, block) => {
      const blockCount = countEstimatedSessions(block.start_date, block.end_date, [block.weekday]);
      return sum + blockCount;
    }, 0),
    [planningBlocks],
  );

  const total = useMemo(() => lines.reduce((sum, line) => sum + lineAmount(line), 0), [lines]);

  const selectedSolfegeRule = useMemo(
    () => solfegeRules.find((rule) => String(rule.level_code) === String(estimatedLevel)),
    [solfegeRules, estimatedLevel],
  );

  const solfegeSlotOptions = useMemo<SolfegeSlotOption[]>(() => {
    if (!selectedSolfegeRule) {
      return [];
    }
    const weekdays = selectedSolfegeRule.allowed_weekdays.length > 0
      ? selectedSolfegeRule.allowed_weekdays.filter((day) => Number.isFinite(day) && day >= 0 && day <= 6)
      : [0, 1, 2, 3, 4, 5, 6];

    const options: SolfegeSlotOption[] = [];
    for (const weekday of weekdays) {
      for (const slot of selectedSolfegeRule.allowed_time_slots) {
        const parts = timeSlotParts(slot);
        if (!parts) {
          continue;
        }
        const key = `${weekday}|${parts.start}|${parts.end}`;
        options.push({
          key,
          weekday,
          start_time: parts.start,
          end_time: parts.end,
          duration_minutes: selectedSolfegeRule.duration_minutes,
          location_id: selectedSolfegeRule.location_id,
          modality: selectedSolfegeRule.modality,
          label: `${weekdayLabel(weekday)} ${parts.start}-${parts.end}`,
        });
      }
    }
    return options;
  }, [selectedSolfegeRule]);

  const selectedSolfegeSlot = useMemo(
    () => solfegeSlotOptions.find((item) => item.key === selectedSolfegeSlotKey) ?? null,
    [solfegeSlotOptions, selectedSolfegeSlotKey],
  );
  const languageTemplates = useMemo(
    () => quoteTemplates.filter((item) => normalizeLang(item.language) === normalizeLang(language)),
    [quoteTemplates, language],
  );

  const planningBlocksJson = useMemo(
    () =>
      JSON.stringify(
        planningBlocks.map((row) => ({
          activity_id: row.activity_id || null,
          activity_label: activities.find((item) => item.id === row.activity_id)?.name || null,
          location_id: row.location_id || null,
          location_label: locations.find((item) => item.id === row.location_id)?.name || null,
          weekday: row.weekday,
          weekday_label: weekdayLabel(row.weekday),
          start_date: row.start_date,
          end_date: row.end_date,
          start_time: row.start_time,
          end_time: row.end_time,
          modality: row.modality || null,
        })),
      ),
    [planningBlocks],
  );

  const selectedSolfegeSlotJson = useMemo(
    () => (selectedSolfegeSlot ? JSON.stringify(selectedSolfegeSlot) : ""),
    [selectedSolfegeSlot],
  );

  const linesJson = useMemo(
    () => JSON.stringify(lines.map((line, index) => buildLinePayload(line, index))),
    [lines],
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
        title: activity?.name ?? "Activite",
        unitPrice: activity?.default_course_rate_ttc ?? "0",
      });
      return;
    }
    if (kind === "product") {
      const product = products.find((item) => item.id === refId);
      updateLine(uid, {
        refId,
        title: product?.title ?? "Produit",
        unitPrice: product?.price_incl_vat ?? "0",
      });
      return;
    }
    const kit = kits.find((item) => item.id === refId);
    updateLine(uid, {
      refId,
      title: kit?.title ?? "Kit",
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

  return (
    <form action={createAction} className="quote-wizard-layout">
      <input type="hidden" name="return_to" value={returnTo} />
      <input type="hidden" name="lines_json" value={linesJson} />
      <input type="hidden" name="planning_blocks_json" value={planningBlocksJson} />
      <input type="hidden" name="solfege_slot_json" value={selectedSolfegeSlotJson} />

      <section className="quote-wizard-main stack">
        <article className="card quote-wizard-card">
          <h3>1. Contexte</h3>
          <p className="muted">Acquisition prospect ou client actif.</p>
          <div className="row wrap gap-sm top-gap-sm">
            <label className="row gap-xs">
              <input
                type="radio"
                name="context_type"
                value="acquisition"
                checked={contextType === "acquisition"}
                onChange={() => setContextType("acquisition")}
              />
              Acquisition (prospect)
            </label>
            <label className="row gap-xs">
              <input
                type="radio"
                name="context_type"
                value="active_client"
                checked={contextType === "active_client"}
                onChange={() => setContextType("active_client")}
              />
              Client actif
            </label>
          </div>
          {contextType === "acquisition" ? (
            <label className="top-gap-sm">
              Prospect
              <select name="prospect_id" value={selectedProspectId} onChange={(event) => setSelectedProspectId(event.target.value)} required>
                <option value="">Selectionner un prospect</option>
                {prospects.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label} - {item.email}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <label className="top-gap-sm">
              Client
              <select name="client_id" value={selectedClientId} onChange={(event) => setSelectedClientId(event.target.value)} required>
                <option value="">Selectionner un client</option>
                {clients.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label} - {item.email}
                  </option>
                ))}
              </select>
            </label>
          )}
        </article>

        <article className="card quote-wizard-card">
          <h3>2. Parametres devis</h3>
          <div className="grid cols-2 top-gap-sm">
            <label>
              Type de devis
              <select name="quote_type_id" defaultValue={quoteTypes[0]?.id ?? ""}>
                <option value="">Par defaut</option>
                {quoteTypes.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Catalogue tarifaire
              <select name="pricing_catalog_id" defaultValue={catalogs[0]?.id ?? ""}>
                <option value="">Aucun</option>
                {catalogs.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Template devis
              <select name="quote_template_id" value={selectedTemplateId} onChange={(event) => {
                const nextId = event.target.value;
                setSelectedTemplateId(nextId);
                const template = quoteTemplates.find((item) => item.id === nextId);
                if (template?.language) {
                  setLanguage(template.language.toLowerCase());
                }
              }}>
              <option value="">Aucun</option>
                {languageTemplates.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} ({item.code})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Plan de paiement
              <select name="payment_plan_id" defaultValue={paymentPlans[0]?.id ?? ""}>
                <option value="">Aucun</option>
                {paymentPlans.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} ({item.payment_method})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Version CGV de reference
              <select name="cgv_version_id" defaultValue={cgvVersions[0]?.id ?? ""}>
                <option value="">Aucune</option>
                {cgvVersions.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.version_label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Annee scolaire
              <input type="text" name="school_year_label" placeholder="2026-2027" />
            </label>
            <label>
              Devise
              <select name="currency" value={currency} onChange={(event) => setCurrency(event.target.value)}>
                <option value="EUR">EUR</option>
                <option value="USD">USD</option>
                <option value="GBP">GBP</option>
              </select>
            </label>
            <label>
              Langue
              <select
                name="language"
                value={language}
                onChange={(event) => {
                  const nextLanguage = normalizeLang(event.target.value);
                  setLanguage(nextLanguage);
                  const currentTemplate = quoteTemplates.find((item) => item.id === selectedTemplateId);
                  if (currentTemplate && normalizeLang(currentTemplate.language) === nextLanguage) {
                    return;
                  }
                  const fallbackTemplate =
                    quoteTemplates.find((item) => item.is_default && normalizeLang(item.language) === nextLanguage) ??
                    quoteTemplates.find((item) => normalizeLang(item.language) === nextLanguage) ??
                    null;
                  setSelectedTemplateId(fallbackTemplate?.id ?? "");
                }}
              >
                <option value="fr">Francais</option>
                <option value="en">English</option>
              </select>
            </label>
            <label>
              TVA (%)
              <input
                type="number"
                name="tva_rate"
                min={0}
                max={100}
                step="0.01"
                value={tvaRate}
                onChange={(event) => setTvaRate(event.target.value)}
              />
            </label>
            <label>
              Delai expiration (jours)
              <input type="number" name="expiry_days" min={1} max={120} defaultValue={10} required />
            </label>
          </div>
        </article>

        <article className="card quote-wizard-card">
          <h3>3. Planning piano</h3>
          <p className="muted">
            Ajoutez une ou plusieurs activites. Pour chaque activite, l heure de fin est calculee automatiquement depuis la duree en base.
          </p>
          <div className="row wrap gap-sm top-gap-sm">
            <button type="button" className="ghost" onClick={addPlanningBlock}>+ Ajouter une activite planning</button>
          </div>
          {planningBlocks.length === 0 ? <p className="muted top-gap-sm">Aucun bloc planning configure.</p> : null}
          <div className="list top-gap-sm">
            {planningBlocks.map((block, index) => (
              <article key={block.uid} className="item">
                <div className="row spread wrap gap-sm">
                  <strong>Activite #{index + 1}</strong>
                  <button type="button" className="ghost small-btn" onClick={() => removePlanningBlock(block.uid)}>
                    Supprimer
                  </button>
                </div>
                <div className="grid cols-4 top-gap-sm">
                  <label>
                    Activite
                    <select
                      value={block.activity_id}
                      onChange={(event) => syncPlanningActivity(block.uid, event.target.value, block.start_time)}
                    >
                      <option value="">Selectionner</option>
                      {activities.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name} ({item.duration_minutes} min)
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Lieu
                    <select
                      value={block.location_id}
                      onChange={(event) => updatePlanningBlock(block.uid, { location_id: event.target.value })}
                    >
                      <option value="">Aucun</option>
                      {locations.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Jour
                    <select
                      value={String(block.weekday)}
                      onChange={(event) => updatePlanningBlock(block.uid, { weekday: Number.parseInt(event.target.value, 10) || 0 })}
                    >
                      {WEEKDAY_LABELS.map((entry) => (
                        <option key={entry.value} value={entry.value}>
                          {entry.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Modalite
                    <select
                      value={block.modality}
                      onChange={(event) => updatePlanningBlock(block.uid, { modality: event.target.value })}
                    >
                      <option value="">Auto</option>
                      <option value="ONLINE">En ligne</option>
                      <option value="ONSITE">Presentiel</option>
                    </select>
                  </label>
                  <label>
                    Date debut
                    <input type="date" value={block.start_date} onChange={(event) => updatePlanningBlock(block.uid, { start_date: event.target.value })} />
                  </label>
                  <label>
                    Date fin
                    <input type="date" value={block.end_date} onChange={(event) => updatePlanningBlock(block.uid, { end_date: event.target.value })} />
                  </label>
                  <label>
                    Heure debut
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
                    />
                  </label>
                  <label>
                    Heure fin (auto)
                    <input type="time" value={block.end_time} readOnly />
                  </label>
                </div>
              </article>
            ))}
          </div>
          <p className="muted top-gap-sm">Apercu rapide: {sessionsCount} seances estimees (hors jours feries/fermetures).</p>
        </article>

        <article className="card quote-wizard-card">
          <h3>4. Solfege (optionnel)</h3>
          <label className="top-gap-sm">
            Niveau estime
            <select name="estimated_solfege_level" value={estimatedLevel} onChange={(event) => setEstimatedLevel(event.target.value)}>
              <option value="">Non applicable</option>
              {["1", "2", "3", "4", "5"].map((level) => (
                <option key={level} value={level}>
                  Niveau {level}
                </option>
              ))}
            </select>
          </label>
          {selectedSolfegeRule ? (
            <div className="quote-solfege-preview top-gap-sm">
              <p>
                Duree suggeree: <strong>{selectedSolfegeRule.duration_minutes} min</strong>
              </p>
              <p className="muted">Jours autorises: {selectedSolfegeRule.allowed_weekdays.length > 0 ? selectedSolfegeRule.allowed_weekdays.join(", ") : "Tous"}</p>
              <p className="muted">Creneaux configures: {solfegeSlotOptions.length}</p>
              <label className="top-gap-sm">
                Creneau propose
                <select value={selectedSolfegeSlotKey} onChange={(event) => setSelectedSolfegeSlotKey(event.target.value)}>
                  <option value="">Selectionner un creneau</option>
                  {solfegeSlotOptions.map((slot) => (
                    <option key={slot.key} value={slot.key}>
                      {slot.label}
                    </option>
                  ))}
                </select>
              </label>
              {selectedSolfegeSlot ? (
                <p className="muted top-gap-sm">
                  Selection: <strong>{selectedSolfegeSlot.label}</strong>
                  {selectedSolfegeSlot.modality ? ` · ${selectedSolfegeSlot.modality}` : ""}
                </p>
              ) : null}
            </div>
          ) : (
            <p className="muted top-gap-sm">Selectionne un niveau pour afficher la regle active.</p>
          )}
        </article>

        <article className="card quote-wizard-card">
          <h3>5. Lignes devis (services / produits / kits / remises / supplements)</h3>
          <div className="row wrap gap-sm top-gap-sm">
            <button type="button" className="ghost" onClick={() => addLine("activity")}>+ Activite</button>
            <button type="button" className="ghost" onClick={() => addLine("product")}>+ Produit</button>
            <button type="button" className="ghost" onClick={() => addLine("kit")}>+ Kit</button>
            <button type="button" className="ghost" onClick={() => addLine("discount")}>+ Remise</button>
            <button type="button" className="ghost" onClick={() => addLine("surcharge")}>+ Supplement</button>
          </div>
          {lines.length === 0 ? <p className="muted top-gap-sm">Aucune ligne. Ajoute au moins une ligne tarifaire.</p> : null}
          <div className="quote-lines-list top-gap-sm">
            {lines.map((line) => (
              <article key={line.uid} className="quote-line-card">
                <div className="row spread wrap gap-sm">
                  <strong>{line.kind.toUpperCase()}</strong>
                  <button type="button" className="ghost small-btn" onClick={() => removeLine(line.uid)}>
                    Supprimer
                  </button>
                </div>
                {(line.kind === "activity" || line.kind === "product" || line.kind === "kit") ? (
                  <label className="top-gap-sm">
                    Element
                    <select
                      value={line.refId}
                      onChange={(event) => applyRefToLine(line.uid, line.kind, event.target.value)}
                    >
                      <option value="">Selectionner</option>
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
                    Intitule
                    <input type="text" value={line.title} onChange={(event) => updateLine(line.uid, { title: event.target.value })} required />
                  </label>
                  <label>
                    Quantite
                    <input type="number" min={0.01} step="0.01" value={line.quantity} onChange={(event) => updateLine(line.uid, { quantity: event.target.value })} required />
                  </label>
                  <label>
                    Prix TTC
                    <input
                      type="number"
                      step="0.01"
                      value={line.unitPrice}
                      onChange={(event) => updateLine(line.uid, { unitPrice: event.target.value })}
                      required
                      readOnly={isCatalogKind(line.kind)}
                    />
                  </label>
                  <div className="quote-line-amount">
                    <span>Montant</span>
                    <strong>{toMoney(String(lineAmount(line)), currency)}</strong>
                  </div>
                </div>
                {isCatalogKind(line.kind) ? (
                  <small className="muted">
                    Prix catalogue applique automatiquement depuis la base. Utilisez une remise ou un supplement pour ajuster.
                  </small>
                ) : null}
              </article>
            ))}
          </div>
        </article>

        <article className="card quote-wizard-card">
          <h3>6. Finalisation</h3>
          <p className="muted">Le devis est cree en brouillon. L envoi au prospect se fait ensuite depuis le panneau detail.</p>
          <div className="row wrap gap-sm top-gap-sm">
            <button type="submit">Creer le devis brouillon</button>
            <a className="ghost" href={returnTo}>Annuler</a>
          </div>
        </article>
      </section>

      <aside className="quote-wizard-sticky">
        <article className="card quote-summary-card">
          <h3>Resume sticky</h3>
          <p className="muted">Contexte: <strong>{contextType === "acquisition" ? "Acquisition" : "Client actif"}</strong></p>
          <p className="muted">Devise: <strong>{currency}</strong> · Langue: <strong>{language.toUpperCase()}</strong></p>
          <p className="muted">TVA: <strong>{tvaRate || "0"} %</strong></p>
          <p className="muted">Lignes: <strong>{lines.length}</strong></p>
          <p className="muted">Activites planning: <strong>{planningBlocks.length}</strong></p>
          <p className="muted">Seances estimees: <strong>{sessionsCount}</strong></p>
          {selectedSolfegeSlot ? <p className="muted">Creneau solfege: <strong>{selectedSolfegeSlot.label}</strong></p> : null}
          <p className="quote-total">Total estime: {toMoney(String(total), currency)}</p>
        </article>
      </aside>
    </form>
  );
}
