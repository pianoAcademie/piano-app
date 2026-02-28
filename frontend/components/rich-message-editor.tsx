"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type MessageBodyFormat = "TEXT" | "HTML";

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

export default function RichMessageEditor({
  name,
  formatName = "body_format",
  defaultValue,
  defaultFormat = "TEXT",
  placeholder,
  rows = 12,
  maxLength,
}: RichMessageEditorProps) {
  const initialFormat = useMemo(() => normalizeFormat(defaultFormat), [defaultFormat]);
  const initialValue = defaultValue ?? "";

  const [format, setFormat] = useState<MessageBodyFormat>(initialFormat);
  const [value, setValue] = useState(initialValue);
  const [sourceMode, setSourceMode] = useState(false);
  const editorRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (format !== "HTML" || sourceMode || !editorRef.current) {
      return;
    }
    if (editorRef.current.innerHTML !== value) {
      editorRef.current.innerHTML = value;
    }
  }, [format, sourceMode, value]);

  const setFormatWithConversion = (next: MessageBodyFormat) => {
    if (next === format) {
      return;
    }
    if (next === "HTML") {
      setValue(plainTextToHtml(value));
      setSourceMode(false);
      setFormat("HTML");
      return;
    }
    setValue(htmlToPlainText(value));
    setSourceMode(false);
    setFormat("TEXT");
  };

  const applyCommand = (command: string) => {
    if (format !== "HTML" || sourceMode || !editorRef.current) {
      return;
    }
    editorRef.current.focus();
    document.execCommand(command, false);
    setValue(editorRef.current.innerHTML);
  };

  const insertLink = () => {
    if (format !== "HTML" || sourceMode || !editorRef.current) {
      return;
    }
    const href = window.prompt("URL du lien (https://...)");
    if (!href) {
      return;
    }
    editorRef.current.focus();
    document.execCommand("createLink", false, href);
    setValue(editorRef.current.innerHTML);
  };

  return (
    <div className="rich-message-editor">
      <div className="rich-message-editor-top">
        <div className="segmented-inline" role="tablist" aria-label="Format du message">
          <button
            type="button"
            className={format === "TEXT" ? "active" : ""}
            onClick={() => setFormatWithConversion("TEXT")}
          >
            Texte
          </button>
          <button
            type="button"
            className={format === "HTML" ? "active" : ""}
            onClick={() => setFormatWithConversion("HTML")}
          >
            HTML
          </button>
        </div>
        {format === "HTML" ? (
          <button type="button" className="ghost compact" onClick={() => setSourceMode((current) => !current)}>
            {sourceMode ? "Apercu" : "Code HTML"}
          </button>
        ) : null}
      </div>

      {format === "TEXT" ? (
        <textarea
          className="rich-message-textarea"
          rows={rows}
          name={`${name}__visible_text`}
          value={value}
          maxLength={maxLength}
          placeholder={placeholder}
          onChange={(event) => setValue(event.target.value)}
        />
      ) : sourceMode ? (
        <textarea
          className="rich-message-textarea rich-message-source"
          rows={rows}
          name={`${name}__visible_html`}
          value={value}
          maxLength={maxLength}
          placeholder={placeholder}
          onChange={(event) => setValue(event.target.value)}
        />
      ) : (
        <div className="rich-message-shell">
          <div className="rich-message-toolbar" aria-label="Outils de mise en forme">
            <button type="button" onClick={() => applyCommand("bold")}>B</button>
            <button type="button" onClick={() => applyCommand("italic")}>I</button>
            <button type="button" onClick={() => applyCommand("underline")}>U</button>
            <button type="button" onClick={() => applyCommand("insertUnorderedList")}>UL</button>
            <button type="button" onClick={() => applyCommand("insertOrderedList")}>1.</button>
            <button type="button" onClick={insertLink}>Lien</button>
            <button type="button" onClick={() => applyCommand("undo")}>↶</button>
            <button type="button" onClick={() => applyCommand("redo")}>↷</button>
          </div>
          <div
            ref={editorRef}
            className="rich-message-surface"
            contentEditable
            suppressContentEditableWarning
            onInput={(event) => {
              const next = (event.currentTarget as HTMLDivElement).innerHTML;
              setValue(maxLength && next.length > maxLength ? next.slice(0, maxLength) : next);
            }}
          />
        </div>
      )}

      <input type="hidden" name={name} value={value} />
      <input type="hidden" name={formatName} value={format} />
    </div>
  );
}
