import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import QuoteToEnrollmentWizard from "../../../../../components/quotes/quote-to-enrollment-wizard";
import {
  finalizeQuoteTransformationAction,
  saveQuoteTransformationDraftAction,
} from "../../../../../lib/actions";
import { backendRequest } from "../../../../../lib/backend";
import {
  coerceQuoteToEnrollmentDraft,
  readObject,
  type QuoteTransformActivityCatalog,
  type QuoteTransformClient,
  type QuoteTransformLegalEntity,
  type QuoteTransformLine,
  type QuoteTransformPlan,
  type QuoteTransformProspect,
  type QuoteTransformQuote,
  type QuoteTransformScenario,
  type QuoteTransformSession,
} from "../../../../../lib/quote-transformation";
import type {
  AdminActivityOut,
  AdminClientOut,
  AdminLegalEntityOut,
  AdminSessionOut,
  LocationOut,
  PlanOut,
} from "../../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

type RouteParams = {
  params: {
    quoteId: string;
  };
  searchParams: SearchParams;
};

type QuoteLineOut = {
  id: string;
  line_type: string;
  line_category: string;
  master_item_type: string | null;
  activity_id: string | null;
  title: string;
  quantity: string;
  duration_minutes: number | null;
  pricing_unit: string | null;
  vat_rate: string;
  amount_ht: string;
  amount_ttc: string;
  meta: Record<string, unknown>;
};

