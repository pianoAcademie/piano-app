import "server-only";

import { NextRequest } from "next/server";

function readForwardedValue(value: string | null): string | null {
  const candidate = value?.split(",")[0]?.trim() ?? "";
  return candidate || null;
}

function inferProtocol(host: string): string {
  const normalizedHost = host.toLowerCase();
  if (
    normalizedHost.startsWith("localhost") ||
    normalizedHost.startsWith("127.0.0.1") ||
    normalizedHost.startsWith("[::1]")
  ) {
    return "http";
  }
  return "https";
}

export function getPublicOrigin(request: NextRequest): string {
  const forwardedHost = readForwardedValue(request.headers.get("x-forwarded-host"));
  const host =
    forwardedHost ||
    readForwardedValue(request.headers.get("host")) ||
    request.nextUrl.host ||
    new URL(request.url).host;
  const proto = readForwardedValue(request.headers.get("x-forwarded-proto")) || inferProtocol(host);
  return `${proto}://${host}`;
}

export function buildPublicUrl(request: NextRequest, path: string): URL {
  return new URL(path, getPublicOrigin(request));
}
