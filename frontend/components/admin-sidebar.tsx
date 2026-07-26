"use client";

import { useEffect, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";

import AdminNav from "./admin-nav";

const SIDEBAR_COLLAPSED_KEY = "admin_sidebar_collapsed_v1";

type UiLanguage = "fr" | "en";

type AdminSidebarProps = {
  displayName: string;
  email: string;
  roleLabel: string;
  isFullAdmin?: boolean;
  permissions?: Partial<Record<string, boolean | string | null>>;
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

export default function AdminSidebar({ displayName, email, roleLabel, isFullAdmin = true, permissions = {} }: AdminSidebarProps): JSX.Element {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const navigationKey = `${pathname}?${searchParams.toString()}`;
  const language: UiLanguage = searchParams.get("lang") === "en" ? "en" : "fr";
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const displayedRoleLabel = language === "en" && roleLabel === "Administrateur" ? "Administrator" : roleLabel;
  const collapseLabel = language === "en" ? "Collapse sidebar" : "Replier la barre laterale";
  const expandLabel = language === "en" ? "Expand sidebar" : "Etendre la barre laterale";
  const collapseText = language === "en" ? "Collapse" : "Replier";
  const expandText = language === "en" ? "Expand" : "Etendre";
  const mobileMenuText = language === "en" ? "Menu" : "Menu";
  const openMobileMenuLabel = language === "en" ? "Open admin menu" : "Ouvrir le menu admin";
  const closeMobileMenuLabel = language === "en" ? "Close admin menu" : "Fermer le menu admin";

  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1");
    } catch {
      setCollapsed(false);
    }
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [navigationKey]);

  useEffect(() => {
    if (!mobileOpen) {
      return undefined;
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
      }
    };
    document.body.classList.add("admin-mobile-nav-open");
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.classList.remove("admin-mobile-nav-open");
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [mobileOpen]);

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
    <>
      <button
        type="button"
        className="admin-mobile-menu-trigger"
        aria-label={openMobileMenuLabel}
        aria-expanded={mobileOpen}
        aria-controls="admin-sidebar-panel"
        onClick={() => setMobileOpen(true)}
      >
        <span aria-hidden="true">☰</span>
        <span>{mobileMenuText}</span>
      </button>

      <button
        type="button"
        className={`admin-mobile-menu-backdrop ${mobileOpen ? "visible" : ""}`}
        aria-label={closeMobileMenuLabel}
        aria-hidden={!mobileOpen}
        tabIndex={mobileOpen ? 0 : -1}
        onClick={() => setMobileOpen(false)}
      />

      <aside
        id="admin-sidebar-panel"
        className={`admin-sidebar ${collapsed ? "collapsed" : ""} ${mobileOpen ? "mobile-open" : ""}`.trim()}
      >
        <div className="admin-sidebar-mobile-head">
          <strong>{language === "en" ? "Admin navigation" : "Navigation admin"}</strong>
          <button type="button" onClick={() => setMobileOpen(false)} aria-label={closeMobileMenuLabel}>
            ×
          </button>
        </div>

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

        <AdminNav
          collapsed={collapsed}
          language={language}
          isFullAdmin={isFullAdmin}
          permissions={permissions}
          onNavigate={() => setMobileOpen(false)}
        />

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
    </>
  );
}
