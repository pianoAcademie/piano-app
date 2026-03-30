import { proxyGet } from "../../../../_proxy";

export async function GET(request: Request): Promise<Response> {
  return proxyGet(request);
}
