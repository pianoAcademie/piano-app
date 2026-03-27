"use client";

import { useState } from "react";

type ImportAction = "CREATE" | "UPDATE";
type ClientKind = "ADULT" | "CHILD" | string;

type PreviewSampleRow = {
  student_external_id: string;
  family_external_id: string | null;
  display_name: string;
  client_kind: ClientKind;
  action: ImportAction;
  parent_contacts_count: number;
  warning_messages: string[];
};

type PreviewResponse = {
  source_system: string;
  file_name: string | null;
  rows_total: number;
  students_detected: number;
  adult_students_detected: number;
  child_students_detected: number;
  parent_contacts_detected: number;
  families_detected: number;
  would_create_clients: number;
  would_update_clients: number;
  would_create_family_links: number;
  warnings: string[];
  sample_rows: PreviewSampleRow[];
};

type ExecuteResponse = {
  source_system: string;
  file_name: string | null;
  rows_total: number;
  processed_students: number;
  parents_created: number;
  parents_updated: number;
  students_created: number;
  students_updated: number;
  family_links_created: number;
  family_links_updated: number;
  warnings: string[];
  summary: string;
};

function clientKindLabel(value: ClientKind): string {
  return value === "CHILD" ? "Enfant" : "Adulte";
}

function actionLabel(value: ImportAction): string {
  return value === "CREATE" ? "Creation" : "Mise a jour";
}

async function postCsv<T>(path: string, file: File): Promise<T> {
  const formData = new FormData();
  formData.append("csv_file", file);

  const response = await fetch(path, {
    method: "POST",
    body: formData,
  });
  const payload = (await response.json().catch(() => null)) as { detail?: string } | T | null;
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload && typeof payload.detail === "string"
        ? payload.detail
        : `Import impossible (${response.status})`;
    throw new Error(detail);
  }
  return payload as T;
}

