import styles from "./InlineAlert.module.css";

type InlineAlertTone = "info" | "error";

export default function InlineAlert({
  title,
  description,
  action,
  tone = "info",
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  tone?: InlineAlertTone;
}) {
  return (
    <div className={`${styles.alert} ${styles[tone]}`} role="alert">
      <div className={styles.title}>{title}</div>
      {description ? <div className={styles.description}>{description}</div> : null}
      {action ? <div className={styles.action}>{action}</div> : null}
    </div>
  );
}
