import "server-only";
import { cookies } from "next/headers";

export const LEGACY_ACCESS_TOKEN_COOKIE = "access_token";
export const ADMIN_ACCESS_TOKEN_COOKIE = "admin_access_token";
export const ADMIN_IMPERSONATION_RETURN_TOKEN_COOKIE = "admin_impersonation_return_token";
export const PORTAL_ACCESS_TOKEN_COOKIE = "portal_access_token";
export const PORTAL_RETURN_TO_COOKIE = "portal_return_to";

const EIGHT_HOURS_IN_SECONDS = 60 * 60 * 8;
const TOKEN_EXPIRY_SKEW_SECONDS = 30;

function parsePositiveInteger(raw: string | undefined): number | null {
  if (!raw) {
    return null;
  }
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

function adminCookieMaxAgeSeconds(): number {
  const configuredMinutes = parsePositiveInteger(process.env.ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES);
  if (configuredMinutes !== null) {
    return configuredMinutes * 60;
  }
  return EIGHT_HOURS_IN_SECONDS;
}

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

function cookieSameSite(name: string): "lax" | "none" {
  if (!isSecureCookie()) {
    return "lax";
  }
  if (
    name === PORTAL_ACCESS_TOKEN_COOKIE
    || name === LEGACY_ACCESS_TOKEN_COOKIE
    || name === PORTAL_RETURN_TO_COOKIE
    || name === ADMIN_IMPERSONATION_RETURN_TOKEN_COOKIE
  ) {
    return "none";
  }
  return "lax";
}

function setCookieValue(name: string, value: string, options: { path: string; maxAge: number }): void {
  const { path, maxAge } = options;
  cookies().set(name, value, {
    httpOnly: true,
    sameSite: cookieSameSite(name),
    secure: isSecureCookie(),
    path,
    maxAge,
  });
}

function clearCookieValue(name: string, options: { path: string }): void {
  const { path } = options;
  cookies().set(name, "", {
    httpOnly: true,
    sameSite: cookieSameSite(name),
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

function isExpiredJwt(token: string | null): boolean {
  const payload = decodeJwtPayloadUnsafe(token);
  if (!payload || typeof payload.exp !== "number" || !Number.isFinite(payload.exp)) {
    return false;
  }
  return payload.exp <= Math.floor(Date.now() / 1000) + TOKEN_EXPIRY_SKEW_SECONDS;
}

export function getAdminToken(): string | null {
  const adminToken = cookies().get(ADMIN_ACCESS_TOKEN_COOKIE)?.value ?? null;
  if (adminToken && !isExpiredJwt(adminToken)) {
    return adminToken;
  }

  const legacyToken = cookies().get(LEGACY_ACCESS_TOKEN_COOKIE)?.value ?? null;
  const legacyClaims = decodeJwtPayloadUnsafe(legacyToken);
  if (legacyToken && !isExpiredJwt(legacyToken) && legacyClaims?.role === "admin") {
    return legacyToken;
  }
  return null;
}

export function getPortalToken(): string | null {
  const portalToken = cookies().get(PORTAL_ACCESS_TOKEN_COOKIE)?.value ?? null;
  if (portalToken && !isExpiredJwt(portalToken)) {
    return portalToken;
  }

  const legacyToken = cookies().get(LEGACY_ACCESS_TOKEN_COOKIE)?.value ?? null;
  const legacyClaims = decodeJwtPayloadUnsafe(legacyToken);
  if (!legacyToken || !legacyClaims || isExpiredJwt(legacyToken)) {
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
    getAdminToken()
    ?? getPortalToken()
    ?? (() => {
      const legacyToken = cookies().get(LEGACY_ACCESS_TOKEN_COOKIE)?.value ?? null;
      return legacyToken && !isExpiredJwt(legacyToken) ? legacyToken : null;
    })()
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
  const maxAge = options.maxAge ?? adminCookieMaxAgeSeconds();
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

export function setAdminImpersonationReturnToken(token: string, maxAgeSeconds: number): void {
  setCookieValue(ADMIN_IMPERSONATION_RETURN_TOKEN_COOKIE, token, { path: "/", maxAge: maxAgeSeconds });
}

export function getAdminImpersonationReturnToken(): string | null {
  const token = cookies().get(ADMIN_IMPERSONATION_RETURN_TOKEN_COOKIE)?.value ?? null;
  return token && !isExpiredJwt(token) ? token : null;
}

export function clearAdminImpersonationReturnToken(): void {
  clearCookieValue(ADMIN_IMPERSONATION_RETURN_TOKEN_COOKIE, { path: "/" });
}

export function clearPortalToken(): void {
  clearCookieValue(PORTAL_ACCESS_TOKEN_COOKIE, { path: "/" });
}

export function clearLegacyToken(): void {
  clearCookieValue(LEGACY_ACCESS_TOKEN_COOKIE, { path: "/" });
}

export function clearAllAuthTokens(): void {
  clearAdminToken();
  clearAdminImpersonationReturnToken();
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

export function readAdminImpersonationClaims(): JwtPayloadLike | null {
  const token = cookies().get(ADMIN_ACCESS_TOKEN_COOKIE)?.value ?? null;
  return decodeJwtPayloadUnsafe(token);
}
