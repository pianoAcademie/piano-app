import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  createAdminCatalogProductAction,
  createAdminCatalogRequestAction,
  deleteAdminCatalogProductAction,
  deliverAdminCatalogRequestAction,
  reviewAdminCatalogRequestAction,
  updateAdminCatalogInventoryAction,
  updateAdminCatalogProductAction,
} from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import type {
  AdminCatalogCategoryOut,
  AdminCatalogProductOut,
  AdminCatalogRequestOut,
  AdminCatalogStockOut,
  AdminClientOut,
  LocationOut,
} from "../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
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

function dateInputValue(value: string | null): string {
  if (!value) {
    return "";
  }
  return value.slice(0, 10);
}

function buildProductsQuery(params: {
  q: string;
  category: string;
  status: string;
  visibility: string;
  online: string;
  add: string;
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
  const query = sp.toString();
  return query ? `?${query}` : "";
}

export default async function AdminProductsPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("access_token")?.value;
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
  const showAddForm = add === "1";

  const returnTo = `/admin/products${buildProductsQuery({
    q: query,
    category,
    status,
    visibility,
    online,
    add: "",
  })}`;
  const addLink = `/admin/products${buildProductsQuery({
    q: query,
    category,
    status,
    visibility,
    online,
    add: "1",
  })}`;

  const [categoriesResult, productsResult, stocksResult, requestsResult, locationsResult, clientsResult] = await Promise.all([
    backendRequest<AdminCatalogCategoryOut[]>("/api/v1/admin/config/catalog/categories?include_inactive=true", {}, token),
    backendRequest<AdminCatalogProductOut[]>("/api/v1/admin/config/catalog/products?include_inactive=true", {}, token),
    backendRequest<AdminCatalogStockOut[]>("/api/v1/admin/config/catalog/stocks", {}, token),
    backendRequest<AdminCatalogRequestOut[]>("/api/v1/admin/catalog/requests", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations", {}, token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?limit=1000", {}, token),
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

  const activeCategories = categories.filter((row) => row.active);
  const activeProducts = products.filter((row) => row.active);
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

  const clientOptions = clients
    .filter((row) => row.role === "client" && row.client_status !== "ARCHIVED")
    .map((row) => ({
      id: row.id,
      label: `${`${row.first_name ?? ""} ${row.last_name ?? ""}`.trim() || row.email} (${row.client_kind})`,
    }))
    .sort((a, b) => a.label.localeCompare(b.label, "fr"));

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h2>Gestion des produits</h2>
        <p className="muted">Catalogue, stock par local et demandes produits eleves.</p>
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
            <Link className="ghost" href="/admin/products">
              Reinitialiser
            </Link>
            <span className="badge">{filteredProducts.length} produit(s)</span>
          </div>
        </form>

        {showAddForm ? (
          <form action={createAdminCatalogProductAction} className="grid cols-4 config-form-grid top-gap-sm">
            <input type="hidden" name="return_to" value={returnTo} />
            <label className="span-2">
              Titre
              <input type="text" name="title" required maxLength={255} placeholder="Partition Niveau 1" />
            </label>
            <label>
              Categorie
              <select name="category_id" defaultValue="">
                <option value="">-</option>
                {activeCategories.map((categoryRow) => (
                  <option key={categoryRow.id} value={categoryRow.id}>
                    {categoryRow.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Code-barres
              <input type="text" name="barcode" maxLength={120} />
            </label>
            <label>
              Tarif HT
              <input type="number" name="price_excl_vat" min="0" step="0.01" defaultValue="0.00" required />
            </label>
            <label>
              Tarif TTC
              <input type="number" name="price_incl_vat" min="0" step="0.01" defaultValue="0.00" required />
            </label>
            <label>
              TVA (%)
              <input type="number" name="vat_rate" min="0" max="100" step="0.001" defaultValue="20.000" required />
            </label>
            <label>
              Lien web
              <input type="url" name="web_link" />
            </label>
            <label className="span-2">
              Visuel (URL)
              <input type="url" name="image_url" />
            </label>
            <label className="span-2">
              Description courte
              <input type="text" name="short_description" maxLength={500} />
            </label>
            <label className="span-4">
              Description longue
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
            <div className="row span-4">
              <button type="submit">Ajouter</button>
            </div>
          </form>
        ) : null}

        <div className="table-wrap top-gap-sm">
          <table className="data-table">
            <thead>
              <tr>
                <th>Produit</th>
                <th>Categorie</th>
                <th>TTC</th>
                <th>TVA</th>
                <th>Stock global</th>
                <th>Online</th>
                <th>Public</th>
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
                filteredProducts.map((product) => (
                  <tr key={product.id}>
                    <td>
                      <strong>{product.title}</strong>
                      {product.barcode ? <p className="muted">Code: {product.barcode}</p> : null}
                    </td>
                    <td>{product.category_name || "-"}</td>
                    <td>{formatMoney(product.price_incl_vat, "EUR")}</td>
                    <td>{Number(product.vat_rate).toFixed(2)}%</td>
                    <td>{product.stock_global_quantity}</td>
                    <td>{yesNoLabel(product.purchasable_online)}</td>
                    <td>{yesNoLabel(product.is_public)}</td>
                    <td>{yesNoLabel(product.active)}</td>
                    <td>
                      <details>
                        <summary className="mode-link">Modifier</summary>
                        <form action={updateAdminCatalogProductAction} className="grid cols-2 top-gap-sm">
                          <input type="hidden" name="product_id" value={product.id} />
                          <input type="hidden" name="return_to" value={returnTo} />
                          <label className="span-2">
                            Titre
                            <input type="text" name="title" defaultValue={product.title} required maxLength={255} />
                          </label>
                          <label>
                            Categorie
                            <select name="category_id" defaultValue={product.category_id ?? ""}>
                              <option value="">-</option>
                              {categories.map((categoryRow) => (
                                <option key={categoryRow.id} value={categoryRow.id}>
                                  {categoryRow.name}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Code-barres
                            <input type="text" name="barcode" defaultValue={product.barcode || ""} maxLength={120} />
                          </label>
                          <label>
                            Tarif HT
                            <input type="number" name="price_excl_vat" min="0" step="0.01" defaultValue={product.price_excl_vat} required />
                          </label>
                          <label>
                            Tarif TTC
                            <input type="number" name="price_incl_vat" min="0" step="0.01" defaultValue={product.price_incl_vat} required />
                          </label>
                          <label>
                            TVA (%)
                            <input type="number" name="vat_rate" min="0" max="100" step="0.001" defaultValue={product.vat_rate} required />
                          </label>
                          <label>
                            Lien web
                            <input type="url" name="web_link" defaultValue={product.web_link || ""} />
                          </label>
                          <label className="span-2">
                            Description courte
                            <input type="text" name="short_description" defaultValue={product.short_description || ""} maxLength={500} />
                          </label>
                          <label className="span-2">
                            Description longue
                            <textarea name="long_description" rows={3} maxLength={12000} defaultValue={product.long_description || ""} />
                          </label>
                          <label className="checkline">
                            <input type="checkbox" name="purchasable_online" defaultChecked={product.purchasable_online} />
                            Achetable en ligne
                          </label>
                          <label className="checkline">
                            <input type="checkbox" name="is_public" defaultChecked={product.is_public} />
                            Public
                          </label>
                          <label className="checkline">
                            <input type="checkbox" name="active" defaultChecked={product.active} />
                            Actif
                          </label>
                          <div className="row span-2">
                            <button type="submit">Enregistrer</button>
                          </div>
                        </form>
                        <form action={deleteAdminCatalogProductAction} className="top-gap-sm">
                          <input type="hidden" name="product_id" value={product.id} />
                          <input type="hidden" name="return_to" value={returnTo} />
                          <button type="submit" className="danger">
                            Supprimer
                          </button>
                        </form>
                      </details>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h3>Stocks par local</h3>
        {stocks.length === 0 ? (
          <p className="muted">Aucun stock initialise (creez d abord un produit).</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Produit</th>
                  <th>Lieu</th>
                  <th>Inventaire</th>
                  <th>Date inventaire</th>
                  <th>Stock reel</th>
                  <th>Stock estime</th>
                  <th>Mise a jour inventaire</th>
                </tr>
              </thead>
              <tbody>
                {stocks.map((stock) => (
                  <tr
                    key={`${stock.product_id}-${stock.location_id}`}
                    className={stock.real_quantity < 0 || stock.estimated_quantity < 0 ? "catalog-stock-negative" : ""}
                  >
                    <td>{stock.product_title}</td>
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
        )}
      </section>

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
            <select name="product_id" required defaultValue="">
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
            <select name="location_id" required defaultValue="">
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

        <div className="table-wrap top-gap-sm">
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
      </section>
    </section>
  );
}
