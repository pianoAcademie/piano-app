import type { ReactNode } from "react";

type FilterChipsBarProps = {
  children: ReactNode;
  className?: string;
};

export default function FilterChipsBar({ children, className = "" }: FilterChipsBarProps): JSX.Element {
  return <div className={`client-filter-chips-bar ${className}`.trim()}>{children}</div>;
}
