"use client";

import { useEffect, useState } from "react";

import AdminNav from "./admin-nav";
import { type UiLanguage, uiText } from "../lib/ui-i18n";

const SIDEBAR_COLLAPSED_KEY = "admin_sidebar_collapsed_v1";

type AdminSidebarProps = {
  displayName: string;
  email: string;
  roleLabel: string;
  language: UiLanguage;
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

export default function AdminSidebar({ displayName, email, roleLabel, language }: AdminSidebarProps): JSX.Element {
  const [collapsed, setCollapsed] = useState(false);

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
          <small className="admin-user-role muted">{roleLabel}</small>
          <small className="admin-user-email muted">{email}</small>
        </div>
      </div>

      <AdminNav collapsed={collapsed} language={language} />

      <button
        type="button"
        className="admin-sidebar-toggle"
        onClick={toggleCollapsed}
        aria-label={collapsed ? uiText(language, "admin.sidebar_expand_aria") : uiText(language, "admin.sidebar_collapse_aria")}
      >
        <span aria-hidden="true">{collapsed ? "»" : "«"}</span>
        <span className="admin-sidebar-toggle-label">
          {collapsed ? uiText(language, "admin.sidebar_expand") : uiText(language, "admin.sidebar_collapse")}
        </span>
      </button>
    </aside>
  );
}
