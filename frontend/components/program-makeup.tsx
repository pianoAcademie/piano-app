"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { makeupProgrammingAction } from "../lib/actions";

type Slot = { id: string; title: string; start: string; end: string; location: string; timezone: string; version: string };
type Options = { options: Slot[]; pass: string; ends_at: string; currency: string };

export default function ProgramMakeup({ studentId, requestId, studentName }: {
  studentId: string; requestId: string; studentName: string;
}): JSX.Element {
  const router = useRouter();
  const inFlight = useRef(false);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState<Options | null>(null);
  const [start, setStart] = useState(() => new Date().toLocaleDateString("en-CA"));
  const [place, setPlace] = useState("");
  const [selected, setSelected] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState(false);
  const [saved, setSaved] = useState(false);
  const slot = data?.options.find(option => option.id === selected);
  const label = (s: Slot): string => `${new Date(s.start).toLocaleString("fr-FR", { timeZone: s.timezone, dateStyle: "full", timeStyle: "short" })} – ${new Date(s.end).toLocaleTimeString("fr-FR", { timeZone: s.timezone, hour: "2-digit", minute: "2-digit" })} · ${s.location} · ${s.title}`;

  async function run(confirm: boolean): Promise<void> {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setMessage(""); setError(false);
    try {
      const result = await makeupProgrammingAction(studentId, requestId, confirm ? "program" : "options", confirm ? { session_id: selected, expected_version: slot?.version || "" } : { start });
      if (!result.ok) { setError(true); setMessage(result.message); return; }
      if (confirm) {
        setSaved(true);
        setMessage("Rattrapage enregistré. Aucun crédit supplémentaire consommé, aucun supplément à facturer. Aucun email de confirmation envoyé.");
        router.refresh();
      } else {
        setData(result.data as Options); setSelected(""); setPlace("");
      }
    } catch {
      setError(true);
      setMessage("La réponse n'a pas pu être reçue. Vous pouvez réessayer : une même confirmation ne crée pas de doublon.");
    } finally { inFlight.current = false; setBusy(false); }
  }

  return <div className="top-gap-sm">
    {!open ? <button type="button" onClick={() => { setOpen(true); void run(false); }}>Programmer ce rattrapage</button> : <section aria-label={`Programmer le rattrapage de ${studentName}`}>
      <h4>Programmer ce rattrapage — {studentName}</h4>
      {!saved ? <>
        <p>Une seule séance de remplacement. Le cours habituel et sa facturation sont conservés. Aucun crédit supplémentaire du pass n'est consommé.</p>
        <fieldset disabled={busy}>
          <div className="row">
            <label>Rechercher sur un mois à partir du<input type="date" value={start} onChange={e => { setStart(e.target.value); setData(null); setSelected(""); }} /></label>
            <button type="button" disabled={!start} onClick={() => void run(false)}>Rechercher les disponibilités</button>
          </div>
          {data ? <>
            <p>{data.pass} · Fin de validité : {new Date(data.ends_at).toLocaleDateString("fr-FR")}</p>
            <label>Lieu<select value={place} onChange={e => { setPlace(e.target.value); setSelected(""); }}>
              <option value="">Tous les lieux compatibles</option>
              {[...new Set(data.options.map(o => o.location))].map(location => <option key={location}>{location}</option>)}
            </select></label>
            <label>Créneau de remplacement<select value={selected} onChange={e => setSelected(e.target.value)}>
              <option value="">Choisir un créneau</option>
              {data.options.filter(o => !place || o.location === place).map(o => <option key={o.id} value={o.id}>{label(o)}</option>)}
            </select></label>
            {!data.options.length ? <p>Aucun créneau compatible disponible sur cette période. Essayez une autre date ; ne forcez pas une inscription payante.</p> : null}
          </> : null}
          {slot ? <div className="flash-ok top-gap-sm">
            <strong>{label(slot)}</strong>
            <p>Supplément à payer : 0 {data?.currency}. Le rattrapage est lié à cette absence ; les factures existantes restent inchangées.</p>
            <button type="button" className="primary" onClick={() => void run(true)}>Confirmer ce rattrapage</button>
          </div> : null}
          <button type="button" className="top-gap-sm" onClick={() => setOpen(false)}>Fermer</button>
        </fieldset>
      </> : null}
      <p role={error ? "alert" : "status"} aria-live="polite" className={error ? "flash-err" : ""}>
        {busy ? "Vérification et enregistrement en cours…" : message}
      </p>
    </section>}
  </div>;
}
