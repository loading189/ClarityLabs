// src/components/detail/TransactionsTab.tsx
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTransactions } from "../../hooks/useTransactions";
import {
  bulkApplyByMerchantKey,
  getCategories,
  getBrainVendor,
  setBrainVendor,
  forgetBrainVendor,
  saveCategorization,
  createCategoryRule,
  type BrainVendor,
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

const MERCHANT_STOPWORDS = new Set([
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

function toMerchantKey(description?: string | null) {
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
    .filter((token) => token && !MERCHANT_STOPWORDS.has(token))
    .slice(0, 6);
  return tokens.join(" ");
}

function buildRuleContainsText(description?: string | null) {
  const cleaned = (description || "")
    .replace(/\s+/g, " ")
    .trim();
  if (!cleaned) return "";
  return cleaned.slice(0, 80);
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
  const [vendorPanelOpen, setVendorPanelOpen] = useState(false);
  const [vendorInfo, setVendorInfo] = useState<BrainVendor | null>(null);
  const [vendorLoading, setVendorLoading] = useState(false);
  const [vendorErr, setVendorErr] = useState<string | null>(null);
  const [vendorActionErr, setVendorActionErr] = useState<string | null>(null);
  const [vendorActionMsg, setVendorActionMsg] = useState<string | null>(null);
  const [vendorActionLoading, setVendorActionLoading] = useState(false);
  const [vendorCategoryId, setVendorCategoryId] = useState<string>("");
  const [vendorCanonicalName, setVendorCanonicalName] = useState<string>("");
  const [applyToUncategorized, setApplyToUncategorized] = useState(false);
  const [rulePanelOpen, setRulePanelOpen] = useState(false);
  const [ruleContainsText, setRuleContainsText] = useState("");
  const [ruleDirection, setRuleDirection] = useState<"" | "inflow" | "outflow">("");
  const [ruleAccount, setRuleAccount] = useState("");
  const [rulePriority, setRulePriority] = useState(100);
  const [ruleCategoryId, setRuleCategoryId] = useState("");
  const [ruleActionErr, setRuleActionErr] = useState<string | null>(null);
  const [ruleActionMsg, setRuleActionMsg] = useState<string | null>(null);
  const [ruleActionLoading, setRuleActionLoading] = useState(false);

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
  const getTxnKey = useCallback((txn: NormalizedTxn) => {
    return txn.source_event_id || txn.id;
  }, []);

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

  const categoriesBySystemKey = useMemo(() => {
    const map = new Map<string, CategoryOut>();
    categories.forEach((category) => {
      if (category.system_key) {
        map.set(category.system_key.toLowerCase(), category);
      }
    });
    return map;
  }, [categories]);

  const selectableCategories = useMemo(
    () => categories.filter((category) => !isCategoryUncategorized(category)),
    [categories, isCategoryUncategorized]
  );

  const merchantKeyByTxn = useMemo(() => {
    const map = new Map<string, string>();
    txns.forEach((txn) => {
      map.set(getTxnKey(txn), toMerchantKey(txn.description));
    });
    return map;
  }, [getTxnKey, txns]);

  const categoryOptions = useMemo(() => {
    const set = new Set<string>();
    txns.forEach((txn) => {
      if (txn.category) {
        set.add(txn.category);
      }
    });
    return Array.from(set).sort((a, b) => a.localeCompare(b));
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
        const candidate = merchantKeyByTxn.get(getTxnKey(t)) ?? "";
        if (!candidate.includes(merchantKey)) return false;
      }
      if (cutoff) {
        const occurredAt = t.occurred_at ? Date.parse(t.occurred_at) : Number.NaN;
        if (Number.isFinite(occurredAt) && occurredAt < cutoff) return false;
      }
      return true;
    });
  }, [filters, getTxnKey, merchantKeyByTxn, txns]);

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
    const selectedKey = getTxnKey(selectedTxn);
    const stillVisible = filteredTxns.some((txn) => getTxnKey(txn) === selectedKey);
    if (!stillVisible) {
      setSelectedTxn(null);
    }
  }, [filteredTxns, getTxnKey, selectedTxn]);

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
    if (!selectedTxn) {
      setVendorPanelOpen(false);
      setVendorInfo(null);
      setVendorErr(null);
      setVendorActionErr(null);
      setVendorActionMsg(null);
      setVendorActionLoading(false);
      setVendorCategoryId("");
      setVendorCanonicalName("");
      setApplyToUncategorized(false);
      setRulePanelOpen(false);
      setRuleContainsText("");
      setRuleDirection("");
      setRuleAccount("");
      setRulePriority(100);
      setRuleCategoryId("");
      setRuleActionErr(null);
      setRuleActionMsg(null);
      setRuleActionLoading(false);
      return;
    }
    setVendorPanelOpen(false);
    setVendorInfo(null);
    setVendorErr(null);
    setVendorActionErr(null);
    setVendorActionMsg(null);
    setVendorActionLoading(false);
    setVendorCategoryId("");
    setVendorCanonicalName(selectedTxn.description ?? "");
    setApplyToUncategorized(false);
    setRulePanelOpen(false);
    setRuleContainsText(buildRuleContainsText(selectedTxn.description));
    setRuleDirection((selectedTxn.direction ?? "") as "inflow" | "outflow" | "");
    setRuleAccount(selectedTxn.account ?? "");
    setRulePriority(100);
    setRuleCategoryId("");
    setRuleActionErr(null);
    setRuleActionMsg(null);
    setRuleActionLoading(false);
  }, [selectedTxn]);

  useEffect(() => {
    if (!selectedTxn) return;
    if (!selectedCategoryId || !categoriesById.has(selectedCategoryId)) {
      const nextId = pickDefaultCategoryId(selectedTxn);
      if (nextId) setSelectedCategoryId(nextId);
    }
  }, [categoriesById, pickDefaultCategoryId, selectedCategoryId, selectedTxn]);

  const selectedCategory = selectedCategoryId ? categoriesById.get(selectedCategoryId) ?? null : null;
  const selectedCategoryValid = Boolean(
    selectedCategoryId && selectedCategory && !isCategoryUncategorized(selectedCategory)
  );

  useEffect(() => {
    if (!selectedTxn) return;
    const existing = ruleCategoryId ? categoriesById.get(ruleCategoryId) ?? null : null;
    if (existing && !isCategoryUncategorized(existing)) return;
    if (selectedCategoryValid) {
      setRuleCategoryId(selectedCategoryId);
    } else {
      setRuleCategoryId(selectableCategories[0]?.id ?? "");
    }
  }, [
    categoriesById,
    isCategoryUncategorized,
    ruleCategoryId,
    selectableCategories,
    selectedCategoryId,
    selectedCategoryValid,
    selectedTxn,
  ]);

  useEffect(() => {
    if (!vendorPanelOpen) return;
    if (vendorInfo?.system_key) {
      const mapped = categoriesBySystemKey.get(vendorInfo.system_key.toLowerCase());
      if (mapped && !isCategoryUncategorized(mapped)) {
        setVendorCategoryId(mapped.id);
        return;
      }
    }
    if (!vendorCategoryId) {
      if (selectedCategoryValid) {
        setVendorCategoryId(selectedCategoryId);
      } else {
        setVendorCategoryId(selectableCategories[0]?.id ?? "");
      }
    }
  }, [
    categoriesBySystemKey,
    isCategoryUncategorized,
    selectedCategoryId,
    selectedCategoryValid,
    selectableCategories,
    vendorCategoryId,
    vendorInfo,
    vendorPanelOpen,
  ]);

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

  const provenanceInfo = useMemo(() => {
    if (!selectedTxn) return null;
    const source = selectedTxn.suggestion_source ?? "";
    const confidenceRaw = selectedTxn.confidence;
    const hasConfidence = typeof confidenceRaw === "number";
    const confidence = hasConfidence
      ? Math.max(0, Math.min(100, Math.round(confidenceRaw * 100)))
      : null;
    const reason = selectedTxn.reason ?? "";
    if (!source && confidence === null && !reason) return null;
    return {
      source,
      confidence,
      reason,
    };
  }, [selectedTxn]);

  const vendorMappedCategory = useMemo(() => {
    if (!vendorInfo?.system_key) return null;
    return categoriesBySystemKey.get(vendorInfo.system_key.toLowerCase()) ?? null;
  }, [categoriesBySystemKey, vendorInfo]);

  const vendorCategoryName = vendorMappedCategory?.name ?? vendorInfo?.system_key ?? "—";

  const loadVendorInfo = useCallback(
    async (merchantKey: string) => {
      if (!merchantKey) return;
      setVendorLoading(true);
      setVendorErr(null);
      try {
        const res = await getBrainVendor(businessId, merchantKey);
        setVendorInfo(res);
        setVendorCanonicalName(res.canonical_name || merchantKey);
      } catch (e: any) {
        const message = e?.message ?? "Failed to load vendor memory";
        if (message.includes("404")) {
          setVendorInfo(null);
        } else {
          setVendorErr(message);
        }
      } finally {
        setVendorLoading(false);
      }
    },
    [businessId]
  );

  const handleSave = useCallback(async () => {
    if (!selectedTxn) return;
    const sourceEventId = getTxnKey(selectedTxn);
    if (!sourceEventId) {
      setActionErr("Missing source event id for this transaction.");
      return;
    }
    if (!selectedCategoryValid) {
      setActionErr("Select a valid category before saving.");
      return;
    }
    setActionErr(null);
    setActionMsg(null);
    setActionLoading(true);
    try {
      await saveCategorization(businessId, {
        source_event_id: sourceEventId,
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
  }, [
    businessId,
    getTxnKey,
    refresh,
    selectedCategoryId,
    selectedCategoryValid,
    selectedTxn,
  ]);

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

  const toggleVendorPanel = useCallback(async () => {
    if (vendorPanelOpen) {
      setVendorPanelOpen(false);
      return;
    }
    if (!selectedTxn?.merchant_key) return;
    setVendorPanelOpen(true);
    setVendorActionErr(null);
    setVendorActionMsg(null);
    setVendorErr(null);
    setVendorCanonicalName(selectedTxn.description ?? selectedTxn.merchant_key ?? "");
    await loadVendorInfo(selectedTxn.merchant_key);
  }, [loadVendorInfo, selectedTxn, vendorPanelOpen]);

  const handleVendorSave = useCallback(async () => {
    if (!selectedTxn?.merchant_key) return;
    if (!vendorCategoryId) {
      setVendorActionErr("Select a valid category for this vendor.");
      return;
    }
    setVendorActionErr(null);
    setVendorActionMsg(null);
    setVendorActionLoading(true);
    try {
      const res = await setBrainVendor(businessId, {
        merchant_key: selectedTxn.merchant_key,
        category_id: vendorCategoryId,
        canonical_name: vendorCanonicalName.trim() || undefined,
      });
      setVendorInfo(res);
      let message = "Vendor memory updated.";
      if (applyToUncategorized) {
        const bulk = await bulkApplyByMerchantKey(businessId, {
          merchant_key: selectedTxn.merchant_key,
          category_id: vendorCategoryId,
          source: "bulk",
          confidence: 1.0,
        });
        message = `Vendor memory updated. Applied to ${bulk.matched_events} events.`;
      }
      setVendorActionMsg(message);
      await refresh();
    } catch (e: any) {
      setVendorActionErr(e?.message ?? "Failed to update vendor memory");
    } finally {
      setVendorActionLoading(false);
    }
  }, [
    applyToUncategorized,
    businessId,
    refresh,
    selectedTxn,
    vendorCategoryId,
    vendorCanonicalName,
  ]);

  const handleVendorForget = useCallback(async () => {
    if (!selectedTxn?.merchant_key) return;
    setVendorActionErr(null);
    setVendorActionMsg(null);
    setVendorActionLoading(true);
    try {
      const res = await forgetBrainVendor(businessId, {
        merchant_key: selectedTxn.merchant_key,
      });
      if (res.deleted) {
        setVendorInfo(null);
        setVendorActionMsg("Vendor memory cleared.");
      } else {
        setVendorActionMsg("No vendor memory found to remove.");
      }
    } catch (e: any) {
      setVendorActionErr(e?.message ?? "Failed to forget vendor memory");
    } finally {
      setVendorActionLoading(false);
    }
  }, [businessId, selectedTxn]);

  const handleRuleCreate = useCallback(async () => {
    if (!selectedTxn) return;
    const trimmedContains = ruleContainsText.trim();
    if (!trimmedContains) {
      setRuleActionErr("Enter text to match before saving this rule.");
      return;
    }
    if (!ruleCategoryId) {
      setRuleActionErr("Select a category for this rule.");
      return;
    }
    const category = categoriesById.get(ruleCategoryId);
    if (!category || isCategoryUncategorized(category)) {
      setRuleActionErr("Select a valid category for this rule.");
      return;
    }
    setRuleActionErr(null);
    setRuleActionMsg(null);
    setRuleActionLoading(true);
    try {
      await createCategoryRule(businessId, {
        contains_text: trimmedContains,
        category_id: ruleCategoryId,
        direction: ruleDirection || null,
        account: ruleAccount.trim() || null,
        priority: Number.isFinite(rulePriority) ? rulePriority : 100,
        active: true,
      });
      setRuleActionMsg("Rule created. Refreshing transactions…");
      await refresh();
    } catch (e: any) {
      setRuleActionErr(e?.message ?? "Failed to create rule");
    } finally {
      setRuleActionLoading(false);
    }
  }, [
    businessId,
    categoriesById,
    isCategoryUncategorized,
    refresh,
    ruleAccount,
    ruleCategoryId,
    ruleContainsText,
    ruleDirection,
    rulePriority,
    selectedTxn,
  ]);

  if (loading && !data) return <div className={styles.loading}>Loading transactions…</div>;

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
            {categoryOptions.map((category) => (
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
            {filteredTxns.map((t) => {
              const txnKey = getTxnKey(t);
              const occurredLabel = t.occurred_at
                ? new Date(t.occurred_at).toLocaleString()
                : "—";
              const eventId = txnKey || "—";
              return (
              <tr
                key={txnKey}
                className={
                  txnKey === (selectedTxn ? getTxnKey(selectedTxn) : "") ? styles.tableRowSelected : ""
                }
                onClick={() => setSelectedTxn(t)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    setSelectedTxn(t);
                  }
                }}
                role="button"
                tabIndex={0}
                aria-label={`Open actions for ${t.description ?? "transaction"}`}
              >
                <td className={styles.noWrap}>
                  {occurredLabel}
                </td>
                <td>
                  <div className={styles.tableTitle}>{t.description}</div>
                  <small className={styles.tableSub}>
                    event {eventId ? eventId.slice(-6) : "—"}
                    {t.counterparty_hint ? ` · hint: ${t.counterparty_hint}` : ""}
                  </small>
                </td>
                <td>{t.account ?? "—"}</td>
                <td>{t.category ?? "—"}</td>
                <td className={styles.alignRight}>
                  {fmtMoney(t.amount, t.direction)}
                </td>
              </tr>
              );
            })}
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
                  {selectedTxn.occurred_at
                    ? new Date(selectedTxn.occurred_at).toLocaleString()
                    : "—"}
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

            {provenanceInfo && (
              <div className={styles.drawerSection}>
                <div className={styles.drawerSectionLabel}>Categorization source</div>
                <div className={styles.provenanceCard}>
                  {provenanceInfo.source && (
                    <div className={styles.provenanceRow}>
                      <span>Source</span>
                      <span className={styles.provenanceValue}>{provenanceInfo.source}</span>
                    </div>
                  )}
                  {provenanceInfo.confidence !== null && (
                    <div className={styles.provenanceRow}>
                      <span>Confidence</span>
                      <span className={styles.provenanceValue}>
                        {provenanceInfo.confidence}%
                      </span>
                    </div>
                  )}
                  {provenanceInfo.reason && (
                    <div className={styles.provenanceReason}>{provenanceInfo.reason}</div>
                  )}
                </div>
              </div>
            )}

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

            {selectedTxn.merchant_key && (
              <div className={styles.drawerSection}>
                <div className={styles.drawerSectionLabel}>Vendor</div>
                <div className={styles.vendorRow}>
                  <span className={styles.vendorKey}>{selectedTxn.merchant_key}</span>
                  <button
                    className={styles.linkButton}
                    onClick={toggleVendorPanel}
                    type="button"
                  >
                    {vendorPanelOpen ? "Hide vendor" : "Manage vendor"}
                  </button>
                </div>
              </div>
            )}

            {vendorPanelOpen && selectedTxn.merchant_key && (
              <div className={styles.vendorPanel}>
                <div className={styles.vendorPanelHeader}>
                  <div>
                    <div className={styles.vendorPanelTitle}>Vendor memory</div>
                    <div className={styles.vendorPanelSub}>
                      Applies automatically only to uncategorized transactions.
                    </div>
                  </div>
                  <button
                    className={styles.linkButton}
                    onClick={() => setVendorPanelOpen(false)}
                    type="button"
                  >
                    Close
                  </button>
                </div>

                {vendorLoading && (
                  <div className={styles.drawerHelp}>Loading vendor memory…</div>
                )}
                {vendorErr && <div className={styles.actionError}>{vendorErr}</div>}

                {!vendorLoading && !vendorInfo && (
                  <div className={styles.vendorEmpty}>
                    No vendor memory found yet for this merchant key.
                  </div>
                )}

                <div className={styles.vendorGrid}>
                  <div>
                    <div className={styles.vendorLabel}>Merchant key</div>
                    <div className={styles.vendorValue}>{selectedTxn.merchant_key}</div>
                  </div>
                  <label className={styles.vendorLabel} htmlFor="vendor-canonical">
                    Canonical name
                  </label>
                  <input
                    id="vendor-canonical"
                    className={styles.textInput}
                    value={vendorCanonicalName}
                    onChange={(event) => setVendorCanonicalName(event.target.value)}
                    placeholder="e.g., Acme Co"
                  />
                  <div>
                    <div className={styles.vendorLabel}>Current category</div>
                    <div className={styles.vendorValue}>{vendorCategoryName}</div>
                  </div>
                </div>

                {vendorInfo && (
                  <div className={styles.vendorMeta}>
                    <span>Confidence: {Math.round(vendorInfo.confidence * 100)}%</span>
                    <span>Evidence: {vendorInfo.evidence_count}</span>
                    {vendorInfo.updated_at && (
                      <span>Updated: {new Date(vendorInfo.updated_at).toLocaleString()}</span>
                    )}
                  </div>
                )}

                {vendorInfo?.alias_keys?.length ? (
                  <div className={styles.vendorAliases}>
                    <div className={styles.vendorLabel}>Aliases</div>
                    <div className={styles.vendorAliasList}>
                      {vendorInfo.alias_keys.map((alias) => (
                        <span key={alias} className={styles.vendorAlias}>
                          {alias}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}

                <div className={styles.vendorControls}>
                  <label className={styles.vendorLabel} htmlFor="vendor-category">
                    Change vendor category
                  </label>
                  <select
                    id="vendor-category"
                    className={styles.select}
                    value={vendorCategoryId}
                    onChange={(event) => setVendorCategoryId(event.target.value)}
                    disabled={selectableCategories.length === 0}
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
                  <label className={styles.checkboxRow}>
                    <input
                      type="checkbox"
                      checked={applyToUncategorized}
                      onChange={(event) => setApplyToUncategorized(event.target.checked)}
                    />
                    Apply to existing uncategorized
                  </label>
                </div>

                {vendorActionErr && <div className={styles.actionError}>{vendorActionErr}</div>}
                {vendorActionMsg && <div className={styles.actionMessage}>{vendorActionMsg}</div>}

                <div className={styles.vendorActions}>
                  <button
                    className={styles.primaryButton}
                    onClick={handleVendorSave}
                    disabled={!vendorCategoryId || vendorActionLoading}
                    type="button"
                  >
                    {vendorActionLoading ? "Saving…" : "Save vendor"}
                  </button>
                  <button
                    className={styles.secondaryButton}
                    onClick={handleVendorForget}
                    disabled={vendorActionLoading}
                    type="button"
                  >
                    Forget vendor
                  </button>
                </div>
              </div>
            )}

            <div className={styles.drawerSection}>
              <div className={styles.drawerSectionHeader}>
                <div className={styles.drawerSectionLabel}>Create rule</div>
                <button
                  className={styles.linkButton}
                  onClick={() => setRulePanelOpen((open) => !open)}
                  type="button"
                >
                  {rulePanelOpen ? "Hide" : "Show"}
                </button>
              </div>
              <div className={styles.drawerHelp}>
                Create a business rule that auto-categorizes matching transactions.
              </div>
              {rulePanelOpen && (
                <div className={styles.rulePanel}>
                  <label className={styles.ruleLabel} htmlFor="rule-contains">
                    Contains text
                  </label>
                  <input
                    id="rule-contains"
                    className={styles.textInput}
                    value={ruleContainsText}
                    onChange={(event) => setRuleContainsText(event.target.value)}
                    placeholder="e.g., Acme Coffee"
                  />
                  <label className={styles.ruleLabel} htmlFor="rule-direction">
                    Direction
                  </label>
                  <select
                    id="rule-direction"
                    className={styles.select}
                    value={ruleDirection}
                    onChange={(event) =>
                      setRuleDirection(event.target.value as "" | "inflow" | "outflow")
                    }
                  >
                    <option value="">Any direction</option>
                    <option value="inflow">Inflow</option>
                    <option value="outflow">Outflow</option>
                  </select>
                  <label className={styles.ruleLabel} htmlFor="rule-account">
                    Account
                  </label>
                  <input
                    id="rule-account"
                    className={styles.textInput}
                    value={ruleAccount}
                    onChange={(event) => setRuleAccount(event.target.value)}
                    placeholder="e.g., Checking"
                  />
                  <label className={styles.ruleLabel} htmlFor="rule-category">
                    Category
                  </label>
                  <select
                    id="rule-category"
                    className={styles.select}
                    value={ruleCategoryId}
                    onChange={(event) => setRuleCategoryId(event.target.value)}
                    disabled={selectableCategories.length === 0}
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
                  <label className={styles.ruleLabel} htmlFor="rule-priority">
                    Priority
                  </label>
                  <input
                    id="rule-priority"
                    className={styles.textInput}
                    type="number"
                    min={1}
                    value={Number.isFinite(rulePriority) ? rulePriority : 100}
                    onChange={(event) => {
                      const next = Number(event.target.value);
                      setRulePriority(Number.isFinite(next) ? next : 100);
                    }}
                  />

                  {ruleActionErr && <div className={styles.actionError}>{ruleActionErr}</div>}
                  {ruleActionMsg && <div className={styles.actionMessage}>{ruleActionMsg}</div>}

                  <div className={styles.ruleActions}>
                    <button
                      className={styles.primaryButton}
                      onClick={handleRuleCreate}
                      disabled={!ruleContainsText.trim() || !ruleCategoryId || ruleActionLoading}
                      type="button"
                    >
                      {ruleActionLoading ? "Creating…" : "Create rule"}
                    </button>
                  </div>
                </div>
              )}
            </div>

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
