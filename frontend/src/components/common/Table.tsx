import styles from "./Table.module.css";

export type TableColumn<T> = {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  align?: "left" | "right";
  width?: string;
};

export default function Table<T>({
  columns,
  rows,
  getRowId,
  onRowClick,
  emptyMessage = "No rows to display.",
  rowActions,
}: {
  columns: Array<TableColumn<T>>;
  rows: T[];
  getRowId: (row: T) => string;
  onRowClick?: (row: T) => void;
  emptyMessage?: string;
  rowActions?: (row: T) => React.ReactNode;
}) {
  return (
    <div className={styles.tableCard}>
      <table className={styles.table}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                className={`${styles.headCell} ${
                  column.align === "right" ? styles.alignRight : ""
                }`}
                style={column.width ? { width: column.width } : undefined}
              >
                {column.header}
              </th>
            ))}
            {rowActions && <th className={styles.headCell}>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={getRowId(row)}
              className={onRowClick ? styles.clickableRow : undefined}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={`${styles.cell} ${
                    column.align === "right" ? styles.alignRight : ""
                  }`}
                >
                  {column.render(row)}
                </td>
              ))}
              {rowActions && <td className={styles.cell}>{rowActions(row)}</td>}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={columns.length + (rowActions ? 1 : 0)} className={styles.empty}>
                {emptyMessage}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
