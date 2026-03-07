"use client";

import { useMemo, useState } from "react";

type ProspectStatus = "active" | "converted" | "archived" | "lost" | "new";

type ProspectInitial = {
  id?: string;
  status?: string;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  phone?: string | null;
  source?: string | null;
  notes?: string | null;
  meta?: Record<string, unknown>;
};

type AdminProspectFormProps = {
  mode: "create" | "edit";
  returnTo: string;
  submitAction: (formData: FormData) => Promise<void>;
  initial?: ProspectInitial;
};

function stringFromUnknown(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export default function AdminProspectForm({ mode, returnTo, submitAction, initial }: AdminProspectFormProps): JSX.Element {
  const initialMeta = (initial?.meta ?? {}) as Record<string, unknown>;
  const initialType = String(initialMeta.prospect_type || "").trim().toLowerCase() === "child" ? "child" : "adult";
  const [prospectType, setProspectType] = useState<"adult" | "child">(initialType);

  const childMeta = useMemo(() => {
    const raw = initialMeta.child;
    return raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  }, [initialMeta.child]);

  const parentMeta = useMemo(() => {
    const raw = initialMeta.parent_referent;
    return raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  }, [initialMeta.parent_referent]);

  const defaultAdultAddress = stringFromUnknown(initialMeta.adult_address);

  const defaultStatus = (() => {
    const status = String(initial?.status || "active").trim().toLowerCase();
    if (status === "converted" || status === "archived" || status === "lost" || status === "new") {
      return status as ProspectStatus;
    }
    return "active";
  })();

  return (
    <form action={submitAction} className="grid cols-2 config-form-grid">
      <input type="hidden" name="return_to" value={returnTo} />
      {initial?.id ? <input type="hidden" name="prospect_id" value={initial.id} /> : null}

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
            <input type="text" name="adult_first_name" required defaultValue={initial?.first_name ?? ""} />
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
          <section className="card span-2">
            <h4>Eleve (enfant)</h4>
            <div className="grid cols-3 top-gap-sm">
              <label>
                Prenom enfant
                <input type="text" name="child_first_name" required defaultValue={stringFromUnknown(childMeta.first_name) || (initial?.first_name ?? "")} />
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

          <section className="card span-2">
            <h4>Parent referent</h4>
            <div className="grid cols-3 top-gap-sm">
              <label>
                Civilite
                <input type="text" name="parent_title" placeholder="Mme/M." defaultValue={stringFromUnknown(parentMeta.title)} />
              </label>
              <label>
                Prenom parent
                <input type="text" name="parent_first_name" required defaultValue={stringFromUnknown(parentMeta.first_name)} />
              </label>
              <label>
                Nom parent
                <input type="text" name="parent_last_name" required defaultValue={stringFromUnknown(parentMeta.last_name)} />
              </label>
              <label>
                Email parent
                <input type="email" name="parent_email" required defaultValue={stringFromUnknown(parentMeta.email) || (initial?.email ?? "")} />
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
