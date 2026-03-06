import "server-only";

import { getTokenForPathname } from "./auth-cookies";

const DEFAULT_BACKEND_URL = "http://localhost:8000";
const DEFAULT_TIMEOUT_MS = 30000;

export function backendUrl(): string {
  return process.env.BACKEND_INTERNAL_URL ?? DEFAULT_BACKEND_URL;
}

function backendTimeoutMs(): number {
  const raw = process.env.BACKEND_TIMEOUT_MS;
  const parsed = Number(raw);
  if (Number.isFinite(parsed) && parsed > 0) {
    return parsed;
  }
  return DEFAULT_TIMEOUT_MS;
}

export type BackendResult<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number; message: string };

function normalizePath(path: string): string {
  if (path.startsWith("/")) {
    return path;
  }
  return `/${path}`;
}

function extractErrorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    const detail = record.detail;
    if (typeof detail === "string") {
      return detail;
    }
  }
  return fallback;
}

export async function backendRequest<T>(
  path: string,
  init: RequestInit = {},
  token?: string,
): Promise<BackendResult<T>> {
  const headers = new Headers(init.headers ?? {});

  const isFormDataBody =
    typeof FormData !== "undefined" &&
    init.body !== null &&
    init.body !== undefined &&
    init.body instanceof FormData;

  if (!headers.has("Content-Type") && init.body && !isFormDataBody) {
    headers.set("Content-Type", "application/json");
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const timeoutController = new AbortController();
  const timeout = setTimeout(() => timeoutController.abort(), backendTimeoutMs());
  const signal = init.signal ? AbortSignal.any([init.signal, timeoutController.signal]) : timeoutController.signal;

  let response: Response;
  try {
    response = await fetch(`${backendUrl()}${normalizePath(path)}`, {
      ...init,
      headers,
      cache: "no-store",
      signal,
    });
  } catch (error) {
    clearTimeout(timeout);

    if (error instanceof Error && error.name === "AbortError") {
      return {
        ok: false,
        status: 504,
        message: "Backend request timeout",
      };
    }

    return {
      ok: false,
      status: 503,
      message: "Backend unreachable",
    };
  }

  clearTimeout(timeout);

  const text = await response.text();
  const payload = text ? safeJsonParse(text) : null;

  if (!response.ok) {
    return {
      ok: false,
      status: response.status,
      message: extractErrorMessage(payload, `Backend error ${response.status}`),
    };
  }

  return {
    ok: true,
    status: response.status,
    data: (payload as T) ?? ({} as T),
  };
}

export async function backendRequestForPath<T>(
  pathname: string,
  path: string,
  init: RequestInit = {},
): Promise<BackendResult<T>> {
  const token = getTokenForPathname(pathname) ?? undefined;
  return backendRequest<T>(path, init, token);
}

function safeJsonParse(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}
