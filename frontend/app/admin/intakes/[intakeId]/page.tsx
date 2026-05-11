import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  generateTypeformDraftQuoteAction,
  reanalyzeTypeformIntakeAction,
  saveTypeformIntakeNormalizedDataAction,
  saveTypeformIntakeReferralAction,
  saveTypeformIntakeResolutionAction,
} from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import { hasAdminPermission } from "../../../../lib/admin-access";
import type { UserOut } from "../../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../../lib/ui-i18n";
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
  slot_proposals: Record<string, unknown>[];
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

function solfegeProposalLabel(value: Record<string, unknown>): string {
  const label = typeof value.label === "string" ? value.label.trim() : "";
  if (label) return label;
  const weekday = typeof value.weekday_label === "string" ? value.weekday_label.trim() : "";
  const start = typeof value.start_time === "string" ? value.start_time.trim() : "";
  const end = typeof value.end_time === "string" ? value.end_time.trim() : "";
  return [weekday, [start, end].filter(Boolean).join("-")].filter(Boolean).join(" ");
}

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
  solfege_slot_proposal: Record<string, unknown>;
  preview_quote: TypeformQuotePreviewOut | null;
  related_quote_id: string | null;
  form_config: TypeformFormConfigOut | null;
  referral: {
    id: string;
    declared_referrer_text: string;
    category: string | null;
    status: string;
    match_status: string;
    referrer_user_id: string | null;
    reward_amount: string;
    currency: string;
    trigger_ratio: string;
    credit_transaction_id: string | null;
    match_candidates: Array<{
      user_id: string;
      display_name: string;
      email: string | null;
      confidence: number;
      reasons: string[];
    }>;
  } | null;
};

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatDate(value: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString(localeForUiLanguage(language), { dateStyle: "short", timeStyle: "short" });
}

