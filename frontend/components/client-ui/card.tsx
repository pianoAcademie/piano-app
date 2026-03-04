import type { ReactNode } from "react";

type CardProps = {
  children: ReactNode;
  className?: string;
};

export default function Card({ children, className = "" }: CardProps): JSX.Element {
  return <section className={`card client-ui-card ${className}`.trim()}>{children}</section>;
}
