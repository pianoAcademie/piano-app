import { memo } from "react";
import type { ReactNode } from "react";

type TransactionRowProps = {
  typeBadge: ReactNode;
  label: string;
  meta: string;
  amount: string;
  statusBadge: ReactNode;
  actions?: ReactNode;
};

function TransactionRow({ typeBadge, label, meta, amount, statusBadge, actions }: TransactionRowProps): JSX.Element {
  return (
    <article className="client-transaction-row-v2">
      <div className="client-transaction-type">{typeBadge}</div>
      <div className="client-transaction-main">
        <h3 title={label}>{label}</h3>
        <p title={meta}>{meta}</p>
      </div>
      <div className="client-transaction-side">
        <strong>{amount}</strong>
        <span>{statusBadge}</span>
      </div>
      {actions ? <div className="client-transaction-actions">{actions}</div> : null}
    </article>
  );
}

export default memo(TransactionRow);
