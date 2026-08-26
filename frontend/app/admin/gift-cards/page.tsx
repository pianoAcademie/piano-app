import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { importAdminGiftCardAction, updateAdminGiftCardStatusAction } from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import { normalizeUiLanguage } from "../../../lib/ui-i18n";
import type { AdminFormulaOut, AdminGiftCardOut, UserOut } from "../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function money(value: string, currency: string, language: string): string {
  return new Intl.NumberFormat(language === "en" ? "en-GB" : "fr-FR", {
    style: "currency",
    currency,
  }).format(Number(value));
}

function dateTime(value: string | null, language: string): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat(language === "en" ? "en-GB" : "fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default async function AdminGiftCardsPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) redirect("/login?error_code=session_expired");

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") redirect("/login?error_code=admin_access_required");
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const fr = language !== "en";
  const params = searchParams ?? {};
  const okMessage = readParam(params, "ok");
  const errorMessage = readParam(params, "error");
  const search = readParam(params, "q").trim();
  const statusFilter = readParam(params, "status").trim().toUpperCase();
  const query = new URLSearchParams();
  if (search) query.set("search", search);
  if (statusFilter) query.set("status", statusFilter);

  const [cardsResult, formulasResult] = await Promise.all([
    backendRequest<AdminGiftCardOut[]>(`/api/v1/admin/gift-cards${query.size ? `?${query.toString()}` : ""}`, {}, token),
    backendRequest<AdminFormulaOut[]>("/api/v1/admin/formulas?include_inactive=true", {}, token),
  ]);
  const cards = cardsResult.ok ? cardsResult.data : [];
  const plans = formulasResult.ok ? formulasResult.data.filter((formula) => formula.kind === "PACK" && formula.active) : [];
  const loadError = !cardsResult.ok ? cardsResult.message : !formulasResult.ok ? formulasResult.message : "";

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h1>{fr ? "Cartes cadeaux" : "Gift cards"}</h1>
        <p className="muted">
          {fr
            ? "Importez les cartes vendues sur WordPress, contrôlez leur statut et laissez le bénéficiaire activer lui-même l'offre reçue."
            : "Import cards sold through WordPress, review their status, and let recipients activate the gifted offer."}
        </p>
      </section>
      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage || loadError ? <section className="flash-err">{errorMessage || loadError}</section> : null}

      <section className="card">
        <h2>{fr ? "Importer une carte existante" : "Import an existing card"}</h2>
        <p className="muted">
          {fr
            ? "Une même commande WordPress peut être rejouée sans créer de doublon. Le code complet n'est jamais conservé après l'import."
            : "A WordPress order can be replayed safely without creating a duplicate. The full code is never retained after import."}
        </p>
        <form action={importAdminGiftCardAction} className="grid cols-3 config-form-grid">
          <label>
            {fr ? "Code unique" : "Unique code"}
            <input name="code" required minLength={6} maxLength={80} autoComplete="off" placeholder="268E-B072-8557-F80C" />
          </label>
          <label>
            {fr ? "Offre remise au bénéficiaire" : "Gifted offer"}
            <select name="plan_id" required defaultValue="">
              <option value="" disabled>{fr ? "Sélectionner une offre" : "Select an offer"}</option>
              {plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name}</option>)}
            </select>
          </label>
          <label>
            {fr ? "Source" : "Source"}
            <select name="source" defaultValue="WORDPRESS">
              <option value="WORDPRESS">WordPress</option>
              <option value="PHYSICAL">{fr ? "Carte physique" : "Physical card"}</option>
              <option value="ADMIN">Admin</option>
              <option value="MIGRATION">Migration</option>
            </select>
          </label>

          <label>{fr ? "Commande WordPress" : "WordPress order"}<input name="external_order_ref" maxLength={120} /></label>
          <label>{fr ? "Ligne de commande" : "Order line"}<input name="external_line_ref" maxLength={120} defaultValue="1" /></label>
          <label>{fr ? "Date du paiement" : "Payment date"}<input type="datetime-local" name="paid_at" /></label>
          <label>{fr ? "Nom de l'acheteur" : "Purchaser name"}<input name="purchaser_name" maxLength={255} /></label>
          <label>{fr ? "Email de l'acheteur" : "Purchaser email"}<input type="email" name="purchaser_email" maxLength={255} /></label>
          <label>{fr ? "Nom du bénéficiaire" : "Recipient name"}<input name="recipient_name" maxLength={255} /></label>
          <label>{fr ? "Email du bénéficiaire" : "Recipient email"}<input type="email" name="recipient_email" maxLength={255} /></label>
          <label>{fr ? "Valeur de l'offre TTC" : "Gifted value incl. tax"}<input type="number" name="face_value_ttc" min="0" step="0.01" defaultValue="0" /></label>
          <label>{fr ? "Prix payé TTC" : "Price paid incl. tax"}<input type="number" name="purchase_price_ttc" min="0" step="0.01" defaultValue="0" /></label>
          <label>{fr ? "Remise TTC" : "Discount incl. tax"}<input type="number" name="discount_ttc" min="0" step="0.01" defaultValue="0" /></label>
          <label>{fr ? "TVA (%)" : "VAT (%)"}<input type="number" name="vat_rate" min="0" step="0.001" defaultValue="20" /></label>
          <label>{fr ? "Valable à partir du" : "Valid from"}<input type="datetime-local" name="valid_from" /></label>
          <label>{fr ? "Expiration" : "Expiry"}<input type="datetime-local" name="expires_at" /></label>
          <label className="span-2">{fr ? "Message personnel" : "Personal message"}<textarea name="personal_message" rows={2} maxLength={1000} /></label>
          <div className="row span-3"><button type="submit">{fr ? "Importer la carte" : "Import card"}</button></div>
        </form>
      </section>

      <section className="card">
        <div className="row space-between">
          <h2>{fr ? "Registre" : "Register"}</h2>
          <form method="get" className="row">
            <input name="q" defaultValue={search} placeholder={fr ? "Code, commande ou email" : "Code, order or email"} />
            <select name="status" defaultValue={statusFilter}>
              <option value="">{fr ? "Tous les statuts" : "All statuses"}</option>
              <option value="ACTIVE">{fr ? "Active" : "Active"}</option>
              <option value="REDEEMED">{fr ? "Utilisée" : "Redeemed"}</option>
              <option value="BLOCKED">{fr ? "Bloquée" : "Blocked"}</option>
              <option value="EXPIRED">{fr ? "Expirée" : "Expired"}</option>
            </select>
            <button className="ghost" type="submit">{fr ? "Filtrer" : "Filter"}</button>
          </form>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr>
              <th>{fr ? "Code" : "Code"}</th><th>{fr ? "Offre" : "Offer"}</th><th>{fr ? "Origine" : "Origin"}</th>
              <th>{fr ? "Bénéficiaire" : "Recipient"}</th><th>{fr ? "Montants" : "Amounts"}</th><th>{fr ? "Statut" : "Status"}</th><th>{fr ? "Activation" : "Activation"}</th><th>{fr ? "Actions" : "Actions"}</th>
            </tr></thead>
            <tbody>
              {cards.length === 0 ? <tr><td colSpan={8} className="muted">{fr ? "Aucune carte." : "No gift cards."}</td></tr> : null}
              {cards.map((card) => (
                <tr key={card.id}>
                  <td><strong>•••• {card.code_suffix}</strong><br /><small>{card.external_order_ref ? `#${card.external_order_ref}` : "—"}</small></td>
                  <td>{card.plan_name}</td>
                  <td>{card.source}<br /><small>{dateTime(card.paid_at, language)}</small></td>
                  <td>{card.recipient_name || card.recipient_email || "—"}</td>
                  <td>{money(card.face_value_ttc, card.currency, language)}<br /><small>{fr ? "Payé" : "Paid"}: {money(card.purchase_price_ttc, card.currency, language)}</small></td>
                  <td><span className={`status-pill ${card.status === "ACTIVE" ? "status-ok" : card.status === "REDEEMED" ? "status-info" : "status-warn"}`}>{card.status}</span></td>
                  <td>{dateTime(card.redeemed_at, language)}</td>
                  <td>
                    {card.status === "ACTIVE" ? (
                      <form action={updateAdminGiftCardStatusAction}>
                        <input type="hidden" name="gift_card_id" value={card.id} />
                        <input type="hidden" name="status" value="BLOCKED" />
                        <button className="ghost small-btn" type="submit">{fr ? "Bloquer" : "Block"}</button>
                      </form>
                    ) : card.status === "BLOCKED" ? (
                      <form action={updateAdminGiftCardStatusAction}>
                        <input type="hidden" name="gift_card_id" value={card.id} />
                        <input type="hidden" name="status" value="ACTIVE" />
                        <button className="ghost small-btn" type="submit">{fr ? "Réactiver" : "Reactivate"}</button>
                      </form>
                    ) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