function formatAmount(value: string, currency: string, language: UiLanguage): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) {
    return `${value} ${currency}`;
  }
  try {
    return new Intl.NumberFormat(localeForUiLanguage(language), { style: "currency", currency: currency || "EUR" }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${(currency || "EUR").toUpperCase()}`;
  }
}

function statusLabel(value: string, language: UiLanguage): string {
  if (value === "NEW") return uiText(language, "admin.intakes.status_new");
  if (value === "NORMALIZED") return uiText(language, "admin.intakes.status_normalized");
  if (value === "MATCHING_REQUIRED") return uiText(language, "admin.intakes.status_matching_required");
  if (value === "READY_FOR_DRAFT_QUOTE") return uiText(language, "admin.intakes.status_ready_draft");
  if (value === "BLOCKED") return uiText(language, "admin.intakes.status_blocked");
  if (value === "PROCESSED") return uiText(language, "admin.intakes.status_processed");
  if (value === "IGNORED") return uiText(language, "admin.intakes.status_ignored");
  return value;
}

const INTAKE_REFERRAL_TEXT: Record<UiLanguage, Record<string, string>> = {
  fr: {
    declared: "Parrainage declare",
    category: "Categorie parrainage",
    online: "En ligne",
    home: "Domicile",
    title: "Parrainage",
    valid_referrer: "Parrain valide : {id}",
    no_match: "Aucune famille trouvee automatiquement.",
    referrer_family: "Famille marraine",
    validate_referrer: "Valider le parrain",
    family: "Famille",
    email: "Email",
    score: "Score",
    status_needs_review: "A verifier",
    status_awaiting_payment: "En attente paiement",
    status_credit_granted: "Avoir genere",
    status_cancelled: "Annule",
    status_declared: "Declare",
  },
  en: {
    declared: "Declared referral",
    category: "Referral category",
    online: "Online",
    home: "Home",
    title: "Referral",
    valid_referrer: "Validated referrer: {id}",
    no_match: "No family was matched automatically.",
    referrer_family: "Referrer family",
    validate_referrer: "Validate referrer",
    family: "Family",
    email: "Email",
    score: "Score",
    status_needs_review: "To review",
    status_awaiting_payment: "Awaiting payment",
    status_credit_granted: "Credit granted",
    status_cancelled: "Cancelled",
    status_declared: "Declared",
  },
};

function intakeReferralText(language: UiLanguage, key: string, values?: Record<string, string | number>): string {
  const template = INTAKE_REFERRAL_TEXT[language][key] || INTAKE_REFERRAL_TEXT.fr[key] || key;
  if (!values) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (_match, token) => String(values[token] ?? ""));
}

function referralCategoryLabel(value: string | null, language: UiLanguage): string {
  if (value === "PARIS") return "Paris";
  if (value === "BAR_LE_DUC") return "Bar-le-Duc";
  if (value === "ONLINE") return intakeReferralText(language, "online");
  if (value === "DOMICILE") return intakeReferralText(language, "home");
  return value || "-";
}

function referralStatusLabel(value: string, language: UiLanguage): string {
  if (value === "NEEDS_REVIEW") return intakeReferralText(language, "status_needs_review");
  if (value === "AWAITING_PAYMENT") return intakeReferralText(language, "status_awaiting_payment");
  if (value === "CREDIT_GRANTED") return intakeReferralText(language, "status_credit_granted");
  if (value === "CANCELLED") return intakeReferralText(language, "status_cancelled");
  if (value === "DECLARED") return intakeReferralText(language, "status_declared");
  return value || "-";
}

function statusClass(value: string): string {
  if (value === "READY_FOR_DRAFT_QUOTE" || value === "PROCESSED") return "status-ok";
  if (value === "MATCHING_REQUIRED" || value === "NEW" || value === "NORMALIZED") return "status-warn";
  return "status-off";
}

function segmentLabel(value: string | null, language: UiLanguage): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "eveil") return uiText(language, "admin.intakes.segment_eveil");
  if (normalized === "child") return uiText(language, "admin.intakes.segment_child");
  if (normalized === "teen") return uiText(language, "admin.intakes.segment_teen");
  if (normalized === "adult") return uiText(language, "admin.intakes.segment_adult");
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

function normalizedEntries(payload: Record<string, unknown>): Array<{ key: string; value: string }> {
  return Object.entries(payload).map(([key, value]) => ({
    key,
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

function proposalLabel(index: number, language: UiLanguage): string {
  return uiText(language, "admin.intakes.proposal", { index: index + 1 });
}

function manualProposalLabel(index: number, language: UiLanguage): string {
  return uiText(language, "admin.intakes.manual_choice", { index: index + 1 });
}

const EMPTY_PREQUOTE_BLOCKAGES = [
  "Aucune ligne de pre-devis n est configuree pour ce formulaire.",
  "Aucune ligne de pre-devis ne correspond aux choix du formulaire.",
  "Le pre-devis est vide car aucune ligne exploitable n a ete resolue.",
];

function slotBadgeLabel(option: TypeformSessionMatchOptionOut, language: UiLanguage): string {
  return option.recurrence_label || uiText(language, "admin.intakes.punctual");
}

function slotOptionTitle(option: TypeformSessionMatchOptionOut): string {
  if (option.activity_name) {
    return option.activity_name;
  }
  if (option.title) {
    return option.title;
  }
  return "";
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
  const normalized = label.trim().toLowerCase();
  if (normalized === "fort" || normalized === "strong") return "status-ok";
  if (normalized === "moyen" || normalized === "medium") return "status-warn";
  return "status-off";
}

function confidenceLabel(label: string, language: UiLanguage): string {
  const normalized = label.trim().toLowerCase();
  if (normalized === "fort" || normalized === "strong") {
    return uiText(language, "admin.intakes.confidence_strong");
  }
  if (normalized === "moyen" || normalized === "medium") {
    return uiText(language, "admin.intakes.confidence_medium");
  }
  if (normalized === "faible" || normalized === "low") {
    return uiText(language, "admin.intakes.confidence_low");
  }
  return label;
}

function clientModeLabel(mode: string, language: UiLanguage): string {
  if (mode === "existing_client") return uiText(language, "admin.intakes.mode_existing_client");
  if (mode === "existing_family") return uiText(language, "admin.intakes.mode_existing_family");
  if (mode === "new_parent_child_prospect") return uiText(language, "admin.intakes.mode_new_parent_child");
  return uiText(language, "admin.intakes.mode_new_adult");
}

export default async function AdminTypeformIntakeDetailPage({ params, searchParams }: RouteParams): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || !hasAdminPermission(meResult.data, "can_view_intakes")) {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

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
  const emptyPreviewOnlyBlockage =
    !detail.related_quote_id
    && detail.preview_quote === null
    && detail.blockages.length > 0
    && detail.blockages.every((message) => EMPTY_PREQUOTE_BLOCKAGES.includes(message));
  const draftQuoteBlocked =
    Boolean(detail.related_quote_id)
    || (detail.blockages.length > 0 && !emptyPreviewOnlyBlockage)
    || detail.intake_status === "IGNORED";

  return (
    <section className="admin-page-grid">
      {showResolutionSavedModal ? (
        <section className="modal-overlay" role="dialog" aria-modal="true" aria-label={t("admin.intakes.resolution_saved_title")}>
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={dismissSuccessHref} aria-label={uiText(language, "common.close")}>
              ×
            </Link>
            <h3 className="modal-title">{t("admin.intakes.resolution_saved_title")}</h3>
            <section className="flash-ok modal-flash" role="status">
              {ok}
            </section>
            <p className="muted">{t("admin.intakes.resolution_saved_body")}</p>
            <div className="row modal-actions-end top-gap-sm">
              <Link href={dismissSuccessHref}>{uiText(language, "common.close")}</Link>
            </div>
          </article>
        </section>
      ) : null}

      {showErrorModal ? (
        <section className="modal-overlay" role="dialog" aria-modal="true" aria-label={t("admin.intakes.quote_generation_impossible_title")}>
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={dismissErrorHref} aria-label={uiText(language, "common.close")}>
              ×
            </Link>
            <h3 className="modal-title">{t("admin.intakes.quote_generation_impossible_title")}</h3>
            <section className="flash-err modal-flash" role="alert">
              {error}
            </section>
            <p className="muted">{t("admin.intakes.quote_generation_impossible_body")}</p>
            <div className="row modal-actions-end top-gap-sm">
              <Link className="ghost" href={dismissErrorHref}>{uiText(language, "common.close")}</Link>
              <Link href={normalizedEditorHref}>{t("admin.intakes.correct_data")}</Link>
            </div>
          </article>
        </section>
      ) : null}

      {editor === "normalized" ? (
        <section className="modal-overlay" role="dialog" aria-modal="true" aria-label={t("admin.intakes.normalized_editor_title")}>
          <article className="modal-panel modal-panel-wide">
            <Link className="modal-close-x" href={closeNormalizedEditorHref} aria-label={uiText(language, "common.close")}>
              ×
            </Link>
            <h3 className="modal-title">{t("admin.intakes.normalized_editor_title")}</h3>
            <p className={styles.editorIntro}>{t("admin.intakes.normalized_editor_intro")}</p>
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
                  <h4>{t("admin.intakes.parent_adult")}</h4>
                  <label>
                    {t("admin.intakes.first_name")}
                    <input name="parent_first_name" defaultValue={normalizedScalarValue(normalizedPayload, "parent_first_name")} />
                  </label>
                  <label>
                    {t("admin.intakes.last_name")}
                    <input name="parent_last_name" defaultValue={normalizedScalarValue(normalizedPayload, "parent_last_name")} />
                  </label>
                  <label>
                    {uiText(language, "common.email")}
                    <input
                      name="parent_email"
                      type="email"
                      defaultValue={normalizedScalarValue(normalizedPayload, "parent_email")}
                      placeholder={t("admin.intakes.email_placeholder")}
                    />
                  </label>
                  <label>
                    {t("admin.intakes.phone")}
                    <input name="parent_phone" defaultValue={normalizedScalarValue(normalizedPayload, "parent_phone")} />
                  </label>
                </section>

                <section className={styles.editorSection}>
                  <h4>{t("admin.intakes.child_client")}</h4>
                  <label>
                    {t("admin.intakes.customer_type")}
                    <select name="customer_type" defaultValue={normalizedScalarValue(normalizedPayload, "customer_type") || "child"}>
                      <option value="child">{t("admin.intakes.customer_type_child")}</option>
                      <option value="adult">{t("admin.intakes.customer_type_adult")}</option>
                    </select>
                  </label>
                  <label>
                    {t("admin.intakes.first_name")}
                    <input name="child_first_name" defaultValue={normalizedScalarValue(normalizedPayload, "child_first_name")} />
                  </label>
                  <label>
                    {t("admin.intakes.last_name")}
                    <input name="child_last_name" defaultValue={normalizedScalarValue(normalizedPayload, "child_last_name")} />
                  </label>
                  <label>
                    {t("admin.intakes.birth_date")}
                    <input name="child_birth_date" type="date" defaultValue={normalizedScalarValue(normalizedPayload, "child_birth_date")} />
                  </label>
                </section>

                <section className={styles.editorSection}>
                  <h4>{t("admin.intakes.request")}</h4>
                  <label>
                    {t("admin.intakes.requested_location")}
                    <input name="requested_location" defaultValue={normalizedScalarValue(normalizedPayload, "requested_location")} />
                  </label>
                  <label>
                    {t("admin.intakes.course_mode")}
                    <input name="requested_course_mode" defaultValue={normalizedScalarValue(normalizedPayload, "requested_course_mode")} />
                  </label>
                  <label>
                    {t("admin.intakes.formula")}
                    <input name="requested_formula_type" defaultValue={normalizedScalarValue(normalizedPayload, "requested_formula_type")} />
                  </label>
                  <label>
                    {intakeReferralText(language, "declared")}
                    <input name="referral_referrer_name" defaultValue={normalizedScalarValue(normalizedPayload, "referral_referrer_name")} />
                  </label>
                  <label>
                    {intakeReferralText(language, "category")}
                    <select name="referral_category" defaultValue={normalizedScalarValue(normalizedPayload, "referral_category")}>
                      <option value="">-</option>
                      <option value="PARIS">Paris</option>
                      <option value="BAR_LE_DUC">Bar-le-Duc</option>
                      <option value="ONLINE">{intakeReferralText(language, "online")}</option>
                      <option value="DOMICILE">{intakeReferralText(language, "home")}</option>
                    </select>
                  </label>
                </section>

                <section className={styles.editorSection}>
                  <h4>{t("admin.intakes.slot_preferences")}</h4>
                  <label>
                    {t("admin.intakes.requested_days")}
                    <textarea
                      name="requested_days"
                      defaultValue={normalizedListValue(normalizedPayload, "requested_days")}
                      rows={4}
                      placeholder={t("admin.intakes.one_day_per_line")}
                    />
                  </label>
                  <label>
                    {t("admin.intakes.requested_times")}
                    <textarea
                      name="requested_times"
                      defaultValue={normalizedListValue(normalizedPayload, "requested_times")}
                      rows={4}
                      placeholder={t("admin.intakes.one_time_per_line")}
                    />
                  </label>
                  <label>
                    {t("admin.intakes.requested_slot_preferences")}
                    <textarea
                      name="requested_slot_preferences"
                      defaultValue={normalizedListValue(normalizedPayload, "requested_slot_preferences")}
                      rows={5}
                      placeholder={t("admin.intakes.one_preference_per_line")}
                    />
                  </label>
                </section>

                <section className={`${styles.editorSection} ${styles.editorSectionWide}`}>
                  <h4>{t("admin.intakes.products_and_notes")}</h4>
                  <label>
                    {t("admin.intakes.requested_products")}
                    <textarea
                      name="requested_products"
                      defaultValue={normalizedListValue(normalizedPayload, "requested_products")}
                      rows={4}
                      placeholder={t("admin.intakes.one_product_per_line")}
                    />
                  </label>
                  <label>
                    {uiText(language, "common.notes")}
                    <textarea
                      name="notes"
                      defaultValue={normalizedScalarValue(normalizedPayload, "notes")}
                      rows={5}
                      placeholder={t("admin.intakes.internal_comments")}
                    />
                  </label>
                </section>
              </div>

              <div className="row modal-actions-end top-gap-sm">
                <Link className="ghost" href={closeNormalizedEditorHref}>{uiText(language, "common.cancel")}</Link>
                <button type="submit">{t("admin.intakes.save_corrections")}</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <div className="row wrap gap-sm">
              <span className={`status-pill ${statusClass(detail.intake_status)}`}>{statusLabel(detail.intake_status, language)}</span>
              <span className="badge">{detail.source_form_label}</span>
            </div>
            <h2 className="top-gap-sm">{t("admin.intakes.detail_title")}</h2>
            <p className="muted">{t("admin.intakes.received_on", { responseId: detail.source_response_id, date: formatDate(detail.received_at, language) })}</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href={backHref}>{t("admin.intakes.back_inbox")}</Link>
            {detail.related_quote_id ? (
              <Link className="ghost" href={`/admin/quotes/${encodeURIComponent(detail.related_quote_id)}`}>{t("admin.intakes.open_related_quote")}</Link>
            ) : null}
          </div>
        </div>
      </section>

      {ok && !showResolutionSavedModal ? <section className="flash-ok">{ok}</section> : null}

      <section className={`grid cols-2 ${styles.panelGrid}`}>
        <article className="card">
          <h3>{t("admin.intakes.summary_title")}</h3>
          <div className={`${styles.kvGrid} top-gap-sm`}>
            <div><strong>{t("admin.intakes.form_identifier")}</strong><p className="muted">{detail.source_form_id}</p></div>
            <div><strong>{t("admin.intakes.source_code")}</strong><p className="muted">{detail.form_config?.source_code || "-"}</p></div>
            <div><strong>{uiText(language, "common.site")}</strong><p className="muted">{detail.detected_location || "-"}</p></div>
            <div><strong>{t("admin.intakes.segment")}</strong><p className="muted">{segmentLabel(detail.detected_segment, language)}</p></div>
            <div><strong>{t("admin.intakes.school_year")}</strong><p className="muted">{detail.detected_school_year || "-"}</p></div>
            <div><strong>{t("admin.intakes.current_client_mode")}</strong><p className="muted">{clientModeLabel(resolution.clientMode, language)}</p></div>
          </div>
        </article>

        <article className="card">
          <h3>{t("admin.intakes.warnings_blockages_title")}</h3>
          <div className="top-gap-sm">
            <p><strong>{uiText(language, "common.warnings")}</strong></p>
            {detail.warnings.length === 0 ? <p className="muted">{t("admin.intakes.no_warning")}</p> : (
              <ul className={styles.messageList}>
                {detail.warnings.map((message) => <li key={message}>{message}</li>)}
              </ul>
            )}
            <p className="top-gap-sm"><strong>{uiText(language, "common.blockages")}</strong></p>
            {detail.blockages.length === 0 ? <p className="muted">{t("admin.intakes.no_blockage")}</p> : (
              <ul className={`${styles.messageList} ${styles.messageListBlocked}`}>
                {detail.blockages.map((message) => <li key={message}>{message}</li>)}
              </ul>
            )}
          </div>
        </article>

        {detail.referral ? (
          <article className="card span-2">
            <div className="row spread wrap gap-sm">
              <div>
                <h3>{intakeReferralText(language, "title")}</h3>
                <p className="muted">
                  {detail.referral.declared_referrer_text || "-"} · {referralCategoryLabel(detail.referral.category, language)} · {formatAmount(detail.referral.reward_amount, detail.referral.currency, language)}
                </p>
              </div>
              <span className={`status-pill ${detail.referral.status === "CREDIT_GRANTED" ? "status-ok" : detail.referral.status === "NEEDS_REVIEW" ? "status-warn" : "status-off"}`}>
                {referralStatusLabel(detail.referral.status, language)}
              </span>
            </div>
            <div className={`${styles.candidateStack} top-gap-sm`}>
              {detail.referral.referrer_user_id ? (
                <p className="muted">{intakeReferralText(language, "valid_referrer", { id: detail.referral.referrer_user_id })}</p>
              ) : detail.referral.match_candidates.length === 0 ? (
                <p className="muted">{intakeReferralText(language, "no_match")}</p>
              ) : (
                <form action={saveTypeformIntakeReferralAction} className="grid cols-2 config-form-grid">
                  <input type="hidden" name="intake_id" value={detail.id} />
                  <input type="hidden" name="return_to" value={intakeHref} />
                  <label>
                    {intakeReferralText(language, "referrer_family")}
                    <select name="referrer_user_id" defaultValue={detail.referral.match_candidates[0]?.user_id || ""}>
                      {detail.referral.match_candidates.map((candidate) => (
                        <option key={candidate.user_id} value={candidate.user_id}>
                          {candidate.display_name} · {candidate.confidence}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="row align-end">
                    <button type="submit">{intakeReferralText(language, "validate_referrer")}</button>
                  </div>
                </form>
              )}
              {detail.referral.match_candidates.length > 0 ? (
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>{intakeReferralText(language, "family")}</th>
                        <th>{intakeReferralText(language, "email")}</th>
                        <th>{intakeReferralText(language, "score")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.referral.match_candidates.map((candidate) => (
                        <tr key={`referral-candidate-${candidate.user_id}`}>
                          <td>{candidate.display_name}</td>
                          <td>{candidate.email || "-"}</td>
                          <td>{candidate.confidence}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </div>
          </article>
        ) : null}

        <article className="card span-2">
          <h3>{t("admin.intakes.response_simplified")}</h3>
          <div className="table-wrap top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{uiText(language, "common.key")}</th>
                  <th>{uiText(language, "common.value")}</th>
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
              <h3>{t("admin.intakes.normalized_data_title")}</h3>
              <p className="muted">{t("admin.intakes.normalized_data_subtitle")}</p>
            </div>
            <Link className="ghost" href={normalizedEditorHref}>{t("admin.intakes.correct_complete")}</Link>
          </div>
          <div className="table-wrap top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{uiText(language, "common.key")}</th>
                  <th>{uiText(language, "common.value")}</th>
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
          <h3>{t("admin.intakes.matching_client_title")}</h3>
          <div className={`${styles.candidateStack} top-gap-sm`}>
            {detail.client_candidates.length === 0 ? <p className="muted">{t("admin.intakes.no_auto_match")}</p> : null}
            {detail.client_candidates.map((candidate) => (
              <article className={styles.candidateItem} key={`${candidate.kind}-${candidate.client_id || candidate.display_name}-${candidate.adult_client_id || ""}-${candidate.child_client_id || ""}`}>
                <div className="row spread wrap gap-sm">
                  <strong>{candidate.display_name}</strong>
                  <span className={`status-pill ${confidencePillClass(candidate.confidence_label)}`}>{confidenceLabel(candidate.confidence_label, language)} · {candidate.confidence}</span>
                </div>
                <p className="muted">{candidate.subtitle || candidate.kind}</p>
                {candidate.reasons.length > 0 ? (
                  <p className="muted">{t("admin.intakes.reasons")}: {candidate.reasons.join(", ")}</p>
                ) : null}
              </article>
            ))}
          </div>
        </article>

        <article className="card span-2">
          <h3>{t("admin.intakes.resolution_panel")}</h3>
          <form action={saveTypeformIntakeResolutionAction} className="grid cols-2 config-form-grid top-gap-sm" id="resolution-form">
            <input type="hidden" name="intake_id" value={detail.id} />
            <input type="hidden" name="return_to" value={intakeHref} />

            <label>
              {t("admin.intakes.client_mode")}
              <select name="client_mode" defaultValue={resolution.clientMode}>
                <option value="new_adult_prospect">{t("admin.intakes.mode_new_adult")}</option>
                <option value="new_parent_child_prospect">{t("admin.intakes.mode_new_parent_child")}</option>
                <option value="existing_client">{t("admin.intakes.mode_existing_client")}</option>
                <option value="existing_family">{t("admin.intakes.mode_existing_family")}</option>
              </select>
            </label>

            <label>
              {t("admin.intakes.existing_client")}
              <select name="selected_client_id" defaultValue={resolution.selectedClientId}>
                <option value="">{uiText(language, "common.no")}</option>
                {clientCandidates.map((candidate) => (
                  <option key={candidate.client_id || candidate.display_name} value={candidate.client_id || ""}>
                    {candidate.display_name} · {confidenceLabel(candidate.confidence_label, language)} · {candidate.confidence}
                  </option>
                ))}
              </select>
            </label>

            <label>
              {t("admin.intakes.family_adult")}
              <select name="selected_family_adult_client_id" defaultValue={resolution.selectedFamilyAdultClientId}>
                <option value="">{uiText(language, "common.no")}</option>
                {familyCandidates.map((candidate) => (
                  <option key={`adult-${candidate.adult_client_id || candidate.display_name}`} value={candidate.adult_client_id || ""}>
                    {candidate.display_name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              {t("admin.intakes.family_child")}
              <select name="selected_family_child_client_id" defaultValue={resolution.selectedFamilyChildClientId}>
                <option value="">{uiText(language, "common.no")}</option>
                {familyCandidates.map((candidate) => (
                  <option key={`child-${candidate.child_client_id || candidate.display_name}`} value={candidate.child_client_id || ""}>
                    {candidate.display_name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              {t("admin.intakes.family_payer")}
              <select name="selected_family_billing_client_id" defaultValue={resolution.selectedFamilyBillingClientId}>
                <option value="">{t("admin.intakes.automatic")}</option>
                {familyCandidates.map((candidate) => (
                  <option key={`billing-${candidate.billing_client_id || candidate.display_name}`} value={candidate.billing_client_id || ""}>
                    {candidate.display_name}
                  </option>
                ))}
              </select>
            </label>

            <label className="span-2">
              {t("admin.intakes.arbitration_notes")}
              <textarea name="resolution_notes" defaultValue={resolution.notes} rows={3} />
            </label>

            <div className="span-2">
              <h4>{t("admin.intakes.slots")}</h4>
              <div className={`${styles.candidateStack} top-gap-sm`}>
                {solfegeProposalLabel(detail.solfege_slot_proposal || {}) ? (
                  <article className={styles.candidateItem}>
                    <div className="row spread wrap gap-sm">
                      <div>
                        <strong>{t("admin.intakes.solfege_online")}</strong>
                        <p className="muted">{t("admin.intakes.solfege_typeform_proposal", { slot: solfegeProposalLabel(detail.solfege_slot_proposal) })}</p>
                      </div>
                      <span className="status-pill status-ok">{t("admin.intakes.proposed_match")}</span>
                    </div>
                  </article>
                ) : null}
                {detail.session_recommendations.length === 0 && !solfegeProposalLabel(detail.solfege_slot_proposal || {}) ? <p className="muted">{t("admin.intakes.no_slot_recommendation")}</p> : null}
                {detail.session_recommendations.map((recommendation) => (
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
                      {t("admin.intakes.selected_slot")}
                      <select name={`selected_session_for_${recommendation.activity_id}`} defaultValue={recommendation.selected_session_id || ""}>
                        <option value="">
                          {recommendation.slot_proposals.length > 0 ? t("admin.intakes.typeform_proposal_retained") : t("admin.intakes.no_selection")}
                        </option>
                        {recommendation.options.length > 0 ? (
                          <optgroup label={t("admin.intakes.auto_proposals")}>
                            {recommendation.options.map((option, index) => (
                              <option key={option.session_id} value={option.session_id}>
                                {proposalLabel(index, language)} · {option.selection_label}
                              </option>
                            ))}
                          </optgroup>
                        ) : null}
                        {recommendation.manual_options.length > 0 ? (
                          <optgroup label={t("admin.intakes.manual_choices")}>
                            {recommendation.manual_options.map((option, index) => (
                              <option key={option.session_id} value={option.session_id}>
                                {manualProposalLabel(index, language)} · {option.selection_label}
                              </option>
                            ))}
                          </optgroup>
                        ) : null}
                      </select>
                    </label>
                    <p className="muted">
                      {recommendation.slot_proposals.length > 0
                        ? t("admin.intakes.typeform_proposals_available", {
                            typeformCount: recommendation.slot_proposals.length,
                            autoCount: recommendation.options.length,
                            manualCount: recommendation.manual_options.length,
                          })
                        : t("admin.intakes.proposals_available", { autoCount: recommendation.options.length, manualCount: recommendation.manual_options.length })}
                    </p>
                    {recommendation.slot_proposals.length > 0 ? (
                      <div className="table-wrap top-gap-sm">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>{t("admin.intakes.proposal_header")}</th>
                              <th>{t("admin.intakes.occurrence")}</th>
                              <th>{uiText(language, "common.location")}</th>
                              <th>{t("admin.quote_config.solfege_mode")}</th>
                              <th>{t("admin.quote_config.solfege_duration")}</th>
                              <th>{t("admin.intakes.reasons")}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {recommendation.slot_proposals.map((proposal, index) => (
                              <tr className={styles.selectedOptionRow} key={`${recommendation.activity_id}-slot-proposal-${index}`}>
                                <td>
                                  <div className={styles.optionCellStack}>
                                    <strong>{proposalLabel(index, language)}</strong>
                                    <span className="badge">{t("admin.intakes.retained")}</span>
                                  </div>
                                </td>
                                <td>
                                  <div className={styles.optionCellStack}>
                                    <strong>{solfegeProposalLabel(proposal)}</strong>
                                    <span className="muted">{t("admin.intakes.solfege_typeform_source")}</span>
                                  </div>
                                </td>
                                <td>{typeof proposal.location_label === "string" ? proposal.location_label : ""}</td>
                                <td>{typeof proposal.modality === "string" ? proposal.modality : ""}</td>
                                <td>{typeof proposal.duration_minutes === "number" ? t("admin.quote_config.solfege_duration_short", { minutes: proposal.duration_minutes }) : ""}</td>
                                <td>{t("admin.intakes.solfege_typeform_reason")}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : null}
                    {recommendation.options.length > 0 ? (
                      <div className="table-wrap top-gap-sm">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>{t("admin.intakes.proposal_header")}</th>
                              <th>{t("admin.intakes.occurrence")}</th>
                              <th>{t("admin.intakes.series")}</th>
                              <th>{uiText(language, "common.location")}</th>
                              <th>{t("admin.intakes.seats")}</th>
                              <th>{uiText(language, "common.score")}</th>
                              <th>{t("admin.intakes.reasons")}</th>
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
                                    <strong>{proposalLabel(index, language)}</strong>
                                    {recommendation.selected_session_id === option.session_id ? (
                                      <span className="badge">{t("admin.intakes.retained")}</span>
                                    ) : null}
                                  </div>
                                </td>
                                <td>
                                  <div className={styles.optionCellStack}>
                                    <strong>{option.occurrence_label}</strong>
                                    <span className="muted">{slotOptionTitle(option)}</span>
                                  </div>
                                </td>
                                <td>{slotBadgeLabel(option, language)}</td>
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
                    {recommendation.manual_options.length > 0 ? (
                      <div className="table-wrap top-gap-sm">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>{t("admin.intakes.manual_choice_header")}</th>
                              <th>{t("admin.formulas.activities_label")}</th>
                              <th>{t("admin.intakes.occurrence")}</th>
                              <th>{t("admin.intakes.series")}</th>
                              <th>{uiText(language, "common.location")}</th>
                              <th>{t("admin.intakes.seats")}</th>
                              <th>{uiText(language, "common.score")}</th>
                              <th>{t("admin.intakes.reasons")}</th>
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
                                    <strong>{manualProposalLabel(index, language)}</strong>
                                    {recommendation.selected_session_id === option.session_id ? (
                                      <span className="badge">{t("admin.intakes.retained")}</span>
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
                                <td>{slotBadgeLabel(option, language)}</td>
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
                ))}
              </div>
            </div>

          </form>
          <div className="row wrap gap-sm top-gap-sm">
            <button type="submit" form="resolution-form">{t("admin.intakes.save_arbitration")}</button>
            <form action={reanalyzeTypeformIntakeAction} className="inline">
              <input type="hidden" name="intake_id" value={detail.id} />
              <input type="hidden" name="return_to" value={intakeHref} />
              <button type="submit" className="ghost">{t("admin.intakes.reanalyze_proposals")}</button>
            </form>
          </div>
        </article>

        <article className="card span-2">
          <div className="row spread wrap gap-sm">
            <div>
              <h3>{t("admin.intakes.preview_quote_title")}</h3>
              <p className="muted">{t("admin.intakes.preview_quote_subtitle")}</p>
            </div>
            <form action={generateTypeformDraftQuoteAction}>
              <input type="hidden" name="intake_id" value={detail.id} />
              <input type="hidden" name="return_to" value={`/admin/intakes/${encodeURIComponent(detail.id)}`} />
              <button type="submit" disabled={draftQuoteBlocked}>
                {detail.related_quote_id
                  ? t("admin.intakes.quote_already_created")
                  : draftQuoteNeedsArbitrage
                  ? t("admin.intakes.generate_quote_with_warning")
                  : t("admin.intakes.generate_quote")}
              </button>
            </form>
          </div>
          {draftQuoteNeedsArbitrage && !detail.related_quote_id ? (
            <section className="flash-warn top-gap-sm">
              {t("admin.intakes.quote_generation_warning")}
            </section>
          ) : null}
          {emptyPreviewOnlyBlockage ? (
            <section className="flash-warn top-gap-sm">
              <div>{t("admin.intakes.empty_quote_warning")}</div>
              <form action={generateTypeformDraftQuoteAction} className="top-gap-sm">
                <input type="hidden" name="intake_id" value={detail.id} />
                <input type="hidden" name="return_to" value={`/admin/intakes/${encodeURIComponent(detail.id)}`} />
                <input type="hidden" name="allow_empty_quote" value="1" />
                <button type="submit">{t("admin.intakes.generate_empty_quote")}</button>
              </form>
            </section>
          ) : null}

          {detail.preview_quote ? (
            <>
              <div className={`${styles.kvGrid} top-gap-sm`}>
                <div><strong>{t("admin.intakes.context")}</strong><p className="muted">{detail.preview_quote.context_label}</p></div>
                <div><strong>{t("admin.intakes.customer_or_prospect")}</strong><p className="muted">{detail.preview_quote.customer_label}</p></div>
                <div><strong>{uiText(language, "common.location")}</strong><p className="muted">{detail.preview_quote.location_name || "-"}</p></div>
                <div><strong>{t("admin.intakes.quote_type")}</strong><p className="muted">{detail.preview_quote.quote_type_name || "-"}</p></div>
                <div><strong>{t("admin.intakes.catalog")}</strong><p className="muted">{detail.preview_quote.pricing_catalog_name || "-"}</p></div>
                <div><strong>{t("admin.intakes.payment_plan")}</strong><p className="muted">{detail.preview_quote.payment_plan_name || "-"}</p></div>
                <div><strong>{t("admin.intakes.legal_entity")}</strong><p className="muted">{detail.preview_quote.legal_entity_name || "-"}</p></div>
                <div><strong>{t("admin.intakes.school_year")}</strong><p className="muted">{detail.preview_quote.school_year_label || "-"}</p></div>
              </div>

              <div className="top-gap-sm">
                <strong>{t("admin.intakes.options")}</strong>
                {detail.preview_quote.selected_options.length === 0 ? (
                  <p className="muted">{t("admin.intakes.no_specific_options")}</p>
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
                      <th>{t("admin.intakes.line")}</th>
                      <th>{uiText(language, "common.quantity")}</th>
                      <th>{t("admin.intakes.unit_price_ttc")}</th>
                      <th>{uiText(language, "common.vat")}</th>
                      <th>{t("admin.intakes.total_ttc")}</th>
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
                        <td>{formatAmount(line.unit_price_ttc, detail.preview_quote?.currency || "EUR", language)}</td>
                        <td>{line.vat_rate}%</td>
                        <td>{formatAmount(line.amount_ttc, detail.preview_quote?.currency || "EUR", language)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className={`${styles.totalRow} top-gap-sm`}>
                <div><strong>{t("admin.intakes.total_ht")}</strong><p>{formatAmount(detail.preview_quote.total_ht, detail.preview_quote.currency, language)}</p></div>
                <div><strong>{t("admin.intakes.total_vat")}</strong><p>{formatAmount(detail.preview_quote.total_vat, detail.preview_quote.currency, language)}</p></div>
                <div><strong>{t("admin.intakes.total_ttc")}</strong><p>{formatAmount(detail.preview_quote.total_ttc, detail.preview_quote.currency, language)}</p></div>
              </div>
            </>
          ) : (
            <p className="muted top-gap-sm">{t("admin.intakes.no_preview_quote")}</p>
          )}
        </article>
      </section>
    </section>
  );
}
