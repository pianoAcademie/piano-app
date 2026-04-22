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
  emptySummaryLabel?: string;
  maxSelections?: number;
  requiredSelection?: boolean;
  requiredSelectionMessage?: string;
  selectedCountLabel?: string;
  removeOptionLabel?: string;
  clearLabel?: string;
  availableOptionsLabel?: string;
  noResultsLabel?: string;
  limitResultsLabel?: string;
  onSelectionChange?: (ids: string[]) => void;
};

function interpolate(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key) => String(values[key] ?? ""));
}

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
  emptySummaryLabel = "Selection vide",
  maxSelections,
  requiredSelection = false,
  requiredSelectionMessage = "Selection obligatoire.",
  selectedCountLabel = "{count} selection(s)",
  removeOptionLabel = "Retirer {label}",
  clearLabel = "Vider",
  availableOptionsLabel = "{label} disponibles",
  noResultsLabel = "Aucun resultat.",
  limitResultsLabel = "Affichage limite a 120 resultats.",
  onSelectionChange,
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
  useEffect(() => {
    setSelected(Array.from(new Set(selectedIds.filter((id) => optionById.has(id)))));
  }, [selectedIds, optionById]);

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
      setSelectionError(requiredSelectionMessage);
    };
    form.addEventListener("submit", onSubmit);
    return () => form.removeEventListener("submit", onSubmit);
  }, [requiredSelection, requiredSelectionMessage, selected]);

  useEffect(() => {
    if (selected.length > 0 && selectionError) {
      setSelectionError("");
    }
  }, [selected, selectionError]);

  useEffect(() => {
    onSelectionChange?.(selected);
  }, [onSelectionChange, selected]);

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
        <small className="muted">
          {selected.length > 0 ? interpolate(selectedCountLabel, { count: selected.length }) : emptySummaryLabel}
        </small>
      </div>

      <div className="planning-multi-search-selected" aria-live="polite">
        {selectedOptions.length === 0 ? (
          <small className="muted">{emptySelectionLabel}</small>
        ) : (
          selectedOptions.map((option) => (
            <span key={option.id} className="badge planning-multi-search-chip">
              {option.label}
              <button
                type="button"
                aria-label={interpolate(removeOptionLabel, { label: option.label })}
                onClick={() => setSelected((prev) => prev.filter((id) => id !== option.id))}
              >
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
            {clearLabel}
          </button>
        ) : null}
      </div>

      <div className="planning-multi-search-options" role="listbox" aria-label={interpolate(availableOptionsLabel, { label })}>
        {filteredOptions.length === 0 ? (
          <small className="muted">{noResultsLabel}</small>
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
        {hasHiddenOptions ? <small className="muted">{limitResultsLabel}</small> : null}
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
