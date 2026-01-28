// src/components/detail/TransactionsTab.tsx
import { useEffect, useMemo, useState } from "react";
import { useTransactions } from "../../hooks/useTransactions";
import styles from "./TransactionsTab.module.css";

export type TransactionsDrilldown = {
  merchant_key?: string;
  direction?: "inflow" | "outflow";
  category_id?: string;
  search?: string;
  date_preset?: "7d" | "30d" | "90d";
};

function fmtMoney(amount: number, direction?: string) {
  const signed =
    direction === "outflow" ? -Math.abs(amount)
    : direction === "inflow" ? Math.abs(amount)
    : amount; // fallback if direction missing

  const sign = signed < 0 ? "-" : "";
  return `${sign}$${Math.abs(signed).toFixed(2)}`;
}

type FilterDirection = "all" | "inflow" | "outflow";
type DatePreset = "7d" | "30d" | "90d";

type TransactionFilters = {
  search: string;
  direction: FilterDirection;
  categoryId: string;
  datePreset: DatePreset | null;
  merchantKey: string;
};

const DEFAULT_FILTERS: TransactionFilters = {
  search: "",
  direction: "all",
  categoryId: "all",
  datePreset: null,
  merchantKey: "",
};

const DATE_PRESET_DAYS: Record<DatePreset, number> = {
  "7d": 7,
  "30d": 30,
  "90d": 90,
};

function toMerchantKey(description: string) {
  const stopwords = new Set([
    "pos",
    "ach",
    "debit",
    "credit",
    "card",
    "purchase",
    "payment",
    "pmt",
    "online",
    "web",
    "www",
    "inc",
    "llc",
    "co",
    "company",
    "corp",
    "corporation",
    "the",
  ]);
  const normalized = (description || "")
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s*]/g, " ")
    .replace(/\d+/g, " ")
    .replace(/\*/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const tokens = normalized
    .split(" ")
    .filter((token) => token && !stopwords.has(token))
    .slice(0, 6);
  return tokens.join(" ");
}