export default function MyMusicStaffImporter(): JSX.Element {
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [result, setResult] = useState<ExecuteResponse | null>(null);
  const [error, setError] = useState("");
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isImporting, setIsImporting] = useState(false);

  const handlePreview = async (): Promise<void> => {
    if (!csvFile) {
      setError("Choisissez d abord le CSV exporte depuis MyMusicStaff.");
      return;
    }

    setIsPreviewing(true);
    setError("");
    setResult(null);
    try {
      const payload = await postCsv<PreviewResponse>("/api/admin/clients/imports/mymusicstaff/preview", csvFile);
      setPreview(payload);
    } catch (err) {
      setPreview(null);
      setError(err instanceof Error ? err.message : "Analyse impossible.");
    } finally {
      setIsPreviewing(false);
    }
  };

  const handleImport = async (): Promise<void> => {
    if (!csvFile) {
      setError("Choisissez d abord le CSV exporte depuis MyMusicStaff.");
      return;
    }

    setIsImporting(true);
    setError("");
    try {
      const payload = await postCsv<ExecuteResponse>("/api/admin/clients/imports/mymusicstaff/execute", csvFile);
      setResult(payload);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Import impossible.");
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <div className="admin-page-grid">
      <section className="card">
        <div className="row spread">
          <div>
            <h2>Importer depuis MyMusicStaff</h2>
            <p className="muted">
              Charge un export CSV MyMusicStaff pour creer ou mettre a jour eleves, parents et liens de famille.
            </p>
          </div>
        </div>
        <div className="flash-warn">
          Les profils importes sont crees ou maintenus en statut <strong>Inactif</strong>. Tu peux relancer le meme CSV
          ensuite: l import est idempotent et preserve les relations parents / enfants.
        </div>
        <div className="grid cols-2">
          <label>
            Fichier CSV MyMusicStaff
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => {
                setCsvFile(event.target.files?.[0] ?? null);
                setPreview(null);
                setResult(null);
                setError("");
              }}
            />
          </label>
          <section className="item">
            <p>
              <strong>Fichier selectionne:</strong> {csvFile?.name ?? "Aucun fichier"}
            </p>
            <p className="muted">Modele attendu: export brut MyMusicStaff en CSV separe par point-virgule.</p>
          </section>
        </div>
        <div className="row wrap gap-sm">
          <button type="button" onClick={handlePreview} disabled={!csvFile || isPreviewing || isImporting}>
            {isPreviewing ? "Analyse en cours..." : "Analyser le CSV"}
          </button>
          <button
            type="button"
            className="ghost"
            onClick={handleImport}
            disabled={!csvFile || !preview || isPreviewing || isImporting}
          >
            {isImporting ? "Import en cours..." : "Importer les profils"}
          </button>
        </div>
      </section>

      {error ? <section className="flash-err">{error}</section> : null}
      {result ? <section className="flash-ok">{result.summary}</section> : null}

      {preview ? (
        <>
          <section className="card">
            <h2>Previsualisation</h2>
            <div className="grid cols-4">
              <section className="item">
                <strong>{preview.rows_total}</strong>
                <p className="muted">Lignes CSV</p>
              </section>
              <section className="item">
                <strong>{preview.students_detected}</strong>
                <p className="muted">Eleves detectes</p>
              </section>
              <section className="item">
                <strong>{preview.parent_contacts_detected}</strong>
                <p className="muted">Parents detectes</p>
              </section>
              <section className="item">
                <strong>{preview.families_detected}</strong>
                <p className="muted">Familles detectees</p>
              </section>
              <section className="item">
                <strong>{preview.would_create_clients}</strong>
                <p className="muted">Profils a creer</p>
              </section>
              <section className="item">
                <strong>{preview.would_update_clients}</strong>
                <p className="muted">Profils a mettre a jour</p>
              </section>
              <section className="item">
                <strong>{preview.would_create_family_links}</strong>
                <p className="muted">Liens famille a creer</p>
              </section>
              <section className="item">
                <strong>{preview.child_students_detected}</strong>
                <p className="muted">Eleves enfants</p>
              </section>
            </div>
          </section>

          {preview.warnings.length ? (
            <section className="card">
              <h2>Warnings</h2>
              <ul className="list">
                {preview.warnings.slice(0, 20).map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className="card table-wrap">
            <div className="row spread">
              <h2>Echantillon avant import</h2>
              <span className="muted">20 premieres lignes utiles</span>
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Eleve</th>
                  <th>Type</th>
                  <th>Action</th>
                  <th>Famille</th>
                  <th>Parents</th>
                  <th>Warnings</th>
                </tr>
              </thead>
              <tbody>
                {preview.sample_rows.map((row) => (
                  <tr key={row.student_external_id}>
                    <td>
                      <strong>{row.display_name}</strong>
                      <br />
                      <small className="muted">{row.student_external_id}</small>
                    </td>
                    <td>{clientKindLabel(row.client_kind)}</td>
                    <td>
                      <span className="badge">{actionLabel(row.action)}</span>
                    </td>
                    <td>{row.family_external_id || "-"}</td>
                    <td>{row.parent_contacts_count}</td>
                    <td>
                      {row.warning_messages.length ? (
                        <ul className="list">
                          {row.warning_messages.map((warning) => (
                            <li key={`${row.student_external_id}-${warning}`}>{warning}</li>
                          ))}
                        </ul>
                      ) : (
                        <span className="muted">Aucun</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      ) : null}

      {result ? (
        <section className="card">
          <h2>Import termine</h2>
          <div className="grid cols-4">
            <section className="item">
              <strong>{result.students_created}</strong>
              <p className="muted">Eleves crees</p>
            </section>
            <section className="item">
              <strong>{result.students_updated}</strong>
              <p className="muted">Eleves mis a jour</p>
            </section>
            <section className="item">
              <strong>{result.parents_created}</strong>
              <p className="muted">Parents crees</p>
            </section>
            <section className="item">
              <strong>{result.parents_updated}</strong>
              <p className="muted">Parents mis a jour</p>
            </section>
            <section className="item">
              <strong>{result.family_links_created}</strong>
              <p className="muted">Liens famille crees</p>
            </section>
            <section className="item">
              <strong>{result.family_links_updated}</strong>
              <p className="muted">Liens famille mis a jour</p>
            </section>
            <section className="item">
              <strong>{result.processed_students}</strong>
              <p className="muted">Eleves traites</p>
            </section>
            <section className="item">
              <strong>{result.rows_total}</strong>
              <p className="muted">Lignes source</p>
            </section>
          </div>
          {result.warnings.length ? (
            <div className="flash-warn">
              <strong>Warnings import:</strong>
              <ul className="list">
                {result.warnings.slice(0, 20).map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
