import { proxyGet, proxyPost } from "../../_proxy";

export async function GET(request: Request): Promise<Response> {
  const response = await proxyGet(request);
  response.headers.set("referrer-policy", "no-referrer");
  return response;
}

export async function POST(request: Request): Promise<Response> {
  const response = await proxyPost(request);
  response.headers.set("referrer-policy", "no-referrer");
  return response;
}
