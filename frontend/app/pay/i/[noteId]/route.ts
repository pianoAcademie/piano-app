import { NextRequest } from "next/server";

import { backendUrl } from "../../../../lib/backend";

type RouteParams = {
  params: {
    noteId: string;
  };
};

function upstreamPublicPayUrl(request: NextRequest, noteId: string): URL {
  const upstreamUrl = new URL(`${backendUrl()}/api/v1/admin/clients/invoices/range/${noteId}/public-pay`);
  const shortToken = request.nextUrl.searchParams.get("t");
  const legacyToken = request.nextUrl.searchParams.get("token");
  if (shortToken) {
    upstreamUrl.searchParams.set("t", shortToken);
  } else if (legacyToken) {
    upstreamUrl.searchParams.set("token", legacyToken);
  }
  return upstreamUrl;
}

function extractErrorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    if (typeof record.detail === "string" && record.detail.trim()) {
      return record.detail.trim();
    }
  }
  return fallback;
}

function paymentErrorHtml(message: string): string {
  return `<!doctype html>
<html lang="fr">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Paiement indisponible</title>
    <style>
      body { font-family: Arial, sans-serif; background: #f6f7f9; color: #111827; margin: 0; padding: 24px; }
      .card { max-width: 720px; margin: 0 auto; background: #fff; border: 1px solid #e6e8ee; border-radius: 14px; padding: 20px; }
      h1 { margin: 0 0 10px; font-size: 22px; }
      p { margin: 8px 0; line-height: 1.45; }
      .muted { color: #4b5563; }
    </style>
  </head>
  <body>
    <section class="card">
      <h1>Paiement indisponible</h1>
      <p>${message}</p>
      <p class="muted">Si besoin, contactez l'administration Piano Academie.</p>
    </section>
  </body>
</html>`;
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function paymentRedirectHtml(location: string): string {
  const safeLocation = escapeHtml(location);
  return `<!doctype html>
<html lang="fr">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Redirection vers Payplug</title>
    <meta http-equiv="refresh" content="0;url=${safeLocation}" />
    <style>
      body { font-family: Arial, sans-serif; background: #f6f7f9; color: #111827; margin: 0; padding: 24px; }
      .card { max-width: 720px; margin: 0 auto; background: #fff; border: 1px solid #e6e8ee; border-radius: 14px; padding: 20px; }
      h1 { margin: 0 0 10px; font-size: 22px; }
      p { margin: 8px 0; line-height: 1.45; }
      .button {
        display: inline-block;
        margin-top: 14px;
        padding: 12px 18px;
        border-radius: 10px;
        background: #d4a23b;
        color: #111827;
        font-weight: 700;
        text-decoration: none;
      }
      .muted { color: #4b5563; }
    </style>
  </head>
  <body>
    <section class="card">
      <h1>Redirection vers Payplug</h1>
      <p>Si rien ne s'ouvre automatiquement, utilisez le bouton ci-dessous.</p>
      <a class="button" href="${safeLocation}" rel="noopener noreferrer">Continuer vers le paiement</a>
      <p class="muted">Cette page peut apparaitre quand le lecteur PDF bloque les redirections directes.</p>
    </section>
    <script>
      (function () {
        var url = ${JSON.stringify(location)};
        try {
          if (window.top && window.top !== window) {
            window.top.location.href = url;
            return;
          }
        } catch (error) {
        }
        window.location.replace(url);
      })();
    </script>
  </body>
</html>`;
}

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const upstream = await fetch(upstreamPublicPayUrl(request, params.noteId).toString(), {
    method: "GET",
    cache: "no-store",
    redirect: "manual",
  });

  const redirectLocation = upstream.headers.get("location");
  if (redirectLocation && upstream.status >= 300 && upstream.status < 400) {
    return new Response(paymentRedirectHtml(redirectLocation), {
      status: 200,
      headers: {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "no-store",
      },
    });
  }

  const contentType = upstream.headers.get("content-type") ?? "application/json; charset=utf-8";
  const responseText = await upstream.text();
  if (upstream.ok) {
    return new Response(responseText, {
      status: upstream.status,
      headers: {
        "content-type": contentType,
        "cache-control": "no-store",
      },
    });
  }

  let payload: unknown = null;
  if (contentType.includes("application/json")) {
    try {
      payload = JSON.parse(responseText);
    } catch {
      payload = null;
    }
  }
  const message = extractErrorMessage(payload, `Erreur paiement (${upstream.status})`);
  return new Response(paymentErrorHtml(message), {
    status: upstream.status,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}
