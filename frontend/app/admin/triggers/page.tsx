import Link from "next/link";
import { redirect } from "next/navigation";

import {
  createAutomationTriggerAction,
  deleteAutomationTriggerAction,
  updateAutomationTriggerAction,
} from "../../../lib/actions";
import { getAdminToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import type { CourseTypeOut, LocationOut, PlanOut, UserOut } from "../../../lib/types";
import styles from "./triggers.module.css";

type SearchParams = Record<string, string | string[] | undefined>;
type TriggerRule = {
  id: string; name: string; event_type: string; template_ref: string;
  plan_id: string | null; course_type_id: string | null; location_id: string | null;
  client_kind: string | null; delay_minutes: number; active: boolean;
};
type MessagingTemplate = { id: string; code: string | null; name: string; kind: string; channel: string; active: boolean };

function param(params: SearchParams, key: string): string {
  const value = params[key];
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

const EVENT_LABELS: Record<string, string> = {
  PLAN_PURCHASE_CONFIRMED: "Achat d'une formule confirmé",
  TRIAL_COURSE_ATTENDED: "Cours d'essai effectué",
  FIRST_STUDIO_BOOKING_CREATED: "Première réservation de studio dans ce lieu",
};

function templateRef(template: MessagingTemplate): string {
  return template.kind === "CUSTOM" ? `custom:${template.id}` : `predefined:${template.code}`;
}

function RuleFields({
  rule, plans, courseTypes, locations, templates,
}: {
  rule?: TriggerRule; plans: PlanOut[]; courseTypes: CourseTypeOut[]; locations: LocationOut[]; templates: MessagingTemplate[];
}): JSX.Element {
  return (
    <>
      <label className={`${styles.field} ${styles.wide}`}><span>Nom du trigger *</span><input name="name" required maxLength={160} defaultValue={rule?.name ?? ""} placeholder="Ex. Livret après achat essai adulte" /></label>
      <label className={styles.field}><span>Déclencheur *</span><select name="event_type" required defaultValue={rule?.event_type ?? "PLAN_PURCHASE_CONFIRMED"}>
        {Object.entries(EVENT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label className={styles.field}><span>Email à envoyer *</span><select name="template_ref" required defaultValue={rule?.template_ref ?? "predefined:AUTOMATION_TRIAL_ADULT_BOOKING_GUIDE"}>
        {templates.map((template) => <option key={templateRef(template)} value={templateRef(template)}>{template.name}</option>)}
      </select></label>
      <label className={styles.field}><span>Formule achetée</span><select name="plan_id" defaultValue={rule?.plan_id ?? ""}><option value="">— Non applicable —</option>{plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name}</option>)}</select></label>
      <label className={styles.field}><span>Type de cours (facultatif)</span><select name="course_type_id" defaultValue={rule?.course_type_id ?? ""}><option value="">Tous les types</option>{courseTypes.map((course) => <option key={course.id} value={course.id}>{course.name}</option>)}</select></label>
      <label className={styles.field}><span>Lieu (facultatif)</span><select name="location_id" defaultValue={rule?.location_id ?? ""}><option value="">Tous les lieux</option>{locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select></label>
      <label className={styles.field}><span>Public (facultatif)</span><select name="client_kind" defaultValue={rule?.client_kind ?? ""}><option value="">Adultes et enfants</option><option value="ADULT">Adulte</option><option value="CHILD">Enfant / adolescent (email au responsable)</option></select></label>
      <label className={styles.field}><span>Délai avant envoi</span><select name="delay_minutes" defaultValue={String(rule?.delay_minutes ?? 0)}><option value="0">Immédiatement</option><option value="30">30 minutes</option><option value="60">1 heure</option><option value="1440">1 jour</option><option value="2880">2 jours</option><option value="10080">7 jours</option></select></label>
      <label className={styles.check}><input type="checkbox" name="active" defaultChecked={rule?.active ?? true} /> Actif</label>
    </>
  );
}

export default async function AdminTriggersPage({ searchParams = {} }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = getAdminToken();
  if (!token) redirect("/login?error_code=session_expired");
  const [meResult, rulesResult, plansResult, courseTypesResult, locationsResult, templatesResult] = await Promise.all([
    backendRequest<UserOut>("/api/v1/auth/me", {}, token),
    backendRequest<TriggerRule[]>("/api/v1/admin/triggers", {}, token),
    backendRequest<PlanOut[]>("/api/v1/plans", {}, token),
    backendRequest<CourseTypeOut[]>("/api/v1/course-types", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations", {}, token),
    backendRequest<MessagingTemplate[]>("/api/v1/admin/config/messaging-templates?channel=EMAIL&active_only=true", {}, token),
  ]);
  if (!meResult.ok || meResult.data.role !== "admin") redirect("/admin?error=Accès%20non%20autorisé");
  const rules = rulesResult.ok ? rulesResult.data : [];
  const plans = plansResult.ok ? plansResult.data : [];
  const courseTypes = courseTypesResult.ok ? courseTypesResult.data : [];
  const locations = locationsResult.ok ? locationsResult.data : [];
  const templates = templatesResult.ok ? templatesResult.data : [];
  const error = param(searchParams, "error") || (!rulesResult.ok ? rulesResult.message : "");
  const ok = param(searchParams, "ok");
  const planNames = new Map(plans.map((item) => [item.id, item.name]));
  const courseNames = new Map(courseTypes.map((item) => [item.id, item.name]));
  const locationNames = new Map(locations.map((item) => [item.id, item.name]));

  return <main className={styles.page}>
    <section className={styles.hero}><div><h1>Triggers</h1><p className="muted">Automatisez un email à partir d'une action réelle du client.</p></div><span className={styles.metric}>{rules.filter((rule) => rule.active).length} actif(s)</span></section>
    {ok ? <p className="notice success">{ok}</p> : null}{error ? <p className="notice error">{error}</p> : null}
    <p className={styles.help}><strong>Fonctionnement :</strong> choisissez le déclencheur, affinez avec la formule, le type de cours, le lieu ou le public, puis sélectionnez un modèle email. Les modèles se créent dans <Link href="/admin/config?section=messaging">Configuration → Messagerie</Link>. Un même événement ne peut être envoyé qu'une fois par trigger.</p>
    <details className={styles.panel} open={rules.length === 0}><summary><strong>Créer un trigger</strong></summary><form action={createAutomationTriggerAction} className={styles.form}><RuleFields plans={plans} courseTypes={courseTypes} locations={locations} templates={templates} /><div className={styles.actions}><button type="submit">Créer et activer</button></div></form></details>
    <section className={styles.rules} aria-label="Triggers configurés">
      {rules.map((rule) => <article className={styles.rule} key={rule.id}>
        <div className={styles.ruleHeader}><div><h2>{rule.name}</h2><p>{EVENT_LABELS[rule.event_type] ?? rule.event_type}</p></div><span className={`${styles.badge} ${rule.active ? styles.active : styles.inactive}`}>{rule.active ? "Actif" : "Inactif"}</span></div>
        <div className={styles.badges}>{rule.plan_id ? <span className={styles.badge}>Formule : {planNames.get(rule.plan_id) ?? rule.plan_id}</span> : null}{rule.course_type_id ? <span className={styles.badge}>Cours : {courseNames.get(rule.course_type_id) ?? rule.course_type_id}</span> : null}{rule.location_id ? <span className={styles.badge}>Lieu : {locationNames.get(rule.location_id) ?? rule.location_id}</span> : null}{rule.client_kind ? <span className={styles.badge}>{rule.client_kind === "ADULT" ? "Adultes" : "Enfants"}</span> : null}{rule.delay_minutes ? <span className={styles.badge}>Délai : {rule.delay_minutes} min</span> : <span className={styles.badge}>Envoi immédiat</span>}</div>
        <details><summary>Modifier</summary><form action={updateAutomationTriggerAction} className={styles.form}><input type="hidden" name="rule_id" value={rule.id} /><RuleFields rule={rule} plans={plans} courseTypes={courseTypes} locations={locations} templates={templates} /><div className={styles.actions}><button type="submit">Enregistrer</button></div></form><form action={deleteAutomationTriggerAction} className={styles.actions}><input type="hidden" name="rule_id" value={rule.id} /><button className={styles.danger} type="submit">Supprimer</button></form></details>
      </article>)}
      {!rules.length ? <p className={styles.panel}>Aucun trigger pour le moment.</p> : null}
    </section>
  </main>;
}
