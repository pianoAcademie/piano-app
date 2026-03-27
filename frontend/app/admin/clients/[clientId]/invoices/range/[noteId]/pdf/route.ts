import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { backendUrl } from "../../../../../../../../lib/backend";

type RouteParams = {
  params: {
    clientId: string;
    noteId: string;
  };
};

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function extractPaymentUrlFromPdf(buffer: ArrayBuffer): string | null {
  const content = Buffer.from(buffer).toString("latin1");
  const match = content.match(/\/URI \((https?:\/\/[^)]+)\)/);
  return match?.[1] ?? null;
}

function invoicePreviewHtml(params: {
  iframeUrl: string;
  downloadUrl: string;
  paymentUrl: string | null;
}): string {
  const { iframeUrl, downloadUrl, paymentUrl } = params;
  const safeIframeUrl = escapeHtml(iframeUrl);
  const safeDownloadUrl = escapeHtml(downloadUrl);
  const safePaymentUrl = paymentUrl ? escapeHtml(paymentUrl) : null;
  const paymentButton = safePaymentUrl
    ? `<a class="pay-button" href="${safePaymentUrl}" target="_blank" rel="noopener noreferrer">Payer en ligne</a>`
    : `<span class="pay-button pay-button-disabled">Paiement indisponible</span>`;

  return `<!doctype html>
<html lang="fr">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Apercu facture</title>
    <style>
      :root {
        color-scheme: light;
      }
      body {
        margin: 0;
        font-family: Arial, sans-serif;
        background: #f4f5f7;
        color: #111827;
      }
      .shell {
        min-height: 100vh;
        display: grid;
        grid-template-rows: auto 1fr;
      }
      .toolbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        padding: 16px 20px;
        background: #fff;
        border-bottom: 1px solid #e5e7eb;
      }
      .toolbar p {
        margin: 0;
        color: #4b5563;
        font-size: 14px;
      }
      .actions {
        display: flex;
        align-items: center;
        gap: 12px;
      }
      .download-link,
      .pay-button {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 42px;
        padding: 0 18px;
        border-radius: 10px;
        text-decoration: none;
        font-weight: 700;
      }
      .download-link {
        border: 1px solid #d5dae2;
        background: #fff;
        color: #1f2937;
      }
      .pay-button {
        border: 1px solid #d2a12d;
        background: #d2a12d;
        color: #172033;
      }
      .pay-button-disabled {
        opacity: 0.6;
        cursor: not-allowed;
      }
      iframe {
        width: 100%;
        height: calc(100vh - 75px);
        border: 0;
        background: #fff;
      }
    </style>
  </head>
  <body>
    <main class="shell">
      <section class="toolbar">
        <p>Le bouton ci-dessus lance le paiement de facon fiable, meme si le lecteur PDF bloque les liens internes.</p>
        <div class="actions">
          <a class="download-link" href="${safeDownloadUrl}">Telecharger le PDF</a>
          ${paymentButton}
        </div>
      </section>
      <iframe src="${safeIframeUrl}" title="Apercu facture"></iframe>
    </main>
  </body>
</html>`;
}

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    const loginUrl = new URL("/login?error=Session%20expiree", request.url);
    return NextResponse.redirect(loginUrl, 302);
  }

  const { clientId, noteId } = params;
  const inline = request.nextUrl.searchParams.get("inline") === "true";
  const raw = request.nextUrl.searchParams.get("raw") === "1";
  const upstreamUrl = new URL(`${backendUrl()}/api/v1/admin/clients/${clientId}/invoices/range/${noteId}/pdf`);
  upstreamUrl.searchParams.set("inline", inline ? "true" : "false");

  const response = await fetch(upstreamUrl.toString(), {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const returnTab = request.nextUrl.searchParams.get("payment_return_tab") === "paiements" ? "paiements" : "factures";
    const fallback = new URL(
      `/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(`Facture indisponible (${response.status})`)}`,
      request.url,
    );
    return NextResponse.redirect(fallback, 302);
  }

  const buffer = await response.arrayBuffer();
  const contentDisposition = response.headers.get("content-disposition") ?? 'attachment; filename="facture-periode.pdf"';
  const contentType = response.headers.get("content-type") ?? "application/pdf";

  if (inline && !raw) {
    const iframeUrl = new URL(request.url);
    iframeUrl.searchParams.set("raw", "1");
    iframeUrl.searchParams.set("inline", "true");

    const downloadUrl = new URL(request.url);
    downloadUrl.searchParams.delete("raw");
    downloadUrl.searchParams.set("inline", "false");

    const paymentUrl = extractPaymentUrlFromPdf(buffer);
    return new Response(
      invoicePreviewHtml({
        iframeUrl: iframeUrl.toString(),
        downloadUrl: downloadUrl.toString(),
        paymentUrl,
      }),
      {
        status: 200,
        headers: {
          "content-type": "text/html; charset=utf-8",
          "cache-control": "no-store",
        },
      },
    );
  }

  return new Response(buffer, {
    status: 200,
    headers: {
      "content-type": contentType,
      "content-disposition": contentDisposition,
      "cache-control": "no-store",
    },
  });
}
