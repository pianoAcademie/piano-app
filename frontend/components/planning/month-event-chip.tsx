import { localeForUiLanguage, type UiLanguage, uiText } from "../../lib/ui-i18n";

export type PlanningEventChipData = {
  id: string;
  title: string;
  start_at_utc: string;
  end_at_utc: string;
  timezone?: string;
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
  location_tone?: string;
  show_location_badge?: boolean;
  type_label: string;
  status_label: string;
  status: string;
};

type MonthEventChipProps = {
  language: UiLanguage;
  event: PlanningEventChipData;
  href: string;
  expanded?: boolean;
  compact?: boolean;
};

const UUID_RE = /\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/i;
const TEST_TITLE_RE = /\b(smoke|pa\s*day|test)\b/i;
const LONG_ID_RE = /\b\d{6,}\b/;

function formatEventTime(value: string, timezone?: string, language: UiLanguage = "fr"): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "--:--";
  }
  return parsed.toLocaleTimeString(localeForUiLanguage(language), {
    timeZone: timezone || "Europe/Paris",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
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

function normalizedTypeLabel(value: string, language: UiLanguage = "fr"): string {
  const normalized = (value || "").trim().toLowerCase();
  if (normalized.includes("priv")) {
    return uiText(language, "admin.planning.session_type.private");
  }
  if (normalized.includes("online")) {
    return uiText(language, "admin.planning.session_type.online");
  }
  if (normalized.includes("domicile")) {
    return uiText(language, "admin.planning.session_type.home");
  }
  return uiText(language, "admin.planning.session_type.group");
}

function defaultTitleFromType(typeLabel: string, language: UiLanguage = "fr"): string {
  const normalized = normalizedTypeLabel(typeLabel, language);
  if (normalized === uiText(language, "admin.planning.session_type.private")) {
    return uiText(language, "admin.planning.default_private_course");
  }
  if (normalized === uiText(language, "admin.planning.session_type.online")) {
    return uiText(language, "admin.planning.default_online_course");
  }
  if (normalized === uiText(language, "admin.planning.session_type.home")) {
    return uiText(language, "admin.planning.default_home_course");
  }
  return uiText(language, "admin.planning.default_group_course");
}

function sanitizeTitle(value: string, typeLabel: string, language: UiLanguage = "fr"): string {
  const trimmed = (value || "").trim();
  if (!trimmed) {
    return defaultTitleFromType(typeLabel, language);
  }
  const hasTestPattern = TEST_TITLE_RE.test(trimmed) || UUID_RE.test(trimmed) || LONG_ID_RE.test(trimmed);
  if (hasTestPattern) {
    return defaultTitleFromType(typeLabel, language) === uiText(language, "admin.planning.default_group_course")
      ? uiText(language, "admin.planning.test_slot")
      : defaultTitleFromType(typeLabel, language);
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

function locationToneClass(value: string): string {
  const normalized = (value || "").trim().toLowerCase();
  if (!normalized) {
    return "location-tone-1";
  }
  let hash = 0;
  for (let index = 0; index < normalized.length; index += 1) {
    hash = (hash * 31 + normalized.charCodeAt(index)) >>> 0;
  }
  return `location-tone-${(hash % 6) + 1}`;
}

function compactLocationLabel(value: string, language: UiLanguage = "fr"): string {
  const trimmed = (value || "").trim();
  if (!trimmed) {
    return uiText(language, "common.location");
  }
  if (trimmed.length <= 12) {
    return trimmed;
  }
  const tokens = trimmed.split(/[\s/-]+/).filter((token) => token.length > 0);
  if (tokens.length > 1) {
    const lastToken = tokens[tokens.length - 1];
    if (lastToken.length <= 12) {
      return lastToken;
    }
  }
  return trimmed.slice(0, 12).trim();
}

export default function MonthEventChip({
  language,
  event,
  href,
  expanded = false,
  compact = false,
}: MonthEventChipProps): JSX.Element {
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const teacherFullName = (event.teacher_display_name || "").trim();
  const habitualTeacherName = (event.habitual_teacher_display_name || "").trim();
  const substituteTeacherName = (event.substitute_teacher_display_name || "").trim();
  const effectiveTeacherName = (event.effective_teacher_display_name || teacherFullName).trim();
  const isSubstituteActive = substituteTeacherName.length > 0 && effectiveTeacherName === substituteTeacherName;
  const teacherRequired = event.requires_professor !== false;
  const teacherMissing = teacherRequired && teacherFullName.length === 0;
  const teacherCompactBase = !teacherRequired
    ? t("admin.planning.no_teacher_required")
    : teacherMissing
      ? t("admin.planning.not_provided_compact")
      : compactTeacherName(effectiveTeacherName || teacherFullName);
  const teacherCompact = isSubstituteActive && !teacherMissing ? `${teacherCompactBase} (${t("admin.planning.substitute_short")})` : teacherCompactBase;
  const locationLabel = (event.location_label || "").trim() || t("common.location");
  const typeLabel = normalizedTypeLabel(event.type_label, language);
  const displayTitle = sanitizeTitle(event.title, typeLabel, language);
  const timezone = (event.timezone || "").trim() || "Europe/Paris";
  const startTime = formatEventTime(event.start_at_utc, timezone, language);
  const endTime = formatEventTime(event.end_at_utc, timezone, language);
  const showLocationBadge = Boolean(event.show_location_badge);
  const locationBadgeLabel = compactLocationLabel(locationLabel, language);
  const locationTone = (event.location_tone || "").trim() || locationToneClass(locationLabel);
  const tooltip = [
    `${startTime}-${endTime}`,
    event.title,
    `${t("admin.planning.effective_teacher")}: ${!teacherRequired ? t("admin.planning.no_teacher_required") : teacherMissing ? t("admin.planning.not_provided_compact") : effectiveTeacherName}`,
    isSubstituteActive && habitualTeacherName ? `${t("admin.planning.regular_teacher")}: ${habitualTeacherName}` : null,
    isSubstituteActive && substituteTeacherName ? `${t("admin.planning.substitute_teacher")}: ${substituteTeacherName}` : null,
    `${t("common.location")}: ${locationLabel}`,
    `${t("common.type")}: ${typeLabel}`,
    `${t("common.status")}: ${event.status_label}`,
  ]
    .filter((line): line is string => Boolean(line))
    .join("\n");
  const showStatusBadge = shouldShowStatusBadge(event.status);
  const capacityUsed = resolveCapacityUsed(event);
  const capacityMax = Math.max(0, Math.floor(event.capacity_max || 0));
  const capacityLabel = event.capacity_label?.trim() || `${capacityUsed}/${capacityMax}`;
  return (
    <a
      className={`month-event-chip ${expanded ? "expanded" : ""} ${compact ? "compact" : ""} ${showLocationBadge ? `has-location-cue ${locationTone}` : ""}`}
      href={href}
      title={tooltip}
    >
      <div className="month-event-chip-meta">
        <span className="month-event-chip-time">{startTime}</span>
        <span className="month-event-chip-badges">
          <span className={`month-badge month-badge-capacity ${capacityBadgeClass(capacityUsed, capacityMax)}`}>{capacityLabel}</span>
          {showLocationBadge ? (
            <span className={`month-badge month-badge-location ${locationTone}`} title={locationLabel}>
              {locationBadgeLabel}
            </span>
          ) : null}
          {showStatusBadge ? <span className={`month-badge ${statusBadgeClass(event.status)}`}>{event.status_label}</span> : null}
        </span>
      </div>
      <p className="month-event-chip-title">{displayTitle}</p>
      <p className="month-event-chip-sub">
        <span className={`month-event-chip-prof ${teacherMissing ? "missing" : ""}`}>{t("admin.planning.teacher_short")} : {teacherCompact}</span>
        {teacherMissing ? <span className="month-event-chip-warn" aria-hidden="true">⚠</span> : null}
        <span className="month-event-chip-sep" aria-hidden="true">
          ·
        </span>
        <span className="month-event-chip-location">{locationLabel}</span>
      </p>
    </a>
  );
}
