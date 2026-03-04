import { memo } from "react";
import type { ReactNode } from "react";

type CompactInvoiceRowProps = {
  title: string;
  statusBadge: ReactNode;
  meta: string;
  subline?: string;
  actions?: ReactNode;
};

function CompactInvoiceRow({ title, statusBadge, meta, subline, actions }: CompactInvoiceRowProps): JSX.Element {
  return (
    <article className="client-compact-invoice-row">
      <div className="client-compact-invoice-main">
        <div className="client-compact-invoice-title-row">
          <h3 title={title}>{title}</h3>
          <span>{statusBadge}</span>
        </div>
        <p title={meta}>{meta}</p>
        {subline ? (
          <p className="client-compact-invoice-subline" title={subline}>
            {subline}
          </p>
        ) : null}
      </div>
      {actions ? <div className="client-compact-invoice-actions">{actions}</div> : null}
    </article>
  );
}

export default memo(CompactInvoiceRow);
