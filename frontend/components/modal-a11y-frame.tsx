"use client";

import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

type Props = {
  closeHref: string;
  className: string;
  label: string;
  children: ReactNode;
};

function getFocusable(root: HTMLElement): HTMLElement[] {
  return Array.from(
    root.querySelectorAll<HTMLElement>(
      "a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex='-1'])",
    ),
  ).filter((el) => !el.hasAttribute("disabled") && el.getAttribute("aria-hidden") !== "true");
}

export default function ModalA11yFrame({ closeHref, className, label, children }: Props): JSX.Element {
  const ref = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const root = ref.current;
    if (!root) {
      return;
    }

    const focusable = getFocusable(root);
    if (focusable.length > 0) {
      focusable[0].focus();
    } else {
      root.focus();
    }

    const onKeyDown = (event: KeyboardEvent): void => {
      if (!ref.current) {
        return;
      }

      if (event.key === "Escape") {
        event.preventDefault();
        window.location.assign(closeHref);
        return;
      }

      if (event.key !== "Tab") {
        return;
      }

      const items = getFocusable(ref.current);
      if (items.length === 0) {
        event.preventDefault();
        return;
      }

      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement as HTMLElement | null;

      if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
        return;
      }

      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      }
    };

    root.addEventListener("keydown", onKeyDown);
    return () => {
      root.removeEventListener("keydown", onKeyDown);
    };
  }, [closeHref]);

  return (
    <section ref={ref} className={className} role="dialog" aria-modal="true" aria-label={label} tabIndex={-1}>
      {children}
    </section>
  );
}

