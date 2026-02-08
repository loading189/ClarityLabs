import Skeleton from "./Skeleton";
import styles from "./LoadingState.module.css";

export default function LoadingState({ label = "Loading…", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div className={styles.loading} role="status" aria-live="polite">
      <div className={styles.label}>{label}</div>
      <div className={styles.skeletons}>
        {Array.from({ length: rows }).map((_, index) => (
          <Skeleton key={index} />
        ))}
      </div>
    </div>
  );
}
