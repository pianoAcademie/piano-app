"use client";

import { useMemo, useState } from "react";

type ActivityOption = {
  id: string;
  name: string;
  duration_minutes: number;
  default_hourly_rate: string | null;
  default_course_rate_ttc: string | null;
};

type ProductOption = {
  id: string;
  title: string;
  price_incl_vat: string;
  vat_rate: string;
};

type KitOption = {
  id: string;
  title: string;
  effective_price_ttc: string;
  vat_rate: string;
};

type InitialQuoteLine = {
  id: string;
  line_type: string;
  line_category: string;
  master_item_type: string | null;
  activity_id: string | null;
  product_id: string | null;
  kit_id: string | null;
  title: string;
  quantity: string;
  vat_rate: string;
  unit_price_ttc: string;
};

type LineKind = "activity" | "product" | "kit" | "discount" | "surcharge";

type EditableLine = {
  uid: string;
  kind: LineKind;
  refId: string;
  title: string;
  quantity: string;
  vatRate: string;
  unitPrice: string;
  saved: boolean;
  dirty: boolean;
};

type QuoteLinesEditorProps = {
  quoteId: string;
  returnTo: string;
  editable: boolean;
  currency: string;
  initialLines: InitialQuoteLine[];
  activities: ActivityOption[];
  products: ProductOption[];
  kits: KitOption[];
  activityCatalogPriceByActivityId?: Record<string, string>;
  productCatalogPriceByProductId?: Record<string, string>;
  kitCatalogPriceByKitId?: Record<string, string>;
  planningByActivityId?: Record<string, { plannedQuantity: number; pendingSelection: boolean }>;
  defaultVatRate?: string;
  saveAction: (formData: FormData) => Promise<void>;
};

function lineAmount(line: EditableLine): number {
  const qty = Number(line.quantity);
  const price = Number(line.unitPrice);
  if (!Number.isFinite(qty) || !Number.isFinite(price)) {
    return 0;
  }
  return qty * price;
}

function lineVatRate(line: EditableLine): number {
  const value = Number(line.vatRate);
  if (!Number.isFinite(value) || value < 0) {
    return 0;
  }
  return value;
}

function lineUnitHt(line: EditableLine): number {
  const ttc = Number(line.unitPrice);
  const rate = lineVatRate(line);
  if (!Number.isFinite(ttc)) {
    return 0;
  }
  if (rate <= 0) {
    return ttc;
  }
  return ttc / (1 + rate / 100);
}

function lineUnitVat(line: EditableLine): number {
  return Number(line.unitPrice) - lineUnitHt(line);
}

function lineAmountHt(line: EditableLine): number {
  return lineUnitHt(line) * Number(line.quantity || "0");
}

function lineAmountVat(line: EditableLine): number {
  return lineUnitVat(line) * Number(line.quantity || "0");
}

function toMoney(value: number, currency = "EUR"): string {
  if (!Number.isFinite(value)) {
    return `0,00 ${(currency || "EUR").toUpperCase()}`;
  }
  try {
    return new Intl.NumberFormat("fr-FR", { style: "currency", currency: (currency || "EUR").toUpperCase() }).format(value);
  } catch {
    return `${value.toFixed(2)} ${(currency || "EUR").toUpperCase()}`;
  }
}

function formatPercentDisplay(value: string | null | undefined): string {
  const parsed = Number(String(value ?? "").trim());
  if (!Number.isFinite(parsed)) {
    return "0,00%";
  }
  return `${new Intl.NumberFormat("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(parsed)}%`;
}

function formatQuantityDisplay(value: string | null | undefined): string {
  return normalizeQuantityInput(value);
}

function normalizeQuantityInput(value: string | null | undefined): string {
  const parsed = Number(String(value ?? "").trim());
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return "1";
  }
  return String(Math.max(1, Math.round(parsed)));
}

function normalizePercentInput(value: string | null | undefined): string {
  const parsed = Number(String(value ?? "").trim());
  if (!Number.isFinite(parsed) || parsed < 0) {
    return "0.00";
  }
  return parsed.toFixed(2);
}

