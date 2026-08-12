"use client";

import { useCallback, useEffect, useMemo, useState, type MouseEvent } from "react";
import { useFormStatus } from "react-dom";

import RichMessageEditor from "../rich-message-editor";
import SearchMultiSelect from "../search-multi-select";
import type { UiLanguage } from "../../lib/ui-i18n";

type Destination =
  | "PRIVATE"
  | "STUDENTS_AND_PARENTS"
  | "PARENTS"
  | "STUDENTS"
  | "PROFESSOR"
  | "ADMINS"
  | "SELF";

type SendChannel = "EMAIL" | "SMS";

type GroupNoteTemplate = {
  id: string;
  name: string;
  body: string;
  body_format: "TEXT" | "HTML";
};

type StudentOption = {
  id: string;
  label: string;
};

type Props = {
  action: (formData: FormData) => void | Promise<void>;
  sessionId: string;
  sessionTitle: string;
  closeHref: string;
  returnTo: string;
  language: UiLanguage;
  initialNote: string;
  initialTemplateId?: string;
  initialDestination: Destination;
  templates: GroupNoteTemplate[];
  students: StudentOption[];
  selectedStudentIds: string[];
  successMessage?: string | null;
  errorMessage?: string | null;
};

const STUDENT_DESTINATIONS = new Set<Destination>([
  "STUDENTS_AND_PARENTS",
  "PARENTS",
  "STUDENTS",
]);

function SubmitState({ dirty, language }: { dirty: boolean; language: UiLanguage }): JSX.Element {
  const { pending } = useFormStatus();
  const isEnglish = language === "en";

  return (
    <span className={`group-note-save-state ${pending ? "is-pending" : dirty ? "is-dirty" : "is-clean"}`} aria-live="polite">
      <span aria-hidden="true">{pending ? "◌" : dirty ? "●" : "✓"}</span>
      {pending
        ? (isEnglish ? "Saving…" : "Enregistrement…")
        : dirty
          ? (isEnglish ? "Unsaved changes" : "Modifications non enregistrées")
          : (isEnglish ? "No pending changes" : "Aucune modification en attente")}
    </span>
  );
}

