import Link from "next/link";
import { type UiLanguage, uiText } from "../lib/ui-i18n";

type TeacherInvoicingNavTab = "hub" | "statements" | "invoices" | "template" | "salary-grid";

type TeacherInvoicingNavItem = {
  id: TeacherInvoicingNavTab;
  labelKey: string;
  href: string;
};

const NAV_ITEMS: TeacherInvoicingNavItem[] = [
  { id: "statements", labelKey: "admin.teacher_invoicing.statements", href: "/admin/teacher-invoicing/statements" },
  { id: "invoices", labelKey: "common.invoices", href: "/admin/teacher-invoicing/invoices" },
  { id: "template", labelKey: "admin.teacher_invoicing.invoice_template", href: "/admin/teacher-invoicing/template" },
  { id: "salary-grid", labelKey: "admin.teacher_invoicing.salary_grid", href: "/admin/teacher-invoicing/salary-grid" },
];

type AdminTeacherInvoicingNavProps = {
  activeTab: TeacherInvoicingNavTab;
  language?: UiLanguage;
};

export default function AdminTeacherInvoicingNav({ activeTab, language = "fr" }: AdminTeacherInvoicingNavProps): JSX.Element {
  return (
    <section className="card teacher-invoicing-header-card">
      <div className="row spread teacher-invoicing-header-top">
        <div>
          <h2>{uiText(language, "admin.teacher_invoicing.title")}</h2>
          <p className="muted">
            {uiText(language, "admin.teacher_invoicing.subtitle")}
          </p>
        </div>
        {activeTab === "hub" ? null : (
          <Link className="ghost" href="/admin/teacher-invoicing">
            {uiText(language, "admin.teacher_invoicing.back_hub")}
          </Link>
        )}
      </div>

      <nav className="teacher-invoicing-tabs" aria-label={uiText(language, "admin.teacher_invoicing.subnav_aria")}>
        {NAV_ITEMS.map((item) => (
          <Link key={item.id} href={item.href} className={`teacher-invoicing-tab ${activeTab === item.id ? "active" : ""}`}>
            {uiText(language, item.labelKey)}
          </Link>
        ))}
      </nav>
    </section>
  );
}
