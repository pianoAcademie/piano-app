"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

type ClientTabNavigationProps = {
  ariaLabel: string;
  clientId: string;
  currentTab: string;
  tabs: Array<{ id: string; label: string }>;
};

function tabHref(clientId: string, tab: string): string {
  return `/admin/clients/${clientId}?tab=${tab}`;
}

export default function ClientTabNavigation({
  ariaLabel,
  clientId,
  currentTab,
  tabs,
}: ClientTabNavigationProps): JSX.Element {
  const router = useRouter();
  const [pendingTab, setPendingTab] = useState<string | null>(null);

  useEffect(() => {
    setPendingTab(null);
  }, [currentTab]);

  const warmTab = (tab: string) => {
    if (tab !== currentTab) {
      router.prefetch(tabHref(clientId, tab));
    }
  };

  return (
    <nav className="client-tabs" aria-label={ariaLabel} aria-busy={pendingTab !== null}>
      {tabs.map((tab) => {
        const href = tabHref(clientId, tab.id);
        const isSelected = (pendingTab ?? currentTab) === tab.id;
        return (
          <Link
            key={tab.id}
            href={href}
            prefetch={false}
            className={`client-tab ${isSelected ? "active" : ""}`}
            aria-current={currentTab === tab.id ? "page" : undefined}
            onPointerEnter={() => warmTab(tab.id)}
            onFocus={() => warmTab(tab.id)}
            onTouchStart={() => warmTab(tab.id)}
            onClick={() => setPendingTab(tab.id)}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
