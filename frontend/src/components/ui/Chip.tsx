import styles from "./Chip.module.css";

type ChipTone = "default" | "info" | "success" | "warning" | "danger" | "neutral";

export default function Chip({
  children,
  tone = "default",
  className,
}: {
  children: React.ReactNode;
  tone?: ChipTone;
  className?: string;
}) {
  return <span className={`${styles.chip} ${styles[tone]} ${className ?? ""}`}>{children}</span>;
}
