"use client";

import { useMemo, useState } from "react";

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
}: Props): JSX.Element {
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
  const addSelected = (id: string): void => {
    if (!optionById.has(id)) {
      return;
    }
    setSelected((prev) => (prev.includes(id) ? prev : [...prev, id]));
  };

  return (
    <div className={`planning-multi-search ${className ?? ""}`.trim()}>
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

      {selected.map((value) => (
        <input key={value} type="hidden" name={name} value={value} />
      ))}
    </div>
  );
}
