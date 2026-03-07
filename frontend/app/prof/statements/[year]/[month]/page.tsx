import { redirect } from "next/navigation";

type SearchParams = Record<string, string | string[] | undefined>;

function appendQuery(searchParams: SearchParams, year: string, month: string): string {
  const query = new URLSearchParams();
  query.set("year", year);
  query.set("month", month);
  for (const [key, value] of Object.entries(searchParams)) {
    if (key === "year" || key === "month") {
      continue;
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        if (item) {
          query.append(key, item);
        }
      }
    } else if (value) {
      query.set(key, value);
    }
  }
  return query.toString();
}

export default function TeacherStatementMonthLegacyPage({
  params,
  searchParams,
}: {
  params: { year: string; month: string };
  searchParams: SearchParams;
}): never {
  const query = appendQuery(searchParams, params.year, params.month);
  redirect(`/prof/statements?${query}`);
}
