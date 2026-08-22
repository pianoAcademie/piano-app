import sanitizeHtml from "sanitize-html";

const ALLOWED_TAGS = [
  "a", "article", "b", "blockquote", "br", "code", "div", "em",
  "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "li", "ol",
  "p", "pre", "section", "small", "span", "strong", "sub", "sup",
  "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul",
] as const;

const EXTERNAL_CONTENT_IFRAME_HOSTS = [
  "cloudlearning.fr",
  "www.cloudlearning.fr",
  "puzzel.org",
  "www.puzzel.org",
  "canva.com",
  "www.canva.com",
] as const;

const EXTERNAL_CONTENT_IMAGE_HOSTS = new Set([
  "piano-academie.com",
  "www.piano-academie.com",
]);

const EXTERNAL_CONTENT_IFRAME_SANDBOX = [
  "allow-forms",
  "allow-popups",
  "allow-presentation",
  "allow-same-origin",
  "allow-scripts",
].join(" ");

function trustedHttpsUrl(value: string | undefined, allowedHosts: ReadonlySet<string>): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    const hostname = parsed.hostname.toLowerCase();
    if (!allowedHosts.has(hostname)) return null;
    if (parsed.protocol === "http:") parsed.protocol = "https:";
    if (parsed.protocol !== "https:") return null;
    return parsed.toString();
  } catch {
    return null;
  }
}

const ALLOWED_STYLES: sanitizeHtml.IOptions["allowedStyles"] = {
  "*": {
    // Email templates use the color-only `background` shorthand for CTA buttons.
    // Keep this deliberately limited to colors so CSS URLs cannot pass through.
    background: [/^#[0-9a-f]{3,8}$/i, /^rgba?\([\d\s,.%]+\)$/i, /^[a-z]+$/i],
    "background-color": [/^#[0-9a-f]{3,8}$/i, /^rgba?\([\d\s,.%]+\)$/i, /^[a-z]+$/i],
    display: [/^(?:inline|inline-block|block)$/i],
    color: [/^#[0-9a-f]{3,8}$/i, /^rgba?\([\d\s,.%]+\)$/i, /^[a-z]+$/i],
    "border-radius": [/^(?:0|\d+(?:\.\d+)?(?:px|pt|em|rem|%))(?:\s+(?:0|\d+(?:\.\d+)?(?:px|pt|em|rem|%))){0,3}$/i],
    "font-size": [/^\d+(?:\.\d+)?(?:px|pt|em|rem|%)$/i],
    "font-style": [/^(?:normal|italic)$/i],
    "font-weight": [/^(?:normal|bold|bolder|lighter|[1-9]00)$/i],
    "line-height": [/^\d+(?:\.\d+)?(?:px|pt|em|rem|%)?$/i],
    margin: [/^(?:0|\d+(?:\.\d+)?(?:px|pt|em|rem|%))(?:\s+(?:0|\d+(?:\.\d+)?(?:px|pt|em|rem|%))){0,3}$/i],
    "margin-left": [/^\d+(?:\.\d+)?(?:px|pt|em|rem|%)$/i],
    padding: [/^(?:0|\d+(?:\.\d+)?(?:px|pt|em|rem|%))(?:\s+(?:0|\d+(?:\.\d+)?(?:px|pt|em|rem|%))){0,3}$/i],
    "text-align": [/^(?:left|right|center|justify)$/i],
    "text-decoration": [/^(?:none|underline|line-through)$/i],
  },
};

/** Sanitizes rich text before it reaches React's raw HTML rendering path. */
export function sanitizeRichHtml(value: string | null | undefined): string {
  if (!value) return "";
  return sanitizeHtml(value, {
    allowedTags: [...ALLOWED_TAGS],
    allowedAttributes: {
      "*": ["class", "style"],
      a: ["href", "name", "target", "rel", "title"],
      table: ["border", "cellpadding", "cellspacing", "role"],
      td: ["colspan", "rowspan", "scope"],
      th: ["colspan", "rowspan", "scope"],
    },
    allowedSchemes: ["https", "mailto", "tel"],
    allowProtocolRelative: false,
    allowedStyles: ALLOWED_STYLES,
    disallowedTagsMode: "discard",
    enforceHtmlBoundary: true,
    transformTags: {
      a: (_tagName, attribs) => ({
        tagName: "a",
        attribs: {
          ...attribs,
          rel: "noopener noreferrer",
          ...(attribs.target === "_blank" ? { target: "_blank" } : {}),
        },
      }),
    },
  });
}

/**
 * Sanitizes LearnDash lesson content while retaining only the media providers
 * used by Piano Academie. Keep this separate from generic rich text so an
 * iframe can never slip into an email, quote, or message preview.
 */
export function sanitizeExternalCourseContentHtml(value: string | null | undefined): string {
  if (!value) return "";
  const iframeHosts = new Set<string>(EXTERNAL_CONTENT_IFRAME_HOSTS);

  return sanitizeHtml(value, {
    allowedTags: [...ALLOWED_TAGS, "figure", "figcaption", "iframe", "img"],
    allowedAttributes: {
      "*": ["class", "style"],
      a: ["href", "name", "target", "rel", "title"],
      iframe: ["src", "title", "loading", "sandbox", "referrerpolicy", "allow", "allowfullscreen"],
      img: ["src", "alt", "title", "width", "height", "loading", "referrerpolicy"],
      table: ["border", "cellpadding", "cellspacing", "role"],
      td: ["colspan", "rowspan", "scope"],
      th: ["colspan", "rowspan", "scope"],
    },
    allowedSchemes: ["https", "mailto", "tel"],
    allowedSchemesByTag: {
      iframe: ["https"],
      img: ["https"],
    },
    allowedIframeHostnames: [...EXTERNAL_CONTENT_IFRAME_HOSTS],
    allowProtocolRelative: false,
    allowedStyles: ALLOWED_STYLES,
    disallowedTagsMode: "discard",
    enforceHtmlBoundary: true,
    transformTags: {
      a: (_tagName, attribs) => ({
        tagName: "a",
        attribs: {
          ...attribs,
          rel: "noopener noreferrer",
          ...(attribs.target === "_blank" ? { target: "_blank" } : {}),
        },
      }),
      iframe: (_tagName, attribs) => {
        const src = trustedHttpsUrl(attribs.src, iframeHosts);
        if (!src) return { tagName: "span", attribs: {} as Record<string, string> };
        return {
          tagName: "iframe",
          attribs: {
            src,
            title: attribs.title || "Contenu pedagogique interactif",
            loading: "lazy",
            sandbox: EXTERNAL_CONTENT_IFRAME_SANDBOX,
            referrerpolicy: "strict-origin-when-cross-origin",
            allow: "fullscreen",
            allowfullscreen: "",
          },
        };
      },
      img: (_tagName, attribs) => {
        const src = trustedHttpsUrl(attribs.src, EXTERNAL_CONTENT_IMAGE_HOSTS);
        if (!src) return { tagName: "span", attribs: {} as Record<string, string> };
        return {
          tagName: "img",
          attribs: {
            src,
            alt: attribs.alt || "",
            ...(attribs.title ? { title: attribs.title } : {}),
            ...(attribs.width ? { width: attribs.width } : {}),
            ...(attribs.height ? { height: attribs.height } : {}),
            loading: "lazy",
            referrerpolicy: "strict-origin-when-cross-origin",
          },
        };
      },
    },
  });
}
