import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import AdminProductActionsMenu from "../../../components/admin-product-actions-menu";
import AdminProductEditModal from "../../../components/admin-product-edit-modal";
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
  AdminCatalogProductOut,
  AdminCatalogReorderProductOut,
  AdminCatalogRequestOut,
  AdminCatalogStockOut,
  AdminCatalogStockTransferOut,
  AdminStockMovementListOut,
  AdminClientOut,
  LocationOut,
} from "../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

type ProductsView = "products" | "reorder" | "entries" | "transfers" | "requests";

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

function yesNoLabel(value: boolean): string {
  return value ? "Oui" : "Non";
}

function dateInputValue(value: string | null): string {
  if (!value) {
    return "";
  }
  return value.slice(0, 10);
}

function reorderStatusLabel(status: string): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "TO_ORDER") {
    return "A commander";
  }
  if (normalized === "ORDERED") {
    return "Commande passee";
  }
  if (normalized === "RECEIVED") {
    return "Recu";
  }
  return "Normal";
}

function transferStatusLabel(status: string): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "DONE") {
    return "Fait";
  }
  if (normalized === "CANCELLED") {
    return "Annule";
  }
  return "En attente";
}

function catalogRequestStatusLabel(status: string): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "PROCESSING") {
    return "En cours";
  }
  if (normalized === "REJECTED") {
    return "Refusee";
  }
  if (normalized === "INVOICE_TO_SEND") {
    return "Facture a envoyer";
  }
  if (normalized === "TO_DELIVER") {
    return "A remettre";
  }
  if (normalized === "DELIVERED") {
    return "Remis";
  }
  return normalized || "-";
}

function catalogRequestSourceLabel(source: string): string {
  const normalized = source.trim().toUpperCase();
  if (normalized === "PROFESSOR") {
    return "Professeur";
  }
  if (normalized === "ADMIN") {
    return "Administration";
  }
  return normalized || "-";
}

function stockMovementTypeLabel(movementType: string): string {
  const normalized = movementType.trim().toUpperCase();
  if (normalized === "ADJUSTMENT") {
    return "Correction";
  }
  return "Entree";
}

