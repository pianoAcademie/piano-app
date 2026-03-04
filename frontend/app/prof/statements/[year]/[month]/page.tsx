import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { logoutAction, teacherApproveStatementsAction, teacherDisputeStatementsAction } from "../../../../../lib/actions";
import { backendRequest } from "../../../../../lib/backend";
import ActionCard from "../../../../../components/teacher-ui/action-card";
import AlertCard from "../../../../../components/teacher-ui/alert-card";
import BottomTabs from "../../../../../components/teacher-ui/bottom-tabs";
import ListRow from "../../../../../components/teacher-ui/list-row";
import PageHeaderMobile from "../../../../../components/teacher-ui/page-header-mobile";
import SectionAccordion from "../../../../../components/teacher-ui/section-accordion";
import StatChip from "../../../../../components/teacher-ui/stat-chip";
import type { TeacherStatementOut } from "../../../../../lib/types";

const MONTH_LABELS = [
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

function profTabHref(tab: string): string {
  return `/prof?tab=${encodeURIComponent(tab)}`;
}

export default async function TeacherStatementMonthDetailPage({
  params,
  searchParams,
}: {
  params: { year: string; month: string };
  searchParams: Record<string, string | string[] | undefined>;
}): Promise<JSX.Element> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  const year = Number.parseInt(params.year, 10);
  const month = Number.parseInt(params.month, 10);
  if (!Number.isFinite(year) || !Number.isFinite(month)) {
    redirect("/prof/statements?error=Periode%20invalide");
  }

  const ok = Array.isArray(searchParams.ok) ? searchParams.ok[0] : (searchParams.ok ?? "");
  const error = Array.isArray(searchParams.error) ? searchParams.error[0] : (searchParams.error ?? "");
  const statementsResult = await backendRequest<TeacherStatementOut[]>(`/api/v1/teacher/statements/${year}/${month}`, {}, token);
  if (!statementsResult.ok) {
    return <section className="flash-err">Erreur releve detail: {statementsResult.message}</section>;
  }

  const monthLabel = MONTH_LABELS[Math.max(1, Math.min(12, month)) - 1] ?? String(month);

  return (
    <section className="page teacher-shell teacher-subpage">
      <PageHeaderMobile
        title="Detail des releves"
        subtitle={`${monthLabel} ${year}`}
        trailing={
          <Link className="mode-link teacher-header-link" href={`/prof/statements?year=${year}&month=${month}`}>
            Retour releves
          </Link>
        }
        menu={
          <div className="teacher-header-menu-items">
            <Link className="teacher-header-menu-link" href="/prof">
              Accueil
            </Link>
            <form action={logoutAction}>
              <button className="ghost teacher-header-menu-btn" type="submit">
                Se deconnecter
              </button>
            </form>
          </div>
        }
      />

      <BottomTabs
        activeId="statements"
        items={[
          { id: "overview", label: "A traiter", icon: "📌", href: profTabHref("overview") },
          { id: "planning", label: "Planning", icon: "📅", href: profTabHref("planning") },
          { id: "statements", label: "Releves", icon: "🧾", href: "/prof/statements" },
          { id: "messages", label: "Messages", icon: "✉️", href: profTabHref("messages") },
          { id: "profile", label: "Profil", icon: "👤", href: profTabHref("profile") },
        ]}
      />

      {ok ? <AlertCard tone="ok">{ok}</AlertCard> : null}
      {error ? <AlertCard tone="error">{error}</AlertCard> : null}

      <ActionCard title="Actions" subtitle="Validation ou signalement sur la periode.">
        <div className="row teacher-actions-wrap">
          <form action={teacherApproveStatementsAction}>
            <input type="hidden" name="year" value={year} />
            <input type="hidden" name="month" value={month} />
            <input type="hidden" name="return_to" value={`/prof/statements/${year}/${month}`} />
            <button type="submit">Approuver et generer</button>
          </form>
          <form action={teacherDisputeStatementsAction} className="teacher-dispute-form">
            <input type="hidden" name="year" value={year} />
            <input type="hidden" name="month" value={month} />
            <input type="hidden" name="return_to" value={`/prof/statements/${year}/${month}`} />
            <input type="text" name="message" placeholder="Motif du litige" required />
            <button type="submit" className="ghost">
              Litige
            </button>
          </form>
        </div>
      </ActionCard>

      <div className="grid teacher-entity-grid">
        {statementsResult.data.map((statement) => (
          <article key={statement.payor_legal_entity_id} className="card">
            <div className="row spread">
              <strong>{statement.payor_legal_entity_name}</strong>
              <span className={`status-pill ${statement.attendance_complete ? "status-ok" : "status-warn"}`}>
                {statement.attendance_complete ? statement.status : "Presences a renseigner"}
              </span>
            </div>

            <div className="teacher-chip-row">
              <StatChip label="HT" value={`${statement.totals_ht} ${statement.currency}`} />
              <StatChip label="TVA" value={`${statement.totals_vat} ${statement.currency}`} />
              <StatChip label="TTC" value={`${statement.totals_ttc} ${statement.currency}`} tone="ok" />
            </div>

            <SectionAccordion title="Lignes de releve" defaultOpen={true}>
              <div className="list teacher-list-compact">
                {statement.lines.map((line) => (
                  <ListRow
                    key={`${statement.payor_legal_entity_id}-${line.course_type_id ?? line.course_type_label}`}
                    left={line.course_type_label}
                    subtitle={`${line.hours} h | Taux HT ${line.unit_rate_ht}`}
                    right={`${line.amount_ttc} ${statement.currency}`}
                  />
                ))}
              </div>
            </SectionAccordion>

            {!statement.attendance_complete ? (
              <SectionAccordion
                title="Presences a renseigner"
                subtitle="Completer avant approbation"
                badge={<span className="status-pill status-warn">{statement.missing_sessions.length}</span>}
              >
                <div className="list teacher-list-compact">
                  {statement.missing_sessions.map((row) => (
                    <ListRow
                      key={row.session_id}
                      left={row.title}
                      subtitle={`${new Date(row.start_at_utc).toLocaleString("fr-FR")} | ${row.pending_students_count}/${row.total_students_count}`}
                    />
                  ))}
                </div>
              </SectionAccordion>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
