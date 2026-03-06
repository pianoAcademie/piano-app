import Link from "next/link";

type TeacherInvoicingNavTab = "hub" | "statements" | "invoices" | "template" | "salary-grid";

type TeacherInvoicingNavItem = {
  id: TeacherInvoicingNavTab;
  label: string;
  href: string;
};

const NAV_ITEMS: TeacherInvoicingNavItem[] = [
  { id: "statements", label: "Releves", href: "/admin/teacher-invoicing/statements" },
  { id: "invoices", label: "Factures", href: "/admin/teacher-invoicing/invoices" },
  { id: "template", label: "Template de facture", href: "/admin/teacher-invoicing/template" },
  { id: "salary-grid", label: "Grille de salaire", href: "/admin/teacher-invoicing/salary-grid" },
];

type AdminTeacherInvoicingNavProps = {
  activeTab: TeacherInvoicingNavTab;
};

export default function AdminTeacherInvoicingNav({ activeTab }: AdminTeacherInvoicingNavProps): JSX.Element {
  return (
    <section className="card teacher-invoicing-header-card">
      <div className="row spread teacher-invoicing-header-top">
        <div>
          <h2>Facturation professeurs</h2>
          <p className="muted">
            Gerez les releves, les factures, le modele de facture et la grille de salaire des professeurs.
          </p>
        </div>
        {activeTab === "hub" ? null : (
          <Link className="ghost" href="/admin/teacher-invoicing">
            Retour hub
          </Link>
        )}
      </div>

      <nav className="teacher-invoicing-tabs" aria-label="Sous-navigation facturation professeurs">
        {NAV_ITEMS.map((item) => (
          <Link key={item.id} href={item.href} className={`teacher-invoicing-tab ${activeTab === item.id ? "active" : ""}`}>
            {item.label}
          </Link>
        ))}
      </nav>
    </section>
  );
}
