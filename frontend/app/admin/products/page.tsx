import Link from "next/link";
import { randomUUID } from "node:crypto";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import AdminProductActionsMenu from "../../../components/admin-product-actions-menu";
import AdminSupplyOrders from "../../../components/admin-supply-orders";
import AdminProductCreateModal from "../../../components/admin-product-create-modal";
import AdminProductEditModal from "../../../components/admin-product-edit-modal";
import SearchMultiSelect from "../../../components/search-multi-select";
import {
  cancelAdminCatalogTransferAction,
  completeAdminCatalogTransferAction,
  createAdminCatalogProductAction,
  createAdminCatalogRequestAction,
  createAdminStockAdjustmentAction,
  createAdminStockEntryAction,
  createAdminCatalogTransferAction,
  deleteAdminCatalogProductAction,
  deliverAdminCatalogRequestAction,
  reviewAdminCatalogRequestAction,
  updateAdminCatalogInventoryAction,
  updateAdminCatalogProductAction,
  updateAdminCatalogReorderStatusAction,
} from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import type {
  AdminCatalogCategoryOut,
  AdminSupplyOrderOut,
  AdminCatalogProductOut,
  AdminCatalogReorderProductOut,
  AdminCatalogRequestOut,
  AdminCatalogStockOut,
  AdminCatalogStockTransferOut,
  AdminStockMovementListOut,
  AdminClientOut,
  UserOut,
  LocationOut,
} from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

type ProductsView = "products" | "reorder" | "entries" | "transfers" | "requests";
type ProductSortColumn =
  | "title"
  | "category"
  | "location"
  | "price"
  | "stock_global"
  | "stock_reserve"
  | "reorder"
  | "active";
type SortDirection = "asc" | "desc";
type ProductPerPage = 25 | 50 | 100;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function parseView(value: string): ProductsView {
  const normalized = value.trim().toLowerCase();
  if (normalized === "reorder") {
    return "reorder";
  }
  if (normalized === "transfers") {
    return "transfers";
  }
  if (normalized === "entries") {
    return "entries";
  }
  if (normalized === "requests") {
    return "requests";
  }
  return "products";
}

function parseProductSortColumn(value: string): ProductSortColumn {
  if (
    value === "title" ||
    value === "category" ||
    value === "location" ||
    value === "price" ||
    value === "stock_global" ||
    value === "stock_reserve" ||
    value === "reorder" ||
    value === "active"
  ) {
    return value;
  }
  return "title";
}

function parseSortDirection(value: string): SortDirection {
  return value === "desc" ? "desc" : "asc";
}

function parseProductPerPage(value: string): ProductPerPage {
  if (value === "50") {
    return 50;
  }
  if (value === "100") {
    return 100;
  }
  return 25;
}

function parsePage(value: string): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return 1;
  }
  return parsed;
}

