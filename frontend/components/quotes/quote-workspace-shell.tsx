import React from "react";

export default function QuoteWorkspaceShell({
  header,
  sidebar,
  rightRail,
  children,
}: {
  header: React.ReactNode;
  sidebar: React.ReactNode;
  rightRail: React.ReactNode;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <section className="quote-workspace-shell">
      <header className="quote-workspace-header-sticky">{header}</header>
      <aside className="quote-workspace-left">{sidebar}</aside>
      <main className="quote-workspace-main">{children}</main>
      <aside className="quote-workspace-right">{rightRail}</aside>
    </section>
  );
}
