"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest } from "../../../lib/backend";

type SportigoImportResult = {
  dry_run: boolean;
  activate: boolean;
  rows_seen: number;
  imported_clients_total: number;
  imported_monthly_total: number;
  imported_credit_clients_total: number;
  clients_created: number;
  clients_reused_by_sportigo_id: number;
  clients_reused_by_email: number;
  studio_credits_total: number;
  collective_credits_total: number;
  online_credits_total: number;
  solfege_credits_total: number;
  errors: string[];
  warnings: string[];
};

function checked(formData: FormData, name: string): boolean {
  const value = String(formData.get(name) ?? "").toLowerCase();
  return value === "1" || value === "true" || value === "on";
}

export async function importSportigoAction(formData: FormData): Promise<void> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const file = formData.get("file");
  if (!(file instanceof File) || file.size <= 0) {
    redirect("/admin/sportigo-import?error=Sélectionnez+le+fichier+CSV+préparé.");
  }
  const payload = new FormData();
  payload.set("file", file, file.name);
  for (const name of [
    "batch_reference",
    "template_plan_code",
    "studio_credit_type_code",
    "collective_credit_type_code",
    "online_credit_type_code",
    "solfege_credit_type_code",
    "confirm_apply",
  ]) {
    payload.set(name, String(formData.get(name) ?? "").trim());
  }
  payload.set("dry_run", checked(formData, "dry_run") ? "true" : "false");
  payload.set("activate", checked(formData, "activate") ? "true" : "false");

  const result = await backendRequest<SportigoImportResult>(
    "/api/v1/admin/sportigo-import",
    { method: "POST", body: payload },
    token,
    180000,
  );
  if (!result.ok) {
    redirect(`/admin/sportigo-import?error=${encodeURIComponent(result.message)}`);
  }
  const data = result.data;
  const params = new URLSearchParams();
  params.set("mode", data.dry_run ? "Prévisualisation" : data.activate ? "Import activé" : "Import préparé");
  params.set("clients", String(data.imported_clients_total));
  params.set("monthly", String(data.imported_monthly_total));
  params.set("credit_clients", String(data.imported_credit_clients_total));
  params.set("created", String(data.clients_created));
  params.set("reused", String(data.clients_reused_by_sportigo_id + data.clients_reused_by_email));
  params.set("credits", `${data.studio_credits_total}/${data.collective_credits_total}/${data.online_credits_total}/${data.solfege_credits_total}`);
  if (data.errors.length) {
    params.set("error", data.errors.slice(0, 4).join(" | "));
  } else {
    params.set("ok", "1");
  }
  redirect(`/admin/sportigo-import?${params.toString()}`);
}
