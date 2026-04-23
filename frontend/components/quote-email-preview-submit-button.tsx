"use client";

import { useState } from "react";

import { normalizeUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";

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
  language?: UiLanguage | string;
};

export default function QuoteEmailPreviewSubmitButton({
  formId,
  previewUrl,
  label,
  title,
  description,
  confirmLabel,
  cancelLabel,
  className,
  disabled = false,
  language: languageProp = "fr",
}: QuoteEmailPreviewSubmitButtonProps): JSX.Element {
  const language = normalizeUiLanguage(languageProp);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const resolvedTitle = title ?? t("admin.quote_email_preview.default_title");
  const resolvedDescription = description ?? t("admin.quote_email_preview.default_description");
  const resolvedConfirmLabel = confirmLabel ?? t("admin.quote_email_preview.default_confirm");
  const resolvedCancelLabel = cancelLabel ?? t("common.cancel");
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
      setErrorMessage(t("common.form_not_found"));
      return;
    }

    const formData = new FormData(form);
    const recipientEmail = String(formData.get("recipient_email") ?? "").trim();
    const templateRefRaw = String(formData.get("template_ref") ?? "").trim();
    if (!recipientEmail) {
      setErrorMessage(t("admin.quote_email_preview.recipient_required"));
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
        setErrorMessage(extractErrorMessage(parsed, t("admin.quote_email_preview.preview_unavailable", { status: response.status })));
        return;
      }
      if (!isQuoteEmailPreviewPayload(parsed)) {
        setErrorMessage(t("admin.quote_email_preview.invalid_preview"));
        return;
      }
      setPreview(parsed);
      setOpen(true);
    } catch {
      setErrorMessage(t("admin.quote_email_preview.load_failed"));
    } finally {
      setLoading(false);
    }
  };

  const confirm = (): void => {
    const form = document.getElementById(formId);
    if (!(form instanceof HTMLFormElement)) {
      setErrorMessage(t("common.form_not_found"));
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
        {loading ? t("admin.quote_email_preview.loading") : label}
      </button>

      {errorMessage ? <section className="flash-err top-gap-sm">{errorMessage}</section> : null}

      {open && preview ? (
        <section className="modal-overlay">
          <article className="modal-panel quote-email-preview-modal">
            <button className="modal-close-x" type="button" onClick={close} aria-label={t("common.close")}>
              ×
            </button>
            <h3 className="modal-title">{resolvedTitle}</h3>
            {resolvedDescription ? (
              <p className="muted" style={{ whiteSpace: "pre-line" }}>
                {resolvedDescription}
              </p>
            ) : null}
            <div className="quote-email-preview-grid">
              <div className="quote-email-preview-field">
                <strong>{t("admin.quote_email_preview.recipient")}</strong>
                <div className="quote-email-preview-value">{preview.recipient_email}</div>
              </div>
              <div className="quote-email-preview-field">
                <strong>{t("admin.quote_email_preview.subject")}</strong>
                <div className="quote-email-preview-value">{preview.subject || "-"}</div>
              </div>
              <div className="quote-email-preview-field">
                <strong>{t("common.message")}</strong>
                {preview.body_format.trim().toUpperCase() === "HTML" ? (
                  <div className="quote-email-preview-body" dangerouslySetInnerHTML={{ __html: preview.body || "<p>-</p>" }} />
                ) : (
                  <pre className="quote-email-preview-body quote-email-preview-text">{preview.body || "-"}</pre>
                )}
              </div>
            </div>
            <div className="row modal-actions-end">
              <button type="button" className="ghost" onClick={close}>
                {resolvedCancelLabel}
              </button>
              <button type="button" onClick={confirm}>
                {resolvedConfirmLabel}
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