export function TransactionsTab({
  businessId,
  drilldown,
  onClearDrilldown,
}: {
  businessId: string;
  drilldown?: TransactionsDrilldown | null;
  onClearDrilldown?: () => void;
}) {
  const { data, loading, err, refresh } = useTransactions(businessId, 50);
  const [filters, setFilters] = useState<TransactionFilters>(DEFAULT_FILTERS);

  const drilldownKey = useMemo(() => {
    if (!drilldown) return "";
    return [
      drilldown.merchant_key ?? "",
      drilldown.direction ?? "",
      drilldown.category_id ?? "",
      drilldown.search ?? "",
      drilldown.date_preset ?? "",
    ].join("|");
  }, [drilldown]);

  useEffect(() => {
    if (!drilldown) return;
    setFilters({
      search: drilldown.search ?? "",
      direction: drilldown.direction ?? "all",
      categoryId: drilldown.category_id ?? "all",
      datePreset: drilldown.date_preset ?? null,
      merchantKey: drilldown.merchant_key ?? "",
    });
  }, [drilldownKey, drilldown]);

  const txns = data?.transactions ?? [];

  const categories = useMemo(() => {
    const uniq = new Set<string>();
    txns.forEach((t) => {
      if (t.category) uniq.add(t.category);
    });
    return Array.from(uniq).sort((a, b) => a.localeCompare(b));
  }, [txns]);

  const filteredTxns = useMemo(() => {
    if (!txns.length) return [];
    const search = filters.search.trim().toLowerCase();
    const merchantKey = filters.merchantKey.trim().toLowerCase();
    const now = Date.now();
    const days = filters.datePreset ? DATE_PRESET_DAYS[filters.datePreset] : null;
    const cutoff = days ? now - days * 24 * 60 * 60 * 1000 : null;

    return txns.filter((t) => {
      if (filters.direction !== "all" && t.direction !== filters.direction) {
        return false;
      }
      if (filters.categoryId !== "all" && t.category !== filters.categoryId) {
        return false;
      }
      if (search) {
        const haystack = `${t.description ?? ""} ${t.counterparty_hint ?? ""}`.toLowerCase();
        if (!haystack.includes(search)) return false;
      }
      if (merchantKey) {
        const candidate = toMerchantKey(t.description ?? "");
        if (!candidate.includes(merchantKey)) return false;
      }
      if (cutoff) {
        const occurredAt = Date.parse(t.occurred_at);
        if (Number.isFinite(occurredAt) && occurredAt < cutoff) return false;
      }
      return true;
    });
  }, [filters, txns]);

  if (loading && !data) return <div style={{ padding: 12 }}>Loading transactions…</div>;
  if (err) return (
    <div style={{ padding: 12 }}>
      <div style={{ marginBottom: 8 }}>Error: {err}</div>
      <button onClick={refresh}>Retry</button>
    </div>
  );

  const hasFilters = Boolean(
    filters.search.trim() ||
      filters.direction !== "all" ||
      filters.categoryId !== "all" ||
      filters.datePreset ||
      filters.merchantKey.trim()
  );

  return (
    <div className={styles.container}>
      <div className={styles.headerRow}>
        <div className={styles.headerTitle}>Recent Transactions</div>
        <div className={styles.headerMeta}>
          <small>
            As of {data?.as_of ? new Date(data.as_of).toLocaleString() : "—"}
          </small>
          <button className={styles.secondaryButton} onClick={refresh}>Refresh</button>
        </div>
      </div>

      <div className={styles.filterBar}>
        <div className={styles.filterGroup}>
          <input
            className={styles.searchInput}
            placeholder="Search description or vendor…"
            value={filters.search}
            onChange={(e) =>
              setFilters((prev) => ({
                ...prev,
                search: e.target.value,
              }))
            }
          />
          <select
            className={styles.select}
            value={filters.direction}
            onChange={(e) =>
              setFilters((prev) => ({
                ...prev,
                direction: e.target.value as FilterDirection,
              }))
            }
          >
            <option value="all">All directions</option>
            <option value="inflow">Inflow</option>
            <option value="outflow">Outflow</option>
          </select>
          <select
            className={styles.select}
            value={filters.categoryId}
            onChange={(e) =>
              setFilters((prev) => ({
                ...prev,
                categoryId: e.target.value,
              }))
            }
          >
            <option value="all">All categories</option>
            {categories.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
          <div className={styles.datePresetGroup}>
            {(["7d", "30d", "90d"] as DatePreset[]).map((preset) => (
              <button
                key={preset}
                className={`${styles.datePresetButton} ${
                  filters.datePreset === preset ? styles.datePresetButtonActive : ""
                }`}
                onClick={() =>
                  setFilters((prev) => ({
                    ...prev,
                    datePreset: prev.datePreset === preset ? null : preset,
                  }))
                }
                type="button"
              >
                {preset}
              </button>
            ))}
          </div>
          <button
            className={styles.clearButton}
            onClick={() => {
              setFilters(DEFAULT_FILTERS);
              onClearDrilldown?.();
            }}
            disabled={!hasFilters}
          >
            {drilldown ? "Clear drilldown" : "Clear filters"}
          </button>
        </div>
        <div className={styles.resultsMeta}>
          {filters.merchantKey && (
            <span className={styles.drilldownPill}>
              Merchant: {filters.merchantKey}
            </span>
          )}
          <span>{filteredTxns.length} results</span>
        </div>
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>When</th>
              <th>Description</th>
              <th>Account</th>
              <th>Category</th>
              <th className={styles.alignRight}>Amount</th>
            </tr>
          </thead>
          <tbody>
            {filteredTxns.map((t) => (
              <tr key={t.id}>
                <td className={styles.noWrap}>
                  {new Date(t.occurred_at).toLocaleString()}
                </td>
                <td>
                  <div className={styles.tableTitle}>{t.description}</div>
                  <small className={styles.tableSub}>
                    event {t.source_event_id.slice(-6)}
                    {t.counterparty_hint ? ` · hint: ${t.counterparty_hint}` : ""}
                  </small>
                </td>
                <td>{t.account}</td>
                <td>{t.category}</td>
                <td className={styles.alignRight}>
                  {fmtMoney(t.amount, t.direction)}
                </td>
              </tr>
            ))}
            {filteredTxns.length === 0 && (
              <tr>
                <td colSpan={5} className={styles.emptyRow}>
                  No transactions match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {data?.last_event_occurred_at && (
        <small className={styles.footerMeta}>
          Latest event occurred at {new Date(data.last_event_occurred_at).toLocaleString()}.
        </small>
      )}
    </div>
  );
}
