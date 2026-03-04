import type { ReactNode } from "react";

type ListRowProps = {
  title: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  href?: string;
};

export default function ListRow({ title, subtitle, right, href }: ListRowProps): JSX.Element {
  const content = (
    <>
      <div className="client-list-row-main">
        <strong>{title}</strong>
        {subtitle ? <p className="muted">{subtitle}</p> : null}
      </div>
      {right ? <div className="client-list-row-right">{right}</div> : null}
    </>
  );

  if (href) {
    return (
      <a className="client-list-row item" href={href}>
        {content}
      </a>
    );
  }

  return <article className="client-list-row item">{content}</article>;
}
