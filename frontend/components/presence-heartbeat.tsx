"use client";

import { Capacitor } from "@capacitor/core";
import { useEffect, useRef } from "react";

type PresenceChannel = "WEB_DESKTOP" | "WEB_MOBILE" | "INSTALLED_WEB" | "NATIVE_APP";
type DeviceType = "DESKTOP" | "MOBILE" | "TABLET" | "APP";

const VISIBLE_QUERY_PARAMETERS = ["tab", "view", "section"] as const;

function currentPage(): string {
  const params = new URLSearchParams();
  for (const key of VISIBLE_QUERY_PARAMETERS) {
    const value = new URLSearchParams(window.location.search).get(key);
    if (value) params.set(key, value.slice(0, 80));
  }
  const query = params.toString();
  return `${window.location.pathname}${query ? `?${query}` : ""}`.slice(0, 300);
}

function presenceChannel(): PresenceChannel {
  if (Capacitor.isNativePlatform()) {
    return "NATIVE_APP";
  }
  const standalone = window.matchMedia?.("(display-mode: standalone)").matches === true;
  const iosStandalone = (window.navigator as Navigator & { standalone?: boolean }).standalone === true;
  const source = new URLSearchParams(window.location.search).get("source")?.trim().toLowerCase();
  if (standalone || iosStandalone || source === "installed_web" || source === "mobile_app") {
    return "INSTALLED_WEB";
  }
  return /ipad|tablet|iphone|android|mobile/i.test(window.navigator.userAgent)
    ? "WEB_MOBILE"
    : "WEB_DESKTOP";
}

function deviceType(channel: PresenceChannel): DeviceType {
  if (channel === "NATIVE_APP") return "APP";
  const userAgent = navigator.userAgent.toLowerCase();
  if (/ipad|tablet/.test(userAgent)) return "TABLET";
  if (/iphone|android|mobile/.test(userAgent)) return "MOBILE";
  return "DESKTOP";
}

function presenceOrigin(channel: PresenceChannel): string {
  const storageKey = "piano_presence_origin_v2";
  try {
    const stored = window.sessionStorage.getItem(storageKey);
    if (stored) return stored;
  } catch {
    // Continue without session storage.
  }

  let origin = channel === "NATIVE_APP" ? "NATIVE_APP" : channel === "INSTALLED_WEB" ? "INSTALLED_WEB" : "DIRECT";
  const currentParameters = new URLSearchParams(window.location.search);
  const campaignSource = currentParameters.get("utm_source")?.trim();
  if (channel !== "NATIVE_APP" && channel !== "INSTALLED_WEB" && campaignSource) {
    const campaignParts = [
      campaignSource,
      currentParameters.get("utm_medium")?.trim(),
      currentParameters.get("utm_campaign")?.trim(),
    ].filter(Boolean);
    origin = `CAMPAIGN:${campaignParts.join(" / ")}`;
  } else if (channel !== "NATIVE_APP" && channel !== "INSTALLED_WEB" && document.referrer) {
    try {
      const referrer = new URL(document.referrer);
      origin = referrer.origin === window.location.origin
        ? `INTERNAL:${referrer.pathname}`
        : `EXTERNAL:${referrer.hostname}`;
    } catch {
      origin = "DIRECT";
    }
  }
  try {
    window.sessionStorage.setItem(storageKey, origin);
  } catch {
    // Origin tracking remains informative only.
  }
  return origin.slice(0, 200);
}

function actionLabel(target: EventTarget | null): string | null {
  if (!(target instanceof Element)) return null;
  const actionable = target.closest("a, button, summary, input[type='submit']");
  if (!(actionable instanceof HTMLElement)) return null;
  const label = (
    actionable.getAttribute("aria-label")
    || actionable.getAttribute("title")
    || (actionable instanceof HTMLInputElement ? actionable.value : actionable.textContent)
    || ""
  ).replace(/\s+/g, " ").trim();
  if (!label) return null;
  const prefix = actionable instanceof HTMLAnchorElement ? "NAVIGATION" : "ACTION";
  return `${prefix}:${label}`.slice(0, 200);
}

export default function PresenceHeartbeat(): null {
  const lastActionRef = useRef("PAGE_VIEW");

  useEffect(() => {
    let stopped = false;
    const channel = presenceChannel();
    const origin = presenceOrigin(channel);
    const device = deviceType(channel);

    const sendHeartbeat = async (): Promise<void> => {
      if (stopped || document.visibilityState !== "visible" || !navigator.onLine) {
        return;
      }
      try {
        await fetch("/api/presence", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            channel,
            current_path: currentPage(),
            origin,
            last_action: lastActionRef.current,
            device_type: device,
          }),
          cache: "no-store",
          keepalive: true,
        });
      } catch {
        // Presence is informative only and must never interrupt portal usage.
      }
    };

    const onVisibilityChange = (): void => {
      if (document.visibilityState === "visible") {
        void sendHeartbeat();
      }
    };

    const onAction = (event: MouseEvent): void => {
      const label = actionLabel(event.target);
      if (!label) return;
      lastActionRef.current = label;
      void sendHeartbeat();
    };

    void sendHeartbeat();
    const interval = window.setInterval(() => void sendHeartbeat(), 15_000);
    document.addEventListener("visibilitychange", onVisibilityChange);
    document.addEventListener("click", onAction, true);
    window.addEventListener("online", onVisibilityChange);

    return () => {
      stopped = true;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      document.removeEventListener("click", onAction, true);
      window.removeEventListener("online", onVisibilityChange);
    };
  }, []);

  return null;
}
