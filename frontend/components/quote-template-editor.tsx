"use client";

import { useMemo, useState } from "react";
import FontFamily from "@tiptap/extension-font-family";
import Image from "@tiptap/extension-image";
import Link from "@tiptap/extension-link";
import TextStyle from "@tiptap/extension-text-style";
import TextAlign from "@tiptap/extension-text-align";
import Underline from "@tiptap/extension-underline";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";

type QuoteTemplateVariable = {
  key: string;
  label: string;
  description: string;
  example: string;
};

type EditorSnippet = {
  key: string;
  label: string;
  value: string;
};

type QuoteTemplateEditorProps = {
  subjectName: string;
  bodyName: string;
  defaultSubject: string;
  defaultBody: string;
  variables: QuoteTemplateVariable[];
};

function tokenForVariable(key: string): string {
  return `{${key}}`;
}

function looksLikeHtml(value: string): boolean {
  return /<\s*[a-z!/][^>]*>/i.test(value);
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function plainTextToHtml(value: string): string {
  if (!value) {
    return "";
  }
  return escapeHtml(value).replace(/\n/g, "<br>");
}

function decodeHtmlEntities(value: string): string {
  if (!value || typeof document === "undefined") {
    return value;
  }
  const textarea = document.createElement("textarea");
  textarea.innerHTML = value;
  return textarea.value;
}

function normalizeInitialEditorValue(value: string): string {
  const raw = String(value || "");
  if (!raw.trim()) {
    return "";
  }
  let decoded = raw;
  for (let i = 0; i < 3; i += 1) {
    const next = decodeHtmlEntities(decoded);
    if (next === decoded) {
      break;
    }
    decoded = next;
  }
  if (looksLikeHtml(decoded)) {
    return decoded;
  }
  if (looksLikeHtml(raw)) {
    return raw;
  }
  return plainTextToHtml(decoded);
}

const FONT_FAMILY_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "Police par defaut" },
  { value: "Arial", label: "Arial" },
  { value: "Verdana", label: "Verdana" },
  { value: "Georgia", label: "Georgia" },
  { value: "Times New Roman", label: "Times New Roman" },
  { value: "Trebuchet MS", label: "Trebuchet MS" },
];

const FONT_SIZE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "Taille par defaut" },
  { value: "11px", label: "11 px" },
  { value: "12px", label: "12 px" },
  { value: "13px", label: "13 px" },
  { value: "14px", label: "14 px" },
  { value: "16px", label: "16 px" },
  { value: "18px", label: "18 px" },
  { value: "20px", label: "20 px" },
];

