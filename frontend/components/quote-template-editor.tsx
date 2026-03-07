"use client";

import { useMemo, useRef, useState } from "react";

type QuoteTemplateVariable = {
  key: string;
  label: string;
  description: string;
  example: string;
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

export default function QuoteTemplateEditor({
  subjectName,
  bodyName,
  defaultSubject,
  defaultBody,
  variables,
}: QuoteTemplateEditorProps): JSX.Element {
  const hasVariables = variables.length > 0;
  const [subject, setSubject] = useState<string>(defaultSubject);
  const [body, setBody] = useState<string>(defaultBody);
  const [editorMode, setEditorMode] = useState<"wysiwyg" | "html">("wysiwyg");
  const [selectedVariable, setSelectedVariable] = useState<string>(variables[0]?.key || "quote_number");
  const editorRef = useRef<HTMLDivElement | null>(null);

  const selected = useMemo(
    () => variables.find((item) => item.key === selectedVariable) ?? variables[0] ?? null,
    [selectedVariable, variables],
  );

  function insertToken(): void {
    if (!selected) {
      return;
    }
    const token = tokenForVariable(selected.key);
    if (editorMode === "wysiwyg" && editorRef.current) {
      editorRef.current.focus();
      document.execCommand("insertText", false, token);
      setBody(editorRef.current.innerHTML);
      return;
    }
    setBody((prev) => `${prev}${prev.endsWith("\n") || !prev ? "" : "\n"}${token}`);
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
          <button type="button" className={editorMode === "wysiwyg" ? "" : "ghost"} onClick={() => setEditorMode("wysiwyg")}>
            WYSIWYG
          </button>
          <button type="button" className={editorMode === "html" ? "" : "ghost"} onClick={() => setEditorMode("html")}>
            HTML
          </button>
        </div>
        {editorMode === "wysiwyg" ? (
          <div
            ref={editorRef}
            className="wysiwyg-editor top-gap-sm"
            contentEditable
            suppressContentEditableWarning
            onInput={(event) => setBody((event.currentTarget as HTMLDivElement).innerHTML)}
            dangerouslySetInnerHTML={{ __html: body }}
          />
        ) : (
          <textarea
            value={body}
            onChange={(event) => setBody(event.target.value)}
            rows={10}
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
    </div>
  );
}
