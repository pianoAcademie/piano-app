"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AdminNav from "./admin-nav";

const SIDEBAR_COLLAPSED_KEY = "admin_sidebar_collapsed_v1";

type UiLanguage = "fr" | "en";

type AdminSidebarProps = {
  displayName: string;
  email: string;
  roleLabel: string;
};

function initialsFromDisplayName(value: string): string {
  const tokens = value.trim().split(/\s+/).filter((token) => token.length > 0);
  if (tokens.length === 0) {
    return "A";
  }
  if (tokens.length === 1) {
    return tokens[0].slice(0, 1).toUpperCase();
  }
  return `${tokens[0].slice(0, 1)}${tokens[1].slice(0, 1)}`.toUpperCase();
}

export default function AdminSidebar({ displayName, email, roleLabel }: AdminSidebarProps): JSX.Element {
  const searchParams = useSearchParams();
  const language: UiLanguage = searchParams.get("lang") === "en" ? "en" : "fr";
  const [collapsed, setCollapsed] = useState(false);
  const displayedRoleLabel = language === "en" && roleLabel === "Administrateur" ? "Administrator" : roleLabel;
  const collapseLabel = language === "en" ? "Collapse sidebar" : "Replier la barre laterale";
  const expandLabel = language === "en" ? "Expand sidebar" : "Etendre la barre laterale";
  const collapseText = language === "en" ? "Collapse" : "Replier";
  const expandText = language === "en" ? "Expand" : "Etendre";

  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1");
    } catch {
      setCollapsed(false);
    }
  }, []);

  const toggleCollapsed = (): void => {
    const next = !collapsed;
    setCollapsed(next);
    try {
      window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, next ? "1" : "0");
    } catch {
      // Ignore localStorage failures in private mode.
    }
  };

  return (
    <aside className={`admin-sidebar ${collapsed ? "collapsed" : ""}`}>
      <div className="admin-brand" title="Piano Academie">
        <span className="admin-brand-mark" aria-hidden="true">
          PA
        </span>
        <span className="admin-brand-text">Piano Academie</span>
      </div>

      <div className="admin-user-card">
        <span className="admin-user-avatar" aria-hidden="true">
          {initialsFromDisplayName(displayName)}
        </span>
        <div className="admin-user-main">
          <p className="admin-user-name">{displayName}</p>
          <small className="admin-user-role muted">{displayedRoleLabel}</small>
          <small className="admin-user-email muted">{email}</small>
        </div>
      </div>

      <AdminNav collapsed={collapsed} language={language} />

      <button
        type="button"
        className="admin-sidebar-toggle"
        onClick={toggleCollapsed}
        aria-label={collapsed ? expandLabel : collapseLabel}
      >
        <span aria-hidden="true">{collapsed ? "»" : "«"}</span>
        <span className="admin-sidebar-toggle-label">{collapsed ? expandText : collapseText}</span>
      </button>
    </aside>
  );
}
