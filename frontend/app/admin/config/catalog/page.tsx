import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  createAdminCatalogCategoryAction,
  createAdminCatalogKitAction,
  deleteAdminCatalogCategoryAction,
  deleteAdminCatalogKitAction,
  duplicateAdminCatalogKitAction,
  toggleAdminCatalogCategoryArchiveAction,
  toggleAdminCatalogKitArchiveAction,
  updateAdminCatalogCategoryAction,
  updateAdminCatalogKitAction,
} from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import AdminKitActionsMenu from "../../../../components/admin-kit-actions-menu";
import CatalogKitCompositionPricing from "../../../../components/catalog-kit-composition-pricing";
import type { AdminCatalogCategoryOut, AdminCatalogKitOut, AdminCatalogProductOut } from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;
type CatalogTab = "categories" | "kits";
type StatusFilter = "all" | "active" | "archived";

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function parseTab(value: string): CatalogTab {
  return value.trim().toLowerCase() === "kits" ? "kits" : "categories";
}

function parseStatusFilter(value: string): StatusFilter {
  const normalized = value.trim().toLowerCase();
  if (normalized === "active") {
    return "active";
  }
  if (normalized === "archived") {
    return "archived";
  }
  return "all";
}

function buildCatalogConfigHref(params: SearchParams, updates: Record<string, string | undefined>): string {
  const sp = new URLSearchParams();
  for (const [key, rawValue] of Object.entries(params)) {
    const value = Array.isArray(rawValue) ? rawValue[0] : rawValue;
    if (!value) {
      continue;
    }
    sp.set(key, value);
  }
  for (const [key, value] of Object.entries(updates)) {
    if (!value) {
      sp.delete(key);
      continue;
    }
    sp.set(key, value);
  }
  const query = sp.toString();
  return query ? `/admin/config/catalog?${query}` : "/admin/config/catalog";
}

