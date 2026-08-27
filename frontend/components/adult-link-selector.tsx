"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import type { AdminAdultCandidateOut } from "../lib/types";
import { normalizeUiLanguage, uiText } from "../lib/ui-i18n";

type Props = {
  adults?: AdminAdultCandidateOut[];
  language?: "fr" | "en";
};

export default function AdultLinkSelector({ adults = [], language }: Props): JSX.Element {
  const searchParams = useSearchParams();
  const resolvedLanguage = language ?? normalizeUiLanguage(searchParams?.get("lang"));
  const [selectedId, setSelectedId] = useState<string>("");
  const [query, setQuery] = useState<string>("");
  const [knownAdults, setKnownAdults] = useState<AdminAdultCandidateOut[]>(adults);
  const [isSearching, setIsSearching] = useState(false);
  const [searchFailed, setSearchFailed] = useState(false);
  const t = (key: string, values?: Record<string, string | number>) => uiText(resolvedLanguage, key, values);
  const normalize = (value: string | null | undefined) =>
    (value ?? "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .trim();
  const sortedAdults = useMemo(
    () =>
      [...knownAdults].sort((left, right) =>
        left.display_name.localeCompare(right.display_name, resolvedLanguage, { sensitivity: "base" }),
      ),
    [knownAdults, resolvedLanguage],
  );

  useEffect(() => {
    const needle = query.trim();
    if (!needle) {
      setIsSearching(false);
      setSearchFailed(false);
      return;
    }

    const controller = new AbortController();
    const timeoutId = window.setTimeout(async () => {
      setIsSearching(true);
      setSearchFailed(false);
      try {
        const response = await fetch(`/api/admin/clients/adult-candidates?q=${encodeURIComponent(needle)}`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Adult search failed (${response.status})`);
        }
        const matches = (await response.json()) as AdminAdultCandidateOut[];
        setKnownAdults((current) => {
          const merged = new Map(current.map((adult) => [adult.id, adult]));
          for (const adult of matches) {
            merged.set(adult.id, adult);
          }
          return [...merged.values()];
        });
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setSearchFailed(true);
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
  }, [query]);
  const filteredAdults = useMemo(() => {
    const needle = normalize(query);
    if (!needle) {
      return sortedAdults;
    }
    return sortedAdults.filter((adult) => {
      const haystack = normalize(
        [
          adult.display_name,
          adult.email,
          adult.mobile_phone_1,
          adult.mobile_phone_2,
          adult.home_phone,
          adult.city,
          adult.postal_code,
        ]
          .filter(Boolean)
          .join(" "),
      );
      return haystack.includes(needle);
    });
  }, [query, sortedAdults]);
  const selected = useMemo(
    () => sortedAdults.find((adult) => adult.id === selectedId) ?? null,
    [sortedAdults, selectedId],
  );
  const selectOptions = useMemo(() => {
    if (!selected || filteredAdults.some((adult) => adult.id === selected.id)) {
      return filteredAdults;
    }
    return [selected, ...filteredAdults];
  }, [filteredAdults, selected]);
  const statusMessage = !query.trim()
    ? t("admin.clients.existing_adult_search_prompt")
    : isSearching
      ? t("admin.clients.existing_adult_searching")
      : searchFailed
        ? t("admin.clients.existing_adult_search_error")
        : filteredAdults.length > 0
          ? t("admin.clients.existing_adult_matches", { count: filteredAdults.length })
          : t("admin.clients.no_existing_adult_match");

  return (
    <div className="grid">
      <label>
        {t("common.search")}
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t("admin.clients.existing_adult_search_placeholder")}
          autoComplete="off"
        />
      </label>
      <label>
        {t("admin.clients.existing_adult_to_link")}
        <select name="existing_adult_id" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
          <option value="">{t("admin.clients.no_existing_adult")}</option>
          {selectOptions.map((adult) => (
            <option key={adult.id} value={adult.id}>
              {adult.display_name}
            </option>
          ))}
        </select>
      </label>
      <p className="muted">{statusMessage}</p>

      {selected ? (
        <article className="item">
          <strong>{selected.display_name}</strong>
          <p className="muted">
            {selected.email} | {t("client.mobile_phone_1")}: {selected.mobile_phone_1 ?? "-"} | {t("client.mobile_phone_2")}: {selected.mobile_phone_2 ?? "-"} | {t("client.home_phone_label")}:{" "}
            {selected.home_phone ?? "-"}
          </p>
          <p className="muted">
            {t("admin.client_detail.address")}: {selected.address_line ?? "-"}, {selected.postal_code ?? "-"} {selected.city ?? "-"} ({selected.address_country}) | {t("admin.client_detail.country_residence")}:{" "}
            {selected.residence_country}
          </p>
        </article>
      ) : null}
    </div>
  );
}
