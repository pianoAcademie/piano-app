"use server";

import { revalidatePath } from "next/cache";
import { getAdminToken, getProfessorPortalToken } from "./auth-cookies";
import { backendRequest } from "./backend";

export async function partitionDistributionAction(form: FormData): Promise<{ ok: boolean; message: string }> {
  const admin = form.get("portal") === "admin";
  const token = admin ? getAdminToken() : getProfessorPortalToken();
  if (!token) return { ok: false, message: "Reconnectez-vous pour continuer." };
  const action = String(form.get("action"));
  let path = "/api/v1/partition-distribution";
  let body: Record<string, unknown>;
  let method = "POST";
  if (action === "cancel") {
    path += `/movements/${encodeURIComponent(String(form.get("movement_id")))}/cancel`;
    body = {};
  } else if (action === "confirm") {
    path += `/movements/${encodeURIComponent(String(form.get("movement_id")))}/confirm`;
    body = { quantity: Number(form.get("quantity")) };
  } else if (action === "deliver") {
    path += "/deliver";
    body = { assignment_id: form.get("assignment_id"), product_id: form.get("product_id"), professor_id: form.get("professor_id") };
  } else if (action === "define" || action === "change") {
    path = admin ? `/api/v1/admin/clients/${encodeURIComponent(String(form.get("student_id")))}/repertoire`
      : `/api/v1/professors/me/students/${encodeURIComponent(String(form.get("student_id")))}/repertoire`;
    body = { product_id: form.get("product_id"), status: "TO_DELIVER" };
    if (action === "change") {
      path += `/${encodeURIComponent(String(form.get("assignment_id")))}`;
      method = "PATCH";
    }
  } else if (action === "movement") {
    path += "/movements";
    body = { operation_id: form.get("operation_id"), professor_id: form.get("professor_id"),
      product_id: form.get("product_id"), quantity: Number(form.get("quantity")), kind: form.get("kind") };
  } else return { ok: false, message: "Action invalide." };
  const result = await backendRequest(path, { method, body: JSON.stringify(body) }, token);
  if (!result.ok) return { ok: false, message: result.message };
  revalidatePath("/prof/partitions");
  revalidatePath("/admin/partition-distribution");
  revalidatePath("/prof");
  revalidatePath("/admin/products");
  return { ok: true, message: action === "cancel" ? "Demande annulée." : action === "confirm" ? "Mouvement validé : le stock est à jour."
    : action === "deliver" ? "Partition remise à l’élève. Votre stock et son suivi sont à jour."
    : action === "define" || action === "change" ? "Partition enregistrée pour cet élève." : "Demande enregistrée. Elle attend la validation à Richelieu." };
}
