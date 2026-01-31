import styles from "./DataState.module.css";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return <div className={styles.state}>{label}</div>;
}

export function EmptyState({ label = "No data available." }: { label?: string }) {
  return <div className={styles.state}>{label}</div>;
}

export function ErrorState({
  label = "Something went wrong.",
  action,
}: {
  label?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className={styles.state}>
      <div>{label}</div>
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}
