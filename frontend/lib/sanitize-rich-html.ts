import sanitizeHtml from "sanitize-html";

const ALLOWED_TAGS = [
  "a", "article", "b", "blockquote", "br", "code", "div", "em",
  "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "li", "ol",
  "p", "pre", "section", "small", "span", "strong", "sub", "sup",
  "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul",
] as const;

const ALLOWED_STYLES: sanitizeHtml.IOptions["allowedStyles"] = {
  "*": {
    "background-color": [/^#[0-9a-f]{3,8}$/i, /^rgba?\([\d\s,.%]+\)$/i, /^[a-z]+$/i],
    color: [/^#[0-9a-f]{3,8}$/i, /^rgba?\([\d\s,.%]+\)$/i, /^[a-z]+$/i],
    "font-size": [/^\d+(?:\.\d+)?(?:px|pt|em|rem|%)$/i],
    "font-style": [/^(?:normal|italic)$/i],
    "font-weight": [/^(?:normal|bold|bolder|lighter|[1-9]00)$/i],
    "line-height": [/^\d+(?:\.\d+)?(?:px|pt|em|rem|%)?$/i],
    "margin-left": [/^\d+(?:\.\d+)?(?:px|pt|em|rem|%)$/i],
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
