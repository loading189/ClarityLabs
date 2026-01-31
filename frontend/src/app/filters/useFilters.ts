import { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { buildSearchParams, parseFilters, resolveDateRange, type FilterState } from "./filters";

export function useFilters(): [
  FilterState,
  (updates: Partial<FilterState> | ((current: FilterState) => FilterState)) => void,
] {
  const [params, setParams] = useSearchParams();

  const filters = useMemo(() => parseFilters(params), [params]);

  useEffect(() => {
    if (filters.start && filters.end) return;
    const resolved = resolveDateRange(filters);
    setParams(
      buildSearchParams({
        ...filters,
        start: resolved.start,
        end: resolved.end,
        window: resolved.window,
      }),
      { replace: true }
    );
  }, [filters, setParams]);

  const updateFilters = (
    updates: Partial<FilterState> | ((current: FilterState) => FilterState)
  ) => {
    setParams((prev) => {
      const current = parseFilters(prev);
      const next =
        typeof updates === "function" ? (updates as (c: FilterState) => FilterState)(current) : {
          ...current,
          ...updates,
        };
      return buildSearchParams(next);
    });
  };

  return [filters, updateFilters];
}
