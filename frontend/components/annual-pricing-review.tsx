"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { annualPricingAction } from "../lib/actions";
import { PricingLinesTable, pricingMoney, type PricingLine } from "./quote-pricing-recap";
import { allowedAudiences, initialStudent, type StudentOption, type CourseOption, type Audience } from "../lib/annual-pricing-selection";

type Option = { id: string; label: string };
type Enrollment = { status: "AUTO" | "NEW" | "RETURNING_MANUAL"; history_found: boolean; evidence: { note: string; actor_name: string; verified_at: string } | null };
type Context = {
  applicable: boolean;
  students: StudentOption[]; families: Record<string, Option[]>; references: Record<string, string | null>;
  primary_courses: Record<string, Option[]>;
  lines: CourseOption[];
  enrollments: Record<string, Enrollment>; manual_discounts: PricingLine[]; review_error: string | null;
  review: { verified_at: string; actor_name?: string; student_id: string; audience: string; primary_line_id: string; primary_contract_course_key?: string; review_note: string;
    enrollment?: { status: string; source: string; note: string }; family: boolean; family_reference_child_id?: string; keep_manual?: boolean; total: string } | null;
};
type Preview = { version: string; previous_total: string; total: string; returning_verified: boolean;
  display_lines: PricingLine[]; replaced_discounts: PricingLine[]; keep_manual: boolean; family: boolean;
  enrollment: { status: string; source: string; note: string };
  decisions: { line_id: string; title: string; quantity: string; base: string; net: string;
    pricing: { components: { code: string; label: string; amount_ttc: string }[] } }[] };

