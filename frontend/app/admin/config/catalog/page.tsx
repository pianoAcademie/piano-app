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
import type { AdminCatalogCategoryOut, AdminCatalogKitOut, AdminCatalogProductOut, UserOut } from "../../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../../lib/ui-i18n";

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

function statusLabel(active: boolean, language: UiLanguage): string {
  return active ? uiText(language, "common.active") : uiText(language, "common.archived");
}

function visibilityLabel(isPublic: boolean, language: UiLanguage): string {
  return isPublic ? uiText(language, "common.visible") : uiText(language, "common.hidden");
}

function kitPriceModeLabel(mode: string, language: UiLanguage): string {
  return mode.trim().toLowerCase() === "forced"
    ? uiText(language, "admin.catalog.price_mode_forced")
    : uiText(language, "admin.catalog.price_mode_calculated");
}

export default async function AdminCatalogConfigPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
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
    redirect("/login?error_code=session_expired");
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

  const normalizedCategoryQuery = categoryQuery.toLocaleLowerCase(localeForUiLanguage(language));
  const normalizedKitQuery = kitQuery.toLocaleLowerCase(localeForUiLanguage(language));
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
    .sort((left, right) => left.title.localeCompare(right.title, localeForUiLanguage(language)));
  const kitSelectableCategories = categories
    .filter((category) => category.active || category.id === selectedKit?.category_id)
    .sort((left, right) => left.name.localeCompare(right.name, localeForUiLanguage(language)));

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
  const catalogStats = {
    categories: categories.length,
    activeCategories: categories.filter((row) => row.active).length,
    kits: kits.length,
    activeKits: kits.filter((row) => row.active).length,
    uncategorizedProducts: products.filter((row) => !row.category_id).length,
  };

  return (
    <main className="stack catalog-admin-page">
      <section className="card">
        <div className="row spread">
          <div>
            <h1>{t("admin.catalog.title")}</h1>
            <p className="muted">{t("admin.catalog.subtitle")}</p>
          </div>
          <div className="row">
            <Link className="ghost" href={createCategoryHref}>
              {t("admin.catalog.add_category")}
            </Link>
            <Link className="mode-link" href={createKitHref}>
              {t("admin.catalog.add_kit")}
            </Link>
          </div>
        </div>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

      {loadErrors.length > 0 ? (
        <section className="card">
          <h3>{t("admin.catalog.load_errors")}</h3>
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
            {t("admin.catalog.categories_title")}
          </Link>
          <Link className={`catalog-admin-tab ${activeTab === "kits" ? "active" : ""}`} href={kitsTabHref}>
            {t("admin.catalog.kits_title")}
          </Link>
        </nav>
      </section>

      <section className="card">
        <div className="config-metric-grid">
          <article>
            <span>{t("admin.catalog.categories_title")}</span>
            <strong>{catalogStats.categories}</strong>
          </article>
          <article>
            <span>{t("admin.catalog.metrics_active_categories")}</span>
            <strong>{catalogStats.activeCategories}</strong>
          </article>
          <article>
            <span>{t("admin.catalog.kits_title")}</span>
            <strong>{catalogStats.kits}</strong>
          </article>
          <article>
            <span>{t("admin.catalog.metrics_active_kits")}</span>
            <strong>{catalogStats.activeKits}</strong>
          </article>
          <article className={catalogStats.uncategorizedProducts > 0 ? "is-warning" : ""}>
            <span>{t("admin.catalog.metrics_uncategorized_products")}</span>
            <strong>{catalogStats.uncategorizedProducts}</strong>
          </article>
        </div>
      </section>

      {activeTab === "categories" ? (
        <section className="card">
          <div className="row spread">
            <h3>{t("admin.catalog.categories_title")}</h3>
            <form method="get" className="row catalog-admin-filters">
              <input type="hidden" name="tab" value="categories" />
              <label>
                {uiText(language, "common.search")}
                <input type="search" name="category_q" defaultValue={categoryQuery} placeholder={t("admin.catalog.search_placeholder")} />
              </label>
              <label>
                {uiText(language, "common.status")}
                <select name="category_status" defaultValue={categoryStatus}>
                  <option value="all">{uiText(language, "common.all")}</option>
                  <option value="active">{uiText(language, "common.active")}</option>
                  <option value="archived">{uiText(language, "common.archived")}</option>
                </select>
              </label>
              <button type="submit">{uiText(language, "common.apply")}</button>
              <Link className="ghost" href={buildCatalogConfigHref(params, { category_q: undefined, category_status: undefined })}>
                {uiText(language, "common.reset")}
              </Link>
            </form>
          </div>

          {filteredCategories.length === 0 ? (
            <p className="muted">{t("admin.catalog.no_categories")}</p>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{uiText(language, "common.name")}</th>
                    <th>{uiText(language, "common.code")}</th>
                    <th>{uiText(language, "common.description")}</th>
                    <th>{t("admin.catalog.linked_products")}</th>
                    <th>{uiText(language, "common.status")}</th>
                    <th>{uiText(language, "common.order")}</th>
                    <th>{uiText(language, "common.actions")}</th>
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
                        <td>{statusLabel(category.active, language)}</td>
                        <td>{category.display_order}</td>
                        <td>
                          <details className="catalog-actions-menu">
                            <summary className="ghost catalog-actions-trigger">...</summary>
                            <div className="catalog-actions-menu-panel">
                              <Link className="catalog-actions-item" href={editHref}>
                                {uiText(language, "common.edit")}
                              </Link>
                              <form action={toggleAdminCatalogCategoryArchiveAction}>
                                <input type="hidden" name="category_id" value={category.id} />
                                <input type="hidden" name="archive" value={category.active ? "true" : "false"} />
                                <input type="hidden" name="return_to" value={currentHref} />
                                <button type="submit" className="catalog-actions-item">
                                  {category.active ? uiText(language, "common.archive") : uiText(language, "common.unarchive")}
                                </button>
                              </form>
                              <form action={deleteAdminCatalogCategoryAction}>
                                <input type="hidden" name="category_id" value={category.id} />
                                <input type="hidden" name="return_to" value={currentHref} />
                                <button type="submit" className="catalog-actions-item danger">
                                  {uiText(language, "common.delete")}
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
            <h3>{t("admin.catalog.kits_title")}</h3>
            <form method="get" className="row catalog-admin-filters">
              <input type="hidden" name="tab" value="kits" />
              <label>
                {uiText(language, "common.search")}
                <input type="search" name="kit_q" defaultValue={kitQuery} placeholder={t("admin.catalog.search_placeholder")} />
              </label>
              <label>
                {uiText(language, "common.status")}
                <select name="kit_status" defaultValue={kitStatus}>
                  <option value="all">{uiText(language, "common.all")}</option>
                  <option value="active">{uiText(language, "common.active")}</option>
                  <option value="archived">{uiText(language, "common.archived")}</option>
                </select>
              </label>
              <button type="submit">{uiText(language, "common.apply")}</button>
              <Link className="ghost" href={buildCatalogConfigHref(params, { kit_q: undefined, kit_status: undefined })}>
                {uiText(language, "common.reset")}
              </Link>
            </form>
          </div>

          {filteredKits.length === 0 ? (
            <p className="muted">{t("admin.catalog.no_kits")}</p>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{uiText(language, "common.name")}</th>
                    <th>{uiText(language, "common.category")}</th>
                    <th>{uiText(language, "common.details")}</th>
                    <th>{t("admin.catalog.computed_price")}</th>
                    <th>{t("admin.catalog.billed_price")}</th>
                    <th>{t("admin.catalog.price_mode")}</th>
                    <th>{uiText(language, "common.status")}</th>
                    <th>{uiText(language, "common.visibility")}</th>
                    <th>{uiText(language, "common.actions")}</th>
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
                        <td>{formatMoney(kit.computed_price_incl_vat, kit.currency || "EUR", language)}</td>
                        <td>{formatMoney(kit.price_effective_incl_vat || kit.price_incl_vat, kit.currency || "EUR", language)}</td>
                        <td>{kitPriceModeLabel(kit.price_mode, language)}</td>
                        <td>{statusLabel(kit.active, language)}</td>
                        <td>{visibilityLabel(kit.is_public, language)}</td>
                        <td>
                          <AdminKitActionsMenu
                            editHref={editHref}
                            viewCompositionHref={viewCompositionHref}
                            kitId={kit.id}
                            returnTo={currentHref}
                            active={kit.active}
                            labels={{
                              menuAria: t("admin.catalog.kit_actions_menu"),
                              edit: uiText(language, "common.edit"),
                              duplicate: uiText(language, "common.duplicate"),
                              archive: uiText(language, "common.archive"),
                              unarchive: uiText(language, "common.unarchive"),
                              delete: uiText(language, "common.delete"),
                              viewComposition: t("admin.catalog.view_composition"),
                            }}
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
                <h3>{selectedCategory ? t("admin.catalog.edit_category_title") : t("admin.catalog.add_category_title")}</h3>
                <p className="muted">{t("admin.catalog.archived_category_hint")}</p>
              </div>
              <Link className="ghost" href={categoryCloseHref}>
                {uiText(language, "common.close")}
              </Link>
            </header>

            <form action={selectedCategory ? updateAdminCatalogCategoryAction : createAdminCatalogCategoryAction} className="catalog-admin-drawer-form">
              <input type="hidden" name="return_to" value={categoryReturnTo} />
              {selectedCategory ? <input type="hidden" name="category_id" value={selectedCategory.id} /> : null}

              <section className="catalog-admin-drawer-body">
                <label>
                  {uiText(language, "common.name")}
                  <input type="text" name="name" required maxLength={120} defaultValue={selectedCategory?.name || ""} />
                </label>
                <label>
                  {uiText(language, "common.code")}
                  <input type="text" name="code" maxLength={64} defaultValue={selectedCategory?.code || ""} />
                </label>
                <label>
                  {uiText(language, "common.description")}
                  <textarea name="description" rows={3} maxLength={2000} defaultValue={selectedCategory?.description || ""} />
                </label>
                <label>
                  {uiText(language, "common.order")}
                  <input type="number" name="display_order" min={0} step={1} defaultValue={selectedCategory?.display_order ?? 0} />
                </label>
                <label>
                  {uiText(language, "common.status")}
                  <select name="status" defaultValue={selectedCategory?.active === false ? "archived" : "active"}>
                    <option value="active">{uiText(language, "common.active")}</option>
                    <option value="archived">{uiText(language, "common.archived")}</option>
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
                  {t("admin.catalog.requestable_by_teachers")}
                </label>
              </section>

              <footer className="catalog-admin-drawer-footer">
                <button type="submit">{selectedCategory ? uiText(language, "common.save") : t("admin.catalog.create_category")}</button>
                <Link className="ghost" href={categoryCloseHref}>
                  {uiText(language, "common.cancel")}
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
                <h3>{selectedKit ? t("admin.catalog.edit_kit_title") : t("admin.catalog.add_kit_title")}</h3>
                <p className="muted">{t("admin.catalog.archived_kit_hint")}</p>
              </div>
              <Link className="ghost" href={kitCloseHref}>
                {uiText(language, "common.close")}
              </Link>
            </header>

            <form action={selectedKit ? updateAdminCatalogKitAction : createAdminCatalogKitAction} className="catalog-admin-drawer-form">
              <input type="hidden" name="return_to" value={kitReturnTo} />
              {selectedKit ? <input type="hidden" name="kit_id" value={selectedKit.id} /> : null}

              <section className="catalog-admin-drawer-body">
                <article className="card">
                  <h4>{uiText(language, "common.general_information")}</h4>
                  <div className="grid cols-2 config-form-grid">
                    <label>
                      {uiText(language, "common.name")}
                      <input type="text" name="title" required maxLength={255} defaultValue={selectedKit?.title || ""} />
                    </label>
                    <label>
                      {uiText(language, "common.code")}
                      <input type="text" name="code" maxLength={64} defaultValue={selectedKit?.code || ""} />
                    </label>
                    <label>
                      {uiText(language, "common.category")}
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
                      {uiText(language, "common.status")}
                      <select name="status" defaultValue={selectedKit?.active === false ? "archived" : "active"}>
                        <option value="active">{uiText(language, "common.active")}</option>
                        <option value="archived">{uiText(language, "common.archived")}</option>
                      </select>
                    </label>
                    <label className="span-2">
                      {uiText(language, "common.short_description")}
                      <input type="text" name="short_description" maxLength={500} defaultValue={selectedKit?.short_description || ""} />
                    </label>
                    <label className="span-2">
                      {uiText(language, "common.description")}
                      <textarea name="long_description" rows={3} maxLength={12000} defaultValue={selectedKit?.long_description || ""} />
                    </label>
                    <label className="span-2">
                      {uiText(language, "common.image_url")}
                      <input type="url" name="image_url" defaultValue={selectedKit?.image_url || ""} />
                    </label>
                  </div>
                </article>

                <CatalogKitCompositionPricing
                  locale={localeForUiLanguage(language)}
                  labels={{
                    compositionTitle: t("admin.catalog.composition_title"),
                    compositionSubtitle: t("admin.catalog.composition_subtitle"),
                    addLine: t("admin.catalog.add_line"),
                    emptyLine: t("admin.catalog.empty_line"),
                    product: uiText(language, "common.product"),
                    selectProduct: t("admin.catalog.select_product"),
                    quantity: uiText(language, "common.quantity"),
                    order: uiText(language, "common.order"),
                    unitPrice: t("admin.catalog.unit_price"),
                    subtotal: t("admin.catalog.subtotal"),
                    action: uiText(language, "common.actions"),
                    delete: uiText(language, "common.delete"),
                    priceTitle: t("admin.catalog.price_title"),
                    computedPriceAutomatic: t("admin.catalog.computed_price_automatic"),
                    priceMode: t("admin.catalog.price_mode"),
                    useCalculatedPrice: t("admin.catalog.use_calculated_price"),
                    forcePrice: t("admin.catalog.force_price"),
                    billedPriceTtc: t("admin.catalog.billed_price_ttc"),
                    currency: t("admin.catalog.currency"),
                    computedPrice: t("admin.catalog.computed_price"),
                    billedPrice: t("admin.catalog.billed_price"),
                    gap: t("admin.catalog.price_gap"),
                  }}
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
                  <h4>{uiText(language, "common.vat")}</h4>
                  <div className="grid cols-2 config-form-grid">
                    <label>
                      {uiText(language, "common.vat")} (%)
                      <input type="number" name="vat_rate" min={0} max={100} step="0.001" required defaultValue={selectedKit?.vat_rate || "20.000"} />
                    </label>
                  </div>
                </article>

                <article className="card">
                  <h4>{uiText(language, "common.usage")}</h4>
                  <div className="grid cols-2 config-form-grid">
                    <label className="checkline">
                      <input type="hidden" name="use_in_manual_billing" value="false" />
                      <input
                        type="checkbox"
                        name="use_in_manual_billing"
                        value="true"
                        defaultChecked={selectedKit?.use_in_manual_billing ?? true}
                      />
                      {t("admin.catalog.manual_billing")}
                    </label>
                    <label className="checkline">
                      <input type="hidden" name="use_in_enrollments" value="false" />
                      <input
                        type="checkbox"
                        name="use_in_enrollments"
                        value="true"
                        defaultChecked={selectedKit?.use_in_enrollments ?? true}
                      />
                      {t("admin.catalog.enrollments")}
                    </label>
                    <label className="checkline">
                      <input type="hidden" name="is_public" value="false" />
                      <input type="checkbox" name="is_public" value="true" defaultChecked={selectedKit?.is_public ?? true} />
                      {t("admin.catalog.visible_catalog")}
                    </label>
                    <label className="checkline">
                      <input type="hidden" name="purchasable_online" value="false" />
                      <input
                        type="checkbox"
                        name="purchasable_online"
                        value="true"
                        defaultChecked={selectedKit?.purchasable_online ?? false}
                      />
                      {t("admin.catalog.purchasable_online")}
                    </label>
                  </div>
                </article>
              </section>

              <footer className="catalog-admin-drawer-footer">
                <button type="submit">{selectedKit ? uiText(language, "common.save") : t("admin.catalog.create_kit")}</button>
                <Link className="ghost" href={kitCloseHref}>
                  {uiText(language, "common.cancel")}
                </Link>
              </footer>
            </form>
          </article>
        </section>
      ) : null}
    </main>
  );
}
