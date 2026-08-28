"use client";

import { useEffect, useMemo, useState } from "react";

type Candidate = {
  id: string;
  label: string;
  email: string;
  client_kind: "ADULT" | "CHILD";
};

type Props = {
  kind: "ADULT" | "CHILD";
  label: string;
  name: string;
  placeholder: string;
  emptyLabel: string;
  noResultsLabel: string;
  searchingLabel: string;
  excludedIds?: string[];
};

export default function ClientLookupSingleSelect({
  kind,
  label,
  name,
  placeholder,
  emptyLabel,
  noResultsLabel,
  searchingLabel,
  excludedIds = [],
}: Props): JSX.Element {
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selected, setSelected] = useState<Candidate | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [failed, setFailed] = useState(false);
  const excluded = useMemo(() => new Set(excludedIds), [excludedIds]);

  useEffect(() => {
    const needle = query.trim();
    if (needle.length < 2) {
      setCandidates([]);
      setIsSearching(false);
      setFailed(false);
      return;
    }

    const controller = new AbortController();
    const timeoutId = window.setTimeout(async () => {
      setIsSearching(true);
      setFailed(false);
      try {
        const params = new URLSearchParams({ q: needle, kind });
        const response = await fetch(`/api/admin/clients/search?${params.toString()}`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Client search failed (${response.status})`);
        }
        const matches = (await response.json()) as Candidate[];
        setCandidates(matches.filter((candidate) => !excluded.has(candidate.id)));
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setCandidates([]);
          setFailed(true);
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsSearching(false);
        }
      }
    }, 250);

    return () => {
      window.clearTimeout(timeoutId);
      controller.abort();
    };
  }, [excluded, kind, query]);

  const options = selected && !candidates.some((candidate) => candidate.id === selected.id)
    ? [selected, ...candidates]
    : candidates;
  const status = query.trim().length < 2
    ? placeholder
    : isSearching
      ? searchingLabel
      : failed
        ? noResultsLabel
        : candidates.length === 0
          ? noResultsLabel
          : "";

  return (
    <div className="grid">
      <label>
        {label}
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={placeholder}
          autoComplete="off"
        />
      </label>
      <label>
        <span className="sr-only">{label}</span>
        <select
          name={name}
          value={selected?.id ?? ""}
          onChange={(event) => {
            const match = options.find((candidate) => candidate.id === event.target.value) ?? null;
            setSelected(match);
          }}
          required
        >
          <option value="">{emptyLabel}</option>
          {options.map((candidate) => (
            <option key={candidate.id} value={candidate.id}>
              {candidate.label}{candidate.email ? ` — ${candidate.email}` : ""}
            </option>
          ))}
        </select>
      </label>
      {status ? <p className="muted">{status}</p> : null}
    </div>
  );
}