function buildLinePayload(line: EditableLine, index: number): Record<string, unknown> {
  if (line.kind === "discount") {
    return {
      line_category: "product",
      line_type: "discount",
      master_item_type: "discount_rule",
      title: line.title || "Remise",
      quantity: normalizeQuantityInput(line.quantity),
      vat_rate: line.vatRate || "0",
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
      quantity: normalizeQuantityInput(line.quantity),
      vat_rate: line.vatRate || "0",
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
      quantity: normalizeQuantityInput(line.quantity),
      vat_rate: line.vatRate || "0",
      unit_price_ttc: line.unitPrice || "0",
      sort_order: index,
    };
  }
  if (line.kind === "kit") {
    return {
      line_category: "product",
      line_type: "item",
      master_item_type: "kit",
      kit_id: line.refId || null,
      title: line.title || "Kit",
      quantity: normalizeQuantityInput(line.quantity),
      vat_rate: line.vatRate || "0",
      unit_price_ttc: line.unitPrice || "0",
      sort_order: index,
    };
  }
  return {
    line_category: "product",
    line_type: "item",
    master_item_type: "product",
    product_id: line.refId || null,
    title: line.title || "Produit",
    quantity: normalizeQuantityInput(line.quantity),
    vat_rate: line.vatRate || "0",
    unit_price_ttc: line.unitPrice || "0",
    sort_order: index,
  };
}

function inferKind(row: InitialQuoteLine): LineKind {
  const lineType = row.line_type.trim().toLowerCase();
  if (lineType === "discount") {
    return "discount";
  }
  if (lineType === "surcharge") {
    return "surcharge";
  }
  if (row.activity_id) {
    return "activity";
  }
  if (row.kit_id) {
    return "kit";
  }
  return "product";
}

function inferRefId(row: InitialQuoteLine): string {
  if (row.activity_id) {
    return row.activity_id;
  }
  if (row.product_id) {
    return row.product_id;
  }
  if (row.kit_id) {
    return row.kit_id;
  }
  return "";
}

