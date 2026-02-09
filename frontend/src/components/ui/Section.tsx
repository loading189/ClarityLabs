import SectionHeader from "./SectionHeader";
import styles from "./Section.module.css";

export default function Section({
  title,
  subtitle,
  actions,
  children,
  className,
}: {
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`${styles.section} ${className ?? ""}`}>
      {title ? <SectionHeader title={title} subtitle={subtitle} actions={actions} /> : null}
      <div className={styles.body}>{children}</div>
    </section>
  );
}
