export type PartialPaymentContext = {
  invoice_number: string;
  invoice_status: string;
  invoice_total: string;
  balance: string;
  currency: string;
  recipients: string[];
  requests: {
    id: string; amount: string; status: string; active: boolean;
    created_at: string; expires_at: string; sent_at: string | null;
    paid_at: string | null; email_error: string | null; recipients: string[];
  }[];
};

export type PartialPaymentActionState = { ok?: boolean; message?: string; error?: string };

/** Parse money without silently accepting extra precision, signs or exponent notation. */
export function partialPaymentCents(raw: string): number | null {
  const clean = raw.trim().replace(/\s/g, "");
  if (!/^\d+(?:[.,]\d{1,2})?$/.test(clean)) return null;
  const [whole, fraction = ""] = clean.replace(",", ".").split(".");
  const value = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  return Number.isSafeInteger(value) ? value : null;
}
