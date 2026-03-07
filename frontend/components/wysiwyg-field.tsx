"use client";

import { useMemo, useRef, useState } from "react";

type WysiwygFieldProps = {
  name: string;
  label: string;
  defaultValue: string;
  minHeightPx?: number;
  helpText?: string;
};

function exec(command: string, value?: string): void {
  if (typeof document === "undefined") {
    return;
  }
  document.execCommand(command, false, value);
}

export default function WysiwygField({
  name,
  label,
  defaultValue,
  minHeightPx = 220,
  helpText,
}: WysiwygFieldProps): JSX.Element {
  const [mode, setMode] = useState<"wysiwyg" | "html">("wysiwyg");
  const [value, setValue] = useState<string>(defaultValue || "");
  const editorRef = useRef<HTMLDivElement | null>(null);

  const toolbar = useMemo(
    () => [
      { label: "B", action: () => exec("bold") },
      { label: "I", action: () => exec("italic") },
      { label: "U", action: () => exec("underline") },
      { label: "H2", action: () => exec("formatBlock", "h2") },
      { label: "P", action: () => exec("formatBlock", "p") },
      { label: "Liste", action: () => exec("insertUnorderedList") },
      { label: "1.2.3", action: () => exec("insertOrderedList") },
    ],
    [],
  );

  return (
    <label>
      {label}
      <div className="row wrap gap-sm top-gap-sm">
        <button
          type="button"
          className={mode === "wysiwyg" ? "" : "ghost"}
          onClick={() => setMode("wysiwyg")}
        >
          WYSIWYG
        </button>
        <button
          type="button"
          className={mode === "html" ? "" : "ghost"}
          onClick={() => setMode("html")}
        >
          HTML
        </button>
      </div>

      {mode === "wysiwyg" ? (
        <div className="top-gap-sm">
          <div className="row wrap gap-sm">
            {toolbar.map((item) => (
              <button
                key={item.label}
                type="button"
                className="ghost"
                onClick={() => {
                  item.action();
                  setValue(editorRef.current?.innerHTML ?? "");
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div
            ref={editorRef}
            className="wysiwyg-editor top-gap-sm"
            contentEditable
            suppressContentEditableWarning
            onInput={(event) => setValue((event.currentTarget as HTMLDivElement).innerHTML)}
            dangerouslySetInnerHTML={{ __html: value }}
            style={{ minHeight: `${minHeightPx}px` }}
          />
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
    </label>
  );
}
