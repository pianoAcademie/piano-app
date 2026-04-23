import MonthEventChip, { type PlanningEventChipData } from "./month-event-chip";
import { type UiLanguage, uiText } from "../../lib/ui-i18n";

type MonthDayCardProps = {
  language: UiLanguage;
  dayLabel: string;
  events: PlanningEventChipData[];
  isToday: boolean;
  maxVisibleEvents?: number;
  dayDetailsHref: string;
  openSessionHref: (sessionId: string) => string;
  expanded?: boolean;
};

export default function MonthDayCard({
  language,
  dayLabel,
  events,
  isToday,
  maxVisibleEvents = 5,
  dayDetailsHref,
  openSessionHref,
  expanded = false,
}: MonthDayCardProps): JSX.Element {
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const visibleEvents = events.slice(0, maxVisibleEvents);
  const remainingCount = Math.max(events.length - visibleEvents.length, 0);

  return (
    <article className={`agenda-day month-day-card ${expanded ? "expanded" : ""} ${isToday ? "today" : ""}`}>
      <div className="month-day-card-header">
        <h3>
          {dayLabel}
          {isToday ? <span className="month-day-card-today-dot" aria-hidden="true" /> : null}
        </h3>
        {events.length > 0 ? <span className="badge">{events.length}</span> : null}
      </div>

      {events.length > 0 ? (
        <div className="month-day-card-body">
          <div className="month-day-card-events">
            {visibleEvents.map((event) => (
              <MonthEventChip
                key={event.id}
                language={language}
                event={event}
                href={openSessionHref(event.id)}
                expanded={expanded}
                compact={!expanded}
              />
            ))}
          </div>
          {remainingCount > 0 ? (
            <a className="month-day-card-more" href={dayDetailsHref}>
              {t("admin.planning.more_events", { count: remainingCount })}
            </a>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
