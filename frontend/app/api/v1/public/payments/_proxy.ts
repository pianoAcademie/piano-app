import { backendUrl } from "../../../../../lib/backend";

function passthroughHeaders(request: Request, includeContentType: boolean): HeadersInit {
  const headers: Record<string, string> = {};
  const contentType = request.headers.get("content-type");
  if (includeContentType && contentType) {
    headers["content-type"] = contentType;
  }
  const userAgent = request.headers.get("user-agent");
  if (userAgent) {
    headers["user-agent"] = userAgent;
  }
  return headers;
}

export function upstreamUrl(pathname: string, search: string): string {
  return `${backendUrl()}${pathname}${search}`;
}

export async function passthroughTextResponse(upstream: Response): Promise<Response> {
  const responseText = await upstream.text();
  const headers = new Headers();
  const contentType = upstream.headers.get("content-type");
  if (contentType) {
    headers.set("content-type", contentType);
  }
  headers.set("cache-control", "no-store");
  const location = upstream.headers.get("location");
  if (location) {
    headers.set("location", location);
  }
  return new Response(responseText, {
    status: upstream.status,
    headers,
  });
}

export async function proxyGet(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const upstream = await fetch(upstreamUrl(url.pathname, url.search), {
    method: "GET",
    headers: passthroughHeaders(request, false),
    cache: "no-store",
    redirect: "manual",
  });
  return passthroughTextResponse(upstream);
}

export async function proxyPost(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const rawBody = await request.text();
  const upstream = await fetch(upstreamUrl(url.pathname, url.search), {
    method: "POST",
    headers: passthroughHeaders(request, true),
    body: rawBody,
    cache: "no-store",
    redirect: "manual",
  });
  return passthroughTextResponse(upstream);
}
