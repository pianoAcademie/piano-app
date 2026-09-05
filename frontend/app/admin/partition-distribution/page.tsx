import { redirect } from "next/navigation";
import { getAdminToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import PartitionDistribution, { DistributionData } from "../../../components/partition-distribution";

export default async function Page({ searchParams }: { searchParams: { week?: string } }) {
  const token = getAdminToken();
  if (!token) redirect("/login");
  const response = await backendRequest<DistributionData>(`/api/v1/partition-distribution${searchParams.week ? `?week=${encodeURIComponent(searchParams.week)}` : ""}`, {}, token);
  if (!response.ok) return <main className="page"><h1>Distribution des partitions</h1><p role="alert">{response.message}</p></main>;
  return <PartitionDistribution data={response.data} />;
}
