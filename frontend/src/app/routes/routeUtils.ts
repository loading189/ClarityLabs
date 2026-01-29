import { buildSearchParams, type FilterState } from "../filters/filters";

export function ledgerPath(businessId: string, filters: FilterState) {
  const params = buildSearchParams(filters);
  const query = params.toString();
  return `/app/${businessId}/ledger${query ? `?${query}` : ""}`;
}
