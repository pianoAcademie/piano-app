import type { AdminSessionOut } from "../../lib/types";
import MonthEventChip from "./month-event-chip";

type DayEventsDrawerProps = {
  isOpen: boolean;
  dayLabel: string;
  events: AdminSessionOut[];
  closeHref: string;
  openSessionHref: (sessionId: string) => string;
};

export default function DayEventsDrawer({
  isOpen,
  dayLabel,
  events,
  closeHref,
  openSessionHref,
}: DayEventsDrawerProps): JSX.Element | null {
  if (!isOpen) {
    return null;
  }

  return (
    <section className="modal-overlay">
      <article className="modal-panel day-events-drawer-panel">
        <a className="modal-close-x" href={closeHref} aria-label="Fermer">
          ×
        </a>
        <h2 className="modal-title">Cours du {dayLabel}</h2>
        <p className="muted">{events.length} cours sur cette journee.</p>

        {events.length === 0 ? (
          <p className="muted">0 cours</p>
        ) : (
          <div className="day-events-drawer-list">
            {events.map((event) => (
              <MonthEventChip key={`drawer-${event.id}`} event={event} href={openSessionHref(event.id)} />
            ))}
          </div>
        )}
      </article>
    </section>
  );
}
