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
};

type QuoteWizardFormProps = {
  returnTo: string;
  prospects: ProspectOption[];
  clients: ClientOption[];
  quoteTypes: QuoteTypeOption[];
  catalogs: CatalogOption[];
  paymentPlans: PaymentPlanOption[];
  cgvVersions: CgvOption[];
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

function toMoney(value: string): string {
  const n = Number(value);
  if (!Number.isFinite(n)) {
    return "0,00 EUR";
  }
  try {
    return new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(n);
  } catch {
    return `${n.toFixed(2)} EUR`;
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

export default function QuoteWizardForm({
  returnTo,
  prospects,
  clients,
  quoteTypes,
  catalogs,
  paymentPlans,
  cgvVersions,
  locations,
  activities,
  products,
  kits,
  solfegeRules,
  defaultProspectId,
  createAction,
}: QuoteWizardFormProps): JSX.Element {
  const [contextType, setContextType] = useState<"acquisition" | "active_client">("acquisition");
  const [selectedProspectId, setSelectedProspectId] = useState<string>(defaultProspectId || "");
  const [selectedClientId, setSelectedClientId] = useState<string>("");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [weekdays, setWeekdays] = useState<number[]>([0]);
  const [startTime, setStartTime] = useState<string>("17:00");
  const [endTime, setEndTime] = useState<string>("18:00");
  const [estimatedLevel, setEstimatedLevel] = useState<string>("");
  const [lines, setLines] = useState<WizardLine[]>([]);

  const sessionsCount = useMemo(() => countEstimatedSessions(startDate, endDate, weekdays), [startDate, endDate, weekdays]);

  const total = useMemo(() => lines.reduce((sum, line) => sum + lineAmount(line), 0), [lines]);

  const selectedSolfegeRule = useMemo(
    () => solfegeRules.find((rule) => String(rule.level_code) === String(estimatedLevel)),
    [solfegeRules, estimatedLevel],
  );

  const linesJson = useMemo(
    () => JSON.stringify(lines.map((line, index) => buildLinePayload(line, index))),
    [lines],
  );

  function toggleWeekday(value: number): void {
    setWeekdays((prev) => (prev.includes(value) ? prev.filter((day) => day !== value) : [...prev, value].sort((a, b) => a - b)));
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
              Delai expiration (jours)
              <input type="number" name="expiry_days" min={1} max={120} defaultValue={10} required />
            </label>
          </div>
        </article>

        <article className="card quote-wizard-card">
          <h3>3. Planning piano</h3>
          <div className="grid cols-2 top-gap-sm">
            <label>
              Lieu
              <select name="location_id" defaultValue={locations[0]?.id ?? ""}>
                <option value="">Aucun</option>
                {locations.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Activite planning
              <select name="calendar_activity_id" defaultValue={activities[0]?.id ?? ""}>
                <option value="">Aucune</option>
                {activities.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Date debut
              <input type="date" name="calendar_start_date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
            </label>
            <label>
              Date fin
              <input type="date" name="calendar_end_date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
            </label>
            <label>
              Heure debut
              <input type="time" name="calendar_start_time" value={startTime} onChange={(event) => setStartTime(event.target.value)} />
            </label>
            <label>
              Heure fin
              <input type="time" name="calendar_end_time" value={endTime} onChange={(event) => setEndTime(event.target.value)} />
            </label>
          </div>
          <div className="row wrap gap-sm top-gap-sm">
            {WEEKDAY_LABELS.map((entry) => (
              <label key={entry.value} className="row gap-xs quote-weekday-chip">
                <input
                  type="checkbox"
                  name="calendar_weekdays"
                  value={String(entry.value)}
                  checked={weekdays.includes(entry.value)}
                  onChange={() => toggleWeekday(entry.value)}
                />
                {entry.label}
              </label>
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
              <p className="muted">Creneaux configures: {selectedSolfegeRule.allowed_time_slots.length}</p>
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
                    <input type="number" step="0.01" value={line.unitPrice} onChange={(event) => updateLine(line.uid, { unitPrice: event.target.value })} required />
                  </label>
                  <div className="quote-line-amount">
                    <span>Montant</span>
                    <strong>{toMoney(String(lineAmount(line)))}</strong>
                  </div>
                </div>
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
          <p className="muted">Lignes: <strong>{lines.length}</strong></p>
          <p className="muted">Seances estimees: <strong>{sessionsCount}</strong></p>
          <p className="quote-total">Total estime: {toMoney(String(total))}</p>
        </article>
      </aside>
    </form>
  );
}
