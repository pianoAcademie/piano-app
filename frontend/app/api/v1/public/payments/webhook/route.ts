import { proxyGet, proxyPost } from "../_proxy";

export async function GET(request: Request): Promise<Response> {
  return proxyGet(request);
}

export async function POST(request: Request): Promise<Response> {
  return proxyPost(request);
}