function normalizeText(value: string | null): string {
  return (value || "").trim().toLocaleLowerCase("fr-FR");
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

function statusLabel(active: boolean): string {
  return active ? "Actif" : "Archive";
}

function visibilityLabel(isPublic: boolean): string {
  return isPublic ? "Visible" : "Masque";
}

function kitPriceModeLabel(mode: string): string {
  return mode.trim().toLowerCase() === "forced" ? "Force" : "Automatique";
}

export default async function AdminCatalogConfigPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const params = searchParams ?? {};
  const activeTab = parseTab(readParam(params, "tab"));
  const categoryQuery = readParam(params, "category_q").trim();
  const categoryStatus = parseStatusFilter(readParam(params, "category_status"));
  const kitQuery = readParam(params, "kit_q").trim();
  const kitStatus = parseStatusFilter(readParam(params, "kit_status"));
  const categoryDrawerModeRaw = readParam(params, "category_drawer").trim().toLowerCase();
  const categoryDrawerMode = categoryDrawerModeRaw === "edit" ? "edit" : categoryDrawerModeRaw === "create" ? "create" : "";
  const categoryId = readParam(params, "category_id").trim();
  const kitDrawerModeRaw = readParam(params, "kit_drawer").trim().toLowerCase();
  const kitDrawerMode = kitDrawerModeRaw === "edit" ? "edit" : kitDrawerModeRaw === "create" ? "create" : "";
  const kitId = readParam(params, "kit_id").trim();
  const okMessage = readParam(params, "ok");
  const errorMessage = readParam(params, "error");

  const [categoriesResult, kitsResult, productsResult] = await Promise.all([
    backendRequest<AdminCatalogCategoryOut[]>("/api/v1/admin/config/catalog/categories?include_inactive=true", {}, token),
    backendRequest<AdminCatalogKitOut[]>("/api/v1/admin/config/catalog/kits?include_inactive=true", {}, token),
    backendRequest<AdminCatalogProductOut[]>("/api/v1/admin/config/catalog/products?include_inactive=true", {}, token),
  ]);

  const unauthorized = [categoriesResult, kitsResult, productsResult].some((result) => !result.ok && result.status === 401);
  if (unauthorized) {
    redirect("/login?error=Session%20expiree");
  }

  const loadErrors: string[] = [];
  const categories = categoriesResult.ok ? categoriesResult.data : [];
  const kits = kitsResult.ok ? kitsResult.data : [];
  const products = productsResult.ok ? productsResult.data : [];

  if (!categoriesResult.ok) {
    loadErrors.push(`Categories: ${categoriesResult.message}`);
  }
  if (!kitsResult.ok) {
    loadErrors.push(`Kits: ${kitsResult.message}`);
  }
  if (!productsResult.ok) {
    loadErrors.push(`Produits: ${productsResult.message}`);
  }

  const selectedCategory = categories.find((row) => row.id === categoryId) ?? null;
  const selectedKit = kits.find((row) => row.id === kitId) ?? null;
  const showCategoryDrawer = activeTab === "categories" && (categoryDrawerMode === "create" || (categoryDrawerMode === "edit" && !!selectedCategory));
  const showKitDrawer = activeTab === "kits" && (kitDrawerMode === "create" || (kitDrawerMode === "edit" && !!selectedKit));

  const selectedKitItems = selectedKit
    ? [...selectedKit.items].sort((left, right) => left.display_order - right.display_order)
    : [];

  const linkedProductsByCategory = new Map<string, number>();
  for (const product of products) {
    if (!product.category_id) {
      continue;
    }
    linkedProductsByCategory.set(product.category_id, (linkedProductsByCategory.get(product.category_id) ?? 0) + 1);
  }

  const normalizedCategoryQuery = categoryQuery.toLocaleLowerCase("fr-FR");
  const normalizedKitQuery = kitQuery.toLocaleLowerCase("fr-FR");
  const filteredCategories = categories.filter((category) => {
    if (categoryStatus === "active" && !category.active) {
      return false;
    }
    if (categoryStatus === "archived" && category.active) {
      return false;
    }
    if (!normalizedCategoryQuery) {
      return true;
    }
    const haystack = `${normalizeText(category.name)} ${normalizeText(category.code)} ${normalizeText(category.description)}`;
    return haystack.includes(normalizedCategoryQuery);
  });
  const filteredKits = kits.filter((kit) => {
    if (kitStatus === "active" && !kit.active) {
      return false;
    }
    if (kitStatus === "archived" && kit.active) {
      return false;
    }
    if (!normalizedKitQuery) {
      return true;
    }
    const haystack = `${normalizeText(kit.title)} ${normalizeText(kit.code)} ${normalizeText(kit.short_description)}`;
    return haystack.includes(normalizedKitQuery);
  });

  const selectedKitProductIds = new Set(selectedKitItems.map((item) => item.product_id));
  const kitSelectableProducts = products
    .filter((product) => product.active || selectedKitProductIds.has(product.id))
    .sort((left, right) => left.title.localeCompare(right.title, "fr-FR"));
  const kitSelectableCategories = categories
    .filter((category) => category.active || category.id === selectedKit?.category_id)
    .sort((left, right) => left.name.localeCompare(right.name, "fr-FR"));

  const currentHref = buildCatalogConfigHref(params, {});
  const categoryReturnTo = buildCatalogConfigHref(params, { tab: "categories", category_drawer: undefined, category_id: undefined });
  const kitReturnTo = buildCatalogConfigHref(params, {
    tab: "kits",
    kit_drawer: undefined,
    kit_id: undefined,
  });
  const categoriesTabHref = buildCatalogConfigHref(params, { tab: "categories", kit_drawer: undefined, kit_id: undefined });
  const kitsTabHref = buildCatalogConfigHref(params, { tab: "kits", category_drawer: undefined, category_id: undefined });
  const createCategoryHref = buildCatalogConfigHref(params, { tab: "categories", category_drawer: "create", category_id: undefined });
  const createKitHref = buildCatalogConfigHref(params, { tab: "kits", kit_drawer: "create", kit_id: undefined });
  const categoryCloseHref = buildCatalogConfigHref(params, { category_drawer: undefined, category_id: undefined });
  const kitCloseHref = buildCatalogConfigHref(params, { kit_drawer: undefined, kit_id: undefined });

  return (
    <main className="stack catalog-admin-page">
      <section className="card">
        <div className="row spread">
          <div>
            <h1>Configuration des categories et des kits</h1>
            <p className="muted">Gerez separement les categories de produits et les kits.</p>
          </div>
          <div className="row">
            <Link className="ghost" href={createCategoryHref}>
              Ajouter une categorie
            </Link>
            <Link className="mode-link" href={createKitHref}>
              Ajouter un kit
            </Link>
          </div>
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

      <section className="card">
        <nav className="catalog-admin-tabs">
          <Link className={`catalog-admin-tab ${activeTab === "categories" ? "active" : ""}`} href={categoriesTabHref}>
            Categories
          </Link>
          <Link className={`catalog-admin-tab ${activeTab === "kits" ? "active" : ""}`} href={kitsTabHref}>
            Kits
          </Link>
        </nav>
      </section>

      {activeTab === "categories" ? (
        <section className="card">
          <div className="row spread">
            <h3>Categories</h3>
            <form method="get" className="row catalog-admin-filters">
              <input type="hidden" name="tab" value="categories" />
              <label>
                Recherche
                <input type="search" name="category_q" defaultValue={categoryQuery} placeholder="Nom, code ou description..." />
              </label>
              <label>
                Statut
                <select name="category_status" defaultValue={categoryStatus}>
                  <option value="all">Tous</option>
                  <option value="active">Actifs</option>
                  <option value="archived">Archives</option>
                </select>
              </label>
              <button type="submit">Filtrer</button>
              <Link className="ghost" href={buildCatalogConfigHref(params, { category_q: undefined, category_status: undefined })}>
                Reinitialiser
              </Link>
            </form>
          </div>

          {filteredCategories.length === 0 ? (
            <p className="muted">Aucune categorie correspondant aux filtres.</p>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Nom</th>
                    <th>Code</th>
                    <th>Description</th>
                    <th>Produits lies</th>
                    <th>Statut</th>
                    <th>Ordre</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCategories.map((category) => {
                    const editHref = buildCatalogConfigHref(params, {
                      tab: "categories",
                      category_drawer: "edit",
                      category_id: category.id,
                    });
                    return (
                      <tr key={category.id}>
                        <td>{category.name}</td>
                        <td>{category.code || "-"}</td>
                        <td>{category.description || "-"}</td>
                        <td>{linkedProductsByCategory.get(category.id) ?? 0}</td>
                        <td>{statusLabel(category.active)}</td>
                        <td>{category.display_order}</td>
                        <td>
                          <details className="catalog-actions-menu">
                            <summary className="ghost catalog-actions-trigger">...</summary>
                            <div className="catalog-actions-menu-panel">
                              <Link className="catalog-actions-item" href={editHref}>
                                Modifier
                              </Link>
                              <form action={toggleAdminCatalogCategoryArchiveAction}>
                                <input type="hidden" name="category_id" value={category.id} />
                                <input type="hidden" name="archive" value={category.active ? "true" : "false"} />
                                <input type="hidden" name="return_to" value={currentHref} />
                                <button type="submit" className="catalog-actions-item">
                                  {category.active ? "Archiver" : "Desarchiver"}
                                </button>
                              </form>
                              <form action={deleteAdminCatalogCategoryAction}>
                                <input type="hidden" name="category_id" value={category.id} />
                                <input type="hidden" name="return_to" value={currentHref} />
                                <button type="submit" className="catalog-actions-item danger">
                                  Supprimer
                                </button>
                              </form>
                            </div>
                          </details>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}

      {activeTab === "kits" ? (
        <section className="card">
          <div className="row spread">
            <h3>Kits</h3>
            <form method="get" className="row catalog-admin-filters">
              <input type="hidden" name="tab" value="kits" />
              <label>
                Recherche
                <input type="search" name="kit_q" defaultValue={kitQuery} placeholder="Nom, code ou description..." />
              </label>
              <label>
                Statut
                <select name="kit_status" defaultValue={kitStatus}>
                  <option value="all">Tous</option>
                  <option value="active">Actifs</option>
                  <option value="archived">Archives</option>
                </select>
              </label>
              <button type="submit">Filtrer</button>
              <Link className="ghost" href={buildCatalogConfigHref(params, { kit_q: undefined, kit_status: undefined })}>
                Reinitialiser
              </Link>
            </form>
          </div>

          {filteredKits.length === 0 ? (
            <p className="muted">Aucun kit correspondant aux filtres.</p>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Nom</th>
                    <th>Categorie</th>
                    <th>Elements</th>
                    <th>Prix calcule</th>
                    <th>Prix facture</th>
                    <th>Mode de prix</th>
                    <th>Statut</th>
                    <th>Visibilite</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredKits.map((kit) => {
                    const editHref = buildCatalogConfigHref(params, { tab: "kits", kit_drawer: "edit", kit_id: kit.id });
                    const viewCompositionHref = buildCatalogConfigHref(params, {
                      tab: "kits",
                      kit_drawer: "edit",
                      kit_id: kit.id,
                      kit_focus: "composition",
                    });
                    return (
                      <tr key={kit.id}>
                        <td>
                          <strong>{kit.title}</strong>
                          <br />
                          <span className="muted">{kit.code || "-"}</span>
                        </td>
                        <td>{kit.category_name || "-"}</td>
                        <td>{kit.items.length}</td>
                        <td>{formatMoney(kit.computed_price_incl_vat, kit.currency || "EUR")}</td>
                        <td>{formatMoney(kit.price_effective_incl_vat || kit.price_incl_vat, kit.currency || "EUR")}</td>
                        <td>{kitPriceModeLabel(kit.price_mode)}</td>
                        <td>{statusLabel(kit.active)}</td>
                        <td>{visibilityLabel(kit.is_public)}</td>
                        <td>
                          <AdminKitActionsMenu
                            editHref={editHref}
                            viewCompositionHref={viewCompositionHref}
                            kitId={kit.id}
                            returnTo={currentHref}
                            active={kit.active}
                            duplicateAction={duplicateAdminCatalogKitAction}
                            toggleArchiveAction={toggleAdminCatalogKitArchiveAction}
                            deleteAction={deleteAdminCatalogKitAction}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}

      {showCategoryDrawer ? (
        <section className="catalog-admin-drawer-overlay">
          <article className="catalog-admin-drawer">
            <header className="catalog-admin-drawer-header">
              <div>
                <h3>{selectedCategory ? "Modifier la categorie" : "Ajouter une categorie"}</h3>
                <p className="muted">Une categorie archivee ne sera plus proposee dans les nouveaux formulaires.</p>
              </div>
              <Link className="ghost" href={categoryCloseHref}>
                Fermer
              </Link>
            </header>

            <form action={selectedCategory ? updateAdminCatalogCategoryAction : createAdminCatalogCategoryAction} className="catalog-admin-drawer-form">
              <input type="hidden" name="return_to" value={categoryReturnTo} />
              {selectedCategory ? <input type="hidden" name="category_id" value={selectedCategory.id} /> : null}

              <section className="catalog-admin-drawer-body">
                <label>
                  Nom
                  <input type="text" name="name" required maxLength={120} defaultValue={selectedCategory?.name || ""} />
                </label>
                <label>
                  Code
                  <input type="text" name="code" maxLength={64} defaultValue={selectedCategory?.code || ""} />
                </label>
                <label>
                  Description
                  <textarea name="description" rows={3} maxLength={2000} defaultValue={selectedCategory?.description || ""} />
                </label>
                <label>
                  Ordre d affichage
                  <input type="number" name="display_order" min={0} step={1} defaultValue={selectedCategory?.display_order ?? 0} />
                </label>
                <label>
                  Statut
                  <select name="status" defaultValue={selectedCategory?.active === false ? "archived" : "active"}>
                    <option value="active">Actif</option>
                    <option value="archived">Archive</option>
                  </select>
                </label>
                <label className="checkline">
                  <input type="hidden" name="can_be_requested_by_professor" value="false" />
                  <input
                    type="checkbox"
                    name="can_be_requested_by_professor"
                    value="true"
                    defaultChecked={selectedCategory?.can_be_requested_by_professor ?? true}
                  />
                  Commandable par les professeurs
                </label>
              </section>

              <footer className="catalog-admin-drawer-footer">
                <button type="submit">{selectedCategory ? "Enregistrer" : "Creer la categorie"}</button>
                <Link className="ghost" href={categoryCloseHref}>
                  Annuler
                </Link>
              </footer>
            </form>
          </article>
        </section>
      ) : null}

      {showKitDrawer ? (
        <section className="catalog-admin-drawer-overlay">
          <article className="catalog-admin-drawer catalog-admin-drawer-kit">
            <header className="catalog-admin-drawer-header">
              <div>
                <h3>{selectedKit ? "Modifier le kit" : "Ajouter un kit"}</h3>
                <p className="muted">Un kit archive ne sera plus propose dans les nouveaux formulaires.</p>
              </div>
              <Link className="ghost" href={kitCloseHref}>
                Fermer
              </Link>
            </header>

            <form action={selectedKit ? updateAdminCatalogKitAction : createAdminCatalogKitAction} className="catalog-admin-drawer-form">
              <input type="hidden" name="return_to" value={kitReturnTo} />
              {selectedKit ? <input type="hidden" name="kit_id" value={selectedKit.id} /> : null}

              <section className="catalog-admin-drawer-body">
                <article className="card">
                  <h4>Informations generales</h4>
                  <div className="grid cols-2 config-form-grid">
                    <label>
                      Nom
                      <input type="text" name="title" required maxLength={255} defaultValue={selectedKit?.title || ""} />
                    </label>
                    <label>
                      Code
                      <input type="text" name="code" maxLength={64} defaultValue={selectedKit?.code || ""} />
                    </label>
                    <label>
                      Categorie
                      <select name="category_id" defaultValue={selectedKit?.category_id ?? ""}>
                        <option value="">-</option>
                        {kitSelectableCategories.map((category) => (
                          <option key={category.id} value={category.id}>
                            {category.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Statut
                      <select name="status" defaultValue={selectedKit?.active === false ? "archived" : "active"}>
                        <option value="active">Actif</option>
                        <option value="archived">Archive</option>
                      </select>
                    </label>
                    <label className="span-2">
                      Description courte
                      <input type="text" name="short_description" maxLength={500} defaultValue={selectedKit?.short_description || ""} />
                    </label>
                    <label className="span-2">
                      Description
                      <textarea name="long_description" rows={3} maxLength={12000} defaultValue={selectedKit?.long_description || ""} />
                    </label>
                    <label className="span-2">
                      Visuel (URL)
                      <input type="url" name="image_url" defaultValue={selectedKit?.image_url || ""} />
                    </label>
                  </div>
                </article>

                <CatalogKitCompositionPricing
                  products={kitSelectableProducts.map((product) => ({
                    id: product.id,
                    title: product.title,
                    priceInclVat: product.price_incl_vat,
                  }))}
                  initialItems={selectedKitItems.map((item) => ({
                    productId: item.product_id,
                    quantity: item.quantity,
                    displayOrder: item.display_order,
                  }))}
                  initialPriceMode={selectedKit?.price_mode || "calculated"}
                  initialForcedPrice={selectedKit?.forced_price || ""}
                  initialCurrency={selectedKit?.currency || "EUR"}
                />

                <article className="card">
                  <h4>TVA</h4>
                  <div className="grid cols-2 config-form-grid">
                    <label>
                      TVA (%)
                      <input type="number" name="vat_rate" min={0} max={100} step="0.001" required defaultValue={selectedKit?.vat_rate || "20.000"} />
                    </label>
                  </div>
                </article>

                <article className="card">
                  <h4>Usage</h4>
                  <div className="grid cols-2 config-form-grid">
                    <label className="checkline">
                      <input type="hidden" name="use_in_manual_billing" value="false" />
                      <input
                        type="checkbox"
                        name="use_in_manual_billing"
                        value="true"
                        defaultChecked={selectedKit?.use_in_manual_billing ?? true}
                      />
                      Utilisable en facturation manuelle
                    </label>
                    <label className="checkline">
                      <input type="hidden" name="use_in_enrollments" value="false" />
                      <input
                        type="checkbox"
                        name="use_in_enrollments"
                        value="true"
                        defaultChecked={selectedKit?.use_in_enrollments ?? true}
                      />
                      Utilisable en inscriptions
                    </label>
                    <label className="checkline">
                      <input type="hidden" name="is_public" value="false" />
                      <input type="checkbox" name="is_public" value="true" defaultChecked={selectedKit?.is_public ?? true} />
                      Visible dans le catalogue
                    </label>
                    <label className="checkline">
                      <input type="hidden" name="purchasable_online" value="false" />
                      <input
                        type="checkbox"
                        name="purchasable_online"
                        value="true"
                        defaultChecked={selectedKit?.purchasable_online ?? false}
                      />
                      Achetable en ligne
                    </label>
                  </div>
                </article>
              </section>

              <footer className="catalog-admin-drawer-footer">
                <button type="submit">{selectedKit ? "Enregistrer" : "Creer le kit"}</button>
                <Link className="ghost" href={kitCloseHref}>
                  Annuler
                </Link>
              </footer>
            </form>
          </article>
        </section>
      ) : null}
    </main>
  );
}
