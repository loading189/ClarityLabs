import styles from "./EmptyState.module.css";

export default function EmptyState({
  title,
  description,
  action,
  icon = "◎",
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: string;
}) {
  return (
    <div className={styles.emptyState} role="status">
      <div className={styles.icon}>{icon}</div>
      <div>
        <div className={styles.title}>{title}</div>
        {description ? <div className={styles.description}>{description}</div> : null}
      </div>
      {action ? <div className={styles.action}>{action}</div> : null}
    </div>
  );
}
