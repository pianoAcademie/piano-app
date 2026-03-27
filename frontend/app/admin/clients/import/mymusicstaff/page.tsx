import Link from "next/link";

import MyMusicStaffImporter from "../../../../../components/mymusicstaff-importer";

export default function AdminClientsMyMusicStaffImportPage(): JSX.Element {
  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread">
          <div>
            <h1>Import MyMusicStaff</h1>
            <p className="muted">
              Importe des eleves et leurs parents depuis le logiciel actuel, en preservant les relations de famille.
            </p>
          </div>
          <Link className="mode-link" href="/admin/clients">
            Retour clients
          </Link>
        </div>
      </section>

      <MyMusicStaffImporter />
    </section>
  );
}
