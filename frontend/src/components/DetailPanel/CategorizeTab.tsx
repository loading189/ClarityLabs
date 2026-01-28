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

export default function CategorizeTab({ businessId }: { businessId: string }) {
  const [txns, setTxns] = useState<NormalizedTxn[]>([]);
  const [cats, setCats] = useState<CategoryOut[]>([]);
  const [metrics, setMetrics] = useState<CategorizeMetricsOut | null>(null);
  const [selectedTxn, setSelectedTxn] = useState<NormalizedTxn | null>(null);
  const [selectedCategoryId, setSelectedCategoryId] = useState<string>("");
  const selectedTxnRef = useRef<NormalizedTxn | null>(null);

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
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
      const sign = direction === "inflow" ? "+" : "-";
      const amount = Number.isFinite(txn.amount) ? Math.abs(txn.amount) : 0;
      return `${sign}${currencyFormatter.format(amount)}`;
    },
    [currencyFormatter]
  );

  const isUncategorized = useCallback((value?: string | null) => {
    return (value ?? "").trim().toLowerCase() === "uncategorized";
  }, []);

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
    if (!suggestedCategoryId || isUncategorized(selectedTxn?.suggested_system_key)) return null;
    return catsById.get(suggestedCategoryId) ?? null;
  }, [catsById, isUncategorized, selectedTxn, suggestedCategoryId]);

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
    setErr(null);
    setMsg(null);

    try {
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
      setErr(e?.message ?? "Failed to load categorization");
    } finally {
      if (seq === loadSeq.current) setLoading(false);
    }
  }, [businessId, pickBestCategoryId]);

  const pickTxn = useCallback(
    (t: NormalizedTxn) => {
      setSelectedTxn(t);
      setSelectedCategoryId(pickBestCategoryId(t, cats));
      setMsg(null);
      setErr(null);
    },
    [cats, pickBestCategoryId]
  );

  const doSave = useCallback(
    async (categoryId: string, source: "manual" | "rule" | "ml") => {
      if (!selectedTxn) return;

      setErr(null);
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
      } catch (e: any) {
        setErr(e?.message ?? "Save failed");
      }
    },
    [businessId, selectedTxn, load]
  );

  const doBulkApply = useCallback(
    async (categoryId: string) => {
      if (!selectedTxn) return;

      if (!selectedTxn.merchant_key) {
        setErr("No merchant key available for this vendor.");
        return;
      }

      setErr(null);
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
      } catch (e: any) {
        setErr(e?.message ?? "Failed to apply vendor categorization");
      }
    },
    [businessId, load, selectedTxn]
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

  if (loading) return <div className={styles.loading}>Loading…</div>;
  if (err) return <div className={styles.error}>Error: {err}</div>;

  return (
    <div className={styles.container}>
      {/* LEFT: txns */}
      <div className={styles.panel}>
        <div className={styles.headerRow}>
          <h3 className={styles.title}>To categorize</h3>
          <button className="closeBtn" onClick={load}>
            Reload
          </button>
        </div>

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

        {txns.length === 0 ? (
          <div className={styles.emptyState}>No uncategorized transactions.</div>
        ) : (
          <div className={styles.txnList}>
            {txns.map((t) => (
              <button
                key={t.source_event_id}
                onClick={() => pickTxn(t)}
                aria-pressed={selectedTxn?.source_event_id === t.source_event_id}
                aria-label={`Select transaction ${t.description}`}
                className={`${styles.txnItem} ${
                  selectedTxn?.source_event_id === t.source_event_id ? styles.txnItemActive : ""
                } closeBtn`}
              >
                <div className={styles.txnTitle}>{t.description}</div>
                <div className={styles.txnMeta}>
                  {new Date(t.occurred_at).toLocaleString()} • {t.account} • {t.direction} •{" "}
                  {formatAmount(t)}
                </div>

                {t.suggested_category_id &&
                  catsById.has(t.suggested_category_id) &&
                  !isUncategorized(t.suggested_system_key) && (
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
        {err && <div className={styles.error}>Error: {err}</div>}

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
                  className="closeBtn"
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
                  className="closeBtn"
                  disabled={
                    !selectedTxn.merchant_key ||
                    (!suggestedIdIsValid && !selectedCategoryId) ||
                    isUncategorized(selectedTxn.suggested_system_key)
                  }
                  onClick={() =>
                    doBulkApply(suggestedIdIsValid ? suggestedCategoryId : selectedCategoryId)
                  }
                >
                  Always use this for this vendor
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
                  className="closeBtn"
                  disabled={!selectedCategoryId}
                  onClick={() => doSave(selectedCategoryId, "manual")}
                >
                  Save categorization
                </button>

                <button
                  className="closeBtn"
                  disabled={!suggestedIdIsValid}
                  onClick={() => doSave(suggestedCategoryId, "rule")}
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
