import styles from "./KeyValueList.module.css";

export type KeyValueItem = {
  label: string;
  value: React.ReactNode;
};

export default function KeyValueList({ items, columns = 2 }: { items: KeyValueItem[]; columns?: 1 | 2 }) {
  return (
    <div className={`${styles.list} ${columns === 1 ? styles.single : ""}`}>
      {items.map((item) => (
        <div key={item.label} className={styles.item}>
          <div className={styles.label}>{item.label}</div>
          <div className={styles.value}>{item.value}</div>
        </div>
      ))}
    </div>
  );
}
