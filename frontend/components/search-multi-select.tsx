"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Option = {
  id: string;
  label: string;
};

type Props = {
  label: string;
  name: string;
  options: Option[];
  selectedIds: string[];
  placeholder: string;
  className?: string;
  emptySelectionLabel?: string;
  maxSelections?: number;
  requiredSelection?: boolean;
};

function normalize(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("fr-FR");
}

export default function SearchMultiSelect({
  label,
  name,
  options,
  selectedIds,
  placeholder,
  className,
  emptySelectionLabel = "Aucune selection.",
  maxSelections,
  requiredSelection = false,
}: Props): JSX.Element {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const optionById = useMemo(() => new Map(options.map((option) => [option.id, option])), [options]);
  const sortedOptions = useMemo(
    () => [...options].sort((a, b) => a.label.localeCompare(b.label, "fr")),
    [options],
  );
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string[]>(
    () => Array.from(new Set(selectedIds.filter((id) => optionById.has(id)))),
  );

  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const selectedOptions = useMemo(
    () => selected.map((id) => optionById.get(id)).filter((option): option is Option => Boolean(option)),
    [optionById, selected],
  );

  const matchingOptions = useMemo(() => {
    const normalizedQuery = normalize(query.trim());
    const candidates = sortedOptions.filter((option) => !selectedSet.has(option.id));
    if (!normalizedQuery) {
      return candidates;
    }
    return candidates.filter((option) => normalize(option.label).includes(normalizedQuery));
  }, [query, selectedSet, sortedOptions]);
  const filteredOptions = matchingOptions.slice(0, 120);
  const hasHiddenOptions = matchingOptions.length > filteredOptions.length;
  const singleSelection = maxSelections === 1;
  const [selectionError, setSelectionError] = useState("");

  useEffect(() => {
    if (!requiredSelection) {
      setSelectionError("");
      return;
    }
    const root = rootRef.current;
    const form = root?.closest("form");
    if (!form) {
      return;
    }
    const onSubmit = (event: Event): void => {
      if (selected.length > 0) {
        setSelectionError("");
        return;
      }
      event.preventDefault();
      setSelectionError("Selectionnez un eleve dans la liste.");
    };
    form.addEventListener("submit", onSubmit);
    return () => form.removeEventListener("submit", onSubmit);
  }, [requiredSelection, selected]);

  useEffect(() => {
    if (selected.length > 0 && selectionError) {
      setSelectionError("");
    }
  }, [selected, selectionError]);

  const addSelected = (id: string): void => {
    if (!optionById.has(id)) {
      return;
    }
    setSelected((prev) => {
      if (singleSelection) {
        return prev[0] === id ? prev : [id];
      }
      if (prev.includes(id)) {
        return prev;
      }
      if (typeof maxSelections === "number" && maxSelections > 0 && prev.length >= maxSelections) {
        return prev;
      }
      return [...prev, id];
    });
  };

  return (
    <div ref={rootRef} className={`planning-multi-search ${className ?? ""}`.trim()}>
      <div className="planning-multi-search-head">
        <strong>{label}</strong>
        <small className="muted">{selected.length > 0 ? `${selected.length} selection(s)` : "Selection vide"}</small>
      </div>

      <div className="planning-multi-search-selected" aria-live="polite">
        {selectedOptions.length === 0 ? (
          <small className="muted">{emptySelectionLabel}</small>
        ) : (
          selectedOptions.map((option) => (
            <span key={option.id} className="badge planning-multi-search-chip">
              {option.label}
              <button type="button" aria-label={`Retirer ${option.label}`} onClick={() => setSelected((prev) => prev.filter((id) => id !== option.id))}>
                ×
              </button>
            </span>
          ))
        )}
      </div>

      <div className="planning-multi-search-toolbar">
        <input
          type="search"
          className="planning-multi-search-input"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              const first = filteredOptions[0];
              if (first) {
                addSelected(first.id);
                setQuery("");
              }
            }
          }}
          placeholder={placeholder}
        />
        {selected.length > 0 ? (
          <button type="button" className="reset-link planning-multi-search-clear" onClick={() => setSelected([])}>
            Vider
          </button>
        ) : null}
      </div>

      <div className="planning-multi-search-options" role="listbox" aria-label={`${label} disponibles`}>
        {filteredOptions.length === 0 ? (
          <small className="muted">Aucun resultat.</small>
        ) : (
          filteredOptions.map((option) => (
            <button
              key={option.id}
              type="button"
              className="planning-multi-search-option"
              onClick={() => {
                addSelected(option.id);
                setQuery("");
              }}
            >
              {option.label}
            </button>
          ))
        )}
        {hasHiddenOptions ? <small className="muted">Affichage limite a 120 resultats.</small> : null}
      </div>

      {selectionError ? (
        <small className="planning-multi-search-error" role="alert">
          {selectionError}
        </small>
      ) : null}

      {singleSelection ? (
        <input type="hidden" name={name} value={selected[0] ?? ""} />
      ) : (
        selected.map((value) => <input key={value} type="hidden" name={name} value={value} />)
      )}
    </div>
  );
}
