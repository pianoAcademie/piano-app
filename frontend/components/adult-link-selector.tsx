"use client";

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
};

export default function AdultLinkSelector({ adults }: Props): JSX.Element {
  const [selectedId, setSelectedId] = useState<string>("");
  const selected = useMemo(
    () => adults.find((adult) => adult.id === selectedId) ?? null,
    [adults, selectedId],
  );

  return (
    <div className="grid">
      <label>
        Adulte existant a rattacher
        <select name="existing_adult_id" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
          <option value="">Aucun</option>
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
            {selected.email} | Mobile 1: {selected.mobile_phone_1 ?? "-"} | Mobile 2: {selected.mobile_phone_2 ?? "-"} | Domicile:{" "}
            {selected.home_phone ?? "-"}
          </p>
          <p className="muted">
            Adresse: {selected.address_line ?? "-"}, {selected.postal_code ?? "-"} {selected.city ?? "-"} ({selected.address_country}) | Residence:{" "}
            {selected.residence_country}
          </p>
        </article>
      ) : null}
    </div>
  );
}