export default function GroupNoteComposer({
  action,
  sessionId,
  sessionTitle,
  closeHref,
  returnTo,
  language,
  initialNote,
  initialTemplateId = "",
  initialDestination,
  templates,
  students,
  selectedStudentIds,
  successMessage,
  errorMessage,
}: Props): JSX.Element {
  const isEnglish = language === "en";
  const initialTemplate = templates.find((template) => template.id === initialTemplateId) ?? null;
  const [destination, setDestination] = useState<Destination>(initialDestination);
  const [selectedIds, setSelectedIds] = useState(selectedStudentIds);
  const [selectedTemplateId, setSelectedTemplateId] = useState(initialTemplate?.id ?? "");
  const initialEditorValue = initialTemplate?.body ?? initialNote;
  const [editorValue, setEditorValue] = useState(initialEditorValue);
  const [editorFormat, setEditorFormat] = useState<"TEXT" | "HTML">(initialTemplate?.body_format ?? "HTML");
  const [editorVersion, setEditorVersion] = useState(0);
  const defaultSubject = `${isEnglish ? "Group note" : "Note de groupe"} - ${sessionTitle}`;
  const [subject, setSubject] = useState(defaultSubject);
  const [sendToSelf, setSendToSelf] = useState(false);
  const [sendChannels, setSendChannels] = useState<SendChannel[]>(["EMAIL"]);

  const dirty = useMemo(() => {
    const initialIds = [...selectedStudentIds].sort();
    const currentIds = [...selectedIds].sort();
    return editorValue !== initialEditorValue
      || destination !== initialDestination
      || initialIds.join("|") !== currentIds.join("|")
      || (destination !== "PRIVATE" && (
        subject !== defaultSubject
        || sendToSelf
        || sendChannels.length !== 1
        || sendChannels[0] !== "EMAIL"
      ));
  }, [
    defaultSubject,
    destination,
    editorValue,
    initialDestination,
    initialEditorValue,
    selectedIds,
    selectedStudentIds,
    sendChannels,
    sendToSelf,
    subject,
  ]);

  const recipientNames = useMemo(
    () => students.filter((student) => selectedIds.includes(student.id)).map((student) => student.label.split(" <")[0] || student.label),
    [selectedIds, students],
  );
  const studentAudience = STUDENT_DESTINATIONS.has(destination);
  const sendsEmail = sendChannels.includes("EMAIL");

  const toggleSendChannel = (channel: SendChannel): void => {
    setSendChannels((current) => (
      current.includes(channel)
        ? current.filter((item) => item !== channel)
        : [...current, channel]
    ));
  };

  useEffect(() => {
    const warnBeforeLeaving = (event: BeforeUnloadEvent): void => {
      if (!dirty) {
        return;
      }
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeLeaving);
    return () => window.removeEventListener("beforeunload", warnBeforeLeaving);
  }, [dirty]);

  useEffect(() => {
    const confirmHeaderClose = (event: globalThis.MouseEvent): void => {
      const target = event.target instanceof Element ? event.target.closest("[data-group-note-close]") : null;
      if (!target || !dirty) {
        return;
      }
      const confirmed = window.confirm(
        isEnglish
          ? "Your unsaved changes will be lost. Close anyway?"
          : "Vos modifications non enregistrées seront perdues. Fermer quand même ?",
      );
      if (!confirmed) {
        event.preventDefault();
      }
    };
    document.addEventListener("click", confirmHeaderClose);
    return () => document.removeEventListener("click", confirmHeaderClose);
  }, [dirty, isEnglish]);

  const confirmClose = (event: MouseEvent<HTMLAnchorElement>): void => {
    if (!dirty) {
      return;
    }
    const confirmed = window.confirm(
      isEnglish
        ? "Your unsaved changes will be lost. Close anyway?"
        : "Vos modifications non enregistrées seront perdues. Fermer quand même ?",
    );
    if (!confirmed) {
      event.preventDefault();
    }
  };

  const handleSelectionChange = useCallback((ids: string[]): void => {
    setSelectedIds(ids);
  }, []);

  const destinations: Array<{ value: Destination; title: string; description: string }> = isEnglish
    ? [
        { value: "PRIVATE", title: "Internal note", description: "Visible to the administration only; no message is sent." },
        { value: "STUDENTS_AND_PARENTS", title: "Students and parents", description: "Send the same message to both." },
        { value: "PARENTS", title: "Parents only", description: "Contact the family contacts." },
        { value: "STUDENTS", title: "Students only", description: "Contact the selected students." },
        { value: "PROFESSOR", title: "Teacher", description: "Send the note to the assigned teacher." },
        { value: "ADMINS", title: "Administration", description: "Send the note to administrators." },
        { value: "SELF", title: "Myself", description: "Send a copy to your own account." },
      ]
    : [
        { value: "PRIVATE", title: "Note interne", description: "Visible uniquement par l’administration ; aucun message n’est envoyé." },
        { value: "STUDENTS_AND_PARENTS", title: "Élèves et parents", description: "Envoyer le même message aux deux." },
        { value: "PARENTS", title: "Parents uniquement", description: "Contacter les responsables familiaux." },
        { value: "STUDENTS", title: "Élèves uniquement", description: "Contacter les élèves sélectionnés." },
        { value: "PROFESSOR", title: "Professeur", description: "Envoyer la note au professeur affecté." },
        { value: "ADMINS", title: "Administration", description: "Envoyer la note aux administrateurs." },
        { value: "SELF", title: "Moi-même", description: "Envoyer une copie à votre propre compte." },
      ];

  return (
    <form
      action={action}
      className="note-modal-form group-note-composer"
      onSubmit={(event) => {
        const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
        if (submitter?.value !== "SEND") {
          return;
        }
        const selectedChannelLabels = sendChannels.map((channel) => (
          channel === "EMAIL" ? (isEnglish ? "email" : "e-mail") : "SMS"
        ));
        const confirmed = window.confirm(
          isEnglish
            ? `Save this note and send it by ${selectedChannelLabels.join(" and ")} to the selected recipients?`
            : `Enregistrer cette note et l’envoyer par ${selectedChannelLabels.join(" et ")} aux destinataires sélectionnés ?`,
        );
        if (!confirmed) {
          event.preventDefault();
        }
      }}
    >
      <input type="hidden" name="session_id" value={sessionId} />
      <input type="hidden" name="session_title" value={sessionTitle} />
      <input type="hidden" name="return_to" value={returnTo} />

      <div className="group-note-status-bar">
        <SubmitState dirty={dirty} language={language} />
        <span className="muted">
          {isEnglish ? "Everything is kept while this window remains open." : "Tout est conservé tant que cette fenêtre reste ouverte."}
        </span>
      </div>

      {successMessage ? (
        <div className="group-note-feedback is-success" role="status">
          <strong>{isEnglish ? "Saved" : "Enregistrement confirmé"}</strong>
          <span>{successMessage}</span>
        </div>
      ) : null}
      {errorMessage ? (
        <div className="group-note-feedback is-error" role="alert">
          <strong>{isEnglish ? "Action failed" : "L’action n’a pas abouti"}</strong>
          <span>{errorMessage}</span>
        </div>
      ) : null}

      <div className="note-modal-body group-note-body">
        <section className="group-note-section" aria-labelledby={`group-note-content-${sessionId}`}>
          <div className="group-note-section-heading">
            <span className="group-note-step" aria-hidden="true">1</span>
            <div>
              <h3 id={`group-note-content-${sessionId}`}>{isEnglish ? "Write the note" : "Rédiger la note"}</h3>
              <p>{isEnglish ? "Write once, then choose who should receive it." : "Rédigez une seule fois, puis choisissez qui doit la recevoir."}</p>
            </div>
          </div>

          {templates.length > 0 ? (
            <label className="group-note-template-field">
              <span>{isEnglish ? "Start from a template (optional)" : "Partir d’un modèle (optionnel)"}</span>
              <select
                value={selectedTemplateId}
                onChange={(event) => {
                  const templateId = event.target.value;
                  const template = templates.find((item) => item.id === templateId) ?? null;
                  setSelectedTemplateId(templateId);
                  setEditorValue(template?.body ?? initialNote);
                  setEditorFormat(template?.body_format ?? "HTML");
                  setEditorVersion((version) => version + 1);
                }}
              >
                <option value="">{isEnglish ? "No template" : "Aucun modèle"}</option>
                {templates.map((template) => (
                  <option key={template.id} value={template.id}>{template.name}</option>
                ))}
              </select>
            </label>
          ) : null}

          <RichMessageEditor
            key={`${editorVersion}-${selectedTemplateId}`}
            name="group_note"
            formatName="group_note_format"
            rows={8}
            maxLength={12000}
            language={language}
            placeholder={isEnglish ? "Write a group note…" : "Saisir une note de groupe…"}
            defaultValue={editorValue}
            defaultFormat={editorFormat}
            onValueChange={setEditorValue}
          />
        </section>

        <section className="group-note-section" aria-labelledby={`group-note-audience-${sessionId}`}>
          <div className="group-note-section-heading">
            <span className="group-note-step" aria-hidden="true">2</span>
            <div>
              <h3 id={`group-note-audience-${sessionId}`}>{isEnglish ? "Choose the audience" : "Choisir les destinataires"}</h3>
              <p>{isEnglish ? "The send options adapt immediately to this choice." : "Les options d’envoi s’adaptent immédiatement à ce choix."}</p>
            </div>
          </div>

          <div className="group-note-audience-grid">
            {destinations.map((item) => (
              <label key={item.value} className={`group-note-audience-card ${destination === item.value ? "is-selected" : ""}`}>
                <input
                  type="radio"
                  name="note_destination"
                  value={item.value}
                  checked={destination === item.value}
                  onChange={() => setDestination(item.value)}
                />
                <span>
                  <strong>{item.title}</strong>
                  <small>{item.description}</small>
                </span>
              </label>
            ))}
          </div>

          {studentAudience ? (
            <div className="group-note-student-picker">
              <div className="group-note-recipient-count">
                <strong>{selectedIds.length} {isEnglish ? "selected student(s)" : "élève(s) sélectionné(s)"}</strong>
                <span className="muted">
                  {recipientNames.length > 0
                    ? recipientNames.join(", ")
                    : (isEnglish ? "No student selected" : "Aucun élève sélectionné")}
                </span>
              </div>
              <SearchMultiSelect
                className="session-edit-span"
                label={isEnglish ? "Included students" : "Élèves inclus"}
                name="included_student_ids"
                options={students}
                selectedIds={selectedIds}
                language={language}
                placeholder={isEnglish ? "Search a student…" : "Rechercher un élève…"}
                emptySelectionLabel={students.length > 0
                  ? (isEnglish ? "No student selected." : "Aucun élève sélectionné.")
                  : (isEnglish ? "No student is booked on this slot." : "Aucun élève n’est inscrit sur ce créneau.")}
                onSelectionChange={handleSelectionChange}
              />
            </div>
          ) : null}
        </section>

        <section className="group-note-section" aria-labelledby={`group-note-send-${sessionId}`}>
          <div className="group-note-section-heading">
            <span className="group-note-step" aria-hidden="true">3</span>
            <div>
              <h3 id={`group-note-send-${sessionId}`}>{isEnglish ? "Save or send" : "Enregistrer ou envoyer"}</h3>
              <p>
                {destination === "PRIVATE"
                  ? (isEnglish ? "This note will remain internal." : "Cette note restera interne.")
                  : (isEnglish ? "Choose email, SMS, or both before sending." : "Choisissez l’e-mail, le SMS ou les deux avant l’envoi.")}
              </p>
            </div>
          </div>

          {destination === "PRIVATE" ? (
            <div className="group-note-send-summary">
              <strong>{isEnglish ? "No external message" : "Aucun envoi externe"}</strong>
              <span>{isEnglish ? "Use “Save note” below." : "Utilisez « Enregistrer la note » ci-dessous."}</span>
            </div>
          ) : (
            <div className="group-note-send-options">
              <fieldset className="group-note-channel-fieldset">
                <legend>{isEnglish ? "Sending channels" : "Canaux d’envoi"}</legend>
                <div className="group-note-channel-grid">
                  {(["EMAIL", "SMS"] as const).map((channel) => {
                    const selected = sendChannels.includes(channel);
                    return (
                      <label key={channel} className={`group-note-channel-card ${selected ? "is-selected" : ""}`}>
                        <input
                          type="checkbox"
                          name="send_channels"
                          value={channel}
                          checked={selected}
                          onChange={() => toggleSendChannel(channel)}
                        />
                        <span>
                          <strong>{channel === "EMAIL" ? (isEnglish ? "Email" : "E-mail") : "SMS"}</strong>
                          <small>
                            {channel === "EMAIL"
                              ? (isEnglish ? "Keep the formatting and subject." : "Conserve la mise en forme et l’objet.")
                              : (isEnglish ? "Send a plain-text version to mobile numbers." : "Envoie une version texte aux numéros mobiles.")}
                          </small>
                        </span>
                      </label>
                    );
                  })}
                </div>
                {sendChannels.length === 0 ? (
                  <span className="field-error" role="alert">
                    {isEnglish ? "Select at least one sending channel." : "Sélectionnez au moins un canal d’envoi."}
                  </span>
                ) : null}
              </fieldset>
              {sendsEmail ? (
                <label>
                  {isEnglish ? "Email subject" : "Objet de l’e-mail"}
                  <input
                    type="text"
                    name="subject"
                    value={subject}
                    onChange={(event) => setSubject(event.target.value)}
                    maxLength={255}
                  />
                </label>
              ) : (
                <input type="hidden" name="subject" value={subject} />
              )}
              <label className="checkline">
                <input
                  type="checkbox"
                  name="send_to_self"
                  checked={sendToSelf}
                  onChange={(event) => setSendToSelf(event.target.checked)}
                />
                {isEnglish ? "Send me a copy" : "M’envoyer une copie"}
              </label>
              <div className="group-note-send-summary">
                <strong>
                  {sendChannels.length > 0
                    ? (isEnglish ? "Ready to send" : "Prêt pour l’envoi")
                    : (isEnglish ? "Choose a channel" : "Choisissez un canal")}
                </strong>
                <span>
                  {studentAudience
                    ? `${selectedIds.length} ${isEnglish ? "selected student(s)" : "élève(s) sélectionné(s)"}`
                    : destinations.find((item) => item.value === destination)?.title}
                </span>
                {sendChannels.length > 0 ? (
                  <span className="muted">
                    {sendChannels.map((channel) => channel === "EMAIL" ? (isEnglish ? "Email" : "E-mail") : "SMS").join(" + ")}
                  </span>
                ) : null}
              </div>
            </div>
          )}
        </section>
      </div>

      <footer className="note-modal-footer group-note-footer">
        <div className="group-note-footer-left">
          <a className="reset-link" href={closeHref} onClick={confirmClose}>
            {isEnglish ? "Close" : "Fermer"}
          </a>
          <SubmitState dirty={dirty} language={language} />
        </div>
        <div className="row">
          <button type="submit" name="note_action" value="SAVE_ONLY" className="ghost">
            {isEnglish ? "Save note" : "Enregistrer la note"}
          </button>
          {destination !== "PRIVATE" ? (
            <button
              type="submit"
              name="note_action"
              value="SEND"
              disabled={sendChannels.length === 0 || (studentAudience && selectedIds.length === 0)}
            >
              {isEnglish ? "Save and send" : "Enregistrer et envoyer"}
            </button>
          ) : null}
        </div>
      </footer>
    </form>
  );
}
