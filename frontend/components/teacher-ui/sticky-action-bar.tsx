import type { ReactNode } from "react";

type StickyActionBarProps = {
  children: ReactNode;
};

export default function StickyActionBar({ children }: StickyActionBarProps): JSX.Element {
  return <div className="teacher-sticky-action-bar">{children}</div>;
}
