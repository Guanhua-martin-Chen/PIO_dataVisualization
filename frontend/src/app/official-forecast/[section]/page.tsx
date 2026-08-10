import { notFound, redirect } from "next/navigation";

import OfficialForecastSection, {
  type OfficialSection,
} from "../../../features/official-forecast/OfficialForecastSection";
import { officialHref, queryValue } from "../../../features/official-forecast/officialQuery";

const sections: OfficialSection[] = [
  "brands",
  "revenue",
  "quantity",
  "wholesale",
  "plc",
  "governance",
  "top-movers",
  "output",
];

export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ section: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { section } = await params;
  const rawQuery = await searchParams;
  const query = {
    month: queryValue(rawQuery.month),
    brand: queryValue(rawQuery.brand),
    level: queryValue(rawQuery.level),
  };
  if (section === "brand-breakdown") redirect(officialHref("/official-forecast/revenue", query));
  if (!sections.includes(section as OfficialSection)) notFound();
  return <OfficialForecastSection section={section as OfficialSection} initialQuery={query} />;
}
