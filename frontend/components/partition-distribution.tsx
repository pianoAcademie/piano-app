"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { partitionDistributionAction } from "../lib/partition-distribution-actions";

export type DistributionData = {
  week: string; is_admin: boolean;
  products: { id: string; title: string }[];
  needs: { student_id: string; student_name: string; professor_id: string; professor: string; site: string; course_at: string;
    assignment_id: string | null; product_id: string | null; title: string; status: string }[];
  totals: { professor_id: string; professor: string; product_id: string; title: string; needed: number; held: number; pending: number; to_pickup: number; richelieu: number }[];
  movements: { id: string; professor_id: string; product_id: string; professor: string; title: string; kind: string; state: string; quantity: number; created_at: string; confirmed_at: string | null;
    student: string | null; actor: string | null; confirmed_by: string | null }[];
};

function ActionForm({ children, portal }: { children: React.ReactNode; portal: string }) {
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const busy = useRef(false);
  const operation = useRef<string | null>(null);
  const router = useRouter();
  return <form onSubmit={async event => {
    event.preventDefault();
    if (busy.current) return;
    const data = new FormData(event.currentTarget);
    operation.current ??= crypto.randomUUID();
    data.set("operation_id", operation.current);
    data.set("portal", portal);
    busy.current = true; setPending(true); setResult(null);
    try {
      const response = await partitionDistributionAction(data);
      setResult(response);
      if (response.ok) router.refresh();
    } catch { setResult({ ok: false, message: "Réponse non reçue. Réessayez : le même retrait ne sera pas compté deux fois." }); }
    finally { busy.current = false; setPending(false); }
  }}>
    <fieldset disabled={pending || result?.ok} style={{ border: 0, padding: 0, margin: "8px 0" }}>{children}</fieldset>
    {pending && <p role="status">Enregistrement en cours…</p>}
    {result && <p role={result.ok ? "status" : "alert"}>{result.message}</p>}
  </form>;
}

const hidden = (name: string, value: string) => <input type="hidden" name={name} value={value} />;
const dateText = (value: string) => new Date(value).toLocaleString("fr-FR", { timeZone: "Europe/Paris", dateStyle: "short", timeStyle: "short" });

