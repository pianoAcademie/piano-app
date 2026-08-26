import Link from "next/link";

import type { ProfessorLocalIntakeDetailOut } from "../lib/types";
import ModalA11yFrame from "./modal-a11y-frame";

type Props = {
  intake: ProfessorLocalIntakeDetailOut;
  closeHref: string;
};

function receivedAtLabel(value: string): string {
  return new Date(value).toLocaleString("fr-FR", {
    dateStyle: "long",
    timeStyle: "short",
    timeZone: "Europe/Paris",
  });
}

export default function ProfessorLocalIntakeRequestModal({ intake, closeHref }: Props): JSX.Element {
  const studentName = intake.child_label || intake.prospect_label;

  return (
    <section className="modal-overlay modal-overlay-front">
      <ModalA11yFrame
        className="modal-panel teacher-intake-request-modal"
        closeHref={closeHref}
        label={`Détails de la demande de ${studentName}`}
      >
        <header className="row spread">
          <div>
            <span className="eyebrow">Demande Typeform</span>
            <h2 className="modal-title">{studentName}</h2>
            <p className="muted">Reçue le {receivedAtLabel(intake.received_at)}</p>
          </div>
          <Link className="modal-close-x" href={closeHref} aria-label="Fermer">
            ×
          </Link>
        </header>

        <section className="teacher-intake-request-summary" aria-label="Résumé de la demande">
          <div>
            <span>Responsable</span>
            <strong>{intake.prospect_label}</strong>
          </div>
          <div>
            <span>Demande</span>
            <strong>{intake.requested_summary || "Nouvel intake Bar-le-Duc"}</strong>
          </div>
        </section>

        <section className="teacher-intake-request-answers" aria-labelledby="teacher-intake-request-answers-title">
          <h3 id="teacher-intake-request-answers-title">Informations communiquées</h3>
          {intake.answers.length > 0 ? (
            <dl>
              {intake.answers.map((answer, index) => (
                <div key={`${answer.label}-${index}`}>
                  <dt>{answer.label}</dt>
                  <dd>{answer.value}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="muted">Aucune réponse détaillée n’est disponible pour cette demande.</p>
          )}
        </section>

        <footer className="teacher-intake-request-actions">
          <Link className="mode-link" href={closeHref}>Fermer</Link>
          <Link className="teacher-intake-request-confirm" href={`/prof/intakes/${intake.id}`}>
            Choisir le créneau et la partition
          </Link>
        </footer>
      </ModalA11yFrame>
    </section>
  );
}
