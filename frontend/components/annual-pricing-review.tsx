"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { annualPricingAction } from "../lib/actions";

type Option = { id: string; label: string };
type Context = {
  students: Option[]; families: Record<string, Option[]>; references: Record<string, string | null>;
  primary_courses: Record<string, Option[]>;
  lines: { id: string; title: string; quantity: string }[];
  review: { verified_at: string; student_id: string; audience: string; primary_line_id: string; primary_contract_course_key?: string; review_note: string } | null;
};
type Preview = { version: string; previous_total: string; total: string; returning_verified: boolean;
  decisions: { line_id: string; title: string; quantity: string; base: string; net: string;
    pricing: { components: { code: string; label: string; amount_ttc: string }[] } }[] };

export default function AnnualPricingReview({ quoteId, editable, revision }: { quoteId: string; editable: boolean; revision: string }): JSX.Element {
  const router = useRouter();
  const [context, setContext] = useState<Context | null>(null);
  const [student, setStudent] = useState("");
  const [audience, setAudience] = useState("");
  const [primary, setPrimary] = useState("");
  const [reference, setReference] = useState("");
  const [replaceReference, setReplaceReference] = useState(false);
  const [note, setNote] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    let active = true;
    annualPricingAction(quoteId, "context").then(result => {
      if (!active) return;
      if (!result.ok) { setMessage(result.message); return; }
      const data = result.data as Context;
      setContext(data);
      const id = data.review?.student_id || (data.students.length === 1 ? data.students[0].id : "");
      setStudent(id); setReference(data.references[id] || "");
      setAudience(data.review?.audience || "");
      setPrimary(data.review?.primary_contract_course_key ? `contract:${data.review.primary_contract_course_key}` : data.review?.primary_line_id || (data.lines.length === 1 ? data.lines[0].id : ""));
      setNote(data.review?.review_note || "");
    });
    return () => { active = false; };
  }, [quoteId, revision]);

  async function run(apply: boolean): Promise<void> {
    setBusy(true); setMessage("");
    try {
      const result = await annualPricingAction(quoteId, apply ? "apply" : "preview", {
        student_id: student, audience, primary_line_id: primary.startsWith("contract:") ? null : primary,
        primary_contract_course_key: primary.startsWith("contract:") ? primary.slice(9) : null,
        replace_family_reference: replaceReference,
        family_reference_child_id: reference || null, review_note: note,
        expected_version: apply ? preview?.version : undefined,
      });
      if (!result.ok) { setMessage(result.message); setPreview(null); return; }
      if (apply) {
        setMessage("Remises enregistrées. Les lignes du devis et l'échéancier sont mis à jour. Aucun email envoyé.");
        setPreview(null); router.refresh();
      } else setPreview(result.data as Preview);
    } finally { setBusy(false); }
  }
  return <details className="card top-gap-sm">
    <summary><strong>Vérifier et calculer les remises annuelles</strong>{context?.review ? " · Décision enregistrée" : ""}</summary>
    <p>Prix issus de la grille, remises détaillées par séance et conservées à l'inscription. Les remises manuelles ne sont jamais cumulées automatiquement.</p>
    {!editable ? <p>Devis verrouillé : décision tarifaire conservée, aucune modification.</p> : <>
      {context && !context.students.length ? <p role="alert">Rattachez d'abord une fiche enfant au client du devis pour vérifier les liens familiaux. Aucun rapprochement automatique par nom.</p> : null}
      <fieldset disabled={busy} onChange={() => setPreview(null)}>
        <div className="grid cols-2">
          <label>Élève concerné<select value={student} onChange={e => { setStudent(e.target.value); setReference(context?.references[e.target.value] || ""); }}>
            <option value="">Sélectionner</option>{context?.students.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select></label>
          <label>Catégorie vérifiée pour ce cours<select value={audience} onChange={e => setAudience(e.target.value)}>
            <option value="">À vérifier</option><option value="CHILD">Enfant (hors adolescent)</option><option value="TEEN">Adolescent</option>
          </select></label>
          <label>Premier cours annuel<select value={primary} onChange={e => setPrimary(e.target.value)}>
            <option value="">Sélectionner le cours principal</option>{context?.lines.map(l => <option key={l.id} value={l.id}>{l.title} · {l.quantity} séances</option>)}
            {context?.primary_courses[student]?.map(c => <option key={c.id} value={`contract:${c.id}`}>Déjà souscrit : {c.label}</option>)}
          </select></label>
          <label>Enfant de référence de la famille pour la saison<select value={reference} onChange={e => setReference(e.target.value)}>
            <option value="">Pas de remise famille</option>{context?.families[student]?.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select></label>
        </div>
        <p>La référence ne dépend pas de l'ordre d'acceptation des devis. Vérifiez l'inscription annuelle de cet enfant et conservez le même choix pour toute la famille.</p>
        <label><input type="checkbox" checked={replaceReference} onChange={e => setReplaceReference(e.target.checked)} /> Modifier la référence de la famille (brouillons seulement ; les autres devis devront être revérifiés)</label>
        <label>Vérification / justificatif interne (obligatoire)<textarea value={note} minLength={10} onChange={e => setNote(e.target.value)} placeholder="Catégorie contrôlée, inscription annuelle du premier enfant, référence du devis…" /></label>
        <button type="button" disabled={!student || !audience || !primary || note.trim().length < 10} onClick={() => void run(false)}>Calculer et afficher l'aperçu</button>
      </fieldset>
      {preview ? <div className="top-gap-sm">
        <table><thead><tr><th>Cours</th><th>Base / séance</th><th>Remises / séance</th><th>Net / séance</th><th>Quantité</th></tr></thead>
          <tbody>{preview.decisions.map(d => <tr key={d.line_id}><td>{d.title}</td><td>{d.base} €</td><td>{d.pricing.components.length ? d.pricing.components.map(c => <div key={c.code}>{c.label} : {c.amount_ttc} €</div>) : "Aucune"}</td><td>{d.net} €</td><td>{d.quantity}</td></tr>)}</tbody></table>
        {!preview.returning_verified ? <p>Aucune inscription annuelle active de la saison précédente retrouvée : fidélité non attribuée.</p> : null}
        <p>Total avant : {preview.previous_total} € — Total après : <strong>{preview.total} € TTC</strong></p>
        <button className="primary" type="button" disabled={busy} onClick={() => void run(true)}>Confirmer ces remises sur le devis</button>
      </div> : null}
    </>}
    <p role="status" aria-live="polite">{busy ? "Vérification en cours…" : message}</p>
  </details>;
}
