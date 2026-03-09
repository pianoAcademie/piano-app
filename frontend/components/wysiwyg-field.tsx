"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "@tiptap/extension-link";
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

export default function WysiwygField({
  name,
  label,
  defaultValue,
  minHeightPx = 220,
  helpText,
}: WysiwygFieldProps): JSX.Element {
  const initialValue = looksLikeHtml(defaultValue) ? defaultValue : plainTextToHtml(defaultValue || "");
  const [mode, setMode] = useState<"wysiwyg" | "html">("wysiwyg");
  const [value, setValue] = useState<string>(initialValue);
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [2, 3] },
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
      { label: "H2", action: "heading2" },
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
      | "heading2"
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
      case "heading2":
        chain.toggleHeading({ level: 2 }).run();
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
      const next = looksLikeHtml(value) ? value : plainTextToHtml(value);
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
    setMode("html");
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
          <div className="row wrap gap-sm">
            {toolbar.map((item) => (
              <button
                key={item.label}
                type="button"
                className="ghost"
                onClick={() => {
                  applyCommand(item.action as Parameters<typeof applyCommand>[0]);
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
          <EditorContent editor={editor} />
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
