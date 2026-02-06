import { useEffect, useMemo } from "react";
import { useParams } from "react-router-dom";
import PageHeader from "../../components/common/PageHeader";
import FilterBar from "../../components/common/FilterBar";
import { assertBusinessId } from "../../utils/businessId";
import { CategorizeTab } from "../../features/categorize";
import { useAppState } from "../state/appState";
import { useFilters } from "../filters/useFilters";
import { resolveDateRange } from "../filters/filters";
import styles from "./CategorizePage.module.css";

export default function CategorizePage() {
  const { businessId: businessIdParam } = useParams();
  const businessId = assertBusinessId(businessIdParam, "CategorizePage");
  const [filters, setFilters] = useFilters();
  const { dateRange, setDateRange } = useAppState();
  const resolvedRange = useMemo(() => resolveDateRange(filters), [filters]);

  useEffect(() => {
    setDateRange({ start: resolvedRange.start, end: resolvedRange.end });
  }, [resolvedRange.end, resolvedRange.start, setDateRange]);

  if (!businessId) {
    return (
      <div className={styles.page}>
        <PageHeader
          title="Categorize"
          subtitle="Review the queue, handle bulk changes, and keep the ledger clean."
        />
        <div className={styles.error}>Invalid business id in URL.</div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <PageHeader
        title="Categorize"
        subtitle="Review the queue, handle bulk changes, and keep the ledger clean."
        actions={
          <div className={styles.summary}>
            <span>
              {dateRange.start} → {dateRange.end}
            </span>
          </div>
        }
      />
      <FilterBar
        filters={filters}
        onChange={setFilters}
        showAccountFilter={false}
        showCategoryFilter={false}
        showSearch={false}
      />
      <CategorizeTab businessId={businessId} />
    </div>
  );
}