function formatMoney(amountRaw: string | null, currency: string | null, language: UiLanguage): string {
  if (!amountRaw) {
    return "-";
  }
  const amount = Number(amountRaw);
  const normalizedCurrency = currency || "EUR";
  if (!Number.isFinite(amount)) {
    return `${amountRaw} ${normalizedCurrency}`;
  }
  try {
    return new Intl.NumberFormat(localeForUiLanguage(language), {
      style: "currency",
      currency: normalizedCurrency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${normalizedCurrency}`;
  }
}

function ProductThumbnail({ product, size = "desktop" }: { product: AdminCatalogProductOut; size?: "desktop" | "mobile" }): JSX.Element {
  const className = size === "mobile" ? "catalog-product-thumb catalog-product-thumb-mobile" : "catalog-product-thumb";
  const initial = (product.title || "?").trim().charAt(0).toUpperCase() || "?";
  if (product.image_url) {
    return <img src={product.image_url} alt="" className={className} loading="lazy" />;
  }
  return (
    <span className={`${className} catalog-product-thumb-fallback`} aria-hidden="true">
      {initial}
    </span>
  );
}

function yesNoLabel(value: boolean, language: UiLanguage): string {
  return value ? uiText(language, "common.yes") : uiText(language, "common.no");
}

function dateInputValue(value: string | null): string {
  if (!value) {
    return "";
  }
  return value.slice(0, 10);
}

function formatDateTime(value: string | null, language: UiLanguage): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(localeForUiLanguage(language), {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function reorderStatusLabel(status: string, language: UiLanguage): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "TO_ORDER") {
    return uiText(language, "admin.products.reorder_status_to_order");
  }
  if (normalized === "ORDERED") {
    return uiText(language, "admin.products.reorder_status_ordered");
  }
  if (normalized === "RECEIVED") {
    return uiText(language, "admin.products.reorder_status_received");
  }
  return uiText(language, "admin.products.reorder_status_normal");
}

function transferStatusLabel(status: string, language: UiLanguage): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "DONE") {
    return uiText(language, "admin.products.transfer_status_done");
  }
  if (normalized === "CANCELLED") {
    return uiText(language, "admin.products.transfer_status_cancelled");
  }
  return uiText(language, "admin.products.transfer_status_pending");
}

function catalogRequestStatusLabel(status: string, language: UiLanguage): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "PROCESSING") {
    return uiText(language, "admin.products.request_status_processing");
  }
  if (normalized === "REJECTED") {
    return uiText(language, "admin.products.request_status_rejected");
  }
  if (normalized === "WAITING_STOCK") {
    return uiText(language, "admin.products.request_status_waiting_stock");
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

function stockMovementTypeLabel(movementType: string, language: UiLanguage): string {
  const normalized = movementType.trim().toUpperCase();
  if (normalized === "ADJUSTMENT") {
    return uiText(language, "admin.products.movement_type_adjustment");
  }
  return uiText(language, "admin.products.movement_type_entry");
}

function stockMovementSourceTypeLabel(sourceType: string, language: UiLanguage): string {
  const normalized = sourceType.trim().toLowerCase();
  if (normalized === "purchase") {
    return uiText(language, "admin.products.movement_source_purchase");
  }
  if (normalized === "delivery") {
    return uiText(language, "admin.products.movement_source_delivery");
  }
  if (normalized === "correction") {
    return uiText(language, "admin.products.movement_source_correction");
  }
  if (normalized === "return") {
    return uiText(language, "admin.products.movement_source_return");
  }
  return uiText(language, "admin.products.movement_source_other");
}

function buildProductsQuery(params: {
  q: string;
  category: string;
  status: string;
  visibility: string;
  online: string;
  add: string;
  view: ProductsView;
  product: string;
  editProduct: string;
  sortBy: ProductSortColumn;
  sortDir: SortDirection;
  page: number;
  perPage: ProductPerPage;
  reorderStatus: string;
  transferStatus: string;
  entryProduct: string;
  entryLocation: string;
  entryQuery: string;
  entryId: string;
  entryPage: string;
}): string {
  const sp = new URLSearchParams();
  if (params.q) {
    sp.set("q", params.q);
  }
  if (params.category) {
    sp.set("category", params.category);
  }
  if (params.status && params.status !== "all") {
    sp.set("status", params.status);
  }
  if (params.visibility && params.visibility !== "all") {
    sp.set("visibility", params.visibility);
  }
  if (params.online && params.online !== "all") {
    sp.set("online", params.online);
  }
  if (params.add === "1") {
    sp.set("add", "1");
  }
  if (params.product) {
    sp.set("product", params.product);
  }
  if (params.editProduct) {
    sp.set("edit_product", params.editProduct);
  }
  if (params.sortBy !== "title") {
    sp.set("sort_by", params.sortBy);
  }
  if (params.sortDir !== "asc") {
    sp.set("sort_dir", params.sortDir);
  }
  if (params.page > 1) {
    sp.set("page", String(params.page));
  }
  if (params.perPage !== 25) {
    sp.set("per_page", String(params.perPage));
  }
  if (params.view !== "products") {
    sp.set("view", params.view);
  }
  if (params.reorderStatus && params.reorderStatus !== "all") {
    sp.set("reorder_status", params.reorderStatus);
  }
  if (params.transferStatus && params.transferStatus !== "all") {
    sp.set("transfer_status", params.transferStatus);
  }
  if (params.entryProduct) {
    sp.set("entry_product", params.entryProduct);
  }
  if (params.entryLocation) {
    sp.set("entry_location", params.entryLocation);
  }
  if (params.entryQuery) {
    sp.set("entry_q", params.entryQuery);
  }
  if (params.entryId) {
    sp.set("entry_id", params.entryId);
  }
  if (params.entryPage && params.entryPage !== "1") {
    sp.set("entry_page", params.entryPage);
  }
  const query = sp.toString();
  return query ? `?${query}` : "";
}

function productSortIndicator(currentSortBy: ProductSortColumn, currentSortDir: SortDirection, targetSortBy: ProductSortColumn): string {
  if (currentSortBy !== targetSortBy) {
    return "↕";
  }
  return currentSortDir === "asc" ? "↑" : "↓";
}

function compareText(a: string | null | undefined, b: string | null | undefined): number {
  return (a ?? "").localeCompare(b ?? "", "fr", { sensitivity: "base" });
}

function compareNumber(a: number, b: number): number {
  return a - b;
}

async function loadLocationsForProducts(token: string): Promise<{ ok: true; data: LocationOut[] } | { ok: false; message: string }> {
  const directResult = await backendRequest<LocationOut[]>("/api/v1/locations?active=false", {}, token);
  if (directResult.ok) {
    return directResult;
  }
  const legacyResult = await backendRequest<LocationOut[]>("/api/v1/catalogue/locations?active=false", {}, token);
  if (legacyResult.ok) {
    return legacyResult;
  }
  return { ok: false, message: `${directResult.message} | ${legacyResult.message}` };
}

export default async function AdminProductsPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const params = searchParams ?? {};
  const okMessage = readParam(params, "ok");
  const errorMessage = readParam(params, "error");
  const query = readParam(params, "q").trim();
  const category = readParam(params, "category").trim();
  const status = readParam(params, "status").trim() || "all";
  const visibility = readParam(params, "visibility").trim() || "all";
  const online = readParam(params, "online").trim() || "all";
  const add = readParam(params, "add").trim();
  const selectedProductId = readParam(params, "product").trim();
  const editProductId = readParam(params, "edit_product").trim();
  const currentView = parseView(readParam(params, "view"));
  const sortBy = parseProductSortColumn(readParam(params, "sort_by"));
  const sortDir = parseSortDirection(readParam(params, "sort_dir"));
  const requestedPage = parsePage(readParam(params, "page"));
  const perPage = parseProductPerPage(readParam(params, "per_page"));
  const reorderStatus = readParam(params, "reorder_status").trim() || "all";
  const transferStatus = readParam(params, "transfer_status").trim() || "all";
  const entryProduct = readParam(params, "entry_product").trim();
  const entryLocation = readParam(params, "entry_location").trim();
  const entryQuery = readParam(params, "entry_q").trim();
  const entryId = readParam(params, "entry_id").trim();
  const entryPageRaw = readParam(params, "entry_page").trim();
  const entryPageParsed = Number.parseInt(entryPageRaw, 10);
  const entryPage = Number.isFinite(entryPageParsed) && entryPageParsed > 0 ? entryPageParsed : 1;
  const showAddForm = add === "1" && currentView === "products";

  const baseQuery = {
    q: query,
    category,
    status,
    visibility,
    online,
    view: currentView,
    product: selectedProductId,
    sortBy,
    sortDir,
    page: requestedPage,
    perPage,
    reorderStatus,
    transferStatus,
    entryProduct,
    entryLocation,
    entryQuery,
    entryId,
    entryPage: String(entryPage),
  };

  const returnTo = `/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "" })}`;
  const addFormReturnTo = `/admin/products${buildProductsQuery({ ...baseQuery, add: "1", editProduct: "" })}`;
  const addLink = `/admin/products${buildProductsQuery({ ...baseQuery, add: "1", editProduct: "" })}`;
  const closeModalLink = `/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "" })}`;
  const clearSelectedProductLink = `/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "", product: "" })}`;
  const entriesViewLink = `/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "", view: "entries" })}`;
  const transfersViewLink = `/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "", view: "transfers" })}`;

  const stocksPath = selectedProductId
    ? `/api/v1/admin/config/catalog/stocks?product_id=${encodeURIComponent(selectedProductId)}`
    : null;
  const reorderPath = reorderStatus && reorderStatus !== "all"
    ? `/api/v1/admin/config/catalog/reorder-products?status_filter=${encodeURIComponent(reorderStatus)}`
    : "/api/v1/admin/config/catalog/reorder-products";
  const transfersPath = transferStatus && transferStatus !== "all"
    ? `/api/v1/admin/config/catalog/transfers?status_filter=${encodeURIComponent(transferStatus)}`
    : "/api/v1/admin/config/catalog/transfers";
  const entryQueryParams = new URLSearchParams();
  entryQueryParams.set("page", String(entryPage));
  entryQueryParams.set("page_size", "20");
  if (entryProduct) {
    entryQueryParams.set("product_id", entryProduct);
  }
  if (entryLocation) {
    entryQueryParams.set("location_id", entryLocation);
  }
  if (entryQuery) {
    entryQueryParams.set("q", entryQuery);
  }
  const entriesPath = `/api/v1/admin/stock/entries?${entryQueryParams.toString()}`;

  const [categoriesResult, productsResult, stocksResult, requestsResult, locationsResult, clientsResult, reorderResult, transfersResult, entriesResult, supplyOrdersResult] = await Promise.all([
    backendRequest<AdminCatalogCategoryOut[]>("/api/v1/admin/config/catalog/categories?include_inactive=true", {}, token),
    backendRequest<AdminCatalogProductOut[]>("/api/v1/admin/config/catalog/products?include_inactive=true", {}, token),
    stocksPath ? backendRequest<AdminCatalogStockOut[]>(stocksPath, {}, token) : Promise.resolve({ ok: true as const, data: [] as AdminCatalogStockOut[] }),
    backendRequest<AdminCatalogRequestOut[]>("/api/v1/admin/catalog/requests", {}, token),
    loadLocationsForProducts(token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?limit=1000", {}, token),
    backendRequest<AdminCatalogReorderProductOut[]>(reorderPath, {}, token),
    backendRequest<AdminCatalogStockTransferOut[]>(transfersPath, {}, token),
    backendRequest<AdminStockMovementListOut>(entriesPath, {}, token),
    currentView === "reorder" ? backendRequest<AdminSupplyOrderOut[]>("/api/v1/admin/config/catalog/supply-orders", {}, token) : Promise.resolve({ ok: true as const, data: [] as AdminSupplyOrderOut[] }),
  ]);

  const loadErrors: string[] = [];
  const supplyOrders = supplyOrdersResult.ok ? supplyOrdersResult.data : (() => {
    loadErrors.push(`Commandes fournisseurs : ${supplyOrdersResult.message}`);
    return [] as AdminSupplyOrderOut[];
  })();
  const categories = categoriesResult.ok
    ? categoriesResult.data
    : (() => {
        loadErrors.push(`${t("admin.products.load_categories")}: ${categoriesResult.message}`);
        return [] as AdminCatalogCategoryOut[];
      })();
  const products = productsResult.ok
    ? productsResult.data
    : (() => {
        loadErrors.push(`${t("admin.products.load_products")}: ${productsResult.message}`);
        return [] as AdminCatalogProductOut[];
      })();
  const stocks = stocksResult.ok
    ? stocksResult.data
    : (() => {
        loadErrors.push(`${t("admin.products.load_stocks")}: ${stocksResult.message}`);
        return [] as AdminCatalogStockOut[];
      })();
  const requests = requestsResult.ok
    ? requestsResult.data
    : (() => {
        loadErrors.push(`${t("admin.products.load_requests")}: ${requestsResult.message}`);
        return [] as AdminCatalogRequestOut[];
      })();
  const locations = locationsResult.ok
    ? locationsResult.data
    : (() => {
        loadErrors.push(`${t("admin.products.load_locations")}: ${locationsResult.message}`);
        return [] as LocationOut[];
      })();
  const clients = clientsResult.ok
    ? clientsResult.data
    : (() => {
        loadErrors.push(`${t("admin.products.load_clients")}: ${clientsResult.message}`);
        return [] as AdminClientOut[];
      })();
  const reorderProducts = reorderResult.ok
    ? reorderResult.data
    : (() => {
        loadErrors.push(`${t("admin.products.load_reorder")}: ${reorderResult.message}`);
        return [] as AdminCatalogReorderProductOut[];
      })();
  const transfers = transfersResult.ok
    ? transfersResult.data
    : (() => {
        loadErrors.push(`${t("admin.products.load_transfers")}: ${transfersResult.message}`);
        return [] as AdminCatalogStockTransferOut[];
      })();
  const entriesPage = entriesResult.ok
    ? entriesResult.data
    : (() => {
        loadErrors.push(`${t("admin.products.load_entries")}: ${entriesResult.message}`);
        return { items: [], total: 0, page: 1, page_size: 20 } as AdminStockMovementListOut;
      })();

  const activeCategories = categories.filter((row) => row.active);
  const activeProducts = products.filter((row) => row.active);
  const stockableProducts = activeProducts.filter((row) => !row.is_virtual);
  const activeLocations = locations.filter((row) => row.active);
  const activeCatalogRequests = requests.filter(
    (row) => row.status === "PROCESSING" || row.status === "WAITING_STOCK" || row.status === "INVOICE_TO_SEND" || row.status === "TO_DELIVER",
  );
  const activeCatalogRequestIds = new Set(activeCatalogRequests.map((row) => row.id));
  const productStats = {
    total: products.length,
    active: activeProducts.length,
    virtual: activeProducts.filter((row) => row.is_virtual).length,
    lowStock: activeProducts.filter((row) => !row.is_virtual && row.stock_global_quantity < row.reserve_stock).length,
    activeRequests: activeCatalogRequests.length,
  };

  const qLower = query.toLocaleLowerCase("fr-FR");
  const filteredProducts = products
    .filter((product) => {
      if (qLower) {
        const haystack = [product.title, product.barcode || "", product.category_name || "", product.short_description || ""]
          .join(" ")
          .toLocaleLowerCase("fr-FR");
        if (!haystack.includes(qLower)) {
          return false;
        }
      }
      if (category && product.category_id !== category) {
        return false;
      }
      if (status === "active" && !product.active) {
        return false;
      }
      if (status === "inactive" && product.active) {
        return false;
      }
      if (visibility === "public" && !product.is_public) {
        return false;
      }
      if (visibility === "private" && product.is_public) {
        return false;
      }
      if (online === "online" && !product.purchasable_online) {
        return false;
      }
      if (online === "offline" && product.purchasable_online) {
        return false;
      }
      return true;
    })
    .sort((a, b) => {
      let comparison = 0;
      switch (sortBy) {
        case "category":
          comparison = compareText(a.category_name, b.category_name) || compareText(a.title, b.title);
          break;
        case "location":
          comparison = compareText(a.primary_location_name, b.primary_location_name) || compareText(a.title, b.title);
          break;
        case "price":
          comparison = compareNumber(Number(a.price_incl_vat), Number(b.price_incl_vat)) || compareText(a.title, b.title);
          break;
        case "stock_global":
          comparison = compareNumber(a.stock_global_quantity, b.stock_global_quantity) || compareText(a.title, b.title);
          break;
        case "stock_reserve":
          comparison = compareNumber(a.reserve_stock, b.reserve_stock) || compareText(a.title, b.title);
          break;
        case "reorder": {
          const aNeeds = !a.is_virtual && a.stock_global_quantity < a.reserve_stock ? 1 : 0;
          const bNeeds = !b.is_virtual && b.stock_global_quantity < b.reserve_stock ? 1 : 0;
          comparison = compareNumber(aNeeds, bNeeds) || compareText(a.title, b.title);
          break;
        }
        case "active":
          comparison = compareNumber(a.active ? 1 : 0, b.active ? 1 : 0) || compareText(a.title, b.title);
          break;
        case "title":
        default:
          comparison = compareText(a.title, b.title);
          break;
      }
      return sortDir === "desc" ? comparison * -1 : comparison;
    });

  const totalProductPages = Math.max(1, Math.ceil(filteredProducts.length / perPage));
  const productPage = Math.min(requestedPage, totalProductPages);
  const productPageStart = (productPage - 1) * perPage;
  const paginatedProducts = filteredProducts.slice(productPageStart, productPageStart + perPage);
  const productsBaseQuery = { ...baseQuery, page: productPage };
  const productSortHref = (targetSortBy: ProductSortColumn): string => {
    const nextDir: SortDirection = sortBy === targetSortBy && sortDir === "asc" ? "desc" : "asc";
    return `/admin/products${buildProductsQuery({
      ...productsBaseQuery,
      add: "",
      editProduct: "",
      sortBy: targetSortBy,
      sortDir: nextDir,
      page: 1,
    })}`;
  };
  const productPrevLink = `/admin/products${buildProductsQuery({
    ...productsBaseQuery,
    add: "",
    editProduct: "",
    page: Math.max(1, productPage - 1),
  })}`;
  const productNextLink = `/admin/products${buildProductsQuery({
    ...productsBaseQuery,
    add: "",
    editProduct: "",
    page: Math.min(totalProductPages, productPage + 1),
  })}`;

  const selectedProduct = products.find((row) => row.id === selectedProductId) ?? null;
  const editedProduct = products.find((row) => row.id === editProductId) ?? null;

  const selectedProductStocks = stocks
    .filter((stock) => !selectedProduct || stock.product_id === selectedProduct.id)
    .sort((a, b) => a.location_name.localeCompare(b.location_name, "fr"));

  const clientOptions = clients
    .filter((row) => row.role === "client" && row.client_status !== "ARCHIVED")
    .map((row) => ({
      id: row.id,
      label: `${`${row.first_name ?? ""} ${row.last_name ?? ""}`.trim() || row.email} (${row.client_kind === "CHILD" ? uiText(language, "client.child") : uiText(language, "client.adult")})`,
    }))
    .sort((a, b) => a.label.localeCompare(b.label, "fr"));

  const requestsByLocation = requests
    .filter((row) => activeCatalogRequestIds.has(row.id))
    .filter((row) => !selectedProduct || row.product_id === selectedProduct.id)
    .reduce<
      Array<{ key: string; locationName: string; productTitle: string; quantity: number; estimatedStock: number | null; status: string }>
    >((acc, row) => {
      const key = `${row.location_id}-${row.product_id}-${row.status}`;
      const found = acc.find((item) => item.key === key);
      if (found) {
        found.quantity += row.quantity;
        return acc;
      }
      acc.push({
        key,
        locationName: row.location_name,
        productTitle: row.product_title,
        quantity: row.quantity,
        estimatedStock: row.stock_estimated_quantity,
        status: row.status,
      });
      return acc;
    }, [])
    .sort((a, b) => a.locationName.localeCompare(b.locationName, "fr") || a.productTitle.localeCompare(b.productTitle, "fr"));

  const entryItems = entriesPage.items;
  const entryTotalPages = Math.max(1, Math.ceil(entriesPage.total / Math.max(entriesPage.page_size || 1, 1)));
  const selectedEntry = entryItems.find((row) => row.id === entryId) ?? null;
  const entryPrevLink = `/admin/products${buildProductsQuery({
    ...baseQuery,
    add: "",
    editProduct: "",
    entryPage: String(Math.max(1, entryPage - 1)),
  })}`;
  const entryNextLink = `/admin/products${buildProductsQuery({
    ...baseQuery,
    add: "",
    editProduct: "",
    entryPage: String(Math.min(entryTotalPages, entryPage + 1)),
  })}`;

  return (
    <section className="admin-page-grid">
      <section className="card catalog-admin-hero">
        <div className="catalog-admin-hero-main">
          <div>
            <h2>{t("admin.products.title")}</h2>
            <p className="muted">{t("admin.products.subtitle")}</p>
          </div>
          <div className="row wrap gap-xs">
            <Link className="mode-link" href="/admin/partition-distribution">Distribution des partitions — Paris</Link>
            <Link className="ghost" href={addLink}>
              {t("admin.products.add_product")}
            </Link>
            <Link className="mode-link" href="/admin/config/catalog">
              {t("admin.products.configure_categories_kits")}
            </Link>
          </div>
        </div>
        <div className="catalog-admin-hub-grid">
          <Link className="catalog-admin-hub-card" href={`/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "", view: "products" })}`}>
            <strong>{t("admin.products.tab_products")}</strong>
            <span>{t("admin.products.hub_products_desc")}</span>
          </Link>
          <Link className="catalog-admin-hub-card" href="/admin/config/catalog?tab=categories">
            <strong>{t("admin.catalog.categories_title")}</strong>
            <span>{t("admin.products.hub_categories_desc")}</span>
          </Link>
          <Link className="catalog-admin-hub-card" href="/admin/config/catalog?tab=kits">
            <strong>{t("admin.catalog.kits_title")}</strong>
            <span>{t("admin.products.hub_kits_desc")}</span>
          </Link>
        </div>
      </section>

      <section className="card">
        <div className="row wrap gap-xs catalog-tabs-scroll">
          <Link className={currentView === "products" ? "mode-link" : "ghost"} href={`/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "", view: "products" })}`}>
            {t("admin.products.tab_products")}
          </Link>
          <Link className={currentView === "reorder" ? "mode-link" : "ghost"} href={`/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "", view: "reorder" })}`}>
            {t("admin.products.tab_reorder")}
          </Link>
          <Link className={currentView === "entries" ? "mode-link" : "ghost"} href={`/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "", view: "entries" })}`}>
            {t("admin.products.tab_entries")}
          </Link>
          <Link className={currentView === "transfers" ? "mode-link" : "ghost"} href={`/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "", view: "transfers" })}`}>
            {t("admin.products.tab_transfers")}
          </Link>
          <Link className={currentView === "requests" ? "mode-link" : "ghost"} href={`/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "", view: "requests" })}`}>
            {t("admin.products.tab_requests")}
          </Link>
        </div>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

      {loadErrors.length > 0 ? (
        <section className="card">
          <h3>{t("admin.products.load_errors")}</h3>
          <ul className="config-error-list">
            {loadErrors.map((message) => (
              <li key={message} className="flash-err">
                {message}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="card">
        <div className="config-metric-grid">
          <article>
            <span>{t("admin.config.metrics.total")}</span>
            <strong>{productStats.total}</strong>
          </article>
          <article>
            <span>{t("common.active")}</span>
            <strong>{productStats.active}</strong>
          </article>
          <article>
            <span>{t("admin.products.metrics_virtual")}</span>
            <strong>{productStats.virtual}</strong>
          </article>
          <article className={productStats.lowStock > 0 ? "is-warning" : ""}>
            <span>{t("admin.products.metrics_low_stock")}</span>
            <strong>{productStats.lowStock}</strong>
          </article>
          <article className={productStats.activeRequests > 0 ? "is-warning" : ""}>
            <span>{t("admin.products.metrics_active_requests")}</span>
            <strong>{productStats.activeRequests}</strong>
          </article>
        </div>
      </section>

      {currentView === "products" ? (
        <>
          <section className="card">
            <div className="row spread">
              <h3>{t("admin.products.section_products")}</h3>
              <div className="row">
                <Link className="ghost" href={addLink}>
                  {t("admin.products.add_product")}
                </Link>
                <Link className="mode-link" href="/admin/config/catalog">
                  {t("admin.products.configure_categories_kits")}
                </Link>
              </div>
            </div>

            <form method="get" className="grid cols-5 config-form-grid top-gap-sm">
              <input type="hidden" name="view" value="products" />
              <input type="hidden" name="product" value={selectedProductId} />
              <input type="hidden" name="sort_by" value={sortBy} />
              <input type="hidden" name="sort_dir" value={sortDir} />
              <input type="hidden" name="page" value="1" />
              <label className="span-2">
                {t("admin.products.free_search")}
                <input type="search" name="q" defaultValue={query} placeholder={t("admin.products.search_placeholder")} />
              </label>
              <label>
                {uiText(language, "common.category")}
                <select name="category" defaultValue={category}>
                  <option value="">{t("common.all")}</option>
                  {categories.map((categoryRow) => (
                    <option key={categoryRow.id} value={categoryRow.id}>
                      {categoryRow.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {uiText(language, "common.status")}
                <select name="status" defaultValue={status}>
                  <option value="all">{t("common.all")}</option>
                  <option value="active">{t("common.active")}</option>
                  <option value="inactive">{t("common.inactive")}</option>
                </select>
              </label>
              <label>
                {uiText(language, "common.visibility")}
                <select name="visibility" defaultValue={visibility}>
                  <option value="all">{t("common.all")}</option>
                  <option value="public">{t("common.public")}</option>
                  <option value="private">{t("common.private")}</option>
                </select>
              </label>
              <label>
                {t("admin.products.online_purchase")}
                <select name="online" defaultValue={online}>
                  <option value="all">{t("common.all")}</option>
                  <option value="online">{t("common.yes")}</option>
                  <option value="offline">{t("common.no")}</option>
                </select>
              </label>
              <label>
                {t("admin.products.products_per_page")}
                <select name="per_page" defaultValue={String(perPage)}>
                  <option value="25">25</option>
                  <option value="50">50</option>
                  <option value="100">100</option>
                </select>
              </label>
              <div className="row span-5">
                <button type="submit">{t("common.apply")}</button>
                <Link
                  className="ghost"
                  href={`/admin/products${buildProductsQuery({
                    ...productsBaseQuery,
                    q: "",
                    category: "",
                    status: "all",
                    visibility: "all",
                    online: "all",
                    add: "",
                    editProduct: "",
                    product: "",
                    sortBy: "title",
                    sortDir: "asc",
                    page: 1,
                  })}`}
                >
                  {t("common.reset")}
                </Link>
                <span className="badge">{t("admin.products.products_count", { count: filteredProducts.length })}</span>
                <span className="badge">
                  {t("admin.products.page_badge", { page: productPage, total: totalProductPages })}
                </span>
              </div>
            </form>

            <div className="table-wrap catalog-desktop-table top-gap-sm">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>
                      <Link className="sort-link" href={productSortHref("title")}>
                        {t("common.product")} {productSortIndicator(sortBy, sortDir, "title")}
                      </Link>
                    </th>
                    <th>
                      <Link className="sort-link" href={productSortHref("category")}>
                        {t("common.category")} {productSortIndicator(sortBy, sortDir, "category")}
                      </Link>
                    </th>
                    <th>
                      <Link className="sort-link" href={productSortHref("location")}>
                        {t("admin.products.main_location")} {productSortIndicator(sortBy, sortDir, "location")}
                      </Link>
                    </th>
                    <th>
                      <Link className="sort-link" href={productSortHref("price")}>
                        {t("admin.products.column_price_ttc")} {productSortIndicator(sortBy, sortDir, "price")}
                      </Link>
                    </th>
                    <th>
                      <Link className="sort-link" href={productSortHref("stock_global")}>
                        {t("admin.products.column_global_stock")} {productSortIndicator(sortBy, sortDir, "stock_global")}
                      </Link>
                    </th>
                    <th>
                      <Link className="sort-link" href={productSortHref("stock_reserve")}>
                        {t("admin.products.column_reserve_stock")} {productSortIndicator(sortBy, sortDir, "stock_reserve")}
                      </Link>
                    </th>
                    <th>
                      <Link className="sort-link" href={productSortHref("reorder")}>
                        {t("admin.products.column_reorder_needed")} {productSortIndicator(sortBy, sortDir, "reorder")}
                      </Link>
                    </th>
                    <th>
                      <Link className="sort-link" href={productSortHref("active")}>
                        {t("common.active")} {productSortIndicator(sortBy, sortDir, "active")}
                      </Link>
                    </th>
                    <th>{t("common.actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredProducts.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="muted">
                        {t("admin.products.no_products")}
                      </td>
                    </tr>
                  ) : (
                    paginatedProducts.map((product) => {
                      const needsAlert = !product.is_virtual && product.stock_global_quantity < product.reserve_stock;
                      const selectLink = `/admin/products${buildProductsQuery({ ...productsBaseQuery, add: "", editProduct: "", product: product.id })}`;
                      const editLink = `/admin/products${buildProductsQuery({ ...productsBaseQuery, add: "", editProduct: product.id, product: selectedProductId || product.id })}`;
                      return (
                        <tr key={product.id} className={selectedProduct?.id === product.id ? "catalog-selected-row" : ""}>
                          <td>
                            <div className="catalog-product-cell">
                              <ProductThumbnail product={product} />
                              <div className="catalog-product-copy">
                                <Link href={selectLink} className="mode-link">
                                  {product.title}
                                </Link>
                                {product.is_virtual ? <p className="muted">{t("admin.products.virtual_product")}</p> : null}
                                {product.barcode ? <p className="muted">{t("admin.products.barcode")}: {product.barcode}</p> : null}
                              </div>
                            </div>
                          </td>
                          <td>{product.category_name || "-"}</td>
                          <td>{product.primary_location_name || "-"}</td>
                          <td>{formatMoney(product.price_incl_vat, "EUR", language)}</td>
                          <td>{product.is_virtual ? "-" : product.stock_global_quantity}</td>
                          <td>{product.is_virtual ? "-" : product.reserve_stock}</td>
                          <td>{product.is_virtual ? t("admin.products.not_applicable") : needsAlert ? t("common.yes") : t("common.no")}</td>
                          <td>{yesNoLabel(product.active, language)}</td>
                          <td>
                            <AdminProductActionsMenu
                              editHref={editLink}
                              productId={product.id}
                              returnTo={returnTo}
                              deleteAction={deleteAdminCatalogProductAction}
                              language={language}
                            />
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
            <div className="catalog-mobile-cards top-gap-sm">
              {paginatedProducts.map((product) => {
                const selectLink = `/admin/products${buildProductsQuery({ ...productsBaseQuery, add: "", editProduct: "", product: product.id })}`;
                const editLink = `/admin/products${buildProductsQuery({ ...productsBaseQuery, add: "", editProduct: product.id, product: selectedProductId || product.id })}`;
                return (
                  <article key={`product-mobile-${product.id}`} className="catalog-mobile-card">
                    <div className="catalog-product-cell">
                      <ProductThumbnail product={product} size="mobile" />
                      <div className="catalog-product-copy">
                        <p className="catalog-mobile-title">{product.title}</p>
                        <p className="muted">
                          {product.category_name || t("admin.products.no_category")} · {formatMoney(product.price_incl_vat, "EUR", language)}
                        </p>
                        <p className="muted">
                          {product.is_virtual
                            ? t("admin.products.virtual_product")
                            : t("admin.products.stock_summary", {
                                stock: product.stock_global_quantity,
                                reserve: product.reserve_stock,
                              })}
                        </p>
                      </div>
                    </div>
                    <div className="row wrap gap-xs top-gap-sm">
                      <Link className="ghost" href={selectLink}>
                        {t("admin.products.view_stock")}
                      </Link>
                      <Link className="ghost" href={editLink}>
                        {t("common.edit")}
                      </Link>
                    </div>
                  </article>
                );
              })}
            </div>
            {filteredProducts.length > 0 ? (
              <div className="row spread clients-pagination top-gap-sm">
                <small className="muted">
                  {t("admin.products.pagination_summary", {
                    start: productPageStart + 1,
                    end: Math.min(productPageStart + paginatedProducts.length, filteredProducts.length),
                    total: filteredProducts.length,
                  })}
                </small>
                <div className="row">
                  {productPage > 1 ? (
                    <Link className="mode-link" href={productPrevLink}>
                      ← {t("common.previous")}
                    </Link>
                  ) : (
                    <span className="mode-link disabled-link">← {t("common.previous")}</span>
                  )}
                  <span className="badge">
                    {t("admin.products.page_badge", { page: productPage, total: totalProductPages })}
                  </span>
                  {productPage < totalProductPages ? (
                    <Link className="mode-link" href={productNextLink}>
                      {t("common.next")} →
                    </Link>
                  ) : (
                    <span className="mode-link disabled-link">{t("common.next")} →</span>
                  )}
                </div>
              </div>
            ) : null}
          </section>

          <section className="card">
            <details>
              <summary>{t("admin.products.stocks_by_location", { count: selectedProductStocks.length })}</summary>
              {selectedProduct ? (
                <p className="top-gap-sm">
                  <Link className="ghost" href={clearSelectedProductLink}>
                    {t("admin.products.clear_selected_product")}
                  </Link>
                </p>
              ) : null}
              {!selectedProduct ? (
                <p className="muted">{t("admin.products.choose_product_stock")}</p>
              ) : selectedProduct.is_virtual ? (
                <p className="muted">{t("admin.products.virtual_no_location_stock")}</p>
              ) : selectedProductStocks.length === 0 ? (
                <p className="muted">{t("admin.products.no_initialized_stock")}</p>
              ) : (
                <>
                  <p className="muted">
                    {t("admin.products.selected_product_summary", {
                      title: selectedProduct.title,
                      count: selectedProduct.stock_global_quantity,
                    })}
                  </p>
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>{t("common.location")}</th>
                          <th>{t("admin.products.column_inventory")}</th>
                          <th>{t("admin.products.column_inventory_date")}</th>
                          <th>{t("admin.products.column_real_stock")}</th>
                          <th>{t("admin.products.column_estimated_stock")}</th>
                          <th>{t("admin.products.column_inventory_update")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedProductStocks.map((stock) => (
                          <tr
                            key={`${stock.product_id}-${stock.location_id}`}
                            className={stock.real_quantity < 0 || stock.estimated_quantity < 0 ? "catalog-stock-negative" : ""}
                          >
                            <td>{stock.location_name}</td>
                            <td>{stock.inventory_quantity}</td>
                            <td>{stock.inventory_date || "-"}</td>
                            <td>{stock.real_quantity}</td>
                            <td>{stock.estimated_quantity}</td>
                            <td>
                              <form action={updateAdminCatalogInventoryAction} className="catalog-stock-form">
                                <input type="hidden" name="product_id" value={stock.product_id} />
                                <input type="hidden" name="location_id" value={stock.location_id} />
                                <input type="hidden" name="return_to" value={returnTo} />
                                <input type="number" name="inventory_quantity" min={0} step={1} defaultValue={stock.inventory_quantity} required />
                                <input type="date" name="inventory_date" defaultValue={dateInputValue(stock.inventory_date)} />
                                <button type="submit">{t("admin.products.reset_inventory")}</button>
                              </form>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </details>
          </section>

          <section className="card">
            <details>
              <summary>{t("admin.products.needs_by_location", { count: requestsByLocation.length })}</summary>
              {!selectedProduct ? (
                <p className="muted">{t("admin.products.choose_product_needs")}</p>
              ) : requestsByLocation.length === 0 ? (
                <p className="muted">{t("admin.products.no_current_need")}</p>
              ) : (
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>{t("common.location")}</th>
                        <th>{t("common.product")}</th>
                        <th>{t("common.status")}</th>
                        <th>{t("admin.products.column_requested_quantity")}</th>
                        <th>{t("admin.products.column_estimated_local_stock")}</th>
                        <th>{t("common.warnings")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {requestsByLocation.map((row) => {
                        const shortage = row.estimatedStock !== null ? row.estimatedStock < row.quantity : false;
                        return (
                          <tr key={row.key} className={shortage ? "catalog-stock-negative" : ""}>
                            <td>{row.locationName}</td>
                            <td>{row.productTitle}</td>
                            <td>{catalogRequestStatusLabel(row.status, language)}</td>
                            <td>{row.quantity}</td>
                            <td>{row.estimatedStock ?? "-"}</td>
                            <td>{shortage ? t("admin.products.estimated_stock_insufficient") : "-"}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </details>
          </section>
        </>
      ) : null}

      {currentView === "reorder" ? (
        <>
        <AdminSupplyOrders orders={supplyOrders} products={stockableProducts.filter(p => p.active && p.nature === "material")}
          locations={activeLocations.filter(location => !location.is_online)} submissionId={randomUUID()}
          today={new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Paris", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date())}
          language={language} />
        <section className="card">
          <div className="row spread">
            <h3>{t("admin.products.tab_reorder")}</h3>
            <form method="get" className="row">
              <input type="hidden" name="view" value="reorder" />
              <label>
                {t("common.status")}
                <select name="reorder_status" defaultValue={reorderStatus}>
                  <option value="all">{t("common.all")}</option>
                  <option value="TO_ORDER">{t("admin.products.reorder_status_to_order")}</option>
                  <option value="ORDERED">{t("admin.products.reorder_status_ordered")}</option>
                  <option value="RECEIVED">{t("admin.products.reorder_status_received")}</option>
                  <option value="NORMAL">{t("admin.products.reorder_status_normal")}</option>
                </select>
              </label>
              <button type="submit">{t("common.apply")}</button>
            </form>
          </div>
          <div className="table-wrap catalog-desktop-table top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t("common.product")}</th>
                  <th>{t("common.category")}</th>
                  <th>{t("admin.products.column_global_stock")}</th>
                  <th>{t("admin.products.column_reserve_stock")}</th>
                  <th>{t("admin.products.main_location")}</th>
                  <th>{t("admin.products.reorder_status_label")}</th>
                  <th>{t("admin.products.update_status")}</th>
                </tr>
              </thead>
              <tbody>
                {reorderProducts.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="muted">
                      {t("admin.products.no_reorder")}
                    </td>
                  </tr>
                ) : (
                  reorderProducts.map((product) => (
                    <tr key={product.product_id} className={product.stock_global_quantity < product.reserve_stock ? "catalog-stock-negative" : ""}>
                      <td>{product.title}</td>
                      <td>{product.category_name || "-"}</td>
                      <td>{product.stock_global_quantity}</td>
                      <td>{product.reserve_stock}</td>
                      <td>{product.primary_location_name || "-"}</td>
                      <td>{reorderStatusLabel(product.reorder_status, language)}</td>
                      <td>
                        <form action={updateAdminCatalogReorderStatusAction} className="row wrap gap-xs">
                          <input type="hidden" name="product_id" value={product.product_id} />
                          <input type="hidden" name="return_to" value={returnTo} />
                          <select name="reorder_status" defaultValue={product.reorder_status}>
                            <option value="TO_ORDER">{t("admin.products.reorder_status_to_order")}</option>
                            <option value="ORDERED">{t("admin.products.reorder_status_ordered")}</option>
                            <option value="RECEIVED">{t("admin.products.reorder_status_received")}</option>
                            <option value="NORMAL">{t("admin.products.reorder_status_normal")}</option>
                          </select>
                          <button type="submit">{t("common.save")}</button>
                        </form>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div className="catalog-mobile-cards top-gap-sm">
            {reorderProducts.map((product) => (
              <article key={`reorder-mobile-${product.product_id}`} className="catalog-mobile-card">
                <p className="catalog-mobile-title">{product.title}</p>
                <p className="muted">
                  {product.category_name || t("admin.products.no_category")} · {product.primary_location_name || t("admin.products.no_location")}
                </p>
                <p className="muted">
                  {t("admin.products.stock_summary", { stock: product.stock_global_quantity, reserve: product.reserve_stock })}
                </p>
                <form action={updateAdminCatalogReorderStatusAction} className="row wrap gap-xs top-gap-sm">
                  <input type="hidden" name="product_id" value={product.product_id} />
                  <input type="hidden" name="return_to" value={returnTo} />
                  <select name="reorder_status" defaultValue={product.reorder_status}>
                    <option value="TO_ORDER">{t("admin.products.reorder_status_to_order")}</option>
                    <option value="ORDERED">{t("admin.products.reorder_status_ordered")}</option>
                    <option value="RECEIVED">{t("admin.products.reorder_status_received")}</option>
                    <option value="NORMAL">{t("admin.products.reorder_status_normal")}</option>
                  </select>
                  <button type="submit">{t("admin.products.mobile_update_status")}</button>
                </form>
              </article>
            ))}
          </div>
        </section>
        </>
      ) : null}

      {currentView === "entries" ? (
        <>
          <section className="card">
            <div className="row spread">
              <h3>{t("admin.products.new_stock_entry")}</h3>
              <span className="badge">{t("admin.products.movements_count", { count: entriesPage.total })}</span>
            </div>
            <form action={createAdminStockEntryAction} className="grid cols-2 config-form-grid catalog-entry-form top-gap-sm">
              <input type="hidden" name="return_to" value={returnTo} />
              <label>
                {t("common.product")}
                <select name="product_id" required defaultValue={entryProduct || selectedProduct?.id || ""}>
                  <option value="">{t("admin.products.select_product")}</option>
                  {stockableProducts.map((product) => (
                    <option key={product.id} value={product.id}>
                      {product.title}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("common.location")}
                <select name="location_id" required defaultValue={entryLocation || selectedProduct?.primary_location_id || ""}>
                  <option value="">{t("admin.products.select_location")}</option>
                  {activeLocations.map((location) => (
                    <option key={location.id} value={location.id}>
                      {location.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("common.quantity")}
                <input type="number" name="quantity" min={1} step={1} defaultValue={1} required />
              </label>
              <label>
                {t("common.date")}
                <input type="date" name="occurred_at" defaultValue={new Date().toISOString().slice(0, 10)} />
              </label>
              <label>
                {t("common.source")}
                <select name="source_type" defaultValue="delivery">
                  <option value="delivery">{t("admin.products.movement_source_delivery")}</option>
                  <option value="purchase">{t("admin.products.movement_source_purchase")}</option>
                  <option value="return">{t("admin.products.movement_source_return")}</option>
                  <option value="correction">{t("admin.products.movement_source_correction")}</option>
                  <option value="other">{t("admin.products.movement_source_other")}</option>
                </select>
              </label>
              <label>
                {t("admin.products.reference_optional")}
                <input type="text" name="source_reference" maxLength={255} />
              </label>
              <label className="span-2">
                {t("admin.products.note_optional")}
                <textarea name="note" rows={2} maxLength={2000} />
              </label>
              <div className="row span-2">
                <button type="submit">{t("admin.products.save_stock_entry")}</button>
              </div>
            </form>
            <details className="top-gap-sm">
              <summary className="mode-link">{t("admin.products.inventory_adjustment")}</summary>
              <form action={createAdminStockAdjustmentAction} className="grid cols-2 config-form-grid top-gap-sm">
                <input type="hidden" name="return_to" value={returnTo} />
                <label>
                  {t("common.product")}
                  <select name="adjust_product_id" required defaultValue={entryProduct || selectedProduct?.id || ""}>
                    <option value="">{t("admin.products.select_product")}</option>
                    {stockableProducts.map((product) => (
                      <option key={product.id} value={product.id}>
                        {product.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("common.location")}
                  <select name="adjust_location_id" required defaultValue={entryLocation || selectedProduct?.primary_location_id || ""}>
                    <option value="">{t("admin.products.select_location")}</option>
                    {activeLocations.map((location) => (
                      <option key={location.id} value={location.id}>
                        {location.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("admin.products.delta_quantity")}
                  <input type="number" name="adjust_quantity" step={1} defaultValue={0} required />
                </label>
                <label>
                  {t("common.date")}
                  <input type="date" name="adjust_occurred_at" defaultValue={new Date().toISOString().slice(0, 10)} />
                </label>
                <label>
                  {t("admin.products.reason")}
                  <select name="adjust_source_type" defaultValue="correction">
                    <option value="correction">{t("admin.products.movement_source_correction")}</option>
                    <option value="return">{t("admin.products.movement_source_return")}</option>
                    <option value="other">{t("admin.products.movement_source_other")}</option>
                  </select>
                </label>
                <label>
                  {t("admin.products.reference_optional")}
                  <input type="text" name="adjust_source_reference" maxLength={255} />
                </label>
                <label className="span-2">
                  {t("admin.products.note_optional")}
                  <textarea name="adjust_note" rows={2} maxLength={2000} />
                </label>
                <div className="row span-2">
                  <button type="submit" className="ghost">
                    {t("admin.products.save_adjustment")}
                  </button>
                </div>
              </form>
            </details>
          </section>

          <section className="card">
            <div className="row spread">
              <h3>{t("admin.products.entries_history")}</h3>
              <form method="get" className="row wrap gap-xs">
                <input type="hidden" name="view" value="entries" />
                <label>
                  {t("common.product")}
                  <select name="entry_product" defaultValue={entryProduct}>
                    <option value="">{t("common.all")}</option>
                    {stockableProducts.map((product) => (
                      <option key={product.id} value={product.id}>
                        {product.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("common.location")}
                  <select name="entry_location" defaultValue={entryLocation}>
                    <option value="">{t("common.all")}</option>
                    {activeLocations.map((location) => (
                      <option key={location.id} value={location.id}>
                        {location.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("common.search")}
                  <input type="search" name="entry_q" defaultValue={entryQuery} placeholder={t("admin.products.entry_search_placeholder")} />
                </label>
                <button type="submit">{t("common.apply")}</button>
              </form>
            </div>
            <div className="table-wrap catalog-desktop-table top-gap-sm">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t("common.date")}</th>
                    <th>{t("common.product")}</th>
                    <th>{t("common.location")}</th>
                    <th>{t("admin.products.quantity_short_header")}</th>
                    <th>{t("common.type")}</th>
                    <th>{t("common.source")}</th>
                    <th>{t("admin.products.reference")}</th>
                    <th>{t("admin.products.created_by")}</th>
                    <th>{t("common.actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {entryItems.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="muted">
                        {t("admin.products.no_entries")}
                      </td>
                    </tr>
                  ) : (
                    entryItems.map((entry) => {
                      const qty = Number(entry.quantity);
                      const detailLink = `/admin/products${buildProductsQuery({
                        ...baseQuery,
                        add: "",
                        editProduct: "",
                        entryId: entry.id,
                      })}`;
                      return (
                        <tr key={entry.id}>
                          <td>{formatDateTime(entry.occurred_at, language)}</td>
                          <td>{entry.product_title}</td>
                          <td>{entry.location_name}</td>
                          <td>{qty >= 0 ? `+${qty}` : qty}</td>
                          <td>{stockMovementTypeLabel(entry.movement_type, language)}</td>
                          <td>{stockMovementSourceTypeLabel(entry.source_type, language)}</td>
                          <td>{entry.source_reference || "-"}</td>
                          <td>{entry.created_by_name || "-"}</td>
                          <td>
                            <Link className="ghost" href={detailLink}>
                              {t("common.details")}
                            </Link>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
            <div className="catalog-mobile-cards top-gap-sm">
              {entryItems.map((entry) => {
                const qty = Number(entry.quantity);
                const detailLink = `/admin/products${buildProductsQuery({
                  ...baseQuery,
                  add: "",
                  editProduct: "",
                  entryId: entry.id,
                })}`;
                return (
                  <article key={`mobile-${entry.id}`} className="catalog-mobile-card">
                    <p className="catalog-mobile-title">{entry.product_title}</p>
                    <p className="muted">
                      {formatDateTime(entry.occurred_at, language)} · {entry.location_name}
                    </p>
                    <p className="muted">
                      {stockMovementTypeLabel(entry.movement_type, language)} · {stockMovementSourceTypeLabel(entry.source_type, language)}
                    </p>
                    <div className="row spread">
                      <strong>{qty >= 0 ? `+${qty}` : qty}</strong>
                      <Link className="ghost" href={detailLink}>
                        {t("common.details")}
                      </Link>
                    </div>
                  </article>
                );
              })}
            </div>
            <div className="row spread top-gap-sm">
              <span className="muted">
                {t("admin.products.page_fraction", { page: entryPage, total: entryTotalPages })}
              </span>
              <div className="row gap-xs">
                {entryPage > 1 ? (
                  <Link className="ghost" href={entryPrevLink}>
                    {t("common.previous")}
                  </Link>
                ) : null}
                {entryPage < entryTotalPages ? (
                  <Link className="ghost" href={entryNextLink}>
                    {t("common.next")}
                  </Link>
                ) : null}
              </div>
            </div>
          </section>
        </>
      ) : null}

      {currentView === "transfers" ? (
        <>
          <section className="card">
            <h3>{t("admin.products.new_transfer")}</h3>
            <form action={createAdminCatalogTransferAction} className="grid cols-4 config-form-grid">
              <input type="hidden" name="return_to" value={returnTo} />
              <label>
                {t("common.product")}
                <select name="product_id" defaultValue={selectedProduct?.id ?? ""} required>
                  <option value="">{t("admin.products.select_product")}</option>
                  {stockableProducts.map((product) => (
                    <option key={product.id} value={product.id}>
                      {product.title}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("admin.products.source_location")}
                <select name="source_location_id" defaultValue={selectedProduct?.primary_location_id ?? ""} required>
                  <option value="">{t("admin.products.select_source_location")}</option>
                  {activeLocations.map((location) => (
                    <option key={location.id} value={location.id}>
                      {location.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("admin.products.target_location")}
                <select name="target_location_id" defaultValue="" required>
                  <option value="">{t("admin.products.select_target_location")}</option>
                  {activeLocations.map((location) => (
                    <option key={location.id} value={location.id}>
                      {location.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("common.quantity")}
                <input type="number" name="quantity" min={1} step={1} defaultValue={1} required />
              </label>
              <label>
                {t("admin.products.planned_date")}
                <input type="date" name="planned_transfer_date" />
              </label>
              <label>
                {t("admin.products.assignee")}
                <select name="assigned_to_user_id" defaultValue="">
                  <option value="">{t("admin.products.no_assignee")}</option>
                  {clients.map((client) => (
                    <option key={client.id} value={client.id}>
                      {`${client.first_name ?? ""} ${client.last_name ?? ""}`.trim() || client.email}
                    </option>
                  ))}
                </select>
              </label>
              <label className="span-2">
                {t("admin.products.note")}
                <input type="text" name="note" maxLength={2000} />
              </label>
              <div className="row span-4">
                <button type="submit">{t("admin.products.create_transfer")}</button>
              </div>
            </form>
          </section>

          <section className="card">
            <div className="row spread">
              <h3>{t("admin.products.transfer_tracking")}</h3>
              <form method="get" className="row">
                <input type="hidden" name="view" value="transfers" />
                <label>
                  {t("common.status")}
                  <select name="transfer_status" defaultValue={transferStatus}>
                    <option value="all">{t("common.all")}</option>
                    <option value="PENDING">{t("admin.products.transfer_status_pending")}</option>
                    <option value="DONE">{t("admin.products.transfer_status_done")}</option>
                    <option value="CANCELLED">{t("admin.products.transfer_status_cancelled")}</option>
                  </select>
                </label>
                <button type="submit">{t("common.apply")}</button>
              </form>
            </div>
            <div className="table-wrap catalog-desktop-table top-gap-sm">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t("admin.products.column_created_at")}</th>
                    <th>{t("common.product")}</th>
                    <th>{t("admin.products.column_route")}</th>
                    <th>{t("admin.products.quantity_short_header")}</th>
                    <th>{t("admin.products.column_planned_date")}</th>
                    <th>{t("admin.products.column_assignee")}</th>
                    <th>{t("common.status")}</th>
                    <th>{t("admin.products.column_action")}</th>
                  </tr>
                </thead>
                <tbody>
                  {transfers.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="muted">
                        {t("admin.products.no_transfers")}
                      </td>
                    </tr>
                  ) : (
                    transfers.map((transfer) => (
                      <tr key={transfer.id}>
                        <td>{formatDateTime(transfer.created_at, language)}</td>
                        <td>{transfer.product_title}</td>
                        <td>
                          {transfer.source_location_name} {"->"} {transfer.target_location_name}
                        </td>
                        <td>{transfer.quantity}</td>
                        <td>{transfer.planned_transfer_date || "-"}</td>
                        <td>{transfer.assigned_to_name || "-"}</td>
                        <td>
                          {transferStatusLabel(transfer.status, language)}
                          {transfer.completed_transfer_date ? <div className="muted">{t("admin.products.transfer_completed_on", { date: transfer.completed_transfer_date })}</div> : null}
                        </td>
                        <td>
                          {transfer.status === "PENDING" ? (
                            <div className="catalog-request-actions">
                              <form action={completeAdminCatalogTransferAction} className="row wrap gap-xs">
                                <input type="hidden" name="transfer_id" value={transfer.id} />
                                <input type="hidden" name="return_to" value={returnTo} />
                                <input type="date" name="completed_transfer_date" defaultValue={dateInputValue(transfer.planned_transfer_date)} />
                                <input type="text" name="note" maxLength={2000} placeholder={t("admin.products.completion_note_placeholder")} />
                                <button type="submit">{t("admin.products.mark_done")}</button>
                              </form>
                              <form action={cancelAdminCatalogTransferAction} className="row wrap gap-xs">
                                <input type="hidden" name="transfer_id" value={transfer.id} />
                                <input type="hidden" name="return_to" value={returnTo} />
                                <input type="text" name="note" maxLength={2000} placeholder={t("admin.products.cancel_reason_placeholder")} />
                                <button type="submit" className="danger ghost">
                                  {t("common.cancel")}
                                </button>
                              </form>
                            </div>
                          ) : (
                            <span className="muted">{t("admin.products.no_action")}</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <div className="catalog-mobile-cards top-gap-sm">
              {transfers.map((transfer) => (
                <article key={`transfer-mobile-${transfer.id}`} className="catalog-mobile-card">
                  <p className="catalog-mobile-title">{transfer.product_title}</p>
                  <p className="muted">
                    {transfer.source_location_name} {"->"} {transfer.target_location_name}
                  </p>
                  <p className="muted">
                    {t("admin.products.quantity_short", { quantity: transfer.quantity })} · {transferStatusLabel(transfer.status, language)}
                  </p>
                  {transfer.status === "PENDING" ? (
                    <div className="catalog-request-actions">
                      <form action={completeAdminCatalogTransferAction} className="row wrap gap-xs">
                        <input type="hidden" name="transfer_id" value={transfer.id} />
                        <input type="hidden" name="return_to" value={returnTo} />
                        <input type="date" name="completed_transfer_date" defaultValue={dateInputValue(transfer.planned_transfer_date)} />
                        <button type="submit">{t("admin.products.mark_done")}</button>
                      </form>
                      <form action={cancelAdminCatalogTransferAction} className="row wrap gap-xs">
                        <input type="hidden" name="transfer_id" value={transfer.id} />
                        <input type="hidden" name="return_to" value={returnTo} />
                        <input type="text" name="note" maxLength={2000} placeholder={t("admin.products.cancel_reason_placeholder")} />
                        <button type="submit" className="danger ghost">
                          {t("common.cancel")}
                        </button>
                      </form>
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          </section>
        </>
      ) : null}

      {currentView === "requests" ? (
        <section className="card">
          <h3>{t("admin.products.student_requests")}</h3>
          <p className="muted">{t("admin.products.student_requests_subtitle")}</p>
          <form action={createAdminCatalogRequestAction} className="grid cols-4 config-form-grid">
            <input type="hidden" name="return_to" value={returnTo} />
            <SearchMultiSelect
              className="span-2"
              label={t("admin.products.student")}
              name="student_user_id"
              options={clientOptions}
              selectedIds={[]}
              placeholder={t("admin.products.search_student")}
              language={language}
              maxSelections={1}
              requiredSelection
              emptySelectionLabel={t("admin.products.select_student")}
              emptySummaryLabel={t("admin.products.select_student")}
            />
            <label>
              {t("common.product")}
              <select name="product_id" required defaultValue={selectedProduct?.id ?? ""}>
                <option value="">{t("admin.products.select_product")}</option>
                {activeProducts.map((product) => (
                  <option key={product.id} value={product.id}>
                    {product.title}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("common.quantity")}
              <input type="number" name="quantity" min={1} step={1} defaultValue={1} required />
            </label>
            <div className="span-2 catalog-request-auto-location">
              <strong>{t("common.location")}</strong>
              <span className="muted">{t("admin.products.location_from_next_lesson")}</span>
            </div>
            <label className="span-2">
              {t("admin.products.note")}
              <input type="text" name="note" maxLength={2000} />
            </label>
            <label className="checkline">
              <input type="checkbox" name="should_bill" />
              {t("admin.products.bill_item")}
            </label>
            <div className="row span-4">
              <button type="submit">{t("admin.products.add_admin_request")}</button>
            </div>
          </form>

          <div className="table-wrap catalog-desktop-table top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t("common.date")}</th>
                  <th>{t("common.source")}</th>
                  <th>{t("admin.products.student")}</th>
                  <th>{t("admin.products.product_location")}</th>
                  <th>{t("admin.products.quantity_short_header")}</th>
                  <th>{t("common.status")}</th>
                  <th>{t("admin.products.column_billing")}</th>
                  <th>{t("admin.products.column_stock")}</th>
                  <th>{t("common.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {requests.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="muted">
                      {t("admin.products.no_requests")}
                    </td>
                  </tr>
                ) : (
                  requests.map((request) => (
                    <tr key={request.id}>
                      <td>{formatDateTime(request.requested_at, language)}</td>
                      <td>{catalogRequestSourceLabel(request.request_source, language)}</td>
                      <td>{request.student_name}</td>
                      <td>
                        {request.product_title}
                        <br />
                        <small className="muted">{request.location_name}</small>
                        {request.assigned_session_start_at ? (
                          <>
                            <br />
                            <small className="muted">
                              {formatDateTime(request.assigned_session_start_at, language)} · {request.assigned_professor_name || t("admin.products.teacher_to_assign")}
                            </small>
                          </>
                        ) : null}
                        {request.stock_transfer_id ? (
                          <>
                            <br />
                            <small className="muted">{t("admin.products.stock_transfer_in_progress")}</small>
                          </>
                        ) : null}
                      </td>
                      <td>{request.quantity}</td>
                      <td>{catalogRequestStatusLabel(request.status, language)}</td>
                      <td>{request.should_bill === null ? "-" : yesNoLabel(request.should_bill, language)}</td>
                      <td>
                        {t("admin.products.real_stock_label")}: {request.stock_real_quantity ?? "-"}
                        <br />
                        {t("admin.products.estimated_stock_label")}: {request.stock_estimated_quantity ?? "-"}
                        <br />
                        <small className="muted">{t("admin.products.reserved_for_handover", { quantity: request.stock_reserved_quantity })}</small>
                      </td>
                      <td>
                        <div className="catalog-request-actions">
                          {request.status === "PROCESSING" ? (
                            <>
                              <form action={reviewAdminCatalogRequestAction}>
                                <input type="hidden" name="request_id" value={request.id} />
                                <input type="hidden" name="decision" value="ACCEPT" />
                                <input type="hidden" name="return_to" value={returnTo} />
                                <label className="checkline">
                                  <input type="checkbox" name="should_bill" />
                                  {t("admin.products.bill_item")}
                                </label>
                                <input type="text" name="note" maxLength={2000} placeholder={t("admin.products.accept_note_placeholder")} />
                                <button type="submit">{t("admin.products.accept")}</button>
                              </form>
                              <form action={reviewAdminCatalogRequestAction}>
                                <input type="hidden" name="request_id" value={request.id} />
                                <input type="hidden" name="decision" value="REJECT" />
                                <input type="hidden" name="return_to" value={returnTo} />
                                <input type="text" name="note" maxLength={2000} placeholder={t("admin.products.reject_note_placeholder")} />
                                <button type="submit" className="danger ghost">
                                  {t("admin.products.reject")}
                                </button>
                              </form>
                            </>
                          ) : null}
                          {(request.status === "TO_DELIVER" || request.status === "INVOICE_TO_SEND") && (
                            <form action={deliverAdminCatalogRequestAction}>
                              <input type="hidden" name="request_id" value={request.id} />
                              <input type="hidden" name="return_to" value={returnTo} />
                              <select name="delivered_by_user_id" defaultValue="">
                                <option value="">{t("admin.products.delivered_by_current_user")}</option>
                                {clients.map((client) => (
                                  <option key={client.id} value={client.id}>
                                    {`${client.first_name ?? ""} ${client.last_name ?? ""}`.trim() || client.email}
                                  </option>
                                ))}
                              </select>
                              <input type="text" name="note" maxLength={2000} placeholder={t("admin.products.delivery_note_placeholder")} />
                              <button type="submit">{t("admin.products.mark_delivered")}</button>
                            </form>
                          )}
                          {request.note ? <small className="muted">{request.note}</small> : null}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div className="catalog-mobile-cards top-gap-sm">
            {requests.map((request) => (
              <article key={`request-mobile-${request.id}`} className="catalog-mobile-card">
                <p className="catalog-mobile-title">{request.product_title}</p>
                <p className="muted">
                  {request.student_name} · {request.location_name}
                </p>
                <p className="muted">
                  {catalogRequestStatusLabel(request.status, language)} · {t("admin.products.quantity_short", { quantity: request.quantity })}
                </p>
                {request.assigned_session_start_at ? (
                  <p className="muted">
                    {formatDateTime(request.assigned_session_start_at, language)} · {request.assigned_professor_name || t("admin.products.teacher_to_assign")}
                  </p>
                ) : null}
                <div className="catalog-request-actions">
                  {request.status === "PROCESSING" ? (
                    <>
                      <form action={reviewAdminCatalogRequestAction} className="row wrap gap-xs">
                        <input type="hidden" name="request_id" value={request.id} />
                        <input type="hidden" name="decision" value="ACCEPT" />
                        <input type="hidden" name="return_to" value={returnTo} />
                        <label className="checkline">
                          <input type="checkbox" name="should_bill" />
                          {t("admin.products.bill_item")}
                        </label>
                        <button type="submit">{t("admin.products.accept")}</button>
                      </form>
                      <form action={reviewAdminCatalogRequestAction} className="row wrap gap-xs">
                        <input type="hidden" name="request_id" value={request.id} />
                        <input type="hidden" name="decision" value="REJECT" />
                        <input type="hidden" name="return_to" value={returnTo} />
                        <button type="submit" className="danger ghost">
                          {t("admin.products.reject")}
                        </button>
                      </form>
                    </>
                  ) : null}
                  {(request.status === "TO_DELIVER" || request.status === "INVOICE_TO_SEND") ? (
                    <form action={deliverAdminCatalogRequestAction} className="row wrap gap-xs">
                      <input type="hidden" name="request_id" value={request.id} />
                      <input type="hidden" name="return_to" value={returnTo} />
                      <button type="submit">{t("admin.products.mark_delivered")}</button>
                    </form>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {selectedEntry ? (
        <section className="modal-overlay" role="dialog" aria-modal="true" aria-label={t("admin.products.entry_details_aria")}>
          <section className="modal-panel modal-day-details">
            <div className="row spread">
              <h3 className="modal-title">{t("admin.products.entry_details_title")}</h3>
              <Link
                className="ghost"
                href={`/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "", entryId: "" })}`}
                aria-label={t("common.close")}
              >
                {t("common.close")}
              </Link>
            </div>
            <section className="modal-card">
              <div className="grid cols-2 config-form-grid">
                <p>
                  <strong>{t("common.product")}:</strong> {selectedEntry.product_title}
                </p>
                <p>
                  <strong>{t("common.location")}:</strong> {selectedEntry.location_name}
                </p>
                <p>
                  <strong>{t("common.date")}:</strong> {formatDateTime(selectedEntry.occurred_at, language)}
                </p>
                <p>
                  <strong>{t("common.quantity")}:</strong> {Number(selectedEntry.quantity) >= 0 ? "+" : ""}
                  {selectedEntry.quantity}
                </p>
                <p>
                  <strong>{t("common.type")}:</strong> {stockMovementTypeLabel(selectedEntry.movement_type, language)}
                </p>
                <p>
                  <strong>{t("common.source")}:</strong> {stockMovementSourceTypeLabel(selectedEntry.source_type, language)}
                </p>
                <p>
                  <strong>{t("admin.products.reference")}:</strong> {selectedEntry.source_reference || "-"}
                </p>
                <p>
                  <strong>{t("admin.products.created_by")}:</strong> {selectedEntry.created_by_name || "-"}
                </p>
                <p className="span-2">
                  <strong>{t("admin.products.note")}:</strong> {selectedEntry.note || "-"}
                </p>
              </div>
            </section>
          </section>
        </section>
      ) : null}

      {showAddForm ? (
        <AdminProductCreateModal
          categories={activeCategories}
          locations={activeLocations}
          closeHref={closeModalLink}
          returnTo={addFormReturnTo}
          errorMessage={errorMessage}
          createAction={createAdminCatalogProductAction}
          language={language}
        />
      ) : null}

      {editedProduct ? (
        <AdminProductEditModal
          product={editedProduct}
          categories={categories}
          locations={locations}
          closeHref={closeModalLink}
          returnTo={returnTo}
          entriesHref={entriesViewLink}
          transfersHref={transfersViewLink}
          updateAction={updateAdminCatalogProductAction}
          language={language}
        />
      ) : null}
    </section>
  );
}
