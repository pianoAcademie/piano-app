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
    "studio_pack_plan_code",
    "collective_pack_plan_code",
    "online_pack_plan_code",
    "solfege_pack_plan_code",
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

type HistoricalInvoiceImportResult = {
  dry_run: boolean;
  rows_seen: number;
  rows_valid: number;
  clients_matched: number;
  invoices_created: number;
  invoices_updated: number;
  invoices_unchanged: number;
  errors: string[];
};

export async function importSportigoHistoricalInvoicesAction(formData: FormData): Promise<void> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) redirect("/login?error_code=session_expired");
  const archive = formData.get("archive");
  if (!(archive instanceof File) || archive.size <= 0) {
    redirect("/admin/sportigo-import?invoice_error=Sélectionnez+une+archive+ZIP.");
  }
  const payload = new FormData();
  payload.set("archive", archive, archive.name);
  payload.set("batch_reference", String(formData.get("batch_reference") ?? "").trim());
  payload.set("confirm_apply", String(formData.get("confirm_apply") ?? "").trim());
  payload.set("dry_run", checked(formData, "dry_run") ? "true" : "false");
  const result = await backendRequest<HistoricalInvoiceImportResult>(
    "/api/v1/admin/sportigo-import/historical-invoices",
    { method: "POST", body: payload },
    token,
    300000,
  );
  if (!result.ok) redirect(`/admin/sportigo-import?invoice_error=${encodeURIComponent(result.message)}`);
  const data = result.data;
  const params = new URLSearchParams();
  params.set("invoice_mode", data.dry_run ? "Prévisualisation" : "Import appliqué");
  params.set("invoice_rows", String(data.rows_valid));
  params.set("invoice_clients", String(data.clients_matched));
  params.set("invoice_created", String(data.invoices_created));
  params.set("invoice_updated", String(data.invoices_updated));
  params.set("invoice_unchanged", String(data.invoices_unchanged));
  if (data.errors.length) params.set("invoice_error", data.errors.slice(0, 4).join(" | "));
  else params.set("invoice_ok", "1");
  redirect(`/admin/sportigo-import?${params.toString()}`);
}
