import MonthEventChip, { type PlanningEventChipData } from "./month-event-chip";

type DayEventsDrawerProps = {
  isOpen: boolean;
  dayLabel: string;
  events: PlanningEventChipData[];
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
        <h2 className="modal-title">Journee du {dayLabel}</h2>
        <p className="muted">{events.length} cours.</p>

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
