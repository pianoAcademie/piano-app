"use client";

import { useEffect, useMemo, useState } from "react";

type ProposedSlot = {
  key: string;
  label: string;
  start_time: string;
  end_time: string;
};

type QuoteFollowupSlotFormProps = {
  followupId: string;
  returnTo: string;
  proposedSlots: ProposedSlot[];
  submitAction: (formData: FormData) => Promise<void>;
};

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function QuoteFollowupSlotForm({
  followupId,
  returnTo,
  proposedSlots,
  submitAction,
}: QuoteFollowupSlotFormProps): JSX.Element {
  const [selectedSlotKey, setSelectedSlotKey] = useState<string>("");
  const [slotDate, setSlotDate] = useState<string>(todayIso());
  const [startTime, setStartTime] = useState<string>("");
  const [endTime, setEndTime] = useState<string>("");

  const selectedSlot = useMemo(
    () => proposedSlots.find((row) => row.key === selectedSlotKey) ?? null,
    [proposedSlots, selectedSlotKey],
  );

  useEffect(() => {
    if (!selectedSlot) {
      return;
    }
    setStartTime(selectedSlot.start_time);
    setEndTime(selectedSlot.end_time);
  }, [selectedSlot]);

  return (
    <form action={submitAction} className="card quote-followup-form">
      <h4>Selectionner / modifier le creneau solfege</h4>
      <input type="hidden" name="followup_id" value={followupId} />
      <input type="hidden" name="return_to" value={returnTo} />
      {proposedSlots.length > 0 ? (
        <label>
          Creneau propose
          <select value={selectedSlotKey} onChange={(event) => setSelectedSlotKey(event.target.value)}>
            <option value="">Saisie manuelle</option>
            {proposedSlots.map((row) => (
              <option key={row.key} value={row.key}>
                {row.label}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <p className="muted">Aucun creneau preconfigure trouve. Saisie manuelle.</p>
      )}
      <label>
        Date
        <input type="date" name="slot_date" value={slotDate} onChange={(event) => setSlotDate(event.target.value)} required />
      </label>
      <label>
        Debut
        <input type="time" name="slot_start_time" value={startTime} onChange={(event) => setStartTime(event.target.value)} required />
      </label>
      <label>
        Fin
        <input type="time" name="slot_end_time" value={endTime} onChange={(event) => setEndTime(event.target.value)} required />
      </label>
      <button type="submit">Enregistrer creneau</button>
    </form>
  );
}
