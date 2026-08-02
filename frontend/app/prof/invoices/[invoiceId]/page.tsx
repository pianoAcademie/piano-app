import Link from "next/link";
import { redirect } from "next/navigation";

import {
  logoutAction,
  teacherCancelInvoiceAction,
  teacherSendInvoiceToAccountingAction,
  teacherUncancelInvoiceAction,
} from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import { getPortalReturnTo, getPortalToken, readPortalImpersonationClaims } from "../../../../lib/auth-cookies";
import { buildProfessorHelpLabels } from "../../../../lib/professor-help-labels";
import ActionCard from "../../../../components/teacher-ui/action-card";
import AlertCard from "../../../../components/teacher-ui/alert-card";
import BottomTabs from "../../../../components/teacher-ui/bottom-tabs";
import ProfessorHelpAssistant from "../../../../components/teacher-ui/help-assistant";
import ListRow from "../../../../components/teacher-ui/list-row";
import PageHeaderMobile from "../../../../components/teacher-ui/page-header-mobile";
import PortalImpersonationBanner from "../../../../components/portal-impersonation-banner";
import SectionAccordion from "../../../../components/teacher-ui/section-accordion";
import StatChip from "../../../../components/teacher-ui/stat-chip";
import type { TeacherInvoiceOut, UserOut } from "../../../../lib/types";
import { normalizeUiLanguage, type UiLanguage, uiText } from "../../../../lib/ui-i18n";

function profTabHref(tab: string): string {
  return `/prof?tab=${encodeURIComponent(tab)}`;
}

function formatDateLabel(value: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString(language === "en" ? "en-GB" : "fr-FR");
}

function invoiceStatusLabel(rawStatus: string, language: UiLanguage): string {
  const normalized = rawStatus.trim().toLowerCase();
  if (normalized === "sent_to_accounting") {
    return uiText(language, "teacher.invoice_status_sent_to_accounting");
  }
  if (normalized === "cancelled") {
    return uiText(language, "teacher.invoice_status_cancelled");
  }
  if (normalized === "generated") {
    return uiText(language, "teacher.invoice_status_generated");
  }
  return rawStatus;
}

