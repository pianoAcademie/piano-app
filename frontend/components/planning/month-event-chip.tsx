import type { AdminSessionOut } from "../../lib/types";

type MonthEventChipProps = {
  event: AdminSessionOut;
  href: string;
};

function formatEventTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "--:--";
  }
  return parsed.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function compactTeacherName(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }
  if (trimmed.length <= 20) {
    return trimmed;
  }
  const tokens = trimmed.split(/\s+/).filter((token) => token.length > 0);
  if (tokens.length <= 1) {
    return trimmed;
  }
  const firstName = tokens[0];
  const lastToken = tokens[tokens.length - 1];
  const initial = lastToken.slice(0, 1).toUpperCase();
  if (!initial) {
    return firstName;
  }
  return `${firstName} ${initial}.`;
}

function statusBadgeClass(status: string): string {
  const normalized = status.toUpperCase();
  if (normalized === "CANCELLED") {
    return "month-badge-status-cancelled";
  }
  if (normalized === "COMPLETED") {
    return "month-badge-status-completed";
  }
  return "month-badge-status-planned";
}

export default function MonthEventChip({ event, href }: MonthEventChipProps): JSX.Element {
  const teacherFullName = (event.teacher_display_name || "").trim();
  const teacherMissing = teacherFullName.length === 0;
  const teacherCompact = teacherMissing ? "(non renseigne)" : compactTeacherName(teacherFullName);
  const locationLabel = (event.location_label || "").trim() || "Lieu";
  const startTime = formatEventTime(event.start_at_utc);
  const endTime = formatEventTime(event.end_at_utc);
  const tooltip = `${startTime}-${endTime}\n${event.title}\nProf: ${teacherMissing ? "(non renseigne)" : teacherFullName}\nLieu: ${locationLabel}\nStatut: ${event.status_label}`;

  return (
    <a className="month-event-chip" href={href} title={tooltip}>
      <div className="month-event-chip-meta">
        <span className="month-event-chip-time">{startTime}</span>
        <span className="month-event-chip-badges">
          <span className="month-badge month-badge-type">{event.type_label}</span>
          <span className={`month-badge ${statusBadgeClass(event.status)}`}>{event.status_label}</span>
        </span>
      </div>
      <p className="month-event-chip-title">{event.title}</p>
      <p className="month-event-chip-sub">
        <span className={`month-event-chip-prof ${teacherMissing ? "missing" : ""}`}>Prof : {teacherCompact}</span>
        {teacherMissing ? <span className="month-event-chip-warn" aria-hidden="true">⚠</span> : null}
        <span className="month-event-chip-sep" aria-hidden="true">
          ·
        </span>
        <span className="month-event-chip-location">{locationLabel}</span>
      </p>
    </a>
  );
}
