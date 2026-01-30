import PageHeader from "../../components/common/PageHeader";
import styles from "./StubPage.module.css";

export default function StubPage({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children?: React.ReactNode;
}) {
  return (
    <div className={styles.page}>
      <PageHeader title={title} subtitle={subtitle} />
      <div className={styles.card}>
        {children ?? "This module is staged for a future sprint."}
      </div>
    </div>
  );
}