export default function QuoteTemplateEditor({
  subjectName,
  bodyName,
  defaultSubject,
  defaultBody,
  variables,
}: QuoteTemplateEditorProps): JSX.Element {
  const snippets: EditorSnippet[] = useMemo(
    () => [
      {
        key: "page_break",
        label: "Saut de page",
        value: "{page_break_html}",
      },
      {
        key: "footer",
        label: "Pied de page standard",
        value: "{footer_standard_html}",
      },
      {
        key: "document_style",
        label: "Style documentaire",
        value: "{document_style_html}",
      },
      {
        key: "cover_page",
        label: "Page de couverture standard",
        value: "{cover_page_standard_html}",
      },
      {
        key: "header_page",
        label: "Entete standard",
        value: "{header_standard_html}",
      },
      {
        key: "section",
        label: "Bloc section simple",
        value: "<h2>Titre section</h2><p>Contenu...</p>",
      },
      {
        key: "block_recipient",
        label: "Bloc destinataire",
        value:
          "<h2>Destinataire</h2>"
          + "<p><strong>Nom :</strong> {recipient_name}</p>"
          + "<p><strong>Email :</strong> {recipient_email}</p>"
          + "<p><strong>Type :</strong> {prospect_type_label}</p>"
          + "{prospect_identity_block_html}",
      },
      {
        key: "block_family_page",
        label: "Page informations famille",
        value:
          "{page_break_html}"
          + "{header_standard_html}"
          + "<h2>Informations famille</h2>"
          + "<div class='quote-block'>{prospect_identity_block_html}</div>"
          + "{footer_standard_html}",
      },
      {
        key: "block_services",
        label: "Bloc activites retenues",
        value:
          "<h2>Les Activites retenues</h2>{activities_planning_table_html}",
      },
      {
        key: "block_prestations",
        label: "Bloc prestations",
        value: "<h2>Prestations</h2>{services_table_html}",
      },
      {
        key: "block_material",
        label: "Bloc materiel",
        value: "<h2>Materiel</h2>{products_table_html}",
      },
      {
        key: "block_adjustments_table",
        label: "Bloc remises/supplements",
        value: "<h2>Remises et supplements</h2>{adjustments_table_html}",
      },
      {
        key: "block_payment",
        label: "Bloc paiement",
        value:
          "<h2>Paiement</h2>"
          + "<p>{payment_schedule_summary}</p>"
          + "{payment_method_block_html}"
          + "{payment_schedule_table_html}",
      },
      {
        key: "block_adjustment",
        label: "Bloc recapitulatif financier",
        value: "{financial_recap_block_html}",
      },
      {
        key: "block_calendar",
        label: "Bloc calendrier",
        value:
          "<h2>Calendrier des cours</h2>"
          + "<p>{calendar_summary}</p>"
          + "{calendar_activity_semesters_html}",
      },
      {
        key: "page_full",
        label: "Page complete (entete + bloc + footer)",
        value:
          "{header_standard_html}"
          + "<div class='quote-block'><h2>Titre page</h2><p>Contenu...</p></div>"
          + "{footer_standard_html}"
          + "{page_break_html}",
      },
      {
        key: "totals_table",
        label: "Tableau totaux",
        value: "{financial_recap_block_html}",
      },
    ],
    [],
  );
  const hasVariables = variables.length > 0;
  const initialBody = normalizeInitialEditorValue(defaultBody);
  const [subject, setSubject] = useState<string>(defaultSubject);
  const [body, setBody] = useState<string>(initialBody);
  const [editorMode, setEditorMode] = useState<"wysiwyg" | "html">("wysiwyg");
  const [fontFamily, setFontFamily] = useState<string>("");
  const [fontSize, setFontSize] = useState<string>("");
  const [editorPopupOpen, setEditorPopupOpen] = useState<boolean>(false);
  const [selectedVariable, setSelectedVariable] = useState<string>(variables[0]?.key || "quote_number");
  const [selectedSnippet, setSelectedSnippet] = useState<string>(snippets[0]?.key || "page_break");
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
      TextStyle,
      FontFamily.configure({
        types: ["textStyle"],
      }),
      Underline,
      Link.configure({
        openOnClick: false,
      }),
      TextAlign.configure({
        types: ["heading", "paragraph"],
      }),
      Image,
    ],
    content: initialBody,
    editorProps: {
      attributes: {
        class: "quote-template-editor-surface",
      },
    },
    onUpdate: ({ editor: editorInstance }) => {
      setBody(editorInstance.getHTML());
    },
  });

  const selected = useMemo(
    () => variables.find((item) => item.key === selectedVariable) ?? variables[0] ?? null,
    [selectedVariable, variables],
  );
  const selectedSnippetDef = useMemo(
    () => snippets.find((item) => item.key === selectedSnippet) ?? snippets[0] ?? null,
    [selectedSnippet, snippets],
  );

  function applyCommand(
    action:
      | "bold"
      | "italic"
      | "underline"
      | "paragraph"
      | "heading1"
      | "heading2"
      | "heading3"
      | "bulletList"
      | "orderedList"
      | "alignLeft"
      | "alignCenter"
      | "alignRight"
      | "undo"
      | "redo",
  ): void {
    if (!editor || editorMode !== "wysiwyg") {
      return;
    }
    const chain = editor.chain().focus();
    switch (action) {
      case "bold":
        chain.toggleBold().run();
        break;
      case "italic":
        chain.toggleItalic().run();
        break;
      case "underline":
        chain.toggleUnderline().run();
        break;
      case "paragraph":
        chain.setParagraph().run();
        break;
      case "heading1":
        chain.toggleHeading({ level: 1 }).run();
        break;
      case "heading2":
        chain.toggleHeading({ level: 2 }).run();
        break;
      case "heading3":
        chain.toggleHeading({ level: 3 }).run();
        break;
      case "bulletList":
        chain.toggleBulletList().run();
        break;
      case "orderedList":
        chain.toggleOrderedList().run();
        break;
      case "alignLeft":
        chain.setTextAlign("left").run();
        break;
      case "alignCenter":
        chain.setTextAlign("center").run();
        break;
      case "alignRight":
        chain.setTextAlign("right").run();
        break;
      case "undo":
        chain.undo().run();
        break;
      case "redo":
        chain.redo().run();
        break;
      default:
        break;
    }
    setBody(editor.getHTML());
  }

  function switchToWysiwyg(): void {
    if (editorMode === "wysiwyg") {
      return;
    }
    const next = normalizeInitialEditorValue(body);
    if (editor) {
      editor.commands.setContent(next, false);
    }
    setBody(next);
    setEditorMode("wysiwyg");
  }

  function switchToHtml(): void {
    if (editorMode === "html") {
      return;
    }
    if (editor) {
      setBody(editor.getHTML());
    }
    setEditorPopupOpen(false);
    setEditorMode("html");
  }

  function insertHtmlAtCursor(html: string): void {
    if (!editor || editorMode !== "wysiwyg") {
      return;
    }
    editor.chain().focus().insertContent(html).run();
    setBody(editor.getHTML());
  }

  function insertToken(): void {
    if (!selected) {
      return;
    }
    const token = tokenForVariable(selected.key);
    if (editorMode === "wysiwyg" && editor) {
      editor.chain().focus().insertContent(token).run();
      setBody(editor.getHTML());
      return;
    }
    setBody((prev) => `${prev}${prev.endsWith("\n") || !prev ? "" : "\n"}${token}`);
  }

  function insertSnippet(): void {
    if (!selectedSnippetDef) {
      return;
    }
    const snippet = selectedSnippetDef.value;
    if (editorMode === "wysiwyg" && editor) {
      insertHtmlAtCursor(snippet);
      return;
    }
    setBody((prev) => `${prev}${prev.endsWith("\n") || !prev ? "" : "\n"}${snippet}`);
  }

  function insertLink(): void {
    if (!editor || editorMode !== "wysiwyg") {
      return;
    }
    const href = window.prompt("URL du lien (https://...)");
    if (!href) {
      return;
    }
    editor.chain().focus().extendMarkRange("link").setLink({ href }).run();
    setBody(editor.getHTML());
  }

  function applyFontFamily(next: string): void {
    setFontFamily(next);
    if (!editor || editorMode !== "wysiwyg") {
      return;
    }
    const chain = editor.chain().focus();
    if (!next) {
      chain.unsetFontFamily().run();
    } else {
      chain.setFontFamily(next).run();
    }
    setBody(editor.getHTML());
  }

  function applyFontSize(next: string): void {
    setFontSize(next);
    if (!editor || editorMode !== "wysiwyg") {
      return;
    }
    const chain = editor.chain().focus();
    if (!next) {
      chain.unsetMark("textStyle").run();
    } else {
      chain.setMark("textStyle", { fontSize: next }).run();
    }
    setBody(editor.getHTML());
  }

  function insertImageUrl(): void {
    if (!editor || editorMode !== "wysiwyg") {
      return;
    }
    const src = window.prompt("URL de l image (https://...)");
    if (!src) {
      return;
    }
    editor.chain().focus().setImage({ src }).run();
    setBody(editor.getHTML());
  }

  function renderToolbar(showPopupButton = true): JSX.Element {
    return (
      <div className="quote-template-toolbar" aria-label="Outils de mise en forme">
        <div className="toolbar-group">
          <button type="button" className="ghost small-btn" onClick={() => applyCommand("bold")}>B</button>
          <button type="button" className="ghost small-btn" onClick={() => applyCommand("italic")}>I</button>
          <button type="button" className="ghost small-btn" onClick={() => applyCommand("underline")}>U</button>
        </div>
        <div className="toolbar-group">
          <button type="button" className="ghost small-btn" onClick={() => applyCommand("heading1")}>H1</button>
          <button type="button" className="ghost small-btn" onClick={() => applyCommand("heading2")}>H2</button>
          <button type="button" className="ghost small-btn" onClick={() => applyCommand("heading3")}>H3</button>
          <button type="button" className="ghost small-btn" onClick={() => applyCommand("paragraph")}>P</button>
        </div>
        <div className="toolbar-group">
          <button type="button" className="ghost small-btn" onClick={() => applyCommand("bulletList")}>• Liste</button>
          <button type="button" className="ghost small-btn" onClick={() => applyCommand("orderedList")}>1. Liste</button>
        </div>
        <div className="toolbar-group">
          <button type="button" className="ghost small-btn" onClick={() => applyCommand("alignLeft")}>Gauche</button>
          <button type="button" className="ghost small-btn" onClick={() => applyCommand("alignCenter")}>Centre</button>
          <button type="button" className="ghost small-btn" onClick={() => applyCommand("alignRight")}>Droite</button>
        </div>
        <div className="toolbar-group">
          <button type="button" className="ghost small-btn" onClick={insertLink}>Lien</button>
          <button type="button" className="ghost small-btn" onClick={insertImageUrl}>Image URL</button>
        </div>
        <div className="toolbar-group">
          <select
            className="ghost small-btn"
            value={fontFamily}
            onChange={(event) => applyFontFamily(event.target.value)}
            aria-label="Famille de police"
          >
            {FONT_FAMILY_OPTIONS.map((option) => (
              <option key={option.label} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <select
            className="ghost small-btn"
            value={fontSize}
            onChange={(event) => applyFontSize(event.target.value)}
            aria-label="Taille de police"
          >
            {FONT_SIZE_OPTIONS.map((option) => (
              <option key={option.label} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="toolbar-group">
          <button type="button" className="ghost small-btn" onClick={() => applyCommand("undo")}>↶</button>
          <button type="button" className="ghost small-btn" onClick={() => applyCommand("redo")}>↷</button>
          {showPopupButton ? (
            <button
              type="button"
              className="ghost small-btn"
              onClick={() => setEditorPopupOpen(true)}
            >
              Ouvrir en popup
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="grid config-form-grid">
      <label>
        Objet du template
        <input
          type="text"
          name={subjectName}
          value={subject}
          onChange={(event) => setSubject(event.target.value)}
          required
          maxLength={255}
        />
      </label>

      <label>
        Corps du template
        <div className="row wrap gap-sm top-gap-sm">
          <button type="button" className={editorMode === "wysiwyg" ? "" : "ghost"} onClick={switchToWysiwyg}>
            Editeur
          </button>
          <button type="button" className={editorMode === "html" ? "" : "ghost"} onClick={switchToHtml}>
            HTML
          </button>
        </div>
        <p className="muted top-gap-sm">
          Pour une pagination PDF propre (couverture, entete, pied de page, sauts), utilisez les blocs predefinis, idealement en mode HTML.
        </p>
        {editorMode === "wysiwyg" ? (
          <div className="quote-template-editor-shell top-gap-sm">
            {renderToolbar()}
            {editorPopupOpen ? (
              <div className="quote-template-inline-placeholder muted">
                Edition en popup ouverte.
              </div>
            ) : (
              <div className="quote-template-editor-scroll">
                <EditorContent editor={editor} />
              </div>
            )}
          </div>
        ) : (
          <textarea
            value={body}
            onChange={(event) => setBody(event.target.value)}
            rows={14}
            required
            maxLength={20000}
            className="top-gap-sm"
          />
        )}
        <textarea name={bodyName} value={body} onChange={() => {}} hidden readOnly />
      </label>

      <div className="card">
        <h5>Picker variables</h5>
        <div className="row wrap gap-sm top-gap-sm">
          <select value={selectedVariable} onChange={(event) => setSelectedVariable(event.target.value)} disabled={!hasVariables}>
            {variables.map((item) => (
              <option key={item.key} value={item.key}>
                {item.label}
              </option>
            ))}
          </select>
          <button type="button" className="ghost" onClick={insertToken} disabled={!hasVariables}>Inserer dans le corps</button>
        </div>
        {!hasVariables ? <p className="muted top-gap-sm">Aucune variable disponible.</p> : null}
        {selected ? (
          <div className="top-gap-sm">
            <p className="muted"><code>{tokenForVariable(selected.key)}</code></p>
            <p className="muted">{selected.description}</p>
            <p className="muted">Exemple: {selected.example}</p>
          </div>
        ) : null}
      </div>

      <div className="card">
        <h5>Bibliotheque de blocs</h5>
        <div className="row wrap gap-sm top-gap-sm">
          <select value={selectedSnippet} onChange={(event) => setSelectedSnippet(event.target.value)}>
            {snippets.map((item) => (
              <option key={item.key} value={item.key}>
                {item.label}
              </option>
            ))}
          </select>
          <button type="button" className="ghost" onClick={insertSnippet}>Inserer le bloc</button>
        </div>
        {selectedSnippetDef ? (
          <p className="muted top-gap-sm"><code>{selectedSnippetDef.value}</code></p>
        ) : null}
      </div>

      {editorPopupOpen && editorMode === "wysiwyg" ? (
        <section className="modal-overlay" onClick={() => setEditorPopupOpen(false)}>
          <article
            className="modal-panel quote-template-editor-modal"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              className="modal-close-x"
              type="button"
              onClick={() => setEditorPopupOpen(false)}
              aria-label="Fermer"
            >
              ×
            </button>
            <h3 className="modal-title">Editeur de modele de devis</h3>
            <div className="quote-template-editor-shell">
              {renderToolbar(false)}
              <div className="quote-template-editor-scroll">
                <EditorContent editor={editor} />
              </div>
            </div>
          </article>
        </section>
      ) : null}
    </div>
  );
}
