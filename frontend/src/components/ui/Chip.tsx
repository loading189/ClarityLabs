import styles from "./Chip.module.css";

type ChipTone = "default" | "info";

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
