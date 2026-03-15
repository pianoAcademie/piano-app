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

type EditorState = {
  originalUid: string | null;
  line: EditableLine;
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

type ResolvedUnitPrice = {
  unitPrice: string;
  sourceLabel: string;
};

function PencilIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M4 16.25V20h3.75L18.8 8.94l-3.75-3.75L4 16.25Zm2.92 2.33H6v-.92l9.8-9.79.92.92-9.8 9.79ZM20.7 7.04a1 1 0 0 0 0-1.42l-2.32-2.33a1.03 1.03 0 0 0-1.42 0l-1.31 1.3 3.75 3.75 1.3-1.3Z"
        fill="currentColor"
      />
    </svg>
  );
}

function TrashIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M9 3h6l1 2h4v2H4V5h4l1-2Zm1 6h2v8h-2V9Zm4 0h2v8h-2V9ZM7 9h2v8H7V9Zm-1 11a2 2 0 0 1-2-2V8h16v10a2 2 0 0 1-2 2H6Z"
        fill="currentColor"
      />
    </svg>
  );
}

function PlusIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6V5Z" fill="currentColor" />
    </svg>
  );
}

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

function resolvedSourceUnitPrice(
  line: EditableLine,
  activities: ActivityOption[],
  products: ProductOption[],
  kits: KitOption[],
  activityCatalogPriceByActivityId: Record<string, string>,
  productCatalogPriceByProductId: Record<string, string>,
  kitCatalogPriceByKitId: Record<string, string>,
): ResolvedUnitPrice | null {
  if (line.kind === "activity") {
    const activity = activities.find((item) => item.id === line.refId);
    const catalogPrice = activityCatalogPriceByActivityId[line.refId];
    if (catalogPrice && catalogPrice !== "") {
      return { unitPrice: catalogPrice, sourceLabel: "tarif catalogue" };
    }
    const direct = parsePositive(activity?.default_course_rate_ttc);
    if (direct !== null) {
      return { unitPrice: direct.toFixed(2), sourceLabel: "tarif par cours activite" };
    }
    const fallbackPrice = computeActivityFallbackPrice(activity);
    if (fallbackPrice && fallbackPrice !== "") {
      return { unitPrice: fallbackPrice, sourceLabel: "tarif horaire activite" };
    }
    return null;
  }
  if (line.kind === "product") {
    const product = products.find((item) => item.id === line.refId);
    const catalogPrice = productCatalogPriceByProductId[line.refId];
    if (catalogPrice && catalogPrice !== "") {
      return { unitPrice: catalogPrice, sourceLabel: "tarif catalogue" };
    }
    if (product?.price_incl_vat) {
      return { unitPrice: product.price_incl_vat, sourceLabel: "prix produit" };
    }
    return null;
  }
  if (line.kind === "kit") {
    const kit = kits.find((item) => item.id === line.refId);
    const catalogPrice = kitCatalogPriceByKitId[line.refId];
    if (catalogPrice && catalogPrice !== "") {
      return { unitPrice: catalogPrice, sourceLabel: "tarif catalogue" };
    }
    if (kit?.effective_price_ttc) {
      return { unitPrice: kit.effective_price_ttc, sourceLabel: "prix kit" };
    }
    return null;
  }
  return null;
}

