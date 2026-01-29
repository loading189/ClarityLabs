import styles from "./Drawer.module.css";

export default function Drawer({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  if (!open) return null;
  return (
    <div className={styles.overlay} role="dialog" aria-modal="true">
      <div className={styles.drawer}>
        <div className={styles.header}>
          <div>
            <div className={styles.title}>{title}</div>
          </div>
          <button className={styles.closeButton} onClick={onClose} type="button">
            Close
          </button>
        </div>
        <div className={styles.body}>{children}</div>
      </div>
    </div>
  );
}
