import { uiText, type UiLanguage } from "../../lib/ui-i18n";
import MonthEventChip, { type PlanningEventChipData } from "./month-event-chip";

type MonthDayCardProps = {
  dayLabel: string;
  events: PlanningEventChipData[];
  isToday: boolean;
  language?: UiLanguage;
  maxVisibleEvents?: number;
  dayDetailsHref: string;
  openSessionHref: (sessionId: string) => string;
  expanded?: boolean;
};

export default function MonthDayCard({
  dayLabel,
  events,
  isToday,
  language = "fr",
  maxVisibleEvents = 5,
  dayDetailsHref,
  openSessionHref,
  expanded = false,
}: MonthDayCardProps): JSX.Element {
  const visibleEvents = events.slice(0, maxVisibleEvents);
  const remainingCount = Math.max(events.length - visibleEvents.length, 0);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

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
                event={event}
                href={openSessionHref(event.id)}
                language={language}
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
