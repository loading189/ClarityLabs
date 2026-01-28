// src/components/detail/TransactionsTab.tsx
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTransactions } from "../../hooks/useTransactions";
import {
  bulkApplyByMerchantKey,
  getCategories,
  saveCategorization,
  type CategoryOut,
} from "../../api/categorize";
import type { NormalizedTxn } from "../../api/transactions";
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
  const [selectedTxn, setSelectedTxn] = useState<NormalizedTxn | null>(null);
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [categoriesLoading, setCategoriesLoading] = useState(false);
  const [categoriesErr, setCategoriesErr] = useState<string | null>(null);
  const [selectedCategoryId, setSelectedCategoryId] = useState<string>("");
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [bulkLoading, setBulkLoading] = useState(false);

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

  const isUncategorized = useCallback((value?: string | null) => {
    return (value ?? "").trim().toLowerCase() === "uncategorized";
  }, []);

  const isCategoryUncategorized = useCallback(
    (category?: CategoryOut | null) => {
      if (!category) return false;
      return isUncategorized(category.system_key) || isUncategorized(category.name);
    },
    [isUncategorized]
  );

  const categoriesById = useMemo(() => {
    const map = new Map<string, CategoryOut>();
    categories.forEach((category) => map.set(category.id, category));
    return map;
  }, [categories]);

  const categoriesByName = useMemo(() => {
    const map = new Map<string, CategoryOut>();
    categories.forEach((category) => map.set(category.name.toLowerCase(), category));
    return map;
  }, [categories]);

  const selectableCategories = useMemo(
    () => categories.filter((category) => !isCategoryUncategorized(category)),
    [categories, isCategoryUncategorized]
  );

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

  const loadCategories = useCallback(async () => {
    if (!businessId) return;
    setCategoriesLoading(true);
    setCategoriesErr(null);
    try {
      const res = await getCategories(businessId);
      setCategories(res);
    } catch (e: any) {
      setCategoriesErr(e?.message ?? "Failed to load categories");
    } finally {
      setCategoriesLoading(false);
    }
  }, [businessId]);

  useEffect(() => {
    loadCategories();
  }, [loadCategories]);

  useEffect(() => {
    if (!selectedTxn) return;
    const stillVisible = filteredTxns.some((txn) => txn.id === selectedTxn.id);
    if (!stillVisible) {
      setSelectedTxn(null);
    }
  }, [filteredTxns, selectedTxn]);

  const pickDefaultCategoryId = useCallback(
    (txn: NormalizedTxn | null) => {
      if (!txn) return "";
      const suggestedId = (txn.suggested_category_id ?? "") as string;
      if (suggestedId) {
        const match = categoriesById.get(suggestedId);
        if (match && !isCategoryUncategorized(match)) return match.id;
      }
      const byName = categoriesByName.get((txn.category ?? "").toLowerCase());
      if (byName && !isCategoryUncategorized(byName)) return byName.id;
      return selectableCategories[0]?.id ?? "";
    },
    [categoriesById, categoriesByName, isCategoryUncategorized, selectableCategories]
  );

  useEffect(() => {
    if (!selectedTxn) {
      setSelectedCategoryId("");
      return;
    }
    const nextId = pickDefaultCategoryId(selectedTxn);
    setSelectedCategoryId(nextId);
    setActionErr(null);
    setActionMsg(null);
  }, [pickDefaultCategoryId, selectedTxn]);

  useEffect(() => {
    if (!selectedTxn) return;
    if (!selectedCategoryId || !categoriesById.has(selectedCategoryId)) {
      const nextId = pickDefaultCategoryId(selectedTxn);
      if (nextId) setSelectedCategoryId(nextId);
    }
  }, [categoriesById, pickDefaultCategoryId, selectedCategoryId, selectedTxn]);

  useEffect(() => {
    if (!selectedTxn) return;
    const suggestedId = selectedTxn.suggested_category_id ?? "";
    if (suggestedId && selectedCategoryId) {
      const match = categoriesById.get(suggestedId);
      if (match && !isCategoryUncategorized(match) && suggestedId !== selectedCategoryId) {
        setSelectedCategoryId(suggestedId);
      }
    }
  }, [categoriesById, isCategoryUncategorized, selectedCategoryId, selectedTxn]);

  useEffect(() => {
    if (!selectedTxn) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSelectedTxn(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedTxn]);

  const selectedCategory = selectedCategoryId ? categoriesById.get(selectedCategoryId) ?? null : null;
  const selectedCategoryValid = Boolean(
    selectedCategoryId && selectedCategory && !isCategoryUncategorized(selectedCategory)
  );

  const suggestionInfo = useMemo(() => {
    if (!selectedTxn) return null;
    const suggestedId = selectedTxn.suggested_category_id ?? "";
    const suggestedCategory = suggestedId ? categoriesById.get(suggestedId) ?? null : null;
    const suggestedName = suggestedCategory?.name ?? selectedTxn.suggested_category_name ?? "";
    const suggestedSystemKey = selectedTxn.suggested_system_key ?? suggestedCategory?.system_key ?? "";
    if (!suggestedName) return null;
    if (isUncategorized(suggestedName) || isUncategorized(suggestedSystemKey)) return null;
    if (suggestedCategory && isCategoryUncategorized(suggestedCategory)) return null;
    const confidence = Math.max(0, Math.min(100, Math.round(Number(selectedTxn.confidence ?? 0) * 100)));
    return {
      name: suggestedName,
      confidence,
      source: selectedTxn.suggestion_source ?? "",
      reason: selectedTxn.reason ?? "",
    };
  }, [categoriesById, isCategoryUncategorized, isUncategorized, selectedTxn]);

  const handleSave = useCallback(async () => {
    if (!selectedTxn) return;
    if (!selectedCategoryValid) {
      setActionErr("Select a valid category before saving.");
      return;
    }
    setActionErr(null);
    setActionMsg(null);
    setActionLoading(true);
    try {
      await saveCategorization(businessId, {
        source_event_id: selectedTxn.source_event_id,
        category_id: selectedCategoryId,
        source: "manual",
        confidence: 1.0,
      });
      setActionMsg("Categorization saved. Refreshing transactions…");
      await refresh();
    } catch (e: any) {
      setActionErr(e?.message ?? "Failed to save categorization");
    } finally {
      setActionLoading(false);
    }
  }, [businessId, refresh, selectedCategoryId, selectedCategoryValid, selectedTxn]);

  const handleBulkApply = useCallback(async () => {
    if (!selectedTxn) return;
    if (!selectedTxn.merchant_key) {
      setActionErr("No merchant key available for this vendor.");
      return;
    }
    if (!selectedCategoryValid) {
      setActionErr("Select a valid category before applying to this vendor.");
      return;
    }
    setActionErr(null);
    setActionMsg(null);
    setBulkLoading(true);
    try {
      const res = await bulkApplyByMerchantKey(businessId, {
        merchant_key: selectedTxn.merchant_key,
        category_id: selectedCategoryId,
        source: "bulk",
        confidence: 1.0,
      });
      setActionMsg(
        `Applied to ${res.matched_events} events (${res.created} new, ${res.updated} updated). Refreshing…`
      );
      await refresh();
    } catch (e: any) {
      setActionErr(e?.message ?? "Failed to apply vendor categorization");
    } finally {
      setBulkLoading(false);
    }
  }, [businessId, refresh, selectedCategoryId, selectedCategoryValid, selectedTxn]);

  if (loading && !data) return <div style={{ padding: 12 }}>Loading transactions…</div>;

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

      {(err || categoriesErr) && (
        <div className={styles.loadError}>
          {err && (
            <div>
              Transactions error: {err}{" "}
              <button className={styles.linkButton} onClick={refresh}>
                Retry
              </button>
            </div>
          )}
          {categoriesErr && (
            <div>
              Categories error: {categoriesErr}{" "}
              <button className={styles.linkButton} onClick={loadCategories}>
                Retry
              </button>
            </div>
          )}
        </div>
      )}

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
            {Array.from(new Set(txns.map((t) => t.category)))
              .sort((a, b) => a.localeCompare(b))
              .map((category) => (
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
              <tr
                key={t.id}
                className={t.id === selectedTxn?.id ? styles.tableRowSelected : ""}
                onClick={() => setSelectedTxn(t)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    setSelectedTxn(t);
                  }
                }}
                role="button"
                tabIndex={0}
                aria-label={`Open actions for ${t.description}`}
              >
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

      {selectedTxn && (
        <div className={styles.drawerOverlay} onClick={() => setSelectedTxn(null)}>
          <aside
            className={styles.drawerPanel}
            aria-label="Transaction actions"
            onClick={(event) => event.stopPropagation()}
          >
            <div className={styles.drawerHeader}>
              <div>
                <div className={styles.drawerTitle}>{selectedTxn.description}</div>
                <div className={styles.drawerMeta}>
                  {new Date(selectedTxn.occurred_at).toLocaleString()}
                </div>
              </div>
              <button
                className={styles.closeButton}
                aria-label="Close drawer"
                onClick={() => setSelectedTxn(null)}
                type="button"
              >
                ×
              </button>
            </div>

            <div className={styles.drawerAmount}>
              {fmtMoney(selectedTxn.amount, selectedTxn.direction)}
            </div>

            <div className={styles.drawerSection}>
              <div className={styles.drawerSectionLabel}>Current category</div>
              <div className={styles.drawerSectionValue}>
                {selectedTxn.category || "—"}
              </div>
            </div>

            {suggestionInfo && (
              <div className={styles.drawerSection}>
                <div className={styles.drawerSectionLabel}>Suggestion</div>
                <div className={styles.suggestionCard}>
                  <div className={styles.suggestionTitle}>{suggestionInfo.name}</div>
                  <div className={styles.suggestionMeta}>
                    Confidence: {suggestionInfo.confidence}%
                  </div>
                  {suggestionInfo.source && (
                    <div className={styles.suggestionMeta}>
                      Source: {suggestionInfo.source}
                    </div>
                  )}
                  {suggestionInfo.reason && (
                    <div className={styles.suggestionReason}>{suggestionInfo.reason}</div>
                  )}
                </div>
              </div>
            )}

            <div className={styles.drawerSection}>
              <label className={styles.drawerSectionLabel} htmlFor="txn-category">
                Categorize as
              </label>
              <select
                id="txn-category"
                className={styles.select}
                value={selectedCategoryId}
                onChange={(event) => setSelectedCategoryId(event.target.value)}
                disabled={categoriesLoading || selectableCategories.length === 0}
              >
                {selectableCategories.length === 0 && (
                  <option value="">No categories available</option>
                )}
                {selectableCategories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
              {categoriesLoading && (
                <div className={styles.drawerHelp}>Loading categories…</div>
              )}
            </div>

            {actionErr && <div className={styles.actionError}>{actionErr}</div>}
            {actionMsg && <div className={styles.actionMessage}>{actionMsg}</div>}

            <div className={styles.drawerActions}>
              <button
                className={styles.primaryButton}
                onClick={handleSave}
                disabled={!selectedCategoryValid || actionLoading}
                type="button"
              >
                {actionLoading ? "Saving…" : "Save categorization"}
              </button>
              <button
                className={styles.secondaryButton}
                onClick={handleBulkApply}
                disabled={!selectedTxn.merchant_key || !selectedCategoryValid || bulkLoading}
                type="button"
              >
                {bulkLoading ? "Applying…" : "Always use this for vendor"}
              </button>
              {!selectedTxn.merchant_key && (
                <div className={styles.drawerHelp}>Merchant key required for vendor rule.</div>
              )}
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
