import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { backendRequest } from "../../../lib/backend";
import type { UserOut } from "../../../lib/types";
import { importSportigoAction } from "./actions";

type SearchParams = Record<string, string | string[] | undefined>;

type CatalogItem = { code: string; name: string; kind: string | null };
type Catalog = { subscription_plans: CatalogItem[]; credit_types: CatalogItem[] };

function value(params: Record<string, string | string[] | undefined>, name: string): string {
  const raw = params[name];
  return Array.isArray(raw) ? raw[0] ?? "" : raw ?? "";
}

function findDefault(items: CatalogItem[], words: string[]): string {
  const match = items.find((item) => {
    const haystack = `${item.code} ${item.name}`.toLocaleLowerCase("fr");
    return words.every((word) => haystack.includes(word));
  });
  return match?.code ?? items[0]?.code ?? "";
}

export default async function SportigoImportPage({ searchParams }: { searchParams: SearchParams }) {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) redirect("/login?error_code=session_expired");
  const [me, catalogResult] = await Promise.all([
    backendRequest<UserOut>("/api/v1/auth/me", {}, token),
    backendRequest<Catalog>("/api/v1/admin/sportigo-import/catalog", {}, token),
  ]);
  const params = searchParams;
  if (!me.ok || me.data.role !== "admin") redirect("/login?error_code=admin_access_required");
  if (!catalogResult.ok) {
    return <section className="card"><h1>Import Sportigo</h1><p className="error">{catalogResult.message}</p></section>;
  }
  const catalog = catalogResult.data;
  const monthlyDefault = findDefault(catalog.subscription_plans, ["collect", "adulte"]);
  const studioDefault = findDefault(catalog.credit_types, ["studio"]);
  const collectiveDefault = findDefault(catalog.credit_types, ["collect"]);
  const onlineDefault = findDefault(catalog.credit_types, ["ligne"]);
  const solfegeDefault = findDefault(catalog.credit_types, ["solf"]);
  const ok = value(params, "ok");
  const error = value(params, "error");

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread">
          <div>
            <h1>Import Sportigo</h1>
            <p className="muted">Import idempotent des adultes, abonnements et crédits. Aucun email n’est envoyé par cet écran.</p>
          </div>
          <Link href="/admin/clients">Retour aux clients</Link>
        </div>
        {error ? <p className="error">{error}</p> : null}
        {ok ? (
          <div className="success">
            <strong>{value(params, "mode")}</strong> — {value(params, "clients")} client(s), {value(params, "monthly")} abonnement(s), {value(params, "credit_clients")} client(s) avec crédits.
            <br />Créés : {value(params, "created")} · Rapprochés : {value(params, "reused")} · Crédits studio/collectif/en ligne/solfège : {value(params, "credits")}.
          </div>
        ) : null}
      </section>

      <section className="card">
        <form action={importSportigoAction} className="stack">
          <label>
            Fichier CSV préparé
            <input name="file" type="file" accept=".csv,text/csv" required />
          </label>
          <label>
            Référence du lot
            <input name="batch_reference" defaultValue="SPORTIGO-2026-08-05-INITIAL" required maxLength={120} />
          </label>
          <div className="grid cols-2">
            <label>
              Formule mensuelle modèle
              <select name="template_plan_code" defaultValue={monthlyDefault} required>
                {catalog.subscription_plans.map((item) => <option key={item.code} value={item.code}>{item.name} · {item.code}</option>)}
              </select>
            </label>
            <label>
              Crédit studio
              <select name="studio_credit_type_code" defaultValue={studioDefault} required>
                {catalog.credit_types.map((item) => <option key={item.code} value={item.code}>{item.name} · {item.code}</option>)}
              </select>
            </label>
            <label>
              Crédit cours collectif
              <select name="collective_credit_type_code" defaultValue={collectiveDefault} required>
                {catalog.credit_types.map((item) => <option key={item.code} value={item.code}>{item.name} · {item.code}</option>)}
              </select>
            </label>
            <label>
              Crédit cours en ligne
              <select name="online_credit_type_code" defaultValue={onlineDefault} required>
                {catalog.credit_types.map((item) => <option key={item.code} value={item.code}>{item.name} · {item.code}</option>)}
              </select>
            </label>
            <label>
              Crédit solfège
              <select name="solfege_credit_type_code" defaultValue={solfegeDefault} required>
                {catalog.credit_types.map((item) => <option key={item.code} value={item.code}>{item.name} · {item.code}</option>)}
              </select>
            </label>
          </div>
          <label className="row gap-sm">
            <input name="dry_run" type="checkbox" defaultChecked /> Prévisualisation uniquement
          </label>
          <label className="row gap-sm">
            <input name="activate" type="checkbox" /> Activer les comptes et droits (uniquement samedi)
          </label>
          <label>
            Confirmation d’application
            <input name="confirm_apply" placeholder="Laisser vide en prévisualisation ; sinon recopier la référence du lot" />
          </label>
          <button type="submit">Contrôler / importer</button>
        </form>
      </section>
    </section>
  );
}