function sameMoneyValue(left: string | null | undefined, right: string | null | undefined): boolean {
  const leftNumber = Number(String(left ?? "").trim());
  const rightNumber = Number(String(right ?? "").trim());
  if (!Number.isFinite(leftNumber) || !Number.isFinite(rightNumber)) {
    return false;
  }
  return Math.abs(leftNumber - rightNumber) < 0.005;
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

function editableLineChanged(current: EditableLine, next: EditableLine): boolean {
  return current.kind !== next.kind
    || String(current.refId) !== String(next.refId)
    || String(current.title) !== String(next.title)
    || String(current.quantity) !== String(next.quantity)
    || String(current.vatRate) !== String(next.vatRate)
    || String(current.unitPrice) !== String(next.unitPrice);
}

function newLine(kind: LineKind, defaultVatRate: string): EditableLine {
  return {
    uid: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    kind,
    refId: "",
    title: "",
    quantity: "1",
    vatRate: kind === "discount" || kind === "surcharge" ? "0.00" : normalizePercentInput(defaultVatRate),
    unitPrice: "0",
    saved: false,
    dirty: true,
  };
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
  const [editorState, setEditorState] = useState<EditorState | null>(null);

  const linesJson = useMemo(() => JSON.stringify(lines.map((line, index) => buildLinePayload(line, index))), [lines]);
  const total = useMemo(() => lines.reduce((sum, line) => sum + lineAmount(line), 0), [lines]);
  const totalHt = useMemo(() => lines.reduce((sum, line) => sum + lineAmountHt(line), 0), [lines]);
  const totalVat = useMemo(() => lines.reduce((sum, line) => sum + lineAmountVat(line), 0), [lines]);
  const savedCount = lines.filter((line) => line.saved && !line.dirty).length;
  const modifiedCount = lines.filter((line) => line.saved && line.dirty).length;
  const newCount = lines.filter((line) => !line.saved).length;
  const pendingSaveCount = lines.filter((line) => !line.saved || line.dirty).length;

  function openCreateModal(kind: LineKind): void {
    setEditorState({
      originalUid: null,
      line: newLine(kind, defaultVatRate),
    });
  }

  function openEditModal(uid: string): void {
    const current = lines.find((line) => line.uid === uid);
    if (!current) {
      return;
    }
    setEditorState({
      originalUid: uid,
      line: { ...current },
    });
  }

  function closeEditor(): void {
    setEditorState(null);
  }

  function removeLine(uid: string): void {
    setLines((prev) => prev.filter((line) => line.uid !== uid));
    setEditorState((prev) => (prev?.originalUid === uid ? null : prev));
  }

  function updateEditor(patch: Partial<EditableLine>): void {
    setEditorState((prev) => {
      if (!prev) {
        return prev;
      }
      return {
        ...prev,
        line: { ...prev.line, ...patch },
      };
    });
  }

  function applyRefToEditor(kind: LineKind, refId: string): void {
    if (!editorState) {
      return;
    }
    if (!refId) {
      updateEditor({ refId: "", title: "", unitPrice: "0" });
      return;
    }
    setEditorState((prev) => {
      if (!prev) {
        return prev;
      }
      const line = prev.line;
      if (kind === "activity") {
        const activity = activities.find((item) => item.id === refId);
        const catalogPrice = activityCatalogPriceByActivityId[refId];
        const fallbackPrice = computeActivityFallbackPrice(activity);
        const resolvedUnitPrice = catalogPrice ?? fallbackPrice ?? line.unitPrice;
        const currentVat = Number(line.vatRate || "0");
        const shouldPrefillVat = !Number.isFinite(currentVat) || currentVat <= 0;
        return {
          ...prev,
          line: {
            ...line,
            refId,
            title: activity?.name ?? "Activite",
            vatRate: shouldPrefillVat ? (defaultVatRate || "0") : line.vatRate,
            unitPrice: resolvedUnitPrice && resolvedUnitPrice !== "" ? resolvedUnitPrice : "0",
          },
        };
      }
      if (kind === "product") {
        const product = products.find((item) => item.id === refId);
        const catalogPrice = productCatalogPriceByProductId[refId];
        const resolvedVatRate = product?.vat_rate ?? line.vatRate;
        const resolvedUnitPrice = catalogPrice ?? product?.price_incl_vat ?? line.unitPrice;
        return {
          ...prev,
          line: {
            ...line,
            refId,
            title: product?.title ?? "Produit",
            vatRate: resolvedVatRate && resolvedVatRate !== "" ? resolvedVatRate : "0",
            unitPrice: resolvedUnitPrice && resolvedUnitPrice !== "" ? resolvedUnitPrice : "0",
          },
        };
      }
      const kit = kits.find((item) => item.id === refId);
      const catalogPrice = kitCatalogPriceByKitId[refId];
      const resolvedVatRate = kit?.vat_rate ?? line.vatRate;
      const resolvedUnitPrice = catalogPrice ?? kit?.effective_price_ttc ?? line.unitPrice;
      return {
        ...prev,
        line: {
          ...line,
          refId,
          title: kit?.title ?? "Kit",
          vatRate: resolvedVatRate && resolvedVatRate !== "" ? resolvedVatRate : "0",
          unitPrice: resolvedUnitPrice && resolvedUnitPrice !== "" ? resolvedUnitPrice : "0",
        },
      };
    });
  }

  function commitEditor(): void {
    if (!editorState) {
      return;
    }
    const draft = editorState.line;
    if (editorState.originalUid === null) {
      setLines((prev) => [...prev, draft]);
      setEditorState(null);
      return;
    }
    setLines((prev) =>
      prev.map((line) => {
        if (line.uid !== editorState.originalUid) {
          return line;
        }
        if (!editableLineChanged(line, draft)) {
          return line;
        }
        return {
          ...draft,
          uid: line.uid,
          saved: line.saved,
          dirty: line.saved ? true : draft.dirty,
        };
      }),
    );
    setEditorState(null);
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

  const editorLine = editorState?.line ?? null;
  const editorSelectedLabel = editorLine
    ? selectedOptionLabel(editorLine.kind, editorLine.refId, activities, products, kits)
    : null;
  const editorPlanningSummary = editorLine
    ? planningSummaryForLine(editorLine, planningByActivityId)
    : null;
  const editorPlanningMismatch = editorLine
    ? hasPlanningMismatch(editorLine, editorPlanningSummary)
    : false;
  const editorResolvedSourcePrice = editorLine
    ? resolvedSourceUnitPrice(
      editorLine,
      activities,
      products,
      kits,
      activityCatalogPriceByActivityId,
      productCatalogPriceByProductId,
      kitCatalogPriceByKitId,
    )
    : null;
  const editorPlannedQuantity = editorPlanningSummary?.plannedQuantity ?? 0;
  const editorCanAlignQuantity =
    editorLine?.kind === "activity"
    && editorPlannedQuantity > 0
    && formatQuantityDisplay(editorLine.quantity) !== String(editorPlannedQuantity);
  const editorHasSourcePriceGap =
    editorLine !== null
    && editorResolvedSourcePrice !== null
    && !sameMoneyValue(editorLine.unitPrice, editorResolvedSourcePrice.unitPrice);

  return (
    <form action={saveAction}>
      <input type="hidden" name="quote_id" value={quoteId} />
      <input type="hidden" name="return_to" value={returnTo} />
      <input type="hidden" name="lines_json" value={linesJson} />

      <div className="quote-editor-toolbar row spread wrap gap-sm">
        <div className="quote-editor-toolbar-main">
          <strong>Lignes facturees</strong>
          <span className="quote-editor-count">
            {savedCount} enregistree(s), {modifiedCount + newCount} brouillon(s)
          </span>
        </div>
        <div className="row wrap gap-sm">
          <button type="button" className="ghost quote-add-button" onClick={() => openCreateModal("activity")} disabled={!editable}>
            <PlusIcon />
            <span>Activite</span>
          </button>
          <button type="button" className="ghost quote-add-button" onClick={() => openCreateModal("product")} disabled={!editable}>
            <PlusIcon />
            <span>Produit</span>
          </button>
          <button type="button" className="ghost quote-add-button" onClick={() => openCreateModal("kit")} disabled={!editable}>
            <PlusIcon />
            <span>Kit</span>
          </button>
          <button type="button" className="ghost quote-add-button" onClick={() => openCreateModal("discount")} disabled={!editable}>
            <PlusIcon />
            <span>Remise</span>
          </button>
          <button type="button" className="ghost quote-add-button" onClick={() => openCreateModal("surcharge")} disabled={!editable}>
            <PlusIcon />
            <span>Supplement</span>
          </button>
          <span className={`quote-status-chip ${pendingSaveCount > 0 ? "quote-status-chip-pending" : "quote-status-chip-saved"}`}>
            {pendingSaveCount > 0 ? "A enregistrer" : "Enregistre"}
          </span>
        </div>
      </div>

      <section className="quote-editor-pane quote-editor-pane-saved top-gap-sm">
        {lines.length === 0 ? (
          <p className="quote-editor-empty">Aucune ligne enregistree pour ce devis.</p>
        ) : (
          <div className="quote-saved-list">
            {lines.map((line) => {
              const planningSummary = planningSummaryForLine(line, planningByActivityId);
              const planningMismatch = hasPlanningMismatch(line, planningSummary);
              return (
                <article key={line.uid} className="quote-saved-card">
                  <div className="quote-saved-card-top">
                    <div className="quote-saved-card-head">
                      <div className="quote-saved-card-badges">
                        <span className="quote-line-kind-pill">{lineTypeLabel(line.kind)}</span>
                        <span className={`quote-status-chip ${lineStatusClass(line)}`}>{lineStatusLabel(line)}</span>
                      </div>
                      <button
                        type="button"
                        className="quote-saved-card-title-button"
                        onClick={() => openEditModal(line.uid)}
                      >
                        <span className="quote-line-title-text" title={line.title || "-"}>
                          {line.title || "-"}
                        </span>
                      </button>
                    </div>
                    <div className="quote-saved-card-actions">
                      <button
                        type="button"
                        className="quote-icon-button"
                        onClick={() => openEditModal(line.uid)}
                        disabled={!editable}
                        aria-label={`Modifier ${line.title || "la ligne"}`}
                        title="Modifier"
                      >
                        <PencilIcon />
                      </button>
                      <button
                        type="button"
                        className="quote-icon-button quote-icon-button-danger"
                        onClick={() => removeLine(line.uid)}
                        disabled={!editable}
                        aria-label={`Supprimer ${line.title || "la ligne"}`}
                        title="Supprimer"
                      >
                        <TrashIcon />
                      </button>
                    </div>
                  </div>
                  <div className="quote-saved-card-metrics">
                    <div>
                      <span>Qt facturee</span>
                      <strong>{formatQuantityDisplay(line.quantity)}</strong>
                    </div>
                    <div className={planningMismatch ? "quote-saved-card-metric-warning" : ""}>
                      <span>Qt planifiee</span>
                      <strong>{formatPlannedQuantityDisplay(planningSummary)}</strong>
                    </div>
                    <div>
                      <span>PU TTC</span>
                      <strong>{toMoney(Number(line.unitPrice || "0"), currency)}</strong>
                    </div>
                    <div>
                      <span>Total TTC</span>
                      <strong>{toMoney(lineAmount(line), currency)}</strong>
                    </div>
                  </div>
                  <div className="quote-saved-card-footer">
                    <span>TVA {formatPercentDisplay(line.vatRate)}</span>
                    {planningMismatch ? <span>Le planning et la facturation ne sont pas alignes.</span> : null}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {editorLine ? (
        <section className="modal-overlay" role="dialog" aria-modal="true" aria-label="Modifier une ligne de devis">
          <article className="modal-panel quote-line-editor-modal" onClick={(event) => event.stopPropagation()}>
            <button type="button" className="modal-close-x" onClick={closeEditor} aria-label="Fermer">
              ×
            </button>
            <div className="quote-line-editor-modal-head">
              <div>
                <p className="quote-line-editor-kicker">
                  {editorState?.originalUid ? "Edition de ligne" : "Nouvelle ligne"}
                </p>
                <h3 className="modal-title">
                  {editorState?.originalUid ? "Modifier la ligne" : `Ajouter ${lineTypeLabel(editorLine.kind).toLowerCase()}`}
                </h3>
              </div>
              <span className={`quote-status-chip ${editorLine.saved ? "quote-status-chip-editing" : "quote-status-chip-new"}`}>
                {editorLine.saved ? "Brouillon modifie" : "Ajout au brouillon"}
              </span>
            </div>

            <article className="quote-line-card quote-line-card-modal">
              <div className="row spread wrap gap-sm">
                <strong>{lineTypeLabel(editorLine.kind)}</strong>
                {editorState?.originalUid ? (
                  <button
                    type="button"
                    className="ghost small-btn"
                    onClick={() => {
                      removeLine(editorState.originalUid as string);
                      closeEditor();
                    }}
                    disabled={!editable}
                  >
                    Supprimer
                  </button>
                ) : null}
              </div>
              {(editorLine.kind === "activity" || editorLine.kind === "product" || editorLine.kind === "kit") ? (
                <>
                  <label className="top-gap-sm">
                    Element
                    <select
                      value={editorLine.refId}
                      onChange={(event) => applyRefToEditor(editorLine.kind, event.target.value)}
                      disabled={!editable}
                    >
                      <option value="">Selectionner</option>
                      {selectableOptions(editorLine.kind, activities, products, kits).map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  {editorSelectedLabel ? (
                    <small className="muted quote-selected-item-label" title={editorSelectedLabel}>
                      {editorSelectedLabel}
                    </small>
                  ) : null}
                </>
              ) : null}
              <div className="grid cols-4 top-gap-sm">
                <label className="cols-span-4">
                  Intitule
                  <input
                    type="text"
                    value={editorLine.title}
                    onChange={(event) => updateEditor({ title: event.target.value })}
                    title={editorLine.title || ""}
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
                    value={editorLine.quantity}
                    onChange={(event) => updateEditor({ quantity: normalizeQuantityInput(event.target.value) })}
                    required
                    disabled={!editable}
                  />
                </label>
                {editorCanAlignQuantity ? (
                  <div className="quote-line-planning-summary cols-span-4">
                    <span>Le planning prevoit {editorPlannedQuantity} seance(s) pour cette activite.</span>
                    <button
                      type="button"
                      className="ghost small-btn"
                      onClick={() => updateEditor({ quantity: String(editorPlannedQuantity) })}
                      disabled={!editable}
                    >
                      Aligner la quantite sur le planning
                    </button>
                  </div>
                ) : null}
                {editorLine.kind === "activity" ? (
                  <div className={`quote-line-planning-summary cols-span-4${editorPlanningMismatch ? " is-warning" : ""}`}>
                    <span>Quantite facturee : {formatQuantityDisplay(editorLine.quantity)}</span>
                    <span>Quantite planifiee : {formatPlannedQuantityDisplay(editorPlanningSummary)}</span>
                  </div>
                ) : null}
                <label>
                  TVA (%)
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step="0.01"
                    value={editorLine.vatRate}
                    onChange={(event) => updateEditor({ vatRate: event.target.value })}
                    required
                    disabled={!editable}
                  />
                </label>
                <label className="quote-price-field">
                  Prix unitaire TTC
                  <input
                    type="number"
                    step="0.01"
                    value={editorLine.unitPrice}
                    onChange={(event) => updateEditor({ unitPrice: event.target.value })}
                    required
                    disabled={!editable}
                  />
                </label>
                {editorResolvedSourcePrice ? (
                  <div className={`quote-line-planning-summary cols-span-4${editorHasSourcePriceGap ? " is-warning" : ""}`}>
                    <span>
                      Tarif source actuel : {toMoney(Number(editorResolvedSourcePrice.unitPrice || "0"), currency)}
                      {" · "}
                      {editorResolvedSourcePrice.sourceLabel}
                    </span>
                    {editorHasSourcePriceGap ? (
                      <button
                        type="button"
                        className="ghost small-btn"
                        onClick={() => updateEditor({ unitPrice: editorResolvedSourcePrice.unitPrice })}
                        disabled={!editable}
                      >
                        Reappliquer ce tarif
                      </button>
                    ) : null}
                  </div>
                ) : null}
                <div className="quote-line-amounts-row">
                  <div className="quote-line-amount">
                    <span>Total ligne TTC</span>
                    <strong>{toMoney(lineAmount(editorLine), currency)}</strong>
                  </div>
                  <div className="quote-line-amount">
                    <span>Montant HT</span>
                    <strong>{toMoney(lineAmountHt(editorLine), currency)}</strong>
                  </div>
                  <div className="quote-line-amount">
                    <span>Montant TVA</span>
                    <strong>{toMoney(lineAmountVat(editorLine), currency)}</strong>
                  </div>
                </div>
              </div>
              {isCatalogKind(editorLine.kind) ? (
                <small className="muted">
                  Le total de ligne se recalcule automatiquement depuis la quantite et le prix unitaire. Vous pouvez reappliquer le tarif source actuel si necessaire.
                </small>
              ) : null}
            </article>

            <div className="row modal-actions-end top-gap-sm">
              <button type="button" className="ghost" onClick={closeEditor}>
                Annuler
              </button>
              <button type="button" onClick={commitEditor} disabled={!editable}>
                Appliquer au brouillon
              </button>
            </div>
          </article>
        </section>
      ) : null}

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
