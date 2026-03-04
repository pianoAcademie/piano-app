import type { ReactNode } from "react";

type UrgentPayCardProps = {
  amountLabel: ReactNode;
  countLabel?: ReactNode;
  children: ReactNode;
};

export default function UrgentPayCard({ amountLabel, countLabel, children }: UrgentPayCardProps): JSX.Element {
  return (
    <section className="client-urgent-pay-card">
      <header className="client-urgent-pay-head">
        <div>
          <h2>À régler</h2>
          <p className="client-urgent-pay-amount">{amountLabel}</p>
        </div>
        {countLabel ? <span className="badge">{countLabel}</span> : null}
      </header>
      <div className="client-urgent-pay-body">{children}</div>
    </section>
  );
}
