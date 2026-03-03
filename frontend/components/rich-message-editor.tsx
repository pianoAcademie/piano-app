"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type MessageBodyFormat = "TEXT" | "HTML";
type EditorMode = "TEXT" | "WYSIWYG" | "HTML_SOURCE";

type RichMessageEditorProps = {
  name: string;
  formatName?: string;
  defaultValue?: string;
  defaultFormat?: MessageBodyFormat | string;
  placeholder?: string;
  rows?: number;
  maxLength?: number;
};

function normalizeFormat(value: string | undefined): MessageBodyFormat {
  return String(value || "TEXT").trim().toUpperCase() === "HTML" ? "HTML" : "TEXT";
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

function looksLikeHtml(value: string): boolean {
  return /<\s*[a-z!/][^>]*>/i.test(value);
}

function htmlToPlainText(value: string): string {
  if (!value) {
    return "";
  }
  const withBreaks = value
    .replace(/<\s*br\s*\/?>/gi, "\n")
    .replace(/<\s*\/\s*p\s*>/gi, "\n")
    .replace(/<\s*\/\s*div\s*>/gi, "\n")
    .replace(/<\s*li\b[^>]*>/gi, "- ");
  const withoutTags = withBreaks.replace(/<[^>]+>/g, "");
  if (typeof window === "undefined") {
    return withoutTags
      .replace(/&nbsp;/g, " ")
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&#39;/g, "'")
      .replace(/&quot;/g, '"')
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }
  const decoder = window.document.createElement("textarea");
  decoder.innerHTML = withoutTags;
  return decoder.value.replace(/\n{3,}/g, "\n\n").trim();
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("File read failed"));
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.readAsDataURL(file);
  });
}

