"use client";

import { useRef, useState } from "react";
import { learningAction } from "../../lib/learning-actions";
import type { LearningCommand, LearningSnapshot, PieceStatus } from "../../lib/learning-progress";
import type { RepertoirePartitionOut } from "../../lib/types";
import styles from "./learning-card.module.css";

type Props = { studentId: string; studentName: string; sessionId: string; catalog: RepertoirePartitionOut[]; initial: LearningSnapshot };
type Mode = "CORRECT" | "HISTORY" | "NEXT_BOOK" | "FINISH" | null;
const labels: Record<PieceStatus, string> = { UNKNOWN: "À vérifier", REVIEW: "À reprendre", COMPLETED: "Terminé" };

export default function LearningCard({ studentId, studentName, sessionId, catalog, initial }: Props) {
  const [snapshot, setSnapshot] = useState(initial);
  const [mode, setMode] = useState<Mode>(null);
  const [productId, setProductId] = useState(initial.state.product_id ?? "");
  const [pieceId, setPieceId] = useState("");
  const [statuses, setStatuses] = useState<Record<string, PieceStatus>>({});
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const current = catalog.find((p) => p.product_id === snapshot.state.product_id);
  const book = snapshot.state.books[snapshot.state.product_id ?? ""];
  const piece = current?.pieces.find((p) => p.id === book?.current_piece_id);
  const completed = current?.pieces.filter((p) => book?.pieces[p.id]?.status === "COMPLETED").length ?? 0;
  const editor = catalog.find((p) => p.product_id === productId);
  const allDone = Boolean(current?.pieces.length && completed === current.pieces.length);
  const remaining = current?.pieces.filter((p) => p.id !== book?.current_piece_id && book?.pieces[p.id]?.status !== "COMPLETED") ?? [];

  function selectBook(id: string) {
    setProductId(id);
    const prior = snapshot.state.books[id];
    setNote(prior?.note ?? "");
    setPieceId(prior?.current_piece_id ?? "");
    setStatuses(Object.fromEntries(Object.entries(prior?.pieces ?? {}).map(([key, value]) => [key, value.status])));
  }
  function open(next: Mode) {
    setError("");
    setMode(next);
    selectBook(next === "NEXT_BOOK" ? "" : snapshot.state.product_id ?? "");
    if (next === "FINISH") setPieceId(remaining[0]?.id ?? "");
  }
  async function save(values: Omit<LearningCommand, "revision" | "session_id">) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await learningAction(studentId, sessionId, { ...values, revision: snapshot.revision, session_id: sessionId });
      if (!result.ok) { setError(result.message); return; }
      setSnapshot(result.data); setMode(null); setShowHistory(false);
      setNotice(values.action === "UNDO" ? "Modification annulée ✓" : "Enregistré ✓");
    } catch { setError("Enregistrement non confirmé. Rechargez le suivi pour vérifier avant de réessayer."); }
    finally { inFlight.current = false; setBusy(false); }
  }
  async function reload(history = false) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true);
    try {
      const result = await learningAction(studentId, sessionId);
      if (result.ok) { setSnapshot(result.data); setError(""); setMode(null); setShowHistory(history); }
      else setError(result.message);
    } catch { setError("Connexion indisponible. Vos choix sont conservés dans le formulaire."); }
    finally { inFlight.current = false; setBusy(false); }
  }

  return <section className={styles.card} aria-label={`Progression musicale de ${studentName}`} aria-busy={busy} data-learning-draft={mode !== null}>
    <header className={styles.header}><strong>Travail du cours</strong></header>
    <p className={styles.current}>{current?.title ?? "Partition à renseigner"}<br />
      <strong>{book?.completed ? "Partition terminée ✓" : piece?.title ?? "Morceau à renseigner"}</strong>
    </p>
    {current?.pieces.length ? <small>{completed} morceau{completed > 1 ? "x" : ""} terminé{completed > 1 ? "s" : ""} sur {current.pieces.length}</small> :
      <p className={styles.help}>{current ? "Aucun morceau enregistré dans cette partition. Vous pouvez déjà corriger la partition actuelle." : "Choisissez la partition et le morceau réellement travaillés."}</p>}
    {!mode && <>
      {!book?.completed && piece && <div className={styles.actions}>
        <button type="button" disabled={busy} onClick={() => save({ action: "CONTINUE" })}>Continuer ce morceau</button>
        <button type="button" className={styles.primary} disabled={busy} onClick={() => open("FINISH")}>Terminé → suivant</button>
      </div>}
      {!piece && !book?.completed && <div className={styles.actions}><button type="button" className={styles.primary} disabled={busy} onClick={() => open("CORRECT")}>Choisir le morceau travaillé</button></div>}
      {allDone && !book?.completed && <button type="button" disabled={busy} onClick={() => save({ action: "COMPLETE_BOOK" })}>Terminer cette partition</button>}
      {book?.completed && <button type="button" className={styles.primary} disabled={busy} onClick={() => open("NEXT_BOOK")}>Choisir la prochaine partition</button>}
      <details className={styles.more}><summary>Partition et morceaux déjà travaillés</summary>
        <div className={styles.links}>
          <button type="button" disabled={busy} onClick={() => open("CORRECT")}>Changer la partition ou le morceau</button>
          <button type="button" disabled={busy} onClick={() => open("HISTORY")}>Indiquer les morceaux déjà terminés</button>
          <button type="button" disabled={busy} onClick={() => reload(!showHistory)}>Consulter la progression</button>
        </div>
      </details>
    </>}
    {mode && <form onSubmit={(event) => {
      event.preventDefault();
      save(mode === "FINISH" ? { action: "COMPLETE_PIECE", piece_id: pieceId || null } :
        { action: mode, product_id: productId, piece_id: pieceId || null, note, ...(mode === "HISTORY" ? { statuses } : {}) });
    }}>
      <fieldset disabled={busy} className={styles.editor}>
        <legend>{mode === "FINISH" ? "Choisir le prochain morceau" : mode === "HISTORY" ? "Morceaux déjà terminés" : mode === "NEXT_BOOK" ? "Prochaine partition" : "Partition et morceau travaillés"}</legend>
        {mode !== "FINISH" && <label>Partition travaillée
          <select required value={productId} onChange={(e) => selectBook(e.target.value)}>
            <option value="">Choisir une partition</option>
            {catalog.filter((p) => mode !== "NEXT_BOOK" || p.product_id !== current?.product_id).map((p) => <option key={p.product_id} value={p.product_id}>{p.title}</option>)}
          </select>
        </label>}
        <label>{mode === "FINISH" ? "Morceau suivant" : "Morceau actuel"}
          <select required={mode === "FINISH" && remaining.length > 0} value={pieceId} onChange={(e) => setPieceId(e.target.value)}>
            <option value="">{mode === "FINISH" ? "Aucun : tous les morceaux sont terminés" : "À définir plus tard"}</option>
            {(mode === "FINISH" ? current?.pieces : editor?.pieces)?.filter((p) => mode !== "FINISH" || p.id !== book?.current_piece_id).map((p) =>
              <option key={p.id} value={p.id}>{p.title}{book?.pieces[p.id]?.status === "COMPLETED" && mode === "FINISH" ? " · déjà terminé, à reprendre" : ""}</option>)}
          </select>
        </label>
        {mode === "FINISH" && <p className={styles.help}>« {piece?.title} » sera marqué terminé. Vous pouvez choisir un morceau dans n’importe quel ordre.</p>}
        {mode === "CORRECT" && <p className={styles.help}>Corrige le morceau ou la partition actuelle. Aucun morceau n’est déclaré terminé ; la remise du livre reste suivie séparément.</p>}
        {mode === "NEXT_BOOK" && <p className={styles.help}>La remise physique de cette partition se confirme dans « Mes partitions ».</p>}
        {mode === "HISTORY" && <>
          <p className={styles.help}>Cochez les morceaux déjà terminés. Les autres restent à vérifier. Aucune date de fin passée ne sera inventée.</p>
          <button type="button" disabled={!pieceId} onClick={() => {
            const index = editor?.pieces.findIndex((p) => p.id === pieceId) ?? -1;
            const next = { ...statuses };
            editor?.pieces.slice(0, Math.max(index, 0)).forEach((p) => { next[p.id] = "COMPLETED"; });
            setStatuses(next);
          }}>Tous avant le morceau actuel sont terminés</button>
          <small>Décochez ensuite les exceptions.</small>
          <div className={styles.pieces}>{editor?.pieces.map((p) => <div className={styles.piece} key={p.id}>
            <label><input type="checkbox" checked={statuses[p.id] === "COMPLETED"} onChange={(e) => setStatuses({ ...statuses, [p.id]: e.target.checked ? "COMPLETED" : "UNKNOWN" })} />
              <span>{p.title}{p.id === pieceId ? " · actuel" : ""}</span></label>
            <button type="button" aria-label={`${p.title} : ${labels[statuses[p.id] ?? "UNKNOWN"]}`} onClick={() => setStatuses({ ...statuses, [p.id]: statuses[p.id] === "REVIEW" ? "UNKNOWN" : "REVIEW" })}>
              {labels[statuses[p.id] ?? "UNKNOWN"]}
            </button>
          </div>)}</div>
          {!editor?.pieces.length && <p>Aucun morceau enregistré pour cette partition.</p>}
        </>}
        {mode !== "FINISH" && <details><summary>Note pédagogique (facultative)</summary>
          <textarea aria-label="Note pédagogique" rows={2} maxLength={4000} value={note} onChange={(e) => setNote(e.target.value)} />
        </details>}
        <div className={styles.actions}><button type="button" onClick={() => setMode(null)}>Annuler</button>
          <button type="submit" className={styles.primary}>Enregistrer</button></div>
      </fieldset>
    </form>}
    <div role="status" aria-live="polite" className={styles.notice}>{busy ? "Enregistrement / chargement…" : notice}
      {!busy && snapshot.undo_event_id && <button type="button" onClick={() => save({ action: "UNDO", undo_event_id: snapshot.undo_event_id })}>Annuler la dernière action</button>}
    </div>
    {error && <div role="alert" className={styles.error}>{error}<button type="button" disabled={busy} onClick={() => reload()}>Recharger le suivi</button></div>}
    {showHistory && <div className={styles.history}>
      {Object.entries(snapshot.state.books).map(([id, followedBook]) => {
        const partition = catalog.find((p) => p.product_id === id);
        return <details key={id}><summary>{partition?.title ?? "Ancienne partition"}{followedBook.completed ? " · terminée" : ""}</summary>
          {partition?.pieces.map((p) => <p key={p.id}>{p.title} : {labels[followedBook.pieces[p.id]?.status ?? "UNKNOWN"]}
            {followedBook.pieces[p.id]?.source === "BASELINE" ? " · reprise d’historique" : ""}
            {followedBook.pieces[p.id]?.completed_at ? ` · ${new Date(followedBook.pieces[p.id].completed_at!).toLocaleDateString("fr-FR", { timeZone: "Europe/Paris" })}` : ""}
          </p>)}
          {followedBook.note && <p>{followedBook.note}</p>}
        </details>;
      })}
      <strong>Dernières actions</strong>
      {snapshot.history?.length ? snapshot.history.map((event) => <p key={event.id}>
        {({ CORRECT: "Correction", HISTORY: "Reprise d’historique", CONTINUE: "Morceau poursuivi", COMPLETE_PIECE: "Morceau terminé", COMPLETE_BOOK: "Partition terminée", NEXT_BOOK: "Nouvelle partition", UNDO: "Annulation" } as Record<string, string>)[event.action] ?? event.action}
        {" · "}{new Date(event.at).toLocaleString("fr-FR", { timeZone: "Europe/Paris" })}
        {" · "}{event.actor_name}
        {" · "}{catalog.find((p) => p.product_id === event.product_id)?.title}
        {event.piece_id ? ` · ${catalog.find((p) => p.product_id === event.product_id)?.pieces.find((p) => p.id === event.piece_id)?.title ?? "Morceau archivé"}` : ""}
      </p>) : <p>Pas encore d’action enregistrée.</p>}
    </div>}
  </section>;
}
