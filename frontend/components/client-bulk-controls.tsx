"use client";

import { useEffect, useMemo, useState } from "react";

type GroupOption = {
  id: string;
  name: string;
};

type SelectionScope = "PAGE" | "FILTERED";

type Props = {
  groups: GroupOption[];
  pageCount: number;
  filteredCount: number;
};

function getForm(): HTMLFormElement | null {
  const form = document.getElementById("clients-bulk-form");
  if (form instanceof HTMLFormElement) {
    return form;
  }
  return null;
}

function allPageCheckboxes(form: HTMLFormElement): HTMLInputElement[] {
  return Array.from(form.querySelectorAll<HTMLInputElement>('input[name="client_ids"]'));
}

function checkedClientIds(form: HTMLFormElement): string[] {
  return allPageCheckboxes(form)
    .filter((field) => field.checked)
    .map((field) => field.value)
    .filter((value) => value.length > 0);
}

function filteredClientIds(form: HTMLFormElement): string[] {
  return Array.from(form.querySelectorAll<HTMLInputElement>('input[name="filtered_client_ids"]'))
    .map((field) => field.value)
    .filter((value) => value.length > 0);
}

function setPageChecked(form: HTMLFormElement, checked: boolean): void {
  for (const box of allPageCheckboxes(form)) {
    box.checked = checked;
  }
}

function syncHeaderToggle(form: HTMLFormElement): number {
  const boxes = allPageCheckboxes(form);
  const selected = boxes.filter((box) => box.checked).length;
  const headerToggle = form.querySelector<HTMLInputElement>('input[data-role="select-page-toggle"]');
  if (headerToggle) {
    headerToggle.checked = boxes.length > 0 && selected === boxes.length;
    headerToggle.indeterminate = selected > 0 && selected < boxes.length;
  }
  return selected;
}

export default function ClientBulkControls({ groups, pageCount, filteredCount }: Props): JSX.Element {
  const [action, setAction] = useState("UPDATE_STATUS");
  const [selectionScope, setSelectionScope] = useState<SelectionScope>("PAGE");
  const [selectedOnPage, setSelectedOnPage] = useState(0);

  const canPickGroup = useMemo(() => action === "ASSIGN_GROUP", [action]);
  const canPickStatus = useMemo(() => action === "UPDATE_STATUS", [action]);

  useEffect(() => {
    const form = getForm();
    if (!form) {
      return;
    }

    const onAnyChange = (): void => {
      setSelectedOnPage(syncHeaderToggle(form));
    };

    const headerToggle = form.querySelector<HTMLInputElement>('input[data-role="select-page-toggle"]');
    const onHeaderToggle = (): void => {
      if (!headerToggle) {
        return;
      }
      setPageChecked(form, headerToggle.checked);
      setSelectionScope("PAGE");
      onAnyChange();
    };

    if (headerToggle) {
      headerToggle.addEventListener("change", onHeaderToggle);
    }
    form.addEventListener("change", onAnyChange);
    onAnyChange();

    return () => {
      if (headerToggle) {
        headerToggle.removeEventListener("change", onHeaderToggle);
      }
      form.removeEventListener("change", onAnyChange);
    };
  }, [pageCount, filteredCount]);

  return (
    <div className="grid client-bulk-grid">
      <input type="hidden" name="selection_scope" value={selectionScope} />

      <div className="row bulk-controls-row">
        <label className="bulk-inline-field">
          Action
          <select name="bulk_action" value={action} onChange={(event) => setAction(event.target.value)}>
            <option value="UPDATE_STATUS">Mettre a jour les statuts</option>
            <option value="ASSIGN_GROUP">Affecter a un groupe</option>
            <option value="ARCHIVE">Archiver</option>
            <option value="EMAIL_CLIENTS">Envoyer email clients</option>
            <option value="EMAIL_PARENTS">Envoyer email parents</option>
            <option value="EXPORT">Telecharger Excel (CSV)</option>
            <option value="DELETE">Supprimer</option>
          </select>
        </label>

        <label className="bulk-inline-field">
          Nouveau statut
          <select name="target_status" defaultValue="ACTIVE" disabled={!canPickStatus}>
            <option value="ACTIVE">ACTIF</option>
            <option value="TRIAL">ESSAI</option>
            <option value="PENDING">EN ATTENTE</option>
            <option value="INACTIVE">INACTIF</option>
            <option value="ARCHIVED">ARCHIVE</option>
          </select>
        </label>

        <label className="bulk-inline-field">
          Groupe
          <select name="group_id" defaultValue="" disabled={!canPickGroup}>
            <option value="">Selectionner</option>
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="row bulk-selection-row">
        <button
          type="button"
          className={`ghost small-btn ${selectionScope === "PAGE" ? "mode-active" : ""}`}
          onClick={() => {
            const form = getForm();
            if (!form) {
              return;
            }
            setSelectionScope("PAGE");
            setPageChecked(form, true);
            setSelectedOnPage(syncHeaderToggle(form));
          }}
        >
          Selectionner la page ({pageCount})
        </button>

        <button
          type="button"
          className={`ghost small-btn ${selectionScope === "FILTERED" ? "mode-active" : ""}`}
          onClick={() => {
            setSelectionScope("FILTERED");
            const form = getForm();
            if (!form) {
              return;
            }
            setPageChecked(form, false);
            setSelectedOnPage(syncHeaderToggle(form));
          }}
        >
          Selectionner tous les filtres ({filteredCount})
        </button>

        <button
          type="button"
          className="ghost small-btn"
          onClick={() => {
            const form = getForm();
            if (!form) {
              return;
            }
            setSelectionScope("PAGE");
            setPageChecked(form, false);
            setSelectedOnPage(syncHeaderToggle(form));
          }}
        >
          Effacer la selection
        </button>
      </div>

      <small className="muted">
        {selectionScope === "FILTERED"
          ? `Portee selection: tous les clients filtres (${filteredCount}).`
          : `Portee selection: page courante (${selectedOnPage}/${pageCount}).`}
      </small>

      <div className="row">
        <button
          type="submit"
          onClick={(event) => {
            const form = event.currentTarget.form;
            if (!form) {
              return;
            }

            const selectedIds = checkedClientIds(form);
            const selectedFilteredIds = filteredClientIds(form);

            if (selectionScope === "PAGE" && selectedIds.length === 0) {
              event.preventDefault();
              window.alert("Selectionnez au moins un adherent de la page.");
              return;
            }

            if (selectionScope === "FILTERED" && selectedFilteredIds.length === 0) {
              event.preventDefault();
              window.alert("Aucun adherent ne correspond au filtre.");
              return;
            }

            if (action === "ASSIGN_GROUP") {
              const groupField = form.elements.namedItem("group_id") as HTMLSelectElement | null;
              if (!groupField || !groupField.value) {
                event.preventDefault();
                window.alert("Selectionnez un groupe.");
                return;
              }
            }

            if (action === "DELETE") {
              const total =
                selectionScope === "FILTERED"
                  ? selectedFilteredIds.length
                  : selectedIds.length;
              const confirmed = window.confirm(
                `Confirmer la suppression definitive de ${total} adherent(s) ? Cette action est irreversible.`,
              );
              if (!confirmed) {
                event.preventDefault();
              }
            }
          }}
        >
          Appliquer
        </button>
      </div>
    </div>
  );
}