export default function PartitionDistribution({ data }: { data: DistributionData }) {
  const portal = data.is_admin ? "admin" : "prof";
  return <main className="page teacher-shell">
    <Link href={data.is_admin ? "/admin/products" : "/prof"}>← Retour</Link>
    <h1>{data.is_admin ? "Distribution des partitions — Paris" : "Mes partitions — Paris"}</h1>
    <p>Retrait à Richelieu, puis remise à chaque élève. Les besoins suivent le premier cours de chaque élève dans la semaine.</p>
    <form method="get"><label>Semaine du <input type="date" name="week" defaultValue={data.week} required /></label> <button>Afficher</button></form>
    <section className="card"><h2>Quantités à récupérer à Richelieu</h2>
      {!data.totals.length && <p>Aucun besoin de partition renseigné pour cette semaine.</p>}
      {data.totals.map(row => <article key={`${row.professor_id}-${row.product_id}`} style={{ borderBottom: "1px solid #ddd", padding: "12px 0" }}>
        <h3>{row.title}{data.is_admin ? ` — ${row.professor}` : ""}</h3>
        <p>À remettre : {row.needed} · Déjà chez le professeur : {row.held} · Reste à récupérer : <strong>{Math.max(0, row.needed-row.held)}</strong> · Stock disponible à Richelieu : {row.richelieu}</p>
        {row.needed-row.held > row.richelieu && <p role="alert" style={{ background: "#fde2df", color: "#8b1717", padding: 14, borderRadius: 10, fontWeight: 700 }}>Stock insuffisant : {Math.max(0, row.needed-row.held)} nécessaires, {row.richelieu} disponibles. Il manque {row.needed-row.held-row.richelieu} exemplaire(s). Un retrait partiel est possible.</p>}
        {row.pending > 0 && <p>Demande en attente : {row.pending}. Aucun exemplaire retiré tant que le retrait réel n’est pas confirmé.</p>}
        {data.movements.filter(m => m.product_id === row.product_id && m.professor_id === row.professor_id && m.kind === "PICKUP" && m.state === "PENDING").map(m => <div key={m.id}>
          <ActionForm portal={portal}>{hidden("action", "cancel")}{hidden("movement_id", m.id)}<button>Annuler cette demande</button></ActionForm>
          <ActionForm portal={portal}>{hidden("action", "confirm")}{hidden("movement_id", m.id)}
            <label>Quantité réellement récupérée à Richelieu <input name="quantity" type="number" min="1" max={row.richelieu} required placeholder="Saisir la quantité retirée" /></label>
            <label><input type="checkbox" required /> Je confirme que ces exemplaires ont été physiquement récupérés.</label>
            <button disabled={row.richelieu < 1}>Confirmer le retrait réel</button>
          </ActionForm>
        </div>)}
        {row.pending === 0 &&
        <ActionForm portal={portal}>
          {hidden("action", "movement")}{hidden("professor_id", row.professor_id)}{hidden("product_id", row.product_id)}{hidden("kind", "PICKUP")}
          <label>Quantité demandée <input name="quantity" type="number" min="1" max="500" defaultValue={Math.max(row.to_pickup, 1)} required /></label> <button>Préparer le retrait</button>
        </ActionForm>}
        {row.held > 0 && <ActionForm portal={portal}>
          {hidden("action", "movement")}{hidden("professor_id", row.professor_id)}{hidden("product_id", row.product_id)}{hidden("kind", "RETURN")}
          <label>Exemplaires à rendre <input name="quantity" type="number" min="1" max={row.held} defaultValue="1" required /></label> <button>Déclarer un retour à Richelieu</button>
        </ActionForm>}
      </article>)}
    </section>
    <section className="card"><h2>Élèves à servir</h2>
      {!data.needs.length && <p>Aucune remise à prévoir pour cette semaine.</p>}
      {data.needs.map(row => <article key={`${row.student_id}-${row.assignment_id}`} style={{ borderBottom: "1px solid #ddd", padding: "12px 0" }}>
        <h3>{row.student_name} — {row.title}</h3>
        <p>{row.site} · {dateText(row.course_at)} · {row.professor}</p>
        {row.assignment_id && <details><summary>Changer la partition prévue avant le retrait</summary>
          <ActionForm portal={portal}>
            {hidden("action", "change")}{hidden("student_id", row.student_id)}{hidden("assignment_id", row.assignment_id)}
            <select aria-label="Nouvelle partition prévue" name="product_id" defaultValue={row.product_id ?? ""} required>
              <option value="">Choisir</option>{data.products.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}
            </select> <button>Modifier le besoin</button>
          </ActionForm>
        </details>}
        <ActionForm portal={portal}>
          {hidden("action", row.assignment_id ? "deliver" : "define")}{hidden("professor_id", row.professor_id)}
          {hidden("student_id", row.student_id)}{row.assignment_id && hidden("assignment_id", row.assignment_id)}
          <label>{row.assignment_id ? "Partition effectivement remise" : "Partition à prévoir"} <select name="product_id" defaultValue={row.product_id ?? ""} required>
            <option value="">Choisir une partition</option>{data.products.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}
          </select></label> <button>{row.assignment_id ? "Confirmer la remise à l’élève" : "Enregistrer la partition"}</button>
        </ActionForm>
      </article>)}
    </section>
    <section className="card"><h2>Retraits, retours et remises</h2>
      {data.movements.length === 0 && <p>Aucun mouvement enregistré.</p>}
      {data.movements.map(row => <article key={row.id} style={{ borderBottom: "1px solid #ddd", padding: "8px 0" }}>
        {row.student && <strong>Élève : {row.student}</strong>}
        <p>{dateText(row.confirmed_at ?? row.created_at)} · {row.professor} · {row.title} × {row.quantity} · {({ PICKUP: "Retrait", RETURN: "Retour", DELIVERY: "Remise à l’élève" })[row.kind] ?? row.kind} · {row.state === "CONFIRMED" ? "Confirmé" : row.state === "CANCELLED" ? "Annulé" : "En attente de validation à Richelieu"}</p>
        <small>Enregistré par {row.actor ?? "—"}{row.confirmed_by ? ` · Validé par ${row.confirmed_by}` : ""}</small>
        {row.state === "PENDING" && <ActionForm portal={portal}>{hidden("action", "cancel")}{hidden("movement_id", row.id)}<button>Annuler la demande</button></ActionForm>}
        {data.is_admin && row.state === "PENDING" && <ActionForm portal={portal}>
          {hidden("action", "confirm")}{hidden("movement_id", row.id)}
          <label>Quantité réellement {row.kind === "RETURN" ? "reçue" : "remise au professeur"} <input name="quantity" type="number" min="1" max="500" required /></label> <button>Valider le {row.kind === "RETURN" ? "retour" : "retrait"}</button>
        </ActionForm>}
      </article>)}
    </section>
  </main>;
}
