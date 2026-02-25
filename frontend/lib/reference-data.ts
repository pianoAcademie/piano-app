export type Option<T extends string> = {
  value: T;
  label: string;
};

export const COUNTRY_OPTIONS: Option<string>[] = [
  { value: "FR", label: "France" },
  { value: "BE", label: "Belgique" },
  { value: "CH", label: "Suisse" },
  { value: "LU", label: "Luxembourg" },
  { value: "ES", label: "Espagne" },
  { value: "IT", label: "Italie" },
  { value: "GB", label: "Royaume-Uni" },
  { value: "US", label: "Etats-Unis" },
  { value: "CA", label: "Canada" },
  { value: "DE", label: "Allemagne" },
];

export const TIMEZONE_OPTIONS: Option<string>[] = [
  { value: "Europe/Paris", label: "France (Europe/Paris)" },
  { value: "Europe/Brussels", label: "Belgique (Europe/Brussels)" },
  { value: "Europe/Zurich", label: "Suisse (Europe/Zurich)" },
  { value: "Europe/London", label: "Royaume-Uni (Europe/London)" },
  { value: "Europe/Madrid", label: "Espagne (Europe/Madrid)" },
  { value: "America/New_York", label: "Etats-Unis Est (America/New_York)" },
  { value: "America/Los_Angeles", label: "Etats-Unis Ouest (America/Los_Angeles)" },
];

export const CURRENCY_OPTIONS: Option<string>[] = [
  { value: "EUR", label: "EUR - Euro" },
  { value: "USD", label: "USD - Dollar US" },
];

export const DEFAULT_COUNTRY = "FR";
export const DEFAULT_TIMEZONE = "Europe/Paris";
export const DEFAULT_CURRENCY = "EUR";

export function labelFromOptions(options: Option<string>[], value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  const hit = options.find((option) => option.value === value);
  return hit?.label ?? value;
}
