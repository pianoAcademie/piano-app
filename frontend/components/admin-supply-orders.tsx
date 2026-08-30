"use client";

import { useState, type ReactNode } from "react";
import { useFormStatus } from "react-dom";
import { completeAdminSupplyOrderAction, createAdminSupplyOrderAction } from "../lib/actions";
import type { AdminSupplyOrderOut } from "../lib/types";
import type { UiLanguage } from "../lib/ui-i18n";

function PendingFields({ children, language }: { children: ReactNode; language: UiLanguage }): JSX.Element {
  const { pending } = useFormStatus();
  return <fieldset className="supply-order-fields" disabled={pending} aria-busy={pending}>
    {children}
    {pending ? <p role="status">{language === "en" ? "Saving… Please wait." : "Enregistrement en cours… Veuillez patienter."}</p> : null}
  </fieldset>;
}

export default function AdminSupplyOrders({ orders, products, locations, submissionId, today, language }: {
  orders: AdminSupplyOrderOut[];
  products: { id: string; title: string }[];
  locations: { id: string; name: string }[];
  submissionId: string;
  today: string;
  language: UiLanguage;
}): JSX.Element {
  const t = (fr: string, en: string) => language === "en" ? en : fr;
  const [items, setItems] = useState([{ product_id: "", product_title: "", quantity: 1 }]);
  const [orderedDate, setOrderedDate] = useState(today);
  const dateLabel = (value: string) => new Intl.DateTimeFormat(language === "en" ? "en-GB" : "fr-FR", { timeZone: "UTC" }).format(new Date(`${value}T12:00:00Z`));
  const total = items.reduce((sum, item) => sum + (item.quantity || 0), 0);

  return <section className="card supply-orders">
    <h3>{t("Commandes fournisseurs", "Supplier orders")}</h3>
    <p className="muted">{t("Les quantités commandées restent séparées du stock disponible. Seule la réception physique ajoute des exemplaires au stock.", "Ordered quantities stay separate from available stock. Only physical receipt adds units to stock.")}</p>
    <details className="top-gap-sm">
      <summary className="mode-link">{t("Enregistrer une commande déjà passée", "Record an order already placed")}</summary>
      <form action={createAdminSupplyOrderAction} className="top-gap-sm">
        <PendingFields language={language}>
          <input type="hidden" name="submission_id" value={submissionId} />
          <input type="hidden" name="items" value={JSON.stringify(items.map(item => ({ ...item, product_id: item.product_id === "unlisted" ? null : item.product_id })))} />
          <div className="grid cols-2 config-form-grid">
            <label>{t("Référence de commande (optionnel)", "Order reference (optional)")}<input name="reference" maxLength={255} /></label>
            <label>{t("Fournisseur (optionnel)", "Supplier (optional)")}<input name="supplier" maxLength={255} /></label>
            <label>{t("Lieu de livraison", "Delivery location")}<select name="location_id" defaultValue="" required>
              <option value="">{t("Choisir un lieu", "Select a location")}</option>
              {locations.map(location => <option key={location.id} value={location.id}>{location.name}</option>)}
            </select></label>
            <label>{t("Date de commande", "Order date")}<input type="date" name="ordered_date" value={orderedDate} max={today} required onChange={e => setOrderedDate(e.target.value)} /></label>
            <label>{t("Livraison prévue le", "Expected delivery date")}<input type="date" name="expected_delivery_date" min={orderedDate} required /></label>
          </div>
          <div className="supply-order-lines top-gap-sm">
            {items.map((item, index) => <div className="supply-order-line" key={index}>
              <label>{t("Produit", "Product")}<select value={item.product_id} required onChange={e => setItems(rows => rows.map((row, i) => i === index ? { ...row, product_id: e.target.value } : row))}>
                <option value="">{t("Choisir un produit", "Select a product")}</option>
                <option value="unlisted">{t("Produit non encore référencé", "Product not yet in catalog")}</option>
                {products.map(product => <option key={product.id} value={product.id} disabled={items.some((other, i) => i !== index && other.product_id === product.id)}>{product.title}</option>)}
              </select>{item.product_id === "unlisted" ? <input aria-label={t(`Nom du produit ligne ${index + 1}`, `Product name line ${index + 1}`)} placeholder={t("Nom exact du produit", "Exact product name")} value={item.product_title} maxLength={255} required onChange={e => setItems(rows => rows.map((row, i) => i === index ? { ...row, product_title: e.target.value } : row))} /> : null}</label>
              <label>{t("Quantité commandée", "Ordered quantity")}<input type="number" min={1} max={1000000} step={1} required value={item.quantity || ""} onChange={e => setItems(rows => rows.map((row, i) => i === index ? { ...row, quantity: Number(e.target.value) } : row))} /></label>
              <button className="ghost" type="button" disabled={items.length === 1} onClick={() => setItems(rows => rows.filter((_, i) => i !== index))} aria-label={t(`Retirer la ligne ${index + 1}`, `Remove line ${index + 1}`)}>×</button>
            </div>)}
          </div>
          <div className="row wrap top-gap-sm"><button className="ghost" type="button" disabled={items.length >= 50} onClick={() => setItems(rows => [...rows, { product_id: "", product_title: "", quantity: 1 }])}>{t("Ajouter un produit", "Add product")}</button><strong>{total} {t("exemplaires commandés", "units ordered")}</strong></div>
          <label className="top-gap-sm">{t("Note (optionnel)", "Note (optional)")}<textarea name="note" maxLength={2000} rows={2} /></label>
          <p className="muted">{t("Cette saisie n’envoie aucune commande au fournisseur et ne crée ni facture ni paiement.", "This records the order only: no supplier message, invoice or payment is created.")}</p>
          <button type="submit">{t("Enregistrer en attente de réception", "Save as awaiting delivery")}</button>
        </PendingFields>
      </form>
    </details>
    <p className="muted top-gap-sm">{t("100 dernières commandes au maximum, commandes en attente affichées en premier.", "Up to 100 recent orders, awaiting deliveries shown first.")}</p>
    {orders.length === 0 ? <p>{t("Aucune commande enregistrée.", "No orders recorded.")}</p> : null}
    <div className="supply-order-list">
      {orders.map(order => {
        const quantity = order.items.reduce((sum, item) => sum + item.quantity, 0);
        return <article className="supply-order-card" key={order.id}>
          <div className="row spread wrap"><h4>{order.reference || `${t("Commande", "Order")} ${order.id.slice(0, 8)}`}</h4><span className={`badge ${order.status === "RECEIVED" ? "success" : ""}`}>
            {order.status === "ORDERED" ? t("En attente de réception", "Awaiting delivery") : order.status === "RECEIVED" ? t("Réceptionnée", "Received") : t("Annulée", "Cancelled")}
          </span></div>
          <p><strong>{order.location_name}</strong> · {t("Livraison prévue", "Expected delivery")} : <strong>{dateLabel(order.expected_delivery_date)}</strong></p>
          <p className="muted">{t("Commandée le", "Ordered on")} {dateLabel(order.ordered_date)}{order.supplier ? ` · ${order.supplier}` : ""}</p>
          <ul>{order.items.map(item => <li key={item.id}><strong>{item.quantity}</strong> × {item.product_title}{!item.product_id ? <span className="badge">{t("À référencer avant réception", "Link to catalog before receipt")}</span> : null}</li>)}</ul>
          <p><strong>{t("Total", "Total")} : {quantity}</strong> {t("exemplaires", "units")}</p>
          {order.note ? <p>{order.note}</p> : null}
          {order.received_date ? <p>{t("Entrée en stock effectuée le", "Added to stock on")} {dateLabel(order.received_date)} · <a href="/admin/products?view=entries">{t("Voir les mouvements de stock", "View stock movements")}</a></p> : null}
          {order.status === "ORDERED" ? <div className="top-gap-sm">
            <details><summary className="mode-link">{t("Réceptionner cette commande", "Receive this order")}</summary>
              <form action={completeAdminSupplyOrderAction} className="top-gap-sm"><PendingFields language={language}>
                <input type="hidden" name="order_id" value={order.id} /><input type="hidden" name="operation" value="receive" />
                {order.items.filter(item => !item.product_id).map(item => <label className="top-gap-sm" key={item.id}>
                  {t("Fiche produit pour", "Catalog product for")} {item.product_title}
                  <select name={`link_product_${item.id}`} required defaultValue=""><option value="">{t("Choisir la fiche correspondante", "Select matching product")}</option>
                    {products.map(product => <option key={product.id} value={product.id}>{product.title}</option>)}
                  </select>
                  <small>{t("Si elle n’existe pas, créez d’abord la fiche dans Produits, puis revenez réceptionner.", "If missing, create it under Products first, then return to receive this order.")}</small>
                </label>)}
                <label>{t("Date de réception effective", "Actual receipt date")}<input type="date" name="received_date" min={order.ordered_date} max={today} defaultValue={today} required /></label>
                <label className="row top-gap-sm"><input type="checkbox" name="confirm_received" value="yes" required />{t(`Je confirme avoir reçu les ${quantity} exemplaires à ${order.location_name}.`, `I confirm receipt of all ${quantity} units at ${order.location_name}.`)}</label>
                <p className="muted">{t("En cas de livraison partielle, ne validez pas la réception intégrale.", "For a partial delivery, do not confirm full receipt.")}</p>
                <button type="submit">{t("Confirmer la réception et ajouter au stock", "Confirm receipt and add to stock")}</button>
              </PendingFields></form>
            </details>
            <form action={completeAdminSupplyOrderAction} className="top-gap-sm" onSubmit={event => { if (!window.confirm(t("Annuler ce suivi dans l’application ? Aucun stock ne sera modifié. Contactez séparément le fournisseur si nécessaire.", "Cancel this tracking record? Stock will not change. Contact the supplier separately if needed."))) event.preventDefault(); }}><PendingFields language={language}>
              <input type="hidden" name="order_id" value={order.id} /><input type="hidden" name="operation" value="cancel" />
              <button type="submit" className="ghost">{t("Annuler le suivi de commande", "Cancel order tracking")}</button>
            </PendingFields></form>
          </div> : null}
        </article>;
      })}
    </div>
  </section>;
}
