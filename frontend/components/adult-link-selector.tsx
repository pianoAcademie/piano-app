"use client";

import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { normalizeUiLanguage, uiText } from "../lib/ui-i18n";

type AdultCandidate = {
  id: string;
  display_name: string;
  email: string;
  mobile_phone_1: string | null;
  mobile_phone_2: string | null;
  home_phone: string | null;
  address_line: string | null;
  postal_code: string | null;
  city: string | null;
  address_country: string;
  residence_country: string;
};

type Props = {
  adults: AdultCandidate[];
  language?: "fr" | "en";
};

export default function AdultLinkSelector({ adults, language }: Props): JSX.Element {
  const searchParams = useSearchParams();
  const resolvedLanguage = language ?? normalizeUiLanguage(searchParams?.get("lang"));
  const [selectedId, setSelectedId] = useState<string>("");
  const t = (key: string, values?: Record<string, string | number>) => uiText(resolvedLanguage, key, values);
  const selected = useMemo(
    () => adults.find((adult) => adult.id === selectedId) ?? null,
    [adults, selectedId],
  );

  return (
    <div className="grid">
      <label>
        {t("admin.clients.existing_adult_to_link")}
        <select name="existing_adult_id" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
          <option value="">{t("admin.clients.no_existing_adult")}</option>
          {adults.map((adult) => (
            <option key={adult.id} value={adult.id}>
              {adult.display_name}
            </option>
          ))}
        </select>
      </label>

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
