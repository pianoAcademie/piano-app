# Future service payments: payment receipt + deferred final invoice

## Goal

For a booking paid before the service is actually delivered:

- payment day: create and email a `payment_receipt`
- service day / service completed: create the real customer invoice

This avoids issuing a service invoice dated months before the prestation is performed.

## Architecture choice

Chosen model:

- `payments` keep storing real cash movements
- `invoices` keep representing real customer invoices only
- new table `payment_receipts` stores payment acknowledgements for future services

This keeps the semantic split explicit and avoids polluting the invoice numbering sequence.

## Main rules

- if `service_date > today` and the session is not completed, checkout creates or reuses a `payment_receipt`
- if the service is already completed, the normal final-invoice logic is allowed
- a `payment_receipt` uses its own numbering sequence (`PAY-%YYYY%-%NNNN%`)
- the final invoice keeps the usual invoice sequence
- the final invoice is generated automatically when the session status becomes `COMPLETED`
- admins also have a manual fallback action from the booking row
- no double billing: a second generation request returns the existing final invoice
- cancelled bookings never generate a final invoice

## Email and PDF outputs

New templates:

- `PAYMENT_RECEIPT`
- `PAYMENT_RECEIPT_ADMIN`

PDFs:

- payment receipt PDF: title `JUSTIFICATIF DE PAIEMENT`
- final invoice PDF: existing invoice renderer, now able to show already received payments and a zero remaining balance

## Back-office behavior

On the client `Reservations` tab, each booking now exposes:

- payment received: yes / no
- receipt sent: yes / no
- final invoice generated: yes / no
- scheduled service date
- completion date when available

Admin actions:

- resend payment receipt
- download payment receipt PDF
- generate final invoice
- download final invoice PDF

## Limits / follow-up

- automatic final invoice generation currently hooks on session status `COMPLETED`; if a session is completed outside the usual admin flow, the same rule must still be triggered from that path
- cancellation / refund / credit-note policies are intentionally not redefined here; the new model only preserves payment history cleanly so that later refund or avoir logic can plug in without ambiguity
- payment-provider end-to-end validation still needs manual QA against the live return/webhook flow

## Manual test plan

1. Book and pay a future external session.
2. Verify that:
   - a `PAY-...` receipt is created
   - no final invoice exists yet
   - client and admin receipt emails are sent
3. Mark the session `COMPLETED`.
4. Verify that:
   - the final invoice is created only once
   - invoice date equals the real emission date
   - service date equals the real prestation date
   - previously received payments appear on the invoice
   - remaining balance is `0` when fully paid
5. Cancel a future booking before completion and verify that no final invoice is generated.
