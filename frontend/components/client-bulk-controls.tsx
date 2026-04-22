"use client";

import { useEffect, useMemo, useState } from "react";

import { type UiLanguage, uiText } from "../lib/ui-i18n";

type GroupOption = {
  id: string;
  name: string;
};

type SelectionScope = "PAGE" | "FILTERED";

type Props = {
  groups: GroupOption[];
  pageCount: number;
  filteredCount: number;
  language: UiLanguage;
};

function statusLabel(status: string, language: UiLanguage): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "ACTIVE") return uiText(language, "admin.clients.status_active");
  if (normalized === "TRIAL") return uiText(language, "admin.clients.status_trial");
  if (normalized === "PENDING") return uiText(language, "admin.clients.status_pending");
  if (normalized === "INACTIVE") return uiText(language, "admin.clients.status_inactive");
  if (normalized === "ARCHIVED") return uiText(language, "admin.clients.status_archived");
  return normalized;
}

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

export default function ClientBulkControls({ groups, pageCount, filteredCount, language }: Props): JSX.Element {
  const [action, setAction] = useState("UPDATE_STATUS");
  const [selectionScope, setSelectionScope] = useState<SelectionScope>("PAGE");
  const [selectedOnPage, setSelectedOnPage] = useState(0);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const canPickGroup = useMemo(() => action === "ASSIGN_GROUP", [action]);
  const canPickStatus = useMemo(() => action === "UPDATE_STATUS", [action]);
  const isEmailMessageAction = useMemo(() => action === "EMAIL_CLIENTS" || action === "EMAIL_PARENTS", [action]);
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
          {t("admin.clients.bulk_action")}
          <select name="bulk_action" value={action} onChange={(event) => setAction(event.target.value)}>
            <option value="UPDATE_STATUS">{t("admin.clients.bulk_update_status")}</option>
            <option value="ASSIGN_GROUP">{t("admin.clients.bulk_assign_group")}</option>
            <option value="ARCHIVE">{t("admin.clients.bulk_archive")}</option>
            <option value="EMAIL_CLIENTS">{t("admin.clients.bulk_email_clients")}</option>
            <option value="EMAIL_PARENTS">{t("admin.clients.bulk_email_parents")}</option>
            <option value="SMS_CLIENTS">{t("admin.clients.bulk_sms_clients")}</option>
            <option value="SMS_PARENTS">{t("admin.clients.bulk_sms_parents")}</option>
            <option value="EXPORT">{t("admin.clients.bulk_export")}</option>
            <option value="DELETE">{t("admin.clients.bulk_delete")}</option>
          </select>
        </label>

        <label className="bulk-inline-field">
          {t("admin.clients.bulk_new_status")}
          <select name="target_status" defaultValue="ACTIVE" disabled={!canPickStatus}>
            <option value="ACTIVE">{statusLabel("ACTIVE", language)}</option>
            <option value="TRIAL">{statusLabel("TRIAL", language)}</option>
            <option value="PENDING">{statusLabel("PENDING", language)}</option>
            <option value="INACTIVE">{statusLabel("INACTIVE", language)}</option>
            <option value="ARCHIVED">{statusLabel("ARCHIVED", language)}</option>
          </select>
        </label>

        <label className="bulk-inline-field">
          {t("admin.clients.bulk_group")}
          <select name="group_id" defaultValue="" disabled={!canPickGroup}>
            <option value="">{t("admin.clients.bulk_select_group")}</option>
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
          <label className="span-2">
            {isEmailMessageAction ? t("admin.clients.bulk_subject_required") : t("admin.clients.bulk_subject_optional_sms")}
            <input type="text" name="message_subject" maxLength={255} placeholder={t("admin.clients.bulk_subject_placeholder")} />
          </label>
          <label>
            {t("admin.clients.bulk_format")}
            <select name="message_body_format" defaultValue="TEXT" disabled={isSmsMessageAction}>
              <option value="TEXT">{t("admin.clients.bulk_text")}</option>
              <option value="HTML">{uiText(language, "common.html")}</option>
            </select>
          </label>
          <label className="span-2">
            {t("admin.clients.bulk_message")}
            <textarea name="message_body" rows={5} maxLength={12000} placeholder={t("admin.clients.bulk_message_placeholder")} />
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
          {t("admin.clients.bulk_select_page", { count: pageCount })}
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
          {t("admin.clients.bulk_select_filtered", { count: filteredCount })}
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
          {t("admin.clients.bulk_clear_selection")}
        </button>
      </div>

      <small className="muted">
        {selectionScope === "FILTERED"
          ? t("admin.clients.bulk_scope_filtered", { count: filteredCount })
          : t("admin.clients.bulk_scope_page", { selected: selectedOnPage, count: pageCount })}
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
              window.alert(t("admin.clients.bulk_alert_select_client"));
              return;
            }

            if (selectionScope === "FILTERED" && selectedFilteredIds.length === 0) {
              event.preventDefault();
              window.alert(t("admin.clients.bulk_alert_no_filtered"));
              return;
            }

            if (action === "ASSIGN_GROUP") {
              const groupField = form.elements.namedItem("group_id") as HTMLSelectElement | null;
              if (!groupField || !groupField.value) {
                event.preventDefault();
                window.alert(t("admin.clients.bulk_alert_select_group"));
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
                window.alert(isEmailMessageAction ? t("admin.clients.bulk_alert_subject_and_message") : t("admin.clients.bulk_alert_sms_message"));
                return;
              }
              if (isEmailMessageAction && !subject) {
                event.preventDefault();
                window.alert(t("admin.clients.bulk_alert_subject_and_message"));
                return;
              }
            }

            if (action === "DELETE") {
              const total =
                selectionScope === "FILTERED"
                  ? selectedFilteredIds.length
                  : selectedIds.length;
              const confirmed = window.confirm(
                t("admin.clients.bulk_delete_confirm", { count: total }),
              );
              if (!confirmed) {
                event.preventDefault();
              }
            }
          }}
        >
          {uiText(language, "common.apply")}
        </button>
      </div>
    </div>
  );
}
