import type { Editor } from "@tiptap/react";

export type EditorCursorContext = {
  tag: string;
  fontFamily: string;
  fontSize: string;
};

function normalizeFontFamilyLabel(value: string | undefined): string {
  if (!value) {
    return "Police par defaut";
  }
  const firstFamily = value.split(",")[0]?.trim();
  if (!firstFamily) {
    return "Police par defaut";
  }
  return firstFamily.replace(/^["']|["']$/g, "");
}

function normalizeFontSizeLabel(value: string | undefined): string {
  if (!value) {
    return "Taille par defaut";
  }
  const numericValue = Number.parseFloat(value);
  if (!Number.isFinite(numericValue)) {
    return value;
  }
  const formatted =
    Math.abs(numericValue - Math.round(numericValue)) < 0.01
      ? String(Math.round(numericValue))
      : numericValue.toFixed(1).replace(/\.0$/, "");
  return `${formatted} px`;
}

function resolveCursorElement(editor: Editor): HTMLElement | null {
  if (typeof window === "undefined") {
    return null;
  }
  const anchorPosition = editor.state.selection.$anchor.pos;
  const domAtCursor = editor.view.domAtPos(anchorPosition).node;
  let element =
    domAtCursor.nodeType === Node.ELEMENT_NODE
      ? (domAtCursor as HTMLElement)
      : domAtCursor.parentElement;
  const editorRoot = editor.view.dom as HTMLElement;
  while (element && element !== editorRoot) {
    if (["H1", "H2", "H3", "P", "LI"].includes(element.tagName)) {
      return element;
    }
    element = element.parentElement;
  }
  return editorRoot;
}

function resolveCursorTag(editor: Editor, cursorElement: HTMLElement | null): string {
  if (editor.isActive("heading", { level: 1 })) {
    return "<h1>";
  }
  if (editor.isActive("heading", { level: 2 })) {
    return "<h2>";
  }
  if (editor.isActive("heading", { level: 3 })) {
    return "<h3>";
  }
  if (editor.isActive("bulletList") || editor.isActive("orderedList")) {
    return "<li>";
  }
  if (cursorElement?.tagName) {
    return `<${cursorElement.tagName.toLowerCase()}>`;
  }
  return "<p>";
}

export function getEditorTextStyleState(
  editor: Editor | null | undefined,
): { fontFamily: string; fontSize: string } {
  if (!editor) {
    return { fontFamily: "", fontSize: "" };
  }
  const textStyleAttributes = editor.getAttributes("textStyle") as {
    fontFamily?: string;
    fontSize?: string;
  };
  return {
    fontFamily: typeof textStyleAttributes.fontFamily === "string" ? textStyleAttributes.fontFamily : "",
    fontSize: typeof textStyleAttributes.fontSize === "string" ? textStyleAttributes.fontSize : "",
  };
}

export function getEditorCursorContext(editor: Editor | null | undefined): EditorCursorContext {
  if (!editor) {
    return {
      tag: "<p>",
      fontFamily: "Police par defaut",
      fontSize: "Taille par defaut",
    };
  }

  const cursorElement = resolveCursorElement(editor);
  const computedStyle =
    cursorElement && typeof window !== "undefined" ? window.getComputedStyle(cursorElement) : null;

  return {
    tag: resolveCursorTag(editor, cursorElement),
    fontFamily: normalizeFontFamilyLabel(computedStyle?.fontFamily),
    fontSize: normalizeFontSizeLabel(computedStyle?.fontSize),
  };
}
