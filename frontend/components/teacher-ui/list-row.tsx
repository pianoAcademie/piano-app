import type { ReactNode } from "react";

type ListRowProps = {
  left: ReactNode;
  right?: ReactNode;
  subtitle?: ReactNode;
  href?: string;
};

export default function ListRow({ left, right, subtitle, href }: ListRowProps): JSX.Element {
  const content = (
    <>
      <div className="teacher-list-row-main">
        <strong>{left}</strong>
        {subtitle ? <p className="muted">{subtitle}</p> : null}
      </div>
      {right ? <div className="teacher-list-row-right">{right}</div> : null}
    </>
  );

  if (href) {
    return (
      <a className="teacher-list-row item" href={href}>
        {content}
      </a>
    );
  }

  return <article className="teacher-list-row item">{content}</article>;
}
