"use client";

import { useEffect, useMemo, useState } from "react";
import FontFamily from "@tiptap/extension-font-family";
import Link from "@tiptap/extension-link";
import TextStyle from "@tiptap/extension-text-style";
import TextAlign from "@tiptap/extension-text-align";
import Underline from "@tiptap/extension-underline";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";

type WysiwygFieldProps = {
  name: string;
  label: string;
  defaultValue: string;
  minHeightPx?: number;
  helpText?: string;
};

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

export default function WysiwygField({
  name,
  label,
  defaultValue,
  minHeightPx = 220,
  helpText,
}: WysiwygFieldProps): JSX.Element {
  const initialValue = normalizeInitialEditorValue(defaultValue);
  const [mode, setMode] = useState<"wysiwyg" | "html">("wysiwyg");
  const [value, setValue] = useState<string>(initialValue);
  const [fontFamily, setFontFamily] = useState<string>("");
  const [fontSize, setFontSize] = useState<string>("");
  const [editorPopupOpen, setEditorPopupOpen] = useState<boolean>(false);
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
      Link.configure({ openOnClick: false }),
      TextAlign.configure({ types: ["heading", "paragraph"] }),
    ],
    content: initialValue,
    editorProps: {
      attributes: {
        class: "wysiwyg-editor top-gap-sm",
        style: `min-height:${minHeightPx}px`,
      },
    },
    onUpdate: ({ editor: editorInstance }) => {
      setValue(editorInstance.getHTML());
    },
  });

  const toolbar = useMemo(
    () => [
      { label: "B", action: "bold" },
      { label: "I", action: "italic" },
      { label: "U", action: "underline" },
      { label: "H1", action: "heading1" },
      { label: "H2", action: "heading2" },
      { label: "H3", action: "heading3" },
      { label: "P", action: "paragraph" },
      { label: "Liste", action: "bulletList" },
      { label: "1.2.3", action: "orderedList" },
      { label: "Gauche", action: "alignLeft" },
      { label: "Centre", action: "alignCenter" },
      { label: "Droite", action: "alignRight" },
      { label: "↶", action: "undo" },
      { label: "↷", action: "redo" },
    ],
    [],
  );

  useEffect(() => {
    if (!editor || mode !== "wysiwyg") {
      return;
    }
    const next = looksLikeHtml(value) ? value : plainTextToHtml(value);
    if (editor.getHTML() !== next) {
      editor.commands.setContent(next, false);
    }
  }, [editor, mode, value]);

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
    if (!editor || mode !== "wysiwyg") {
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
    setValue(editor.getHTML());
  }

  function switchToWysiwyg(): void {
    if (mode === "wysiwyg") {
      return;
    }
    if (editor) {
      const next = normalizeInitialEditorValue(value);
      editor.commands.setContent(next, false);
      setValue(next);
    }
    setMode("wysiwyg");
  }

  function switchToHtml(): void {
    if (mode === "html") {
      return;
    }
    if (editor) {
      setValue(editor.getHTML());
    }
    setEditorPopupOpen(false);
    setMode("html");
  }

  function applyFontFamily(next: string): void {
    setFontFamily(next);
    if (!editor || mode !== "wysiwyg") {
      return;
    }
    const chain = editor.chain().focus();
    if (!next) {
      chain.unsetFontFamily().run();
    } else {
      chain.setFontFamily(next).run();
    }
    setValue(editor.getHTML());
  }

  function applyFontSize(next: string): void {
    setFontSize(next);
    if (!editor || mode !== "wysiwyg") {
      return;
    }
    const chain = editor.chain().focus();
    if (!next) {
      chain.unsetMark("textStyle").run();
    } else {
      chain.setMark("textStyle", { fontSize: next }).run();
    }
    setValue(editor.getHTML());
  }

  function insertLink(): void {
    if (!editor || mode !== "wysiwyg") {
      return;
    }
    const href = window.prompt("URL du lien (https://...)");
    if (!href) {
      return;
    }
    editor.chain().focus().extendMarkRange("link").setLink({ href }).run();
    setValue(editor.getHTML());
  }

  function renderToolbar(): JSX.Element {
    return (
      <div className="quote-template-toolbar" aria-label="Outils de mise en forme">
        <div className="toolbar-group">
          {toolbar.map((item) => (
            <button
              key={item.label}
              type="button"
              className="ghost small-btn"
              onClick={() => {
                applyCommand(item.action as Parameters<typeof applyCommand>[0]);
              }}
            >
              {item.label}
            </button>
          ))}
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
          <button type="button" className="ghost small-btn" onClick={insertLink}>
            Lien
          </button>
          <button
            type="button"
            className="ghost small-btn"
            onClick={() => setEditorPopupOpen(true)}
          >
            Ouvrir en popup
          </button>
        </div>
      </div>
    );
  }

  return (
    <label>
      {label}
      <div className="row wrap gap-sm top-gap-sm">
        <button
          type="button"
          className={mode === "wysiwyg" ? "" : "ghost"}
          onClick={switchToWysiwyg}
        >
          WYSIWYG
        </button>
        <button
          type="button"
          className={mode === "html" ? "" : "ghost"}
          onClick={switchToHtml}
        >
          HTML
        </button>
      </div>

      {mode === "wysiwyg" ? (
        <div className="top-gap-sm">
          <div className="quote-template-editor-shell">
            {renderToolbar()}
            {editorPopupOpen ? (
              <div className="quote-template-inline-placeholder muted">
                Edition en popup ouverte.
              </div>
            ) : (
              <EditorContent editor={editor} />
            )}
          </div>
        </div>
      ) : (
        <textarea
          className="top-gap-sm"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          rows={12}
        />
      )}

      <textarea name={name} value={value} onChange={() => {}} hidden readOnly />
      {helpText ? <small className="muted">{helpText}</small> : null}

      {editorPopupOpen && mode === "wysiwyg" ? (
        <section className="modal-overlay" onClick={() => setEditorPopupOpen(false)}>
          <article
            className="modal-panel wysiwyg-editor-modal"
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
            <h3 className="modal-title">Editeur WYSIWYG</h3>
            <div className="quote-template-editor-shell">
              {renderToolbar()}
              <EditorContent editor={editor} />
            </div>
          </article>
        </section>
      ) : null}
    </label>
  );
}
