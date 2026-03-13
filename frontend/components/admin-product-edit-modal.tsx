"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent } from "react";

import type { AdminCatalogCategoryOut, AdminCatalogProductOut, LocationOut } from "../lib/types";
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
};

const TAB_LABELS: Array<{ id: ProductTab; label: string }> = [
  { id: "general", label: "General" },
  { id: "price", label: "Prix" },
  { id: "stock", label: "Stock" },
  { id: "content", label: "Contenu & visibilite" },
];

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

  useEffect(() => {
    const sync = (): void => {
      setIsMobile(window.innerWidth < 768);
    };
    sync();
    window.addEventListener("resize", sync);
    return () => window.removeEventListener("resize", sync);
  }, []);

  const categoryLabel = useMemo(() => product.category_name || "Sans categorie", [product.category_name]);

  const subtypeLabel = isVirtual ? "Virtuel" : "Physique";

  const toggleSection = (tab: ProductTab): void => {
    setOpenSections((current) => ({ ...current, [tab]: !current[tab] }));
  };

  const handleFileSelected = async (event: ChangeEvent<HTMLInputElement>): Promise<void> => {
    const file = event.target.files?.[0] ?? null;
    if (!file) {
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setUploadState({ status: "error", message: "Fichier trop lourd (max 5 MB)." });
      event.target.value = "";
      return;
    }

    const allowed = new Set(["image/jpeg", "image/jpg", "image/png", "image/webp"]);
    if (!allowed.has((file.type || "").toLowerCase())) {
      setUploadState({ status: "error", message: "Formats autorises: JPG, PNG, WEBP." });
      event.target.value = "";
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    setUploadState({ status: "uploading", message: "Import en cours..." });

    try {
      const response = await fetch(`/api/admin/products/${product.id}/image`, {
        method: "POST",
        body: formData,
      });
      const payload = (await response.json()) as { image_url?: string; detail?: string };
      if (!response.ok || !payload.image_url) {
        setUploadState({ status: "error", message: payload.detail || "Echec de l import image." });
        event.target.value = "";
        return;
      }
      setImageUrl(payload.image_url);
      setUploadState({ status: "ok", message: "Image importee." });
    } catch {
      setUploadState({ status: "error", message: "Erreur reseau pendant l import." });
    } finally {
      event.target.value = "";
    }
  };

  const sectionContent = (tab: ProductTab): JSX.Element => {
    if (tab === "general") {
      return (
        <section className="product-edit-section-grid">
          <label className="span-2">
            Titre
            <input type="text" name="title" defaultValue={product.title} required maxLength={255} />
          </label>
          <label>
            Categorie
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
              Local principal
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
            Code-barres
            <input type="text" name="barcode" defaultValue={product.barcode || ""} maxLength={120} />
          </label>
          <label>
            Statut commande
            <select name="reorder_status" defaultValue={product.reorder_status} disabled={isVirtual}>
              <option value="NORMAL">Normal</option>
              <option value="TO_ORDER">A commander</option>
              <option value="ORDERED">Commande passee</option>
              <option value="RECEIVED">Recu</option>
            </select>
          </label>

          <fieldset className="span-3 product-edit-radio-group">
            <legend>Type produit</legend>
            <label className="checkline">
              <input
                type="radio"
                name="is_virtual"
                value="false"
                checked={!isVirtual}
                onChange={() => setIsVirtual(false)}
              />
              Physique (stock gere)
            </label>
            <label className="checkline">
              <input type="radio" name="is_virtual" value="true" checked={isVirtual} onChange={() => setIsVirtual(true)} />
              Virtuel (pas de stock)
            </label>
          </fieldset>

          <section className="span-3 product-image-uploader">
            <div className="product-image-preview" aria-hidden="true">
              {imageUrl ? <img src={imageUrl} alt={`Image ${product.title}`} /> : <span>Apercu</span>}
            </div>
            <div className="product-image-actions">
              <p className="muted">JPG, PNG, WEBP · 5 MB max.</p>
              <div className="row wrap gap-xs">
                <button type="button" className="ghost" onClick={() => fileInputRef.current?.click()} disabled={uploadState.status === "uploading"}>
                  Importer une image
                </button>
                <button
                  type="button"
                  className="ghost danger"
                  onClick={() => setImageUrl("")}
                  disabled={!imageUrl || uploadState.status === "uploading"}
                >
                  Supprimer
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
              URL image
              <input type="url" value={imageUrl} onChange={(event) => setImageUrl(event.target.value)} placeholder="https://..." />
              <small className="muted">Champ optionnel pour coller ou corriger directement le visuel sans ouvrir d options avancees.</small>
            </label>
          </section>
        </section>
      );
    }

    if (tab === "price") {
      return (
        <section className="product-edit-section-grid">
          <label>
            Tarif HT
            <input type="number" name="price_excl_vat" min="0" step="0.01" defaultValue={product.price_excl_vat} required />
          </label>
          <label>
            TVA (%)
            <input type="number" name="vat_rate" min="0" max="100" step="0.001" defaultValue={product.vat_rate} required />
          </label>
          <label>
            Tarif TTC
            <input type="number" name="price_incl_vat" min="0" step="0.01" defaultValue={product.price_incl_vat} required />
          </label>
          <p className="muted span-3">TTC calcule automatiquement si HT + TVA sont modifies.</p>
        </section>
      );
    }

    if (tab === "stock") {
      if (isVirtual) {
        return <p className="muted">Produit virtuel: pas de stock local ni reserve.</p>;
      }
      return (
        <section className="product-edit-section-grid">
          <label>
            Stock reserve
            <input type="number" name="reserve_stock" min="0" step="1" defaultValue={product.reserve_stock} required />
          </label>
          <label>
            Stock global (lecture seule)
            <input type="text" value={String(product.stock_global_quantity)} readOnly />
          </label>
          <div className="row wrap gap-xs span-3">
            <Link className="ghost" href={entriesHref}>
              Voir entrees stock
            </Link>
            <Link className="ghost" href={transfersHref}>
              Voir transferts
            </Link>
          </div>
        </section>
      );
    }

    return (
      <section className="product-edit-section-grid">
        <label className="span-2">
          Lien web
          <input type="url" name="web_link" defaultValue={product.web_link || ""} />
        </label>
        <label className="span-3">
          Description courte
          <textarea name="short_description" rows={2} maxLength={500} defaultValue={product.short_description || ""} />
        </label>
        <label className="span-3">
          Description longue
          <textarea name="long_description" rows={5} maxLength={12000} defaultValue={product.long_description || ""} />
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
      </section>
    );
  };

  return (
    <section className="modal-overlay" aria-hidden="false">
      <ModalA11yFrame className="modal-panel product-edit-modal" label="Modifier produit" closeHref={closeHref}>
        <header className="product-edit-modal-header">
          <div>
            <h3 className="modal-title">Modifier produit</h3>
            <p className="muted">
              {categoryLabel} · {subtypeLabel}
            </p>
          </div>
          <Link href={closeHref} className="ghost" aria-label="Fermer">
            ✕
          </Link>
        </header>

        {!isMobile ? (
          <nav className="product-edit-tabs" aria-label="Sections edition produit">
            {TAB_LABELS.map((tab) => (
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
              ? TAB_LABELS.map((tab) => (
                  <section key={tab.id} hidden={activeTab !== tab.id}>
                    {sectionContent(tab.id)}
                  </section>
                ))
              : TAB_LABELS.map((tab) => (
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
              Annuler
            </Link>
            <button type="submit">Enregistrer</button>
          </footer>
        </form>
      </ModalA11yFrame>
    </section>
  );
}
