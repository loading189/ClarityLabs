import { useParams } from "react-router-dom";
import PageHeader from "../../components/common/PageHeader";
import { assertBusinessId } from "../../utils/businessId";
import { CategorizeTab } from "../../features/categorize";
import { useAppState } from "../state/appState";
import styles from "./CategorizePage.module.css";

export default function CategorizePage() {
  const { businessId: businessIdParam } = useParams();
  const businessId = assertBusinessId(businessIdParam, "CategorizePage");
  const { dateRange } = useAppState();

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
      <CategorizeTab businessId={businessId} />
    </div>
  );
}
