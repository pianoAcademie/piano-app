"use client";

import { Capacitor } from "@capacitor/core";
import type { ActionPerformed, PushNotificationSchema, Token } from "@capacitor/push-notifications";
import { useCallback, useEffect, useRef, useState } from "react";


type Props = {
  language: "fr" | "en";
};

type PushState = "checking" | "available" | "registering" | "enabled" | "denied" | "error" | "unsupported";

const INSTALLATION_ID_KEY = "pa_client_push_installation_id";


function installationId(): string {
  const existing = window.localStorage.getItem(INSTALLATION_ID_KEY);
  if (existing) return existing;
  const created = window.crypto.randomUUID();
  window.localStorage.setItem(INSTALLATION_ID_KEY, created);
  return created;
}


async function sendEvent(notificationId: string, event: "RECEIVED" | "OPENED"): Promise<void> {
  await fetch(`/api/mobile/push/notifications/${encodeURIComponent(notificationId)}/events`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event }),
  }).catch(() => undefined);
}


export default function MobilePushRegistration({ language }: Props): JSX.Element | null {
  const [state, setState] = useState<PushState>("checking");
  const [errorMessage, setErrorMessage] = useState("");
  const listenersReady = useRef(false);
  const isEnglish = language === "en";

  const saveToken = useCallback(async (token: Token): Promise<void> => {
    const platform = Capacitor.getPlatform();
    const response = await fetch("/api/mobile/push/devices", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        installation_id: installationId(),
        push_token: token.value,
        platform: platform === "ios" ? "IOS" : "ANDROID",
        app_target: "CLIENT",
        permission_status: "GRANTED",
        locale: language,
        device_label: platform === "ios" ? "iPhone / iPad" : "Android",
      }),
    });
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
      throw new Error(payload?.detail || `HTTP ${response.status}`);
    }
    setState("enabled");
    setErrorMessage("");
  }, [language]);

  const enable = useCallback(async (): Promise<void> => {
    if (!Capacitor.isNativePlatform()) {
      setState("unsupported");
      return;
    }
    setState("registering");
    setErrorMessage("");
    try {
      const { PushNotifications } = await import("@capacitor/push-notifications");
      const permission = await PushNotifications.requestPermissions();
      if (permission.receive !== "granted") {
        setState("denied");
        return;
      }
      await PushNotifications.register();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
      setState("error");
    }
  }, []);

  useEffect(() => {
    if (!Capacitor.isNativePlatform()) {
      setState("unsupported");
      return;
    }
    let active = true;
    const handles: Array<{ remove: () => Promise<void> }> = [];

    void (async () => {
      try {
        const { PushNotifications } = await import("@capacitor/push-notifications");
        if (Capacitor.getPlatform() === "android") {
          await PushNotifications.createChannel({
            id: "piano_academie_general",
            name: isEnglish ? "Piano Académie notifications" : "Notifications Piano Académie",
            description: isEnglish ? "Important school and lesson information" : "Informations importantes de l’école et des cours",
            importance: 4,
            visibility: 1,
            sound: "default",
            vibration: true,
          });
        }
        if (!listenersReady.current) {
          handles.push(await PushNotifications.addListener("registration", (token) => {
            if (!active) return;
            void saveToken(token).catch((error) => {
              setErrorMessage(error instanceof Error ? error.message : String(error));
              setState("error");
            });
          }));
          handles.push(await PushNotifications.addListener("registrationError", (error) => {
            if (!active) return;
            setErrorMessage(String(error.error || "Registration failed"));
            setState("error");
          }));
          handles.push(await PushNotifications.addListener("pushNotificationReceived", (notification: PushNotificationSchema) => {
            const notificationId = String(notification.data?.notification_id || "");
            if (notificationId) void sendEvent(notificationId, "RECEIVED");
          }));
          handles.push(await PushNotifications.addListener("pushNotificationActionPerformed", (action: ActionPerformed) => {
            const notificationId = String(action.notification.data?.notification_id || "");
            if (notificationId) void sendEvent(notificationId, "OPENED");
            const deepLink = String(action.notification.data?.deep_link || "");
            if (deepLink.startsWith("/client")) window.location.assign(deepLink);
          }));
          listenersReady.current = true;
        }

        const permission = await PushNotifications.checkPermissions();
        if (!active) return;
        if (permission.receive === "granted") {
          setState("registering");
          await PushNotifications.register();
        } else if (permission.receive === "denied") {
          setState("denied");
        } else {
          setState("available");
        }
      } catch (error) {
        if (!active) return;
        setErrorMessage(error instanceof Error ? error.message : String(error));
        setState("error");
      }
    })();

    return () => {
      active = false;
      listenersReady.current = false;
      for (const handle of handles) void handle.remove();
    };
  }, [isEnglish, saveToken]);

  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;
    const forms = Array.from(document.querySelectorAll<HTMLFormElement>("form[data-mobile-push-logout='true']"));
    const handleLogout = (event: SubmitEvent): void => {
      const form = event.currentTarget as HTMLFormElement;
      if (form.dataset.mobilePushDisabled === "true") return;
      event.preventDefault();
      const submitter = event.submitter instanceof HTMLElement ? event.submitter : undefined;
      const controller = new AbortController();
      const timeoutId = window.setTimeout(() => controller.abort(), 1500);
      void fetch("/api/mobile/push/devices", {
        method: "DELETE",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ installation_id: installationId(), app_target: "CLIENT" }),
        signal: controller.signal,
      }).finally(() => {
        window.clearTimeout(timeoutId);
        form.dataset.mobilePushDisabled = "true";
        form.requestSubmit(submitter instanceof HTMLButtonElement ? submitter : undefined);
      });
    };
    for (const form of forms) form.addEventListener("submit", handleLogout);
    return () => {
      for (const form of forms) form.removeEventListener("submit", handleLogout);
    };
  }, []);

  if (state === "checking" || state === "unsupported" || state === "enabled") return null;

  return (
    <section className={`client-push-optin ${state === "error" || state === "denied" ? "warning" : ""}`}>
      <div>
        <strong>{isEnglish ? "Stay informed" : "Restez informé"}</strong>
        <p>
          {state === "denied"
            ? isEnglish
              ? "Notifications are disabled. You can enable them in your phone settings."
              : "Les notifications sont désactivées. Vous pouvez les autoriser dans les réglages du téléphone."
            : isEnglish
              ? "Enable notifications to receive important school and lesson information."
              : "Activez les notifications pour recevoir les informations importantes de l’école et de vos cours."}
        </p>
        {errorMessage ? <small>{errorMessage}</small> : null}
      </div>
      {state === "available" || state === "error" ? (
        <button type="button" onClick={() => void enable()}>
          {isEnglish ? "Enable" : "Activer"}
        </button>
      ) : null}
    </section>
  );
}
