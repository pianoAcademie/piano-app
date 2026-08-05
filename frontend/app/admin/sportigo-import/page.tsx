import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { backendRequest } from "../../../lib/backend";
import type { UserOut } from "../../../lib/types";
import { importSportigoAction, importSportigoHistoricalInvoicesAction } from "./actions";

type SearchParams = Record<string, string | string[] | undefined>;

type CatalogItem = { code: string; name: string; kind: string | null; credit_type_codes: string[] };
type Catalog = { subscription_plans: CatalogItem[]; pack_plans: CatalogItem[] };

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

function compatiblePacks(items: CatalogItem[], creditTypeCode: string): CatalogItem[] {
  const matches = items.filter((item) => item.credit_type_codes.includes(creditTypeCode));
  return matches.length > 0 ? matches : items;
}

function preferredPack(items: CatalogItem[], code: string, words: string[]): string {
  return items.find((item) => item.code === code)?.code ?? findDefault(items, words);
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
  const monthlyDefault = preferredPack(
    catalog.subscription_plans,
    "FORM_ABONNEMENT_MENSUEL_PRESENTIEL_STUDIO_SOL_E2ED74",
    ["présentiel", "studio", "solfège"],
  );
  const studioPacks = compatiblePacks(catalog.pack_plans, "CREDIT_STUDIO");
  const collectivePacks = compatiblePacks(catalog.pack_plans, "CREDIT_PIANO_ONSITE");
  const onlinePacks = compatiblePacks(catalog.pack_plans, "CREDIT_PIANO_ONLINE");
  const solfegePacks = compatiblePacks(catalog.pack_plans, "CREDIT_SOLFEGE_ONLINE");
  const studioDefault = preferredPack(studioPacks, "FORM_10_R_SERVATIONS_DE_STUDIO_2FC501", ["10", "studio"]);
  const collectiveDefault = preferredPack(collectivePacks, "PACK_5_PIANO", ["5", "piano"]);
  const onlineDefault = preferredPack(onlinePacks, "PACK_10_MULTI", ["10", "multi"]);
  const solfegeDefault = preferredPack(solfegePacks, "PACK_SOLFEGE_ONLINE_BALANCE", ["solfège"]);
  const ok = value(params, "ok");
  const error = value(params, "error");
  const invoiceOk = value(params, "invoice_ok");
  const invoiceError = value(params, "invoice_error");

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
              Carnet accès studio
              <select name="studio_pack_plan_code" defaultValue={studioDefault} required>
                {studioPacks.map((item) => <option key={item.code} value={item.code}>{item.name} · {item.code}</option>)}
              </select>
            </label>
            <label>
              Carnet cours collectifs en présentiel
              <select name="collective_pack_plan_code" defaultValue={collectiveDefault} required>
                {collectivePacks.map((item) => <option key={item.code} value={item.code}>{item.name} · {item.code}</option>)}
              </select>
            </label>
            <label>
              Carnet cours collectifs en ligne
              <select name="online_pack_plan_code" defaultValue={onlineDefault} required>
                {onlinePacks.map((item) => <option key={item.code} value={item.code}>{item.name} · {item.code}</option>)}
              </select>
            </label>
            <label>
              Carnet de solfège en ligne
              <select name="solfege_pack_plan_code" defaultValue={solfegeDefault} required>
                {solfegePacks.map((item) => <option key={item.code} value={item.code}>{item.name} · {item.code}</option>)}
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

      <section className="card">
        <div>
          <h2>Factures historiques Sportigo</h2>
          <p className="muted">Charge des PDF acquittés en lecture seule. Cette opération ne crée ni paiement, ni solde, ni prélèvement.</p>
        </div>
        {invoiceError ? <p className="error">{invoiceError}</p> : null}
        {invoiceOk ? (
          <p className="success">
            <strong>{value(params, "invoice_mode")}</strong> — {value(params, "invoice_rows")} facture(s), {value(params, "invoice_clients")} client(s). Créées : {value(params, "invoice_created")} · mises à jour : {value(params, "invoice_updated")} · inchangées : {value(params, "invoice_unchanged")}.
          </p>
        ) : null}
        <form action={importSportigoHistoricalInvoicesAction} className="stack">
          <label>
            Archive ZIP (manifest.csv + PDF)
            <input name="archive" type="file" accept=".zip,application/zip" required />
          </label>
          <label>
            Référence du lot
            <input name="batch_reference" defaultValue="SPORTIGO-INVOICES-2025-2026" required maxLength={120} />
          </label>
          <label className="row gap-sm">
            <input name="dry_run" type="checkbox" defaultChecked /> Prévisualisation uniquement
          </label>
          <label>
            Confirmation d’application
            <input name="confirm_apply" placeholder="Laisser vide en prévisualisation ; sinon recopier la référence du lot" />
          </label>
          <button type="submit">Contrôler / charger les factures</button>
        </form>
      </section>
    </section>
  );
}
