"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import SearchMultiSelect from "./search-multi-select";

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
  returnTo: string;
  submitAction: (formData: FormData) => Promise<void>;
  initial?: ProspectInitial;
  parentCandidates: ParentCandidate[];
  focusTarget?: "child" | "parent" | null;
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
  returnTo,
  submitAction,
  initial,
  parentCandidates,
  focusTarget = null,
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
  const adultFirstNameRef = useRef<HTMLInputElement | null>(null);
  const childFirstNameRef = useRef<HTMLInputElement | null>(null);
  const parentFirstNameRef = useRef<HTMLInputElement | null>(null);
  const parentSectionRef = useRef<HTMLElement | null>(null);

  const defaultStatus = (() => {
    const status = String(initial?.status || "active").trim().toLowerCase();
    if (status === "converted" || status === "archived" || status === "lost" || status === "new") {
      return status as ProspectStatus;
    }
    return "active";
  })();

  useEffect(() => {
    const scrollAndMaybeFocus = (target: HTMLElement | null): void => {
      if (!target) {
        return;
      }
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      if ("focus" in target) {
        target.focus();
      }
    };

    if (prospectType === "adult") {
      scrollAndMaybeFocus(adultFirstNameRef.current);
      return;
    }
    if (focusTarget === "child") {
      scrollAndMaybeFocus(childFirstNameRef.current);
      return;
    }
    if (focusTarget === "parent") {
      if (parentMode === "new_parent") {
        scrollAndMaybeFocus(parentFirstNameRef.current);
        return;
      }
      scrollAndMaybeFocus(parentSectionRef.current);
    }
  }, [focusTarget, parentMode, prospectType]);

  return (
    <form action={submitAction} className="grid cols-2 config-form-grid">
      <input type="hidden" name="return_to" value={returnTo} />
      {initial?.id ? <input type="hidden" name="prospect_id" value={initial.id} /> : null}

      {prospectType === "child" && focusTarget === "child" ? (
        <section className="flash-ok span-2">
          Corrige ici les informations de l&apos;enfant, puis enregistre et reviens au devis.
        </section>
      ) : null}
      {prospectType === "child" && focusTarget === "parent" ? (
        <section className="flash-ok span-2">
          Corrige ici le parent referent, puis enregistre et reviens au devis.
        </section>
      ) : null}

      <label>
        Type de prospect
        <select name="prospect_type" value={prospectType} onChange={(event) => setProspectType(event.target.value === "child" ? "child" : "adult")}>
          <option value="adult">Adulte</option>
          <option value="child">Enfant</option>
        </select>
      </label>

      {mode === "edit" ? (
        <label>
          Statut
          <select name="status" defaultValue={defaultStatus}>
            <option value="active">Actif</option>
            <option value="new">Nouveau</option>
            <option value="lost">Perdu</option>
            <option value="converted">Converti</option>
            <option value="archived">Archive</option>
          </select>
        </label>
      ) : (
        <div />
      )}

      {prospectType === "adult" ? (
        <>
          <label>
            Prenom
            <input ref={adultFirstNameRef} type="text" name="adult_first_name" required defaultValue={initial?.first_name ?? ""} />
          </label>
          <label>
            Nom
            <input type="text" name="adult_last_name" required defaultValue={initial?.last_name ?? ""} />
          </label>
          <label>
            Email
            <input type="email" name="adult_email" required defaultValue={initial?.email ?? ""} />
          </label>
          <label>
            Telephone
            <input type="text" name="adult_phone" defaultValue={initial?.phone ?? ""} />
          </label>
          <label className="span-2">
            Adresse
            <input type="text" name="adult_address" defaultValue={defaultAdultAddress} />
          </label>
        </>
      ) : (
        <>
          <section className="card span-2" id="prospect-child-section">
            <h4>Eleve (enfant)</h4>
            <div className="grid cols-3 top-gap-sm">
              <label>
                Prenom enfant
                <input
                  ref={childFirstNameRef}
                  type="text"
                  name="child_first_name"
                  required
                  defaultValue={stringFromUnknown(childMeta.first_name) || (initial?.first_name ?? "")}
                />
              </label>
              <label>
                Nom enfant
                <input type="text" name="child_last_name" required defaultValue={stringFromUnknown(childMeta.last_name) || (initial?.last_name ?? "")} />
              </label>
              <label>
                Date de naissance
                <input type="date" name="child_birth_date" defaultValue={stringFromUnknown(childMeta.birth_date)} />
              </label>
            </div>
          </section>

          <section ref={parentSectionRef} className="card span-2" id="prospect-parent-section" tabIndex={-1}>
            <h4>Parent referent</h4>
            <fieldset className="top-gap-sm">
              <legend>Mode parent referent</legend>
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
                  Nouveau parent referent
                </label>
                <label className="checkline">
                  <input
                    type="radio"
                    name="parent_referent_mode"
                    value="existing_parent"
                    checked={parentMode === "existing_parent"}
                    onChange={() => setParentMode("existing_parent")}
                  />
                  Rattacher a un parent existant
                </label>
              </div>
            </fieldset>

            {parentMode === "existing_parent" ? (
              <div className="top-gap-sm">
                <SearchMultiSelect
                  label="Rechercher un parent"
                  name="parent_existing_prospect_id"
                  options={parentOptions}
                  selectedIds={selectedParentId ? [selectedParentId] : []}
                  onSelectionChange={(ids) => setSelectedParentId(ids[0] ?? "")}
                  placeholder="Prenom, nom, email, telephone..."
                  emptySelectionLabel="Aucun parent selectionne."
                  maxSelections={1}
                  requiredSelection
                  requiredSelectionMessage="Veuillez selectionner un parent existant ou revenir au mode nouveau parent referent."
                />
                {selectedParent ? (
                  <>
                    <input type="hidden" name="parent_existing_email" value={selectedParent.email} />
                    <input type="hidden" name="parent_existing_first_name" value={selectedParent.first_name ?? ""} />
                    <input type="hidden" name="parent_existing_last_name" value={selectedParent.last_name ?? ""} />
                    <input type="hidden" name="parent_existing_phone" value={selectedParent.phone ?? ""} />
                    <input type="hidden" name="parent_existing_address" value={selectedParent.address ?? ""} />
                    <article className="item top-gap-sm">
                      <strong>Parent selectionne</strong>
                      <p className="muted">
                        {displayName(selectedParent.first_name, selectedParent.last_name, selectedParent.email)}
                        {" · "}
                        {selectedParent.email}
                      </p>
                      <p className="muted">
                        Tel: {selectedParent.phone || "-"}
                        {" · "}
                        Adresse: {selectedParent.address || "-"}
                      </p>
                    </article>
                  </>
                ) : (
                  <p className="muted top-gap-sm">Aucun parent trouve ? Passez en mode nouveau parent referent.</p>
                )}
              </div>
            ) : (
              <div className="grid cols-3 top-gap-sm">
                <label>
                  Civilite
                  <input type="text" name="parent_title" placeholder="Mme/M." defaultValue={stringFromUnknown(parentMeta.title)} />
                </label>
                <label>
                  Prenom parent
                  <input
                    ref={parentFirstNameRef}
                    type="text"
                    name="parent_first_name"
                    required={parentMode === "new_parent"}
                    defaultValue={stringFromUnknown(parentMeta.first_name)}
                  />
                </label>
                <label>
                  Nom parent
                  <input type="text" name="parent_last_name" required={parentMode === "new_parent"} defaultValue={stringFromUnknown(parentMeta.last_name)} />
                </label>
                <label>
                  Email parent
                  <input
                    type="email"
                    name="parent_email"
                    required={parentMode === "new_parent"}
                    defaultValue={stringFromUnknown(parentMeta.email) || (initial?.email ?? "")}
                  />
                </label>
                <label>
                  Telephone parent
                  <input type="text" name="parent_phone" defaultValue={stringFromUnknown(parentMeta.phone) || (initial?.phone ?? "")} />
                </label>
                <label>
                  Adresse parent
                  <input type="text" name="parent_address" defaultValue={stringFromUnknown(parentMeta.address)} />
                </label>
              </div>
            )}
          </section>
        </>
      )}

      <label>
        Source
        <input type="text" name="source" defaultValue={initial?.source ?? ""} placeholder="site_web, telephone, salon..." />
      </label>

      <label>
        Notes
        <input type="text" name="notes" defaultValue={initial?.notes ?? ""} placeholder="Informations utiles" />
      </label>

      <div className="row span-2 top-gap-sm">
        <button type="submit">{mode === "create" ? "Creer prospect" : "Enregistrer prospect"}</button>
      </div>
    </form>
  );
}
