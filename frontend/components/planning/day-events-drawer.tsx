import type { UiLanguage } from "../../lib/ui-messages";
import MonthEventChip, { type PlanningEventChipData } from "./month-event-chip";

type DayEventsDrawerProps = {
  isOpen: boolean;
  dayLabel: string;
  events: PlanningEventChipData[];
  language?: UiLanguage;
  closeHref: string;
  openSessionHref: (sessionId: string) => string;
};

export default function DayEventsDrawer({
  isOpen,
  dayLabel,
  events,
  language = "fr",
  closeHref,
  openSessionHref,
}: DayEventsDrawerProps): JSX.Element | null {
  if (!isOpen) {
    return null;
  }

  const countLabel =
    language === "en"
      ? `${events.length} ${events.length === 1 ? "slot" : "slots"}`
      : `${events.length} cours`;

  return (
    <section className="modal-overlay">
      <article className="modal-panel day-events-drawer-panel">
        <a className="modal-close-x" href={closeHref} aria-label={language === "en" ? "Close" : "Fermer"}>
          ×
        </a>
        <h2 className="modal-title">{language === "en" ? `Schedule for ${dayLabel}` : `Journee du ${dayLabel}`}</h2>
        <p className="muted">{countLabel}</p>

        {events.length === 0 ? (
          <p className="muted">{countLabel}</p>
        ) : (
          <div className="day-events-drawer-list">
            {events.map((event) => (
              <MonthEventChip
                key={`drawer-${event.id}`}
                event={event}
                href={openSessionHref(event.id)}
                language={language}
              />
            ))}
          </div>
        )}
      </article>
    </section>
  );
}
