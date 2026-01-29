import { useEffect } from "react";
import { clampFiltersToRange, type DemoDateRange, type FilterState } from "./filters";

export function useDemoDateRange(
  filters: FilterState,
  setFilters: (updates: Partial<FilterState> | ((current: FilterState) => FilterState)) => void,
  range?: DemoDateRange | null
) {
  useEffect(() => {
    if (!range) return;
    const next = clampFiltersToRange(filters, range);
    if (!next) return;
    setFilters(next);
  }, [filters, range?.end_at, range?.start_at, setFilters]);
}
