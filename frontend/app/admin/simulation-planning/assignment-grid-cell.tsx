"use client";

import { useState } from "react";

import { adminUpdatePlanningSimulationTeacherAssignmentAction } from "../../../lib/actions";
import type { AdminPlanningSimulationSlotOut, AdminProfessorOut } from "../../../lib/types";
import type { UiLanguage } from "../../../lib/ui-i18n";

function text(language: UiLanguage, fr: string, en: string): string {
  return language === "en" ? en : fr;
}

function teacherInitials(label: string): string {
  const parts = label.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) {
    return "?";
  }
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() || "").join("");
}

function warningLabel(code: string, language: UiLanguage): string {
  if (code === "TIME_OVERLAP") {
    return text(language, "Chevauchement horaire", "Schedule overlap");
  }
  if (code === "MULTI_SITE_HALF_DAY") {
    return text(language, "Plusieurs sites sur la même demi-journée", "Multiple locations in the same half-day");
  }
  return code;
}

export function TeacherAssignmentGridCell({
  count,
  slots,
  professors,
  schoolYearLabel,
  returnTo,
  canEdit,
  language,
  mobile = false,
}: {
  count: number;
  slots: AdminPlanningSimulationSlotOut[];
  professors: AdminProfessorOut[];
  schoolYearLabel: string;
  returnTo: string;
  canEdit: boolean;
  language: UiLanguage;
  mobile?: boolean;
}): JSX.Element {
  const [open, setOpen] = useState(false);
  const activeProfessors = professors.filter((professor) => professor.active);
  const assignedSlots = slots.filter((slot) => Boolean(slot.teacher_assignment_label));
  const warningCount = slots.filter((slot) => slot.teacher_assignment_warnings.length > 0).length;
  const allConfirmed = slots.length > 0 && slots.every((slot) => slot.teacher_assignment_status === "CONFIRMED");
  const stateClass = warningCount > 0
    ? "warning"
    : allConfirmed
      ? "confirmed"
      : assignedSlots.length === slots.length && slots.length > 0
        ? "assigned"
        : "unfilled";

  return (
    <>
      <button
        className={`simulation-teacher-cell-trigger ${stateClass} ${mobile ? "mobile" : ""}`}
        type="button"
        onClick={() => setOpen(true)}
        aria-label={text(
          language,
          `Gérer ${count} affectation${count > 1 ? "s" : ""}`,
          `Manage ${count} assignment${count > 1 ? "s" : ""}`,
        )}
      >
        <strong>{count}</strong>
        <span className="simulation-teacher-cell-avatars" aria-hidden="true">
          {assignedSlots.slice(0, 3).map((slot) => (
            <i
              className={slot.teacher_assignment_status === "CONFIRMED" ? "confirmed" : "previsional"}
              key={slot.slot_key}
              title={slot.teacher_assignment_label || undefined}
            >
              {teacherInitials(slot.teacher_assignment_label || "")}
            </i>
          ))}
          {assignedSlots.length < slots.length ? <i className="empty">+</i> : null}
        </span>
        {warningCount > 0 ? <span className="simulation-teacher-cell-alert" aria-hidden="true">!</span> : null}
      </button>

      {open ? (
        <div className="simulation-teacher-assignment-overlay" role="presentation" onMouseDown={() => setOpen(false)}>
          <section
            aria-label={text(language, "Affectation des professeurs", "Teacher assignments")}
            aria-modal="true"
            className="simulation-teacher-assignment-dialog"
            role="dialog"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <span>{slots[0]?.weekday_label || ""} · {slots[0]?.start_time || ""}–{slots[0]?.end_time || ""}</span>
                <h3>{slots[0]?.location_name || text(language, "Créneau simulé", "Simulated slot")}</h3>
                <p>{slots[0]?.course_type_name || ""}</p>
              </div>
              <button type="button" className="ghost" onClick={() => setOpen(false)} aria-label={text(language, "Fermer", "Close")}>×</button>
            </header>

            <div className="simulation-teacher-assignment-dialog-list">
              {slots.length === 0 ? (
                <p className="muted">{text(language, "Aucun créneau détaillé disponible.", "No detailed slot is available.")}</p>
              ) : slots.map((slot, index) => (
                <article className={slot.teacher_assignment_warnings.length > 0 ? "has-warning" : ""} key={slot.slot_key}>
                  <div className="simulation-teacher-assignment-dialog-current">
                    <div>
                      <span>{text(language, "Poste", "Position")} {index + 1}</span>
                      <strong>{slot.teacher_assignment_label || text(language, "À affecter", "Unfilled")}</strong>
                    </div>
                    <span className={`simulation-assignment-status ${slot.teacher_assignment_status?.toLowerCase() || "unfilled"}`}>
                      {slot.teacher_assignment_status === "CONFIRMED"
                        ? text(language, "Confirmé", "Confirmed")
                        : slot.teacher_assignment_label
                          ? text(language, "Prévisionnel", "Provisional")
                          : text(language, "À pourvoir", "Unfilled")}
                    </span>
                  </div>

                  {slot.teacher_assignment_warnings.length > 0 ? (
                    <div className="simulation-assignment-warnings">
                      {slot.teacher_assignment_warnings.map((warning) => (
                        <span key={warning}>{warningLabel(warning, language)}</span>
                      ))}
                    </div>
                  ) : null}

                  {canEdit ? (
                    <form action={adminUpdatePlanningSimulationTeacherAssignmentAction} className="simulation-teacher-assignment-dialog-form">
                      <input type="hidden" name="school_year_label" value={schoolYearLabel} />
                      <input type="hidden" name="slot_key" value={slot.slot_key} />
                      <input type="hidden" name="return_to" value={returnTo} />
                      <label>
                        <span>{text(language, "Professeur actif", "Active teacher")}</span>
                        <select name="professor_id" defaultValue={slot.teacher_assignment_professor_id || ""}>
                          <option value="">{text(language, "— Aucun / provisoire —", "— None / placeholder —")}</option>
                          {activeProfessors.map((professor) => (
                            <option value={professor.id} key={professor.id}>{professor.first_name} {professor.last_name}</option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>{text(language, "Ou libellé provisoire", "Or placeholder label")}</span>
                        <input
                          name="teacher_label"
                          list="simulation-placeholder-teachers"
                          defaultValue={slot.teacher_assignment_professor_id ? "" : slot.teacher_assignment_label || ""}
                          placeholder={text(language, "Ex. Prof à confirmer 1", "E.g. Teacher to confirm 1")}
                        />
                      </label>
                      <label>
                        <span>{text(language, "Statut", "Status")}</span>
                        <select name="assignment_status" defaultValue={slot.teacher_assignment_status || "PREVISIONAL"}>
                          <option value="PREVISIONAL">{text(language, "Prévisionnel", "Provisional")}</option>
                          <option value="CONFIRMED">{text(language, "Confirmé", "Confirmed")}</option>
                        </select>
                      </label>
                      <div className="simulation-assignment-actions">
                        <button type="submit" name="operation" value="save">{text(language, "Enregistrer", "Save")}</button>
                        {slot.teacher_assignment_label ? (
                          <button className="ghost" type="submit" name="operation" value="clear">{text(language, "Retirer", "Clear")}</button>
                        ) : null}
                      </div>
                    </form>
                  ) : (
                    <p className="muted">{text(language, "Consultation uniquement.", "Read-only access.")}</p>
                  )}
                </article>
              ))}
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}
