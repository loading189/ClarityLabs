import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import SignalsTab from "../../features/signals/SignalsTab";
import PageHeader from "../../components/common/PageHeader";
import FilterBar from "../../components/common/FilterBar";
import { ErrorState, LoadingState } from "../../components/common/DataState";
import { useBusinessDetailData } from "../../hooks/useBusinessDetailData";
import { useFilters } from "../filters/useFilters";
import { getDateRangeForWindow, type FilterState } from "../filters/filters";
import { useDemoDateRange } from "../filters/useDemoDateRange";
import { ledgerPath } from "./routeUtils";
import { assertBusinessId } from "../../utils/businessId";

function getString(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  return typeof value === "string" ? value : undefined;
}

function mapDrilldownToFilters(
  current: FilterState,
  payload?: Record<string, unknown> | null
) {
  if (!payload) return current;
  const next: FilterState = { ...current };
  const categoryId = getString(payload, "category_id");
  const category = getString(payload, "category");
  if (categoryId || category) {
    next.category = categoryId ?? category;
  }
  const direction = getString(payload, "direction");
  if (direction === "inflow" || direction === "outflow") {
    next.direction = direction;
  }
  const search = getString(payload, "search");
  const query = getString(payload, "q");
  if (search || query) {
    next.q = search ?? query;
  }
  const windowDaysValue = payload.window_days;
  if (typeof windowDaysValue === "number") {
    const days = Number(windowDaysValue);
    const window = days <= 7 ? "7" : days <= 30 ? "30" : "90";
    Object.assign(next, { window, ...getDateRangeForWindow(window) });
  }
  return next;
}

export default function HealthPage() {
  const { businessId: businessIdParam } = useParams();
  const businessId = assertBusinessId(businessIdParam, "HealthPage");
  const navigate = useNavigate();
  const [filters, setFilters] = useFilters();
  const { data, loading, err } = useBusinessDetailData(businessId);
  useDemoDateRange(filters, setFilters, { start_at: data?.start_at, end_at: data?.end_at });

  const showContent = useMemo(() => !loading && !err && data, [data, err, loading]);

  return (
    <div>
      <PageHeader
        title="Health"
        subtitle="Diagnosis of financial signals with evidence and recommended actions."
      />

      <FilterBar filters={filters} onChange={setFilters} />

      {loading && <LoadingState label="Loading health signals…" />}
      {err && <ErrorState label={`Failed to load health: ${err}`} />}

      {showContent && data && (
        <SignalsTab
          detail={data}
          onNavigate={(target, drilldown) => {
            if (target === "categorize") {
              navigate(`/app/${businessId}/categorize`);
              return;
            }
            if (target === "trends") {
              navigate(`/app/${businessId}/trends`);
              return;
            }
            if (target === "ledger" || target === "transactions") {
              const nextFilters = mapDrilldownToFilters(
                filters,
                drilldown as Record<string, unknown> | null
              );
              navigate(ledgerPath(businessId, nextFilters));
            }
          }}
        />
      )}
    </div>
  );
}
