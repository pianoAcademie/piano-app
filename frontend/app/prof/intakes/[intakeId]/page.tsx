import Link from "next/link";
import { redirect } from "next/navigation";

import AlertCard from "../../../../components/teacher-ui/alert-card";
import PageHeaderMobile from "../../../../components/teacher-ui/page-header-mobile";
import ProfessorLocalIntakeForm from "../../../../components/professor-local-intake-form";
import { getProfessorPortalToken } from "../../../../lib/auth-cookies";
import { backendRequest } from "../../../../lib/backend";
import type { ProfessorLocalIntakeDetailOut, UserOut } from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function payloadText(payload: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (Array.isArray(value)) {
      const text = value.map((item) => String(item ?? "").trim()).filter(Boolean).join(", ");
      if (text) return text;
    }
  }
  return null;
}

export default async function ProfessorLocalIntakePage({
  params,
  searchParams,
}: {
  params: { intakeId: string };
  searchParams: SearchParams;
}): Promise<JSX.Element> {
  const token = getProfessorPortalToken();
  const returnTo = `/prof/intakes/${encodeURIComponent(params.intakeId)}`;
  if (!token) redirect(`/login?portal=prof&return_to=${encodeURIComponent(returnTo)}&error_code=session_expired`);

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "prof") redirect("/login?portal=prof&error_code=session_expired");
  const intakeResult = await backendRequest<ProfessorLocalIntakeDetailOut>(
    `/api/v1/professors/me/intakes/local-confirmations/${encodeURIComponent(params.intakeId)}`,
    {},
    token,
  );
  if (!intakeResult.ok) {
    return (
      <main className="page prof-page teacher-shell teacher-intake-page">
        <PageHeaderMobile title="Confirmation Bar-le-Duc" trailing={<Link className="mode-link" href="/prof">Retour</Link>} />
        <AlertCard tone="error">{intakeResult.message}</AlertCard>
      </main>
    );
  }

  const intake = intakeResult.data;
  const payload = intake.normalized_payload_json;
  const age = payloadText(payload, ["child_age", "student_age", "age"]);
  const contact = payloadText(payload, ["parent_email", "email"]);
  const phone = payloadText(payload, ["parent_phone", "phone"]);
  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");

  return (
    <main className="page prof-page teacher-shell teacher-intake-page">
      <PageHeaderMobile
        title="Confirmation Bar-le-Duc"
        subtitle={intake.child_label || intake.prospect_label}
        statusLabel={intake.local_confirmation_status === "CONFIRMED" ? "Confirmé" : "À confirmer"}
        trailing={<Link className="mode-link" href="/prof">Retour</Link>}
      />

      {ok ? <AlertCard tone="ok">{ok}</AlertCard> : null}
      {error ? <AlertCard tone="error">{error}</AlertCard> : null}

      <section className="card teacher-intake-summary">
        <div>
          <span className="eyebrow">Élève</span>
          <strong>{intake.child_label || intake.prospect_label}</strong>
          {age ? <small>{age}</small> : null}
        </div>
        <div>
          <span className="eyebrow">Responsable</span>
          <strong>{intake.prospect_label}</strong>
          <small>{[contact, phone].filter(Boolean).join(" · ") || "Coordonnées non renseignées"}</small>
        </div>
        <div>
          <span className="eyebrow">Demande</span>
          <strong>{intake.requested_summary || "Nouvel intake Bar-le-Duc"}</strong>
          <small>Reçu le {new Date(intake.received_at).toLocaleDateString("fr-FR", { timeZone: "Europe/Paris" })}</small>
        </div>
      </section>

      {intake.local_confirmation_status === "CONFIRMED" ? (
        <AlertCard tone="ok" title="Déjà confirmé">
          Vous pouvez modifier le créneau ou la partition ci-dessous si nécessaire.
        </AlertCard>
      ) : null}

      <section className="card teacher-intake-editor">
        <ProfessorLocalIntakeForm intake={intake} />
      </section>
    </main>
  );
}