export default function RichMessageEditor({
  name,
  formatName = "body_format",
  defaultValue,
  defaultFormat = "HTML",
  placeholder,
  rows = 12,
  maxLength,
}: RichMessageEditorProps) {
  const initialFormat = useMemo(() => normalizeFormat(defaultFormat), [defaultFormat]);
  const initialValue = defaultValue ?? "";
  const initialEditorValue = useMemo(() => {
    if (initialFormat === "HTML") {
      return initialValue;
    }
    return looksLikeHtml(initialValue) ? initialValue : plainTextToHtml(initialValue);
  }, [initialFormat, initialValue]);

  const [mode, setMode] = useState<EditorMode>("WYSIWYG");
  const [value, setValue] = useState(initialEditorValue);
  const editorRef = useRef<HTMLDivElement | null>(null);
  const imageFileInputRef = useRef<HTMLInputElement | null>(null);
  const attachmentFileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (mode !== "WYSIWYG" || !editorRef.current) {
      return;
    }
    if (editorRef.current.innerHTML !== value) {
      editorRef.current.innerHTML = value;
    }
  }, [mode, value]);

  const updateValue = (next: string) => {
    if (maxLength && next.length > maxLength) {
      setValue(next.slice(0, maxLength));
      return;
    }
    setValue(next);
  };

  const switchToTextMode = () => {
    if (mode === "TEXT") {
      return;
    }
    updateValue(htmlToPlainText(value));
    setMode("TEXT");
  };

  const switchToWysiwygMode = () => {
    if (mode === "WYSIWYG") {
      return;
    }
    if (mode === "TEXT") {
      updateValue(looksLikeHtml(value) ? value : plainTextToHtml(value));
    }
    setMode("WYSIWYG");
  };

  const switchToHtmlSourceMode = () => {
    if (mode === "HTML_SOURCE") {
      return;
    }
    if (mode === "TEXT") {
      updateValue(looksLikeHtml(value) ? value : plainTextToHtml(value));
    } else if (editorRef.current) {
      updateValue(editorRef.current.innerHTML);
    }
    setMode("HTML_SOURCE");
  };

  const applyCommand = (command: string, commandValue?: string) => {
    if (mode !== "WYSIWYG" || !editorRef.current) {
      return;
    }
    editorRef.current.focus();
    document.execCommand("styleWithCSS", false);
    document.execCommand(command, false, commandValue);
    updateValue(editorRef.current.innerHTML);
  };

  const insertHtmlAtCursor = (html: string) => {
    if (mode !== "WYSIWYG" || !editorRef.current) {
      return;
    }
    editorRef.current.focus();
    document.execCommand("insertHTML", false, html);
    updateValue(editorRef.current.innerHTML);
  };

  const insertLink = () => {
    if (mode !== "WYSIWYG" || !editorRef.current) {
      return;
    }
    const href = window.prompt("URL du lien (https://...)");
    if (!href) {
      return;
    }
    editorRef.current.focus();
    document.execCommand("createLink", false, href);
    updateValue(editorRef.current.innerHTML);
  };

  const insertImageUrl = () => {
    if (mode !== "WYSIWYG") {
      return;
    }
    const src = window.prompt("URL de l image (https://...)");
    if (!src) {
      return;
    }
    applyCommand("insertImage", src);
  };

  const insertAttachmentFromFile = async (file: File | null) => {
    if (!file || mode !== "WYSIWYG") {
      return;
    }
    const dataUrl = await readFileAsDataUrl(file);
    const safeName = escapeHtml(file.name || "fichier");
    insertHtmlAtCursor(`<a href="${dataUrl}" download="${safeName}" target="_blank" rel="noreferrer">📎 ${safeName}</a>`);
  };

  const insertImageFromFile = async (file: File | null) => {
    if (!file || mode !== "WYSIWYG") {
      return;
    }
    const dataUrl = await readFileAsDataUrl(file);
    const safeName = escapeHtml(file.name || "image");
    insertHtmlAtCursor(`<img src="${dataUrl}" alt="${safeName}" style="max-width:100%;height:auto;" />`);
  };

  const currentFormat: MessageBodyFormat = mode === "TEXT" ? "TEXT" : "HTML";

  const showWysiwygToolbar = mode === "WYSIWYG";
  const showTextArea = mode === "TEXT";
  const showHtmlSource = mode === "HTML_SOURCE";

  const switchToSize = (size: string) => {
    if (!size) {
      return;
    }
    applyCommand("fontSize", size);
  };

  const switchToFont = (font: string) => {
    if (!font) {
      return;
    }
    applyCommand("fontName", font);
  };

  const applyForeColor = (color: string) => {
    if (!color) {
      return;
    }
    applyCommand("foreColor", color);
  };

  const applyHighlightColor = (color: string) => {
    if (!color) {
      return;
    }
    applyCommand("hiliteColor", color);
    applyCommand("backColor", color);
  };

  return (
    <div className="rich-message-editor">
      <div className="rich-message-editor-top">
        <div className="segmented-inline" role="tablist" aria-label="Mode de l editeur">
          <button
            type="button"
            className={mode === "WYSIWYG" ? "active" : ""}
            onClick={switchToWysiwygMode}
          >
            Editeur
          </button>
          <button
            type="button"
            className={mode === "HTML_SOURCE" ? "active" : ""}
            onClick={switchToHtmlSourceMode}
          >
            HTML
          </button>
          <button
            type="button"
            className={mode === "TEXT" ? "active" : ""}
            onClick={switchToTextMode}
          >
            Texte
          </button>
        </div>
      </div>

      {showTextArea ? (
        <textarea
          className="rich-message-textarea"
          rows={rows}
          name={`${name}__visible_text`}
          value={value}
          maxLength={maxLength}
          placeholder={placeholder}
          onChange={(event) => updateValue(event.target.value)}
        />
      ) : showHtmlSource ? (
        <textarea
          className="rich-message-textarea rich-message-source"
          rows={rows}
          name={`${name}__visible_html`}
          value={value}
          maxLength={maxLength}
          placeholder={placeholder}
          onChange={(event) => updateValue(event.target.value)}
        />
      ) : (
        <div className="rich-message-shell">
          {showWysiwygToolbar ? (
            <div className="rich-message-toolbar" aria-label="Outils de mise en forme">
              <div className="toolbar-group">
                <button type="button" onClick={() => applyCommand("bold")}>B</button>
                <button type="button" onClick={() => applyCommand("italic")}>I</button>
                <button type="button" onClick={() => applyCommand("underline")}>U</button>
              </div>

              <div className="toolbar-group">
                <button type="button" onClick={() => applyCommand("insertUnorderedList")}>• Liste</button>
                <button type="button" onClick={() => applyCommand("insertOrderedList")}>1. Liste</button>
              </div>

              <div className="toolbar-group">
                <select defaultValue="" onChange={(event) => switchToFont(event.target.value)}>
                  <option value="" disabled>Police</option>
                  <option value="Arial">Arial</option>
                  <option value="'Avenir Next'">Avenir Next</option>
                  <option value="'Times New Roman'">Times New Roman</option>
                  <option value="Georgia">Georgia</option>
                  <option value="'Courier New'">Courier New</option>
                </select>
                <select defaultValue="" onChange={(event) => switchToSize(event.target.value)}>
                  <option value="" disabled>Taille</option>
                  <option value="1">10</option>
                  <option value="2">12</option>
                  <option value="3">14</option>
                  <option value="4">16</option>
                  <option value="5">18</option>
                  <option value="6">24</option>
                  <option value="7">32</option>
                </select>
              </div>

              <div className="toolbar-group">
                <label className="toolbar-color-field">
                  Texte
                  <input type="color" defaultValue="#111111" onChange={(event) => applyForeColor(event.target.value)} />
                </label>
                <label className="toolbar-color-field">
                  Surligner
                  <input type="color" defaultValue="#fff176" onChange={(event) => applyHighlightColor(event.target.value)} />
                </label>
              </div>

              <div className="toolbar-group">
                <button type="button" onClick={insertLink}>Lien</button>
                <button type="button" onClick={insertImageUrl}>Image URL</button>
                <button type="button" onClick={() => imageFileInputRef.current?.click()}>Image fichier</button>
                <button type="button" onClick={() => attachmentFileInputRef.current?.click()}>Ajouter fichier</button>
              </div>

              <div className="toolbar-group">
                <button type="button" onClick={() => applyCommand("undo")}>↶</button>
                <button type="button" onClick={() => applyCommand("redo")}>↷</button>
              </div>
            </div>
          ) : null}
          <div
            ref={editorRef}
            className="rich-message-surface"
            contentEditable
            suppressContentEditableWarning
            onInput={(event) => {
              const next = (event.currentTarget as HTMLDivElement).innerHTML;
              updateValue(next);
            }}
          />
        </div>
      )}

      <input
        ref={imageFileInputRef}
        type="file"
        accept="image/*"
        className="hidden-file-input"
        onChange={async (event) => {
          const file = event.currentTarget.files?.[0] ?? null;
          await insertImageFromFile(file);
          event.currentTarget.value = "";
        }}
      />
      <input
        ref={attachmentFileInputRef}
        type="file"
        className="hidden-file-input"
        onChange={async (event) => {
          const file = event.currentTarget.files?.[0] ?? null;
          await insertAttachmentFromFile(file);
          event.currentTarget.value = "";
        }}
      />

      <input type="hidden" name={name} value={value} />
      <input type="hidden" name={formatName} value={currentFormat} />
    </div>
  );
}
