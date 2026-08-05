"use client";

import { useEffect, useState } from "react";

import { type UiLanguage, uiText } from "../lib/ui-i18n";

type PortalReadOnlyPreviewGuardProps = {
  enabled: boolean;
  language: UiLanguage;
};

export default function PortalReadOnlyPreviewGuard({
  enabled,
  language,
}: PortalReadOnlyPreviewGuardProps): JSX.Element | null {
  const [blocked, setBlocked] = useState(false);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    const showBlockedMessage = (): void => {
      setBlocked(true);
      window.setTimeout(() => setBlocked(false), 3500);
    };

    const onSubmit = (event: SubmitEvent): void => {
      const form = event.target instanceof HTMLFormElement ? event.target : null;
      if (!form || form.dataset.readOnlyPreviewAllow === "true") {
        return;
      }
      const method = (form.getAttribute("method") || "post").toLowerCase();
      if (method === "get") {
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();
      showBlockedMessage();
    };

    const onClick = (event: MouseEvent): void => {
      const target = event.target instanceof Element ? event.target : null;
      const blockedLink = target?.closest<HTMLAnchorElement>('a[data-read-only-preview-block="true"]');
      if (!blockedLink) {
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();
      showBlockedMessage();
    };

    document.addEventListener("submit", onSubmit, true);
    document.addEventListener("click", onClick, true);
    return () => {
      document.removeEventListener("submit", onSubmit, true);
      document.removeEventListener("click", onClick, true);
    };
  }, [enabled]);

  if (!enabled || !blocked) {
    return null;
  }

  return (
    <div className="portal-read-only-preview-toast" role="alert">
      {uiText(language, "portal.read_only_action_blocked")}
    </div>
  );
}
