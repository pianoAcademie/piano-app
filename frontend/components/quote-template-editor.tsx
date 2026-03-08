"use client";

import { useMemo, useRef, useState } from "react";

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
        key: "block_services",
        label: "Bloc activites",
        value: "<h2>Activites</h2>{services_table_html}",
      },
      {
        key: "block_material",
        label: "Bloc materiel",
        value: "<h2>Materiel</h2>{products_table_html}",
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
        value:
          "<table width='100%' cellpadding='6' cellspacing='0' border='1'>"
          + "<tr><td><strong>Total HT</strong></td><td align='right'>{total_ht} {currency}</td></tr>"
          + "<tr><td><strong>TVA ({vat_rate} %)</strong></td><td align='right'>{vat_amount} {currency}</td></tr>"
          + "<tr><td><strong>Total TTC</strong></td><td align='right'><strong>{total_ttc} {currency}</strong></td></tr>"
          + "</table>",
      },
    ],
    [],
  );
  const hasVariables = variables.length > 0;
  const [subject, setSubject] = useState<string>(defaultSubject);
  const [body, setBody] = useState<string>(defaultBody);
  const [editorMode, setEditorMode] = useState<"wysiwyg" | "html">("wysiwyg");
  const [selectedVariable, setSelectedVariable] = useState<string>(variables[0]?.key || "quote_number");
  const [selectedSnippet, setSelectedSnippet] = useState<string>(snippets[0]?.key || "page_break");
  const editorRef = useRef<HTMLDivElement | null>(null);

  const selected = useMemo(
    () => variables.find((item) => item.key === selectedVariable) ?? variables[0] ?? null,
    [selectedVariable, variables],
  );
  const selectedSnippetDef = useMemo(
    () => snippets.find((item) => item.key === selectedSnippet) ?? snippets[0] ?? null,
    [selectedSnippet, snippets],
  );

  function syncBodyFromEditor(): void {
    setBody(editorRef.current?.innerHTML ?? "");
  }

  function applyCommand(command: string, commandValue?: string): void {
    if (!editorRef.current || editorMode !== "wysiwyg") {
      return;
    }
    editorRef.current.focus();
    document.execCommand("styleWithCSS", false);
    document.execCommand(command, false, commandValue);
    syncBodyFromEditor();
  }

  function switchToWysiwyg(): void {
    if (editorMode === "wysiwyg") {
      return;
    }
    setEditorMode("wysiwyg");
    if (!looksLikeHtml(body)) {
      setBody(plainTextToHtml(body));
    }
  }

  function switchToHtml(): void {
    if (editorMode === "html") {
      return;
    }
    if (editorRef.current) {
      setBody(editorRef.current.innerHTML);
    }
    setEditorMode("html");
  }

  function insertHtmlAtCursor(html: string): void {
    if (!editorRef.current || editorMode !== "wysiwyg") {
      return;
    }
    editorRef.current.focus();
    document.execCommand("insertHTML", false, html);
    syncBodyFromEditor();
  }

  function insertToken(): void {
    if (!selected) {
      return;
    }
    const token = tokenForVariable(selected.key);
    if (editorMode === "wysiwyg" && editorRef.current) {
      editorRef.current.focus();
      document.execCommand("insertText", false, token);
      syncBodyFromEditor();
      return;
    }
    setBody((prev) => `${prev}${prev.endsWith("\n") || !prev ? "" : "\n"}${token}`);
  }

  function insertSnippet(): void {
    if (!selectedSnippetDef) {
      return;
    }
    const snippet = selectedSnippetDef.value;
    if (editorMode === "wysiwyg" && editorRef.current) {
      insertHtmlAtCursor(snippet);
      return;
    }
    setBody((prev) => `${prev}${prev.endsWith("\n") || !prev ? "" : "\n"}${snippet}`);
  }

  function insertLink(): void {
    if (!editorRef.current || editorMode !== "wysiwyg") {
      return;
    }
    const href = window.prompt("URL du lien (https://...)");
    if (!href) {
      return;
    }
    applyCommand("createLink", href);
  }

  function insertImageUrl(): void {
    if (!editorRef.current || editorMode !== "wysiwyg") {
      return;
    }
    const src = window.prompt("URL de l image (https://...)");
    if (!src) {
      return;
    }
    applyCommand("insertImage", src);
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
            <div className="quote-template-toolbar" aria-label="Outils de mise en forme">
              <div className="toolbar-group">
                <button type="button" className="ghost small-btn" onClick={() => applyCommand("bold")}>B</button>
                <button type="button" className="ghost small-btn" onClick={() => applyCommand("italic")}>I</button>
                <button type="button" className="ghost small-btn" onClick={() => applyCommand("underline")}>U</button>
              </div>
              <div className="toolbar-group">
                <button type="button" className="ghost small-btn" onClick={() => applyCommand("formatBlock", "h1")}>H1</button>
                <button type="button" className="ghost small-btn" onClick={() => applyCommand("formatBlock", "h2")}>H2</button>
                <button type="button" className="ghost small-btn" onClick={() => applyCommand("formatBlock", "h3")}>H3</button>
                <button type="button" className="ghost small-btn" onClick={() => applyCommand("formatBlock", "p")}>P</button>
              </div>
              <div className="toolbar-group">
                <button type="button" className="ghost small-btn" onClick={() => applyCommand("insertUnorderedList")}>• Liste</button>
                <button type="button" className="ghost small-btn" onClick={() => applyCommand("insertOrderedList")}>1. Liste</button>
              </div>
              <div className="toolbar-group">
                <button type="button" className="ghost small-btn" onClick={() => applyCommand("justifyLeft")}>Gauche</button>
                <button type="button" className="ghost small-btn" onClick={() => applyCommand("justifyCenter")}>Centre</button>
                <button type="button" className="ghost small-btn" onClick={() => applyCommand("justifyRight")}>Droite</button>
              </div>
              <div className="toolbar-group">
                <button type="button" className="ghost small-btn" onClick={insertLink}>Lien</button>
                <button type="button" className="ghost small-btn" onClick={insertImageUrl}>Image URL</button>
              </div>
              <div className="toolbar-group">
                <button type="button" className="ghost small-btn" onClick={() => applyCommand("undo")}>↶</button>
                <button type="button" className="ghost small-btn" onClick={() => applyCommand("redo")}>↷</button>
              </div>
            </div>
            <div
              ref={editorRef}
              className="quote-template-editor-surface"
              contentEditable
              suppressContentEditableWarning
              onInput={(event) => setBody((event.currentTarget as HTMLDivElement).innerHTML)}
              dangerouslySetInnerHTML={{ __html: body }}
            />
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
    </div>
  );
}