export default async function TeacherInvoiceDetailPage({
  params,
  searchParams,
}: {
  params: { invoiceId: string };
  searchParams: Record<string, string | string[] | undefined>;
}): Promise<JSX.Element> {
  const token = getPortalToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const impersonationClaims = readPortalImpersonationClaims();
  const isImpersonating = Boolean(impersonationClaims?.imp);
  const impersonationReturnTo = getPortalReturnTo() ?? "/admin";
  const invoiceId = params.invoiceId;
  const ok = Array.isArray(searchParams.ok) ? searchParams.ok[0] : (searchParams.ok ?? "");
  const error = Array.isArray(searchParams.error) ? searchParams.error[0] : (searchParams.error ?? "");
  const impersonationNameHint = Array.isArray(searchParams.imp_name) ? searchParams.imp_name[0] ?? "" : searchParams.imp_name ?? "";

  const [meResult, result] = await Promise.all([
    backendRequest<UserOut>("/api/v1/auth/me", {}, token),
    backendRequest<TeacherInvoiceOut>(`/api/v1/teacher/invoices/${invoiceId}`, {}, token),
  ]);

  const language = normalizeUiLanguage(meResult.ok ? meResult.data.preferred_language : "fr");
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  if (!result.ok) {
    return <section className="flash-err">{t("teacher.teacher_invoice_error")}: {result.message}</section>;
  }
  const invoice = result.data;
  const impersonationDisplayName = impersonationNameHint.trim() || t("portal.teacher");

  return (
    <section className="page teacher-shell teacher-subpage">
      <PageHeaderMobile
        title={t("teacher.invoice_title", { number: invoice.invoice_number })}
        subtitle={`${invoice.payor_legal_entity_name} | ${formatDateLabel(invoice.invoice_date, language)}`}
        menuLabel={t("portal.teacher_menu")}
        trailing={
          <Link
            className="mode-link teacher-header-link"
            href={`/prof/statements?year=${invoice.invoice_date.slice(0, 4)}&month=${invoice.invoice_date.slice(5, 7)}`}
          >
            {t("teacher.back_to_statements")}
          </Link>
        }
        menu={
          <div className="teacher-header-menu-items">
            <Link className="teacher-header-menu-link" href="/prof">
              {t("common.home")}
            </Link>
            <form action={logoutAction}>
              <button className="ghost teacher-header-menu-btn" type="submit">
                {t("common.logout")}
              </button>
            </form>
          </div>
        }
      />

      <BottomTabs
        activeId="statements"
        ariaLabel={t("portal.mobile_teacher_nav")}
        items={[
          { id: "overview", label: t("teacher.todo"), icon: "📌", href: profTabHref("overview") },
          { id: "planning", label: t("teacher.planning"), icon: "📅", href: profTabHref("planning") },
          { id: "statements", label: t("teacher.statements"), icon: "🧾", href: "/prof/statements" },
          { id: "messages", label: t("teacher.messages"), icon: "✉️", href: profTabHref("messages") },
          { id: "profile", label: t("teacher.profile"), icon: "👤", href: profTabHref("profile") },
        ]}
      />

      {isImpersonating ? (
        <PortalImpersonationBanner displayName={impersonationDisplayName} returnTo={impersonationReturnTo} language={language} />
      ) : null}

      {ok ? <AlertCard tone="ok">{ok}</AlertCard> : null}
      {error ? <AlertCard tone="error">{error}</AlertCard> : null}

      <ActionCard title={t("teacher.invoice_actions")} subtitle={`${t("teacher.due_date")}: ${formatDateLabel(invoice.due_date, language)}`}>
        <div className="row teacher-actions-wrap">
          <a className="mode-link" href={`/api/v1/teacher/invoices/${invoice.id}/pdf`}>
            {t("teacher.download_pdf")}
          </a>
          <form action={teacherSendInvoiceToAccountingAction}>
            <input type="hidden" name="invoice_id" value={invoice.id} />
            <input type="hidden" name="return_to" value={`/prof/invoices/${invoice.id}`} />
            <button type="submit">{t("teacher.send_to_accounting")}</button>
          </form>
          {invoice.status === "cancelled" ? (
            <form action={teacherUncancelInvoiceAction}>
              <input type="hidden" name="invoice_id" value={invoice.id} />
              <input type="hidden" name="return_to" value={`/prof/invoices/${invoice.id}`} />
              <button type="submit">{t("teacher.reactivate")}</button>
            </form>
          ) : (
            <form action={teacherCancelInvoiceAction}>
              <input type="hidden" name="invoice_id" value={invoice.id} />
              <input type="hidden" name="return_to" value={`/prof/invoices/${invoice.id}`} />
              <button type="submit" className="danger">
                {t("teacher.cancel")}
              </button>
            </form>
          )}
        </div>
      </ActionCard>

      <ActionCard title={t("teacher.invoice_summary")} subtitle={t("teacher.invoice_summary_help")}>
        <div className="teacher-chip-row">
          <StatChip label={t("common.status")} value={invoiceStatusLabel(invoice.status, language)} tone={invoice.status === "cancelled" ? "warn" : "ok"} />
          <StatChip label={t("common.ht")} value={invoice.totals_ht} />
          <StatChip label={t("common.vat")} value={invoice.totals_vat} />
          <StatChip label={t("common.ttc")} value={invoice.totals_ttc} tone="ok" />
        </div>
        <div className="list teacher-list-compact">
          <ListRow left={t("teacher.teacher_siret")} right={invoice.teacher_siret_display} />
          <ListRow left="IBAN" right={invoice.teacher_iban} />
          <ListRow left={t("teacher.invoice_date")} right={formatDateLabel(invoice.invoice_date, language)} />
          <ListRow left={t("teacher.due_date")} right={formatDateLabel(invoice.due_date, language)} />
        </div>
      </ActionCard>

      <SectionAccordion title={t("teacher.invoice_lines")} defaultOpen={true}>
        <div className="list teacher-list-compact">
          {invoice.lines.map((line) => (
            <ListRow
              key={line.id}
              left={line.course_type_label}
              subtitle={`${line.hours} h | ${t("teacher.hourly_rate_excl_tax")} ${line.unit_rate_ht} | ${t("common.ht")} ${line.amount_ht}`}
              right={line.amount_ttc}
            />
          ))}
        </div>
      </SectionAccordion>
      <ProfessorHelpAssistant language={language} interfaceLabels={buildProfessorHelpLabels(language)} />
    </section>
  );
}