function stockMovementSourceTypeLabel(sourceType: string): string {
  const normalized = sourceType.trim().toLowerCase();
  if (normalized === "purchase") {
    return "Achat";
  }
  if (normalized === "delivery") {
    return "Livraison";
  }
  if (normalized === "correction") {
    return "Correction";
  }
  if (normalized === "return") {
    return "Retour";
  }
  return "Autre";
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
    redirect("/login?error=Session%20expiree");
  }

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

  const [categoriesResult, productsResult, stocksResult, requestsResult, locationsResult, clientsResult, reorderResult, transfersResult, entriesResult] = await Promise.all([
    backendRequest<AdminCatalogCategoryOut[]>("/api/v1/admin/config/catalog/categories?include_inactive=true", {}, token),
    backendRequest<AdminCatalogProductOut[]>("/api/v1/admin/config/catalog/products?include_inactive=true", {}, token),
    stocksPath ? backendRequest<AdminCatalogStockOut[]>(stocksPath, {}, token) : Promise.resolve({ ok: true as const, data: [] as AdminCatalogStockOut[] }),
    backendRequest<AdminCatalogRequestOut[]>("/api/v1/admin/catalog/requests", {}, token),
    loadLocationsForProducts(token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?limit=1000", {}, token),
    backendRequest<AdminCatalogReorderProductOut[]>(reorderPath, {}, token),
    backendRequest<AdminCatalogStockTransferOut[]>(transfersPath, {}, token),
    backendRequest<AdminStockMovementListOut>(entriesPath, {}, token),
  ]);

  const loadErrors: string[] = [];
  const categories = categoriesResult.ok
    ? categoriesResult.data
    : (() => {
        loadErrors.push(`Categories: ${categoriesResult.message}`);
        return [] as AdminCatalogCategoryOut[];
      })();
  const products = productsResult.ok
    ? productsResult.data
    : (() => {
        loadErrors.push(`Produits: ${productsResult.message}`);
        return [] as AdminCatalogProductOut[];
      })();
  const stocks = stocksResult.ok
    ? stocksResult.data
    : (() => {
        loadErrors.push(`Stocks: ${stocksResult.message}`);
        return [] as AdminCatalogStockOut[];
      })();
  const requests = requestsResult.ok
    ? requestsResult.data
    : (() => {
        loadErrors.push(`Demandes produits: ${requestsResult.message}`);
        return [] as AdminCatalogRequestOut[];
      })();
  const locations = locationsResult.ok
    ? locationsResult.data
    : (() => {
        loadErrors.push(`Lieux: ${locationsResult.message}`);
        return [] as LocationOut[];
      })();
  const clients = clientsResult.ok
    ? clientsResult.data
    : (() => {
        loadErrors.push(`Clients: ${clientsResult.message}`);
        return [] as AdminClientOut[];
      })();
  const reorderProducts = reorderResult.ok
    ? reorderResult.data
    : (() => {
        loadErrors.push(`Produits a commander: ${reorderResult.message}`);
        return [] as AdminCatalogReorderProductOut[];
      })();
  const transfers = transfersResult.ok
    ? transfersResult.data
    : (() => {
        loadErrors.push(`Transferts: ${transfersResult.message}`);
        return [] as AdminCatalogStockTransferOut[];
      })();
  const entriesPage = entriesResult.ok
    ? entriesResult.data
    : (() => {
        loadErrors.push(`Entrees stock: ${entriesResult.message}`);
        return { items: [], total: 0, page: 1, page_size: 20 } as AdminStockMovementListOut;
      })();

  const activeCategories = categories.filter((row) => row.active);
  const activeProducts = products.filter((row) => row.active);
  const stockableProducts = activeProducts.filter((row) => !row.is_virtual);
  const activeLocations = locations.filter((row) => row.active);

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
    .sort((a, b) => a.title.localeCompare(b.title, "fr"));

  const selectedProduct = products.find((row) => row.id === selectedProductId) ?? null;
  const editedProduct = products.find((row) => row.id === editProductId) ?? null;

  const selectedProductStocks = stocks
    .filter((stock) => !selectedProduct || stock.product_id === selectedProduct.id)
    .sort((a, b) => a.location_name.localeCompare(b.location_name, "fr"));

  const clientOptions = clients
    .filter((row) => row.role === "client" && row.client_status !== "ARCHIVED")
    .map((row) => ({
      id: row.id,
      label: `${`${row.first_name ?? ""} ${row.last_name ?? ""}`.trim() || row.email} (${row.client_kind})`,
    }))
    .sort((a, b) => a.label.localeCompare(b.label, "fr"));

  const requestsByLocation = requests
    .filter((row) => row.status === "PROCESSING" || row.status === "INVOICE_TO_SEND" || row.status === "TO_DELIVER")
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
      <section className="card">
        <h2>Gestion des produits</h2>
        <p className="muted">Catalogue, stock par local, transferts et demandes produits eleves.</p>
      </section>

      <section className="card">
        <div className="row wrap gap-xs catalog-tabs-scroll">
          <Link className={currentView === "products" ? "mode-link" : "ghost"} href={`/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "", view: "products" })}`}>
            Produits
          </Link>
          <Link className={currentView === "reorder" ? "mode-link" : "ghost"} href={`/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "", view: "reorder" })}`}>
            Produits a commander
          </Link>
          <Link className={currentView === "entries" ? "mode-link" : "ghost"} href={`/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "", view: "entries" })}`}>
            Entrees stock
          </Link>
          <Link className={currentView === "transfers" ? "mode-link" : "ghost"} href={`/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "", view: "transfers" })}`}>
            Transferts stock
          </Link>
          <Link className={currentView === "requests" ? "mode-link" : "ghost"} href={`/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "", view: "requests" })}`}>
            Demandes eleves
          </Link>
        </div>
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

      {currentView === "products" ? (
        <>
          <section className="card">
            <div className="row spread">
              <h3>Produits</h3>
              <div className="row">
                <Link className="ghost" href={addLink}>
                  Ajouter un produit
                </Link>
                <Link className="mode-link" href="/admin/config?section=products">
                  Configurer categories/kits
                </Link>
              </div>
            </div>

            <form method="get" className="grid cols-5 config-form-grid top-gap-sm">
              <input type="hidden" name="view" value="products" />
              <input type="hidden" name="product" value={selectedProductId} />
              <label className="span-2">
                Recherche libre
                <input type="search" name="q" defaultValue={query} placeholder="Titre, code-barres, categorie..." />
              </label>
              <label>
                Categorie
                <select name="category" defaultValue={category}>
                  <option value="">Toutes</option>
                  {categories.map((categoryRow) => (
                    <option key={categoryRow.id} value={categoryRow.id}>
                      {categoryRow.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Statut
                <select name="status" defaultValue={status}>
                  <option value="all">Tous</option>
                  <option value="active">Actifs</option>
                  <option value="inactive">Inactifs</option>
                </select>
              </label>
              <label>
                Visibilite
                <select name="visibility" defaultValue={visibility}>
                  <option value="all">Toutes</option>
                  <option value="public">Public</option>
                  <option value="private">Prive</option>
                </select>
              </label>
              <label>
                Achat en ligne
                <select name="online" defaultValue={online}>
                  <option value="all">Tous</option>
                  <option value="online">Oui</option>
                  <option value="offline">Non</option>
                </select>
              </label>
              <div className="row span-5">
                <button type="submit">Filtrer</button>
                <Link className="ghost" href={`/admin/products${buildProductsQuery({ ...baseQuery, q: "", category: "", status: "all", visibility: "all", online: "all", add: "", editProduct: "" })}`}>
                  Reinitialiser
                </Link>
                <span className="badge">{filteredProducts.length} produit(s)</span>
              </div>
            </form>

            <div className="table-wrap catalog-desktop-table top-gap-sm">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Produit</th>
                    <th>Categorie</th>
                    <th>Local principal</th>
                    <th>TTC</th>
                    <th>Stock global</th>
                    <th>Stock reserve</th>
                    <th>A commander</th>
                    <th>Actif</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredProducts.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="muted">
                        Aucun produit pour ces filtres.
                      </td>
                    </tr>
                  ) : (
                    filteredProducts.map((product) => {
                      const needsAlert = !product.is_virtual && product.stock_global_quantity < product.reserve_stock;
                      const selectLink = `/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "", product: product.id })}`;
                      const editLink = `/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: product.id, product: selectedProductId || product.id })}`;
                      return (
                        <tr key={product.id} className={selectedProduct?.id === product.id ? "catalog-selected-row" : ""}>
                          <td>
                            <Link href={selectLink} className="mode-link">
                              {product.title}
                            </Link>
                            {product.is_virtual ? <p className="muted">Produit virtuel</p> : null}
                            {product.barcode ? <p className="muted">Code: {product.barcode}</p> : null}
                          </td>
                          <td>{product.category_name || "-"}</td>
                          <td>{product.primary_location_name || "-"}</td>
                          <td>{formatMoney(product.price_incl_vat, "EUR")}</td>
                          <td>{product.is_virtual ? "-" : product.stock_global_quantity}</td>
                          <td>{product.is_virtual ? "-" : product.reserve_stock}</td>
                          <td>{product.is_virtual ? "n/a" : needsAlert ? "Oui" : "Non"}</td>
                          <td>{yesNoLabel(product.active)}</td>
                          <td>
                            <AdminProductActionsMenu
                              editHref={editLink}
                              productId={product.id}
                              returnTo={returnTo}
                              deleteAction={deleteAdminCatalogProductAction}
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
              {filteredProducts.map((product) => {
                const selectLink = `/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "", product: product.id })}`;
                const editLink = `/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: product.id, product: selectedProductId || product.id })}`;
                return (
                  <article key={`product-mobile-${product.id}`} className="catalog-mobile-card">
                    <p className="catalog-mobile-title">{product.title}</p>
                    <p className="muted">
                      {product.category_name || "Sans categorie"} · {formatMoney(product.price_incl_vat, "EUR")}
                    </p>
                    <p className="muted">
                      {product.is_virtual ? "Virtuel" : `Stock ${product.stock_global_quantity} / reserve ${product.reserve_stock}`}
                    </p>
                    <div className="row wrap gap-xs top-gap-sm">
                      <Link className="ghost" href={selectLink}>
                        Voir stock
                      </Link>
                      <Link className="ghost" href={editLink}>
                        Modifier
                      </Link>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="card">
            <details>
              <summary>Stocks par local ({selectedProductStocks.length})</summary>
              {selectedProduct ? (
                <p className="top-gap-sm">
                  <Link className="ghost" href={clearSelectedProductLink}>
                    Retirer la selection produit
                  </Link>
                </p>
              ) : null}
              {!selectedProduct ? (
                <p className="muted">Choisissez un produit dans la liste pour afficher ses stocks par local.</p>
              ) : selectedProduct.is_virtual ? (
                <p className="muted">Produit virtuel: aucune gestion de stock par local.</p>
              ) : selectedProductStocks.length === 0 ? (
                <p className="muted">Aucun stock initialise pour ce produit.</p>
              ) : (
                <>
                  <p className="muted">
                    Produit selectionne: <strong>{selectedProduct.title}</strong> ({selectedProduct.stock_global_quantity} en stock reel global)
                  </p>
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Lieu</th>
                          <th>Inventaire</th>
                          <th>Date inventaire</th>
                          <th>Stock reel</th>
                          <th>Stock estime</th>
                          <th>Mise a jour inventaire</th>
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
                                <button type="submit">Reset inventaire</button>
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
              <summary>Besoins par local ({requestsByLocation.length})</summary>
              {!selectedProduct ? (
                <p className="muted">Choisissez un produit pour visualiser les besoins consolides par local.</p>
              ) : requestsByLocation.length === 0 ? (
                <p className="muted">Aucun besoin en cours pour ce produit.</p>
              ) : (
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Lieu</th>
                        <th>Produit</th>
                        <th>Statut</th>
                        <th>Quantite demandee</th>
                        <th>Stock estime local</th>
                        <th>Alerte</th>
                      </tr>
                    </thead>
                    <tbody>
                      {requestsByLocation.map((row) => {
                        const shortage = row.estimatedStock !== null ? row.estimatedStock < row.quantity : false;
                        return (
                          <tr key={row.key} className={shortage ? "catalog-stock-negative" : ""}>
                            <td>{row.locationName}</td>
                            <td>{row.productTitle}</td>
                            <td>{catalogRequestStatusLabel(row.status)}</td>
                            <td>{row.quantity}</td>
                            <td>{row.estimatedStock ?? "-"}</td>
                            <td>{shortage ? "Stock estime insuffisant" : "-"}</td>
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
        <section className="card">
          <div className="row spread">
            <h3>Produits a commander</h3>
            <form method="get" className="row">
              <input type="hidden" name="view" value="reorder" />
              <label>
                Statut
                <select name="reorder_status" defaultValue={reorderStatus}>
                  <option value="all">Tous</option>
                  <option value="TO_ORDER">A commander</option>
                  <option value="ORDERED">Commande passee</option>
                  <option value="RECEIVED">Recu</option>
                  <option value="NORMAL">Normal</option>
                </select>
              </label>
              <button type="submit">Filtrer</button>
            </form>
          </div>
          <div className="table-wrap catalog-desktop-table top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Produit</th>
                  <th>Categorie</th>
                  <th>Stock global</th>
                  <th>Stock reserve</th>
                  <th>Local principal</th>
                  <th>Statut commande</th>
                  <th>Maj statut</th>
                </tr>
              </thead>
              <tbody>
                {reorderProducts.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="muted">
                      Aucun produit a commander pour ce filtre.
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
                      <td>{reorderStatusLabel(product.reorder_status)}</td>
                      <td>
                        <form action={updateAdminCatalogReorderStatusAction} className="row wrap gap-xs">
                          <input type="hidden" name="product_id" value={product.product_id} />
                          <input type="hidden" name="return_to" value={returnTo} />
                          <select name="reorder_status" defaultValue={product.reorder_status}>
                            <option value="TO_ORDER">A commander</option>
                            <option value="ORDERED">Commande passee</option>
                            <option value="RECEIVED">Recu</option>
                            <option value="NORMAL">Normal</option>
                          </select>
                          <button type="submit">Enregistrer</button>
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
                  {product.category_name || "Sans categorie"} · {product.primary_location_name || "Sans local"}
                </p>
                <p className="muted">
                  Stock {product.stock_global_quantity} / Reserve {product.reserve_stock}
                </p>
                <form action={updateAdminCatalogReorderStatusAction} className="row wrap gap-xs top-gap-sm">
                  <input type="hidden" name="product_id" value={product.product_id} />
                  <input type="hidden" name="return_to" value={returnTo} />
                  <select name="reorder_status" defaultValue={product.reorder_status}>
                    <option value="TO_ORDER">A commander</option>
                    <option value="ORDERED">Commande passee</option>
                    <option value="RECEIVED">Recu</option>
                    <option value="NORMAL">Normal</option>
                  </select>
                  <button type="submit">Maj</button>
                </form>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {currentView === "entries" ? (
        <>
          <section className="card">
            <div className="row spread">
              <h3>Nouvelle entree en stock</h3>
              <span className="badge">{entriesPage.total} mouvement(s)</span>
            </div>
            <form action={createAdminStockEntryAction} className="grid cols-2 config-form-grid catalog-entry-form top-gap-sm">
              <input type="hidden" name="return_to" value={returnTo} />
              <label>
                Produit
                <select name="product_id" required defaultValue={entryProduct || selectedProduct?.id || ""}>
                  <option value="">Selectionner un produit</option>
                  {stockableProducts.map((product) => (
                    <option key={product.id} value={product.id}>
                      {product.title}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Local
                <select name="location_id" required defaultValue={entryLocation || selectedProduct?.primary_location_id || ""}>
                  <option value="">Selectionner un local</option>
                  {activeLocations.map((location) => (
                    <option key={location.id} value={location.id}>
                      {location.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Quantite
                <input type="number" name="quantity" min={1} step={1} defaultValue={1} required />
              </label>
              <label>
                Date
                <input type="date" name="occurred_at" defaultValue={new Date().toISOString().slice(0, 10)} />
              </label>
              <label>
                Source
                <select name="source_type" defaultValue="delivery">
                  <option value="delivery">Livraison</option>
                  <option value="purchase">Achat</option>
                  <option value="return">Retour</option>
                  <option value="correction">Correction</option>
                  <option value="other">Autre</option>
                </select>
              </label>
              <label>
                Reference (optionnel)
                <input type="text" name="source_reference" maxLength={255} />
              </label>
              <label className="span-2">
                Note (optionnel)
                <textarea name="note" rows={2} maxLength={2000} />
              </label>
              <div className="row span-2">
                <button type="submit">Enregistrer l entree</button>
              </div>
            </form>
            <details className="top-gap-sm">
              <summary className="mode-link">Correction inventaire</summary>
              <form action={createAdminStockAdjustmentAction} className="grid cols-2 config-form-grid top-gap-sm">
                <input type="hidden" name="return_to" value={returnTo} />
                <label>
                  Produit
                  <select name="adjust_product_id" required defaultValue={entryProduct || selectedProduct?.id || ""}>
                    <option value="">Selectionner un produit</option>
                    {stockableProducts.map((product) => (
                      <option key={product.id} value={product.id}>
                        {product.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Local
                  <select name="adjust_location_id" required defaultValue={entryLocation || selectedProduct?.primary_location_id || ""}>
                    <option value="">Selectionner un local</option>
                    {activeLocations.map((location) => (
                      <option key={location.id} value={location.id}>
                        {location.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Delta quantite (+/-)
                  <input type="number" name="adjust_quantity" step={1} defaultValue={0} required />
                </label>
                <label>
                  Date
                  <input type="date" name="adjust_occurred_at" defaultValue={new Date().toISOString().slice(0, 10)} />
                </label>
                <label>
                  Motif
                  <select name="adjust_source_type" defaultValue="correction">
                    <option value="correction">Correction</option>
                    <option value="return">Retour</option>
                    <option value="other">Autre</option>
                  </select>
                </label>
                <label>
                  Reference (optionnel)
                  <input type="text" name="adjust_source_reference" maxLength={255} />
                </label>
                <label className="span-2">
                  Note (optionnel)
                  <textarea name="adjust_note" rows={2} maxLength={2000} />
                </label>
                <div className="row span-2">
                  <button type="submit" className="ghost">
                    Enregistrer la correction
                  </button>
                </div>
              </form>
            </details>
          </section>

          <section className="card">
            <div className="row spread">
              <h3>Historique des entrees</h3>
              <form method="get" className="row wrap gap-xs">
                <input type="hidden" name="view" value="entries" />
                <label>
                  Produit
                  <select name="entry_product" defaultValue={entryProduct}>
                    <option value="">Tous</option>
                    {stockableProducts.map((product) => (
                      <option key={product.id} value={product.id}>
                        {product.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Local
                  <select name="entry_location" defaultValue={entryLocation}>
                    <option value="">Tous</option>
                    {activeLocations.map((location) => (
                      <option key={location.id} value={location.id}>
                        {location.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Recherche
                  <input type="search" name="entry_q" defaultValue={entryQuery} placeholder="Produit, local, reference..." />
                </label>
                <button type="submit">Filtrer</button>
              </form>
            </div>
            <div className="table-wrap catalog-desktop-table top-gap-sm">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Produit</th>
                    <th>Local</th>
                    <th>Qt</th>
                    <th>Type</th>
                    <th>Source</th>
                    <th>Reference</th>
                    <th>Cree par</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {entryItems.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="muted">
                        Aucune entree pour ces filtres.
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
                          <td>{new Date(entry.occurred_at).toLocaleString("fr-FR")}</td>
                          <td>{entry.product_title}</td>
                          <td>{entry.location_name}</td>
                          <td>{qty >= 0 ? `+${qty}` : qty}</td>
                          <td>{stockMovementTypeLabel(entry.movement_type)}</td>
                          <td>{stockMovementSourceTypeLabel(entry.source_type)}</td>
                          <td>{entry.source_reference || "-"}</td>
                          <td>{entry.created_by_name || "-"}</td>
                          <td>
                            <Link className="ghost" href={detailLink}>
                              Details
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
                      {new Date(entry.occurred_at).toLocaleString("fr-FR")} · {entry.location_name}
                    </p>
                    <p className="muted">
                      {stockMovementTypeLabel(entry.movement_type)} · {stockMovementSourceTypeLabel(entry.source_type)}
                    </p>
                    <div className="row spread">
                      <strong>{qty >= 0 ? `+${qty}` : qty}</strong>
                      <Link className="ghost" href={detailLink}>
                        Details
                      </Link>
                    </div>
                  </article>
                );
              })}
            </div>
            <div className="row spread top-gap-sm">
              <span className="muted">
                Page {entryPage} / {entryTotalPages}
              </span>
              <div className="row gap-xs">
                {entryPage > 1 ? (
                  <Link className="ghost" href={entryPrevLink}>
                    Precedent
                  </Link>
                ) : null}
                {entryPage < entryTotalPages ? (
                  <Link className="ghost" href={entryNextLink}>
                    Suivant
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
            <h3>Nouveau transfert de stock</h3>
            <form action={createAdminCatalogTransferAction} className="grid cols-4 config-form-grid">
              <input type="hidden" name="return_to" value={returnTo} />
              <label>
                Produit
                <select name="product_id" defaultValue={selectedProduct?.id ?? ""} required>
                  <option value="">Selectionner un produit</option>
                  {stockableProducts.map((product) => (
                    <option key={product.id} value={product.id}>
                      {product.title}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Local source
                <select name="source_location_id" defaultValue={selectedProduct?.primary_location_id ?? ""} required>
                  <option value="">Selectionner un local source</option>
                  {activeLocations.map((location) => (
                    <option key={location.id} value={location.id}>
                      {location.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Local destination
                <select name="target_location_id" defaultValue="" required>
                  <option value="">Selectionner un local destination</option>
                  {activeLocations.map((location) => (
                    <option key={location.id} value={location.id}>
                      {location.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Quantite
                <input type="number" name="quantity" min={1} step={1} defaultValue={1} required />
              </label>
              <label>
                Date previsionnelle
                <input type="date" name="planned_transfer_date" />
              </label>
              <label>
                Personne designee
                <select name="assigned_to_user_id" defaultValue="">
                  <option value="">Aucune</option>
                  {clients.map((client) => (
                    <option key={client.id} value={client.id}>
                      {`${client.first_name ?? ""} ${client.last_name ?? ""}`.trim() || client.email}
                    </option>
                  ))}
                </select>
              </label>
              <label className="span-2">
                Note
                <input type="text" name="note" maxLength={2000} />
              </label>
              <div className="row span-4">
                <button type="submit">Creer transfert</button>
              </div>
            </form>
          </section>

          <section className="card">
            <div className="row spread">
              <h3>Suivi des transferts</h3>
              <form method="get" className="row">
                <input type="hidden" name="view" value="transfers" />
                <label>
                  Statut
                  <select name="transfer_status" defaultValue={transferStatus}>
                    <option value="all">Tous</option>
                    <option value="PENDING">En attente</option>
                    <option value="DONE">Fait</option>
                    <option value="CANCELLED">Annule</option>
                  </select>
                </label>
                <button type="submit">Filtrer</button>
              </form>
            </div>
            <div className="table-wrap catalog-desktop-table top-gap-sm">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Date creation</th>
                    <th>Produit</th>
                    <th>Source {"->"} Destination</th>
                    <th>Qt</th>
                    <th>Date prevue</th>
                    <th>Personne designee</th>
                    <th>Statut</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {transfers.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="muted">
                        Aucun transfert.
                      </td>
                    </tr>
                  ) : (
                    transfers.map((transfer) => (
                      <tr key={transfer.id}>
                        <td>{new Date(transfer.created_at).toLocaleString("fr-FR")}</td>
                        <td>{transfer.product_title}</td>
                        <td>
                          {transfer.source_location_name} {"->"} {transfer.target_location_name}
                        </td>
                        <td>{transfer.quantity}</td>
                        <td>{transfer.planned_transfer_date || "-"}</td>
                        <td>{transfer.assigned_to_name || "-"}</td>
                        <td>
                          {transferStatusLabel(transfer.status)}
                          {transfer.completed_transfer_date ? <div className="muted">Transfert: {transfer.completed_transfer_date}</div> : null}
                        </td>
                        <td>
                          {transfer.status === "PENDING" ? (
                            <div className="catalog-request-actions">
                              <form action={completeAdminCatalogTransferAction} className="row wrap gap-xs">
                                <input type="hidden" name="transfer_id" value={transfer.id} />
                                <input type="hidden" name="return_to" value={returnTo} />
                                <input type="date" name="completed_transfer_date" defaultValue={dateInputValue(transfer.planned_transfer_date)} />
                                <input type="text" name="note" maxLength={2000} placeholder="Note completion" />
                                <button type="submit">Marquer fait</button>
                              </form>
                              <form action={cancelAdminCatalogTransferAction} className="row wrap gap-xs">
                                <input type="hidden" name="transfer_id" value={transfer.id} />
                                <input type="hidden" name="return_to" value={returnTo} />
                                <input type="text" name="note" maxLength={2000} placeholder="Motif annulation" />
                                <button type="submit" className="danger ghost">
                                  Annuler
                                </button>
                              </form>
                            </div>
                          ) : (
                            <span className="muted">Aucune action</span>
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
                    Qt {transfer.quantity} · {transferStatusLabel(transfer.status)}
                  </p>
                  {transfer.status === "PENDING" ? (
                    <div className="catalog-request-actions">
                      <form action={completeAdminCatalogTransferAction} className="row wrap gap-xs">
                        <input type="hidden" name="transfer_id" value={transfer.id} />
                        <input type="hidden" name="return_to" value={returnTo} />
                        <input type="date" name="completed_transfer_date" defaultValue={dateInputValue(transfer.planned_transfer_date)} />
                        <button type="submit">Marquer fait</button>
                      </form>
                      <form action={cancelAdminCatalogTransferAction} className="row wrap gap-xs">
                        <input type="hidden" name="transfer_id" value={transfer.id} />
                        <input type="hidden" name="return_to" value={returnTo} />
                        <input type="text" name="note" maxLength={2000} placeholder="Motif annulation" />
                        <button type="submit" className="danger ghost">
                          Annuler
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
          <h3>Demandes produits eleves</h3>
          <p className="muted">Creation admin: la demande est acceptee immediatement (facturee ou non), puis passe a remettre a l eleve.</p>
          <form action={createAdminCatalogRequestAction} className="grid cols-4 config-form-grid">
            <input type="hidden" name="return_to" value={returnTo} />
            <label>
              Eleve
              <select name="student_user_id" required defaultValue="">
                <option value="">Selectionner un eleve</option>
                {clientOptions.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Produit
              <select name="product_id" required defaultValue={selectedProduct?.id ?? ""}>
                <option value="">Selectionner un produit</option>
                {activeProducts.map((product) => (
                  <option key={product.id} value={product.id}>
                    {product.title}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Lieu
              <select name="location_id" required defaultValue={selectedProduct?.primary_location_id ?? ""}>
                <option value="">Selectionner un lieu</option>
                {activeLocations.map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Quantite
              <input type="number" name="quantity" min={1} step={1} defaultValue={1} required />
            </label>
            <label className="span-2">
              Note
              <input type="text" name="note" maxLength={2000} />
            </label>
            <label className="checkline">
              <input type="checkbox" name="should_bill" />
              A facturer
            </label>
            <div className="row span-4">
              <button type="submit">Ajouter demande admin</button>
            </div>
          </form>

          <div className="table-wrap catalog-desktop-table top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Source</th>
                  <th>Eleve</th>
                  <th>Produit / Lieu</th>
                  <th>Qt</th>
                  <th>Statut</th>
                  <th>Facturation</th>
                  <th>Stock</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {requests.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="muted">
                      Aucune demande produit.
                    </td>
                  </tr>
                ) : (
                  requests.map((request) => (
                    <tr key={request.id}>
                      <td>{new Date(request.requested_at).toLocaleString("fr-FR")}</td>
                      <td>{catalogRequestSourceLabel(request.request_source)}</td>
                      <td>{request.student_name}</td>
                      <td>
                        {request.product_title}
                        <br />
                        <small className="muted">{request.location_name}</small>
                      </td>
                      <td>{request.quantity}</td>
                      <td>{catalogRequestStatusLabel(request.status)}</td>
                      <td>{request.should_bill === null ? "-" : request.should_bill ? "Oui" : "Non"}</td>
                      <td>
                        Reel: {request.stock_real_quantity ?? "-"}
                        <br />
                        Estime: {request.stock_estimated_quantity ?? "-"}
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
                                  Facturer
                                </label>
                                <input type="text" name="note" maxLength={2000} placeholder="Note (optionnel)" />
                                <button type="submit">Accepter</button>
                              </form>
                              <form action={reviewAdminCatalogRequestAction}>
                                <input type="hidden" name="request_id" value={request.id} />
                                <input type="hidden" name="decision" value="REJECT" />
                                <input type="hidden" name="return_to" value={returnTo} />
                                <input type="text" name="note" maxLength={2000} placeholder="Motif refus (optionnel)" />
                                <button type="submit" className="danger ghost">
                                  Refuser
                                </button>
                              </form>
                            </>
                          ) : null}
                          {(request.status === "TO_DELIVER" || request.status === "INVOICE_TO_SEND") && (
                            <form action={deliverAdminCatalogRequestAction}>
                              <input type="hidden" name="request_id" value={request.id} />
                              <input type="hidden" name="return_to" value={returnTo} />
                              <select name="delivered_by_user_id" defaultValue="">
                                <option value="">Remis par (utilisateur courant)</option>
                                {clients.map((client) => (
                                  <option key={client.id} value={client.id}>
                                    {`${client.first_name ?? ""} ${client.last_name ?? ""}`.trim() || client.email}
                                  </option>
                                ))}
                              </select>
                              <input type="text" name="note" maxLength={2000} placeholder="Note remise (optionnel)" />
                              <button type="submit">Marquer remis</button>
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
                  {catalogRequestStatusLabel(request.status)} · Qt {request.quantity}
                </p>
                <div className="catalog-request-actions">
                  {request.status === "PROCESSING" ? (
                    <>
                      <form action={reviewAdminCatalogRequestAction} className="row wrap gap-xs">
                        <input type="hidden" name="request_id" value={request.id} />
                        <input type="hidden" name="decision" value="ACCEPT" />
                        <input type="hidden" name="return_to" value={returnTo} />
                        <label className="checkline">
                          <input type="checkbox" name="should_bill" />
                          Facturer
                        </label>
                        <button type="submit">Accepter</button>
                      </form>
                      <form action={reviewAdminCatalogRequestAction} className="row wrap gap-xs">
                        <input type="hidden" name="request_id" value={request.id} />
                        <input type="hidden" name="decision" value="REJECT" />
                        <input type="hidden" name="return_to" value={returnTo} />
                        <button type="submit" className="danger ghost">
                          Refuser
                        </button>
                      </form>
                    </>
                  ) : null}
                  {(request.status === "TO_DELIVER" || request.status === "INVOICE_TO_SEND") ? (
                    <form action={deliverAdminCatalogRequestAction} className="row wrap gap-xs">
                      <input type="hidden" name="request_id" value={request.id} />
                      <input type="hidden" name="return_to" value={returnTo} />
                      <button type="submit">Marquer remis</button>
                    </form>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {selectedEntry ? (
        <section className="modal-overlay" role="dialog" aria-modal="true" aria-label="Details entree stock">
          <section className="modal-panel modal-day-details">
            <div className="row spread">
              <h3 className="modal-title">Details mouvement stock</h3>
              <Link
                className="ghost"
                href={`/admin/products${buildProductsQuery({ ...baseQuery, add: "", editProduct: "", entryId: "" })}`}
                aria-label="Fermer"
              >
                Fermer
              </Link>
            </div>
            <section className="modal-card">
              <div className="grid cols-2 config-form-grid">
                <p>
                  <strong>Produit:</strong> {selectedEntry.product_title}
                </p>
                <p>
                  <strong>Local:</strong> {selectedEntry.location_name}
                </p>
                <p>
                  <strong>Date:</strong> {new Date(selectedEntry.occurred_at).toLocaleString("fr-FR")}
                </p>
                <p>
                  <strong>Quantite:</strong> {Number(selectedEntry.quantity) >= 0 ? "+" : ""}
                  {selectedEntry.quantity}
                </p>
                <p>
                  <strong>Type:</strong> {stockMovementTypeLabel(selectedEntry.movement_type)}
                </p>
                <p>
                  <strong>Source:</strong> {stockMovementSourceTypeLabel(selectedEntry.source_type)}
                </p>
                <p>
                  <strong>Reference:</strong> {selectedEntry.source_reference || "-"}
                </p>
                <p>
                  <strong>Cree par:</strong> {selectedEntry.created_by_name || "-"}
                </p>
                <p className="span-2">
                  <strong>Note:</strong> {selectedEntry.note || "-"}
                </p>
              </div>
            </section>
          </section>
        </section>
      ) : null}

      {showAddForm ? (
        <section className="modal-overlay" role="dialog" aria-modal="true" aria-label="Ajouter produit">
          <section className="modal-panel modal-day-details">
            <div className="row spread">
              <h3 className="modal-title">Ajouter un produit</h3>
              <Link href={closeModalLink} className="ghost" aria-label="Fermer">
                Fermer
              </Link>
            </div>
            <section className="modal-card">
              <form action={createAdminCatalogProductAction} className="grid cols-3 config-form-grid">
                <input type="hidden" name="return_to" value={addFormReturnTo} />

                <label className="span-2">
                  Titre *
                  <input type="text" name="title" required maxLength={255} placeholder="Partition Niveau 1" />
                </label>

                <label>
                  Categorie *
                  <select name="category_id" defaultValue="" required>
                    <option value="">Selectionner...</option>
                    {activeCategories.map((categoryRow) => (
                      <option key={categoryRow.id} value={categoryRow.id}>
                        {categoryRow.name}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Tarif TTC *
                  <input type="number" name="price_incl_vat" min="0" step="0.01" defaultValue="0.00" required />
                </label>

                <label>
                  Tarif HT (optionnel)
                  <input type="number" name="price_excl_vat" min="0" step="0.01" placeholder="Calcule automatiquement si vide" />
                </label>

                <label>
                  TVA (%) (optionnel, defaut 20)
                  <input type="number" name="vat_rate" min="0" max="100" step="0.001" defaultValue="20.000" />
                </label>

                <label>
                  Local principal (optionnel)
                  <select name="primary_location_id" defaultValue="">
                    <option value="">-</option>
                    {activeLocations.map((location) => (
                      <option key={location.id} value={location.id}>
                        {location.name}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Code-barres (optionnel)
                  <input type="text" name="barcode" maxLength={120} />
                </label>

                <label>
                  Stock de reserve (optionnel)
                  <input type="number" name="reserve_stock" min="0" step="1" defaultValue="0" />
                </label>

                <label>
                  Statut commande (optionnel)
                  <select name="reorder_status" defaultValue="NORMAL">
                    <option value="NORMAL">Normal</option>
                    <option value="TO_ORDER">A commander</option>
                    <option value="ORDERED">Commande passee</option>
                    <option value="RECEIVED">Recu</option>
                  </select>
                </label>

                <fieldset className="span-3">
                  <legend>Type de produit</legend>
                  <div className="row">
                    <label className="checkline">
                      <input type="radio" name="is_virtual" value="false" defaultChecked />
                      Produit physique (stock gere)
                    </label>
                    <label className="checkline">
                      <input type="radio" name="is_virtual" value="true" />
                      Produit virtuel (pas de stock)
                    </label>
                  </div>
                </fieldset>

                <label>
                  Lien web (optionnel)
                  <input type="url" name="web_link" />
                </label>

                <label className="span-2">
                  Visuel URL (optionnel)
                  <input type="url" name="image_url" />
                </label>

                <label className="span-2">
                  Description courte (optionnel)
                  <input type="text" name="short_description" maxLength={500} />
                </label>

                <label className="span-3">
                  Description longue (optionnel)
                  <textarea name="long_description" rows={3} maxLength={12000} />
                </label>

                <label className="checkline">
                  <input type="checkbox" name="purchasable_online" />
                  Achetable en ligne
                </label>

                <label className="checkline">
                  <input type="checkbox" name="is_public" defaultChecked />
                  Public (visible client)
                </label>

                <label className="checkline">
                  <input type="checkbox" name="active" defaultChecked />
                  Actif
                </label>

                <div className="row span-3 modal-actions-end">
                  <Link className="ghost" href={closeModalLink}>
                    Annuler
                  </Link>
                  <button type="submit">Ajouter</button>
                </div>
              </form>
            </section>
          </section>
        </section>
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
        />
      ) : null}
    </section>
  );
}
