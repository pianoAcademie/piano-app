import { redirect } from "next/navigation";
import { getProfessorPortalToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import PartitionDistribution, { DistributionData } from "../../../components/partition-distribution";

export default async function Page({ searchParams }: { searchParams: { week?: string } }) {
  const token = getProfessorPortalToken();
  if (!token) redirect("/login?portal=prof");
  const response = await backendRequest<DistributionData>(`/api/v1/partition-distribution${searchParams.week ? `?week=${encodeURIComponent(searchParams.week)}` : ""}`, {}, token);
  if (!response.ok) return <main className="page"><h1>Mes partitions</h1><p role="alert">{response.message}</p></main>;
  return <PartitionDistribution data={response.data} />;
}