function selectableOptions(kind: LineKind, activities: ActivityOption[], products: ProductOption[], kits: KitOption[]): Array<{ id: string; label: string }> {
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

function isCatalogKind(kind: LineKind): boolean {
  return kind === "activity" || kind === "product" || kind === "kit";
}

function selectedOptionLabel(
  kind: LineKind,
  refId: string,
  activities: ActivityOption[],
  products: ProductOption[],
  kits: KitOption[],
): string | null {
  if (!refId) {
    return null;
  }
  if (kind === "activity") {
    return activities.find((item) => item.id === refId)?.name ?? null;
  }
  if (kind === "product") {
    return products.find((item) => item.id === refId)?.title ?? null;
  }
  if (kind === "kit") {
    return kits.find((item) => item.id === refId)?.title ?? null;
  }
  return null;
}

function parsePositive(value: string | null | undefined): number | null {
  const parsed = Number(String(value ?? "").trim());
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

function computeActivityFallbackPrice(activity: ActivityOption | undefined): string | null {
  if (!activity) {
    return null;
  }
  const direct = parsePositive(activity.default_course_rate_ttc);
  if (direct !== null) {
    return direct.toFixed(2);
  }
  const hourly = parsePositive(activity.default_hourly_rate);
  const duration = Number(activity.duration_minutes || 0);
  if (hourly !== null && Number.isFinite(duration) && duration > 0) {
    return (hourly * (duration / 60)).toFixed(2);
  }
  return null;
}

function planningSummaryForLine(
  line: EditableLine,
  planningByActivityId: Record<string, { plannedQuantity: number; pendingSelection: boolean }>,
): { plannedQuantity: number; pendingSelection: boolean } | null {
  if (line.kind !== "activity") {
    return null;
  }
  const activityId = String(line.refId || "").trim();
  if (!activityId) {
    return { plannedQuantity: 0, pendingSelection: false };
  }
  const summary = planningByActivityId[activityId];
  if (!summary) {
    return { plannedQuantity: 0, pendingSelection: false };
  }
  const plannedQuantity = Number.isFinite(summary.plannedQuantity) ? Math.max(0, summary.plannedQuantity) : 0;
  return {
    plannedQuantity,
    pendingSelection: summary.pendingSelection === true,
  };
}

function formatPlannedQuantityDisplay(
  summary: { plannedQuantity: number; pendingSelection: boolean } | null,
): string {
  if (!summary) {
    return "-";
  }
  if (summary.pendingSelection && summary.plannedQuantity <= 0) {
    return "0 (a confirmer)";
  }
  return String(summary.plannedQuantity);
}

function hasPlanningMismatch(
  line: EditableLine,
  summary: { plannedQuantity: number; pendingSelection: boolean } | null,
): boolean {
  if (!summary) {
    return false;
  }
  const billedQuantity = Number(String(line.quantity || "").trim());
  if (!Number.isFinite(billedQuantity)) {
    return summary.plannedQuantity > 0 || summary.pendingSelection;
  }
  return Math.round(billedQuantity) !== summary.plannedQuantity || summary.pendingSelection;
}

export default function QuoteLinesEditor({
  quoteId,
  returnTo,
  editable,
  currency,
  initialLines,
  activities,
  products,
  kits,
  activityCatalogPriceByActivityId = {},
  productCatalogPriceByProductId = {},
  kitCatalogPriceByKitId = {},
  planningByActivityId = {},
  defaultVatRate = "0",
  saveAction,
}: QuoteLinesEditorProps): JSX.Element {
  const [lines, setLines] = useState<EditableLine[]>(
    initialLines.map((row) => ({
      uid: row.id,
      kind: inferKind(row),
      refId: inferRefId(row),
      title: row.title || "",
      quantity: normalizeQuantityInput(row.quantity),
      vatRate: normalizePercentInput(row.vat_rate),
      unitPrice: row.unit_price_ttc || "0",
      saved: true,
      dirty: false,
    })),
  );
  const [activeUid, setActiveUid] = useState<string | null>(initialLines[0]?.id ?? null);

  const linesJson = useMemo(() => JSON.stringify(lines.map((line, index) => buildLinePayload(line, index))), [lines]);
  const total = useMemo(() => lines.reduce((sum, line) => sum + lineAmount(line), 0), [lines]);
  const totalHt = useMemo(() => lines.reduce((sum, line) => sum + lineAmountHt(line), 0), [lines]);
  const totalVat = useMemo(() => lines.reduce((sum, line) => sum + lineAmountVat(line), 0), [lines]);
  const savedCount = lines.filter((line) => line.saved && !line.dirty).length;
  const modifiedCount = lines.filter((line) => line.saved && line.dirty).length;
  const newCount = lines.filter((line) => !line.saved).length;
  const pendingSaveCount = lines.filter((line) => !line.saved || line.dirty).length;

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
        vatRate: "0",
        unitPrice: "0",
        saved: false,
        dirty: true,
      },
    ]);
    setActiveUid(uid);
  }

  function removeLine(uid: string): void {
    setLines((prev) => {
      const next = prev.filter((line) => line.uid !== uid);
      if (activeUid === uid) {
        setActiveUid(next[0]?.uid ?? null);
      }
      return next;
    });
  }

  function updateLine(uid: string, patch: Partial<EditableLine>): void {
    setLines((prev) =>
      prev.map((line) => {
        if (line.uid !== uid) {
          return line;
        }
        const next = { ...line, ...patch };
        const changed = Object.entries(patch).some(([key, value]) => {
          const current = line[key as keyof EditableLine];
          return String(current ?? "") !== String(value ?? "");
        });
        if (!changed) {
          return line;
        }
        return {
          ...next,
          dirty: line.saved ? true : next.dirty,
        };
      }),
    );
  }

  function applyRefToLine(uid: string, kind: LineKind, refId: string): void {
    if (!refId) {
      updateLine(uid, { refId: "", title: "", unitPrice: "0" });
      return;
    }
    setLines((prev) =>
      prev.map((line) => {
        if (line.uid !== uid) {
          return line;
        }
        if (kind === "activity") {
          const activity = activities.find((item) => item.id === refId);
          const catalogPrice = activityCatalogPriceByActivityId[refId];
          const fallbackPrice = computeActivityFallbackPrice(activity);
          const resolvedUnitPrice = catalogPrice ?? fallbackPrice ?? line.unitPrice;
          const currentVat = Number(line.vatRate || "0");
          const shouldPrefillVat = !Number.isFinite(currentVat) || currentVat <= 0;
          return {
            ...line,
            refId,
            title: activity?.name ?? "Activite",
            vatRate: shouldPrefillVat ? (defaultVatRate || "0") : line.vatRate,
            unitPrice: resolvedUnitPrice && resolvedUnitPrice !== "" ? resolvedUnitPrice : "0",
            dirty: line.saved ? true : line.dirty,
          };
        }
        if (kind === "product") {
          const product = products.find((item) => item.id === refId);
          const catalogPrice = productCatalogPriceByProductId[refId];
          const resolvedVatRate = product?.vat_rate ?? line.vatRate;
          const resolvedUnitPrice = catalogPrice ?? product?.price_incl_vat ?? line.unitPrice;
          return {
            ...line,
            refId,
            title: product?.title ?? "Produit",
            vatRate: resolvedVatRate && resolvedVatRate !== "" ? resolvedVatRate : "0",
            unitPrice: resolvedUnitPrice && resolvedUnitPrice !== "" ? resolvedUnitPrice : "0",
            dirty: line.saved ? true : line.dirty,
          };
        }
        const kit = kits.find((item) => item.id === refId);
        const catalogPrice = kitCatalogPriceByKitId[refId];
        const resolvedVatRate = kit?.vat_rate ?? line.vatRate;
        const resolvedUnitPrice = catalogPrice ?? kit?.effective_price_ttc ?? line.unitPrice;
        return {
          ...line,
          refId,
          title: kit?.title ?? "Kit",
          vatRate: resolvedVatRate && resolvedVatRate !== "" ? resolvedVatRate : "0",
          unitPrice: resolvedUnitPrice && resolvedUnitPrice !== "" ? resolvedUnitPrice : "0",
          dirty: line.saved ? true : line.dirty,
        };
      }),
    );
  }

  function lineStatusLabel(line: EditableLine): string {
    if (!line.saved) {
      return "Nouveau non enregistre";
    }
    if (line.dirty) {
      return "Modification en cours";
    }
    return "Enregistre";
  }

  function lineStatusClass(line: EditableLine): string {
    if (!line.saved) return "quote-status-chip-new";
    if (line.dirty) return "quote-status-chip-editing";
    return "quote-status-chip-saved";
  }

  function lineTypeLabel(kind: LineKind): string {
    if (kind === "activity") return "Activite";
    if (kind === "product") return "Produit";
    if (kind === "kit") return "Kit";
    if (kind === "discount") return "Remise";
    return "Supplement";
  }

  const activeLine = lines.find((line) => line.uid === activeUid) ?? null;
  const activeLineSelectedLabel = activeLine
    ? selectedOptionLabel(activeLine.kind, activeLine.refId, activities, products, kits)
    : null;
  const activeLinePlanningSummary = activeLine
    ? planningSummaryForLine(activeLine, planningByActivityId)
    : null;
  const activeLinePlanningMismatch = activeLine
    ? hasPlanningMismatch(activeLine, activeLinePlanningSummary)
    : false;

  return (
    <form action={saveAction}>
      <input type="hidden" name="quote_id" value={quoteId} />
      <input type="hidden" name="return_to" value={returnTo} />
      <input type="hidden" name="lines_json" value={linesJson} />

      <div className="quote-editor-toolbar row spread wrap gap-sm">
        <div className="row wrap gap-sm">
          <button type="button" className="ghost" onClick={() => addLine("activity")} disabled={!editable}>+ Activite</button>
          <button type="button" className="ghost" onClick={() => addLine("product")} disabled={!editable}>+ Produit</button>
          <button type="button" className="ghost" onClick={() => addLine("kit")} disabled={!editable}>+ Kit</button>
          <button type="button" className="ghost" onClick={() => addLine("discount")} disabled={!editable}>+ Remise</button>
          <button type="button" className="ghost" onClick={() => addLine("surcharge")} disabled={!editable}>+ Supplement</button>
        </div>
        <div className="row wrap gap-sm">
          <span className="quote-editor-count">Lignes facturees — {savedCount} enregistree(s), {modifiedCount + newCount} brouillon(s)</span>
          <span className={`quote-status-chip ${pendingSaveCount > 0 ? "quote-status-chip-pending" : "quote-status-chip-saved"}`}>
            {pendingSaveCount > 0 ? "A enregistrer" : "Enregistre"}
          </span>
        </div>
      </div>

      <div className="quote-editor-split quote-editor-split-pricing top-gap-sm">
        <section className="quote-editor-pane quote-editor-pane-saved">
          <h4>Lignes enregistrees</h4>
          {lines.length === 0 ? (
            <p className="quote-editor-empty">Aucune ligne enregistree pour ce devis.</p>
          ) : (
            <div className="quote-saved-table-wrap top-gap-sm">
              <table className="quote-saved-table">
                <thead>
                  <tr>
                    <th className="quote-col-type">Type</th>
                    <th className="quote-col-title">Intitule</th>
                    <th className="quote-col-qty">Qt facturee</th>
                    <th className="quote-col-qty-planned">Qt planifiee</th>
                    <th className="quote-col-vat">TVA</th>
                    <th className="quote-col-price">Prix TTC</th>
                    <th className="quote-col-total">Total TTC</th>
                    <th className="quote-col-status">Statut</th>
                    <th className="quote-col-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line) => {
                    const planningSummary = planningSummaryForLine(line, planningByActivityId);
                    const planningMismatch = hasPlanningMismatch(line, planningSummary);
                    return (
                      <tr key={line.uid} className={activeUid === line.uid ? "active" : ""}>
                        <td className="quote-col-type">{lineTypeLabel(line.kind)}</td>
                        <td className="quote-col-title-cell">
                          <span className="quote-line-title-text" title={line.title || "-"}>
                            {line.title || "-"}
                          </span>
                        </td>
                        <td className="quote-col-qty">{formatQuantityDisplay(line.quantity)}</td>
                        <td className={`quote-col-qty-planned${planningMismatch ? " quote-col-qty-mismatch" : ""}`}>
                          {formatPlannedQuantityDisplay(planningSummary)}
                        </td>
                        <td className="quote-col-vat">{formatPercentDisplay(line.vatRate)}</td>
                        <td className="quote-col-price">{toMoney(Number(line.unitPrice || "0"), currency)}</td>
                        <td className="quote-col-total">{toMoney(lineAmount(line), currency)}</td>
                        <td className="quote-col-status">
                          <span className={`quote-status-chip ${lineStatusClass(line)}`}>{lineStatusLabel(line)}</span>
                        </td>
                        <td className="quote-col-actions">
                          <div className="row wrap gap-xs">
                            <button type="button" className="ghost small-btn" onClick={() => setActiveUid(line.uid)}>
                              Modifier
                            </button>
                            <button type="button" className="ghost small-btn" onClick={() => removeLine(line.uid)} disabled={!editable}>
                              Supprimer
                            </button>
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

        <section className="quote-editor-pane quote-editor-pane-draft">
          <h4>Ajout / modification en cours</h4>
          {!activeLine ? (
            <div className="quote-editor-empty top-gap-sm">
              Selectionnez une ligne enregistree (gauche) ou cliquez sur un bouton “+”.
            </div>
          ) : (
            <>
              <div className={`quote-draft-banner top-gap-sm ${activeLine.saved ? "editing" : "new"}`}>
                {activeLine.saved ? "Modification en cours non enregistree" : "Nouvelle ligne non enregistree"}
              </div>
              <article className="quote-line-card top-gap-sm">
                <div className="row spread wrap gap-sm">
                  <strong>{lineTypeLabel(activeLine.kind)}</strong>
                  <button type="button" className="ghost small-btn" onClick={() => removeLine(activeLine.uid)} disabled={!editable}>
                    Supprimer
                  </button>
                </div>
                {(activeLine.kind === "activity" || activeLine.kind === "product" || activeLine.kind === "kit") ? (
                  <>
                    <label className="top-gap-sm">
                      Element
                      <select
                        value={activeLine.refId}
                        onChange={(event) => applyRefToLine(activeLine.uid, activeLine.kind, event.target.value)}
                        disabled={!editable}
                      >
                        <option value="">Selectionner</option>
                        {selectableOptions(activeLine.kind, activities, products, kits).map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    {activeLineSelectedLabel ? (
                      <small className="muted quote-selected-item-label" title={activeLineSelectedLabel}>
                        {activeLineSelectedLabel}
                      </small>
                    ) : null}
                  </>
                ) : null}
                <div className="grid cols-4 top-gap-sm">
                  <label className="cols-span-4">
                    Intitule
                    <input
                      type="text"
                      value={activeLine.title}
                      onChange={(event) => updateLine(activeLine.uid, { title: event.target.value })}
                      title={activeLine.title || ""}
                      required
                      disabled={!editable}
                    />
                  </label>
                  <label>
                    Quantite
                    <input
                      type="number"
                      min={1}
                      step={1}
                      value={activeLine.quantity}
                      onChange={(event) => updateLine(activeLine.uid, { quantity: normalizeQuantityInput(event.target.value) })}
                      required
                      disabled={!editable}
                    />
                  </label>
                  {activeLine.kind === "activity" ? (
                    <div className={`quote-line-planning-summary cols-span-4${activeLinePlanningMismatch ? " is-warning" : ""}`}>
                      <span>Quantite facturee : {formatQuantityDisplay(activeLine.quantity)}</span>
                      <span>Quantite planifiee : {formatPlannedQuantityDisplay(activeLinePlanningSummary)}</span>
                    </div>
                  ) : null}
                  <label>
                    TVA (%)
                    <input
                      type="number"
                      min={0}
                      max={100}
                      step="0.01"
                      value={activeLine.vatRate}
                      onChange={(event) => updateLine(activeLine.uid, { vatRate: event.target.value })}
                      required
                      disabled={!editable}
                    />
                  </label>
                  <label className="quote-price-field">
                    Prix TTC
                    <input
                      type="number"
                      step="0.01"
                      value={activeLine.unitPrice}
                      onChange={(event) => updateLine(activeLine.uid, { unitPrice: event.target.value })}
                      required
                      disabled={!editable}
                    />
                  </label>
                  <div className="quote-line-amounts-row">
                    <div className="quote-line-amount">
                      <span>Montant TTC</span>
                      <strong>{toMoney(lineAmount(activeLine), currency)}</strong>
                    </div>
                    <div className="quote-line-amount">
                      <span>Montant HT</span>
                      <strong>{toMoney(lineAmountHt(activeLine), currency)}</strong>
                    </div>
                    <div className="quote-line-amount">
                      <span>Montant TVA</span>
                      <strong>{toMoney(lineAmountVat(activeLine), currency)}</strong>
                    </div>
                  </div>
                </div>
                {isCatalogKind(activeLine.kind) ? (
                  <small className="muted">
                    Prix pre-rempli depuis le devis, le catalogue ou la configuration source. Vous pouvez l ajuster si necessaire.
                  </small>
                ) : null}
              </article>
            </>
          )}
        </section>
      </div>

      <div className="row spread wrap top-gap-sm">
        <p className="quote-total">
          Total estime TTC: {toMoney(total, currency)} · HT: {toMoney(totalHt, currency)} · TVA: {toMoney(totalVat, currency)}
        </p>
        <button type="submit" disabled={!editable}>Enregistrer les lignes</button>
      </div>
      {!editable ? <p className="muted top-gap-sm">Le devis est immuable apres envoi.</p> : null}
    </form>
  );
}
