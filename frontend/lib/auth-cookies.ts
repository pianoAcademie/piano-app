import "server-only";
import { cookies } from "next/headers";

export const LEGACY_ACCESS_TOKEN_COOKIE = "access_token";
export const ADMIN_ACCESS_TOKEN_COOKIE = "admin_access_token";
export const PORTAL_ACCESS_TOKEN_COOKIE = "portal_access_token";
export const PORTAL_RETURN_TO_COOKIE = "portal_return_to";

const EIGHT_HOURS_IN_SECONDS = 60 * 60 * 8;

function isSecureCookie(): boolean {
  const cookieSecureOverride = (process.env.COOKIE_SECURE ?? "").trim().toLowerCase();
  if (cookieSecureOverride === "true" || cookieSecureOverride === "1") {
    return true;
  }
  if (cookieSecureOverride === "false" || cookieSecureOverride === "0") {
    return false;
  }
  const nodeEnv = (process.env.NODE_ENV ?? "").trim().toLowerCase();
  const deployEnv = (process.env.DEPLOY_ENV ?? "").trim().toLowerCase();
  return nodeEnv === "production" || deployEnv === "production";
}

function setCookieValue(name: string, value: string, options: { path: string; maxAge: number }): void {
  const { path, maxAge } = options;
  cookies().set(name, value, {
    httpOnly: true,
    sameSite: "lax",
    secure: isSecureCookie(),
    path,
    maxAge,
  });
}

function clearCookieValue(name: string, options: { path: string }): void {
  const { path } = options;
  cookies().set(name, "", {
    httpOnly: true,
    sameSite: "lax",
    secure: isSecureCookie(),
    path,
    maxAge: 0,
  });
}

type JwtPayloadLike = {
  role?: string;
  imp?: boolean;
  act?: string;
  target_role?: string;
  exp?: number;
  [key: string]: unknown;
};

function decodeJwtPayloadUnsafe(token: string | null): JwtPayloadLike | null {
  if (!token) {
    return null;
  }
  const segments = token.split(".");
  if (segments.length < 2) {
    return null;
  }
  try {
    const payloadRaw = Buffer.from(segments[1], "base64url").toString("utf-8");
    return JSON.parse(payloadRaw) as JwtPayloadLike;
  } catch {
    return null;
  }
}

export function getAdminToken(): string | null {
  const adminToken = cookies().get(ADMIN_ACCESS_TOKEN_COOKIE)?.value ?? null;
  if (adminToken) {
    return adminToken;
  }

  const legacyToken = cookies().get(LEGACY_ACCESS_TOKEN_COOKIE)?.value ?? null;
  const legacyClaims = decodeJwtPayloadUnsafe(legacyToken);
  if (legacyToken && legacyClaims?.role === "admin") {
    return legacyToken;
  }
  return null;
}

export function getPortalToken(): string | null {
  const portalToken = cookies().get(PORTAL_ACCESS_TOKEN_COOKIE)?.value ?? null;
  if (portalToken) {
    return portalToken;
  }

  const legacyToken = cookies().get(LEGACY_ACCESS_TOKEN_COOKIE)?.value ?? null;
  const legacyClaims = decodeJwtPayloadUnsafe(legacyToken);
  if (!legacyToken || !legacyClaims) {
    return null;
  }
  // Never treat a legacy admin token as a portal session.
  if (legacyClaims.role === "admin") {
    return null;
  }
  return legacyToken;
}

export function getAnyToken(): string | null {
  return (
    cookies().get(ADMIN_ACCESS_TOKEN_COOKIE)?.value
    ?? cookies().get(PORTAL_ACCESS_TOKEN_COOKIE)?.value
    ?? cookies().get(LEGACY_ACCESS_TOKEN_COOKIE)?.value
    ?? null
  );
}

export function getTokenForPathname(pathname: string): string | null {
  const normalized = pathname.trim().toLowerCase();
  if (normalized.startsWith("/admin")) {
    return getAdminToken();
  }
  if (normalized.startsWith("/client") || normalized.startsWith("/teacher") || normalized.startsWith("/prof") || normalized.startsWith("/q")) {
    return getPortalToken();
  }
  return getAnyToken();
}

export function setAdminToken(token: string, options: { maxAge?: number } = {}): void {
  const maxAge = options.maxAge ?? EIGHT_HOURS_IN_SECONDS;
  setCookieValue(ADMIN_ACCESS_TOKEN_COOKIE, token, { path: "/", maxAge });
}

export function setPortalToken(token: string, options: { maxAge?: number } = {}): void {
  const maxAge = options.maxAge ?? EIGHT_HOURS_IN_SECONDS;
  setCookieValue(PORTAL_ACCESS_TOKEN_COOKIE, token, { path: "/", maxAge });
}

export function setLegacyToken(token: string, options: { maxAge?: number } = {}): void {
  const maxAge = options.maxAge ?? EIGHT_HOURS_IN_SECONDS;
  setCookieValue(LEGACY_ACCESS_TOKEN_COOKIE, token, { path: "/", maxAge });
}

export function clearAdminToken(): void {
  clearCookieValue(ADMIN_ACCESS_TOKEN_COOKIE, { path: "/admin" });
  clearCookieValue(ADMIN_ACCESS_TOKEN_COOKIE, { path: "/" });
}

export function clearPortalToken(): void {
  clearCookieValue(PORTAL_ACCESS_TOKEN_COOKIE, { path: "/" });
}

export function clearLegacyToken(): void {
  clearCookieValue(LEGACY_ACCESS_TOKEN_COOKIE, { path: "/" });
}

export function clearAllAuthTokens(): void {
  clearAdminToken();
  clearPortalToken();
  clearLegacyToken();
}

export function setPortalReturnTo(returnTo: string): void {
  setCookieValue(PORTAL_RETURN_TO_COOKIE, returnTo, { path: "/", maxAge: EIGHT_HOURS_IN_SECONDS });
}

export function getPortalReturnTo(): string | null {
  return cookies().get(PORTAL_RETURN_TO_COOKIE)?.value ?? null;
}

export function clearPortalReturnTo(): void {
  clearCookieValue(PORTAL_RETURN_TO_COOKIE, { path: "/" });
}

export function readPortalImpersonationClaims(): JwtPayloadLike | null {
  const token = cookies().get(PORTAL_ACCESS_TOKEN_COOKIE)?.value ?? null;
  return decodeJwtPayloadUnsafe(token);
}
