import type { ReactNode } from "react";

type KPIBlockProps = {
  label: string;
  value: ReactNode;
  helper?: ReactNode;
};

export default function KPIBlock({ label, value, helper }: KPIBlockProps): JSX.Element {
  return (
    <article className="client-kpi-block">
      <small>{label}</small>
      <strong>{value}</strong>
      {helper ? <p className="muted">{helper}</p> : null}
    </article>
  );
}
