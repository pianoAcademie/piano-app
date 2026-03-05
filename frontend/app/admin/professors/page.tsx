import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { createAdminCollaboratorAction, sendAdminCollaboratorsMessageAction } from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import CollaboratorSelectionControls from "../../../components/collaborator-selection-controls";
import RichMessageEditor from "../../../components/rich-message-editor";
import type { AdminProfessorDetailOut } from "../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

const COLLABORATOR_LANGUAGE_OPTIONS: string[] = [
  "Francais",
  "Anglais",
  "Espagnol",
  "Italien",
  "Allemand",
  "Portugais",
  "Russe",
  "Chinois",
  "Japonais",
];

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
}

export default async function AdminCollaboratorsPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const search = readParam(searchParams, "search").trim();
  const activeOnly = readParam(searchParams, "active_only") === "1";
  const nameSort = readParam(searchParams, "name_sort") === "desc" ? "desc" : "asc";
  const createOpen = readParam(searchParams, "create") === "1";
  const payoutAsOf = readParam(searchParams, "payout_as_of").trim() || todayIsoDate();

  const query = new URLSearchParams();
  if (search) {
    query.set("search", search);
  }
  if (activeOnly) {
    query.set("active_only", "true");
  }
  query.set("name_sort", nameSort);
  query.set("payout_as_of", payoutAsOf);

  const endpoint = query.toString() ? `/api/v1/admin/collaborators?${query.toString()}` : "/api/v1/admin/collaborators";
  const collaboratorsResult = await backendRequest<AdminProfessorDetailOut[]>(endpoint, {}, token);

  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error");
  const closeCreateParams = new URLSearchParams();
  if (search) {
    closeCreateParams.set("search", search);
  }
  if (activeOnly) {
    closeCreateParams.set("active_only", "1");
  }
  closeCreateParams.set("name_sort", nameSort);
  closeCreateParams.set("payout_as_of", payoutAsOf);
  const closeCreateHref = closeCreateParams.toString() ? `/admin/professors?${closeCreateParams.toString()}` : "/admin/professors";
  const openCreateHref = `${closeCreateHref}${closeCreateHref.includes("?") ? "&" : "?"}create=1`;

  const sortedCollaborators = collaboratorsResult.ok
    ? [...collaboratorsResult.data].sort((a, b) => {
        const lastNameCmp = (a.last_name || "").localeCompare(b.last_name || "", "fr", { sensitivity: "base" });
        if (lastNameCmp !== 0) {
          return nameSort === "desc" ? -lastNameCmp : lastNameCmp;
        }
        const firstNameCmp = (a.first_name || "").localeCompare(b.first_name || "", "fr", { sensitivity: "base" });
        if (firstNameCmp !== 0) {
          return nameSort === "desc" ? -firstNameCmp : firstNameCmp;
        }
        const emailCmp = (a.email || "").localeCompare(b.email || "", "fr", { sensitivity: "base" });
        return nameSort === "desc" ? -emailCmp : emailCmp;
      })
    : [];

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread">
          <h2>Collaborateurs</h2>
          <span className="badge">Gestion professeurs: fiche, droits, taux, planning</span>
        </div>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {!collaboratorsResult.ok ? <section className="flash-err">Erreur backend: {collaboratorsResult.message}</section> : null}

      <section className="card">
        <h2>Filtres</h2>
        <form method="get" className="grid cols-3">
          <label>
            Recherche (nom, prenom, email)
            <input type="text" name="search" defaultValue={search} placeholder="ex: fortunato, coach@..." />
          </label>

          <label>
            Collaborateurs actifs uniquement
            <select name="active_only" defaultValue={activeOnly ? "1" : "0"}>
              <option value="0">Non</option>
              <option value="1">Oui</option>
            </select>
          </label>

            <label>
              Tri nom
              <select name="name_sort" defaultValue={nameSort}>
                <option value="asc">A vers Z</option>
                <option value="desc">Z vers A</option>
              </select>
            </label>

            <label>
              Solde de paie calcule au
              <input type="date" name="payout_as_of" defaultValue={payoutAsOf} />
            </label>

          <div className="row">
            <button type="submit">Appliquer</button>
            <a className="reset-link" href="/admin/professors">
              Reinitialiser
            </a>
          </div>
        </form>
      </section>

      <section className="card">
        <div className="row spread">
          <h2>Ajout coach</h2>
          <a className="icon-add-button" href={openCreateHref} aria-label="Ajouter un collaborateur">
            <span className="icon-add-button-plus" aria-hidden="true">
              +
            </span>
            Ajouter
          </a>
        </div>
        <p className="muted">Creation via popup. Mot de passe genere automatiquement et envoye par email.</p>
      </section>

      <section className="card">
        <h2>Liste des collaborateurs</h2>
        {collaboratorsResult.ok ? (
          <form id="collaborators-message-form" action={sendAdminCollaboratorsMessageAction} className="stack-sm">
            <input type="hidden" name="return_to" value={closeCreateHref} />
            <CollaboratorSelectionControls formId="collaborators-message-form" />
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Sel.</th>
                    <th>Nom</th>
                    <th>Prenom</th>
                    <th>Tel</th>
                    <th>Etat</th>
                    <th>Solde paie</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedCollaborators.map((professor) => {
                    const statusLabel = professor.active ? "Actif" : "Inactif";
                    const payoutCurrency = professor.payout_balance_currency || professor.payout_currency || "EUR";
                    const payoutAmount = professor.payout_balance_amount || "0.00";
                    return (
                      <tr key={professor.id}>
                        <td>
                          <input type="checkbox" name="collaborator_ids" value={professor.id} />
                        </td>
                        <td>
                          <Link className="mode-link" href={`/admin/professors/${professor.id}?tab=profil`}>
                            {professor.last_name || "-"}
                          </Link>
                        </td>
                        <td>{professor.first_name || "-"}</td>
                        <td>{professor.phone || "-"}</td>
                        <td>
                          <span className={`status-pill ${professor.active ? "status-ok" : "status-off"}`}>{statusLabel}</span>
                        </td>
                        <td>
                          {payoutAmount} {payoutCurrency}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {sortedCollaborators.length === 0 ? <p className="muted">Aucun collaborateur pour ces filtres.</p> : null}
            </div>

            <details>
              <summary>Messagerie (collaborateurs selectionnes)</summary>
              <div className="grid cols-2" style={{ marginTop: "0.75rem" }}>
                <label className="span-2">
                  Sujet (obligatoire pour email, optionnel pour SMS)
                  <input type="text" name="subject" maxLength={255} placeholder="Objet du message" />
                </label>
                <label className="span-2">
                  Message
                  <RichMessageEditor
                    name="body"
                    formatName="body_format"
                    rows={8}
                    maxLength={12000}
                    placeholder="Contenu du message"
                  />
                </label>
                <div className="row">
                  <button type="submit" name="channel" value="EMAIL">
                    Nouveau courriel
                  </button>
                  <button type="submit" className="ghost" name="channel" value="SMS">
                    Envoyer SMS
                  </button>
                </div>
              </div>
            </details>
          </form>
        ) : null}
      </section>

      {createOpen ? (
        <section className="modal-overlay">
          <article className="modal-panel">
            <a className="modal-close-x" href={closeCreateHref} aria-label="Fermer">
              ×
            </a>
            <h2 className="modal-title">Nouveau collaborateur</h2>
            <p className="muted">Email, prenom et nom sont obligatoires. Le mot de passe est genere et envoye automatiquement.</p>
            <form action={createAdminCollaboratorAction} className="grid cols-3">
              <label>
                Email
                <input type="email" name="email" required />
              </label>

              <label>
                Devise de paiement
                <select name="payout_currency" defaultValue="EUR">
                  <option value="EUR">EUR</option>
                  <option value="USD">USD</option>
                </select>
              </label>

              <label>
                Prenom
                <input type="text" name="first_name" required maxLength={100} />
              </label>

              <label>
                Nom
                <input type="text" name="last_name" required maxLength={100} />
              </label>

              <label>
                Telephone
                <input type="text" name="phone" maxLength={30} />
              </label>

              <label>
                SIRET
                <input type="text" name="siret" maxLength={30} placeholder="ex: 82805141700010" />
              </label>

              <label>
                IBAN
                <input type="text" name="iban" maxLength={34} placeholder="ex: FR761234..." />
              </label>

              <label className="span-2">
                Lien Zoom
                <input type="url" name="zoom_link" placeholder="https://zoom.us/j/..." />
              </label>

              <label className="span-2">
                Adresse
                <input type="text" name="address_line" maxLength={255} placeholder="ex: 10 rue Michelet, 75010 Paris" />
              </label>

              <label>
                Langues (selection multiple)
                <select name="spoken_languages" multiple size={6}>
                  {COLLABORATOR_LANGUAGE_OPTIONS.map((language) => (
                    <option key={language} value={language}>
                      {language}
                    </option>
                  ))}
                </select>
              </label>

              <label className="checkline">
                <input type="checkbox" name="is_coach" defaultChecked />
                Mode coach (planning)
              </label>

              <label className="checkline">
                <input type="checkbox" name="is_admin" />
                Droit administrateur
              </label>

              <label className="checkline">
                <input type="checkbox" name="daily_schedule_email_enabled" />
                Activer email quotidien planning
              </label>

              <label>
                Heure email quotidien (UTC)
                <input type="time" name="daily_schedule_email_time" defaultValue="07:00" />
              </label>

              <label className="checkline">
                <input type="checkbox" name="daily_schedule_skip_if_no_course" defaultChecked />
                Ne pas envoyer si aucun cours
              </label>

              <label className="checkline">
                <input type="checkbox" name="can_view_all_school_sessions" />
                Voir tous les creneaux de l'ecole
              </label>

              <p className="muted span-3">La saisie de presence eleve est activee par defaut pour tout collaborateur cree.</p>

              <div className="row span-3">
                <button type="submit">Creer le collaborateur</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}
    </section>
  );
}
