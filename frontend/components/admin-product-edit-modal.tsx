"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent } from "react";

import type { AdminCatalogCategoryOut, AdminCatalogProductOut, LocationOut } from "../lib/types";
import { type UiLanguage, uiText } from "../lib/ui-i18n";
import ModalA11yFrame from "./modal-a11y-frame";

type ProductTab = "general" | "price" | "stock" | "content";

type Props = {
  product: AdminCatalogProductOut;
  categories: AdminCatalogCategoryOut[];
  locations: LocationOut[];
  closeHref: string;
  returnTo: string;
  entriesHref: string;
  transfersHref: string;
  updateAction: (formData: FormData) => void | Promise<void>;
  language: UiLanguage;
};

type UploadState = {
  status: "idle" | "uploading" | "ok" | "error";
  message: string;
};

export default function AdminProductEditModal({
  product,
  categories,
  locations,
  closeHref,
  returnTo,
  entriesHref,
  transfersHref,
  updateAction,
  language,
}: Props): JSX.Element {
  const [activeTab, setActiveTab] = useState<ProductTab>("general");
  const [isMobile, setIsMobile] = useState(false);
  const [isVirtual, setIsVirtual] = useState(product.is_virtual);
  const [imageUrl, setImageUrl] = useState(product.image_url || "");
  const [uploadState, setUploadState] = useState<UploadState>({ status: "idle", message: "" });
  const [openSections, setOpenSections] = useState<Record<ProductTab, boolean>>({
    general: true,
    price: false,
    stock: false,
    content: false,
  });
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const t = (key: string) => uiText(language, key);
  const tabLabels: Array<{ id: ProductTab; label: string }> = [
    { id: "general", label: t("admin.products.tab_general") },
    { id: "price", label: t("admin.products.tab_price") },
    { id: "stock", label: t("admin.products.tab_stock") },
    { id: "content", label: t("admin.products.tab_content") },
  ];

  useEffect(() => {
    const sync = (): void => {
      setIsMobile(window.innerWidth < 768);
    };
    sync();
    window.addEventListener("resize", sync);
    return () => window.removeEventListener("resize", sync);
  }, []);

  const categoryLabel = useMemo(() => product.category_name || t("admin.products.no_category"), [product.category_name, language]);

  const subtypeLabel = isVirtual ? t("admin.products.subtype_virtual") : t("admin.products.subtype_physical");

  const toggleSection = (tab: ProductTab): void => {
    setOpenSections((current) => ({ ...current, [tab]: !current[tab] }));
  };

  const handleFileSelected = async (event: ChangeEvent<HTMLInputElement>): Promise<void> => {
    const file = event.target.files?.[0] ?? null;
    if (!file) {
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setUploadState({ status: "error", message: t("admin.products.file_too_large") });
      event.target.value = "";
      return;
    }

    const allowed = new Set(["image/jpeg", "image/jpg", "image/png", "image/webp"]);
    if (!allowed.has((file.type || "").toLowerCase())) {
      setUploadState({ status: "error", message: t("admin.products.invalid_image_format") });
      event.target.value = "";
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    setUploadState({ status: "uploading", message: t("admin.products.image_upload_in_progress") });

    try {
      const response = await fetch(`/admin/products/${product.id}/image`, {
        method: "POST",
        body: formData,
      });
      const payload = (await response.json()) as { image_url?: string; detail?: string };
      if (!response.ok || !payload.image_url) {
        setUploadState({ status: "error", message: payload.detail || t("admin.products.image_upload_failed") });
        event.target.value = "";
        return;
      }
      setImageUrl(payload.image_url);
      setUploadState({ status: "ok", message: t("admin.products.image_uploaded") });
    } catch {
      setUploadState({ status: "error", message: t("admin.products.network_upload_error") });
    } finally {
      event.target.value = "";
    }
  };

  const sectionContent = (tab: ProductTab): JSX.Element => {
    if (tab === "general") {
      return (
        <section className="product-edit-section-grid">
          <label className="span-2">
            {t("common.name")}
            <input type="text" name="title" defaultValue={product.title} required maxLength={255} />
          </label>
          <label>
            {t("common.category")}
            <select name="category_id" defaultValue={product.category_id ?? ""}>
              <option value="">-</option>
              {categories.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
            </select>
          </label>
          {!isVirtual ? (
            <label>
              {t("admin.products.main_location")}
              <select name="primary_location_id" defaultValue={product.primary_location_id ?? ""}>
                <option value="">-</option>
                {locations.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <input type="hidden" name="primary_location_id" value={product.primary_location_id ?? ""} />
          )}
          <label>
            {t("admin.products.barcode")}
            <input type="text" name="barcode" defaultValue={product.barcode || ""} maxLength={120} />
          </label>
          <label>
            {t("admin.products.reorder_status_label")}
            <select name="reorder_status" defaultValue={product.reorder_status} disabled={isVirtual}>
              <option value="NORMAL">{t("admin.products.reorder_status_normal")}</option>
              <option value="TO_ORDER">{t("admin.products.reorder_status_to_order")}</option>
              <option value="ORDERED">{t("admin.products.reorder_status_ordered")}</option>
              <option value="RECEIVED">{t("admin.products.reorder_status_received")}</option>
            </select>
          </label>

          <fieldset className="span-3 product-edit-radio-group">
            <legend>{t("admin.products.product_type")}</legend>
            <label className="checkline">
              <input
                type="radio"
                name="is_virtual"
                value="false"
                checked={!isVirtual}
                onChange={() => setIsVirtual(false)}
              />
              {t("admin.products.product_physical")}
            </label>
            <label className="checkline">
              <input type="radio" name="is_virtual" value="true" checked={isVirtual} onChange={() => setIsVirtual(true)} />
              {t("admin.products.product_virtual")}
            </label>
          </fieldset>

          <section className="span-3 product-image-uploader">
            <div className="product-image-preview" aria-hidden="true">
              {imageUrl ? <img src={imageUrl} alt={t("admin.products.image_preview_alt")} /> : <span>{t("admin.products.image_preview_label")}</span>}
            </div>
            <div className="product-image-actions">
              <p className="muted">{t("admin.products.image_help")}</p>
              <div className="row wrap gap-xs">
                <button type="button" className="ghost" onClick={() => fileInputRef.current?.click()} disabled={uploadState.status === "uploading"}>
                  {t("admin.products.import_image")}
                </button>
                <button
                  type="button"
                  className="ghost danger"
                  onClick={() => setImageUrl("")}
                  disabled={!imageUrl || uploadState.status === "uploading"}
                >
                  {t("common.delete")}
                </button>
              </div>
              {uploadState.message ? (
                <p className={uploadState.status === "error" ? "flash-err" : uploadState.status === "ok" ? "flash-ok" : "muted"}>{uploadState.message}</p>
              ) : null}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              name="file"
              accept="image/jpeg,image/jpg,image/png,image/webp"
              onChange={handleFileSelected}
              hidden
            />
            <input type="hidden" name="image_url" value={imageUrl} />
            <label className="span-3 product-image-url-field">
              {t("admin.products.image_url_label")}
              <input type="text" value={imageUrl} onChange={(event) => setImageUrl(event.target.value)} placeholder={t("admin.products.image_url_placeholder")} />
              <small className="muted">{t("admin.products.image_url_edit_help")}</small>
            </label>
          </section>
        </section>
      );
    }

    if (tab === "price") {
      return (
        <section className="product-edit-section-grid">
          <label>
            {t("admin.products.price_excl_label")}
            <input type="number" name="price_excl_vat" min="0" step="0.01" defaultValue={product.price_excl_vat} required />
          </label>
          <label>
            {t("admin.products.vat_label")}
            <input type="number" name="vat_rate" min="0" max="100" step="0.001" defaultValue={product.vat_rate} required />
          </label>
          <label>
            {t("admin.products.column_price_ttc")}
            <input type="number" name="price_incl_vat" min="0" step="0.01" defaultValue={product.price_incl_vat} required />
          </label>
          <p className="muted span-3">{t("admin.products.price_auto_hint")}</p>
        </section>
      );
    }

    if (tab === "stock") {
      if (isVirtual) {
        return <p className="muted">{t("admin.products.virtual_no_stock")}</p>;
      }
      return (
        <section className="product-edit-section-grid">
          <label>
            {t("admin.products.column_reserve_stock")}
            <input type="number" name="reserve_stock" min="0" step="1" defaultValue={product.reserve_stock} required />
          </label>
          <label>
            {t("admin.products.global_stock_read_only")}
            <input type="text" value={String(product.stock_global_quantity)} readOnly />
          </label>
          <div className="row wrap gap-xs span-3">
            <Link className="ghost" href={entriesHref}>
              {t("admin.products.view_stock_entries")}
            </Link>
            <Link className="ghost" href={transfersHref}>
              {t("admin.products.view_transfers")}
            </Link>
          </div>
        </section>
      );
    }

    return (
      <section className="product-edit-section-grid">
        <label className="span-2">
          {t("admin.products.web_link_label")}
          <input type="url" name="web_link" defaultValue={product.web_link || ""} />
        </label>
        <label className="span-3">
          {t("admin.products.short_description_label")}
          <textarea name="short_description" rows={2} maxLength={500} defaultValue={product.short_description || ""} />
        </label>
        <label className="span-3">
          {t("admin.products.long_description_label")}
          <textarea name="long_description" rows={5} maxLength={12000} defaultValue={product.long_description || ""} />
        </label>
        <label className="checkline">
          <input type="checkbox" name="purchasable_online" defaultChecked={product.purchasable_online} />
          {t("admin.products.purchasable_online")}
        </label>
        <label className="checkline">
          <input type="checkbox" name="is_public" defaultChecked={product.is_public} />
          {t("common.public")}
        </label>
        <label className="checkline">
          <input type="checkbox" name="active" defaultChecked={product.active} />
          {t("common.active")}
        </label>
      </section>
    );
  };

  return (
    <section className="modal-overlay" aria-hidden="false">
      <ModalA11yFrame className="modal-panel product-edit-modal" label={t("admin.products.edit_product_modal_title")} closeHref={closeHref}>
        <header className="product-edit-modal-header">
          <div>
            <h3 className="modal-title">{t("admin.products.edit_product_modal_title")}</h3>
            <p className="muted">
              {categoryLabel} · {subtypeLabel}
            </p>
          </div>
          <Link href={closeHref} className="ghost" aria-label={t("common.close")}>
            ✕
          </Link>
        </header>

        {!isMobile ? (
          <nav className="product-edit-tabs" aria-label={t("admin.products.edit_sections_aria")}>
            {tabLabels.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={activeTab === tab.id ? "mode-link" : "ghost"}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        ) : null}

        <form action={updateAction} className="product-edit-modal-form">
          <input type="hidden" name="product_id" value={product.id} />
          <input type="hidden" name="return_to" value={returnTo} />
          {isVirtual ? <input type="hidden" name="reserve_stock" value="0" /> : null}

          <section className="product-edit-modal-body">
            {!isMobile
              ? tabLabels.map((tab) => (
                  <section key={tab.id} hidden={activeTab !== tab.id}>
                    {sectionContent(tab.id)}
                  </section>
                ))
              : tabLabels.map((tab) => (
                  <section key={tab.id} className="product-edit-mobile-accordion">
                    <button type="button" className="ghost product-edit-mobile-toggle" onClick={() => toggleSection(tab.id)}>
                      {tab.label}
                    </button>
                    {openSections[tab.id] ? <div className="top-gap-sm">{sectionContent(tab.id)}</div> : null}
                  </section>
                ))}
          </section>

          <footer className="product-edit-modal-footer">
            <Link className="ghost" href={closeHref}>
              {t("common.cancel")}
            </Link>
            <button type="submit">{t("common.save")}</button>
          </footer>
        </form>
      </ModalA11yFrame>
    </section>
  );
}
