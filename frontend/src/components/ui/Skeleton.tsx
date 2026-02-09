import styles from "./Skeleton.module.css";

export default function Skeleton({ width }: { width?: string }) {
  return <div className={styles.skeleton} style={width ? { width } : undefined} />;
}
