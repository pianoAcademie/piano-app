import Link from "next/link";

type PublicInfoPageProps = {
  eyebrow: string;
  title: string;
  intro: string;
  sections: Array<{
    title: string;
    body: string[];
  }>;
};

const pageStyle = {
  minHeight: "100vh",
  background: "#f7f3ea",
  color: "#1f2937",
  padding: "48px 20px",
} as const;

const shellStyle = {
  width: "min(860px, 100%)",
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

export function PublicInfoPage({ eyebrow, title, intro, sections }: PublicInfoPageProps): JSX.Element {
  return (
    <main style={pageStyle}>
      <article style={shellStyle}>
        <p style={eyebrowStyle}>{eyebrow}</p>
        <h1 style={{ margin: "8px 0 12px", fontSize: 34, lineHeight: 1.15 }}>{title}</h1>
        <p style={{ color: "#6b6258", fontSize: 17, lineHeight: 1.6 }}>{intro}</p>

        <div style={{ display: "grid", gap: 24, marginTop: 32 }}>
          {sections.map((section) => (
            <section key={section.title}>
              <h2 style={{ margin: "0 0 10px", fontSize: 20 }}>{section.title}</h2>
              {section.body.map((paragraph) => (
                <p key={paragraph} style={{ margin: "8px 0", color: "#4b5563", lineHeight: 1.65 }}>
                  {paragraph}
                </p>
              ))}
            </section>
          ))}
        </div>

        <footer style={{ marginTop: 36, paddingTop: 20, borderTop: "1px solid #eadcc4" }}>
          <Link href="/login" style={{ color: "#8a5a16", fontWeight: 700 }}>
            Retour a la connexion
          </Link>
        </footer>
      </article>
    </main>
  );
}