export default function AnnualPricingReview({ quoteId, editable, revision }: { quoteId: string; editable: boolean; revision: string }): JSX.Element | null {
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
  const [enrollmentStatus, setEnrollmentStatus] = useState<Enrollment["status"]>("AUTO");
  const [enrollmentNote, setEnrollmentNote] = useState("");
  const [manualPolicy, setManualPolicy] = useState("BLOCK");
  function populate(data: Context): void {
    setContext(data); setPreview(null); setManualPolicy("BLOCK"); setReplaceReference(false);
    const id = initialStudent(data.students, data.review?.student_id);
    setStudent(id); setReference(data.references[id] || "");
    const allowed = allowedAudiences(data.students.find(s => s.id === id), data.lines);
    setAudience(allowed.includes(data.review?.audience as Audience) ? data.review!.audience : "");
    setPrimary(data.review?.primary_contract_course_key ? `contract:${data.review.primary_contract_course_key}` : data.review?.primary_line_id || (data.lines.length === 1 ? data.lines[0].id : ""));
    setNote(data.review?.review_note || "");
    setEnrollmentStatus(data.enrollments[id]?.status || "AUTO");
    setEnrollmentNote(data.enrollments[id]?.evidence?.note || "");
  }
  useEffect(() => {
    let active = true;
    annualPricingAction(quoteId, "context").then(result => {
      if (!active) return;
      if (!result.ok) { setMessage(result.message); return; }
      populate(result.data as Context);
    }).catch(() => { if (active) setMessage("Chargement impossible. Actualisez la page pour réessayer."); });
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
        enrollment_status: enrollmentStatus, enrollment_note: enrollmentNote, manual_discount_policy: manualPolicy,
        expected_version: apply ? preview?.version : undefined,
      });
      if (!result.ok) { setMessage(result.message); setPreview(null); return; }
      if (apply) {
        setMessage("Remises enregistrées. Les lignes du devis et l'échéancier sont mis à jour. Aucun email envoyé.");
        setPreview(null);
        const fresh = await annualPricingAction(quoteId, "context");
        if (fresh.ok) populate(fresh.data as Context);
        router.refresh();
      } else setPreview(result.data as Preview);
    } catch {
      setMessage("Réponse du serveur indisponible. Actualisez pour vérifier l'enregistrement avant de réessayer."); setPreview(null);
    } finally { setBusy(false); }
  }
  if (context && !context.applicable) return null;
  const selectedStudent = context?.students.find(s => s.id === student);
  const audiences = allowedAudiences(selectedStudent, context?.lines || []);
  const missing = !context ? "Chargement des critères…" : !context.students.length ? "Rattachez un élève client ou prospect dans le cadre du devis." :
    !context.lines.length ? "Aucun cours annuel pris en charge dans ce devis. Les montants enregistrés restent inchangés." :
    !student ? "Sélectionnez l'élève." : !audiences.length ? "Les cours du devis ne correspondent pas à la catégorie de cet élève. Vérifiez le dossier." :
    !audience || !audiences.includes(audience as Audience) ? "Sélectionnez la catégorie vérifiée." : !primary ? "Sélectionnez le premier cours annuel." :
    enrollmentStatus === "RETURNING_MANUAL" && enrollmentNote.trim().length < 10 ? "Justifiez la réinscription (10 caractères minimum)." :
    note.trim().length < 10 ? "Complétez le justificatif du calcul (10 caractères minimum)." :
    context.manual_discounts.length > 0 && manualPolicy === "BLOCK" ? "Choisissez de conserver ou remplacer les remises manuelles ci-dessous." : "";
  const familyMessage = (family: boolean, ref?: string | null) => family ? "Remise famille : élève distinct de l'enfant de référence (application selon le cours et la catégorie)." :
    ref ? "Remise famille non appliquée : cet élève est l'enfant de référence." : "Remise famille non demandée : aucun enfant de référence sélectionné.";
  return <section className="annual-pricing-review">
    {context?.review ? <div className="card top-gap-sm" aria-label="Décision tarifaire enregistrée">
      <h3>{context.review_error ? "Calcul enregistré à revérifier" : "Calcul enregistré"}</h3>
      <p>Validé par {context.review.actor_name || "l’administration"} le {new Date(context.review.verified_at).toLocaleString("fr-FR", { timeZone: "Europe/Paris" })}.</p>
      <p>{context.review.enrollment?.source === "ADMIN" ? "Réinscription / fidélité confirmée par l’administration" : context.review.enrollment?.source === "HISTORY" ? "Fidélité : historique annuel retrouvé" : context.review.enrollment?.status === "NEW" ? "Nouvelle inscription" : "Fidélité non justifiée par un historique ou une confirmation administrative"}</p>
      {context.review.enrollment?.note ? <p>Justificatif de réinscription : {context.review.enrollment.note}</p> : null}
      <p>{context.review.keep_manual ? "Calcul automatique de remise famille non appliqué : seules les lignes conservées comptent." : familyMessage(context.review.family, context.review.family_reference_child_id)}</p>
      <p>Justificatif du calcul : {context.review.review_note}</p>
      {context.review.keep_manual ? <p>Remises manuelles conservées : aucune remise automatique ajoutée.</p> : null}
      {context.review_error ? <p className="form-feedback error" role="alert">{context.review_error}</p> : null}
    </div> : <p className="form-feedback">Aucun calcul annuel confirmé. Les lignes enregistrées ci-dessus restent les montants du devis.</p>}
    <details className="card top-gap-sm">
    <summary><strong>Vérifier et calculer les remises annuelles</strong>{context?.review ? " · Décision enregistrée" : ""}</summary>
    <p>Prix issus de la grille, remises détaillées par séance et conservées à l'inscription. Les remises manuelles ne sont jamais cumulées automatiquement.</p>
    {!editable ? <p>Devis verrouillé : décision tarifaire conservée, aucune modification.</p> : <>
      {context && !context.students.length ? <p role="alert">Aucun élève rattaché à ce devis. <a href={`/admin/quotes/${encodeURIComponent(quoteId)}?section=cadre`}>Vérifier le cadre du devis</a>. Sélectionnez la fiche client ou prospect existante, sans créer de doublon.</p> : null}
      {selectedStudent?.kind === "PROSPECT" ? <p>Élève prospect : {selectedStudent.label}. Vous pouvez vérifier ce devis avant l'inscription. Aucune fiche client ne sera créée par ce calcul.</p> : null}
      <fieldset disabled={busy || !context || !context.students.length || !context.lines.length} onChange={() => { setPreview(null); setMessage(""); }}>
        <div className="grid cols-2">
          <label>Élève concerné<select value={student} onChange={e => { const id = e.target.value; setStudent(id); setReference(context?.references[id] || "");
            setEnrollmentStatus(context?.enrollments[id]?.status || "AUTO"); setEnrollmentNote(context?.enrollments[id]?.evidence?.note || ""); setNote(""); setAudience(""); setPrimary(""); }}>
            <option value="">Sélectionner</option>{context?.students.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select></label>
          <label>Catégorie vérifiée pour ce cours<select value={audience} onChange={e => { setAudience(e.target.value); if (e.target.value === "ADULT") { setReference(""); setReplaceReference(false); } }}>
            <option value="">À vérifier</option>{audiences.map(a => <option key={a} value={a}>{a === "CHILD" ? "Enfant (hors adolescent)" : a === "TEEN" ? "Adolescent" : "Adulte"}</option>)}
          </select></label>
          <label>Premier cours annuel<select value={primary} onChange={e => setPrimary(e.target.value)}>
            <option value="">Sélectionner le cours principal</option>{context?.lines.map(l => <option key={l.id} value={l.id}>{l.title} · {l.quantity} séances</option>)}
            {context?.primary_courses[student]?.map(c => <option key={c.id} value={`contract:${c.id}`}>Déjà souscrit : {c.label}</option>)}
          </select></label>
          {audience !== "ADULT" && selectedStudent?.audiences?.includes("ADULT") !== true ? <label>Enfant de référence de la famille pour la saison<select value={reference} onChange={e => setReference(e.target.value)}>
            <option value="">Pas de remise famille</option>{context?.families[student]?.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select></label> : <p>Adulte : aucune remise enfant/adolescent n'est appliquée automatiquement. Les remises manuelles restent soumises à votre choix ci-dessous.</p>}
        </div>
        <div className="grid cols-2">
          <label>Inscription pour cette saison<select value={enrollmentStatus} onChange={e => setEnrollmentStatus(e.target.value as Enrollment["status"])}>
            <option value="AUTO">Reprendre la confirmation enregistrée ou vérifier l’historique</option><option value="NEW">Nouvelle inscription</option>
            <option value="RETURNING_MANUAL">Réinscription — fidélité confirmée par l’administration</option>
          </select></label>
          {student ? <p>{context?.enrollments[student]?.history_found ? "Historique annuel de la saison précédente retrouvé." : "Aucun historique annuel retrouvé. Pour un ancien élève issu de l’ancien logiciel, confirmez la réinscription ci-contre."}</p> : null}
        </div>
        {enrollmentStatus === "RETURNING_MANUAL" ? <label>Justificatif de réinscription (obligatoire, 10 caractères minimum)
          <textarea value={enrollmentNote} maxLength={2000} onChange={e => setEnrollmentNote(e.target.value)} placeholder="Ex. inscription 2025-2026 vérifiée dans l’ancien logiciel, référence du dossier…" />
        </label> : null}
        <p className="muted">La confirmation est mémorisée pour cet élève et cette saison après enregistrement, y compris pour les devis manuels. Elle ne modifie pas les devis déjà envoyés.</p>
        {audience !== "ADULT" && selectedStudent?.audiences?.includes("ADULT") !== true ? <>
          <p>La référence ne dépend pas de l'ordre d'acceptation des devis. Vérifiez l'inscription annuelle de cet enfant et conservez le même choix pour toute la famille.</p>
          <label><input type="checkbox" checked={replaceReference} onChange={e => setReplaceReference(e.target.checked)} /> Modifier la référence de la famille (brouillons seulement ; les autres devis devront être revérifiés)</label>
        </> : null}
        {context?.manual_discounts.length ? <section className="card top-gap-sm">
          <h4>Remises manuelles / importées déjà enregistrées</h4><PricingLinesTable lines={context.manual_discounts} />
          <label>Traitement de ces remises<select value={manualPolicy} onChange={e => setManualPolicy(e.target.value)}>
            <option value="BLOCK">Choisir explicitement</option><option value="KEEP">Conserver les lignes actuelles — aucune remise automatique ajoutée</option>
            <option value="REPLACE">Remplacer toutes les remises manuelles listées par le calcul automatique</option>
          </select></label>
          <p>Aucune suppression à ce stade. Le remplacement n’a lieu qu’après confirmation de l’aperçu. Vérifiez notamment les remises exceptionnelles.</p>
        </section> : null}
        <label>Vérification / justificatif interne (obligatoire, 10 caractères minimum)<textarea value={note} minLength={10} maxLength={2000} onChange={e => setNote(e.target.value)} placeholder="Catégorie contrôlée, inscription annuelle du premier enfant, référence du devis…" /></label>
        <p role="status">{missing || "Prêt à calculer. L’aperçu ne sera pas enregistré automatiquement."}</p>
        <button type="button" disabled={Boolean(missing) || busy} onClick={() => void run(false)}>Calculer et afficher l'aperçu</button>
      </fieldset>
      {preview ? <div className="top-gap-sm">
        <h3>Aperçu non enregistré</h3>
        {preview.replaced_discounts.length ? <><h4>Remises qui seront remplacées après confirmation</h4><PricingLinesTable lines={preview.replaced_discounts} /></> : null}
        {preview.keep_manual ? <p>Conservation des lignes et montants actuels, sans nouvelle remise automatique.</p> : null}
        <h4>Lignes complètes après confirmation</h4><PricingLinesTable lines={preview.display_lines} />
        {preview.decisions.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Cours</th><th>Base / séance</th><th>Remises / séance</th><th>Net / séance</th><th>Quantité</th></tr></thead>
          <tbody>{preview.decisions.map(d => <tr key={d.line_id}><td>{d.title}</td><td>{d.base} €</td><td>{d.pricing.components.length ? d.pricing.components.map(c => <div key={c.code}>{c.label} : {c.amount_ttc} €</div>) : "Aucune"}</td><td>{d.net} €</td><td>{d.quantity}</td></tr>)}</tbody></table>
        </div> : null}
        <p>{preview.keep_manual ? "Le calcul automatique de remise famille n’est pas appliqué : seules les remises conservées ci-dessus comptent." : familyMessage(preview.family, reference)}</p>
        <p>{preview.returning_verified ? `Fidélité justifiée par ${preview.enrollment.source === "ADMIN" ? "confirmation administrative" : "l’historique annuel"}. Son application dépend du cours et des règles de cumul détaillées ci-dessus.` : "Fidélité non confirmée : aucune remise fidélité automatique. Les remises manuelles conservées restent visibles ci-dessus."}</p>
        <p>Total avant : {pricingMoney(preview.previous_total)} — Total après : <strong>{pricingMoney(preview.total)} TTC</strong></p>
        <button className="primary" type="button" disabled={busy} onClick={() => void run(true)}>Confirmer ces remises sur le devis</button>
      </div> : null}
    </>}
    <p role="status" aria-live="polite">{busy ? "Vérification en cours…" : message}</p>
  </details>
  </section>;
}
