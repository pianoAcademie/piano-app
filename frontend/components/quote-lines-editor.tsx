"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";

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
  meta?: Record<string, unknown>;
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
  meta: Record<string, unknown>;
  manualUnitPriceOverride: boolean;
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
  language?: UiLanguage | string;
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

function toMoney(value: number, currency = "EUR", language: UiLanguage = "fr"): string {
  if (!Number.isFinite(value)) {
    return `0,00 ${(currency || "EUR").toUpperCase()}`;
  }
  try {
    return new Intl.NumberFormat(localeForUiLanguage(language), { style: "currency", currency: (currency || "EUR").toUpperCase() }).format(value);
  } catch {
    return `${value.toFixed(2)} ${(currency || "EUR").toUpperCase()}`;
  }
}

function formatPercentDisplay(value: string | null | undefined, language: UiLanguage = "fr"): string {
  const parsed = Number(String(value ?? "").trim());
  if (!Number.isFinite(parsed)) {
    return "0,00%";
  }
  return `${new Intl.NumberFormat(localeForUiLanguage(language), {
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
  const meta: Record<string, unknown> = { ...(line.meta || {}) };
  if (line.manualUnitPriceOverride) {
    meta.manual_unit_price_override = true;
  } else {
    delete meta.manual_unit_price_override;
  }
  if (line.kind === "discount") {
    return {
      line_category: "product",
      line_type: "discount",
      master_item_type: "discount_rule",
      title: line.title || "Discount",
      quantity: normalizeQuantityInput(line.quantity),
      vat_rate: line.vatRate || "0",
      unit_price_ttc: String(Math.abs(Number(line.unitPrice || "0"))),
      meta,
      sort_order: index,
    };
  }
  if (line.kind === "surcharge") {
    return {
      line_category: "product",
      line_type: "surcharge",
      master_item_type: "surcharge_rule",
      title: line.title || "Surcharge",
      quantity: normalizeQuantityInput(line.quantity),
      vat_rate: line.vatRate || "0",
      unit_price_ttc: String(Math.abs(Number(line.unitPrice || "0"))),
      meta,
      sort_order: index,
    };
  }
  if (line.kind === "activity") {
    return {
      line_category: "service",
      line_type: "item",
      master_item_type: "activity",
      activity_id: line.refId || null,
      title: line.title || "Activity",
      quantity: normalizeQuantityInput(line.quantity),
      vat_rate: line.vatRate || "0",
      unit_price_ttc: line.unitPrice || "0",
      meta,
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
      meta,
      sort_order: index,
    };
  }
  return {
    line_category: "product",
    line_type: "item",
    master_item_type: "product",
    product_id: line.refId || null,
    title: line.title || "Product",
    quantity: normalizeQuantityInput(line.quantity),
    vat_rate: line.vatRate || "0",
    unit_price_ttc: line.unitPrice || "0",
    meta,
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
  language: UiLanguage,
): ResolvedUnitPrice | null {
  if (line.kind === "activity") {
    const activity = activities.find((item) => item.id === line.refId);
    const catalogPrice = activityCatalogPriceByActivityId[line.refId];
    if (catalogPrice && catalogPrice !== "") {
      return { unitPrice: catalogPrice, sourceLabel: uiText(language, "admin.quote_lines.source_catalog") };
    }
    const direct = parsePositive(activity?.default_course_rate_ttc);
    if (direct !== null) {
      return { unitPrice: direct.toFixed(2), sourceLabel: uiText(language, "admin.quote_lines.source_activity_course") };
    }
    const fallbackPrice = computeActivityFallbackPrice(activity);
    if (fallbackPrice && fallbackPrice !== "") {
      return { unitPrice: fallbackPrice, sourceLabel: uiText(language, "admin.quote_lines.source_activity_hourly") };
    }
    return null;
  }
  if (line.kind === "product") {
    const product = products.find((item) => item.id === line.refId);
    const catalogPrice = productCatalogPriceByProductId[line.refId];
    if (catalogPrice && catalogPrice !== "") {
      return { unitPrice: catalogPrice, sourceLabel: uiText(language, "admin.quote_lines.source_catalog") };
    }
    if (product?.price_incl_vat) {
      return { unitPrice: product.price_incl_vat, sourceLabel: uiText(language, "admin.quote_lines.source_product_price") };
    }
    return null;
  }
  if (line.kind === "kit") {
    const kit = kits.find((item) => item.id === line.refId);
    const catalogPrice = kitCatalogPriceByKitId[line.refId];
    if (catalogPrice && catalogPrice !== "") {
      return { unitPrice: catalogPrice, sourceLabel: uiText(language, "admin.quote_lines.source_catalog") };
    }
    if (kit?.effective_price_ttc) {
      return { unitPrice: kit.effective_price_ttc, sourceLabel: uiText(language, "admin.quote_lines.source_kit_price") };
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
  language: UiLanguage = "fr",
): string {
  if (!summary) {
    return "-";
  }
  if (summary.pendingSelection && summary.plannedQuantity <= 0) {
    return uiText(language, "admin.quote_lines.quantity_to_confirm");
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
    || String(current.unitPrice) !== String(next.unitPrice)
    || current.manualUnitPriceOverride !== next.manualUnitPriceOverride;
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
    meta: {},
    manualUnitPriceOverride: false,
    saved: false,
    dirty: true,
  };
}

function editableLineFromInitial(row: InitialQuoteLine): EditableLine {
  const meta = row.meta && typeof row.meta === "object" ? row.meta : {};
  return {
    uid: row.id,
    kind: inferKind(row),
    refId: inferRefId(row),
    title: row.title || "",
    quantity: normalizeQuantityInput(row.quantity),
    vatRate: normalizePercentInput(row.vat_rate),
    unitPrice: row.unit_price_ttc || "0",
    meta,
    manualUnitPriceOverride: meta.manual_unit_price_override === true,
    saved: true,
    dirty: false,
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
  language: languageProp = "fr",
  saveAction,
}: QuoteLinesEditorProps): JSX.Element {
  const language = normalizeUiLanguage(languageProp);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const initialLinesSignature = useMemo(
    () => JSON.stringify(
      initialLines.map((row) => ({
        id: row.id,
        line_type: row.line_type,
        activity_id: row.activity_id,
        product_id: row.product_id,
        kit_id: row.kit_id,
        title: row.title,
        quantity: row.quantity,
        vat_rate: row.vat_rate,
        unit_price_ttc: row.unit_price_ttc,
        meta: row.meta ?? {},
      })),
    ),
    [initialLines],
  );
  const mappedInitialLines = useMemo(() => initialLines.map(editableLineFromInitial), [initialLinesSignature]);
  const [lines, setLines] = useState<EditableLine[]>(() => mappedInitialLines);
  const [editorState, setEditorState] = useState<EditorState | null>(null);
  const [saveConfirmationMessage, setSaveConfirmationMessage] = useState<string>("");
  const handledSuccessTokenRef = useRef<string>("");

  useEffect(() => {
    setLines(mappedInitialLines);
    setEditorState(null);
  }, [mappedInitialLines]);

  useEffect(() => {
    const okMessage = searchParams?.get("ok")?.trim() ?? "";
    if (okMessage !== "Lignes devis mises a jour") {
      return;
    }
    const successToken = `${pathname}?${searchParams?.toString() ?? ""}`;
    if (handledSuccessTokenRef.current === successToken) {
      return;
    }
    handledSuccessTokenRef.current = successToken;
    setLines((prev) => prev.map((line) => ({ ...line, saved: true, dirty: false })));
    setEditorState(null);
    const localizedOkMessage = uiText(language, "admin.quote_lines.saved_success");
    setSaveConfirmationMessage(localizedOkMessage);
    window.alert(localizedOkMessage);
    const nextParams = new URLSearchParams(searchParams?.toString() ?? "");
    nextParams.delete("ok");
    const nextQuery = nextParams.toString();
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, { scroll: false });
  }, [language, pathname, router, searchParams]);

  const linesJson = useMemo(() => JSON.stringify(lines.map((line, index) => buildLinePayload(line, index))), [lines]);
  const total = useMemo(() => lines.reduce((sum, line) => sum + lineAmount(line), 0), [lines]);
  const totalHt = useMemo(() => lines.reduce((sum, line) => sum + lineAmountHt(line), 0), [lines]);
  const totalVat = useMemo(() => lines.reduce((sum, line) => sum + lineAmountVat(line), 0), [lines]);
  const savedCount = lines.filter((line) => line.saved && !line.dirty).length;
  const modifiedCount = lines.filter((line) => line.saved && line.dirty).length;
  const newCount = lines.filter((line) => !line.saved).length;
  const pendingSaveCount = lines.filter((line) => !line.saved || line.dirty).length;

  useEffect(() => {
    if (pendingSaveCount > 0 && saveConfirmationMessage) {
      setSaveConfirmationMessage("");
    }
  }, [pendingSaveCount, saveConfirmationMessage]);

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
      updateEditor({ refId: "", title: "", unitPrice: "0", manualUnitPriceOverride: false });
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
            title: activity?.name ?? t("admin.quote_lines.kind_activity"),
            vatRate: shouldPrefillVat ? (defaultVatRate || "0") : line.vatRate,
            unitPrice: resolvedUnitPrice && resolvedUnitPrice !== "" ? resolvedUnitPrice : "0",
            manualUnitPriceOverride: false,
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
            title: product?.title ?? t("admin.quote_lines.kind_product"),
            vatRate: resolvedVatRate && resolvedVatRate !== "" ? resolvedVatRate : "0",
            unitPrice: resolvedUnitPrice && resolvedUnitPrice !== "" ? resolvedUnitPrice : "0",
            manualUnitPriceOverride: false,
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
          manualUnitPriceOverride: false,
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
      return t("admin.quote_lines.status_new");
    }
    if (line.dirty) {
      return t("admin.quote_lines.status_dirty");
    }
    return t("admin.quote_lines.status_saved");
  }

  function lineStatusClass(line: EditableLine): string {
    if (!line.saved) return "quote-status-chip-new";
    if (line.dirty) return "quote-status-chip-editing";
    return "quote-status-chip-saved";
  }

  function lineTypeLabel(kind: LineKind): string {
    if (kind === "activity") return t("admin.quote_lines.kind_activity");
    if (kind === "product") return t("admin.quote_lines.kind_product");
    if (kind === "kit") return t("admin.quote_lines.kind_kit");
    if (kind === "discount") return t("admin.quote_lines.kind_discount");
    return t("admin.quote_lines.kind_surcharge");
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
      language,
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
          <strong>{t("admin.quote_lines.title_main")}</strong>
          <span className="quote-editor-count">
            {t("admin.quote_lines.counts", { saved: savedCount, draft: modifiedCount + newCount })}
          </span>
        </div>
        <div className="row wrap gap-sm">
          <button type="button" className="ghost quote-add-button" onClick={() => openCreateModal("activity")} disabled={!editable}>
            <PlusIcon />
            <span>{t("admin.quote_lines.kind_activity")}</span>
          </button>
          <button type="button" className="ghost quote-add-button" onClick={() => openCreateModal("product")} disabled={!editable}>
            <PlusIcon />
            <span>{t("admin.quote_lines.kind_product")}</span>
          </button>
          <button type="button" className="ghost quote-add-button" onClick={() => openCreateModal("kit")} disabled={!editable}>
            <PlusIcon />
            <span>{t("admin.quote_lines.kind_kit")}</span>
          </button>
          <button type="button" className="ghost quote-add-button" onClick={() => openCreateModal("discount")} disabled={!editable}>
            <PlusIcon />
            <span>{t("admin.quote_lines.kind_discount")}</span>
          </button>
          <button type="button" className="ghost quote-add-button" onClick={() => openCreateModal("surcharge")} disabled={!editable}>
            <PlusIcon />
            <span>{t("admin.quote_lines.kind_surcharge")}</span>
          </button>
          <span className={`quote-status-chip ${pendingSaveCount > 0 ? "quote-status-chip-pending" : "quote-status-chip-saved"}`}>
            {pendingSaveCount > 0 ? t("admin.quote_lines.pending_save") : t("admin.quote_lines.status_saved")}
          </span>
        </div>
      </div>

      <section className="quote-editor-pane quote-editor-pane-saved top-gap-sm">
        {lines.length === 0 ? (
          <p className="quote-editor-empty">{t("admin.quote_lines.empty")}</p>
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
                        aria-label={t("admin.quote_lines.edit_aria", { title: line.title || t("admin.quote_lines.line_fallback") })}
                        title={t("common.edit")}
                      >
                        <PencilIcon />
                      </button>
                      <button
                        type="button"
                        className="quote-icon-button quote-icon-button-danger"
                        onClick={() => removeLine(line.uid)}
                        disabled={!editable}
                        aria-label={t("admin.quote_lines.delete_aria", { title: line.title || t("admin.quote_lines.line_fallback") })}
                        title={t("common.delete")}
                      >
                        <TrashIcon />
                      </button>
                    </div>
                  </div>
                  <div className="quote-saved-card-metrics">
                    <div>
                      <span>{t("admin.quote_lines.billed_quantity")}</span>
                      <strong>{formatQuantityDisplay(line.quantity)}</strong>
                    </div>
                    <div className={planningMismatch ? "quote-saved-card-metric-warning" : ""}>
                      <span>{t("admin.quote_lines.planned_quantity")}</span>
                      <strong>{formatPlannedQuantityDisplay(planningSummary, language)}</strong>
                    </div>
                    <div>
                      <span>{t("admin.quote_lines.unit_price_ttc_short")}</span>
                      <strong>{toMoney(Number(line.unitPrice || "0"), currency, language)}</strong>
                    </div>
                    <div>
                      <span>{t("admin.quote_lines.total_ttc")}</span>
                      <strong>{toMoney(lineAmount(line), currency, language)}</strong>
                    </div>
                  </div>
                  <div className="quote-saved-card-footer">
                    <span>{t("common.vat")} {formatPercentDisplay(line.vatRate, language)}</span>
                    {planningMismatch ? <span>{t("admin.quote_lines.planning_mismatch")}</span> : null}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {editorLine ? (
        <section className="modal-overlay" role="dialog" aria-modal="true" aria-label={t("admin.quote_lines.modal_aria")}>
          <article className="modal-panel quote-line-editor-modal" onClick={(event) => event.stopPropagation()}>
            <button type="button" className="modal-close-x" onClick={closeEditor} aria-label={t("common.close")}>
              ×
            </button>
            <div className="quote-line-editor-modal-head">
              <div>
                <p className="quote-line-editor-kicker">
                  {editorState?.originalUid ? t("admin.quote_lines.editing_kicker") : t("admin.quote_lines.new_kicker")}
                </p>
                <h3 className="modal-title">
                  {editorState?.originalUid ? t("admin.quote_lines.edit_line") : t("admin.quote_lines.add_line", { kind: lineTypeLabel(editorLine.kind).toLowerCase() })}
                </h3>
              </div>
              <span className={`quote-status-chip ${editorLine.saved ? "quote-status-chip-editing" : "quote-status-chip-new"}`}>
                {editorLine.saved ? t("admin.quote_lines.draft_modified") : t("admin.quote_lines.draft_added")}
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
                    {t("common.delete")}
                  </button>
                ) : null}
              </div>
              {(editorLine.kind === "activity" || editorLine.kind === "product" || editorLine.kind === "kit") ? (
                <>
                  <label className="top-gap-sm">
                    {t("admin.quote_lines.element")}
                    <select
                      value={editorLine.refId}
                      onChange={(event) => applyRefToEditor(editorLine.kind, event.target.value)}
                      disabled={!editable}
                    >
                      <option value="">{t("common.choose")}</option>
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
                  {t("admin.quote_lines.line_title")}
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
                  {t("common.quantity")}
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
                    <span>{t("admin.quote_lines.planning_expected", { count: editorPlannedQuantity })}</span>
                    <button
                      type="button"
                      className="ghost small-btn"
                      onClick={() => updateEditor({ quantity: String(editorPlannedQuantity) })}
                      disabled={!editable}
                    >
                      {t("admin.quote_lines.align_quantity")}
                    </button>
                  </div>
                ) : null}
                {editorLine.kind === "activity" ? (
                  <div className={`quote-line-planning-summary cols-span-4${editorPlanningMismatch ? " is-warning" : ""}`}>
                    <span>{t("admin.quote_lines.billed_quantity_value", { value: formatQuantityDisplay(editorLine.quantity) })}</span>
                    <span>{t("admin.quote_lines.planned_quantity_value", { value: formatPlannedQuantityDisplay(editorPlanningSummary, language) })}</span>
                  </div>
                ) : null}
                <label>
                  {t("admin.quote_lines.vat_percent")}
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
                  {t("admin.quote_lines.unit_price_ttc")}
                  <input
                    type="number"
                    step="0.01"
                    value={editorLine.unitPrice}
                    onChange={(event) => updateEditor({ unitPrice: event.target.value, manualUnitPriceOverride: true })}
                    required
                    disabled={!editable}
                  />
                </label>
                {editorResolvedSourcePrice ? (
                  <div className={`quote-line-planning-summary cols-span-4${editorHasSourcePriceGap ? " is-warning" : ""}`}>
                    <span>
                      {t("admin.quote_lines.current_source_price", { amount: toMoney(Number(editorResolvedSourcePrice.unitPrice || "0"), currency, language) })}
                      {" · "}
                      {editorResolvedSourcePrice.sourceLabel}
                    </span>
                    {editorHasSourcePriceGap ? (
                      <button
                        type="button"
                        className="ghost small-btn"
                        onClick={() => updateEditor({ unitPrice: editorResolvedSourcePrice.unitPrice, manualUnitPriceOverride: false })}
                        disabled={!editable}
                      >
                        {t("admin.quote_lines.reapply_price")}
                      </button>
                    ) : null}
                  </div>
                ) : null}
                <div className="quote-line-amounts-row">
                  <div className="quote-line-amount">
                    <span>{t("admin.quote_lines.line_total_ttc")}</span>
                    <strong>{toMoney(lineAmount(editorLine), currency, language)}</strong>
                  </div>
                  <div className="quote-line-amount">
                    <span>{t("admin.quote_lines.amount_ht")}</span>
                    <strong>{toMoney(lineAmountHt(editorLine), currency, language)}</strong>
                  </div>
                  <div className="quote-line-amount">
                    <span>{t("admin.quote_lines.amount_vat")}</span>
                    <strong>{toMoney(lineAmountVat(editorLine), currency, language)}</strong>
                  </div>
                </div>
              </div>
              {isCatalogKind(editorLine.kind) ? (
                <small className="muted">
                  {t("admin.quote_lines.recalculation_hint")}
                </small>
              ) : null}
            </article>

            <div className="row modal-actions-end top-gap-sm">
              <button type="button" className="ghost" onClick={closeEditor}>
                {t("common.cancel")}
              </button>
              <button type="button" onClick={commitEditor} disabled={!editable}>
                {t("admin.quote_lines.apply_draft")}
              </button>
            </div>
          </article>
        </section>
      ) : null}

      <div className="row spread wrap top-gap-sm">
        <div>
          <p className="quote-total">
            {t("admin.quote_lines.estimated_total", {
              total: toMoney(total, currency, language),
              ht: toMoney(totalHt, currency, language),
              vat: toMoney(totalVat, currency, language),
            })}
          </p>
          {saveConfirmationMessage ? <p className="flash-ok top-gap-sm">{saveConfirmationMessage}</p> : null}
        </div>
        <button type="submit" disabled={!editable}>{t("admin.quote_lines.save_lines")}</button>
      </div>
      {!editable ? <p className="muted top-gap-sm">{t("admin.quote_lines.immutable_after_send")}</p> : null}
    </form>
  );
}
