"use client";

import { useState, useTransition } from "react";

import {
  movePlanningReorganizationBookingAction,
  previewPlanningReorganizationBookingMoveAction,
  type PlanningReorganizationMovePreview,
} from "../../../lib/actions";

export type PlanningReorganizationBooking = {
  id: string;
  client_id: string;
  client_display_name: string;
  status: string;
  student_note: string | null;
};

export type PlanningReorganizationSession = {
  id: string;
  title: string;
  type_label: string;
  location_id: string;
  location_label: string;
  teacher_display_name: string;
  start_at_utc: string;
  end_at_utc: string;
  timezone: string;
  capacity_max: number;
  booked_count: number;
  recurrence_group_id: string | null;
  recurrence_rule: string | null;
  status: string;
  bookings: PlanningReorganizationBooking[];
};

type DraggedBooking = {
  bookingId: string;
  sourceSessionId: string;
  label: string;
};

type PlanningReorganizationBoardProps = {
  sessions: PlanningReorganizationSession[];
  returnTo: string;
  language?: "fr" | "en";
};

type PendingPriceConfirmation = {
  booking: DraggedBooking;
  targetSessionId: string;
  targetLabel: string;
  preview: PlanningReorganizationMovePreview;
};

function formatTime(value: string, timezone: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("fr-FR", {
    timeZone: timezone || "Europe/Paris",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function sessionTimeLabel(session: PlanningReorganizationSession): string {
  return `${formatTime(session.start_at_utc, session.timezone)} - ${formatTime(session.end_at_utc, session.timezone)}`;
}

function formatPriceRange(minimum: number, maximum: number, currency: string, language: "fr" | "en"): string {
  const formatter = new Intl.NumberFormat(language === "en" ? "en-GB" : "fr-FR", {
    style: "currency",
    currency: currency || "EUR",
  });
  return minimum === maximum ? formatter.format(minimum) : `${formatter.format(minimum)} - ${formatter.format(maximum)}`;
}

export function PlanningReorganizationBoard({
  sessions,
  returnTo,
  language = "fr",
}: PlanningReorganizationBoardProps): JSX.Element {
  const [dragged, setDragged] = useState<DraggedBooking | null>(null);
  const [selected, setSelected] = useState<DraggedBooking | null>(null);
  const [dragOverSessionId, setDragOverSessionId] = useState<string | null>(null);
  const [scope, setScope] = useState<"single" | "series_future">("single");
  const [priceConfirmation, setPriceConfirmation] = useState<PendingPriceConfirmation | null>(null);
  const [interactionError, setInteractionError] = useState("");
  const [isPending, startTransition] = useTransition();

  function submitMove(
    bookingToMove: DraggedBooking,
    targetSessionId: string,
    pricePolicy: "keep_source" | "apply_target",
  ): void {
    const formData = new FormData();
    formData.set("booking_id", bookingToMove.bookingId);
    formData.set("target_session_id", targetSessionId);
    formData.set("scope", scope);
    formData.set("price_policy", pricePolicy);
    formData.set("return_to", returnTo);
    setSelected(null);
    setPriceConfirmation(null);
    void movePlanningReorganizationBookingAction(formData);
  }

  function moveToSession(targetSessionId: string): void {
    const bookingToMove = dragged ?? selected;
    if (!bookingToMove || bookingToMove.sourceSessionId === targetSessionId || isPending) {
      return;
    }
    setInteractionError("");
    startTransition(async () => {
      const previewResult = await previewPlanningReorganizationBookingMoveAction({
        bookingId: bookingToMove.bookingId,
        targetSessionId,
        scope,
      });
      if (!previewResult.ok) {
        setInteractionError(previewResult.message);
        return;
      }
      if (previewResult.data.price_change) {
        const targetSession = sessions.find((session) => session.id === targetSessionId);
        setPriceConfirmation({
          booking: bookingToMove,
          targetSessionId,
          targetLabel: targetSession ? sessionTimeLabel(targetSession) : "",
          preview: previewResult.data,
        });
        return;
      }
      submitMove(bookingToMove, targetSessionId, "keep_source");
    });
  }

  if (sessions.length === 0) {
    return (
      <section className="card reorg-empty">
        <h2>Aucun creneau sur cette journee</h2>
        <p>Selectionnez un autre lieu ou une autre date pour afficher les groupes a reorganiser.</p>
      </section>
    );
  }

  return (
    <section className="card reorg-workspace">
      <div className="reorg-toolbar">
        <div>
          <h2>{language === "en" ? "Placement workspace" : "Atelier de placement"}</h2>
          <p>
            {language === "en"
              ? "Drag a student, or tap their name and choose another slot. Capacity rules still apply."
              : "Glissez un eleve, ou touchez son nom puis choisissez un autre creneau. Les capacites restent controlees."}
          </p>
        </div>
        <label className="reorg-scope">
          {language === "en" ? "Scope" : "Portee"}
          <select value={scope} onChange={(event) => setScope(event.target.value as "single" | "series_future")}>
            <option value="single">{language === "en" ? "This session only" : "Cette seance uniquement"}</option>
            <option value="series_future">{language === "en" ? "Remaining series" : "Suite de la serie"}</option>
          </select>
        </label>
      </div>
      <p className="reorg-silent-notice">
        {language === "en"
          ? "Silent reorganization: no change email or SMS is sent to students or parents. Regular course reminders remain scheduled."
          : "Reorganisation silencieuse : aucun email ni SMS de changement n'est envoye aux eleves ou aux parents. Les rappels habituels des cours restent programmes."}
      </p>
      {interactionError ? <p className="form-feedback error">{interactionError}</p> : null}
      {isPending ? <p className="form-feedback success">{language === "en" ? "Moving..." : "Deplacement en cours..."}</p> : null}
      <div className="reorg-board" aria-live="polite">
        {sessions.map((session) => {
          const capacityRatio = session.capacity_max > 0 ? session.booked_count / session.capacity_max : 0;
          const tone = capacityRatio >= 1 ? "full" : capacityRatio >= 0.8 ? "busy" : "available";
          const isDropTarget = dragged !== null && dragged.sourceSessionId !== session.id;
          return (
            <article
              className={`reorg-slot ${dragOverSessionId === session.id ? "drag-over" : ""} ${isDropTarget ? "drop-enabled" : ""}`}
              key={session.id}
              onDragOver={(event) => {
                if (!isDropTarget) {
                  return;
                }
                event.preventDefault();
                setDragOverSessionId(session.id);
              }}
              onDragLeave={() => setDragOverSessionId((current) => (current === session.id ? null : current))}
              onDrop={(event) => {
                event.preventDefault();
                setDragOverSessionId(null);
                moveToSession(session.id);
              }}
            >
              <header className="reorg-slot-header">
                <div>
                  <strong>{sessionTimeLabel(session)}</strong>
                  <span>{session.type_label}</span>
                </div>
                <span className={`reorg-capacity ${tone}`}>{session.booked_count}/{session.capacity_max}</span>
              </header>
              {selected && selected.sourceSessionId !== session.id ? (
                <button type="button" className="button-link reorg-mobile-move-button" onClick={() => moveToSession(session.id)}>
                  {language === "en" ? `Move ${selected.label} here` : `Deplacer ${selected.label} ici`}
                </button>
              ) : null}
              <dl className="reorg-slot-meta">
                <div>
                  <dt>Professeur</dt>
                  <dd>{session.teacher_display_name || "-"}</dd>
                </div>
                <div>
                  <dt>Serie</dt>
                  <dd>{session.recurrence_group_id ? "Oui" : "Non"}</dd>
                </div>
              </dl>
              <div className="reorg-student-list">
                {session.bookings.length ? (
                  session.bookings.map((booking) => (
                    <button
                      type="button"
                      className={`reorg-student-card ${selected?.bookingId === booking.id ? "is-selected" : ""}`}
                      draggable
                      key={booking.id}
                      aria-pressed={selected?.bookingId === booking.id}
                      onClick={() => {
                        setSelected((current) =>
                          current?.bookingId === booking.id
                            ? null
                            : {
                                bookingId: booking.id,
                                sourceSessionId: session.id,
                                label: booking.client_display_name,
                              },
                        );
                      }}
                      onDragStart={(event) => {
                        event.dataTransfer.effectAllowed = "move";
                        setDragged({
                          bookingId: booking.id,
                          sourceSessionId: session.id,
                          label: booking.client_display_name,
                        });
                      }}
                      onDragEnd={() => {
                        setDragged(null);
                        setDragOverSessionId(null);
                      }}
                      title={booking.student_note || booking.client_display_name}
                    >
                      <span>{booking.client_display_name}</span>
                      <small>{booking.status}</small>
                    </button>
                  ))
                ) : (
                  <p className="reorg-slot-empty">Aucun eleve inscrit.</p>
                )}
              </div>
            </article>
          );
        })}
      </div>
      {priceConfirmation ? (
        <section className="modal-overlay" role="dialog" aria-modal="true" aria-label={language === "en" ? "Price change" : "Changement tarifaire"}>
          <article className="modal-panel modal-compact reorg-price-modal">
            <button
              className="modal-close-x"
              type="button"
              onClick={() => setPriceConfirmation(null)}
              aria-label={language === "en" ? "Close" : "Fermer"}
            >
              ×
            </button>
            <h3 className="modal-title">{language === "en" ? "Price change detected" : "Changement tarifaire detecte"}</h3>
            <p>
              {language === "en"
                ? `${priceConfirmation.booking.label} will be moved to ${priceConfirmation.targetLabel}. Which price should apply?`
                : `${priceConfirmation.booking.label} sera deplace vers ${priceConfirmation.targetLabel}. Quel tarif souhaitez-vous appliquer ?`}
            </p>
            <div className="reorg-price-comparison">
              <div>
                <span>{language === "en" ? "Current course price" : "Tarif du cours actuel"}</span>
                <strong>{formatPriceRange(priceConfirmation.preview.source_price_min, priceConfirmation.preview.source_price_max, priceConfirmation.preview.currency, language)}</strong>
              </div>
              <div>
                <span>{language === "en" ? "New course price" : "Tarif du nouveau cours"}</span>
                <strong>{formatPriceRange(priceConfirmation.preview.target_price_min, priceConfirmation.preview.target_price_max, priceConfirmation.preview.currency, language)}</strong>
              </div>
            </div>
            {scope === "series_future" ? (
              <p className="reorg-price-scope-note">
                {language === "en"
                  ? `This choice will apply to ${priceConfirmation.preview.price_change_count} future booking(s) with a price difference.`
                  : `Ce choix sera applique aux ${priceConfirmation.preview.price_change_count} reservation(s) futures avec un ecart de tarif.`}
              </p>
            ) : null}
            <div className="row gap-sm reorg-price-actions">
              <button
                type="button"
                className="button secondary"
                disabled={isPending}
                onClick={() => startTransition(() => submitMove(priceConfirmation.booking, priceConfirmation.targetSessionId, "keep_source"))}
              >
                {language === "en" ? "Keep current price" : "Conserver le tarif actuel"}
              </button>
              <button
                type="button"
                className="button primary"
                disabled={isPending}
                onClick={() => startTransition(() => submitMove(priceConfirmation.booking, priceConfirmation.targetSessionId, "apply_target"))}
              >
                {language === "en" ? "Apply new price" : "Appliquer le nouveau tarif"}
              </button>
            </div>
          </article>
        </section>
      ) : null}
    </section>
  );
}
