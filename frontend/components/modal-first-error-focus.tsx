"use client";

import { useEffect } from "react";

type Props = {
  modalBodySelector: string;
};

export default function ModalFirstErrorFocus({ modalBodySelector }: Props): null {
  useEffect(() => {
    const body = document.querySelector<HTMLElement>(modalBodySelector);
    if (!body) {
      return;
    }

    const invalidField = body.querySelector<HTMLElement>("[data-invalid='true']");
    if (!invalidField) {
      return;
    }

    const bodyRect = body.getBoundingClientRect();
    const fieldRect = invalidField.getBoundingClientRect();
    const targetTop = Math.max(0, body.scrollTop + (fieldRect.top - bodyRect.top) - 16);
    body.scrollTo({ top: targetTop, behavior: "smooth" });
    invalidField.focus({ preventScroll: true });
  }, [modalBodySelector]);

  return null;
}
