import type { ReactNode } from "react";

type PlanCardProps = {
  title: string;
  typeBadge: ReactNode;
  memberStatus: string;
  detailLine: string;
  expiryLine: string;
  progressRatio?: number;
  progressLabel?: string;
  action?: ReactNode;
};

export default function PlanCard({
  title,
  typeBadge,
  memberStatus,
  detailLine,
  expiryLine,
  progressRatio,
  progressLabel,
  action,
}: PlanCardProps): JSX.Element {
  return (
    <article className="client-plan-card-v2">
      <div className="client-plan-card-head">
        <h3 title={title}>{title}</h3>
        <span>{typeBadge}</span>
      </div>
      <p className="muted" title={memberStatus}>
        {memberStatus}
      </p>
      {typeof progressRatio === "number" ? (
        <>
          <div className="client-progress" aria-hidden="true">
            <div className="client-progress-bar" style={{ width: `${Math.max(0, Math.min(100, progressRatio))}%` }} />
          </div>
          {progressLabel ? (
            <p className="muted" title={progressLabel}>
              {progressLabel}
            </p>
          ) : null}
        </>
      ) : null}
      <p className="muted" title={detailLine}>
        {detailLine}
      </p>
      <p className="muted" title={expiryLine}>
        {expiryLine}
      </p>
      {action ? <div className="client-plan-card-action">{action}</div> : null}
    </article>
  );
}
