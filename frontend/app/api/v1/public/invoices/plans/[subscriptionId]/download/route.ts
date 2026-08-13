import { backendUrl } from "../../../../../../../../lib/backend";

type RouteParams = {
  params: {
    subscriptionId: string;
  };
};

export async function GET(request: Request, { params }: RouteParams): Promise<Response> {
  const subscriptionId = params.subscriptionId.trim();
  const token = new URL(request.url).searchParams.get("token")?.trim() ?? "";
  if (!subscriptionId || !token) {
    return new Response("Invoice not found", { status: 404 });
  }

  const response = await fetch(
    `${backendUrl()}/api/v1/public/invoices/plans/${encodeURIComponent(subscriptionId)}/download?${new URLSearchParams({ token }).toString()}`,
    {
      method: "GET",
      cache: "no-store",
    },
  );

  if (!response.ok) {
    return new Response("Invoice not found", { status: response.status });
  }

  const buffer = await response.arrayBuffer();
  const contentDisposition = response.headers.get("content-disposition") ?? 'attachment; filename="facture.pdf"';
  const contentType = response.headers.get("content-type") ?? "application/pdf";

  return new Response(buffer, {
    status: 200,
    headers: {
      "content-type": contentType,
      "content-disposition": contentDisposition,
      "cache-control": "no-store",
    },
  });
}
