"use client";

import { useState } from "react";

type QuoteEmailPreviewPayload = {
  recipient_email: string;
  template_ref: string;
  subject: string;
  body: string;
  body_format: string;
};

type QuoteEmailPreviewSubmitButtonProps = {
  formId: string;
  previewUrl: string;
  label: string;
  title?: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  className?: string;
  disabled?: boolean;
};

export default function QuoteEmailPreviewSubmitButton({
  formId,
  previewUrl,
  label,
  title = "Verifier l'email avant envoi",
  description = "Controlez le destinataire, le sujet et le message avant de confirmer l'envoi.",
  confirmLabel = "Confirmer l'envoi",
  cancelLabel = "Annuler",
  className,
  disabled = false,
}: QuoteEmailPreviewSubmitButtonProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [preview, setPreview] = useState<QuoteEmailPreviewPayload | null>(null);

  const close = (): void => {
    setOpen(false);
    setPreview(null);
    setErrorMessage("");
  };

  const loadPreview = async (): Promise<void> => {
    if (disabled || loading) {
      return;
    }
    const form = document.getElementById(formId);
    if (!(form instanceof HTMLFormElement)) {
      setErrorMessage("Formulaire introuvable.");
      return;
    }

    const formData = new FormData(form);
    const recipientEmail = String(formData.get("recipient_email") ?? "").trim();
    const templateRefRaw = String(formData.get("template_ref") ?? "").trim();
    if (!recipientEmail) {
      setErrorMessage("Adresse email destinataire requise.");
      return;
    }

    setLoading(true);
    setErrorMessage("");
    setPreview(null);

    try {
      const response = await fetch(previewUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          recipient_email: recipientEmail,
          template_ref: templateRefRaw || null,
        }),
      });

      const text = await response.text();
      const parsed = text ? safeJsonParse(text) : null;
      if (!response.ok) {
        setErrorMessage(extractErrorMessage(parsed, `Previsualisation indisponible (${response.status})`));
        return;
      }
      if (!isQuoteEmailPreviewPayload(parsed)) {
        setErrorMessage("Previsualisation email invalide.");
        return;
      }
      setPreview(parsed);
      setOpen(true);
    } catch {
      setErrorMessage("Impossible de charger la previsualisation de l'email.");
    } finally {
      setLoading(false);
    }
  };

  const confirm = (): void => {
    const form = document.getElementById(formId);
    if (!(form instanceof HTMLFormElement)) {
      setErrorMessage("Formulaire introuvable.");
      return;
    }
    close();
    form.requestSubmit();
  };

  return (
    <>
      <button
        type="button"
        className={className}
        disabled={disabled || loading}
        onClick={() => {
          void loadPreview();
        }}
      >
        {loading ? "Chargement..." : label}
      </button>

      {errorMessage ? <section className="flash-err top-gap-sm">{errorMessage}</section> : null}

      {open && preview ? (
        <section className="modal-overlay">
          <article className="modal-panel quote-email-preview-modal">
            <button className="modal-close-x" type="button" onClick={close} aria-label="Fermer">
              ×
            </button>
            <h3 className="modal-title">{title}</h3>
            {description ? (
              <p className="muted" style={{ whiteSpace: "pre-line" }}>
                {description}
              </p>
            ) : null}
            <div className="quote-email-preview-grid">
              <div className="quote-email-preview-field">
                <strong>Destinataire</strong>
                <div className="quote-email-preview-value">{preview.recipient_email}</div>
              </div>
              <div className="quote-email-preview-field">
                <strong>Sujet</strong>
                <div className="quote-email-preview-value">{preview.subject || "-"}</div>
              </div>
              <div className="quote-email-preview-field">
                <strong>Message</strong>
                {preview.body_format.trim().toUpperCase() === "HTML" ? (
                  <div className="quote-email-preview-body" dangerouslySetInnerHTML={{ __html: preview.body || "<p>-</p>" }} />
                ) : (
                  <pre className="quote-email-preview-body quote-email-preview-text">{preview.body || "-"}</pre>
                )}
              </div>
            </div>
            <div className="row modal-actions-end">
              <button type="button" className="ghost" onClick={close}>
                {cancelLabel}
              </button>
              <button type="button" onClick={confirm}>
                {confirmLabel}
              </button>
            </div>
          </article>
        </section>
      ) : null}
    </>
  );
}

function safeJsonParse(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function extractErrorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object") {
    const detail = (payload as Record<string, unknown>).detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
  }
  return fallback;
}

function isQuoteEmailPreviewPayload(value: unknown): value is QuoteEmailPreviewPayload {
  if (!value || typeof value !== "object") {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.recipient_email === "string"
    && typeof candidate.template_ref === "string"
    && typeof candidate.subject === "string"
    && typeof candidate.body === "string"
    && typeof candidate.body_format === "string"
  );
}
