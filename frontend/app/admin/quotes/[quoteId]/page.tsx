import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import CopyLinkButton from "../../../../components/copy-link-button";
import QuoteFollowupSlotForm from "../../../../components/quote-followup-slot-form";
import QuoteLinesEditor from "../../../../components/quote-lines-editor";
import QuotePlanningEditor from "../../../../components/quote-planning-editor";
import {
  changeQuoteFollowupPaymentMethodAction,
  duplicateQuoteAction,
  finalizeQuoteFollowupAction,
  regenerateQuoteDocumentAction,
  selectQuoteFollowupSlotAction,
  sendQuoteAction,
  updateQuoteLinesAction,
  updateQuotePlanningAction,
  updateQuoteSettingsAction,
} from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import type { AdminActivityOut, AdminCatalogKitOut, AdminCatalogProductOut, AdminClientOut, LocationOut } from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

type RouteParams = {
  params: {
    quoteId: string;
  };
  searchParams: SearchParams;
};

type ProspectOut = {
  id: string;
  first_name: string | null;
  last_name: string | null;
  email: string;
};

type QuoteLineOut = {
  id: string;
  line_type: string;
  line_category: string;
  master_item_type: string | null;
  activity_id: string | null;
  product_id: string | null;
  kit_id: string | null;
  title: string;
  quantity: string;
  vat_rate: string;
  unit_price_ht: string;
  unit_vat_amount: string;
  unit_price_ttc: string;
  amount_ht: string;
  amount_vat: string;
  amount_ttc: string;
};

type QuoteOut = {
  id: string;
  quote_number: string;
  status: string;
  context_type: string;
  quote_type_id: string | null;
  pricing_catalog_id: string | null;
  payment_plan_id: string | null;
  quote_template_id: string | null;
  quote_template_version_id: string | null;
  terms_template_id: string | null;
  terms_template_version_id: string | null;
  currency: string;
  language: string | null;
  total_ttc: string;
  expiry_days: number;
  created_at: string;
  expires_at: string | null;
  sent_at: string | null;
  approved_at: string | null;
  prospect_id: string | null;
  client_id: string | null;
  quote_type: string;
  school_year_label: string | null;
  estimated_solfege_level: string | null;
  calendar_snapshot: Record<string, unknown>;
  payment_terms_snapshot: Record<string, unknown>;
  cgv_snapshot: Record<string, unknown>;
  meta: Record<string, unknown>;
  document_status: string;
  document_snapshot_id: string | null;
  document_hash: string | null;
  document_generated_at: string | null;
  public_token: string | null;
  pdf_token: string | null;
};

type QuoteDetailOut = {
  quote: QuoteOut;
  lines: QuoteLineOut[];
};

