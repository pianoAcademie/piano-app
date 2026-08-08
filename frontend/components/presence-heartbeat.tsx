"use client";

import { Capacitor } from "@capacitor/core";
import { useEffect } from "react";

type PresenceChannel = "WEB" | "MOBILE_APP";

function presenceChannel(): PresenceChannel {
  if (Capacitor.isNativePlatform()) {
    return "MOBILE_APP";
  }
  const standalone = window.matchMedia?.("(display-mode: standalone)").matches === true;
  const iosStandalone = (window.navigator as Navigator & { standalone?: boolean }).standalone === true;
  const source = new URLSearchParams(window.location.search).get("source")?.trim().toLowerCase();
  return standalone || iosStandalone || source === "mobile_app" ? "MOBILE_APP" : "WEB";
}

export default function PresenceHeartbeat(): null {
  useEffect(() => {
    let stopped = false;
    const channel = presenceChannel();

    const sendHeartbeat = async (): Promise<void> => {
      if (stopped || document.visibilityState !== "visible" || !navigator.onLine) {
        return;
      }
      try {
        await fetch("/api/presence", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ channel }),
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

    void sendHeartbeat();
    const interval = window.setInterval(() => void sendHeartbeat(), 30_000);
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("online", onVisibilityChange);

    return () => {
      stopped = true;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("online", onVisibilityChange);
    };
  }, []);

  return null;
}
