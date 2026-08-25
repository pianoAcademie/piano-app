"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { getAdminToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import type { AdminTaskOut } from "../../../lib/types";

function value(formData: FormData, name: string): string {
  return String(formData.get(name) ?? "").trim();
}

function safeReturnTo(raw: string, fallback: string): string {
  return raw.startsWith("/admin/tasks") && !raw.startsWith("//") ? raw : fallback;
}

function contactPayload(reference: string): Record<string, string> {
  const [kind, id] = reference.split(":", 2);
  if (!id) return {};
  if (kind === "CLIENT") return { client_id: id };
  if (kind === "PROSPECT") return { prospect_id: id };
  return {};
}

export async function createAdminTaskAction(formData: FormData): Promise<void> {
  const token = getAdminToken();
  if (!token) redirect("/login?error_code=session_expired");
  const returnTo = safeReturnTo(value(formData, "return_to"), "/admin/tasks?create=1");
  const payload = {
    task_type: value(formData, "task_type"),
    description: value(formData, "description"),
    comment: value(formData, "comment") || null,
    assignee_user_id: value(formData, "assignee_user_id") || null,
    due_at: value(formData, "due_at") || null,
    intake_id: value(formData, "intake_id") || null,
    quote_id: value(formData, "quote_id") || null,
    ...contactPayload(value(formData, "contact_ref")),
  };
  const result = await backendRequest<AdminTaskOut>(
    "/api/v1/admin/tasks",
    { method: "POST", body: JSON.stringify(payload) },
    token,
  );
  if (!result.ok) {
    const separator = returnTo.includes("?") ? "&" : "?";
    redirect(`${returnTo}${separator}error=${encodeURIComponent(result.message)}`);
  }
  revalidatePath("/admin/tasks");
  redirect(`/admin/tasks/${result.data.id}?ok=${encodeURIComponent("Tâche créée et responsable notifié.")}`);
}

export async function updateAdminTaskAction(formData: FormData): Promise<void> {
  const token = getAdminToken();
  if (!token) redirect("/login?error_code=session_expired");
  const taskId = value(formData, "task_id");
  const returnTo = safeReturnTo(value(formData, "return_to"), `/admin/tasks/${taskId}`);
  const assigneeId = value(formData, "assignee_user_id");
  const dueAt = value(formData, "due_at");
  const payload = {
    task_type: value(formData, "task_type"),
    status: value(formData, "status"),
    description: value(formData, "description"),
    comment: value(formData, "comment") || null,
    assignee_user_id: assigneeId || null,
    clear_assignee: !assigneeId,
    due_at: dueAt || null,
    clear_due_at: !dueAt,
  };
  const result = await backendRequest<AdminTaskOut>(
    `/api/v1/admin/tasks/${encodeURIComponent(taskId)}`,
    { method: "PATCH", body: JSON.stringify(payload) },
    token,
  );
  if (!result.ok) {
    const separator = returnTo.includes("?") ? "&" : "?";
    redirect(`${returnTo}${separator}error=${encodeURIComponent(result.message)}`);
  }
  revalidatePath("/admin/tasks");
  revalidatePath(`/admin/tasks/${taskId}`);
  redirect(`${returnTo}?ok=${encodeURIComponent("Tâche mise à jour.")}`);
}
