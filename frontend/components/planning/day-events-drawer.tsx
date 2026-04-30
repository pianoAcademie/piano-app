import { uiText, type UiLanguage } from "../../lib/ui-i18n";
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

  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const countLabel = events.length === 0 ? t("admin.planning.zero_courses") : t("admin.planning.courses_count", { count: events.length });

  return (
    <section className="modal-overlay">
      <article className="modal-panel day-events-drawer-panel">
        <a className="modal-close-x" href={closeHref} aria-label={t("common.close")}>
          ×
        </a>
        <h2 className="modal-title">{t("admin.planning.day_events_title", { day: dayLabel })}</h2>
        <p className="muted">{countLabel}</p>

        {events.length === 0 ? (
          <p className="muted">{t("admin.planning.day_events_empty")}</p>
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
