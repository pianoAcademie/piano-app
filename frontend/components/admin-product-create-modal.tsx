"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";

import type { AdminCatalogCategoryOut, LocationOut } from "../lib/types";
import ModalA11yFrame from "./modal-a11y-frame";

type Props = {
  categories: AdminCatalogCategoryOut[];
  locations: LocationOut[];
  closeHref: string;
  returnTo: string;
  errorMessage?: string;
  createAction: (formData: FormData) => void | Promise<void>;
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
}: Props): JSX.Element {
  const [isVirtual, setIsVirtual] = useState(false);
  const [imageUrl, setImageUrl] = useState("");
  const [previewUrl, setPreviewUrl] = useState("");
  const [uploadState, setUploadState] = useState<UploadState>({ status: "idle", message: "" });
  const fileInputRef = useRef<HTMLInputElement | null>(null);

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
      setUploadState({ status: "error", message: "Fichier trop lourd (max 5 MB)." });
      return;
    }

    if (!ALLOWED_TYPES.has((file.type || "").toLowerCase())) {
      event.target.value = "";
      replacePreviewUrl("");
      setUploadState({ status: "error", message: "Formats autorises: JPG, PNG, WEBP." });
      return;
    }

    replacePreviewUrl(URL.createObjectURL(file));
    setUploadState({
      status: "ok",
      message: "Image prete. Elle sera importee automatiquement a la creation du produit.",
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
      <ModalA11yFrame className="modal-panel product-edit-modal product-create-modal" label="Ajouter produit" closeHref={closeHref}>
        <div className="row spread">
          <h3 className="modal-title">Ajouter un produit</h3>
          <Link href={closeHref} className="ghost" aria-label="Fermer">
            Fermer
          </Link>
        </div>
        <section className="modal-card product-create-modal-card">
          <form action={createAction} encType="multipart/form-data" className="product-edit-modal-form">
            <input type="hidden" name="return_to" value={returnTo} />
            <section className="product-edit-modal-body">
              {errorMessage ? <p className="flash-err">{errorMessage}</p> : null}
              <div className="grid cols-3 config-form-grid">
                <label className="span-2">
                  Titre *
                  <input type="text" name="title" required maxLength={255} placeholder="Partition Niveau 1" />
                </label>

                <label>
                  Categorie *
                  <select name="category_id" defaultValue="" required>
                    <option value="">Selectionner...</option>
                    {categories.map((categoryRow) => (
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

                {!isVirtual ? (
                  <label>
                    Local principal (optionnel)
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
                  Code-barres (optionnel)
                  <input type="text" name="barcode" maxLength={120} />
                </label>

                <label>
                  Stock de reserve (optionnel)
                  <input type="number" name="reserve_stock" min="0" step="1" defaultValue="0" disabled={isVirtual} />
                </label>

                <label>
                  Statut commande (optionnel)
                  <select name="reorder_status" defaultValue="NORMAL" disabled={isVirtual}>
                    <option value="NORMAL">Normal</option>
                    <option value="TO_ORDER">A commander</option>
                    <option value="ORDERED">Commande passee</option>
                    <option value="RECEIVED">Recu</option>
                  </select>
                </label>

                <fieldset className="span-3 product-edit-radio-group">
                  <legend>Type de produit</legend>
                  <div className="row">
                    <label className="checkline">
                      <input
                        type="radio"
                        name="is_virtual"
                        value="false"
                        checked={!isVirtual}
                        onChange={() => setIsVirtual(false)}
                      />
                      Produit physique (stock gere)
                    </label>
                    <label className="checkline">
                      <input
                        type="radio"
                        name="is_virtual"
                        value="true"
                        checked={isVirtual}
                        onChange={() => setIsVirtual(true)}
                      />
                      Produit virtuel (pas de stock)
                    </label>
                  </div>
                </fieldset>

                <section className="span-3 product-image-uploader">
                  <div className="product-image-preview" aria-hidden="true">
                    {displayedImage ? <img src={displayedImage} alt="Apercu produit" /> : <span>Apercu</span>}
                  </div>
                  <div className="product-image-actions">
                    <p className="muted">JPG, PNG, WEBP · 5 MB max.</p>
                    <div className="row wrap gap-xs">
                      <button type="button" className="ghost" onClick={() => fileInputRef.current?.click()}>
                        Importer une image
                      </button>
                      <button type="button" className="ghost danger" onClick={clearVisual} disabled={!displayedImage}>
                        Supprimer
                      </button>
                    </div>
                    {uploadState.message ? (
                      <p className={uploadState.status === "error" ? "flash-err" : uploadState.status === "ok" ? "flash-ok" : "muted"}>
                        {uploadState.message}
                      </p>
                    ) : (
                      <p className="muted">Le fichier sera envoye lors de la creation du produit.</p>
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
                    Visuel URL (optionnel)
                    <input
                      type="text"
                      name="image_url"
                      value={imageUrl}
                      onChange={(event) => setImageUrl(event.target.value)}
                      placeholder="https://... ou /admin/products/images/..."
                    />
                    <small className="muted">Tu peux coller une URL, ou choisir un fichier. Si les deux sont renseignes, le fichier importe prendra le dessus.</small>
                  </label>
                </section>

                <label>
                  Lien web (optionnel)
                  <input type="url" name="web_link" />
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
              </div>
            </section>

            <footer className="product-edit-modal-footer">
              <Link className="ghost" href={closeHref}>
                Annuler
              </Link>
              <button type="submit">Ajouter</button>
            </footer>
          </form>
        </section>
      </ModalA11yFrame>
    </section>
  );
}
