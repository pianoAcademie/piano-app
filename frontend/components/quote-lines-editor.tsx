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

function buildLinePayload(line: EditableLine, index: number): Record<string, unknown> {
  if (line.kind === "discount") {
    return {
      line_category: "product",
      line_type: "discount",
      master_item_type: "discount_rule",
      title: line.title || "Remise",
      quantity: line.quantity || "1",
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
      quantity: line.quantity || "1",
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
      quantity: line.quantity || "1",
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
      quantity: line.quantity || "1",
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
    quantity: line.quantity || "1",
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
  defaultVatRate = "0",
  saveAction,
}: QuoteLinesEditorProps): JSX.Element {
  const [lines, setLines] = useState<EditableLine[]>(
    initialLines.map((row) => ({
      uid: row.id,
      kind: inferKind(row),
      refId: inferRefId(row),
      title: row.title || "",
      quantity: row.quantity || "1",
      vatRate: row.vat_rate || "0",
      unitPrice: row.unit_price_ttc || "0",
    })),
  );

  const linesJson = useMemo(() => JSON.stringify(lines.map((line, index) => buildLinePayload(line, index))), [lines]);
  const total = useMemo(() => lines.reduce((sum, line) => sum + lineAmount(line), 0), [lines]);

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
      },
    ]);
  }

  function removeLine(uid: string): void {
    setLines((prev) => prev.filter((line) => line.uid !== uid));
  }

  function updateLine(uid: string, patch: Partial<EditableLine>): void {
    setLines((prev) => prev.map((line) => (line.uid === uid ? { ...line, ...patch } : line)));
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
        };
      }),
    );
  }

  return (
    <form action={saveAction}>
      <input type="hidden" name="quote_id" value={quoteId} />
      <input type="hidden" name="return_to" value={returnTo} />
      <input type="hidden" name="lines_json" value={linesJson} />

      <div className="row wrap gap-sm">
        <button type="button" className="ghost" onClick={() => addLine("activity")} disabled={!editable}>+ Activite</button>
        <button type="button" className="ghost" onClick={() => addLine("product")} disabled={!editable}>+ Produit</button>
        <button type="button" className="ghost" onClick={() => addLine("kit")} disabled={!editable}>+ Kit</button>
        <button type="button" className="ghost" onClick={() => addLine("discount")} disabled={!editable}>+ Remise</button>
        <button type="button" className="ghost" onClick={() => addLine("surcharge")} disabled={!editable}>+ Supplement</button>
      </div>

      {lines.length === 0 ? <p className="muted top-gap-sm">Aucune ligne.</p> : null}
      <div className="quote-lines-list top-gap-sm">
        {lines.map((line) => (
          <article key={line.uid} className="quote-line-card">
            <div className="row spread wrap gap-sm">
              <strong>{line.kind.toUpperCase()}</strong>
              <button type="button" className="ghost small-btn" onClick={() => removeLine(line.uid)} disabled={!editable}>
                Supprimer
              </button>
            </div>
            {(line.kind === "activity" || line.kind === "product" || line.kind === "kit") ? (
              <label className="top-gap-sm">
                Element
                <select
                  value={line.refId}
                  onChange={(event) => applyRefToLine(line.uid, line.kind, event.target.value)}
                  disabled={!editable}
                >
                  <option value="">Selectionner</option>
                  {selectableOptions(line.kind, activities, products, kits).map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <div className="grid cols-4 top-gap-sm">
              <label className="span-4">
                Intitule
                <input type="text" value={line.title} onChange={(event) => updateLine(line.uid, { title: event.target.value })} required disabled={!editable} />
              </label>
              <label>
                Quantite
                <input type="number" min={0.01} step="0.01" value={line.quantity} onChange={(event) => updateLine(line.uid, { quantity: event.target.value })} required disabled={!editable} />
              </label>
              <label>
                TVA (%)
                <input
                  type="number"
                  min={0}
                  max={100}
                  step="0.01"
                  value={line.vatRate}
                  onChange={(event) => updateLine(line.uid, { vatRate: event.target.value })}
                  required
                  disabled={!editable}
                />
              </label>
              <label>
                Prix TTC
                <input
                  type="number"
                  step="0.01"
                  value={line.unitPrice}
                  onChange={(event) => updateLine(line.uid, { unitPrice: event.target.value })}
                  required
                  disabled={!editable}
                />
              </label>
              <div className="quote-line-amount">
                <span>Montant TTC</span>
                <strong>{toMoney(lineAmount(line), currency)}</strong>
              </div>
              <div className="quote-line-amount">
                <span>Montant HT</span>
                <strong>{toMoney(lineAmountHt(line), currency)}</strong>
              </div>
              <div className="quote-line-amount">
                <span>Montant TVA</span>
                <strong>{toMoney(lineAmountVat(line), currency)}</strong>
              </div>
            </div>
            {isCatalogKind(line.kind) ? (
              <small className="muted">
                Prix pre-rempli depuis le catalogue/la base. Vous pouvez l ajuster si necessaire.
              </small>
            ) : null}
          </article>
        ))}
      </div>

      <div className="row spread wrap top-gap-sm">
        <p className="quote-total">
          Total estime TTC: {toMoney(total, currency)} · HT: {toMoney(lines.reduce((sum, line) => sum + lineAmountHt(line), 0), currency)} · TVA: {toMoney(lines.reduce((sum, line) => sum + lineAmountVat(line), 0), currency)}
        </p>
        <button type="submit" disabled={!editable}>Enregistrer les lignes</button>
      </div>
      {!editable ? <p className="muted top-gap-sm">Le devis est immuable apres envoi.</p> : null}
    </form>
  );
}
