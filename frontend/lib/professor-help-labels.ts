import "server-only";

import { type UiLanguage, uiText } from "./ui-i18n";

const UI_LABEL_KEYS: Record<string, string> = {
  todo: "teacher.todo",
  today_title: "teacher.today_title",
  attendance_booked: "teacher.attendance_booked",
  present: "teacher.present",
  excused: "teacher.excused",
  unexcused: "teacher.unexcused",
  planning: "teacher.planning",
  teacher_absence: "teacher.teacher_absence",
  notify_students: "teacher.notify_students",
  declare_teacher_absence: "teacher.declare_teacher_absence",
  confirm_teacher_absence: "teacher.confirm_teacher_absence",
  statements: "teacher.statements",
  previous_month: "teacher.previous_month",
  next_month: "teacher.next_month",
  report_issue: "teacher.report_issue_existing_lines_cta",
  add_missing_service: "teacher.add_missing_service_cta",
  statement_validation: "teacher.statement_validation",
  approve_statement: "teacher.approve_statement",
  billing: "teacher.billing",
  generate_invoice: "teacher.generate_invoice",
  external_billing: "teacher.external_billing",
  send_to_accounting: "teacher.send_to_accounting",
  slot_details: "teacher.slot_details",
  zoom_link: "teacher.zoom_link",
  open_link: "teacher.open_link",
  admin_note_section: "teacher.admin_note_section",
  subject: "teacher.subject",
  internal_note: "teacher.internal_note",
  save_note: "teacher.save_note",
  save: "teacher.save",
  student_internal_note: "teacher.student_internal_note",
  session_internal_note_section: "teacher.session_internal_note_section",
  notes: "teacher.notes",
  notes_search: "teacher.notes_search",
  notes_type: "teacher.notes_type",
  notes_period: "teacher.notes_period",
  notes_location: "teacher.notes_location",
  notes_apply: "teacher.notes_apply",
  notes_open_course: "teacher.notes_open_course",
};

export function buildProfessorHelpLabels(language: UiLanguage): Record<string, string> {
  return Object.fromEntries(
    Object.entries(UI_LABEL_KEYS).map(([token, key]) => [token, uiText(language, key)]),
  );
}
