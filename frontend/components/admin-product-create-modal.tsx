"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";

import type { AdminCatalogCategoryOut, LocationOut } from "../lib/types";
import { type UiLanguage, uiText } from "../lib/ui-i18n";
import ModalA11yFrame from "./modal-a11y-frame";

type Props = {
  categories: AdminCatalogCategoryOut[];
  locations: LocationOut[];
  closeHref: string;
  returnTo: string;
  errorMessage?: string;
  createAction: (formData: FormData) => void | Promise<void>;
  language: UiLanguage;
};

type UploadState = {
  status: "idle" | "ok" | "error";
  message: string;
};

const ALLOWED_TYPES = new Set(["image/jpeg", "image/jpg", "image/png", "image/webp"]);
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

export default function AdminProductCreateModal({
  categories,
  locations,
  closeHref,
  returnTo,
  errorMessage,
  createAction,
  language,
}: Props): JSX.Element {
  const [isVirtual, setIsVirtual] = useState(false);
  const [imageUrl, setImageUrl] = useState("");
  const [previewUrl, setPreviewUrl] = useState("");
  const [uploadState, setUploadState] = useState<UploadState>({ status: "idle", message: "" });
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  useEffect(() => {
    return () => {
      if (previewUrl.startsWith("blob:")) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  const replacePreviewUrl = (nextUrl: string): void => {
    setPreviewUrl((current) => {
      if (current.startsWith("blob:")) {
        URL.revokeObjectURL(current);
      }
      return nextUrl;
    });
  };

  const handleFileSelected = (event: ChangeEvent<HTMLInputElement>): void => {
    const file = event.target.files?.[0] ?? null;
    if (!file) {
      replacePreviewUrl("");
      setUploadState({ status: "idle", message: "" });
      return;
    }

    if (file.size > MAX_IMAGE_BYTES) {
      event.target.value = "";
      replacePreviewUrl("");
      setUploadState({ status: "error", message: t("admin.products.file_too_large") });
      return;
    }

    if (!ALLOWED_TYPES.has((file.type || "").toLowerCase())) {
      event.target.value = "";
      replacePreviewUrl("");
      setUploadState({ status: "error", message: t("admin.products.invalid_image_format") });
      return;
    }

    replacePreviewUrl(URL.createObjectURL(file));
    setUploadState({
      status: "ok",
      message: t("admin.products.image_ready"),
    });
  };

  const clearVisual = (): void => {
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    replacePreviewUrl("");
    setImageUrl("");
    setUploadState({ status: "idle", message: "" });
  };

  const displayedImage = previewUrl || imageUrl;

  return (
    <section className="modal-overlay">
      <ModalA11yFrame className="modal-panel product-edit-modal product-create-modal" label={t("admin.products.add_product_modal_title")} closeHref={closeHref}>
        <div className="row spread">
          <h3 className="modal-title">{t("admin.products.add_product_modal_title")}</h3>
          <Link href={closeHref} className="ghost" aria-label={t("common.close")}>
            {t("common.close")}
          </Link>
        </div>
        <section className="modal-card product-create-modal-card">
          <form action={createAction} encType="multipart/form-data" className="product-edit-modal-form">
            <input type="hidden" name="return_to" value={returnTo} />
            <section className="product-edit-modal-body">
              {errorMessage ? <p className="flash-err">{errorMessage}</p> : null}
              <div className="grid cols-3 config-form-grid">
                <label className="span-2">
                  {t("common.name")} *
                  <input type="text" name="title" required maxLength={255} placeholder={t("admin.products.product_title_placeholder")} />
                </label>

                <label>
                  {t("common.category")} *
                  <select name="category_id" defaultValue="" required>
                    <option value="">{t("common.choose")}...</option>
                    {categories.map((categoryRow) => (
                      <option key={categoryRow.id} value={categoryRow.id}>
                        {categoryRow.name}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  {t("admin.products.column_price_ttc")} *
                  <input type="number" name="price_incl_vat" min="0" step="0.01" defaultValue="0.00" required />
                </label>

                <label>
                  {t("admin.products.price_excl_optional")}
                  <input type="number" name="price_excl_vat" min="0" step="0.01" placeholder={t("admin.products.price_excl_placeholder")} />
                </label>

                <label>
                  {t("admin.products.vat_optional")}
                  <input type="number" name="vat_rate" min="0" max="100" step="0.001" defaultValue="20.000" />
                </label>

                {!isVirtual ? (
                  <label>
                    {t("admin.products.main_location_optional")}
                    <select name="primary_location_id" defaultValue="">
                      <option value="">-</option>
                      {locations.map((location) => (
                        <option key={location.id} value={location.id}>
                          {location.name}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <input type="hidden" name="primary_location_id" value="" />
                )}

                <label>
                  {t("admin.products.barcode_optional")}
                  <input type="text" name="barcode" maxLength={120} />
                </label>

                <label>
                  {t("admin.products.reserve_stock_optional")}
                  <input type="number" name="reserve_stock" min="0" step="1" defaultValue="0" disabled={isVirtual} />
                </label>

                <label>
                  {t("admin.products.reorder_status_optional")}
                  <select name="reorder_status" defaultValue="NORMAL" disabled={isVirtual}>
                    <option value="NORMAL">{t("admin.products.reorder_status_normal")}</option>
                    <option value="TO_ORDER">{t("admin.products.reorder_status_to_order")}</option>
                    <option value="ORDERED">{t("admin.products.reorder_status_ordered")}</option>
                    <option value="RECEIVED">{t("admin.products.reorder_status_received")}</option>
                  </select>
                </label>

                <fieldset className="span-3 product-edit-radio-group">
                  <legend>{t("admin.products.product_type")}</legend>
                  <div className="row">
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
                      <input
                        type="radio"
                        name="is_virtual"
                        value="true"
                        checked={isVirtual}
                        onChange={() => setIsVirtual(true)}
                      />
                      {t("admin.products.product_virtual")}
                    </label>
                  </div>
                </fieldset>

                <label className="span-3">
                  {t("admin.products.nature_label")}
                  <select name="nature" defaultValue="material">
                    <option value="material">{t("admin.products.nature_material")}</option>
                    <option value="service">{t("admin.products.nature_service")}</option>
                  </select>
                  <small className="muted">{t("admin.products.nature_help")}</small>
                </label>

                <section className="span-3 product-image-uploader">
                  <div className="product-image-preview" aria-hidden="true">
                    {displayedImage ? <img src={displayedImage} alt={t("admin.products.image_preview_alt")} /> : <span>{t("admin.products.image_preview_label")}</span>}
                  </div>
                  <div className="product-image-actions">
                    <p className="muted">{t("admin.products.image_help")}</p>
                    <div className="row wrap gap-xs">
                      <button type="button" className="ghost" onClick={() => fileInputRef.current?.click()}>
                        {t("admin.products.import_image")}
                      </button>
                      <button type="button" className="ghost danger" onClick={clearVisual} disabled={!displayedImage}>
                        {t("common.delete")}
                      </button>
                    </div>
                    {uploadState.message ? (
                      <p className={uploadState.status === "error" ? "flash-err" : uploadState.status === "ok" ? "flash-ok" : "muted"}>
                        {uploadState.message}
                      </p>
                    ) : (
                      <p className="muted">{t("admin.products.image_upload_note")}</p>
                    )}
                  </div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    name="image_file"
                    accept="image/jpeg,image/jpg,image/png,image/webp"
                    onChange={handleFileSelected}
                    hidden
                  />
                  <label className="span-3 product-image-url-field">
                    {t("admin.products.image_url_optional")}
                    <input
                      type="text"
                      name="image_url"
                      value={imageUrl}
                      onChange={(event) => setImageUrl(event.target.value)}
                      placeholder={t("admin.products.image_url_placeholder")}
                    />
                    <small className="muted">{t("admin.products.image_url_help")}</small>
                  </label>
                </section>

                <label>
                  {t("admin.products.web_link_optional")}
                  <input type="url" name="web_link" />
                </label>

                <label className="span-2">
                  {t("admin.products.short_description_optional")}
                  <input type="text" name="short_description" maxLength={500} />
                </label>

                <label className="span-3">
                  {t("admin.products.long_description_optional")}
                  <textarea name="long_description" rows={3} maxLength={12000} />
                </label>

                <label className="checkline">
                  <input type="checkbox" name="purchasable_online" />
                  {t("admin.products.purchasable_online")}
                </label>

                <label className="checkline">
                  <input type="checkbox" name="is_public" defaultChecked />
                  {t("admin.products.public_visible_client")}
                </label>

                <label className="checkline">
                  <input type="checkbox" name="active" defaultChecked />
                  {t("common.active")}
                </label>
              </div>
            </section>

            <footer className="product-edit-modal-footer">
              <Link className="ghost" href={closeHref}>
                {t("common.cancel")}
              </Link>
              <button type="submit">{t("admin.products.add_product")}</button>
            </footer>
          </form>
        </section>
      </ModalA11yFrame>
    </section>
  );
}
