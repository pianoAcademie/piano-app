"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useFormState, useFormStatus } from "react-dom";
import { useRouter } from "next/navigation";
import ModalA11yFrame from "./modal-a11y-frame";
import { partialPaymentCents, type PartialPaymentContext, type PartialPaymentActionState } from "../lib/invoice-partial-payment";

type Props = {
  clientId: string; noteId: string; closeHref: string; requestId: string; context: PartialPaymentContext;
  action: (previous: PartialPaymentActionState, data: FormData) => Promise<PartialPaymentActionState>;
};
const format = (cents: number) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(cents / 100);

function Submit({ disabled, children }: { disabled?: boolean; children: string }): JSX.Element {
  const { pending } = useFormStatus();
  return <button className="primary" type="submit" disabled={pending || disabled} aria-disabled={pending || disabled}>
    {pending ? "Traitement en cours…" : children}
  </button>;
}

export default function InvoicePartialPaymentModal({ clientId, noteId, closeHref, requestId, context, action }: Props): JSX.Element {
  const [state, formAction] = useFormState(action, {});
  const router = useRouter();
  const [amount, setAmount] = useState("");
  const active = context.requests.find((r) => r.active);
  const amountCents = partialPaymentCents(amount);
  const balanceCents = partialPaymentCents(context.balance) ?? 0;
  const valid = amountCents !== null && amountCents >= 100 && amountCents < balanceCents;
  const statusLabels: Record<string, string> = { READY: "Lien prêt", CREATING: "Préparation bancaire en cours", PENDING: "En attente du paiement",
    PAID: "Paiement confirmé", CANCELLED: "Lien annulé", REVIEW: "À vérifier" };
  useEffect(() => { if (state.ok || state.error) router.refresh(); }, [state, router]);
  const ids = <><input type="hidden" name="client_id" value={clientId} /><input type="hidden" name="note_id" value={noteId} /></>;
  return <div className="modal-overlay">
    <ModalA11yFrame className="modal-panel invoice-partial-payment-modal" closeHref={closeHref} label="Envoyer un lien de paiement partiel">
      <Link className="modal-close-x" href={closeHref} aria-label="Fermer">×</Link>
      <h3 className="modal-title">Envoyer un lien de paiement partiel</h3>
      <p>Facture <strong>{context.invoice_number}</strong> · Montant initial : {format(partialPaymentCents(context.invoice_total) ?? 0)}</p>
      <p>Solde restant : <strong>{format(balanceCents)}</strong></p>
      <p className="muted">La facture reste inchangée. Aucun paiement n’est enregistré à l’envoi du lien.</p>
      {state.message ? <p role="status" className="flash-ok">{state.message}</p> : null}
      {state.error ? <p role="alert" className="flash-error">{state.error}</p> : null}
      {active ? <section className="card">
        <h4>Une demande est déjà active : {format(partialPaymentCents(active.amount) ?? 0)}</h4>
        <p>{statusLabels[active.status] ?? active.status} · {active.recipients.join(", ")}</p>
        {active.email_error ? <form action={formAction}>
          {ids}<input type="hidden" name="request_id" value={active.id} /><input type="hidden" name="amount" value={active.amount} />
          <p role="alert">{active.email_error}</p><Submit>Réessayer l’envoi du même lien</Submit>
        </form> : <p>Le lien ne peut être réglé qu’une fois. Pour changer son montant, annulez cette demande puis créez-en une nouvelle.</p>}
        <form action={formAction}>
          {ids}<input type="hidden" name="request_id" value={active.id} /><input type="hidden" name="intent" value="cancel" />
          <Submit>Annuler cette demande</Submit>
        </form>
      </section> : context.invoice_status === "ISSUED" && balanceCents > 100 ? <form action={formAction} className="grid top-gap-sm">
        {ids}<input type="hidden" name="request_id" value={requestId} />
        <label>Montant à demander par carte (€)
          <input name="amount" inputMode="decimal" autoComplete="off" required value={amount} placeholder="Ex. 396,00"
            onChange={(event) => setAmount(event.target.value)} aria-describedby="partial-amount-help" />
        </label>
        <small id="partial-amount-help">Au moins 1 €, strictement inférieur au solde restant. Deux décimales maximum.</small>
        <div className="card" aria-live="polite">
          <h4>Aperçu de la demande</h4>
          <p>Destinataire(s) : <strong>{context.recipients.join(", ")}</strong></p>
          <p>À régler par carte : <strong>{valid ? format(amountCents!) : "—"}</strong></p>
          <p>Solde après paiement confirmé : <strong>{valid ? format(balanceCents - amountCents!) : "—"}</strong></p>
          <p className="muted">Le client recevra un courriel aux couleurs de Piano Académie avec un lien sécurisé valable 30 jours.
            Un règlement en espèces prévu ne doit être enregistré qu’après réception effective.</p>
        </div>
        <div className="row"><Link className="reset-link" href={closeHref}>Fermer</Link><Submit disabled={!valid}>Envoyer le lien de paiement partiel</Submit></div>
      </form> : <p>Cette facture ne permet plus de demander un paiement partiel.</p>}
      {context.requests.length ? <section className="top-gap-sm"><h4>Historique des demandes</h4>
        <ul>{context.requests.map((r) => <li key={r.id}>
          {format(partialPaymentCents(r.amount) ?? 0)} · {r.status === "READY" && !r.active ? "Lien expiré" : statusLabels[r.status] ?? r.status}
          {r.paid_at ? ` · reçu le ${new Date(r.paid_at).toLocaleDateString("fr-FR")}` : ""}
        </li>)}</ul>
      </section> : null}
    </ModalA11yFrame>
  </div>;
}
