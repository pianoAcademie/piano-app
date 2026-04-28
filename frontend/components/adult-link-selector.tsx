"use client";

import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

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
  const resolvedLanguage = language ?? (searchParams?.get("lang") === "en" ? "en" : "fr");
  const isEnglish = resolvedLanguage === "en";
  const [selectedId, setSelectedId] = useState<string>("");
  const selected = useMemo(
    () => adults.find((adult) => adult.id === selectedId) ?? null,
    [adults, selectedId],
  );

  return (
    <div className="grid">
      <label>
        {isEnglish ? "Existing adult to link" : "Adulte existant a rattacher"}
        <select name="existing_adult_id" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
          <option value="">{isEnglish ? "None" : "Aucun"}</option>
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
            {selected.email} | {isEnglish ? "Mobile 1" : "Mobile 1"}: {selected.mobile_phone_1 ?? "-"} | {isEnglish ? "Mobile 2" : "Mobile 2"}: {selected.mobile_phone_2 ?? "-"} | {isEnglish ? "Home" : "Domicile"}:{" "}
            {selected.home_phone ?? "-"}
          </p>
          <p className="muted">
            {isEnglish ? "Address" : "Adresse"}: {selected.address_line ?? "-"}, {selected.postal_code ?? "-"} {selected.city ?? "-"} ({selected.address_country}) | {isEnglish ? "Residence" : "Residence"}:{" "}
            {selected.residence_country}
          </p>
        </article>
      ) : null}
    </div>
  );
}
