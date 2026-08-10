export type OfficialQuery = {
  month?: string;
  brand?: string;
  level?: string;
};

export function queryValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export function monthQueryValue(month: string) {
  return /^\d{4}-\d{2}/.test(month) ? month.slice(0, 7) : "";
}

export function resolveMonthQuery(
  requested: string | undefined,
  months: string[],
  fallback: string,
) {
  if (!requested) return fallback;
  return months.find((month) => month === requested || monthQueryValue(month) === requested) ?? fallback;
}

export function resolveChoiceQuery<T extends string>(
  requested: string | undefined,
  choices: readonly T[],
  fallback: T,
) {
  return choices.includes(requested as T) ? requested as T : fallback;
}

export function officialHref(href: string, query: OfficialQuery = {}) {
  const params = new URLSearchParams();
  if (query.month) params.set("month", monthQueryValue(query.month) || query.month);
  if (query.brand) params.set("brand", query.brand);
  if (query.level) params.set("level", query.level);
  const suffix = params.toString();
  return suffix ? `${href}?${suffix}` : href;
}
