import Link from "next/link";
import type { ReactNode } from "react";

type PublicInfoPageProps = {
  eyebrow: string;
  title: string;
  intro: string;
  sections: Array<{
    title: string;
    body: ReactNode[];
    items?: ReactNode[];
    blocks?: Array<
      | { kind: "paragraph"; content: ReactNode }
      | { kind: "list"; items: ReactNode[] }
    >;
  }>;
  languageLinks?: Array<{
    href: string;
    label: string;
    active: boolean;
  }>;
  updatedAt?: string;
  footerHref?: string;
  footerLabel?: string;
};

const pageStyle = {
  minHeight: "100vh",
  background: "#f7f3ea",
  color: "#1f2937",
  padding: "48px 20px",
} as const;

const shellStyle = {
  width: "min(860px, 100%)",
  boxSizing: "border-box",
  margin: "0 auto",
  background: "#fffaf1",
  border: "1px solid #e4d3b5",
  borderRadius: 8,
  boxShadow: "0 16px 40px rgba(31, 41, 55, 0.08)",
  padding: "32px",
} as const;

const eyebrowStyle = {
  color: "#8a5a16",
  fontSize: 13,
  fontWeight: 700,
  letterSpacing: 0,
  textTransform: "uppercase",
} as const;

export function PublicInfoPage({
  eyebrow,
  title,
  intro,
  sections,
  languageLinks = [],
  updatedAt,
  footerHref = "/login",
  footerLabel = "Retour a la connexion",
}: PublicInfoPageProps): JSX.Element {
  return (
    <main style={pageStyle}>
      <article style={shellStyle}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 12,
          }}
        >
          <p style={{ ...eyebrowStyle, margin: 0 }}>{eyebrow}</p>
          {languageLinks.length > 0 ? (
            <nav aria-label="Language / Langue" style={{ display: "flex", gap: 8 }}>
              {languageLinks.map((languageLink) => (
                <Link
                  key={languageLink.href}
                  href={languageLink.href}
                  hrefLang={languageLink.label.toLowerCase()}
                  aria-current={languageLink.active ? "page" : undefined}
                  style={{
                    border: `1px solid ${languageLink.active ? "#8a5a16" : "#d8c7aa"}`,
                    borderRadius: 999,
                    color: languageLink.active ? "#fffaf1" : "#6b4a1d",
                    background: languageLink.active ? "#8a5a16" : "transparent",
                    fontSize: 13,
                    fontWeight: 700,
                    padding: "7px 11px",
                    textDecoration: "none",
                  }}
                >
                  {languageLink.label}
                </Link>
              ))}
            </nav>
          ) : null}
        </div>
        <h1 style={{ margin: "8px 0 12px", fontSize: 34, lineHeight: 1.15 }}>{title}</h1>
        <p style={{ color: "#6b6258", fontSize: 17, lineHeight: 1.6 }}>{intro}</p>
        {updatedAt ? <p style={{ color: "#786f65", fontSize: 14, marginTop: 12 }}>{updatedAt}</p> : null}

        <div style={{ display: "grid", gap: 24, marginTop: 32 }}>
          {sections.map((section) => (
            <section key={section.title}>
              <h2 style={{ margin: "0 0 10px", fontSize: 20 }}>{section.title}</h2>
              {section.blocks
                ? section.blocks.map((block, index) =>
                    block.kind === "paragraph" ? (
                      <p
                        key={index}
                        style={{ margin: "8px 0", color: "#4b5563", lineHeight: 1.65, overflowWrap: "anywhere" }}
                      >
                        {block.content}
                      </p>
                    ) : (
                      <ul
                        key={index}
                        style={{ margin: "10px 0", paddingLeft: 24, color: "#4b5563", lineHeight: 1.65 }}
                      >
                        {block.items.map((item, itemIndex) => (
                          <li key={itemIndex} style={{ margin: "6px 0" }}>
                            {item}
                          </li>
                        ))}
                      </ul>
                    ),
                  )
                : (
                  <>
                    {section.body.map((paragraph, index) => (
                      <p
                        key={index}
                        style={{ margin: "8px 0", color: "#4b5563", lineHeight: 1.65, overflowWrap: "anywhere" }}
                      >
                        {paragraph}
                      </p>
                    ))}
                    {section.items?.length ? (
                      <ul style={{ margin: "10px 0 0", paddingLeft: 24, color: "#4b5563", lineHeight: 1.65 }}>
                        {section.items.map((item, index) => (
                          <li key={index} style={{ margin: "6px 0" }}>
                            {item}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </>
                )}
            </section>
          ))}
        </div>

        <footer style={{ marginTop: 36, paddingTop: 20, borderTop: "1px solid #eadcc4" }}>
          <Link href={footerHref} style={{ color: "#8a5a16", fontWeight: 700 }}>
            {footerLabel}
          </Link>
        </footer>
      </article>
    </main>
  );
}
