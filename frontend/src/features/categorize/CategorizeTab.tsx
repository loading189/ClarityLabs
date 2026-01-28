import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  bulkApplyByMerchantKey,
  getCategories,
  getCategorizeMetrics,
  getTxnsToCategorize,
  saveCategorization,
  type CategoryOut,
  type CategorizeMetricsOut,
  type NormalizedTxn,
} from "../../api/categorize";
import styles from "./CategorizeTab.module.css";
import { logRefresh } from "../../utils/refreshLog";

export type CategorizeDrilldown = {
  merchant_key?: string;
  direction?: "inflow" | "outflow";
  search?: string;
  date_preset?: "7d" | "30d" | "90d";
};

type DatePreset = "7d" | "30d" | "90d";

const DATE_PRESET_DAYS: Record<DatePreset, number> = {
  "7d": 7,
  "30d": 30,
  "90d": 90,
};

export default function CategorizeTab({
  businessId,
  drilldown,
  onClearDrilldown,
  onCategorizationChange,
}: {
  businessId: string;
  drilldown?: CategorizeDrilldown | null;
  onClearDrilldown?: () => void;
  onCategorizationChange?: () => void;
}) {
  const [txns, setTxns] = useState<NormalizedTxn[]>([]);
  const [cats, setCats] = useState<CategoryOut[]>([]);
  const [metrics, setMetrics] = useState<CategorizeMetricsOut | null>(null);
  const [selectedTxn, setSelectedTxn] = useState<NormalizedTxn | null>(null);
  const [selectedCategoryId, setSelectedCategoryId] = useState<string>("");
  const selectedTxnRef = useRef<NormalizedTxn | null>(null);

  const [loading, setLoading] = useState(false);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  // Prevent stale-load races when businessId changes quickly
  const loadSeq = useRef(0);

  const catsById = useMemo(() => {
    const m = new Map<string, CategoryOut>();
    for (const c of cats) m.set(c.id, c);
    return m;
  }, [cats]);

  const currencyFormatter = useMemo(
    () => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }),
    []
  );

  const formatAmount = useCallback(
    (txn: NormalizedTxn): string => {
      const direction = (txn.direction || "").toLowerCase();
      const sign = direction === "inflow" ? "+" : direction === "outflow" ? "-" : "";
      const amount = Number.isFinite(txn.amount) ? Math.abs(txn.amount) : 0;
      return `${sign}${currencyFormatter.format(amount)}`;
    },
    [currencyFormatter]
  );

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

  const pickBestCategoryId = useCallback(
    (txn: NormalizedTxn | null, categories: CategoryOut[]): string => {
      if (!categories.length) return "";
      const suggested = (txn?.suggested_category_id ?? "") as string;
      if (suggested && categories.some((c) => c.id === suggested)) return suggested;
      return categories[0].id;
    },
    []
  );

  // Suggestion-derived UI fields (guarded)
  const suggestedCategoryId = useMemo(
    () => (selectedTxn?.suggested_category_id ?? "") as string,
    [selectedTxn]
  );

  const suggestedCategory = useMemo(() => {
    if (!suggestedCategoryId) return null;
    const category = catsById.get(suggestedCategoryId) ?? null;
    if (!category || isCategoryUncategorized(category)) return null;
    return category;
  }, [catsById, isCategoryUncategorized, suggestedCategoryId]);

  const suggestedName = useMemo(() => {
    if (!suggestedCategory) return "No suggestion";
    return suggestedCategory.name;
  }, [suggestedCategory]);

  const suggestedPct = useMemo(() => {
    const c = Number(selectedTxn?.confidence ?? 0);
    return Math.max(0, Math.min(100, Math.round(c * 100)));
  }, [selectedTxn]);

  const suggestedIdIsValid = useMemo(() => {
    return !!suggestedCategory;
  }, [suggestedCategory]);

  const bulkCategoryId = suggestedIdIsValid ? suggestedCategoryId : selectedCategoryId;
  const bulkCategoryIsValid = useMemo(() => {
    if (!bulkCategoryId) return false;
    return !isCategoryUncategorized(catsById.get(bulkCategoryId));
  }, [bulkCategoryId, catsById, isCategoryUncategorized]);

  const metricsSuggestionPercent = useMemo(() => {
    if (!metrics) return 0;
    const denom = metrics.uncategorized || metrics.total_events || 0;
    if (!denom) return 0;
    return Math.round((metrics.suggestion_coverage / denom) * 100);
  }, [metrics]);

  const load = useCallback(async () => {
    if (!businessId) return;

    const seq = ++loadSeq.current;

    setLoading(true);
    setLoadErr(null);
    setMsg(null);

    try {
      logRefresh("categorize", "reload");
      const [t, c, m] = await Promise.all([
        getTxnsToCategorize(businessId, 50),
        getCategories(businessId),
        getCategorizeMetrics(businessId),
      ]);

      // If a newer load started, ignore this result
      if (seq !== loadSeq.current) return;

      setTxns(t);
      setCats(c);
      setMetrics(m);

      const existingTxn = selectedTxnRef.current
        ? t.find((txn) => txn.source_event_id === selectedTxnRef.current?.source_event_id) ?? null
        : null;
      const nextTxn = existingTxn ?? t[0] ?? null;
      setSelectedTxn(nextTxn);
      setSelectedCategoryId(pickBestCategoryId(nextTxn, c));
    } catch (e: any) {
      if (seq !== loadSeq.current) return;
      setLoadErr(e?.message ?? "Failed to load categorization");
    } finally {
      if (seq === loadSeq.current) setLoading(false);
    }
  }, [businessId, pickBestCategoryId]);

  const pickTxn = useCallback(
    (t: NormalizedTxn) => {
      setSelectedTxn(t);
      setSelectedCategoryId(pickBestCategoryId(t, cats));
      setMsg(null);
      setActionErr(null);
    },
    [cats, pickBestCategoryId]
  );

  const activeDrilldown = useMemo(() => {
    if (!drilldown) return null;
    return {
      direction: drilldown.direction ?? null,
      merchantKey: drilldown.merchant_key ?? "",
      search: drilldown.search ?? "",
      datePreset: drilldown.date_preset ?? null,
    };
  }, [drilldown]);

  const drilldownSummary = useMemo(() => {
    if (!drilldown) return "";
    const parts = [];
    if (drilldown.direction) parts.push(`Direction: ${drilldown.direction}`);
    if (drilldown.merchant_key) parts.push(`Merchant: ${drilldown.merchant_key}`);
    if (drilldown.search) parts.push(`Search: "${drilldown.search}"`);
    if (drilldown.date_preset) parts.push(`Range: ${drilldown.date_preset}`);
    return parts.join(" · ");
  }, [drilldown]);

  const filteredTxns = useMemo(() => {
    if (!activeDrilldown) return txns;
    const search = activeDrilldown.search.trim().toLowerCase();
    const merchantKey = activeDrilldown.merchantKey.trim().toLowerCase();
    const now = Date.now();
    const days = activeDrilldown.datePreset
      ? DATE_PRESET_DAYS[activeDrilldown.datePreset as DatePreset]
      : null;
    const cutoff = days ? now - days * 24 * 60 * 60 * 1000 : null;

    return txns.filter((t) => {
      if (activeDrilldown.direction && t.direction !== activeDrilldown.direction) {
        return false;
      }
      if (search) {
        const haystack = `${t.description ?? ""} ${t.category_hint ?? ""}`.toLowerCase();
        if (!haystack.includes(search)) return false;
      }
      if (merchantKey) {
        const candidate = (t.merchant_key ?? "").toLowerCase();
        if (!candidate.includes(merchantKey)) return false;
      }
      if (cutoff) {
        const occurredAt = t.occurred_at ? Date.parse(t.occurred_at) : Number.NaN;
        if (Number.isFinite(occurredAt) && occurredAt < cutoff) return false;
      }
      return true;
    });
  }, [activeDrilldown, txns]);

  const doSave = useCallback(
    async (categoryId: string, source: "manual" | "rule" | "ml") => {
      if (!selectedTxn) return;

      setActionErr(null);
      setMsg(null);

      try {
        const res: any = await saveCategorization(businessId, {
          source_event_id: selectedTxn.source_event_id,
          category_id: categoryId,
          source,
          confidence: source === "manual" ? 1.0 : Number(selectedTxn.confidence ?? 0.75),
        });

        setMsg(
          res?.learned
            ? `Saved. Learned vendor → ${res.learned_system_key ?? ""}. Reloading…`
            : "Saved. Reloading…"
        );

        await load(); // ✅ ensures next txn shows updated suggestions
        onCategorizationChange?.();
      } catch (e: any) {
        setActionErr(e?.message ?? "Save failed");
      }
    },
    [businessId, selectedTxn, load, onCategorizationChange]
  );

  const doBulkApply = useCallback(
    async (categoryId: string) => {
      if (!selectedTxn) return;

      if (!selectedTxn.merchant_key) {
        setActionErr("No merchant key available for this vendor.");
        return;
      }

      setActionErr(null);
      setMsg(null);

      try {
        const res = await bulkApplyByMerchantKey(businessId, {
          merchant_key: selectedTxn.merchant_key,
          category_id: categoryId,
          source: "bulk",
          confidence: Number(selectedTxn.confidence ?? 1.0),
        });

        setMsg(
          `Applied to ${res.matched_events} events (${res.created} new, ${res.updated} updated). Reloading…`
        );
        await load();
        onCategorizationChange?.();
      } catch (e: any) {
        setActionErr(e?.message ?? "Failed to apply vendor categorization");
      }
    },
    [businessId, load, selectedTxn, onCategorizationChange]
  );


  // When categories arrive/refresh, ensure selection is valid.
  useEffect(() => {
    if (!cats.length) {
      setSelectedCategoryId("");
      return;
    }

    if (!selectedCategoryId || !catsById.has(selectedCategoryId)) {
      setSelectedCategoryId(pickBestCategoryId(selectedTxn, cats));
    }
  }, [cats, catsById, pickBestCategoryId, selectedCategoryId, selectedTxn]);

  useEffect(() => {
    selectedTxnRef.current = selectedTxn;
  }, [selectedTxn]);

  // On business change, reload
  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!selectedTxn) return;
    const stillVisible = filteredTxns.some(
      (txn) => txn.source_event_id === selectedTxn.source_event_id
    );
    if (!stillVisible) {
      setSelectedTxn(filteredTxns[0] ?? null);
    }
  }, [filteredTxns, selectedTxn]);

  if (loading) return <div className={styles.loading}>Loading…</div>;

  return (
    <div className={styles.container}>
      {/* LEFT: txns */}
      <div className={styles.panel}>
        <div className={styles.headerRow}>
          <h3 className={styles.title}>To categorize</h3>
          <button className={styles.buttonSecondary} onClick={load}>
            Reload
          </button>
        </div>

        {drilldown && (
          <div className={styles.drilldownBanner}>
            <span className={styles.drilldownLabel}>Active drilldown</span>
            <span className={styles.drilldownText}>
              {drilldownSummary || "Filters applied from Health."}
            </span>
            <button
              className={styles.drilldownClear}
              onClick={() => onClearDrilldown?.()}
              type="button"
            >
              Clear
            </button>
          </div>
        )}

        {loadErr && <div className={styles.error}>Load error: {loadErr}</div>}

        {metrics && (
          <div className={styles.metricsPanel}>
            <div className={styles.metricsGrid}>
              <div className={styles.metricItem}>
                <span className={styles.metricLabel}>Total events</span>
                <span className={styles.metricValue}>{metrics.total_events}</span>
              </div>
              <div className={styles.metricItem}>
                <span className={styles.metricLabel}>Posted</span>
                <span className={styles.metricValue}>{metrics.posted}</span>
              </div>
              <div className={styles.metricItem}>
                <span className={styles.metricLabel}>Remaining</span>
                <span className={styles.metricValue}>{metrics.uncategorized}</span>
              </div>
              <div className={styles.metricItem}>
                <span className={styles.metricLabel}>Suggestion coverage</span>
                <span className={styles.metricValue}>
                  {metrics.suggestion_coverage} ({metricsSuggestionPercent}%)
                </span>
              </div>
              <div className={styles.metricItem}>
                <span className={styles.metricLabel}>Brain coverage</span>
                <span className={styles.metricValue}>{metrics.brain_coverage}</span>
              </div>
            </div>
          </div>
        )}

        {filteredTxns.length === 0 ? (
          <div className={styles.emptyState}>No uncategorized transactions.</div>
        ) : (
          <div className={styles.txnList}>
            {filteredTxns.map((t) => (
              <button
                key={t.source_event_id}
                onClick={() => pickTxn(t)}
                aria-pressed={selectedTxn?.source_event_id === t.source_event_id}
                aria-label={`Select transaction ${t.description}`}
                className={`${styles.txnItem} ${
                  selectedTxn?.source_event_id === t.source_event_id ? styles.txnItemActive : ""
                }`}
              >
                <div className={styles.txnTitle}>{t.description}</div>
                <div className={styles.txnMeta}>
                  {new Date(t.occurred_at).toLocaleString()} • {t.account} • {t.direction} •{" "}
                  {formatAmount(t)}
                </div>

                {t.suggested_category_id &&
                  catsById.has(t.suggested_category_id) &&
                  !isCategoryUncategorized(catsById.get(t.suggested_category_id)) && (
                    <div className={styles.suggestionLine}>
                      Suggestion: <strong>{catsById.get(t.suggested_category_id)?.name}</strong> •{" "}
                      {Math.round(Number(t.confidence ?? 0) * 100)}%
                    </div>
                  )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* RIGHT: assign */}
      <div className={styles.panel}>
        <h3 className={styles.assignHeader}>Assign category</h3>

        {msg && <div className={styles.message}>{msg}</div>}
        {actionErr && <div className={styles.error}>Error: {actionErr}</div>}

        {!selectedTxn ? (
          <div className={styles.noSelection}>Select a transaction.</div>
        ) : (
          <>
            <div className={styles.txnTitle}>{selectedTxn.description}</div>
            <div className={styles.metaLine}>
              {selectedTxn.direction} • {formatAmount(selectedTxn)} • hint:{" "}
              {selectedTxn.category_hint}
            </div>

            {/* Suggestion box */}
            <div className={styles.suggestionBox}>
              <div className={styles.suggestionHeader}>Suggestion</div>

              <div className={styles.suggestionContent}>
                <strong className={styles.txnTitle}>{suggestedName}</strong>
                {suggestedIdIsValid && (
                  <span className={styles.txnMeta}>
                    {suggestedPct}% • {selectedTxn.suggestion_source ?? "rule"}
                  </span>
                )}
              </div>

              <div className={styles.suggestionReason}>{selectedTxn.reason ?? "—"}</div>

              <div className={styles.buttonRow}>
                <button
                  className={styles.buttonSecondary}
                  disabled={!suggestedIdIsValid}
                  onClick={() => {
                    if (!suggestedIdIsValid) return;
                    setSelectedCategoryId(suggestedCategoryId);
                    setMsg("Suggestion applied (selected).");
                  }}
                >
                  Apply suggestion
                </button>

                <button
                  className={styles.buttonPrimary}
                  disabled={
                    !selectedTxn.merchant_key ||
                    !bulkCategoryIsValid
                  }
                  onClick={() => {
                    if (!bulkCategoryIsValid) return;
                    doBulkApply(bulkCategoryId);
                  }}
                >
                  Apply to vendor (uncategorized only)
                </button>
              </div>
            </div>

            {/* Manual selection */}
            <div className={styles.formRow}>
              <label className={styles.label}>
                <span className={styles.suggestionHeader}>Category</span>

                <select
                  value={selectedCategoryId}
                  onChange={(e) => setSelectedCategoryId(e.target.value)}
                  disabled={!cats.length}
                  className={styles.select}
                >
                  {!cats.length ? (
                    <option value="">No categories</option>
                  ) : (
                    cats.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} — {c.account_code ? `${c.account_code} ` : ""}
                        {c.account_name}
                      </option>
                    ))
                  )}
                </select>
              </label>

              <div className={styles.buttonRow}>
                <button
                  className={styles.buttonPrimary}
                  disabled={!selectedCategoryId}
                  onClick={() => doSave(selectedCategoryId, "manual")}
                >
                  Save categorization
                </button>

                <button
                  className={styles.buttonSecondary}
                  disabled={!suggestedIdIsValid}
                  onClick={() => {
                    if (!suggestedIdIsValid) return;
                    doSave(suggestedCategoryId, "rule");
                  }}
                >
                  Save using suggestion
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
