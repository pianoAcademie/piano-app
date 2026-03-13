export type PlanningEventChipData = {
  id: string;
  title: string;
  start_at_utc: string;
  end_at_utc: string;
  capacity_max: number;
  booked_count?: number;
  enrolled_count?: number;
  capacity_label?: string;
  teacher_display_name: string;
  habitual_teacher_display_name?: string;
  substitute_teacher_display_name?: string | null;
  effective_teacher_display_name?: string;
  requires_professor?: boolean;
  location_label: string;
  type_label: string;
  status_label: string;
  status: string;
};

type MonthEventChipProps = {
  event: PlanningEventChipData;
  href: string;
  expanded?: boolean;
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

function resolveCapacityUsed(event: PlanningEventChipData): number {
  if (typeof event.enrolled_count === "number" && Number.isFinite(event.enrolled_count)) {
    return Math.max(0, Math.floor(event.enrolled_count));
  }
  if (typeof event.booked_count === "number" && Number.isFinite(event.booked_count)) {
    return Math.max(0, Math.floor(event.booked_count));
  }
  return 0;
}

function capacityBadgeClass(used: number, max: number): string {
  if (max <= 0) {
    return "month-badge-capacity-neutral";
  }
  const ratio = used / max;
  if (ratio >= 1) {
    return "month-badge-capacity-danger";
  }
  if (ratio >= 0.5) {
    return "month-badge-capacity-warning";
  }
  return "month-badge-capacity-neutral";
}

export default function MonthEventChip({ event, href, expanded = false }: MonthEventChipProps): JSX.Element {
  const teacherFullName = (event.teacher_display_name || "").trim();
  const habitualTeacherName = (event.habitual_teacher_display_name || "").trim();
  const substituteTeacherName = (event.substitute_teacher_display_name || "").trim();
  const effectiveTeacherName = (event.effective_teacher_display_name || teacherFullName).trim();
  const isSubstituteActive = substituteTeacherName.length > 0 && effectiveTeacherName === substituteTeacherName;
  const teacherRequired = event.requires_professor !== false;
  const teacherMissing = teacherRequired && teacherFullName.length === 0;
  const teacherCompactBase = !teacherRequired
    ? "non requis"
    : teacherMissing
      ? "(non renseigne)"
      : compactTeacherName(effectiveTeacherName || teacherFullName);
  const teacherCompact = isSubstituteActive && !teacherMissing ? `${teacherCompactBase} (rempl.)` : teacherCompactBase;
  const locationLabel = (event.location_label || "").trim() || "Lieu";
  const typeLabel = normalizedTypeLabel(event.type_label);
  const displayTitle = sanitizeTitle(event.title, typeLabel);
  const startTime = formatEventTime(event.start_at_utc);
  const endTime = formatEventTime(event.end_at_utc);
  const tooltip = [
    `${startTime}-${endTime}`,
    event.title,
    `Prof effectif: ${!teacherRequired ? "non requis" : teacherMissing ? "(non renseigne)" : effectiveTeacherName}`,
    isSubstituteActive && habitualTeacherName ? `Prof habituel: ${habitualTeacherName}` : null,
    isSubstituteActive && substituteTeacherName ? `Remplacant: ${substituteTeacherName}` : null,
    `Lieu: ${locationLabel}`,
    `Type: ${typeLabel}`,
    `Statut: ${event.status_label}`,
  ]
    .filter((line): line is string => Boolean(line))
    .join("\n");
  const showStatusBadge = shouldShowStatusBadge(event.status);
  const capacityUsed = resolveCapacityUsed(event);
  const capacityMax = Math.max(0, Math.floor(event.capacity_max || 0));
  const capacityLabel = event.capacity_label?.trim() || `${capacityUsed}/${capacityMax}`;

  return (
    <a className={`month-event-chip ${expanded ? "expanded" : ""}`} href={href} title={tooltip}>
      <div className="month-event-chip-meta">
        <span className="month-event-chip-time">{startTime}</span>
        <span className="month-event-chip-badges">
          <span className={`month-badge month-badge-capacity ${capacityBadgeClass(capacityUsed, capacityMax)}`}>{capacityLabel}</span>
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
