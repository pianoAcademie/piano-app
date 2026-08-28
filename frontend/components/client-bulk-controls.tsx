"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

type GroupOption = {
  id: string;
  name: string;
};

type EmailTemplateOption = {
  id: string;
  name: string;
  subject: string;
  body: string;
  bodyFormat: "TEXT" | "HTML";
};

type SelectionScope = "PAGE" | "FILTERED";

type Props = {
  groups: GroupOption[];
  emailTemplates: EmailTemplateOption[];
  pageCount: number;
  filteredCount: number;
  language?: "fr" | "en";
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

export default function ClientBulkControls({ groups, emailTemplates, pageCount, filteredCount, language }: Props): JSX.Element {
  const searchParams = useSearchParams();
  const resolvedLanguage = language ?? (searchParams?.get("lang") === "en" ? "en" : "fr");
  const isEnglish = resolvedLanguage === "en";
  const statusOptions = isEnglish
    ? [
        { value: "ACTIVE", label: "Active" },
        { value: "TRIAL", label: "Trial" },
        { value: "PENDING", label: "Pending" },
        { value: "RESPONSABLE", label: "Responsible" },
        { value: "INACTIVE", label: "Inactive" },
        { value: "ARCHIVED", label: "Archived" },
      ]
    : [
        { value: "ACTIVE", label: "Actif" },
        { value: "TRIAL", label: "Essai" },
        { value: "PENDING", label: "En attente" },
        { value: "RESPONSABLE", label: "Responsable" },
        { value: "INACTIVE", label: "Inactif" },
        { value: "ARCHIVED", label: "Archive" },
      ];
  const text = isEnglish
    ? {
        action: "Action",
        updateStatuses: "Update statuses",
        assignGroup: "Assign to a group",
        archive: "Archive",
        emailClients: "New email (selected clients)",
        emailClientsOperational: "Operational email (selected clients)",
        emailParents: "New email (selected parents)",
        smsClients: "Send SMS (selected clients)",
        smsParents: "Send SMS (selected parents)",
        exportCsv: "Download Excel (CSV)",
        delete: "Delete",
        newStatus: "New status",
        group: "Group",
        select: "Select",
        subject: "Subject",
        template: "Template",
        noTemplate: "No template",
        subjectRequired: "(required)",
        subjectOptionalSms: "(optional for SMS)",
        subjectPlaceholder: "Message subject",
        format: "Format",
        textFormat: "Text",
        htmlFormat: "HTML",
        message: "Message",
        messagePlaceholder: "Message content...",
        selectPage: `Select page (${pageCount})`,
        selectFiltered: `Select all filtered (${filteredCount})`,
        clearSelection: "Clear selection",
        filteredScope: `Selection scope: all filtered results (${filteredCount}).`,
        pageScope: (selectedCount: number) => `Selection scope: current page (${selectedCount}/${pageCount}).`,
        apply: "Apply",
        pageSelectionRequired: "Select at least one client on the page.",
        noFilteredClient: "No client matches the filter.",
        groupRequired: "Select a group.",
        smsRequired: "SMS message is required.",
        subjectMessageRequired: "Subject and message are required.",
        deleteConfirm: (total: number) => `Confirm permanent deletion of ${total} client(s)? This action cannot be undone.`,
        operationalConfirm: (total: number) => `Send this operational email now to up to ${total} selected client(s)?`,
      }
    : {
        action: "Action",
        updateStatuses: "Mettre a jour les statuts",
        assignGroup: "Affecter a un groupe",
        archive: "Archiver",
        emailClients: "Nouveau courriel (clients selectionnes)",
        emailClientsOperational: "Courriel operationnel (clients selectionnes)",
        emailParents: "Nouveau courriel (parents selectionnes)",
        smsClients: "Envoyer SMS (clients selectionnes)",
        smsParents: "Envoyer SMS (parents selectionnes)",
        exportCsv: "Telecharger Excel (CSV)",
        delete: "Supprimer",
        newStatus: "Nouveau statut",
        group: "Groupe",
        select: "Selectionner",
        subject: "Sujet",
        template: "Modele",
        noTemplate: "Aucun modele",
        subjectRequired: "(obligatoire)",
        subjectOptionalSms: "(optionnel pour SMS)",
        subjectPlaceholder: "Objet du message",
        format: "Format",
        textFormat: "Texte",
        htmlFormat: "HTML",
        message: "Message",
        messagePlaceholder: "Contenu du message...",
        selectPage: `Selectionner la page (${pageCount})`,
        selectFiltered: `Selectionner tous les resultats filtres (${filteredCount})`,
        clearSelection: "Effacer la selection",
        filteredScope: `Portee de selection : tous les resultats filtres (${filteredCount}).`,
        pageScope: (selectedCount: number) => `Portee de selection : page courante (${selectedCount}/${pageCount}).`,
        apply: "Appliquer",
        pageSelectionRequired: "Selectionnez au moins un client de la page.",
        noFilteredClient: "Aucun client ne correspond au filtre.",
        groupRequired: "Selectionnez un groupe.",
        smsRequired: "Message SMS obligatoire.",
        subjectMessageRequired: "Sujet et message obligatoires.",
        deleteConfirm: (total: number) => `Confirmer la suppression definitive de ${total} client(s) ? Cette action est irreversible.`,
        operationalConfirm: (total: number) => `Envoyer maintenant ce courriel operationnel a un maximum de ${total} client(s) selectionne(s) ?`,
      };
  const [action, setAction] = useState("UPDATE_STATUS");
  const [selectionScope, setSelectionScope] = useState<SelectionScope>("PAGE");
  const [selectedOnPage, setSelectedOnPage] = useState(0);
  const [messageSubject, setMessageSubject] = useState("");
  const [messageBody, setMessageBody] = useState("");
  const [messageBodyFormat, setMessageBodyFormat] = useState<"TEXT" | "HTML">("TEXT");

  const canPickGroup = useMemo(() => action === "ASSIGN_GROUP", [action]);
  const canPickStatus = useMemo(() => action === "UPDATE_STATUS", [action]);
  const isEmailMessageAction = useMemo(
    () => action === "EMAIL_CLIENTS" || action === "EMAIL_CLIENTS_OPERATIONAL" || action === "EMAIL_PARENTS",
    [action],
  );
  const isSmsMessageAction = useMemo(() => action === "SMS_CLIENTS" || action === "SMS_PARENTS", [action]);
  const isMessageAction = useMemo(() => isEmailMessageAction || isSmsMessageAction, [isEmailMessageAction, isSmsMessageAction]);

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
          {text.action}
          <select name="bulk_action" value={action} onChange={(event) => setAction(event.target.value)}>
            <option value="UPDATE_STATUS">{text.updateStatuses}</option>
            <option value="ASSIGN_GROUP">{text.assignGroup}</option>
            <option value="ARCHIVE">{text.archive}</option>
            <option value="EMAIL_CLIENTS">{text.emailClients}</option>
            <option value="EMAIL_CLIENTS_OPERATIONAL">{text.emailClientsOperational}</option>
            <option value="EMAIL_PARENTS">{text.emailParents}</option>
            <option value="SMS_CLIENTS">{text.smsClients}</option>
            <option value="SMS_PARENTS">{text.smsParents}</option>
            <option value="EXPORT">{text.exportCsv}</option>
            <option value="DELETE">{text.delete}</option>
          </select>
        </label>

        <label className="bulk-inline-field">
          {text.newStatus}
          <select name="target_status" defaultValue="ACTIVE" disabled={!canPickStatus}>
            {statusOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="bulk-inline-field">
          {text.group}
          <select name="group_id" defaultValue="" disabled={!canPickGroup}>
            <option value="">{text.select}</option>
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {isMessageAction ? (
        <div className="grid cols-2">
          {isEmailMessageAction && emailTemplates.length > 0 ? (
            <label className="span-2">
              {text.template}
              <select
                defaultValue=""
                onChange={(event) => {
                  const template = emailTemplates.find((item) => item.id === event.target.value);
                  if (!template) {
                    return;
                  }
                  setMessageSubject(template.subject);
                  setMessageBody(template.body);
                  setMessageBodyFormat(template.bodyFormat);
                }}
              >
                <option value="">{text.noTemplate}</option>
                {emailTemplates.map((template) => (
                  <option key={template.id} value={template.id}>{template.name}</option>
                ))}
              </select>
            </label>
          ) : null}
          <label className="span-2">
            {text.subject} {isEmailMessageAction ? text.subjectRequired : text.subjectOptionalSms}
            <input
              type="text"
              name="message_subject"
              maxLength={255}
              placeholder={text.subjectPlaceholder}
              value={messageSubject}
              onChange={(event) => setMessageSubject(event.target.value)}
            />
          </label>
          <label>
            {text.format}
            <select
              name="message_body_format"
              value={messageBodyFormat}
              disabled={isSmsMessageAction}
              onChange={(event) => setMessageBodyFormat(event.target.value === "HTML" ? "HTML" : "TEXT")}
            >
              <option value="TEXT">{text.textFormat}</option>
              <option value="HTML">{text.htmlFormat}</option>
            </select>
          </label>
          <label className="span-2">
            {text.message}
            <textarea
              name="message_body"
              rows={12}
              maxLength={12000}
              placeholder={text.messagePlaceholder}
              value={messageBody}
              onChange={(event) => setMessageBody(event.target.value)}
            />
          </label>
        </div>
      ) : null}

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
          {text.selectPage}
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
          {text.selectFiltered}
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
          {text.clearSelection}
        </button>
      </div>

      <small className="muted">
        {selectionScope === "FILTERED"
          ? text.filteredScope
          : text.pageScope(selectedOnPage)}
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
            if (selectionScope === "PAGE" && selectedIds.length === 0) {
              event.preventDefault();
              window.alert(text.pageSelectionRequired);
              return;
            }

            if (selectionScope === "FILTERED" && filteredCount === 0) {
              event.preventDefault();
              window.alert(text.noFilteredClient);
              return;
            }

            if (action === "ASSIGN_GROUP") {
              const groupField = form.elements.namedItem("group_id") as HTMLSelectElement | null;
              if (!groupField || !groupField.value) {
                event.preventDefault();
                window.alert(text.groupRequired);
                return;
              }
            }

            if (isMessageAction) {
              const subjectField = form.elements.namedItem("message_subject") as HTMLInputElement | null;
              const bodyField = form.elements.namedItem("message_body") as HTMLTextAreaElement | null;
              const subject = (subjectField?.value || "").trim();
              const body = (bodyField?.value || "").trim();
              if (!body) {
                event.preventDefault();
                window.alert(isEmailMessageAction ? text.subjectMessageRequired : text.smsRequired);
                return;
              }
              if (isEmailMessageAction && !subject) {
                event.preventDefault();
                window.alert(text.subjectMessageRequired);
                return;
              }
            }

            if (action === "DELETE") {
              const total =
                selectionScope === "FILTERED"
                  ? filteredCount
                  : selectedIds.length;
              const confirmed = window.confirm(text.deleteConfirm(total));
              if (!confirmed) {
                event.preventDefault();
              }
            }

            if (action === "EMAIL_CLIENTS_OPERATIONAL") {
              const total = selectionScope === "FILTERED" ? filteredCount : selectedIds.length;
              if (!window.confirm(text.operationalConfirm(total))) {
                event.preventDefault();
              }
            }
          }}
        >
          {text.apply}
        </button>
      </div>
    </div>
  );
}
