"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

type LocationOption = {
  id: string;
  name: string;
};

type Props = {
  accountId: string;
  language: "fr" | "en";
  locations: LocationOption[];
  selectedLocationIds: string[];
  hasExplicitSelection: boolean;
};

export default function ClientBookingLocationPreferences({
  accountId,
  language,
  locations,
  selectedLocationIds,
  hasExplicitSelection,
}: Props): JSX.Element | null {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const allowedIds = useMemo(() => new Set(locations.map((location) => location.id)), [locations]);
  const defaultIds = useMemo(() => locations.map((location) => location.id), [locations]);
  const [selectedIds, setSelectedIds] = useState(selectedLocationIds);
  const [isPending, startTransition] = useTransition();
  const storageKey = `piano-academie:booking-favorite-locations:${accountId}`;

  const applySelection = (nextIds: string[], mode: "replace" | "push" = "replace"): void => {
    const normalized = Array.from(new Set(nextIds.filter((id) => allowedIds.has(id))));
    if (normalized.length === 0) {
      return;
    }
    setSelectedIds(normalized);
    window.localStorage.setItem(storageKey, JSON.stringify(normalized));
    const nextParams = new URLSearchParams(searchParams.toString());
    nextParams.set("favorite_location_ids", normalized.join(","));
    nextParams.delete("location_id");
    nextParams.delete("session_id");
    nextParams.delete("session_member_id");
    const href = `${pathname}?${nextParams.toString()}`;
    startTransition(() => {
      if (mode === "push") {
        router.push(href, { scroll: false });
      } else {
        router.replace(href, { scroll: false });
      }
    });
  };

  useEffect(() => {
    if (hasExplicitSelection || locations.length === 0) {
      return;
    }
    try {
      const stored = JSON.parse(window.localStorage.getItem(storageKey) || "[]") as unknown;
      if (!Array.isArray(stored)) {
        return;
      }
      const storedIds = stored.map(String).filter((id) => allowedIds.has(id));
      if (storedIds.length > 0 && storedIds.join(",") !== defaultIds.join(",")) {
        applySelection(storedIds);
      }
    } catch {
      // A malformed or unavailable local preference should never block the planning.
    }
    // The initial URL is the source of truth after hydration.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (locations.length === 0) {
    return null;
  }

  const allSelected = selectedIds.length === locations.length;
  const summary = language === "en"
    ? `Favorites · ${selectedIds.length}`
    : `Favoris · ${selectedIds.length}`;

  return (
    <details className="client-booking-location-preferences">
      <summary>
        <span aria-hidden="true">⌖</span>
        <strong>{summary}</strong>
        {isPending ? <small>{language === "en" ? "Updating…" : "Mise à jour…"}</small> : null}
      </summary>
      <div className="client-booking-location-options">
        {locations.map((location) => {
          const checked = selectedIds.includes(location.id);
          return (
            <label key={location.id} className={checked ? "selected" : ""}>
              <input
                type="checkbox"
                checked={checked}
                disabled={isPending || (checked && selectedIds.length === 1)}
                onChange={() => {
                  const nextIds = checked
                    ? selectedIds.filter((id) => id !== location.id)
                    : [...selectedIds, location.id];
                  applySelection(nextIds, "push");
                }}
              />
              <span>{location.name}</span>
            </label>
          );
        })}
        {!allSelected ? (
          <button type="button" disabled={isPending} onClick={() => applySelection(defaultIds, "push")}>
            {language === "en" ? "Select all" : "Tout sélectionner"}
          </button>
        ) : null}
      </div>
      <p>
        {language === "en"
          ? "Only these physical locations are shown by default. Your choice is saved on this device."
          : "Seuls ces lieux physiques sont affichés par défaut. Votre choix est mémorisé sur cet appareil."}
      </p>
    </details>
  );
}
