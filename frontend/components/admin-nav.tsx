import Link from "next/link";

type NavItem = {
  href: string;
  label: string;
};

const NAV_ITEMS: NavItem[] = [
  { href: "/admin", label: "Planning" },
  { href: "/admin/clients", label: "Clients" },
  { href: "/admin/professors", label: "Collaborateurs" },
  { href: "/admin/salary-payments", label: "Paiement des salaires" },
  { href: "/admin/communications", label: "Communications" },
  { href: "/admin/products", label: "Produits" },
  { href: "/admin/config", label: "Configuration" },
  { href: "/admin/reporting", label: "Reporting" },
];

export default function AdminNav(): JSX.Element {
  return (
    <nav className="admin-nav">
      {NAV_ITEMS.map((item) => (
        <Link key={item.href} href={item.href} className="admin-nav-link">
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
