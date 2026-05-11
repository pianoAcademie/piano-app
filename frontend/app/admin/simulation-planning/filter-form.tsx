"use client";

import type { ReactNode } from "react";
import { useRef } from "react";

type SimulationPlanningFilterFormProps = {
  children: ReactNode;
  className?: string;
};

export function SimulationPlanningFilterForm({ children, className }: SimulationPlanningFilterFormProps): JSX.Element {
  const formRef = useRef<HTMLFormElement>(null);

  return (
    <form
      ref={formRef}
      className={className}
      method="get"
      onChange={(event) => {
        if (event.target instanceof HTMLSelectElement) {
          formRef.current?.requestSubmit();
        }
      }}
    >
      {children}
    </form>
  );
}
