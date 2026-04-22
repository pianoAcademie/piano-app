"use client";

import { useMemo, useState } from "react";
import SearchMultiSelect from "./search-multi-select";
import { type UiLanguage, uiText } from "../lib/ui-i18n";

type ProspectStatus = "active" | "converted" | "archived" | "lost" | "new";
type ParentMode = "new_parent" | "existing_parent";

type ProspectInitial = {
  id?: string;
  status?: string;
  parent_prospect_id?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  phone?: string | null;
  source?: string | null;
  notes?: string | null;
  meta?: Record<string, unknown>;
};

type ParentCandidate = {
  id: string;
  first_name: string | null;
  last_name: string | null;
  email: string;
  phone: string | null;
  address: string | null;
};

type AdminProspectFormProps = {
  mode: "create" | "edit";
  language?: UiLanguage;
  returnTo: string;
  submitAction: (formData: FormData) => Promise<void>;
  initial?: ProspectInitial;
  parentCandidates: ParentCandidate[];
};

function stringFromUnknown(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function displayName(firstName: string | null, lastName: string | null, fallback: string): string {
  const value = [firstName, lastName].filter(Boolean).join(" ").trim();
  return value || fallback;
}

export default function AdminProspectForm({
  mode,
  language = "fr",
  returnTo,
  submitAction,
  initial,
  parentCandidates,
}: AdminProspectFormProps): JSX.Element {
  const initialMeta = (initial?.meta ?? {}) as Record<string, unknown>;
  const initialType = String(initialMeta.prospect_type || "").trim().toLowerCase() === "child" ? "child" : "adult";
  const [prospectType, setProspectType] = useState<"adult" | "child">(initialType);
  const initialParentProspectId = (initial?.parent_prospect_id ?? stringFromUnknown(initialMeta.parent_existing_prospect_id)).trim();
  const initialParentModeRaw = stringFromUnknown(initialMeta.parent_referent_mode).toLowerCase();
  const initialParentMode: ParentMode = initialParentProspectId || initialParentModeRaw === "existing_parent" ? "existing_parent" : "new_parent";
  const [parentMode, setParentMode] = useState<ParentMode>(initialParentMode);
  const [selectedParentId, setSelectedParentId] = useState<string>(initialParentProspectId);

  const childMeta = useMemo(() => {
    const raw = initialMeta.child;
    return raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  }, [initialMeta.child]);

  const parentMeta = useMemo(() => {
    const raw = initialMeta.parent_referent;
    return raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  }, [initialMeta.parent_referent]);
  const selectedParent = useMemo(
    () => parentCandidates.find((row) => row.id === selectedParentId) ?? null,
    [parentCandidates, selectedParentId],
  );
  const parentOptions = useMemo(
    () =>
      parentCandidates.map((row) => ({
        id: row.id,
        label: `${displayName(row.first_name, row.last_name, row.email)} · ${row.email}${row.phone ? ` · ${row.phone}` : ""}`,
      })),
    [parentCandidates],
  );

  const defaultAdultAddress = stringFromUnknown(initialMeta.adult_address);

  const defaultStatus = (() => {
    const status = String(initial?.status || "active").trim().toLowerCase();
    if (status === "converted" || status === "archived" || status === "lost" || status === "new") {
      return status as ProspectStatus;
    }
    return "active";
  })();
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  return (
    <form action={submitAction} className="grid cols-2 config-form-grid">
      <input type="hidden" name="return_to" value={returnTo} />
      {initial?.id ? <input type="hidden" name="prospect_id" value={initial.id} /> : null}

      <label>
        {t("admin.prospects.form_type")}
        <select name="prospect_type" value={prospectType} onChange={(event) => setProspectType(event.target.value === "child" ? "child" : "adult")}>
          <option value="adult">{t("admin.prospects.type_adult")}</option>
          <option value="child">{t("admin.prospects.type_child")}</option>
        </select>
      </label>

      {mode === "edit" ? (
        <label>
          {uiText(language, "common.status")}
          <select name="status" defaultValue={defaultStatus}>
            <option value="active">{t("admin.prospects.status_active")}</option>
            <option value="new">{t("admin.prospects.status_new")}</option>
            <option value="lost">{t("admin.prospects.status_lost")}</option>
            <option value="converted">{t("admin.prospects.status_converted")}</option>
            <option value="archived">{t("admin.prospects.status_archived")}</option>
          </select>
        </label>
      ) : (
        <div />
      )}

      {prospectType === "adult" ? (
        <>
          <label>
            {t("admin.prospects.form_first_name")}
            <input type="text" name="adult_first_name" required defaultValue={initial?.first_name ?? ""} />
          </label>
          <label>
            {t("admin.prospects.form_last_name")}
            <input type="text" name="adult_last_name" required defaultValue={initial?.last_name ?? ""} />
          </label>
          <label>
            {uiText(language, "common.email")}
            <input type="email" name="adult_email" required defaultValue={initial?.email ?? ""} />
          </label>
          <label>
            {t("admin.prospects.form_phone")}
            <input type="text" name="adult_phone" defaultValue={initial?.phone ?? ""} />
          </label>
          <label className="span-2">
            {t("admin.prospects.form_address")}
            <input type="text" name="adult_address" defaultValue={defaultAdultAddress} />
          </label>
        </>
      ) : (
        <>
          <section className="card span-2">
            <h4>{t("admin.prospects.child_section")}</h4>
            <div className="grid cols-3 top-gap-sm">
              <label>
                {t("admin.prospects.child_first_name")}
                <input type="text" name="child_first_name" required defaultValue={stringFromUnknown(childMeta.first_name) || (initial?.first_name ?? "")} />
              </label>
              <label>
                {t("admin.prospects.child_last_name")}
                <input type="text" name="child_last_name" required defaultValue={stringFromUnknown(childMeta.last_name) || (initial?.last_name ?? "")} />
              </label>
              <label>
                {t("admin.prospects.child_birth_date")}
                <input type="date" name="child_birth_date" defaultValue={stringFromUnknown(childMeta.birth_date)} />
              </label>
            </div>
          </section>

          <section className="card span-2">
            <h4>{t("admin.prospects.parent_referent")}</h4>
            <fieldset className="top-gap-sm">
              <legend>{t("admin.prospects.parent_mode")}</legend>
              <div className="row wrap gap-sm">
                <label className="checkline">
                  <input
                    type="radio"
                    name="parent_referent_mode"
                    value="new_parent"
                    checked={parentMode === "new_parent"}
                    onChange={() => {
                      setParentMode("new_parent");
                      setSelectedParentId("");
                    }}
                  />
                  {t("admin.prospects.new_parent_referent")}
                </label>
                <label className="checkline">
                  <input
                    type="radio"
                    name="parent_referent_mode"
                    value="existing_parent"
                    checked={parentMode === "existing_parent"}
                    onChange={() => setParentMode("existing_parent")}
                  />
                  {t("admin.prospects.link_existing_parent")}
                </label>
              </div>
            </fieldset>

            {parentMode === "existing_parent" ? (
              <div className="top-gap-sm">
                <SearchMultiSelect
                  label={t("admin.prospects.search_parent")}
                  name="parent_existing_prospect_id"
                  options={parentOptions}
                  selectedIds={selectedParentId ? [selectedParentId] : []}
                  onSelectionChange={(ids) => setSelectedParentId(ids[0] ?? "")}
                  placeholder={t("admin.prospects.search_parent_placeholder")}
                  emptySelectionLabel={t("admin.prospects.no_parent_selected")}
                  emptySummaryLabel={t("admin.prospects.selection_empty")}
                  maxSelections={1}
                  requiredSelection
                  requiredSelectionMessage={t("admin.prospects.select_existing_parent_required")}
                  selectedCountLabel={t("admin.prospects.selection_count")}
                  removeOptionLabel={t("admin.prospects.remove_option")}
                  clearLabel={t("admin.prospects.clear_selection")}
                  availableOptionsLabel={t("admin.prospects.available_options")}
                  noResultsLabel={t("admin.prospects.no_results_short")}
                  limitResultsLabel={t("admin.prospects.results_limit")}
                />
                {selectedParent ? (
                  <>
                    <input type="hidden" name="parent_existing_email" value={selectedParent.email} />
                    <input type="hidden" name="parent_existing_first_name" value={selectedParent.first_name ?? ""} />
                    <input type="hidden" name="parent_existing_last_name" value={selectedParent.last_name ?? ""} />
                    <input type="hidden" name="parent_existing_phone" value={selectedParent.phone ?? ""} />
                    <input type="hidden" name="parent_existing_address" value={selectedParent.address ?? ""} />
                    <article className="item top-gap-sm">
                      <strong>{t("admin.prospects.selected_parent")}</strong>
                      <p className="muted">
                        {displayName(selectedParent.first_name, selectedParent.last_name, selectedParent.email)}
                        {" · "}
                        {selectedParent.email}
                      </p>
                      <p className="muted">
                        {t("admin.prospects.phone_short")}: {selectedParent.phone || "-"}
                        {" · "}
                        {t("admin.prospects.address_short")}: {selectedParent.address || "-"}
                      </p>
                    </article>
                  </>
                ) : (
                  <p className="muted top-gap-sm">{t("admin.prospects.no_parent_found_hint")}</p>
                )}
              </div>
            ) : (
              <div className="grid cols-3 top-gap-sm">
                <label>
                  {t("admin.prospects.parent_title")}
                  <input type="text" name="parent_title" placeholder={t("admin.prospects.parent_title_placeholder")} defaultValue={stringFromUnknown(parentMeta.title)} />
                </label>
                <label>
                  {t("admin.prospects.parent_first_name")}
                  <input type="text" name="parent_first_name" required={parentMode === "new_parent"} defaultValue={stringFromUnknown(parentMeta.first_name)} />
                </label>
                <label>
                  {t("admin.prospects.parent_last_name")}
                  <input type="text" name="parent_last_name" required={parentMode === "new_parent"} defaultValue={stringFromUnknown(parentMeta.last_name)} />
                </label>
                <label>
                  {t("admin.prospects.parent_email")}
                  <input
                    type="email"
                    name="parent_email"
                    required={parentMode === "new_parent"}
                    defaultValue={stringFromUnknown(parentMeta.email) || (initial?.email ?? "")}
                  />
                </label>
                <label>
                  {t("admin.prospects.parent_phone")}
                  <input type="text" name="parent_phone" defaultValue={stringFromUnknown(parentMeta.phone) || (initial?.phone ?? "")} />
                </label>
                <label>
                  {t("admin.prospects.parent_address")}
                  <input type="text" name="parent_address" defaultValue={stringFromUnknown(parentMeta.address)} />
                </label>
              </div>
            )}
          </section>
        </>
      )}

      <label>
        {uiText(language, "common.source")}
        <input type="text" name="source" defaultValue={initial?.source ?? ""} placeholder={t("admin.prospects.source_form_placeholder")} />
      </label>

      <label>
        {uiText(language, "common.notes")}
        <input type="text" name="notes" defaultValue={initial?.notes ?? ""} placeholder={t("admin.prospects.notes_placeholder")} />
      </label>

      <div className="row span-2 top-gap-sm">
        <button type="submit">{mode === "create" ? t("admin.prospects.create_prospect") : t("admin.prospects.save_prospect")}</button>
      </div>
    </form>
  );
}