type QuoteFollowupOut = {
  id: string;
  quote_id: string;
  target_client_id: string | null;
  status: string;
  payment_method_status: string;
  solfege_slot_status: string;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

type PaymentPlanOut = {
  id: string;
  name: string;
  payment_method: string;
};

type QuoteTypeOut = {
  id: string;
  name: string;
};

type PricingCatalogOut = {
  id: string;
  name: string;
};

type CgvVersionOut = {
  id: string;
  version_label: string;
};

type QuoteTemplateOut = {
  id: string;
  code: string;
  name: string;
  language: string;
};

function readParam(params: SearchParams, key: string): string {
  const raw = params[key];
  if (Array.isArray(raw)) {
    return raw[0] ?? "";
  }
  return raw ?? "";
}

function formatDate(value: string | null): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function formatAmount(value: string, currency: string): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) {
    return `${value} ${currency}`;
  }
  try {
    return new Intl.NumberFormat("fr-FR", { style: "currency", currency: currency || "EUR" }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${(currency || "EUR").toUpperCase()}`;
  }
}

function labelForContext(contextType: string): string {
  return contextType === "active_client" ? "Client actif" : "Acquisition";
}

function displayName(firstName: string | null, lastName: string | null, fallback: string): string {
  const value = [firstName, lastName].filter(Boolean).join(" ").trim();
  return value || fallback;
}

function getScheduleItems(snapshot: Record<string, unknown>): Array<Record<string, unknown>> {
  const raw = snapshot.schedule;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter((item): item is Record<string, unknown> => !!item && typeof item === "object");
}

function getCalendarSessions(snapshot: Record<string, unknown>): Array<Record<string, unknown>> {
  const raw = snapshot.sessions;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter((item): item is Record<string, unknown> => !!item && typeof item === "object");
}

const MONTH_LABELS_FR = [
  "Janvier",
  "Fevrier",
  "Mars",
  "Avril",
  "Mai",
  "Juin",
  "Juillet",
  "Aout",
  "Septembre",
  "Octobre",
  "Novembre",
  "Decembre",
];

type PlanningSummaryBlock = {
  key: string;
  title: string;
  count: number;
  semester1: Array<{ monthLabel: string; days: string }>;
  semester2: Array<{ monthLabel: string; days: string }>;
};

function planningVisualSummary(sessions: Array<Record<string, unknown>>): PlanningSummaryBlock[] {
  const grouped = new Map<string, Map<number, number[]>>();
  for (const session of sessions) {
    const dateRaw = String(session.date ?? "").trim();
    const parsed = dateRaw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!parsed) {
      continue;
    }
    const month = Number.parseInt(parsed[2], 10);
    const day = Number.parseInt(parsed[3], 10);
    if (!Number.isFinite(month) || !Number.isFinite(day) || month < 1 || month > 12 || day < 1 || day > 31) {
      continue;
    }
    const activityLabel = String(session.activity_label ?? "").trim() || "Activite";
    const locationLabel = String(session.location_label ?? "").trim();
    const title = locationLabel ? `${activityLabel} · ${locationLabel}` : activityLabel;
    const key = title;
    if (!grouped.has(key)) {
      grouped.set(key, new Map<number, number[]>());
    }
    const monthMap = grouped.get(key)!;
    if (!monthMap.has(month)) {
      monthMap.set(month, []);
    }
    monthMap.get(month)!.push(day);
  }

  const toEntries = (monthMap: Map<number, number[]>, semester: 1 | 2): Array<{ monthLabel: string; days: string }> => {
    const months = Array.from(monthMap.keys()).sort((a, b) => a - b);
    return months
      .filter((month) => (semester === 1 ? month >= 9 || month <= 1 : month >= 2 && month <= 8))
      .map((month) => {
        const days = Array.from(new Set(monthMap.get(month) || [])).sort((a, b) => a - b);
        return {
          monthLabel: MONTH_LABELS_FR[month - 1] || String(month),
          days: days.join(", "),
        };
      });
  };

  return Array.from(grouped.entries()).map(([key, monthMap]) => {
    const count = Array.from(monthMap.values()).reduce((sum, days) => sum + days.length, 0);
    return {
      key,
      title: key,
      count,
      semester1: toEntries(monthMap, 1),
      semester2: toEntries(monthMap, 2),
    };
  });
}

function safeBackPath(raw: string): string {
  const value = raw.trim();
  if (value.startsWith("/admin/quotes")) {
    return value;
  }
  return "/admin/quotes";
}

function readStringMeta(meta: Record<string, unknown>, key: string, fallback = ""): string {
  const raw = meta[key];
  if (typeof raw === "string" && raw.trim()) {
    return raw.trim();
  }
  return fallback;
}

function normalizeLang(value: string | null | undefined): string {
  const normalized = String(value || "").trim().toLowerCase();
  return normalized || "fr";
}

function readObject(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function modalityLabel(value: unknown): string {
  const normalized = String(value ?? "").trim().toUpperCase();
  if (normalized === "ONLINE") {
    return "En ligne";
  }
  if (normalized === "ONSITE") {
    return "Presentiel";
  }
  return normalized || "-";
}

function weekdayLabelFromNumber(value: unknown): string {
  const weekday = Number.parseInt(String(value ?? ""), 10);
  if (weekday === 0) return "Lundi";
  if (weekday === 1) return "Mardi";
  if (weekday === 2) return "Mercredi";
  if (weekday === 3) return "Jeudi";
  if (weekday === 4) return "Vendredi";
  if (weekday === 5) return "Samedi";
  if (weekday === 6) return "Dimanche";
  return "-";
}

function getPlanningBlocks(snapshot: Record<string, unknown>): Array<Record<string, unknown>> {
  const raw = snapshot.blocks;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter((item): item is Record<string, unknown> => !!item && typeof item === "object");
}

function getSelectedSolfegeSlot(meta: Record<string, unknown>, snapshot: Record<string, unknown>): Record<string, unknown> | null {
  const fromMeta = readObject(meta.selected_solfege_slot);
  if (fromMeta) {
    return fromMeta;
  }
  const solfege = readObject(snapshot.solfege);
  if (!solfege) {
    return null;
  }
  return readObject(solfege.selected_slot);
}

function getProposedSolfegeSlots(meta: Record<string, unknown>, snapshot: Record<string, unknown>): Array<{
  key: string;
  label: string;
  start_time: string;
  end_time: string;
}> {
  const fromMeta = meta.proposed_solfege_slots;
  const solfege = readObject(snapshot.solfege);
  const fromSnapshot = solfege?.proposed_slots;
  const raw = Array.isArray(fromMeta) && fromMeta.length > 0
    ? fromMeta
    : Array.isArray(fromSnapshot) ? fromSnapshot : [];
  return raw
    .map((item, index) => {
      const row = readObject(item);
      if (!row) {
        return null;
      }
      const start = String(row.start_time ?? row.start ?? "").trim();
      const end = String(row.end_time ?? row.end ?? "").trim();
      if (!start || !end) {
        return null;
      }
      const weekday = Number.parseInt(String(row.weekday ?? row.day ?? ""), 10);
      const weekdayText = Number.isFinite(weekday) ? weekdayLabelFromNumber(weekday) : "-";
      const modalityText = modalityLabel(row.modality);
      const location = String(row.location_label ?? row.location_name ?? "").trim();
      const suffix = [modalityText !== "-" ? modalityText : "", location].filter(Boolean).join(" · ");
      const label = `${weekdayText} ${start}-${end}${suffix ? ` · ${suffix}` : ""}`;
      return {
        key: `${weekdayText}|${start}|${end}|${index}`,
        label,
        start_time: start,
        end_time: end,
      };
    })
    .filter((row): row is { key: string; label: string; start_time: string; end_time: string } => row !== null);
}

export default async function AdminQuoteDetailPage({ params, searchParams }: RouteParams): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const quoteId = String(params.quoteId || "").trim();
  if (!quoteId) {
    redirect("/admin/quotes?error=Devis%20introuvable");
  }

  const backPath = safeBackPath(readParam(searchParams, "back"));
  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");

  const [detailResult, followupsResult, paymentPlansResult, quoteTypesResult, catalogsResult, cgvVersionsResult, quoteTemplatesResult, activitiesResult, productsResult, kitsResult, locationsResult, prospectsResult, clientsResult] = await Promise.all([
    backendRequest<QuoteDetailOut>(`/api/v1/quotes/${encodeURIComponent(quoteId)}`, {}, token),
    backendRequest<QuoteFollowupOut[]>(`/api/v1/quote-followups?quote_id=${encodeURIComponent(quoteId)}`, {}, token),
    backendRequest<PaymentPlanOut[]>("/api/v1/payment-plans", {}, token),
    backendRequest<QuoteTypeOut[]>("/api/v1/quote-types", {}, token),
    backendRequest<PricingCatalogOut[]>("/api/v1/pricing-catalogs", {}, token),
    backendRequest<CgvVersionOut[]>("/api/v1/cgv-versions", {}, token),
    backendRequest<QuoteTemplateOut[]>("/api/v1/quote-templates?active_only=true", {}, token),
    backendRequest<AdminActivityOut[]>("/api/v1/admin/activities?include_inactive=true", {}, token),
    backendRequest<AdminCatalogProductOut[]>("/api/v1/admin/config/catalog/products?include_inactive=true", {}, token),
    backendRequest<AdminCatalogKitOut[]>("/api/v1/admin/config/catalog/kits?include_inactive=true", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=false", {}, token),
    backendRequest<ProspectOut[]>("/api/v1/prospects?limit=1000", {}, token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?limit=800&include_archived=false", {}, token),
  ]);

  if (!detailResult.ok) {
    return (
      <section className="admin-page-grid">
        <section className="card">
          <h2>Detail devis</h2>
          <p className="flash-err">{detailResult.message}</p>
          <div className="row top-gap-sm">
            <Link className="ghost" href={backPath}>Retour liste devis</Link>
          </div>
        </section>
      </section>
    );
  }

  const detail = detailResult.data;
  const followups = followupsResult.ok ? followupsResult.data : [];
  const activeFollowup = followups[0] ?? null;
  const paymentPlans = paymentPlansResult.ok ? paymentPlansResult.data : [];
  const quoteTypes = quoteTypesResult.ok ? quoteTypesResult.data : [];
  const catalogs = catalogsResult.ok ? catalogsResult.data : [];
  const cgvVersions = cgvVersionsResult.ok ? cgvVersionsResult.data : [];
  const quoteTemplates = quoteTemplatesResult.ok ? quoteTemplatesResult.data : [];
  const activities = activitiesResult.ok ? activitiesResult.data : [];
  const products = productsResult.ok ? productsResult.data : [];
  const kits = kitsResult.ok ? kitsResult.data : [];
  const locations = locationsResult.ok ? locationsResult.data : [];
  const prospects = prospectsResult.ok ? prospectsResult.data : [];
  const clients = clientsResult.ok ? clientsResult.data : [];

  const prospectById = new Map(prospects.map((row) => [row.id, row]));
  const clientById = new Map(clients.map((row) => [row.id, row]));
  const activityById = new Map(activities.map((row) => [row.id, row.name]));
  const locationById = new Map(locations.map((row) => [row.id, row.name]));

  const owner = detail.quote.context_type === "acquisition"
    ? prospectById.get(detail.quote.prospect_id || "")
    : clientById.get(detail.quote.client_id || "");

  const ownerName = owner
    ? displayName(owner.first_name, owner.last_name, owner.email)
    : "-";
  const quoteLanguage = readStringMeta(detail.quote.meta || {}, "language", "fr").toLowerCase();
  const quoteTemplateId = readStringMeta(detail.quote.meta || {}, "template_id");
  const quoteCgvVersionId = readStringMeta(detail.quote.meta || {}, "cgv_version_id") || readStringMeta(detail.quote.cgv_snapshot || {}, "id");
  const calendarSessions = getCalendarSessions(detail.quote.calendar_snapshot || {});
  const planningBlocks = getPlanningBlocks(detail.quote.calendar_snapshot || {});
  const planningSummary = planningVisualSummary(calendarSessions);
  const selectedSolfegeSlot = getSelectedSolfegeSlot(detail.quote.meta || {}, detail.quote.calendar_snapshot || {});
  const proposedSolfegeSlots = getProposedSolfegeSlots(detail.quote.meta || {}, detail.quote.calendar_snapshot || {});
  const activitySolfegeRows = Array.isArray((detail.quote.meta || {}).activity_solfege)
    ? ((detail.quote.meta || {}).activity_solfege as Array<Record<string, unknown>>)
    : [];
  const masterclassRowsMeta = Array.isArray((detail.quote.meta || {}).masterclass_blocks)
    ? ((detail.quote.meta || {}).masterclass_blocks as Array<Record<string, unknown>>)
    : [];
  const masterclassRowsSnapshot = Array.isArray((detail.quote.calendar_snapshot || {}).masterclass_blocks)
    ? ((detail.quote.calendar_snapshot || {}).masterclass_blocks as Array<Record<string, unknown>>)
    : [];
  const masterclassRows = masterclassRowsMeta.length > 0 ? masterclassRowsMeta : masterclassRowsSnapshot;
  const languageQuoteTemplates = quoteTemplates.filter((row) => normalizeLang(row.language) === normalizeLang(quoteLanguage));
  const selectedTemplate = quoteTemplates.find((row) => row.id === quoteTemplateId);
  const templateOptions = (() => {
    if (!selectedTemplate) {
      return languageQuoteTemplates;
    }
    if (languageQuoteTemplates.some((row) => row.id === selectedTemplate.id)) {
      return languageQuoteTemplates;
    }
    return [selectedTemplate, ...languageQuoteTemplates];
  })();
  const cgvOptions = (() => {
    if (!quoteCgvVersionId) {
      return cgvVersions;
    }
    if (cgvVersions.some((row) => row.id === quoteCgvVersionId)) {
      return cgvVersions;
    }
    return [
      { id: quoteCgvVersionId, version_label: String(detail.quote.cgv_snapshot?.version_label || "Snapshot actuel") },
      ...cgvVersions,
    ];
  })();

  const selfPath = `/admin/quotes/${encodeURIComponent(detail.quote.id)}?back=${encodeURIComponent(backPath)}`;

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>Devis {detail.quote.quote_number}</h2>
            <p className="muted">
              {labelForContext(detail.quote.context_type)} · {detail.quote.status} · {formatAmount(detail.quote.total_ttc, detail.quote.currency)}
            </p>
            <p className="muted">Destinataire: {ownerName}</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href={backPath}>Retour liste devis</Link>
            <Link className="ghost" href="/admin/quotes/new">Nouveau devis</Link>
          </div>
        </div>
      </section>

      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}

      <section className="card">
        <h3>Actions</h3>
        <div className="row wrap gap-sm top-gap-sm">
          {detail.quote.status === "created" ? (
            <form action={sendQuoteAction} className="row wrap gap-sm">
              <input type="hidden" name="quote_id" value={detail.quote.id} />
              <input type="hidden" name="return_to" value={selfPath} />
              <input type="email" name="recipient_email" placeholder="Email destinataire (optionnel)" />
              <button type="submit">Envoyer le devis</button>
            </form>
          ) : null}

          <form action={duplicateQuoteAction}>
            <input type="hidden" name="quote_id" value={detail.quote.id} />
            <input type="hidden" name="return_to" value={selfPath} />
            <button type="submit" className="ghost">Dupliquer en nouvelle version</button>
          </form>

          {detail.quote.public_token ? (
            <>
              <Link
                className="ghost"
                href={`/q/${detail.quote.id}?t=${encodeURIComponent(detail.quote.public_token)}`}
                target="_blank"
              >
                Ouvrir page publique
              </Link>
              <CopyLinkButton
                value={`${process.env.NEXT_PUBLIC_FRONTEND_URL ?? "http://localhost:3000"}/q/${detail.quote.id}?t=${detail.quote.public_token}`}
                label="Copier lien public"
              />
            </>
          ) : (
            <small className="muted">Le lien public sera disponible apres envoi.</small>
          )}

          {detail.quote.pdf_token ? (
            <Link
              className="ghost"
              href={`/q/${detail.quote.id}/pdf?t=${encodeURIComponent(detail.quote.pdf_token)}`}
              target="_blank"
            >
              PDF public
            </Link>
          ) : null}
          <Link className="ghost" href={`/admin/quotes/${detail.quote.id}/pdf`} target="_blank">
            PDF admin
          </Link>
          <form action={regenerateQuoteDocumentAction}>
            <input type="hidden" name="quote_id" value={detail.quote.id} />
            <input type="hidden" name="return_to" value={selfPath} />
            <button type="submit" className="ghost" disabled={detail.quote.status !== "created"}>
              Regenerer document
            </button>
          </form>
          {detail.quote.status !== "created" ? (
            <small className="muted">Regeneration reservee au brouillon.</small>
          ) : null}
        </div>
      </section>

      <section className="card">
        <h3>Parametres du devis</h3>
        <p className="muted">Devise, langue, templates, CGV et referentiels metier du devis.</p>
        <form action={updateQuoteSettingsAction} className="grid cols-3 config-form-grid top-gap-sm">
          <input type="hidden" name="quote_id" value={detail.quote.id} />
          <input type="hidden" name="return_to" value={selfPath} />
          <input type="hidden" name="current_meta_json" value={JSON.stringify(detail.quote.meta || {})} />
          <label>
            Type devis
            <select name="quote_type_id" defaultValue={detail.quote.quote_type_id || ""} disabled={detail.quote.status !== "created"}>
              <option value="">Aucun</option>
              {quoteTypes.map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
            </select>
          </label>
          <label>
            Catalogue prix
            <select name="pricing_catalog_id" defaultValue={detail.quote.pricing_catalog_id || ""} disabled={detail.quote.status !== "created"}>
              <option value="">Aucun</option>
              {catalogs.map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
            </select>
          </label>
          <label>
            Plan paiement
            <select name="payment_plan_id" defaultValue={detail.quote.payment_plan_id || ""} disabled={detail.quote.status !== "created"}>
              <option value="">Aucun</option>
              {paymentPlans.map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
            </select>
          </label>
          <label>
            Template
            <select name="quote_template_id" defaultValue={quoteTemplateId} disabled={detail.quote.status !== "created"}>
              <option value="">Aucun</option>
              {templateOptions.map((row) => (
                <option key={row.id} value={row.id}>{row.name} ({row.code})</option>
              ))}
            </select>
          </label>
          <label>
            CGV
            <select name="cgv_version_id" defaultValue={quoteCgvVersionId} disabled={detail.quote.status !== "created"}>
              <option value="">Conserver snapshot actuel</option>
              {cgvOptions.map((row) => (
                <option key={row.id} value={row.id}>{row.version_label}</option>
              ))}
            </select>
          </label>
          <label>
            Langue
            <select name="language" defaultValue={quoteLanguage} disabled={detail.quote.status !== "created"}>
              <option value="fr">Francais</option>
              <option value="en">English</option>
            </select>
          </label>
          <label>
            Devise
            <select name="currency" defaultValue={detail.quote.currency || "EUR"} disabled={detail.quote.status !== "created"}>
              <option value="EUR">EUR</option>
              <option value="USD">USD</option>
              <option value="GBP">GBP</option>
            </select>
          </label>
          <label>
            Delai expiration (jours)
            <input type="number" name="expiry_days" min={1} max={120} defaultValue={detail.quote.expiry_days} disabled={detail.quote.status !== "created"} />
          </label>
          <label>
            Annee scolaire
            <input type="text" name="school_year_label" defaultValue={detail.quote.school_year_label ?? ""} disabled={detail.quote.status !== "created"} />
          </label>
          <div className="row span-3 top-gap-sm">
            <button type="submit" disabled={detail.quote.status !== "created"}>Enregistrer parametres</button>
            {detail.quote.status !== "created" ? <small className="muted">Le devis est immuable apres envoi.</small> : null}
          </div>
        </form>
        <p className="muted top-gap-sm">
          CGV snapshot active: <strong>{String(detail.quote.cgv_snapshot?.version_label || "-")}</strong>
        </p>
        <p className="muted">
          Templates affiches pour la langue: <strong>{quoteLanguage.toUpperCase()}</strong>
        </p>
        <p className="muted">
          Statut document: <strong>{detail.quote.document_status || "stale"}</strong>
          {" · "}
          Genere le: <strong>{formatDate(detail.quote.document_generated_at)}</strong>
        </p>
        <p className="muted">
          Hash document: <strong>{detail.quote.document_hash || "-"}</strong>
        </p>
      </section>

      <section className="card">
        <h3>Infos devis</h3>
        <div className="grid cols-3 top-gap-sm">
          <p><strong>Type:</strong> {detail.quote.quote_type}</p>
          <p><strong>Annee scolaire:</strong> {detail.quote.school_year_label ?? "-"}</p>
          <p><strong>Creation:</strong> {formatDate(detail.quote.created_at)}</p>
          <p><strong>Envoi:</strong> {formatDate(detail.quote.sent_at)}</p>
          <p><strong>Expiration:</strong> {formatDate(detail.quote.expires_at)}</p>
          <p><strong>Solfege:</strong> {selectedSolfegeSlot ? "Configure (voir section dediee)" : "Non configure"}</p>
        </div>
      </section>

      <section className="card">
        <h3>Selection solfege</h3>
        {selectedSolfegeSlot ? (
          <div className="grid cols-3 top-gap-sm">
            <p><strong>Jour:</strong> {weekdayLabelFromNumber(selectedSolfegeSlot.weekday)}</p>
            <p><strong>Horaire:</strong> {String(selectedSolfegeSlot.start_time ?? "--:--")} - {String(selectedSolfegeSlot.end_time ?? "--:--")}</p>
            <p><strong>Duree:</strong> {String(selectedSolfegeSlot.duration_minutes ?? "-")} min</p>
            <p><strong>Modalite:</strong> {modalityLabel(selectedSolfegeSlot.modality)}</p>
            <p><strong>Lieu:</strong> {String(selectedSolfegeSlot.location_label ?? locationById.get(String(selectedSolfegeSlot.location_id ?? "")) ?? "-")}</p>
            <p><strong>Libelle:</strong> {String(selectedSolfegeSlot.label ?? "-")}</p>
          </div>
        ) : (
          <p className="muted">Aucun creneau solfege selectionne sur ce devis.</p>
        )}
      </section>

      <section className="card">
        <h3>Solfege et masterclass par activite</h3>
        <div className="list top-gap-sm">
          {activitySolfegeRows.length === 0 ? (
            <p className="muted">Aucune activite avec solfege configuree.</p>
          ) : (
            activitySolfegeRows.map((row, index) => (
              <article key={`activity-solfege-${index}`} className="item">
                <div className="row spread wrap gap-sm">
                  <strong>{String(row.activity_label || activityById.get(String(row.activity_id || "")) || "Activite")}</strong>
                  <span className="badge">Niveau {String(row.level || "-")}</span>
                </div>
                <p className="muted">
                  Demarrage: {String(row.start_date || "-")}
                  {" · "}
                  Creneau: {String(readObject(row.slot)?.label || "-")}
                </p>
              </article>
            ))
          )}
          {masterclassRows.length === 0 ? (
            <p className="muted">Aucune masterclass configuree.</p>
          ) : (
            masterclassRows.map((row, index) => (
              <article key={`masterclass-${index}`} className="item">
                <div className="row spread wrap gap-sm">
                  <strong>{String(row.activity_label || activityById.get(String(row.activity_id || "")) || "Masterclass samedi")}</strong>
                  <span className="badge">Masterclass</span>
                </div>
                <p className="muted">
                  Session: {String(row.session || "-")}
                  {" · "}
                  Local: {String(row.location_label || locationById.get(String(row.location_id || "")) || "-")}
                </p>
              </article>
            ))
          )}
        </div>
      </section>

      <section className="card">
        <h3>Calendrier previsionnel</h3>
        <p className="muted">{calendarSessions.length} seances calculees.</p>
        {planningSummary.length > 0 ? (
          <div className="list top-gap-sm">
            {planningSummary.map((block) => (
              <article key={block.key} className="item">
                <div className="row spread wrap gap-sm">
                  <strong>{block.title}</strong>
                  <span className="badge">{block.count} cours</span>
                </div>
                <div className="grid cols-2 top-gap-sm">
                  <div>
                    <p><strong>1er semestre</strong></p>
                    {block.semester1.length === 0 ? <p className="muted">Aucune seance</p> : null}
                    {block.semester1.map((item) => (
                      <p key={`${block.key}-s1-${item.monthLabel}`} className="muted">{item.monthLabel}: {item.days}</p>
                    ))}
                  </div>
                  <div>
                    <p><strong>2e semestre</strong></p>
                    {block.semester2.length === 0 ? <p className="muted">Aucune seance</p> : null}
                    {block.semester2.map((item) => (
                      <p key={`${block.key}-s2-${item.monthLabel}`} className="muted">{item.monthLabel}: {item.days}</p>
                    ))}
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : null}
        <div className="top-gap-sm">
          <QuotePlanningEditor
            quoteId={detail.quote.id}
            returnTo={selfPath}
            editable={detail.quote.status === "created"}
            schoolYearLabel={detail.quote.school_year_label}
            activities={activities.map((row) => ({
              id: row.id,
              name: row.name,
              duration_minutes: row.duration_minutes,
            }))}
            locations={locations.map((row) => ({
              id: row.id,
              name: row.name,
            }))}
            initialSnapshot={detail.quote.calendar_snapshot}
            saveAction={updateQuotePlanningAction}
          />
        </div>
        {planningBlocks.length > 0 ? (
          <div className="quote-public-lines top-gap-sm">
            {planningBlocks.map((block, index) => (
              <article key={`block-${index}`} className="quote-public-line-item">
                <strong>{String(block.activity_label ?? activityById.get(String(block.activity_id ?? "")) ?? "Activite")}</strong>
                <span>
                  {weekdayLabelFromNumber(block.weekday)} · {String(block.start_time ?? "--:--")} - {String(block.end_time ?? "--:--")}
                </span>
                <small className="muted">
                  {String(block.start_date ?? "-")} → {String(block.end_date ?? "-")}
                  {" · "}
                  {String(block.location_label ?? locationById.get(String(block.location_id ?? "")) ?? "Lieu non defini")}
                  {" · "}
                  Calendrier: {String(block.calendar_name ?? "Par defaut")}
                </small>
              </article>
            ))}
          </div>
        ) : null}
        <div className="quote-public-lines top-gap-sm">
          {calendarSessions.slice(0, 20).map((session, index) => (
            <article key={`session-${index}`} className="quote-public-line-item">
              <strong>{String(session.date ?? "-")}</strong>
              <span>{String(session.start_time ?? "--:--")} - {String(session.end_time ?? "--:--")}</span>
              <small className="muted">
                {String(session.activity_label ?? activityById.get(String(session.activity_id ?? "")) ?? "Activite")}
                {" · "}
                {String(session.location_label ?? locationById.get(String(session.location_id ?? "")) ?? "Lieu non defini")}
                {" · "}
                {modalityLabel(session.modality)}
              </small>
            </article>
          ))}
        </div>
      </section>

      <section className="card">
        <h3>Lignes du devis</h3>
        <QuoteLinesEditor
          quoteId={detail.quote.id}
          returnTo={selfPath}
          editable={detail.quote.status === "created"}
          currency={detail.quote.currency}
          initialLines={detail.lines}
          activities={activities.map((row) => ({
            id: row.id,
            name: row.name,
            duration_minutes: row.duration_minutes,
            default_course_rate_ttc: row.default_course_rate_ttc,
          }))}
          products={products.map((row) => ({
            id: row.id,
            title: row.title,
            price_incl_vat: row.price_incl_vat,
            vat_rate: row.vat_rate,
          }))}
          kits={kits.map((row) => ({
            id: row.id,
            title: row.title,
            effective_price_ttc: row.price_effective_incl_vat,
            vat_rate: row.vat_rate,
          }))}
          saveAction={updateQuoteLinesAction}
        />
      </section>

      <section className="card">
        <h3>Parcours post-approbation</h3>
        {activeFollowup ? (
          <>
            <p className="muted">
              Statut follow-up: <strong>{activeFollowup.status}</strong> · Paiement: <strong>{activeFollowup.payment_method_status}</strong> · Solfege: <strong>{activeFollowup.solfege_slot_status}</strong>
            </p>

            <div className="grid cols-2 top-gap-sm">
              <QuoteFollowupSlotForm
                followupId={activeFollowup.id}
                returnTo={selfPath}
                proposedSlots={proposedSolfegeSlots}
                submitAction={selectQuoteFollowupSlotAction}
              />

              <form action={changeQuoteFollowupPaymentMethodAction} className="card quote-followup-form">
                <h4>Changer le mode de paiement</h4>
                <input type="hidden" name="followup_id" value={activeFollowup.id} />
                <input type="hidden" name="return_to" value={selfPath} />
                <label>
                  Methode
                  <select name="payment_method_code" required>
                    <option value="">Selectionner</option>
                    {Array.from(new Set(paymentPlans.map((row) => row.payment_method))).map((method) => (
                      <option key={method} value={method}>{method}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Plan de paiement (optionnel)
                  <select name="payment_plan_id" defaultValue="">
                    <option value="">Aucun</option>
                    {paymentPlans.map((row) => (
                      <option key={row.id} value={row.id}>{row.name}</option>
                    ))}
                  </select>
                </label>
                <button type="submit">Mettre a jour paiement</button>
              </form>
            </div>

            <form action={finalizeQuoteFollowupAction} className="row top-gap-sm">
              <input type="hidden" name="followup_id" value={activeFollowup.id} />
              <input type="hidden" name="return_to" value={selfPath} />
              <button type="submit">Finaliser le parcours post-approbation</button>
            </form>
          </>
        ) : (
          <p className="muted">Aucun follow-up actif pour ce devis. Il sera cree automatiquement apres approbation du devis.</p>
        )}
      </section>

      <section className="card">
        <h3>Echeancier snapshot</h3>
        <div className="quote-public-lines top-gap-sm">
          {getScheduleItems(detail.quote.payment_terms_snapshot).length === 0 ? (
            <p className="muted">Aucun echeancier.</p>
          ) : (
            getScheduleItems(detail.quote.payment_terms_snapshot).map((item, index) => (
              <article key={`schedule-${index}`} className="quote-public-line-item">
                <strong>{String(item.label ?? `Echeance ${index + 1}`)}</strong>
                <span>{String(item.due_label ?? item.due_type ?? "-")}</span>
                <small>{String(item.amount_ttc ?? "0")} {detail.quote.currency}</small>
              </article>
            ))
          )}
        </div>
      </section>
    </section>
  );
}
