import { useMemo } from "react";
import {
  getDateRangeForWindow,
  resolveDateRange,
  type DateWindow,
  type FilterState,
} from "../../app/filters/filters";
import styles from "./FilterBar.module.css";

type Option = { label: string; value: string };

export default function FilterBar({
  filters,
  onChange,
  accounts = [],
  categories = [],
  showDirection = false,
}: {
  filters: FilterState;
  onChange: (updates: Partial<FilterState>) => void;
  accounts?: Option[];
  categories?: Option[];
  showDirection?: boolean;
}) {
  const range = resolveDateRange(filters);

  const directionOptions = useMemo(
    () => [
      { label: "All directions", value: "" },
      { label: "Inflow", value: "inflow" },
      { label: "Outflow", value: "outflow" },
    ],
    []
  );

  const presetButtons: Array<{ label: string; value: DateWindow }> = [
    { label: "7d", value: "7" },
    { label: "30d", value: "30" },
    { label: "90d", value: "90" },
  ];

  return (
    <div className={styles.bar}>
      <div className={styles.group}>
        <div className={styles.label}>Date window</div>
        <div className={styles.pills}>
          {presetButtons.map((preset) => (
            <button
              key={preset.value}
              type="button"
              onClick={() => {
                const presetRange = getDateRangeForWindow(preset.value);
                onChange({ window: preset.value, ...presetRange });
              }}
              className={`${styles.pill} ${
                range.window === preset.value ? styles.pillActive : ""
              }`}
            >
              {preset.label}
            </button>
          ))}
        </div>
        <div className={styles.dateInputs}>
          <input
            type="date"
            value={range.start}
            onChange={(event) => onChange({ start: event.target.value, window: undefined })}
          />
          <span className={styles.toLabel}>to</span>
          <input
            type="date"
            value={range.end}
            onChange={(event) => onChange({ end: event.target.value, window: undefined })}
          />
        </div>
      </div>

      <div className={styles.group}>
        <div className={styles.label}>Account</div>
        <select
          value={filters.account ?? ""}
          onChange={(event) => onChange({ account: event.target.value || undefined })}
        >
          <option value="">All accounts</option>
          {accounts.map((account) => (
            <option key={account.value} value={account.value}>
              {account.label}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.group}>
        <div className={styles.label}>Category</div>
        <select
          value={filters.category ?? ""}
          onChange={(event) => onChange({ category: event.target.value || undefined })}
        >
          <option value="">All categories</option>
          {categories.map((category) => (
            <option key={category.value} value={category.value}>
              {category.label}
            </option>
          ))}
        </select>
      </div>

      {showDirection && (
        <div className={styles.group}>
          <div className={styles.label}>Direction</div>
          <select
            value={filters.direction ?? ""}
            onChange={(event) =>
              onChange({
                direction: (event.target.value as FilterState["direction"]) || undefined,
              })
            }
          >
            {directionOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className={styles.group}>
        <div className={styles.label}>Search</div>
        <input
          type="search"
          value={filters.q ?? ""}
          placeholder="Search description, vendor, memo…"
          onChange={(event) => onChange({ q: event.target.value || undefined })}
        />
      </div>
    </div>
  );
}
