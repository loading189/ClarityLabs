import { useParams } from "react-router-dom";
import PageHeader from "../../components/common/PageHeader";
import { assertBusinessId } from "../../utils/businessId";
import RulesTab from "../../features/rules/RulesTab";
import { useAppState } from "../state/appState";
import styles from "./RulesPage.module.css";

export default function RulesPage() {
  const { businessId: businessIdParam } = useParams();
  const businessId = assertBusinessId(businessIdParam, "RulesPage");
  const { dateRange } = useAppState();

  if (!businessId) {
    return (
      <div className={styles.page}>
        <PageHeader
          title="Rules"
          subtitle="Automation rules that keep categorization consistent."
        />
        <div className={styles.error}>Invalid business id in URL.</div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <PageHeader
      title="Rules"
      subtitle="Automation rules that keep categorization consistent."
        actions={
          <div className={styles.summary}>
            <span>
              {dateRange.start} → {dateRange.end}
            </span>
          </div>
        }
      />
      <RulesTab businessId={businessId} />
    </div>
  );
}
