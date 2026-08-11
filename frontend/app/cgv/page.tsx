import type { Metadata } from "next";
import { headers } from "next/headers";
import type { ReactNode } from "react";

import { backendRequest } from "../../lib/backend";
import type { PublicLegalTermsOut } from "../../lib/types";
import { PublicInfoPage } from "../public-info-page";

type SearchParams = Record<string, string | string[] | undefined>;
type LegalTermsLanguage = "fr" | "en";

type LegalSection = {
  title: string;
  body: ReactNode[];
  blocks: Array<
    | { kind: "paragraph"; content: ReactNode }
    | { kind: "list"; items: ReactNode[] }
  >;
};

export const dynamic = "force-dynamic";

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function resolveLanguage(rawLanguage: string, acceptLanguage: string): LegalTermsLanguage {
  for (const candidate of [rawLanguage, acceptLanguage]) {
    const normalized = candidate.trim().toLowerCase();
    if (normalized === "en" || normalized.startsWith("en-")) {
      return "en";
    }
    if (normalized === "fr" || normalized.startsWith("fr-")) {
      return "fr";
    }
  }
  return "fr";
}

function renderInlineMarkdown(value: string): ReactNode {
  const tokenPattern = /(\*\*.+?\*\*|\[[^\]]+\]\((?:https?:\/\/|mailto:)[^)]+\))/g;
  const parts = value.split(tokenPattern).filter(Boolean);

  return parts.map((part, index) => {
    const strong = part.match(/^\*\*(.+)\*\*$/);
    if (strong) {
      return <strong key={index}>{renderInlineMarkdown(strong[1])}</strong>;
    }
    const link = part.match(/^\[([^\]]+)\]\(((?:https?:\/\/|mailto:)[^)]+)\)$/);
    if (link) {
      const external = link[2].startsWith("http");
      return (
        <a
          key={index}
          href={link[2]}
          {...(external ? { target: "_blank", rel: "noreferrer" } : {})}
          style={{ color: "#8a5a16", fontWeight: 600 }}
        >
          {link[1]}
        </a>
      );
    }
    return part;
  });
}

function stripHeadingMarkup(value: string): string {
  return value.replace(/^\*\*(.+)\*\*$/, "$1").trim();
}

function parseLegalTerms(content: string, language: LegalTermsLanguage): LegalSection[] {
  const sections: LegalSection[] = [];
  let current: LegalSection = {
    title: language === "en" ? "Terms" : "Dispositions générales",
    body: [],
    blocks: [],
  };
  let paragraph: string[] = [];
  let listItems: string[] = [];

  const flushParagraph = () => {
    const value = paragraph.join(" ").trim();
    if (value) {
      const contentNode = renderInlineMarkdown(value);
      current.body.push(contentNode);
      current.blocks.push({ kind: "paragraph", content: contentNode });
    }
    paragraph = [];
  };
  const flushList = () => {
    if (listItems.length > 0) {
      current.blocks.push({ kind: "list", items: listItems.map(renderInlineMarkdown) });
    }
    listItems = [];
  };
  const flushSection = () => {
    flushParagraph();
    flushList();
    if (current.blocks.length > 0) {
      sections.push(current);
    }
  };

  for (const rawLine of content.replace(/\r\n?/g, "\n").split("\n")) {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = line.match(/^#{1,6}\s+(.+)$/);
    if (heading) {
      flushSection();
      current = { title: stripHeadingMarkup(heading[1]), body: [], blocks: [] };
      continue;
    }
    const bullet = line.match(/^[-*•]\s+(.+)$/);
    if (bullet) {
      flushParagraph();
      listItems.push(bullet[1]);
      continue;
    }
    flushList();
    paragraph.push(line);
  }
  flushSection();

  return sections.length > 0
    ? sections
    : [
        {
          title: language === "en" ? "Terms" : "Conditions générales de vente",
          body: [renderInlineMarkdown(content)],
          blocks: [{ kind: "paragraph", content: renderInlineMarkdown(content) }],
        },
      ];
}

function formatUpdatedAt(value: string | null, language: LegalTermsLanguage): string | undefined {
  if (!value) {
    return undefined;
  }
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) {
    return undefined;
  }
  const formatted = new Intl.DateTimeFormat(language === "en" ? "en-GB" : "fr-FR", {
    dateStyle: "long",
    timeStyle: "short",
    timeZone: "Europe/Paris",
  }).format(date);
  return language === "en" ? `Last updated: ${formatted}` : `Dernière mise à jour : ${formatted}`;
}

export function generateMetadata({ searchParams }: { searchParams: SearchParams }): Metadata {
  const language = resolveLanguage(readParam(searchParams, "lang"), headers().get("accept-language") ?? "");
  return {
    title: language === "en" ? "Terms and conditions of sale | Piano Académie" : "Conditions générales de vente | Piano Académie",
    description:
      language === "en"
        ? "Terms and conditions of sale for Piano Académie services."
        : "Conditions générales de vente applicables aux services Piano Académie.",
    alternates: {
      canonical: "https://app.piano-academie.com/cgv",
      languages: {
        "fr-FR": "https://app.piano-academie.com/cgv?lang=fr",
        "en-GB": "https://app.piano-academie.com/cgv?lang=en",
      },
    },
  };
}

export default async function LegalTermsPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const language = resolveLanguage(readParam(searchParams, "lang"), headers().get("accept-language") ?? "");
  const result = await backendRequest<PublicLegalTermsOut>(`/api/v1/public/legal-terms?language=${language}`);

  if (!result.ok) {
    return (
      <PublicInfoPage
        eyebrow={language === "en" ? "Legal information" : "Informations légales"}
        title={language === "en" ? "Terms and conditions of sale" : "Conditions générales de vente"}
        intro={
          language === "en"
            ? "The terms and conditions are temporarily unavailable. Please contact Piano Académie before making a purchase."
            : "Les conditions générales de vente sont temporairement indisponibles. Merci de contacter Piano Académie avant tout achat."
        }
        languageLinks={[
          { href: "/cgv?lang=fr", label: "FR", active: language === "fr" },
          { href: "/cgv?lang=en", label: "EN", active: language === "en" },
        ]}
        footerHref={language === "en" ? "/login?lang=en" : "/login"}
        footerLabel={language === "en" ? "Back to sign in" : "Retour à la connexion"}
        sections={[]}
      />
    );
  }

  const fallbackNotice = result.data.used_fallback
    ? language === "en"
      ? "The English version has not yet been entered. The French version currently shown is the contractual version available."
      : ""
    : language === "en"
      ? "These terms govern purchases made through Piano Académie."
      : "Ces conditions régissent les achats effectués auprès de Piano Académie.";

  return (
    <PublicInfoPage
      eyebrow={language === "en" ? "Legal information" : "Informations légales"}
      title={language === "en" ? "Terms and conditions of sale" : "Conditions générales de vente"}
      intro={fallbackNotice}
      updatedAt={formatUpdatedAt(result.data.updated_at, language)}
      languageLinks={[
        { href: "/cgv?lang=fr", label: "FR", active: language === "fr" },
        { href: "/cgv?lang=en", label: "EN", active: language === "en" },
      ]}
      footerHref={language === "en" ? "/login?lang=en" : "/login"}
      footerLabel={language === "en" ? "Back to sign in" : "Retour à la connexion"}
      sections={parseLegalTerms(result.data.content, language)}
    />
  );
}
