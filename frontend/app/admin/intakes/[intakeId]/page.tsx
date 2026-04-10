import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  generateTypeformDraftQuoteAction,
  reanalyzeTypeformIntakeAction,
  saveTypeformIntakeNormalizedDataAction,
  saveTypeformIntakeResolutionAction,
} from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import ConfirmSubmitButton from "../../../../components/confirm-submit-button";
import styles from "../typeform-intakes.module.css";

type SearchParams = Record<string, string | string[] | undefined>;

type RouteParams = {
  params: {
    intakeId: string;
  };
  searchParams: SearchParams;
};

type TypeformAnswerOut = {
  key: string;
  label: string;
  value: string;
};

type TypeformMatchCandidateOut = {
  kind: string;
  client_id: string | null;
  adult_client_id: string | null;
  child_client_id: string | null;
  billing_client_id: string | null;
  display_name: string;
  subtitle: string | null;
  confidence: number;
  confidence_label: string;
  reasons: string[];
};

type TypeformSessionMatchOptionOut = {
  session_id: string;
  activity_id: string;
  activity_name: string;
  location_id: string;
  location_name: string;
  title: string;
  start_at: string;
  start_time_label: string;
  end_time_label: string;
  weekday_label: string;
  occurrence_label: string;
  selection_label: string;
  recurrence_group_id: string | null;
  recurrence_label: string | null;
  seats_remaining: number;
  is_full: boolean;
  score: number;
  reasons: string[];
};

type TypeformSessionRecommendationOut = {
  activity_id: string;
  activity_name: string;
  requested_location: string | null;
  requested_summary: string | null;
  summary_status: string;
  summary_label: string;
  selected_session_id: string | null;
  options: TypeformSessionMatchOptionOut[];
  manual_options: TypeformSessionMatchOptionOut[];
  warnings: string[];
  blockages: string[];
};

type TypeformQuotePreviewLineOut = {
  title: string;
  description: string | null;
  pricing_unit: string;
  quantity: string;
  unit_price_ttc: string;
  amount_ttc: string;
  vat_rate: string;
  meta: Record<string, unknown>;
};

type TypeformQuotePreviewOut = {
  context_type: string;
  context_label: string;
  customer_label: string;
  location_name: string | null;
  payment_plan_name: string | null;
  quote_type_name: string | null;
  pricing_catalog_name: string | null;
  legal_entity_name: string | null;
  school_year_label: string | null;
  language: string | null;
  currency: string;
  selected_options: string[];
  lines: TypeformQuotePreviewLineOut[];
  total_ht: string;
  total_vat: string;
  total_ttc: string;
};

type TypeformFormConfigOut = {
  id: string;
  source_code: string;
  location_code: string;
  school_year_label: string;
  audience_segment: string;
};

type TypeformIntakeDetailOut = {
  id: string;
  source_form_id: string;
  source_form_label: string;
  source_response_id: string;
  received_at: string;
  intake_status: string;
  detected_location: string | null;
  detected_segment: string | null;
  detected_school_year: string | null;
  raw_payload_json: Record<string, unknown>;
  normalized_payload_json: Record<string, unknown>;
  answers: TypeformAnswerOut[];
  warnings: string[];
  blockages: string[];
  resolution: Record<string, unknown>;
  client_candidates: TypeformMatchCandidateOut[];
  session_recommendations: TypeformSessionRecommendationOut[];
  preview_quote: TypeformQuotePreviewOut | null;
  related_quote_id: string | null;
  form_config: TypeformFormConfigOut | null;
};

function isNoRelevantSlotBlockage(message: string): boolean {
  return String(message || "").trim().toLowerCase().startsWith("aucun creneau pertinent trouve pour");
}

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatDate(value: string): string {
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

function statusLabel(value: string): string {
  if (value === "NEW") return "Nouveau";
  if (value === "NORMALIZED") return "Normalise";
  if (value === "MATCHING_REQUIRED") return "Matching requis";
  if (value === "READY_FOR_DRAFT_QUOTE") return "Pret devis";
  if (value === "BLOCKED") return "Bloque";
  if (value === "PROCESSED") return "Traite";
  if (value === "IGNORED") return "Ignore";
  return value;
}

function statusClass(value: string): string {
  if (value === "READY_FOR_DRAFT_QUOTE" || value === "PROCESSED") return "status-ok";
  if (value === "MATCHING_REQUIRED" || value === "NEW" || value === "NORMALIZED") return "status-warn";
  return "status-off";
}

function segmentLabel(value: string | null): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "eveil") return "Eveil";
  if (normalized === "child") return "Enfants";
  if (normalized === "teen") return "Ados";
  if (normalized === "adult") return "Adultes";
  return value || "-";
}

function stringifyValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (Array.isArray(value)) {
    return value.map((item) => stringifyValue(item)).join(", ");
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

const NORMALIZED_FIELD_LABELS: Record<string, string> = {
  parent_first_name: "Prenom parent",
  parent_last_name: "Nom parent",
  parent_email: "Email parent",
  parent_phone: "Telephone parent",
  parent_address_line_1: "Adresse",
  parent_address_line_2: "Complement adresse",
  parent_city: "Ville",
  parent_postal_code: "Code postal",
  parent_country: "Pays",
  parent_address: "Adresse complete",
  child_first_name: "Prenom enfant",
  child_last_name: "Nom enfant",
  child_birth_date: "Date de naissance enfant",
  customer_type: "Type client",
  requested_course_mode: "Mode de cours",
  requested_location: "Lieu souhaite",
  requested_days: "Jours souhaites",
  requested_times: "Horaires souhaites",
  requested_slot_preferences: "Preferences de creneaux",
  requested_formula_type: "Formule souhaitee",
  requested_payment_method: "Mode de reglement souhaite",
  requested_products: "Produits souhaites",
  notes: "Commentaires",
};

function normalizedEntries(payload: Record<string, unknown>): Array<{ key: string; value: string }> {
  return Object.entries(payload).map(([key, value]) => ({
    key: NORMALIZED_FIELD_LABELS[key] || key,
    value: stringifyValue(value),
  }));
}

function setDetailQueryParam(path: string, key: string, value: string | null): string {
  const [pathname, rawSearch = ""] = path.split("?");
  const params = new URLSearchParams(rawSearch);
  if (value === null || value === "") {
    params.delete(key);
  } else {
    params.set(key, value);
  }
  const nextSearch = params.toString();
  return nextSearch ? `${pathname}?${nextSearch}` : pathname;
}

function normalizedScalarValue(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "";
}

function normalizedListValue(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  if (Array.isArray(value)) {
    return value
      .map((item) => String(item ?? "").trim())
      .filter((item) => item.length > 0)
      .join("\n");
  }
  if (typeof value === "string") {
    return value;
  }
  return "";
}

function proposalLabel(index: number): string {
  return `Proposition ${index + 1}`;
}

function manualProposalLabel(index: number): string {
  return `Manuel ${index + 1}`;
}

function slotBadgeLabel(option: TypeformSessionMatchOptionOut): string {
  return option.recurrence_label || "Ponctuel";
}

function slotOptionTitle(option: TypeformSessionMatchOptionOut): string {
  if (option.title && option.title !== option.activity_name) {
    return option.title;
  }
  return option.activity_name;
}

function resolutionObject(detail: TypeformIntakeDetailOut): {
  clientMode: string;
  selectedClientId: string;
  selectedFamilyAdultClientId: string;
  selectedFamilyChildClientId: string;
  selectedFamilyBillingClientId: string;
  notes: string;
} {
  const resolution = detail.resolution || {};
  const clientResolution = (resolution.client_resolution || {}) as Record<string, unknown>;
  return {
    clientMode: String(clientResolution.mode || "new_adult_prospect"),
    selectedClientId: String(clientResolution.selected_client_id || ""),
    selectedFamilyAdultClientId: String(clientResolution.selected_family_adult_client_id || ""),
    selectedFamilyChildClientId: String(clientResolution.selected_family_child_client_id || ""),
    selectedFamilyBillingClientId: String(clientResolution.selected_family_billing_client_id || ""),
    notes: String(resolution.notes || ""),
  };
}

function confidencePillClass(label: string): string {
  if (label === "fort") return "status-ok";
  if (label === "moyen") return "status-warn";
  return "status-off";
}

function clientModeLabel(mode: string): string {
  if (mode === "existing_client") return "Rattacher a un client existant";
  if (mode === "existing_family") return "Rattacher a une famille existante";
  if (mode === "new_parent_child_prospect") return "Creer parent + enfant";
  return "Creer un nouveau prospect adulte";
}

export default async function AdminTypeformIntakeDetailPage({ params, searchParams }: RouteParams): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const intakeId = String(params.intakeId || "").trim();
  if (!intakeId) {
    redirect("/admin/intakes?error=Intake%20introuvable");
  }

  const ok = readParam(searchParams, "ok").trim();
  const error = readParam(searchParams, "error").trim();
  const successModal = readParam(searchParams, "success_modal").trim();
  const editor = readParam(searchParams, "editor").trim();
  const editorError = readParam(searchParams, "editor_error").trim();
  const result = await backendRequest<TypeformIntakeDetailOut>(
    `/api/v1/typeform/intakes/${encodeURIComponent(intakeId)}`,
    {},
    token,
  );
  if (!result.ok) {
    redirect(`/admin/intakes?error=${encodeURIComponent(result.message)}`);
  }

  const detail = result.data;
  const backHref = "/admin/intakes";
  const resolution = resolutionObject(detail);
  const familyCandidates = detail.client_candidates.filter((item) => item.kind === "family");
  const clientCandidates = detail.client_candidates.filter((item) => item.kind === "client");
  const intakeHref = `/admin/intakes/${encodeURIComponent(detail.id)}`;
  const normalizedEditorHref = setDetailQueryParam(setDetailQueryParam(setDetailQueryParam(intakeHref, "error", null), "ok", null), "editor", "normalized");
  const closeNormalizedEditorHref = setDetailQueryParam(setDetailQueryParam(intakeHref, "editor", null), "editor_error", null);
  const dismissErrorHref = setDetailQueryParam(intakeHref, "error", null);
  const dismissSuccessHref = setDetailQueryParam(
    setDetailQueryParam(intakeHref, "success_modal", null),
    "ok",
    null,
  );
  const showErrorModal = Boolean(error) && editor !== "normalized";
  const showResolutionSavedModal = successModal === "resolution_saved" && Boolean(ok);
  const normalizedPayload = detail.normalized_payload_json || {};
  const draftQuoteNeedsArbitrage = detail.intake_status === "MATCHING_REQUIRED";
  const canCreateDraftWithoutActivities =
    detail.intake_status === "BLOCKED"
    && !detail.related_quote_id
    && detail.blockages.length > 0
    && detail.blockages.every(isNoRelevantSlotBlockage)
    && Boolean(detail.preview_quote && detail.preview_quote.lines.length > 0);
  const draftQuoteBlocked =
    Boolean(detail.related_quote_id)
    || (detail.blockages.length > 0 && !canCreateDraftWithoutActivities)
    || draftQuoteNeedsArbitrage
    || detail.intake_status === "IGNORED";
  const resolutionFormId = `intake-resolution-form-${detail.id}`;
  const draftQuoteFormId = `draft-quote-form-${detail.id}`;

  return (
    <section className="admin-page-grid">
      {showResolutionSavedModal ? (
        <section className="modal-overlay" role="dialog" aria-modal="true" aria-label="Arbitrage enregistre">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={dismissSuccessHref} aria-label="Fermer">
              ×
            </Link>
            <h3 className="modal-title">Arbitrage enregistre</h3>
            <section className="flash-ok modal-flash" role="status">
              {ok}
            </section>
            <p className="muted">
              Les creneaux retenus ont bien ete sauvegardes pour cet intake.
            </p>
            <div className="row modal-actions-end top-gap-sm">
              <Link href={dismissSuccessHref}>Fermer</Link>
            </div>
          </article>
        </section>
      ) : null}

      {showErrorModal ? (
        <section className="modal-overlay" role="dialog" aria-modal="true" aria-label="Generation du devis impossible">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={dismissErrorHref} aria-label="Fermer">
              ×
            </Link>
            <h3 className="modal-title">Generation du devis impossible</h3>
            <section className="flash-err modal-flash" role="alert">
              {error}
            </section>
            <p className="muted">
              Corrigez les donnees normalisees si le questionnaire est incomplet, puis relancez la generation du devis.
            </p>
            <div className="row modal-actions-end top-gap-sm">
              <Link className="ghost" href={dismissErrorHref}>Fermer</Link>
              <Link href={normalizedEditorHref}>Corriger les donnees</Link>
            </div>
          </article>
        </section>
      ) : null}

      {editor === "normalized" ? (
        <section className="modal-overlay" role="dialog" aria-modal="true" aria-label="Corriger les donnees normalisees">
          <article className="modal-panel modal-panel-wide">
            <Link className="modal-close-x" href={closeNormalizedEditorHref} aria-label="Fermer">
              ×
            </Link>
            <h3 className="modal-title">Corriger les donnees normalisees</h3>
            <p className={styles.editorIntro}>
              Utilisez cette correction manuelle si le questionnaire est incomplet ou si vous devez forcer une valeur
              avant de generer le devis brouillon.
            </p>
            <form action={saveTypeformIntakeNormalizedDataAction} className={styles.editorForm}>
              <input type="hidden" name="intake_id" value={detail.id} />
              <input type="hidden" name="return_to" value={intakeHref} />

              {editorError ? (
                <section className="flash-err modal-flash" role="alert">
                  {editorError}
                </section>
              ) : null}

              <div className={styles.editorGrid}>
                <section className={styles.editorSection}>
                  <h4>Parent / adulte</h4>
                  <label>
                    Prenom
                    <input name="parent_first_name" defaultValue={normalizedScalarValue(normalizedPayload, "parent_first_name")} />
                  </label>
                  <label>
                    Nom
                    <input name="parent_last_name" defaultValue={normalizedScalarValue(normalizedPayload, "parent_last_name")} />
                  </label>
                  <label>
                    Email
                    <input
                      name="parent_email"
                      type="email"
                      defaultValue={normalizedScalarValue(normalizedPayload, "parent_email")}
                      placeholder="parent@example.com"
                    />
                  </label>
                  <label>
                    Telephone
                    <input name="parent_phone" defaultValue={normalizedScalarValue(normalizedPayload, "parent_phone")} />
                  </label>
                </section>

                <section className={styles.editorSection}>
                  <h4>Enfant / client</h4>
                  <label>
                    Type client
                    <select name="customer_type" defaultValue={normalizedScalarValue(normalizedPayload, "customer_type") || "child"}>
                      <option value="child">Enfant</option>
                      <option value="adult">Adulte</option>
                    </select>
                  </label>
                  <label>
                    Prenom enfant
                    <input name="child_first_name" defaultValue={normalizedScalarValue(normalizedPayload, "child_first_name")} />
                  </label>
                  <label>
                    Nom enfant
                    <input name="child_last_name" defaultValue={normalizedScalarValue(normalizedPayload, "child_last_name")} />
                  </label>
                  <label>
                    Date de naissance
                    <input name="child_birth_date" type="date" defaultValue={normalizedScalarValue(normalizedPayload, "child_birth_date")} />
                  </label>
                </section>

                <section className={styles.editorSection}>
                  <h4>Demande</h4>
                  <label>
                    Lieu demande
                    <input name="requested_location" defaultValue={normalizedScalarValue(normalizedPayload, "requested_location")} />
                  </label>
                  <label>
                    Mode de cours
                    <input name="requested_course_mode" defaultValue={normalizedScalarValue(normalizedPayload, "requested_course_mode")} />
                  </label>
                  <label>
                    Formule
                    <input name="requested_formula_type" defaultValue={normalizedScalarValue(normalizedPayload, "requested_formula_type")} />
                  </label>
                </section>

                <section className={styles.editorSection}>
                  <h4>Preferences creneaux</h4>
                  <label>
                    Jours demandes
                    <textarea
                      name="requested_days"
                      defaultValue={normalizedListValue(normalizedPayload, "requested_days")}
                      rows={4}
                      placeholder="Un jour par ligne"
                    />
                  </label>
                  <label>
                    Horaires demandes
                    <textarea
                      name="requested_times"
                      defaultValue={normalizedListValue(normalizedPayload, "requested_times")}
                      rows={4}
                      placeholder="Un horaire par ligne"
                    />
                  </label>
                  <label>
                    Preferences de creneaux
                    <textarea
                      name="requested_slot_preferences"
                      defaultValue={normalizedListValue(normalizedPayload, "requested_slot_preferences")}
                      rows={5}
                      placeholder="Une preference par ligne"
                    />
                  </label>
                </section>

                <section className={`${styles.editorSection} ${styles.editorSectionWide}`}>
                  <h4>Produits et notes</h4>
                  <label>
                    Produits demandes
                    <textarea
                      name="requested_products"
                      defaultValue={normalizedListValue(normalizedPayload, "requested_products")}
                      rows={4}
                      placeholder="Un produit ou une option par ligne"
                    />
                  </label>
                  <label>
                    Notes
                    <textarea
                      name="notes"
                      defaultValue={normalizedScalarValue(normalizedPayload, "notes")}
                      rows={5}
                      placeholder="Commentaires internes ou precision admin"
                    />
                  </label>
                </section>
              </div>

              <div className="row modal-actions-end top-gap-sm">
                <Link className="ghost" href={closeNormalizedEditorHref}>Annuler</Link>
                <button type="submit">Enregistrer les corrections</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <div className="row wrap gap-sm">
              <span className={`status-pill ${statusClass(detail.intake_status)}`}>{statusLabel(detail.intake_status)}</span>
              <span className="badge">{detail.source_form_label}</span>
            </div>
            <h2 className="top-gap-sm">Intake Typeform</h2>
            <p className="muted">
              Reponse {detail.source_response_id} recue le {formatDate(detail.received_at)}.
            </p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href={backHref}>Retour inbox</Link>
            {detail.related_quote_id ? (
              <Link className="ghost" href={`/admin/quotes/${encodeURIComponent(detail.related_quote_id)}`}>Ouvrir devis</Link>
            ) : null}
          </div>
        </div>
      </section>

      {ok && !showResolutionSavedModal ? <section className="flash-ok">{ok}</section> : null}

      <section className={`grid cols-2 ${styles.panelGrid}`}>
        <article className="card">
          <h3>Resume intake</h3>
          <div className={`${styles.kvGrid} top-gap-sm`}>
            <div><strong>Formulaire</strong><p className="muted">{detail.source_form_id}</p></div>
            <div><strong>Source code</strong><p className="muted">{detail.form_config?.source_code || "-"}</p></div>
            <div><strong>Site</strong><p className="muted">{detail.detected_location || "-"}</p></div>
            <div><strong>Segment</strong><p className="muted">{segmentLabel(detail.detected_segment)}</p></div>
            <div><strong>Annee scolaire</strong><p className="muted">{detail.detected_school_year || "-"}</p></div>
            <div><strong>Mode client actuel</strong><p className="muted">{clientModeLabel(resolution.clientMode)}</p></div>
          </div>
        </article>

        <article className="card">
          <h3>Warnings et blocages</h3>
          <div className="top-gap-sm">
            <p><strong>Warnings</strong></p>
            {detail.warnings.length === 0 ? <p className="muted">Aucun warning.</p> : (
              <ul className={styles.messageList}>
                {detail.warnings.map((message) => <li key={message}>{message}</li>)}
              </ul>
            )}
            <p className="top-gap-sm"><strong>Blocages</strong></p>
            {detail.blockages.length === 0 ? <p className="muted">Aucun blocage.</p> : (
              <ul className={`${styles.messageList} ${styles.messageListBlocked}`}>
                {detail.blockages.map((message) => <li key={message}>{message}</li>)}
              </ul>
            )}
          </div>
        </article>

        <article className="card span-2">
          <h3>Reponse Typeform simplifiee</h3>
          <div className="table-wrap top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Champ</th>
                  <th>Valeur</th>
                </tr>
              </thead>
              <tbody>
                {detail.answers.map((answer) => (
                  <tr key={`${answer.key}-${answer.label}`}>
                    <td>{answer.label}</td>
                    <td>{answer.value || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className="card">
          <div className="row spread wrap gap-sm">
            <div>
              <h3>Donnees normalisees</h3>
              <p className="muted">Bloc editable pour completer ou forcer les valeurs utiles au pipeline.</p>
            </div>
            <Link className="ghost" href={normalizedEditorHref}>Corriger / completer</Link>
          </div>
          <div className="table-wrap top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Cle</th>
                  <th>Valeur</th>
                </tr>
              </thead>
              <tbody>
                {normalizedEntries(detail.normalized_payload_json).map((entry) => (
                  <tr key={entry.key}>
                    <td>{entry.key}</td>
                    <td>{entry.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className="card">
          <h3>Matching client</h3>
          <div className={`${styles.candidateStack} top-gap-sm`}>
            {detail.client_candidates.length === 0 ? <p className="muted">Aucune correspondance detectee automatiquement.</p> : null}
            {detail.client_candidates.map((candidate) => (
              <article className={styles.candidateItem} key={`${candidate.kind}-${candidate.client_id || candidate.display_name}-${candidate.adult_client_id || ""}-${candidate.child_client_id || ""}`}>
                <div className="row spread wrap gap-sm">
                  <strong>{candidate.display_name}</strong>
                  <span className={`status-pill ${confidencePillClass(candidate.confidence_label)}`}>{candidate.confidence_label} · {candidate.confidence}</span>
                </div>
                <p className="muted">{candidate.subtitle || candidate.kind}</p>
                {candidate.reasons.length > 0 ? (
                  <p className="muted">Raisons: {candidate.reasons.join(", ")}</p>
                ) : null}
              </article>
            ))}
          </div>
        </article>

        <article className="card span-2">
          <h3>Panneau de resolution</h3>
          <form
            id={resolutionFormId}
            action={saveTypeformIntakeResolutionAction}
            className="grid cols-2 config-form-grid top-gap-sm"
          >
            <input type="hidden" name="intake_id" value={detail.id} />
            <input type="hidden" name="return_to" value={intakeHref} />

            <label>
              Mode client
              <select name="client_mode" defaultValue={resolution.clientMode}>
                <option value="new_adult_prospect">Creer un nouveau prospect adulte</option>
                <option value="new_parent_child_prospect">Creer parent + enfant</option>
                <option value="existing_client">Rattacher a un client existant</option>
                <option value="existing_family">Rattacher a une famille existante</option>
              </select>
            </label>

            <label>
              Client existant
              <select name="selected_client_id" defaultValue={resolution.selectedClientId}>
                <option value="">Aucun</option>
                {clientCandidates.map((candidate) => (
                  <option key={candidate.client_id || candidate.display_name} value={candidate.client_id || ""}>
                    {candidate.display_name} · {candidate.confidence_label} · {candidate.confidence}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Famille adulte
              <select name="selected_family_adult_client_id" defaultValue={resolution.selectedFamilyAdultClientId}>
                <option value="">Aucune</option>
                {familyCandidates.map((candidate) => (
                  <option key={`adult-${candidate.adult_client_id || candidate.display_name}`} value={candidate.adult_client_id || ""}>
                    {candidate.display_name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Famille enfant
              <select name="selected_family_child_client_id" defaultValue={resolution.selectedFamilyChildClientId}>
                <option value="">Aucun</option>
                {familyCandidates.map((candidate) => (
                  <option key={`child-${candidate.child_client_id || candidate.display_name}`} value={candidate.child_client_id || ""}>
                    {candidate.display_name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Payeur famille
              <select name="selected_family_billing_client_id" defaultValue={resolution.selectedFamilyBillingClientId}>
                <option value="">Automatique</option>
                {familyCandidates.map((candidate) => (
                  <option key={`billing-${candidate.billing_client_id || candidate.display_name}`} value={candidate.billing_client_id || ""}>
                    {candidate.display_name}
                  </option>
                ))}
              </select>
            </label>

            <label className="span-2">
              Notes d arbitrage
              <textarea name="resolution_notes" defaultValue={resolution.notes} rows={3} />
            </label>

            <div className="span-2">
              <h4>Creneaux</h4>
              <div className={`${styles.candidateStack} top-gap-sm`}>
                {detail.session_recommendations.length === 0 ? <p className="muted">Aucune recommandation de creneau.</p> : null}
                {detail.session_recommendations.map((recommendation) => {
                  const autoCount = recommendation.options.length;
                  const manualCount = recommendation.manual_options.length;
                  const hasAutomaticOptions = autoCount > 0;
                  const hasManualOptions = manualCount > 0;
                  return (
                    <article className={styles.candidateItem} key={recommendation.activity_id}>
                      <div className="row spread wrap gap-sm">
                        <div>
                          <strong>{recommendation.activity_name}</strong>
                          <p className="muted">
                            {recommendation.summary_label}
                            {recommendation.requested_summary ? ` · ${recommendation.requested_summary}` : ""}
                          </p>
                        </div>
                        <span className={`status-pill ${recommendation.blockages.length > 0 ? "status-off" : recommendation.warnings.length > 0 ? "status-warn" : "status-ok"}`}>
                          {recommendation.summary_status}
                        </span>
                      </div>
                      <label className="top-gap-sm">
                        Creneau retenu
                        <input
                          type="hidden"
                          name={`initial_selected_session_for_${recommendation.activity_id}`}
                          value={recommendation.selected_session_id || ""}
                        />
                        <select name={`selected_session_for_${recommendation.activity_id}`} defaultValue={recommendation.selected_session_id || ""}>
                          <option value="">Aucune selection</option>
                          {hasAutomaticOptions ? (
                            <optgroup label="Propositions compatibles">
                              {recommendation.options.map((option, index) => (
                                <option key={option.session_id} value={option.session_id}>
                                  {proposalLabel(index)} · {option.selection_label}
                                </option>
                              ))}
                            </optgroup>
                          ) : null}
                          {hasManualOptions ? (
                            <optgroup label={hasAutomaticOptions ? "Choix manuel (autre activite)" : "Choix manuel de creneau"}>
                              {recommendation.manual_options.map((option, index) => (
                                <option key={option.session_id} value={option.session_id}>
                                  {manualProposalLabel(index)} · {option.selection_label}
                                </option>
                              ))}
                            </optgroup>
                          ) : null}
                        </select>
                      </label>
                      <p className="muted">
                        {autoCount} proposition{autoCount > 1 ? "s" : ""} compatible{autoCount > 1 ? "s" : ""}
                        {hasManualOptions ? ` · ${manualCount} choix manuel${manualCount > 1 ? "s" : ""}` : ""}
                      </p>
                      {hasAutomaticOptions ? (
                        <div className="table-wrap top-gap-sm">
                          <table className="data-table">
                            <thead>
                              <tr>
                                <th>Proposition</th>
                                <th>Occurrence</th>
                                <th>Serie</th>
                                <th>Lieu</th>
                                <th>Places</th>
                                <th>Score</th>
                                <th>Raisons</th>
                              </tr>
                            </thead>
                            <tbody>
                              {recommendation.options.map((option, index) => (
                                <tr
                                  className={recommendation.selected_session_id === option.session_id ? styles.selectedOptionRow : undefined}
                                  key={option.session_id}
                                >
                                  <td>
                                    <div className={styles.optionCellStack}>
                                      <strong>{proposalLabel(index)}</strong>
                                      {recommendation.selected_session_id === option.session_id ? (
                                        <span className="badge">Retenu</span>
                                      ) : null}
                                    </div>
                                  </td>
                                  <td>
                                    <div className={styles.optionCellStack}>
                                      <strong>{option.occurrence_label}</strong>
                                      <span className="muted">{slotOptionTitle(option)}</span>
                                    </div>
                                  </td>
                                  <td>{slotBadgeLabel(option)}</td>
                                  <td>{option.location_name}</td>
                                  <td>{option.seats_remaining}</td>
                                  <td>{option.score}</td>
                                  <td>{option.reasons.join(", ")}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : null}
                      {hasManualOptions ? (
                        <div className="table-wrap top-gap-sm">
                          <table className="data-table">
                            <thead>
                              <tr>
                                <th>Choix manuel</th>
                                <th>Activite</th>
                                <th>Occurrence</th>
                                <th>Serie</th>
                                <th>Lieu</th>
                                <th>Places</th>
                                <th>Score</th>
                                <th>Raisons</th>
                              </tr>
                            </thead>
                            <tbody>
                              {recommendation.manual_options.map((option, index) => (
                                <tr
                                  className={recommendation.selected_session_id === option.session_id ? styles.selectedOptionRow : undefined}
                                  key={option.session_id}
                                >
                                  <td>
                                    <div className={styles.optionCellStack}>
                                      <strong>{manualProposalLabel(index)}</strong>
                                      {recommendation.selected_session_id === option.session_id ? (
                                        <span className="badge">Retenu</span>
                                      ) : null}
                                    </div>
                                  </td>
                                  <td>{option.activity_name}</td>
                                  <td>
                                    <div className={styles.optionCellStack}>
                                      <strong>{option.occurrence_label}</strong>
                                      <span className="muted">{slotOptionTitle(option)}</span>
                                    </div>
                                  </td>
                                  <td>{slotBadgeLabel(option)}</td>
                                  <td>{option.location_name}</td>
                                  <td>{option.seats_remaining}</td>
                                  <td>{option.score}</td>
                                  <td>{option.reasons.join(", ")}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : null}
                    </article>
                  );
                })}
              </div>
            </div>

          </form>
          <div className="row wrap gap-sm top-gap-sm">
            <button type="submit" form={resolutionFormId}>Enregistrer arbitrage</button>
            <form action={reanalyzeTypeformIntakeAction} className="inline">
              <input type="hidden" name="intake_id" value={detail.id} />
              <input type="hidden" name="return_to" value={intakeHref} />
              <button type="submit" className="ghost">Analyser a nouveau les propositions</button>
            </form>
          </div>
        </article>

        <article className="card span-2">
          <div className="row spread wrap gap-sm">
            <div>
              <h3>Preview du pre-devis</h3>
              <p className="muted">Le devis brouillon final reutilisera le module devis existant.</p>
            </div>
            <form id={draftQuoteFormId} action={generateTypeformDraftQuoteAction}>
              <input type="hidden" name="intake_id" value={detail.id} />
              <input type="hidden" name="return_to" value={`/admin/intakes/${encodeURIComponent(detail.id)}`} />
              {canCreateDraftWithoutActivities ? (
                <input type="hidden" name="allow_without_activities" value="1" />
              ) : null}
              {canCreateDraftWithoutActivities ? (
                <ConfirmSubmitButton
                  formId={draftQuoteFormId}
                  label="Generer devis sans activites"
                  title="Creer un devis sans activites ?"
                  description={
                    "Aucun creneau pertinent n a ete trouve pour cette intake.\n\n"
                    + "Le devis sera cree sans activites ni planning. "
                    + "Vous pourrez ensuite ajouter les activites manuellement dans le devis."
                  }
                  confirmLabel="Creer le devis vide"
                  disabled={draftQuoteBlocked}
                />
              ) : (
                <button type="submit" disabled={draftQuoteBlocked}>
                  {detail.related_quote_id ? "Devis deja cree" : "Generer devis brouillon"}
                </button>
              )}
            </form>
          </div>
          {canCreateDraftWithoutActivities ? (
            <p className="muted top-gap-sm">
              Aucun creneau n a ete trouve. Vous pouvez tout de meme creer un devis vide, puis ajouter les activites manuellement.
            </p>
          ) : null}
          {draftQuoteNeedsArbitrage && !detail.related_quote_id ? (
            <p className="muted top-gap-sm">
              Enregistrez d abord les arbitrages en attente avant de generer le devis.
            </p>
          ) : null}

          {detail.preview_quote ? (
            <>
              <div className={`${styles.kvGrid} top-gap-sm`}>
                <div><strong>Contexte</strong><p className="muted">{detail.preview_quote.context_label}</p></div>
                <div><strong>Client / prospect</strong><p className="muted">{detail.preview_quote.customer_label}</p></div>
                <div><strong>Lieu</strong><p className="muted">{detail.preview_quote.location_name || "-"}</p></div>
                <div><strong>Type devis</strong><p className="muted">{detail.preview_quote.quote_type_name || "-"}</p></div>
                <div><strong>Catalogue</strong><p className="muted">{detail.preview_quote.pricing_catalog_name || "-"}</p></div>
                <div><strong>Plan de paiement</strong><p className="muted">{detail.preview_quote.payment_plan_name || "-"}</p></div>
                <div><strong>Entite legale</strong><p className="muted">{detail.preview_quote.legal_entity_name || "-"}</p></div>
                <div><strong>Annee scolaire</strong><p className="muted">{detail.preview_quote.school_year_label || "-"}</p></div>
              </div>

              <div className="top-gap-sm">
                <strong>Options</strong>
                {detail.preview_quote.selected_options.length === 0 ? (
                  <p className="muted">Aucune option specifique.</p>
                ) : (
                  <div className={`${styles.chipRow} top-gap-sm`}>
                    {detail.preview_quote.selected_options.map((item) => (
                      <span className="badge" key={item}>{item}</span>
                    ))}
                  </div>
                )}
              </div>

              <div className="table-wrap top-gap-sm">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Ligne</th>
                      <th>Quantite</th>
                      <th>PU TTC</th>
                      <th>TVA</th>
                      <th>Total TTC</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.preview_quote.lines.map((line) => (
                      <tr key={`${line.title}-${line.pricing_unit}-${line.quantity}`}>
                        <td>
                          <strong>{line.title}</strong>
                          {line.description ? <div className="muted">{line.description}</div> : null}
                        </td>
                        <td>{line.quantity}</td>
                        <td>{formatAmount(line.unit_price_ttc, detail.preview_quote?.currency || "EUR")}</td>
                        <td>{line.vat_rate}%</td>
                        <td>{formatAmount(line.amount_ttc, detail.preview_quote?.currency || "EUR")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className={`${styles.totalRow} top-gap-sm`}>
                <div><strong>Total HT</strong><p>{formatAmount(detail.preview_quote.total_ht, detail.preview_quote.currency)}</p></div>
                <div><strong>Total TVA</strong><p>{formatAmount(detail.preview_quote.total_vat, detail.preview_quote.currency)}</p></div>
                <div><strong>Total TTC</strong><p>{formatAmount(detail.preview_quote.total_ttc, detail.preview_quote.currency)}</p></div>
              </div>
            </>
          ) : (
            <p className="muted top-gap-sm">Aucun pre-devis exploitable pour le moment.</p>
          )}
        </article>
      </section>
    </section>
  );
}
