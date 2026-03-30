"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactNode, MouseEvent } from "react";

type SessionEditTab = "general" | "schedule" | "visibility" | "notes";

type SessionEditModalBridgeProps = {
  initialActiveTab: SessionEditTab;
  tabReturnHrefs: Record<SessionEditTab, string>;
  children: ReactNode;
};

function isSessionEditTab(value: string | undefined): value is SessionEditTab {
  return value === "general" || value === "schedule" || value === "visibility" || value === "notes";
}

export default function SessionEditModalBridge({
  initialActiveTab,
  tabReturnHrefs,
  children,
}: SessionEditModalBridgeProps): JSX.Element {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const [activeTab, setActiveTab] = useState<SessionEditTab>(initialActiveTab);

  useEffect(() => {
    setActiveTab(initialActiveTab);
  }, [initialActiveTab]);

  useEffect(() => {
    const root = wrapperRef.current;
    if (!root) {
      return;
    }

    const tabTriggers = Array.from(root.querySelectorAll<HTMLElement>("[data-session-edit-tab]"));
    for (const trigger of tabTriggers) {
      const tab = trigger.dataset.sessionEditTab;
      const isActive = tab === activeTab;
      trigger.classList.toggle("active", isActive);
      trigger.setAttribute("aria-current", isActive ? "page" : "false");
    }

    const panels = Array.from(root.querySelectorAll<HTMLElement>("[data-session-edit-panel]"));
    for (const panel of panels) {
      const tab = panel.dataset.sessionEditPanel;
      const isActive = tab === activeTab;
      panel.classList.toggle("active", isActive);
      panel.hidden = !isActive;
    }

    const returnToInputs = Array.from(root.querySelectorAll<HTMLInputElement>("[data-session-edit-return-to]"));
    for (const returnToInput of returnToInputs) {
      returnToInput.value = tabReturnHrefs[activeTab];
    }

    const scheduleOnlyBlocks = Array.from(root.querySelectorAll<HTMLElement>("[data-session-edit-schedule-only]"));
    for (const block of scheduleOnlyBlocks) {
      block.hidden = activeTab !== "schedule";
    }
  }, [activeTab, tabReturnHrefs]);

  const handleClickCapture = (event: MouseEvent<HTMLDivElement>): void => {
    const target = event.target as HTMLElement | null;
    const tabTrigger = target?.closest<HTMLElement>("[data-session-edit-tab]");
    const tab = tabTrigger?.dataset.sessionEditTab;
    if (!isSessionEditTab(tab)) {
      return;
    }
    event.preventDefault();
    setActiveTab(tab);
  };

  return (
    <div ref={wrapperRef} onClickCapture={handleClickCapture}>
      {children}
    </div>
  );
}
