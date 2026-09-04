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
  course_type_id: string;
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

type MoveScope = "single" | "series_future";

type DraggedBooking = {
  bookingId: string;
  sourceSessionId: string;
  label: string;
};

type PlanningReorganizationBoardProps = {
  initialBookingId?: string;
  sessions: PlanningReorganizationSession[];
  returnTo: string;
  initialScope?: MoveScope;
  language?: "fr" | "en";
};

type PendingPriceConfirmation = {
  booking: DraggedBooking;
  targetSessionId: string;
  targetLabel: string;
  preview: PlanningReorganizationMovePreview;
  scope: MoveScope;
};

type PendingSeriesConfirmation = {
  booking: DraggedBooking;
  targetSessionId: string;
  targetLabel: string;
  preview: PlanningReorganizationMovePreview;
  scope: MoveScope;
};

function returnPathWithScope(returnTo: string, scope: MoveScope): string {
  const [path, rawQuery = ""] = returnTo.split("?", 2);
  const query = new URLSearchParams(rawQuery);
  query.set("scope", scope);
  return `${path}?${query.toString()}`;
}

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
  initialScope = "series_future",
  language = "fr",
  initialBookingId,
}: PlanningReorganizationBoardProps): JSX.Element {
  const [dragged, setDragged] = useState<DraggedBooking | null>(null);
  const [selected, setSelected] = useState<DraggedBooking | null>(() => {
    const source = sessions.find(s => s.bookings.some(b => b.id === initialBookingId));
    const booking = source?.bookings.find(b => b.id === initialBookingId);
    return source && booking ? { bookingId: booking.id, sourceSessionId: source.id, label: booking.client_display_name } : null;
  });
  const [dragOverSessionId, setDragOverSessionId] = useState<string | null>(null);
  const [scope, setScope] = useState<MoveScope>(initialScope);
  const [priceConfirmation, setPriceConfirmation] = useState<PendingPriceConfirmation | null>(null);
  const [seriesConfirmation, setSeriesConfirmation] = useState<PendingSeriesConfirmation | null>(null);
  const [interactionError, setInteractionError] = useState("");
  const [isPending, startTransition] = useTransition();

  function isCompatibleTarget(sourceSessionId: string, target: PlanningReorganizationSession): boolean {
    const source = sessions.find((session) => session.id === sourceSessionId);
    if (!source) return false;
    return (
      source.course_type_id === target.course_type_id
      && source.location_id === target.location_id
      && new Date(source.end_at_utc).getTime() - new Date(source.start_at_utc).getTime()
        === new Date(target.end_at_utc).getTime() - new Date(target.start_at_utc).getTime()
      && target.booked_count < target.capacity_max
    );
  }

  function submitMove(
    bookingToMove: DraggedBooking,
    targetSessionId: string,
    pricePolicy: "keep_source" | "apply_target",
    requestedScope: MoveScope,
    version: string,
  ): void {
    const formData = new FormData();
    formData.set("booking_id", bookingToMove.bookingId);
    formData.set("target_session_id", targetSessionId);
    formData.set("scope", requestedScope);
    formData.set("price_policy", pricePolicy);
    formData.set("expected_version", version);
    formData.set("return_to", returnPathWithScope(returnTo, requestedScope));
    setSelected(null);
    setPriceConfirmation(null);
    setSeriesConfirmation(null);
    void movePlanningReorganizationBookingAction(formData);
  }

  function moveToSession(targetSessionId: string): void {
    const bookingToMove = dragged ?? selected;
    if (!bookingToMove || bookingToMove.sourceSessionId === targetSessionId || isPending) {
      return;
    }
    const requestedScope = scope;
    setInteractionError("");
    startTransition(async () => {
      const previewResult = await previewPlanningReorganizationBookingMoveAction({
        bookingId: bookingToMove.bookingId,
        targetSessionId,
        scope: requestedScope,
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
          scope: requestedScope,
        });
        return;
      }
      if (previewResult.data.affected_bookings > 0) {
        const targetSession = sessions.find((session) => session.id === targetSessionId);
        setSeriesConfirmation({
          booking: bookingToMove,
          targetSessionId,
          targetLabel: targetSession ? sessionTimeLabel(targetSession) : "",
          preview: previewResult.data,
          scope: requestedScope,
        });
        return;
      }
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
          <select value={scope} onChange={(event) => setScope(event.target.value as MoveScope)}>
            <option value="series_future">
              {language === "en" ? "All remaining sessions" : "Toute la serie a partir de cette date"}
            </option>
            <option value="single">{language === "en" ? "This session only" : "Cette seance uniquement"}</option>
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
          const activeBooking = dragged ?? selected;
          const isCompatible = activeBooking !== null && isCompatibleTarget(activeBooking.sourceSessionId, session);
          const isDropTarget = dragged !== null && dragged.sourceSessionId !== session.id && isCompatible;
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
              {selected && selected.sourceSessionId !== session.id && isCompatible ? (
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
                : `${priceConfirmation.booking.label} sera déplacé vers ${priceConfirmation.targetLabel}. Le prix du créneau est différent ; le tarif contractuel actuel est conservé. Un changement de prix nécessite un avenant.`}
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
            {priceConfirmation.scope === "series_future" ? (
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
                onClick={() =>
                  startTransition(() =>
                    submitMove(
                      priceConfirmation.booking,
                      priceConfirmation.targetSessionId,
                      "keep_source",
                      priceConfirmation.scope,
                      priceConfirmation.preview.version,
                    ),
                  )
                }
              >
                {language === "en" ? "Keep current price" : "Conserver le tarif actuel"}
              </button>
            </div>
          </article>
        </section>
      ) : null}
      {seriesConfirmation ? (
        <section
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label={language === "en" ? "Confirm series move" : "Confirmer le deplacement de la serie"}
        >
          <article className="modal-panel modal-compact reorg-price-modal">
            <button
              className="modal-close-x"
              type="button"
              onClick={() => setSeriesConfirmation(null)}
              aria-label={language === "en" ? "Close" : "Fermer"}
            >
              ×
            </button>
            <h3 className="modal-title">
              {seriesConfirmation.scope === "single" ? "Confirmer le déplacement de cette séance" : "Confirmer le déplacement des séances futures"}
            </h3>
            <p>
              {language === "en"
                ? `${seriesConfirmation.booking.label} will be moved to ${seriesConfirmation.targetLabel} for ${seriesConfirmation.preview.affected_bookings} session(s). Prices will not change.`
                : `${seriesConfirmation.booking.label} sera deplace vers ${seriesConfirmation.targetLabel} pour ${seriesConfirmation.preview.affected_bookings} seance(s). Les tarifs ne seront pas modifies.`}
            </p>
            <p>Tarif et remises conservés. Écart financier : 0 €. Aucune nouvelle facture.</p>
            <details><summary>Vérifier les dates et montants ({seriesConfirmation.preview.affected_bookings} séances)</summary>
              <ul>{seriesConfirmation.preview.occurrences.map((o, index) => <li key={index}>
                {new Date(o.source_at).toLocaleString("fr-FR", { timeZone: "Europe/Paris" })} → {new Date(o.target_at).toLocaleString("fr-FR", { timeZone: "Europe/Paris" })} · {o.price} €
              </li>)}</ul>
            </details>
            <div className="row gap-sm reorg-price-actions">
              <button
                type="button"
                className="button secondary"
                disabled={isPending}
                onClick={() => setSeriesConfirmation(null)}
              >
                {language === "en" ? "Cancel" : "Annuler"}
              </button>
              <button
                type="button"
                className="button primary"
                disabled={isPending}
                onClick={() =>
                  startTransition(() =>
                    submitMove(
                      seriesConfirmation.booking,
                      seriesConfirmation.targetSessionId,
                      "keep_source",
                      seriesConfirmation.scope,
                      seriesConfirmation.preview.version,
                    ),
                  )
                }
              >
                {isPending ? "Enregistrement…" : seriesConfirmation.scope === "single" ? "Déplacer cette séance" : "Déplacer toutes ces séances"}
              </button>
            </div>
          </article>
        </section>
      ) : null}
    </section>
  );
}
