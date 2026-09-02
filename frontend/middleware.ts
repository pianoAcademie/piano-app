import { NextRequest, NextResponse } from "next/server";

const ADMIN_ACCESS_TOKEN_COOKIE = "admin_access_token";
const LEGACY_ACCESS_TOKEN_COOKIE = "access_token";
const PORTAL_ACCESS_TOKEN_COOKIE = "portal_access_token";
const AUTH_REFRESH_TOKEN_COOKIE = "auth_refresh_token";
const REFRESH_THRESHOLD_SECONDS = 5 * 60;

type RefreshResponse = {
  access_token: string;
  refresh_token: string;
  access_token_expires_in_seconds: number;
  refresh_token_expires_in_seconds: number;
  role: "admin" | "prof" | "client";
};

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

function portalScope(pathname: string): "admin" | "prof" | "client" | null {
  if (pathname === "/admin" || pathname.startsWith("/admin/")) return "admin";
  if (pathname === "/prof" || pathname.startsWith("/prof/")) return "prof";
  if (
    pathname === "/client"
    || pathname.startsWith("/client/")
    || pathname === "/dashboard"
    || pathname.startsWith("/dashboard/")
  ) return "client";
  return null;
}

function tokenRemainingSeconds(token: string | undefined): number | null {
  if (!token) return null;
  const segments = token.split(".");
  if (segments.length < 2) return null;
  try {
    const base64 = segments[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
    const payload = JSON.parse(atob(padded)) as { exp?: unknown };
    if (typeof payload.exp !== "number" || !Number.isFinite(payload.exp)) return null;
    return payload.exp - Math.floor(Date.now() / 1000);
  } catch {
    return null;
  }
}

function cookieHeader(request: NextRequest, updates: Map<string, string | null>): string {
  const values = new Map(request.cookies.getAll().map((cookie) => [cookie.name, cookie.value]));
  for (const [name, value] of updates.entries()) {
    if (value === null) values.delete(name);
    else values.set(name, value);
  }
  return Array.from(values.entries()).map(([name, value]) => `${name}=${value}`).join("; ");
}

function secureCookies(): boolean {
  const override = (process.env.COOKIE_SECURE ?? "").trim().toLowerCase();
  if (override === "true" || override === "1") return true;
  if (override === "false" || override === "0") return false;
  const nodeEnv = (process.env.NODE_ENV ?? "").trim().toLowerCase();
  const deployEnv = (process.env.DEPLOY_ENV ?? "").trim().toLowerCase();
  return nodeEnv === "production" || deployEnv === "production";
}

function setRefreshedCookies(
  response: NextResponse,
  data: RefreshResponse,
  scope: "admin" | "prof" | "client",
): void {
  const common = { httpOnly: true, secure: secureCookies(), path: "/" } as const;
  const accessCookie = scope === "admin" ? ADMIN_ACCESS_TOKEN_COOKIE : PORTAL_ACCESS_TOKEN_COOKIE;
  response.cookies.set(accessCookie, data.access_token, {
    ...common,
    sameSite: scope === "admin" ? "lax" : "none",
    maxAge: data.access_token_expires_in_seconds,
  });
  response.cookies.set(AUTH_REFRESH_TOKEN_COOKIE, data.refresh_token, {
    ...common,
    sameSite: "none",
    maxAge: data.refresh_token_expires_in_seconds,
  });
}

function clearInvalidSessionCookies(response: NextResponse): void {
  const common = { httpOnly: true, secure: secureCookies(), path: "/", maxAge: 0 } as const;
  response.cookies.set(PORTAL_ACCESS_TOKEN_COOKIE, "", { ...common, sameSite: "none" });
  response.cookies.set(ADMIN_ACCESS_TOKEN_COOKIE, "", { ...common, sameSite: "lax" });
  response.cookies.set(AUTH_REFRESH_TOKEN_COOKIE, "", { ...common, sameSite: "none" });
}

export async function middleware(request: NextRequest): Promise<NextResponse> {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = buildCsp(request, nonce);
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const scope = portalScope(request.nextUrl.pathname);
  const accessCookieName = scope === "admin" ? ADMIN_ACCESS_TOKEN_COOKIE : PORTAL_ACCESS_TOKEN_COOKIE;
  const accessToken = scope
    ? request.cookies.get(accessCookieName)?.value ?? request.cookies.get(LEGACY_ACCESS_TOKEN_COOKIE)?.value
    : undefined;
  const refreshToken = scope ? request.cookies.get(AUTH_REFRESH_TOKEN_COOKIE)?.value : undefined;
  const remainingSeconds = tokenRemainingSeconds(accessToken);

  if (scope && refreshToken && (remainingSeconds === null || remainingSeconds <= REFRESH_THRESHOLD_SECONDS)) {
    try {
      const refreshResponse = await fetch(`${process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000"}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
        cache: "no-store",
        signal: AbortSignal.timeout(5_000),
      });
      if (refreshResponse.ok) {
        const refreshed = await refreshResponse.json() as RefreshResponse;
        const refreshedAccessCookie = scope === "admin" ? ADMIN_ACCESS_TOKEN_COOKIE : PORTAL_ACCESS_TOKEN_COOKIE;
        requestHeaders.set("cookie", cookieHeader(request, new Map([
          [refreshedAccessCookie, refreshed.access_token],
          [AUTH_REFRESH_TOKEN_COOKIE, refreshed.refresh_token],
        ])));
        const refreshedResponse = NextResponse.next({ request: { headers: requestHeaders } });
        refreshedResponse.headers.set("Content-Security-Policy", csp);
        setRefreshedCookies(refreshedResponse, refreshed, scope);
        return refreshedResponse;
      }
      if (refreshResponse.status === 401 || refreshResponse.status === 403) {
        requestHeaders.set("cookie", cookieHeader(request, new Map([
          [accessCookieName, null],
          [AUTH_REFRESH_TOKEN_COOKIE, null],
        ])));
        const invalidResponse = NextResponse.next({ request: { headers: requestHeaders } });
        invalidResponse.headers.set("Content-Security-Policy", csp);
        clearInvalidSessionCookies(invalidResponse);
        return invalidResponse;
      }
      if (remainingSeconds === null || remainingSeconds <= 0) {
        const unavailableUrl = request.nextUrl.clone();
        unavailableUrl.pathname = "/session-unavailable";
        unavailableUrl.search = `?return_to=${encodeURIComponent(`${request.nextUrl.pathname}${request.nextUrl.search}`)}`;
        const unavailableResponse = NextResponse.rewrite(unavailableUrl, { request: { headers: requestHeaders } });
        unavailableResponse.headers.set("Content-Security-Policy", csp);
        return unavailableResponse;
      }
    } catch {
      if (remainingSeconds === null || remainingSeconds <= 0) {
        const unavailableUrl = request.nextUrl.clone();
        unavailableUrl.pathname = "/session-unavailable";
        unavailableUrl.search = `?return_to=${encodeURIComponent(`${request.nextUrl.pathname}${request.nextUrl.search}`)}`;
        const unavailableResponse = NextResponse.rewrite(unavailableUrl, { request: { headers: requestHeaders } });
        unavailableResponse.headers.set("Content-Security-Policy", csp);
        return unavailableResponse;
      }
    }
  }

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
