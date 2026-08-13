import { NextRequest, NextResponse } from "next/server";

const PUBLIC_EMBED_PATHS = [
  "/embed",
  "/events",
  "/login",
  "/buy/session/checkout",
];

function canBeEmbedded(pathname: string): boolean {
  return PUBLIC_EMBED_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

function buildCsp(request: NextRequest, nonce: string): string {
  const frameAncestors = canBeEmbedded(request.nextUrl.pathname)
    ? "'self' https://piano-academie.com https://www.piano-academie.com"
    : "'self'";
  const developmentEval = process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : "";
  return [
    "default-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    `frame-ancestors ${frameAncestors}`,
    "img-src 'self' data: blob: https:",
    "font-src 'self' data: https:",
    "style-src 'self' 'unsafe-inline' https:",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${developmentEval} https://static.zdassets.com`,
    "connect-src 'self' https://*.zendesk.com https://*.zdassets.com https://*.zopim.com https://*.zopim.io wss://*.zendesk.com wss://*.zopim.com",
    "frame-src 'self' blob: https://*.zendesk.com https://*.zopim.com",
    "worker-src 'self' blob:",
    "form-action 'self' https://secure.payplug.com https://checkout.stripe.com https://*.mollie.com",
    "upgrade-insecure-requests",
  ].join("; ");
}

export function middleware(request: NextRequest): NextResponse {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = buildCsp(request, nonce);
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!api|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
