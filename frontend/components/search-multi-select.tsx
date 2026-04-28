"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import type { UiLanguage } from "../lib/ui-messages";

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
  language?: UiLanguage;
  className?: string;
  emptySelectionLabel?: string;
  emptySummaryLabel?: string;
  selectedCountLabel?: string;
  removeOptionLabel?: string;
  clearLabel?: string;
  availableOptionsLabel?: string;
  noResultsLabel?: string;
  limitResultsLabel?: string;
  maxSelections?: number;
  requiredSelection?: boolean;
  requiredSelectionMessage?: string;
  onSelectionChange?: (ids: string[]) => void;
};

function applyTemplate(template: string, replacements: Record<string, string | number>): string {
  return Object.entries(replacements).reduce(
    (output, [key, value]) => output.replaceAll(`{${key}}`, String(value)),
    template,
  );
}

function normalize(value: string, language: UiLanguage): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase(language === "en" ? "en-GB" : "fr-FR");
}

export default function SearchMultiSelect({
  label,
  name,
  options,
  selectedIds,
  placeholder,
  language,
  className,
  emptySelectionLabel,
  emptySummaryLabel,
  selectedCountLabel,
  removeOptionLabel,
  clearLabel,
  availableOptionsLabel,
  noResultsLabel,
  limitResultsLabel,
  maxSelections,
  requiredSelection = false,
  requiredSelectionMessage,
  onSelectionChange,
}: Props): JSX.Element {
  const searchParams = useSearchParams();
  const resolvedLanguage: UiLanguage = language ?? (searchParams?.get("lang") === "en" ? "en" : "fr");
  const text = resolvedLanguage === "en"
    ? {
        emptySelection: "No selection.",
        requiredSelection: "Selection required.",
        selectedCount: (count: number) => `${count} selected`,
        emptyState: "Empty selection",
        remove: (optionLabel: string) => `Remove ${optionLabel}`,
        clear: "Clear",
        available: `${label} available`,
        noResult: "No result.",
        resultLimit: "Display limited to 120 results.",
      }
    : {
        emptySelection: "Aucune selection.",
        requiredSelection: "Selection obligatoire.",
        selectedCount: (count: number) => `${count} selection(s)`,
        emptyState: "Selection vide",
        remove: (optionLabel: string) => `Retirer ${optionLabel}`,
        clear: "Vider",
        available: `${label} disponibles`,
        noResult: "Aucun resultat.",
        resultLimit: "Affichage limite a 120 resultats.",
      };
  const rootRef = useRef<HTMLDivElement | null>(null);
  const optionById = useMemo(() => new Map(options.map((option) => [option.id, option])), [options]);
  const sortedOptions = useMemo(
    () => [...options].sort((a, b) => a.label.localeCompare(b.label, resolvedLanguage === "en" ? "en" : "fr")),
    [options, resolvedLanguage],
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
    const normalizedQuery = normalize(query.trim(), resolvedLanguage);
    const candidates = sortedOptions.filter((option) => !selectedSet.has(option.id));
    if (!normalizedQuery) {
      return candidates;
    }
    return candidates.filter((option) => normalize(option.label, resolvedLanguage).includes(normalizedQuery));
  }, [query, resolvedLanguage, selectedSet, sortedOptions]);
  const filteredOptions = matchingOptions.slice(0, 120);
  const hasHiddenOptions = matchingOptions.length > filteredOptions.length;
  const singleSelection = maxSelections === 1;
  const [selectionError, setSelectionError] = useState("");
  const resolvedEmptySelectionLabel = emptySelectionLabel ?? text.emptySelection;
  const resolvedEmptySummaryLabel = emptySummaryLabel ?? text.emptyState;
  const resolvedRequiredSelectionMessage = requiredSelectionMessage ?? text.requiredSelection;

  const selectedCountSummary = (count: number): string =>
    selectedCountLabel ? applyTemplate(selectedCountLabel, { count }) : text.selectedCount(count);

  const removeOptionText = (optionLabel: string): string =>
    removeOptionLabel ? applyTemplate(removeOptionLabel, { label: optionLabel }) : text.remove(optionLabel);

  const availableOptionsText = availableOptionsLabel
    ? applyTemplate(availableOptionsLabel, { label })
    : text.available;

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
      setSelectionError(resolvedRequiredSelectionMessage);
    };
    form.addEventListener("submit", onSubmit);
    return () => form.removeEventListener("submit", onSubmit);
  }, [requiredSelection, resolvedRequiredSelectionMessage, selected]);

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
        <small className="muted">{selected.length > 0 ? selectedCountSummary(selected.length) : resolvedEmptySummaryLabel}</small>
      </div>

      <div className="planning-multi-search-selected" aria-live="polite">
        {selectedOptions.length === 0 ? (
          <small className="muted">{resolvedEmptySelectionLabel}</small>
        ) : (
          selectedOptions.map((option) => (
            <span key={option.id} className="badge planning-multi-search-chip">
              {option.label}
              <button type="button" aria-label={removeOptionText(option.label)} onClick={() => setSelected((prev) => prev.filter((id) => id !== option.id))}>
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
            {clearLabel ?? text.clear}
          </button>
        ) : null}
      </div>

      <div className="planning-multi-search-options" role="listbox" aria-label={availableOptionsText}>
        {filteredOptions.length === 0 ? (
          <small className="muted">{noResultsLabel ?? text.noResult}</small>
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
        {hasHiddenOptions ? <small className="muted">{limitResultsLabel ?? text.resultLimit}</small> : null}
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
