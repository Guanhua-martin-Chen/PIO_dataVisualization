import ExecutiveOverview from "../features/official-forecast/ExecutiveOverview";
import { queryValue } from "../features/official-forecast/officialQuery";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = await searchParams;
  return <ExecutiveOverview query={{
    month: queryValue(query.month),
    brand: queryValue(query.brand),
    level: queryValue(query.level),
  }} />;
}
