"use client";

import { useState } from "react";

import { professorConfirmLocalIntakeAction } from "../lib/actions";
import type { ProfessorLocalIntakeDetailOut } from "../lib/types";

type PartitionMode = "catalog" | "custom" | "none";

export default function ProfessorLocalIntakeForm({ intake }: { intake: ProfessorLocalIntakeDetailOut }): JSX.Element {
  const initialMode: PartitionMode = intake.local_confirmation_partition_not_required
    ? "none"
    : intake.local_confirmation_product_id
      ? "catalog"
      : intake.local_confirmation_partition_snapshot
        ? "custom"
        : "catalog";
  const [partitionMode, setPartitionMode] = useState<PartitionMode>(initialMode);
  const [selectedSessionId, setSelectedSessionId] = useState(intake.local_confirmation_session_id ?? "");

  return (
    <form action={professorConfirmLocalIntakeAction} className="teacher-intake-form">
      <input type="hidden" name="intake_id" value={intake.id} />
      <input type="hidden" name="return_to" value={`/prof/intakes/${intake.id}`} />

      <fieldset className="teacher-intake-fieldset">
        <legend>1. Créneau à confirmer</legend>
        <p className="muted">Créneaux à venir de votre planning Bar-le-Duc. Une série récurrente n’est affichée qu’une fois.</p>
        {intake.slot_options.length === 0 ? (
          <p className="teacher-intake-empty">Aucun créneau futur Bar-le-Duc n’est disponible dans votre planning.</p>
        ) : (
          <div className="teacher-intake-option-list">
            {intake.slot_options.map((slot) => {
              const checked = selectedSessionId === slot.session_id;
              return (
                <label key={slot.session_id} className={`teacher-intake-option ${checked ? "selected" : ""}`}>
                  <input
                    type="radio"
                    name="session_id"
                    value={slot.session_id}
                    checked={checked}
                    onChange={() => setSelectedSessionId(slot.session_id)}
                    required
                  />
                  <span>
                    <strong>{slot.label}</strong>
                    <small>{slot.location_name} · {slot.seats_remaining} place(s) disponible(s)</small>
                  </span>
                </label>
              );
            })}
          </div>
        )}
      </fieldset>

      <fieldset className="teacher-intake-fieldset">
        <legend>2. Partition à donner</legend>
        <div className="teacher-intake-mode-grid" role="radiogroup" aria-label="Type de partition">
          <label className={partitionMode === "catalog" ? "selected" : ""}>
            <input type="radio" name="partition_mode" checked={partitionMode === "catalog"} onChange={() => setPartitionMode("catalog")} />
            Catalogue
          </label>
          <label className={partitionMode === "custom" ? "selected" : ""}>
            <input type="radio" name="partition_mode" checked={partitionMode === "custom"} onChange={() => setPartitionMode("custom")} />
            Autre
          </label>
          <label className={partitionMode === "none" ? "selected" : ""}>
            <input type="radio" name="partition_mode" checked={partitionMode === "none"} onChange={() => setPartitionMode("none")} />
            Aucune
          </label>
        </div>

        {partitionMode === "catalog" ? (
          <label className="teacher-intake-control">
            Choisir dans la liste des partitions
            <select name="product_id" defaultValue={intake.local_confirmation_product_id ?? ""} required>
              <option value="">Choisir une partition</option>
              {intake.partition_options.map((partition) => (
                <option key={partition.product_id} value={partition.product_id}>
                  {partition.title} — stock Bar-le-Duc : {partition.real_quantity}
                </option>
              ))}
            </select>
            {intake.partition_options.length === 0 ? (
              <small className="muted">Aucune partition n’est encore classée dans le catalogue.</small>
            ) : null}
          </label>
        ) : null}

        {partitionMode === "custom" ? (
          <label className="teacher-intake-control">
            Partition à prévoir
            <input
              type="text"
              name="custom_partition"
              defaultValue={
                !intake.local_confirmation_product_id && !intake.local_confirmation_partition_not_required
                  ? intake.local_confirmation_partition_snapshot ?? ""
                  : ""
              }
              placeholder="Titre, compositeur, niveau…"
              maxLength={500}
              required
            />
          </label>
        ) : null}

        {partitionMode === "none" ? (
          <>
            <input type="hidden" name="partition_not_required" value="on" />
            <p className="teacher-intake-none-copy">Aucune partition ne sera demandée pour cet intake.</p>
          </>
        ) : null}
      </fieldset>

      <label className="teacher-intake-control">
        Commentaire facultatif pour l’administration
        <textarea name="comment" defaultValue={intake.local_confirmation_comment ?? ""} rows={3} maxLength={2000} />
      </label>

      <button className="teacher-intake-submit" type="submit" disabled={intake.slot_options.length === 0}>
        {intake.local_confirmation_status === "CONFIRMED" ? "Mettre à jour la confirmation" : "Confirmer pour Bar-le-Duc"}
      </button>
    </form>
  );
}
