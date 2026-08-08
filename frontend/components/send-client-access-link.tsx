"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { normalizeUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";

type DialogMode = "confirm" | "success" | "error" | null;

type SendClientAccessLinkProps = {
  clientId: string;
  email: string;
  language?: UiLanguage | string;
};

type AccessLinkResponse = {
  message_id: string;
  email: string;
  sent_at: string;
};

export default function SendClientAccessLink({ clientId, email, language: languageProp = "fr" }: SendClientAccessLinkProps): JSX.Element {
  const language = normalizeUiLanguage(languageProp);
  const router = useRouter();
  const [mode, setMode] = useState<DialogMode>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<AccessLinkResponse | null>(null);

  const close = (): void => {
    if (pending) return;
    setMode(null);
    setError("");
  };

  const send = async (): Promise<void> => {
    setPending(true);
    setError("");
    try {
      const response = await fetch(`/api/admin/clients/${clientId}/send-access-link`, {
        method: "POST",
        cache: "no-store",
      });
      const payload = (await response.json().catch(() => ({}))) as Partial<AccessLinkResponse> & { detail?: string };
      if (!response.ok || !payload.message_id) {
        throw new Error(payload.detail || uiText(language, "admin.client_detail.password_send_error"));
      }
      setResult({
        message_id: payload.message_id,
        email: payload.email || email,
        sent_at: payload.sent_at || new Date().toISOString(),
      });
      setMode("success");
      router.refresh();
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : uiText(language, "admin.client_detail.password_send_error"));
      setMode("error");
    } finally {
      setPending(false);
    }
  };

  const openMessages = (): void => {
    router.push(`/admin/clients/${clientId}?tab=messages`);
    setMode(null);
  };

  return (
    <>
      <button type="button" disabled={pending} onClick={() => setMode("confirm")}>
        {pending
          ? uiText(language, "admin.client_detail.password_sending")
          : uiText(language, "admin.client_detail.generate_send_password")}
      </button>

      {mode ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact" role="dialog" aria-modal="true">
            <button className="modal-close-x" type="button" onClick={close} disabled={pending} aria-label={uiText(language, "common.close")}>
              ×
            </button>

            {mode === "confirm" ? (
              <>
                <h3 className="modal-title">{uiText(language, "admin.client_detail.password_confirm_title")}</h3>
                <p className="muted">
                  {uiText(language, "admin.client_detail.password_confirm_description", { email })}
                </p>
                <div className="row modal-actions-end">
                  <button type="button" className="ghost" onClick={close} disabled={pending}>
                    {uiText(language, "common.cancel")}
                  </button>
                  <button type="button" onClick={() => void send()} disabled={pending}>
                    {pending
                      ? uiText(language, "admin.client_detail.password_sending")
                      : uiText(language, "admin.client_detail.password_confirm_send")}
                  </button>
                </div>
              </>
            ) : null}

            {mode === "success" && result ? (
              <>
                <div className="success-dialog-icon" aria-hidden="true">✓</div>
                <h3 className="modal-title">{uiText(language, "admin.client_detail.password_success_title")}</h3>
                <p>{uiText(language, "admin.client_detail.password_success_description", { email: result.email })}</p>
                <p className="muted">{uiText(language, "admin.client_detail.password_success_history")}</p>
                <small className="muted">{uiText(language, "admin.client_detail.password_message_reference", { message_id: result.message_id })}</small>
                <div className="row modal-actions-end top-gap-sm">
                  <button type="button" className="ghost" onClick={close}>
                    {uiText(language, "common.close")}
                  </button>
                  <button type="button" onClick={openMessages}>
                    {uiText(language, "admin.client_detail.password_view_messages")}
                  </button>
                </div>
              </>
            ) : null}

            {mode === "error" ? (
              <>
                <h3 className="modal-title">{uiText(language, "admin.client_detail.password_error_title")}</h3>
                <section className="flash-err">{error}</section>
                <div className="row modal-actions-end top-gap-sm">
                  <button type="button" className="ghost" onClick={close}>
                    {uiText(language, "common.close")}
                  </button>
                  <button type="button" onClick={() => setMode("confirm")}>
                    {uiText(language, "admin.client_detail.password_retry")}
                  </button>
                </div>
              </>
            ) : null}
          </article>
        </section>
      ) : null}
    </>
  );
}
