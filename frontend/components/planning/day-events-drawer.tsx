import MonthEventChip, { type PlanningEventChipData } from "./month-event-chip";
import { type UiLanguage, uiText } from "../../lib/ui-i18n";

type DayEventsDrawerProps = {
  language: UiLanguage;
  isOpen: boolean;
  dayLabel: string;
  events: PlanningEventChipData[];
  closeHref: string;
  openSessionHref: (sessionId: string) => string;
};

export default function DayEventsDrawer({
  language,
  isOpen,
  dayLabel,
  events,
  closeHref,
  openSessionHref,
}: DayEventsDrawerProps): JSX.Element | null {
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  if (!isOpen) {
    return null;
  }

  return (
    <section className="modal-overlay">
      <article className="modal-panel day-events-drawer-panel">
        <a className="modal-close-x" href={closeHref} aria-label={t("common.close")}>
          ×
        </a>
        <h2 className="modal-title">{t("admin.planning.day_events_title", { day: dayLabel })}</h2>
        <p className="muted">{t("admin.planning.courses_count", { count: events.length })}</p>

        {events.length === 0 ? (
          <p className="muted">{t("admin.planning.zero_courses")}</p>
        ) : (
          <div className="day-events-drawer-list">
            {events.map((event) => (
              <MonthEventChip key={`drawer-${event.id}`} language={language} event={event} href={openSessionHref(event.id)} />
            ))}
          </div>
        )}
      </article>
    </section>
  );
}
