"use server";

import { getPortalToken } from "./auth-cookies";
import { backendRequest } from "./backend";
import type { LearningCommand, LearningSnapshot } from "./learning-progress";

export async function learningAction(studentId: string, sessionId: string, command?: LearningCommand): Promise<
  { ok: true; data: LearningSnapshot } | { ok: false; message: string }
> {
  const token = getPortalToken();
  if (!token) return { ok: false, message: "Votre session a expiré. Reconnectez-vous." };
  if (![studentId, sessionId].every((id) => /^[0-9a-f-]{36}$/i.test(id))) {
    return { ok: false, message: "Élève ou cours invalide." };
  }
  const result = await backendRequest<LearningSnapshot>(
    `/api/v1/professors/me/students/${studentId}/learning${command ? "" : `?session_id=${sessionId}`}`,
    command ? { method: "PATCH", body: JSON.stringify({ ...command, session_id: sessionId }) } : {}, token,
  );
  return result.ok ? { ok: true, data: result.data } : { ok: false, message: result.message };
}
