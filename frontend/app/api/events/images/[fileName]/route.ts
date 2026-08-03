import { backendUrl } from "../../../../../lib/backend";

export async function GET(_: Request, context: { params: { fileName: string } }): Promise<Response> {
  const fileName = context.params.fileName?.trim();
  if (!fileName) return new Response("Not found", { status: 404 });

  const response = await fetch(`${backendUrl()}/api/v1/events/images/${encodeURIComponent(fileName)}`, {
    method: "GET",
    cache: "force-cache",
  });
  if (!response.ok) return new Response("Not found", { status: 404 });

  const headers = new Headers();
  const contentType = response.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const contentLength = response.headers.get("content-length");
  if (contentLength) headers.set("Content-Length", contentLength);
  headers.set("Cache-Control", "public, max-age=3600");
  return new Response(response.body, { status: 200, headers });
}
