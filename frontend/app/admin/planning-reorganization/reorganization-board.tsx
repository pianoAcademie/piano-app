"use client";

import { useState, useTransition } from "react";

import { movePlanningReorganizationBookingAction } from "../../../lib/actions";

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

export function PlanningReorganizationBoard({
  sessions,
  returnTo,
}: PlanningReorganizationBoardProps): JSX.Element {
  const [dragged, setDragged] = useState<DraggedBooking | null>(null);
  const [dragOverSessionId, setDragOverSessionId] = useState<string | null>(null);
  const [scope, setScope] = useState<"single" | "series_future">("single");
  const [isPending, startTransition] = useTransition();

  function moveToSession(targetSessionId: string): void {
    if (!dragged || dragged.sourceSessionId === targetSessionId || isPending) {
      return;
    }
    const formData = new FormData();
    formData.set("booking_id", dragged.bookingId);
    formData.set("target_session_id", targetSessionId);
    formData.set("scope", scope);
    formData.set("return_to", returnTo);
    startTransition(() => {
      void movePlanningReorganizationBookingAction(formData);
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
          <h2>Atelier de placement</h2>
          <p>Glissez un eleve vers un autre creneau du meme jour. Le changement reste controle par les capacites.</p>
        </div>
        <label className="reorg-scope">
          Portee
          <select value={scope} onChange={(event) => setScope(event.target.value as "single" | "series_future")}>
            <option value="single">Cette seance uniquement</option>
            <option value="series_future">Suite de la serie</option>
          </select>
        </label>
      </div>
      {isPending ? <p className="form-feedback success">Deplacement en cours...</p> : null}
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
                      className="reorg-student-card"
                      draggable
                      key={booking.id}
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
    </section>
  );
}
