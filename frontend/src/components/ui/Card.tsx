import styles from "./Card.module.css";

export default function Card({
  children,
  className,
  muted = false,
}: {
  children: React.ReactNode;
  className?: string;
  muted?: boolean;
}) {
  return <div className={`${styles.card} ${muted ? styles.muted : ""} ${className ?? ""}`}>{children}</div>;
}