type QuoteOut = {
  id: string;
  quote_number: string;
  status: string;
  currency: string;
  total_ttc: string;
  school_year_label: string | null;
  legal_entity_id: string | null;
  payment_plan_id: string | null;
  quote_type: string;
  quote_type_id: string | null;
  location_id: string | null;
  context_type: string;
  prospect_id: string | null;
  client_id: string | null;
  calendar_snapshot: Record<string, unknown>;
  payment_terms_snapshot: Record<string, unknown>;
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

type ProspectOut = {
  id: string;
  first_name: string | null;
  last_name: string | null;
  email: string;
  phone: string | null;
  parent_prospect_id: string | null;
  meta: Record<string, unknown>;
};

type QuoteTypeOut = {
  id: string;
  name: string;
  formula_id: string | null;
  formula_name: string | null;
};

type PaymentPlanOut = {
  id: string;
  name: string;
};

function readParam(params: SearchParams, key: string): string {
  const raw = params[key];
  if (Array.isArray(raw)) {
    return raw[0] ?? "";
  }
  return raw ?? "";
}

function safeBackPath(raw: string, quoteId: string): string {
  const value = raw.trim();
  if (value.startsWith("/admin/quotes")) {
    return value;
  }
  return `/admin/quotes/${encodeURIComponent(quoteId)}?section=integration`;
}

function parseScenario(raw: string): QuoteTransformScenario {
  const value = String(raw || "").trim().toUpperCase();
  if (value === "A" || value === "B" || value === "C") {
    return value;
  }
  return "live";
}

function parsePreferredStep(raw: string): 1 | 2 | 3 | 4 | 5 | null {
  if (!String(raw || "").trim()) {
    return null;
  }
  const parsed = Number.parseInt(String(raw || "").trim(), 10);
  if (parsed === 1 || parsed === 2 || parsed === 3 || parsed === 4 || parsed === 5) {
    return parsed;
  }
  return null;
}

function toNumber(raw: string, fallback = 0): number {
  const parsed = Number(String(raw || "").replace(",", "."));
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return parsed;
}

function locationNameById(locations: LocationOut[], locationId: string | null): string {
  if (!locationId) {
    return "Lieu non defini";
  }
  return locations.find((location) => location.id === locationId)?.name || "Lieu non defini";
}

function scheduleOptionLinks(basePath: string, scenario: QuoteTransformScenario): Array<{ scenario: QuoteTransformScenario; label: string; href: string; active: boolean }> {
  const items: Array<{ scenario: QuoteTransformScenario; label: string }> = [
    { scenario: "live", label: "Live" },
    { scenario: "A", label: "Scenario A (simple)" },
    { scenario: "B", label: "Scenario B (ambigu)" },
    { scenario: "C", label: "Scenario C (bloquant)" },
  ];

  return items.map((item) => {
    const separator = basePath.includes("?") ? "&" : "?";
    return {
      scenario: item.scenario,
      label: item.label,
      href: `${basePath}${separator}scenario=${encodeURIComponent(item.scenario)}`,
      active: item.scenario === scenario,
    };
  });
}

export default async function AdminQuoteTransformPage({ params, searchParams }: RouteParams): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const quoteId = String(params.quoteId || "").trim();
  if (!quoteId) {
    redirect("/admin/quotes?error=Devis%20introuvable");
  }

  const backPath = safeBackPath(readParam(searchParams, "back"), quoteId);
  const scenario = parseScenario(readParam(searchParams, "scenario"));
  const preferredStep = parsePreferredStep(readParam(searchParams, "step"));
  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");

  const [detailResult, followupsResult, clientsResult, activitiesResult, plansResult, legalEntitiesResult, locationsResult, quoteTypesResult, paymentPlansResult] = await Promise.all([
    backendRequest<QuoteDetailOut>(`/api/v1/quotes/${encodeURIComponent(quoteId)}`, {}, token),
    backendRequest<QuoteFollowupOut[]>(`/api/v1/quote-followups?quote_id=${encodeURIComponent(quoteId)}`, {}, token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?limit=1000&include_archived=false", {}, token),
    backendRequest<AdminActivityOut[]>("/api/v1/admin/activities?include_inactive=true", {}, token),
    backendRequest<PlanOut[]>("/api/v1/plans?active=true", {}, token),
    backendRequest<AdminLegalEntityOut[]>("/api/v1/admin/legal-entities?include_inactive=false", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=false", {}, token),
    backendRequest<QuoteTypeOut[]>("/api/v1/quote-types", {}, token),
    backendRequest<PaymentPlanOut[]>("/api/v1/payment-plans", {}, token),
  ]);

  if (!detailResult.ok) {
    return (
      <section className="admin-page-grid">
        <section className="card">
          <h2>Transformation devis</h2>
          <p className="flash-err">{detailResult.message}</p>
          <div className="row top-gap-sm">
            <Link className="ghost" href={backPath}>Retour devis</Link>
          </div>
        </section>
      </section>
    );
  }

  const detail = detailResult.data;
  const clientsRaw = clientsResult.ok ? clientsResult.data : [];
  const activitiesRaw = activitiesResult.ok ? activitiesResult.data : [];
  const plansRaw = plansResult.ok ? plansResult.data : [];
  const legalEntitiesRaw = legalEntitiesResult.ok ? legalEntitiesResult.data : [];
  const locationsRaw = locationsResult.ok ? locationsResult.data : [];
  const quoteTypes = quoteTypesResult.ok ? quoteTypesResult.data : [];
  const paymentPlans = paymentPlansResult.ok ? paymentPlansResult.data : [];

  const activityIds = Array.from(new Set(
    detail.lines
      .map((line) => line.activity_id)
      .filter((activityId): activityId is string => Boolean(activityId)),
  ));

  const sessionsPerActivity = await Promise.all(
    activityIds.map(async (activityId) => {
      const query = new URLSearchParams();
      query.set("course_type_id", activityId);
      if (detail.quote.location_id) {
        query.set("location_id", detail.quote.location_id);
      }
      const path = `/api/v1/admin/sessions?${query.toString()}`;
      const result = await backendRequest<AdminSessionOut[]>(path, {}, token);
      return {
        activityId,
        sessions: result.ok ? result.data : [],
      };
    }),
  );

  const prospectResult = detail.quote.prospect_id
    ? await backendRequest<ProspectOut>(`/api/v1/prospects/${encodeURIComponent(detail.quote.prospect_id)}`, {}, token)
    : null;

  const followups = followupsResult.ok ? followupsResult.data.slice() : [];
  followups.sort((left, right) => {
    const leftTime = Date.parse(left.updated_at || left.created_at || "");
    const rightTime = Date.parse(right.updated_at || right.created_at || "");
    return (Number.isFinite(rightTime) ? rightTime : 0) - (Number.isFinite(leftTime) ? leftTime : 0);
  });
  const activeFollowup =
    followups.find((row) => String(row.status || "").toLowerCase() !== "completed")
    || followups[0]
    || null;
  const followupPayload = readObject(activeFollowup?.payload) || {};
  const initialDraft = coerceQuoteToEnrollmentDraft(followupPayload.quote_to_enrollment);

  const prospectRaw = prospectResult && prospectResult.ok ? prospectResult.data : null;
  const prospectTypeRaw = String((prospectRaw?.meta || {}).prospect_type || "adult").trim().toLowerCase();
  const sourceClientRaw = detail.quote.client_id
    ? clientsRaw.find((client) => client.id === detail.quote.client_id) || null
    : null;
  const fallbackProspectTypeRaw = String(sourceClientRaw?.client_kind || "").trim().toUpperCase();
  const prospect: QuoteTransformProspect | null = prospectRaw
    ? {
      id: prospectRaw.id,
      firstName: prospectRaw.first_name,
      lastName: prospectRaw.last_name,
      email: prospectRaw.email,
      phone: prospectRaw.phone,
      parentProspectId: prospectRaw.parent_prospect_id,
      prospectType: prospectTypeRaw === "child" ? "child" : "adult",
      meta: prospectRaw.meta || {},
    }
    : sourceClientRaw
    ? {
      id: `client:${sourceClientRaw.id}`,
      firstName: sourceClientRaw.first_name,
      lastName: sourceClientRaw.last_name,
      email: sourceClientRaw.email,
      phone: sourceClientRaw.mobile_phone_1 || sourceClientRaw.phone || sourceClientRaw.home_phone,
      parentProspectId: null,
      prospectType: fallbackProspectTypeRaw === "CHILD" ? "child" : "adult",
      meta: {
        source: "linked_client_fallback",
        linked_client_id: sourceClientRaw.id,
      },
    }
    : null;

  const clients: QuoteTransformClient[] = clientsRaw.map((client) => ({
    id: client.id,
    firstName: client.first_name,
    lastName: client.last_name,
    email: client.email,
    phone: client.phone,
    mobilePhone1: client.mobile_phone_1,
    mobilePhone2: client.mobile_phone_2,
    homePhone: client.home_phone,
    familyName: client.family_name,
    clientKind: client.client_kind,
    clientStatus: client.client_status,
  }));

  const activities: QuoteTransformActivityCatalog[] = activitiesRaw.map((activity) => ({
    id: activity.id,
    name: activity.name,
    serviceCode: activity.service_code,
    durationMinutes: activity.duration_minutes,
    defaultCourseRateTtc: activity.default_course_rate_ttc ? toNumber(activity.default_course_rate_ttc) : null,
    mode: activity.mode,
    active: activity.active,
  }));

  const sessionsByActivityId: Record<string, QuoteTransformSession[]> = {};
  for (const item of sessionsPerActivity) {
    sessionsByActivityId[item.activityId] = item.sessions.map((session) => {
      const seatsRemaining = Math.max(0, Number(session.capacity_max || 0) - Number(session.booked_count || 0));
      return {
        id: session.id,
        courseTypeId: session.course_type_id,
        locationId: session.location_id,
        title: session.title,
        startAtUtc: session.start_at_utc,
        endAtUtc: session.end_at_utc,
        timezone: session.timezone,
        teacherDisplayName: session.effective_teacher_display_name,
        status: session.status,
        statusLabel: session.status_label,
        capacityMax: session.capacity_max,
        bookedCount: session.booked_count,
        seatsRemaining,
      } satisfies QuoteTransformSession;
    });
  }

  const plans: QuoteTransformPlan[] = plansRaw.map((plan) => ({
    id: plan.id,
    name: plan.name,
    kind: plan.kind,
    active: plan.active,
  }));

  const legalEntities: QuoteTransformLegalEntity[] = legalEntitiesRaw.map((entity) => ({
    id: entity.id,
    name: entity.name,
  }));

  const quoteType = quoteTypes.find((row) => row.id === detail.quote.quote_type_id) || null;
  const paymentPlan = paymentPlans.find((row) => row.id === detail.quote.payment_plan_id) || null;
  const legalEntityName = legalEntities.find((entity) => entity.id === detail.quote.legal_entity_id)?.name || "A definir";

  const lines: QuoteTransformLine[] = detail.lines.map((line) => ({
    id: line.id,
    lineType: line.line_type,
    lineCategory: line.line_category,
    masterItemType: line.master_item_type,
    activityId: line.activity_id,
    title: line.title,
    quantity: toNumber(line.quantity, 1),
    durationMinutes: line.duration_minutes,
    pricingUnit: line.pricing_unit,
    amountHt: toNumber(line.amount_ht),
    amountTtc: toNumber(line.amount_ttc),
    vatRate: toNumber(line.vat_rate),
    meta: line.meta || {},
  }));

  const quote: QuoteTransformQuote = {
    id: detail.quote.id,
    quoteNumber: detail.quote.quote_number,
    status: detail.quote.status,
    currency: detail.quote.currency || "EUR",
    totalTtc: toNumber(detail.quote.total_ttc),
    totalHt: Number(lines.reduce((sum, line) => sum + line.amountHt, 0).toFixed(2)),
    schoolYearLabel: detail.quote.school_year_label,
    legalEntityId: detail.quote.legal_entity_id,
    legalEntityName,
    paymentPlanName: paymentPlan?.name || String((detail.quote.payment_terms_snapshot || {}).payment_plan_name || "-"),
    quoteType: detail.quote.quote_type,
    quoteTypeFormulaName: quoteType?.formula_name || null,
    locationId: detail.quote.location_id,
    locationName: locationNameById(locationsRaw, detail.quote.location_id),
  };

  const basePath = `/admin/quotes/${encodeURIComponent(quoteId)}/transform?back=${encodeURIComponent(backPath)}`;
  const scenarioLinks = scheduleOptionLinks(basePath, scenario);

  return (
    <section className="admin-page-grid">
      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}

      <QuoteToEnrollmentWizard
        quote={quote}
        prospect={prospect}
        lines={lines}
        calendarSnapshot={detail.quote.calendar_snapshot || {}}
        clients={clients}
        activities={activities}
        sessionsByActivityId={sessionsByActivityId}
        plans={plans}
        legalEntities={legalEntities}
        scenario={scenario}
        scenarioLinks={scenarioLinks}
        preferredStep={preferredStep}
        followupId={activeFollowup?.id || null}
        followupStatus={activeFollowup?.status || null}
        initialDraft={initialDraft}
        backPath={backPath}
        returnTo={basePath}
        saveDraftAction={saveQuoteTransformationDraftAction}
        finalizeAction={finalizeQuoteTransformationAction}
      />
    </section>
  );
}
