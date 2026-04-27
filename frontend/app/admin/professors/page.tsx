import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { createAdminCollaboratorAction, sendAdminCollaboratorsMessageAction } from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import CollaboratorSelectionControls from "../../../components/collaborator-selection-controls";
import RichMessageEditor from "../../../components/rich-message-editor";
import type { AdminProfessorDetailOut, UserOut } from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

const COLLABORATOR_LANGUAGE_OPTIONS: Array<{ value: string; labelKey: string }> = [
  { value: "Francais", labelKey: "common.french" },
  { value: "Anglais", labelKey: "common.english" },
  { value: "Espagnol", labelKey: "common.spanish" },
  { value: "Italien", labelKey: "common.italian" },
  { value: "Allemand", labelKey: "common.german" },
  { value: "Portugais", labelKey: "common.portuguese" },
  { value: "Russe", labelKey: "common.russian" },
  { value: "Chinois", labelKey: "common.chinese" },
  { value: "Japonais", labelKey: "common.japanese" },
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

function formatAmount(value: string, currency: string, language: UiLanguage): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) {
    return `${value} ${currency}`;
  }
  try {
    return new Intl.NumberFormat(localeForUiLanguage(language), {
      style: "currency",
      currency: currency || "EUR",
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${(currency || "EUR").toUpperCase()}`;
  }
}

export default async function AdminCollaboratorsPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error=Acces%20admin%20requis");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const sortLocale = localeForUiLanguage(language);

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
        const lastNameCmp = (a.last_name || "").localeCompare(b.last_name || "", sortLocale, { sensitivity: "base" });
        if (lastNameCmp !== 0) {
          return nameSort === "desc" ? -lastNameCmp : lastNameCmp;
        }
        const firstNameCmp = (a.first_name || "").localeCompare(b.first_name || "", sortLocale, { sensitivity: "base" });
        if (firstNameCmp !== 0) {
          return nameSort === "desc" ? -firstNameCmp : firstNameCmp;
        }
        const emailCmp = (a.email || "").localeCompare(b.email || "", sortLocale, { sensitivity: "base" });
        return nameSort === "desc" ? -emailCmp : emailCmp;
      })
    : [];

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread">
          <h2>{t("admin.professors.title")}</h2>
          <span className="badge">{t("admin.professors.subtitle")}</span>
        </div>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {!collaboratorsResult.ok ? (
        <section className="flash-err">
          {t("admin.professors.backend_error")}: {collaboratorsResult.message}
        </section>
      ) : null}

      <section className="card">
        <h2>{t("common.filters")}</h2>
        <form method="get" className="grid cols-3">
          <label>
            {t("admin.professors.search_label")}
            <input type="text" name="search" defaultValue={search} placeholder={t("admin.professors.search_placeholder")} />
          </label>

          <label>
            {t("admin.professors.active_only")}
            <select name="active_only" defaultValue={activeOnly ? "1" : "0"}>
              <option value="0">{t("common.no")}</option>
              <option value="1">{t("common.yes")}</option>
            </select>
          </label>

            <label>
              {t("admin.professors.name_sort")}
              <select name="name_sort" defaultValue={nameSort}>
                <option value="asc">{t("admin.professors.sort_asc")}</option>
                <option value="desc">{t("admin.professors.sort_desc")}</option>
              </select>
            </label>

            <label>
              {t("admin.professors.payout_as_of")}
              <input type="date" name="payout_as_of" defaultValue={payoutAsOf} />
            </label>

          <div className="row">
            <button type="submit">{t("common.apply")}</button>
            <a className="reset-link" href="/admin/professors">
              {t("common.reset")}
            </a>
          </div>
        </form>
      </section>

      <section className="card">
        <div className="row spread">
          <h2>{t("admin.professors.add_title")}</h2>
          <a className="icon-add-button" href={openCreateHref} aria-label={t("admin.professors.add_button_aria")}>
            <span className="icon-add-button-plus" aria-hidden="true">
              +
            </span>
            {t("admin.professors.add_button")}
          </a>
        </div>
        <p className="muted">{t("admin.professors.add_subtitle")}</p>
      </section>

      <section className="card">
        <h2>{t("admin.professors.list_title")}</h2>
        {collaboratorsResult.ok ? (
          <form id="collaborators-message-form" action={sendAdminCollaboratorsMessageAction} className="stack-sm">
            <input type="hidden" name="return_to" value={closeCreateHref} />
            <CollaboratorSelectionControls
              formId="collaborators-message-form"
              selectAllLabel={t("admin.professors.selection_all")}
              summaryLabel={t("admin.professors.selection_summary")}
              language={language}
            />
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t("admin.professors.select_short")}</th>
                    <th>{t("admin.professors.last_name")}</th>
                    <th>{t("admin.professors.first_name")}</th>
                    <th>{t("admin.professors.phone_short")}</th>
                    <th>{t("common.status")}</th>
                    <th>{t("admin.professors.payout_balance")}</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedCollaborators.map((professor) => {
                    const statusLabel = professor.active ? t("common.active") : t("common.inactive");
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
                          {formatAmount(payoutAmount, payoutCurrency, language)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {sortedCollaborators.length === 0 ? <p className="muted">{t("admin.professors.no_results")}</p> : null}
            </div>

            <details>
              <summary>{t("admin.professors.messaging_summary")}</summary>
              <div className="grid cols-2" style={{ marginTop: "0.75rem" }}>
                <label className="span-2">
                  {t("admin.professors.subject_label")}
                  <input type="text" name="subject" maxLength={255} placeholder={t("admin.professors.subject_placeholder")} />
                </label>
                <label className="span-2">
                  {t("admin.professors.message_label")}
                  <RichMessageEditor
                    name="body"
                    formatName="body_format"
                    rows={8}
                    maxLength={12000}
                    placeholder={t("admin.professors.message_placeholder")}
                    language={language}
                    labels={{
                      editorModeAria: t("admin.professors.editor_mode_aria"),
                      wysiwygMode: t("admin.professors.editor_mode_wysiwyg"),
                      htmlMode: t("admin.professors.editor_mode_html"),
                      textMode: t("admin.professors.editor_mode_text"),
                      formattingToolsAria: t("admin.professors.editor_toolbar_aria"),
                      unorderedList: t("admin.professors.editor_unordered_list"),
                      orderedList: t("admin.professors.editor_ordered_list"),
                      fontPlaceholder: t("admin.professors.editor_font_placeholder"),
                      sizePlaceholder: t("admin.professors.editor_size_placeholder"),
                      textColor: t("admin.professors.editor_text_color"),
                      highlightColor: t("admin.professors.editor_highlight_color"),
                      insertLink: t("admin.professors.editor_insert_link"),
                      insertImageUrl: t("admin.professors.editor_insert_image_url"),
                      insertImageFile: t("admin.professors.editor_insert_image_file"),
                      addFile: t("admin.professors.editor_add_file"),
                      linkPrompt: t("admin.professors.editor_link_prompt"),
                      imagePrompt: t("admin.professors.editor_image_prompt"),
                      defaultFileName: t("admin.professors.editor_default_file_name"),
                      defaultImageName: t("admin.professors.editor_default_image_name"),
                    }}
                  />
                </label>
                <div className="row">
                  <button type="submit" name="channel" value="EMAIL">
                    {t("admin.professors.email_action")}
                  </button>
                  <button type="submit" className="ghost" name="channel" value="SMS">
                    {t("admin.professors.sms_action")}
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
            <a className="modal-close-x" href={closeCreateHref} aria-label={t("common.close")}>
              ×
            </a>
            <h2 className="modal-title">{t("admin.professors.create_title")}</h2>
            <p className="muted">{t("admin.professors.create_subtitle")}</p>
            <form action={createAdminCollaboratorAction} className="grid cols-3">
              <label>
                {t("common.email")}
                <input type="email" name="email" required />
              </label>

              <label>
                {t("admin.professors.payout_currency")}
                <select name="payout_currency" defaultValue="EUR">
                  <option value="EUR">EUR</option>
                  <option value="USD">USD</option>
                </select>
              </label>

              <label>
                {t("admin.professors.first_name")}
                <input type="text" name="first_name" required maxLength={100} />
              </label>

              <label>
                {t("admin.professors.last_name")}
                <input type="text" name="last_name" required maxLength={100} />
              </label>

              <label>
                {t("admin.professors.phone")}
                <input type="text" name="phone" maxLength={30} />
              </label>

              <label>
                {t("admin.professors.siret_label")}
                <input type="text" name="siret" maxLength={30} placeholder={t("admin.professors.siret_placeholder")} />
              </label>

              <label>
                {t("admin.professors.iban_label")}
                <input type="text" name="iban" maxLength={34} placeholder={t("admin.professors.iban_placeholder")} />
              </label>

              <label className="span-2">
                {t("admin.professors.zoom_link")}
                <input type="url" name="zoom_link" placeholder={t("admin.professors.zoom_placeholder")} />
              </label>

              <label className="span-2">
                {t("admin.professors.address")}
                <input type="text" name="address_line" maxLength={255} placeholder={t("admin.professors.address_placeholder")} />
              </label>

              <label>
                {t("admin.professors.spoken_languages")}
                <select name="spoken_languages" multiple size={6}>
                  {COLLABORATOR_LANGUAGE_OPTIONS.map((language) => (
                    <option key={language.value} value={language.value}>
                      {t(language.labelKey)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="checkline">
                <input type="checkbox" name="is_coach" defaultChecked />
                {t("admin.professors.coach_mode")}
              </label>

              <label className="checkline">
                <input type="checkbox" name="is_admin" />
                {t("admin.professors.administrator_right")}
              </label>

              <label className="checkline">
                <input type="checkbox" name="daily_schedule_email_enabled" />
                {t("admin.professors.daily_schedule_email")}
              </label>

              <label>
                {t("admin.professors.daily_schedule_time")}
                <input type="time" name="daily_schedule_email_time" defaultValue="07:00" />
              </label>

              <label className="checkline">
                <input type="checkbox" name="daily_schedule_skip_if_no_course" defaultChecked />
                {t("admin.professors.skip_if_no_course")}
              </label>

              <label className="checkline">
                <input type="checkbox" name="can_view_all_school_sessions" />
                {t("admin.professors.view_all_school_sessions")}
              </label>

              <p className="muted span-3">{t("admin.professors.presence_enabled_hint")}</p>

              <div className="row span-3">
                <button type="submit">{t("admin.professors.create_button")}</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}
    </section>
  );
}
