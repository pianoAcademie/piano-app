import type { AdminSessionOut } from "../../lib/types";
import MonthEventChip from "./month-event-chip";

type MonthDayCardProps = {
  dayLabel: string;
  events: AdminSessionOut[];
  isToday: boolean;
  maxVisibleEvents?: number;
  dayDetailsHref: string;
  openSessionHref: (sessionId: string) => string;
};

export default function MonthDayCard({
  dayLabel,
  events,
  isToday,
  maxVisibleEvents = 5,
  dayDetailsHref,
  openSessionHref,
}: MonthDayCardProps): JSX.Element {
  const visibleEvents = events.slice(0, maxVisibleEvents);
  const remainingCount = Math.max(events.length - visibleEvents.length, 0);

  return (
    <article className={`agenda-day month-day-card ${isToday ? "today" : ""}`}>
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
              <MonthEventChip key={event.id} event={event} href={openSessionHref(event.id)} />
            ))}
          </div>
          {remainingCount > 0 ? (
            <a className="month-day-card-more" href={dayDetailsHref}>
              +{remainingCount} autres
            </a>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
