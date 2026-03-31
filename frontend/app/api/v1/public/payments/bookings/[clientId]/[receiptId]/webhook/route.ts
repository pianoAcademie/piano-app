import { proxyPost } from "../../../../_proxy";

export async function POST(request: Request): Promise<Response> {
  return proxyPost(request);
}
