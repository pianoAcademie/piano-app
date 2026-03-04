import { memo } from "react";
import type { ReactNode } from "react";

type UpcomingLessonRowProps = {
  timeLabel: string;
  title: string;
  subtitle: string;
  action?: ReactNode;
};

function UpcomingLessonRow({ timeLabel, title, subtitle, action }: UpcomingLessonRowProps): JSX.Element {
  return (
    <article className="client-upcoming-lesson-row">
      <div className="client-upcoming-lesson-time">{timeLabel}</div>
      <div className="client-upcoming-lesson-main">
        <h3 title={title}>{title}</h3>
        <p title={subtitle}>{subtitle}</p>
      </div>
      {action ? <div className="client-upcoming-lesson-action">{action}</div> : null}
    </article>
  );
}

export default memo(UpcomingLessonRow);
