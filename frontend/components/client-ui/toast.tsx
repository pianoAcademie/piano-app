"use client";

import { useEffect, useState } from "react";

type ToastProps = {
  message: string;
  tone?: "ok" | "error";
  durationMs?: number;
};

export default function Toast({ message, tone = "ok", durationMs = 2800 }: ToastProps): JSX.Element | null {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const timeout = window.setTimeout(() => setVisible(false), durationMs);
    return () => window.clearTimeout(timeout);
  }, [durationMs]);

  if (!visible || !message) {
    return null;
  }

  return <section className={`client-toast ${tone}`}>{message}</section>;
}
