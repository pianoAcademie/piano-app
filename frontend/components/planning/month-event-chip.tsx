import type { AdminSessionOut } from "../../lib/types";

type MonthEventChipProps = {
  event: AdminSessionOut;
  href: string;
};

const UUID_RE = /\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/i;
const TEST_TITLE_RE = /\b(smoke|pa\s*day|test)\b/i;
const LONG_ID_RE = /\b\d{6,}\b/;

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
  return "month-badge-status-warning";
}

function normalizedTypeLabel(value: string): string {
  const normalized = (value || "").trim().toLowerCase();
  if (normalized.includes("priv")) {
    return "Prive";
  }
  if (normalized.includes("online")) {
    return "Online";
  }
  if (normalized.includes("domicile")) {
    return "Domicile";
  }
  return "Collectif";
}

function defaultTitleFromType(typeLabel: string): string {
  const normalized = normalizedTypeLabel(typeLabel);
  if (normalized === "Prive") {
    return "Cours prive";
  }
  if (normalized === "Online") {
    return "Cours online";
  }
  if (normalized === "Domicile") {
    return "Cours domicile";
  }
  return "Cours collectif";
}

function sanitizeTitle(value: string, typeLabel: string): string {
  const trimmed = (value || "").trim();
  if (!trimmed) {
    return defaultTitleFromType(typeLabel);
  }
  const hasTestPattern = TEST_TITLE_RE.test(trimmed) || UUID_RE.test(trimmed) || LONG_ID_RE.test(trimmed);
  if (hasTestPattern) {
    return defaultTitleFromType(typeLabel) === "Cours collectif" ? "Creneau test" : defaultTitleFromType(typeLabel);
  }
  return trimmed;
}

function shouldShowStatusBadge(status: string): boolean {
  const normalized = (status || "").toUpperCase();
  return !(normalized === "SCHEDULED" || normalized === "PLANNED");
}

export default function MonthEventChip({ event, href }: MonthEventChipProps): JSX.Element {
  const teacherFullName = (event.teacher_display_name || "").trim();
  const teacherMissing = teacherFullName.length === 0;
  const teacherCompact = teacherMissing ? "(non renseigne)" : compactTeacherName(teacherFullName);
  const locationLabel = (event.location_label || "").trim() || "Lieu";
  const typeLabel = normalizedTypeLabel(event.type_label);
  const displayTitle = sanitizeTitle(event.title, typeLabel);
  const startTime = formatEventTime(event.start_at_utc);
  const endTime = formatEventTime(event.end_at_utc);
  const tooltip = `${startTime}-${endTime}\n${event.title}\nProf: ${teacherMissing ? "(non renseigne)" : teacherFullName}\nLieu: ${locationLabel}\nType: ${typeLabel}\nStatut: ${event.status_label}`;
  const showStatusBadge = shouldShowStatusBadge(event.status);

  return (
    <a className="month-event-chip" href={href} title={tooltip}>
      <div className="month-event-chip-meta">
        <span className="month-event-chip-time">{startTime}</span>
        <span className="month-event-chip-badges">
          <span className="month-badge month-badge-type">{typeLabel}</span>
          {showStatusBadge ? <span className={`month-badge ${statusBadgeClass(event.status)}`}>{event.status_label}</span> : null}
        </span>
      </div>
      <p className="month-event-chip-title">{displayTitle}</p>
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
