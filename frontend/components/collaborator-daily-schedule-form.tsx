import { randomUUID } from "node:crypto";

import { sendAdminCollaboratorDailyScheduleAction } from "../lib/actions";
import { parisDateKey } from "../lib/collaborator-agenda";
import type { UiLanguage } from "../lib/ui-i18n";
import ConfirmSubmitButton from "./confirm-submit-button";

export default function CollaboratorDailyScheduleForm({
  professorId, email, active, returnTo, language,
}: {
  professorId: string;
  email: string;
  active: boolean;
  returnTo: string;
  language: UiLanguage;
}): JSX.Element {
  // The send date is always TODAY in Paris, not the selected agenda period.
  const today = parisDateKey(new Date());
  const requestId = randomUUID();
  const formId = `daily-schedule-${requestId}`;
  const en = language === "en";
  const dateLabel = en ? today : today.split("-").reverse().join("/");
  return (
    <form id={formId} action={sendAdminCollaboratorDailyScheduleAction} className="top-gap-sm" style={{ maxWidth: "100%", overflowWrap: "anywhere" }}>
      <input type="hidden" name="professor_id" value={professorId} />
      <input type="hidden" name="recipient" value={email} />
      <input type="hidden" name="digest_date" value={today} />
      <input type="hidden" name="request_id" value={requestId} />
      <input type="hidden" name="confirmed" value="true" />
      <input type="hidden" name="return_to" value={returnTo} />
      <ConfirmSubmitButton
        formId={formId}
        language={language}
        label={en ? "Resend today's schedule" : "Renvoyer le planning du jour"}
        title={en ? "Send today's schedule?" : "Envoyer le planning du jour ?"}
        description={en
          ? `Send the updated schedule for ${dateLabel} (Paris time) to ${email}?\nThis can resend an email already sent this morning. No email is sent if there are no classes today. Automatic sending settings remain unchanged.`
          : `Envoyer le planning actualisé du ${dateLabel} (heure de Paris) à ${email} ?\nL’email sera renvoyé même s’il a déjà été envoyé ce matin. Aucun envoi s’il n’y a pas de cours aujourd’hui. Les réglages d’envoi automatique restent inchangés.`}
        confirmLabel={en ? "Send email" : "Envoyer l’email"}
        pendingLabel={en ? "Sending…" : "Envoi en cours…"}
        disabled={!active}
        disabledReason={en ? "This collaborator is inactive." : "Ce collaborateur est inactif."}
      />
    </form>
  );
}
