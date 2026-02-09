import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import PageHeader from "../../components/common/PageHeader";
import { ApiError } from "../../api/client";
import {
  fetchCategories,
  fetchTxnsToCategorize,
  saveCategorization,
  type CategoryOut,
  type NormalizedTxn,
} from "../../api/categorize";
import { EmptyState, InlineAlert, LoadingState, Panel } from "../../components/ui";
import Button from "../../components/ui/Button";
import { assertBusinessId } from "../../utils/businessId";
import { normalizeVendorDisplay } from "../../utils/vendors";
import styles from "./CategorizePage.module.css";

export default function CategorizePage() {
  const { businessId: businessIdParam } = useParams();
  const businessId = assertBusinessId(businessIdParam, "CategorizePage");
  const [loading, setLoading] = useState(true);
  const [txns, setTxns] = useState<NormalizedTxn[]>([]);
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [categoriesError, setCategoriesError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [rowLoading, setRowLoading] = useState<Record<string, boolean>>({});
  const [selectedCategoryIds, setSelectedCategoryIds] = useState<Record<string, string>>({});
  const [search, setSearch] = useState("");
  const [direction, setDirection] = useState<"all" | "inflow" | "outflow">("all");

  const formatError = useCallback((err: unknown, fallback: string) => {
    if (err instanceof ApiError) return err.message;
    if (err instanceof Error) return err.message;
    return fallback;
  }, []);

  const load = useCallback(async () => {
    if (!businessId) return;
    setLoading(true);
    setLoadError(null);
    setCategoriesError(null);
    try {
      const [txnResult, categoryResult] = await Promise.allSettled([
        fetchTxnsToCategorize(businessId),
        fetchCategories(businessId),
      ]);

      if (txnResult.status === "fulfilled") {
        setTxns(txnResult.value);
      } else {
        setLoadError(formatError(txnResult.reason, "Unable to load transactions."));
        setTxns([]);
      }

      if (categoryResult.status === "fulfilled") {
        setCategories(categoryResult.value);
      } else {
        setCategoriesError(formatError(categoryResult.reason, "Unable to load categories."));
        setCategories([]);
      }

      setActionError(null);
    } finally {
      setLoading(false);
    }
  }, [businessId, formatError]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!categories.length) return;
    setSelectedCategoryIds((prev) => {
      const next = { ...prev };
      txns.forEach((txn) => {
        if (next[txn.source_event_id]) return;
        if (
          txn.suggested_category_id &&
          categories.some((category) => category.id === txn.suggested_category_id)
        ) {
          next[txn.source_event_id] = txn.suggested_category_id;
          return;
        }
        next[txn.source_event_id] = categories[0].id;
      });
      return next;
    });
  }, [categories, txns]);

  const isUncategorized = useCallback((value?: string | null) => {
    const normalized = (value ?? "").trim().toLowerCase();
    return (
      !normalized ||
      normalized === "uncategorized" ||
      normalized === "unknown" ||
      normalized === "unassigned"
    );
  }, []);

  const isTxnUncategorized = useCallback(
    (txn: NormalizedTxn) => {
      if (txn.category_id) return false;
      if (isUncategorized(txn.category_name)) return true;
      if (isUncategorized(txn.category_hint)) return true;
      return !txn.category_name && !txn.category_hint;
    },
    [isUncategorized]
  );

  const uncategorizedTxns = useMemo(
    () => txns.filter((txn) => isTxnUncategorized(txn)),
    [isTxnUncategorized, txns]
  );

  const filteredTxns = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return uncategorizedTxns.filter((txn) => {
      if (direction !== "all" && txn.direction !== direction) return false;
      if (!normalizedSearch) return true;
      const haystack = `${txn.description ?? ""} ${txn.counterparty_hint ?? ""} ${txn.merchant_key ?? ""}`
        .toLowerCase()
        .trim();
      return haystack.includes(normalizedSearch);
    });
  }, [direction, search, uncategorizedTxns]);

  const currencyFormatter = useMemo(
    () => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }),
    []
  );

  const formatAmount = useCallback(
    (txn: NormalizedTxn) => {
      const directionLabel = txn.direction?.toLowerCase();
      const sign = directionLabel === "inflow" ? "+" : directionLabel === "outflow" ? "-" : "";
      const amount = Number.isFinite(txn.amount) ? Math.abs(txn.amount) : 0;
      return `${sign}${currencyFormatter.format(amount)}`;
    },
    [currencyFormatter]
  );

  const formatDate = useCallback((value?: string | null) => {
    if (!value) return "—";
    const timestamp = Date.parse(value);
    if (!Number.isFinite(timestamp)) return value;
    return new Date(timestamp).toLocaleDateString();
  }, []);

  const resolveCategoryLabel = useCallback(
    (txn: NormalizedTxn) => {
      if (isTxnUncategorized(txn)) return "Uncategorized";
      return txn.category_name ?? txn.category_hint ?? "Uncategorized";
    },
    [isTxnUncategorized]
  );

  const handleApply = useCallback(
    async (txn: NormalizedTxn) => {
      if (!businessId) return;
      const categoryId = selectedCategoryIds[txn.source_event_id];
      if (!categoryId) {
        setActionError("Select a category before applying.");
        return;
      }

      setRowLoading((prev) => ({ ...prev, [txn.source_event_id]: true }));
      setActionError(null);
      setActionMessage(null);
      try {
        await saveCategorization(businessId, {
          source_event_id: txn.source_event_id,
          category_id: categoryId,
          source: "manual",
          confidence: 1,
        });
        setTxns((prev) => prev.filter((item) => item.source_event_id !== txn.source_event_id));
        setActionMessage("Categorization saved. The queue is up to date.");
      } catch (err) {
        setActionError(formatError(err, "Unable to save categorization."));
      } finally {
        setRowLoading((prev) => ({ ...prev, [txn.source_event_id]: false }));
      }
    },
    [businessId, formatError, selectedCategoryIds]
  );

  if (!businessId) {
    return (
      <div className={styles.page}>
        <PageHeader
          title="Categorize"
          subtitle="Review the queue, handle bulk changes, and keep the ledger clean."
        />
        <EmptyState
          title="Select a business workspace"
          description="Categorization is tied to a specific business. Pick a workspace to continue."
          action={
            <Link className={styles.link} to="/businesses">
              Go to Business Select
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <PageHeader
        title="Categorize"
        subtitle="Stay on top of uncategorized transactions with a focused, bookkeeping-first view."
      />
      <Panel className={styles.panel}>
        <div className={styles.toolbar}>
          <div className={styles.toolbarInfo}>
            <div className={styles.toolbarTitle}>Uncategorized queue</div>
            <div className={styles.toolbarMeta}>
              {uncategorizedTxns.length} transactions awaiting categorization
            </div>
          </div>
          <div className={styles.toolbarFilters}>
            <label className={styles.filterField}>
              <span>Search</span>
              <input
                className={styles.input}
                type="search"
                value={search}
                placeholder="Search description or vendor"
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
            <label className={styles.filterField}>
              <span>Direction</span>
              <select
                className={styles.select}
                value={direction}
                onChange={(event) =>
                  setDirection(event.target.value as "all" | "inflow" | "outflow")
                }
              >
                <option value="all">All</option>
                <option value="inflow">Inflow</option>
                <option value="outflow">Outflow</option>
              </select>
            </label>
            <Button variant="ghost" onClick={load} disabled={loading}>
              Refresh
            </Button>
          </div>
        </div>

        {loading && <LoadingState label="Loading uncategorized transactions…" rows={4} />}

        {!loading && loadError && (
          <InlineAlert
            tone="error"
            title="Unable to load categorization"
            description={loadError}
            action={
              <Button variant="secondary" onClick={load}>
                Retry
              </Button>
            }
          />
        )}

        {!loading && categoriesError && (
          <InlineAlert
            tone="error"
            title="Categories unavailable"
            description={categoriesError}
            action={
              <Button variant="secondary" onClick={load}>
                Retry
              </Button>
            }
          />
        )}

        {!loading && !loadError && !categoriesError && categories.length === 0 && (
          <InlineAlert
            tone="error"
            title="No categories available"
            description="Add categories or update your chart of accounts before categorizing."
            action={
              <Link className={styles.link} to={`/app/${businessId}/ledger`}>
                Go to Ledger
              </Link>
            }
          />
        )}

        {!loading && !loadError && categories.length > 0 && filteredTxns.length === 0 && (
          <EmptyState
            title="All caught up. No uncategorized transactions detected."
            description="Great work staying current. You can review the ledger or check signals for follow-ups."
            action={
              <div className={styles.emptyActions}>
                <Link className={styles.link} to={`/app/${businessId}/ledger`}>
                  Go to Ledger
                </Link>
                <Link className={styles.link} to={`/app/${businessId}/signals`}>
                  Go to Signals
                </Link>
                <Link className={styles.link} to={`/app/${businessId}/advisor`}>
                  Go to Inbox
                </Link>
              </div>
            }
          />
        )}

        {!loading && !loadError && categories.length > 0 && filteredTxns.length > 0 && (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Description</th>
                  <th>Vendor</th>
                  <th className={styles.amountCell}>Amount</th>
                  <th>Current category</th>
                  <th>Assign</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filteredTxns.map((txn) => {
                  const categoryValue =
                    selectedCategoryIds[txn.source_event_id] ?? categories[0]?.id ?? "";
                  const vendorLabel = normalizeVendorDisplay(
                    txn.description,
                    txn.counterparty_hint ?? txn.merchant_key
                  );
                  return (
                    <tr key={txn.source_event_id}>
                      <td>{formatDate(txn.occurred_at)}</td>
                      <td>
                        <div className={styles.cellTitle}>{txn.description}</div>
                      </td>
                      <td>{vendorLabel}</td>
                      <td className={styles.amountCell}>{formatAmount(txn)}</td>
                      <td>{resolveCategoryLabel(txn)}</td>
                      <td>
                        <select
                          className={styles.select}
                          value={categoryValue}
                          onChange={(event) =>
                            setSelectedCategoryIds((prev) => ({
                              ...prev,
                              [txn.source_event_id]: event.target.value,
                            }))
                          }
                        >
                          {categories.map((category) => (
                            <option key={category.id} value={category.id}>
                              {category.name}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className={styles.actionCell}>
                        <Button
                          variant="primary"
                          onClick={() => handleApply(txn)}
                          disabled={rowLoading[txn.source_event_id]}
                        >
                          {rowLoading[txn.source_event_id] ? "Saving…" : "Apply"}
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {actionMessage && <div className={styles.actionMessage}>{actionMessage}</div>}
        {actionError && (
          <InlineAlert tone="error" title="Action failed" description={actionError} />
        )}
      </Panel>
    </div>
  );
}
