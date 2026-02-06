import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  applyCategoryRule,
  autoCategorize,
  bulkApplyByMerchantKey,
  deleteCategoryRule,
  getCategories,
  getCategorizeMetrics,
  getTxnsToCategorize,
  listCategoryRules,
  previewCategoryRule,
  getBrainVendors,
  createCategoryRule,
  saveCategorization,
  updateCategoryRule,
  type CategoryRuleOut,
  type CategoryRulePreviewOut,
  type CategoryOut,
  type BrainVendor,
  type CategorizeMetricsOut,
  type NormalizedTxn,
} from "../../api/categorize";
import styles from "./CategorizeTab.module.css";
import { logRefresh } from "../../utils/refreshLog";
import { useAppState } from "../../app/state/appState";
import { isBusinessIdValid } from "../../utils/businessId";
import { isValidIsoDate } from "../../app/filters/filters";
import { normalizeVendorDisplay } from "../../utils/vendors";
import { hasValidCategoryMapping } from "../../utils/categories";
import RecentChangesPanel from "../../components/audit/RecentChangesPanel";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import TransactionDetailDrawer from "../../components/transactions/TransactionDetailDrawer";

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
  const [rules, setRules] = useState<CategoryRuleOut[]>([]);
  const [brainVendors, setBrainVendors] = useState<BrainVendor[]>([]);
  const [vendorErr, setVendorErr] = useState<string | null>(null);
  const [selectedTxn, setSelectedTxn] = useState<NormalizedTxn | null>(null);
  const [selectedCategoryId, setSelectedCategoryId] = useState<string>("");
  const [detailSourceEventId, setDetailSourceEventId] = useState<string | null>(null);
  const selectedTxnRef = useRef<NormalizedTxn | null>(null);
  const { dateRange, dataVersion, bumpDataVersion } = useAppState();

  const [loading, setLoading] = useState(false);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [rulesLoading, setRulesLoading] = useState(false);
  const [rulesErr, setRulesErr] = useState<string | null>(null);
  const [rulesMsg, setRulesMsg] = useState<string | null>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [toastAuditId, setToastAuditId] = useState<string | null>(null);
  const [reconciliationHint, setReconciliationHint] = useState<string | null>(null);
  const [autoCategorizeRunning, setAutoCategorizeRunning] = useState(false);
  const toastTimeoutRef = useRef<number | null>(null);
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [previewRuleId, setPreviewRuleId] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<CategoryRulePreviewOut | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const [applyLoadingRuleId, setApplyLoadingRuleId] = useState<string | null>(null);
  const [createRuleLoading, setCreateRuleLoading] = useState(false);
  const [createRuleErr, setCreateRuleErr] = useState<string | null>(null);
  const [ruleEdits, setRuleEdits] = useState<
    Record<string, { priority: string; category_id: string }>
  >({});
  const dateRangeStart = dateRange.start;
  const dateRangeEnd = dateRange.end;
  const urlSourceEventId = searchParams.get("source_event_id");

  const updateDetailParam = useCallback(
    (sourceEventId: string | null) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (sourceEventId) {
          next.set("source_event_id", sourceEventId);
        } else {
          next.delete("source_event_id");
        }
        return next;
      }, { replace: true });
    },
    [setSearchParams]
  );

  // Prevent stale-load races when businessId changes quickly
  const loadSeq = useRef(0);

  const catsById = useMemo(() => {
    const m = new Map<string, CategoryOut>();
    for (const c of cats) m.set(c.id, c);
    return m;
  }, [cats]);

  const vendorNameByKey = useMemo(() => {
    const map = new Map<string, BrainVendor>();
    brainVendors.forEach((vendor) => {
      vendor.alias_keys?.forEach((alias) => {
        map.set(alias, vendor);
      });
    });
    return map;
  }, [brainVendors]);

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

  const invalidBusinessId = useMemo(() => {
    return !isBusinessIdValid(businessId);
  }, [businessId]);

  const invalidDateRange = useMemo(() => {
    return (
      !isValidIsoDate(dateRangeStart) ||
      !isValidIsoDate(dateRangeEnd) ||
      dateRangeStart > dateRangeEnd
    );
  }, [dateRangeEnd, dateRangeStart]);

  const formatTxnDateTime = useCallback((occurredAt?: string | null): string => {
    if (!occurredAt) return "—";
    const timestamp = Date.parse(occurredAt);
    if (!Number.isFinite(timestamp)) return occurredAt;
    return new Date(timestamp).toLocaleString();
  }, []);

  const formatTxnDate = useCallback((occurredAt?: string | null): string => {
    if (!occurredAt) return "—";
    const timestamp = Date.parse(occurredAt);
    if (!Number.isFinite(timestamp)) return occurredAt;
    return new Date(timestamp).toLocaleDateString();
  }, []);

  const formatSignedAmount = useCallback(
    (amount: number, direction?: string | null): string => {
      const normalizedDirection = (direction || "").toLowerCase();
      const sign =
        normalizedDirection === "inflow" ? "+" : normalizedDirection === "outflow" ? "-" : "";
      const normalizedAmount = Number.isFinite(amount) ? Math.abs(amount) : 0;
      return `${sign}${currencyFormatter.format(normalizedAmount)}`;
    },
    [currencyFormatter]
  );

  const formatLastRun = useCallback((rule: CategoryRuleOut): string => {
    if (!rule.last_run_at) return "Never";
    const stamp = new Date(rule.last_run_at).toLocaleString();
    const updated = rule.last_run_updated_count ?? 0;
    return `${stamp} · ${updated} updated`;
  }, []);

  const pickBestCategoryId = useCallback(
    (txn: NormalizedTxn | null, categories: CategoryOut[]): string => {
      if (!categories.length) return "";
      const suggested = (txn?.suggested_category_id ?? "") as string;
      if (suggested && categories.some((c) => c.id === suggested)) return suggested;
      const fallback = categories.find((category) => hasValidCategoryMapping(category));
      return fallback?.id ?? categories[0].id;
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
    if (!category || !hasValidCategoryMapping(category)) return null;
    return category;
  }, [catsById, suggestedCategoryId]);

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
    return hasValidCategoryMapping(catsById.get(bulkCategoryId));
  }, [bulkCategoryId, catsById]);

  const selectedCategoryValid = useMemo(() => {
    if (!selectedCategoryId) return false;
    return hasValidCategoryMapping(catsById.get(selectedCategoryId));
  }, [catsById, selectedCategoryId]);

  const metricsSuggestionPercent = useMemo(() => {
    if (!metrics) return 0;
    const denom = metrics.uncategorized || metrics.total_events || 0;
    if (!denom) return 0;
    return Math.round((metrics.suggestion_coverage / denom) * 100);
  }, [metrics]);

  const missingCoaMappings = useMemo(() => {
    return cats.filter((cat) => !cat.account_id);
  }, [cats]);

  const load = useCallback(async () => {
    if (!businessId || invalidBusinessId || invalidDateRange) return;

    const seq = ++loadSeq.current;

    setLoading(true);
    setLoadErr(null);
    setMsg(null);

    try {
      logRefresh("categorize", "reload");
      const [t, c, m] = await Promise.all([
        getTxnsToCategorize(businessId, 50, { start_date: dateRangeStart, end_date: dateRangeEnd }),
        getCategories(businessId),
        getCategorizeMetrics(businessId),
      ]);

      // If a newer load started, ignore this result
      if (seq !== loadSeq.current) return;

      setTxns(t);
      setCats(c);
      setMetrics(m);
      setVendorErr(null);
      try {
        const vendors = await getBrainVendors(businessId);
        if (seq !== loadSeq.current) return;
        setBrainVendors(vendors);
      } catch (e: any) {
        if (seq !== loadSeq.current) return;
        console.error("[categorize] vendor fetch failed", {
          businessId,
          dateRangeStart,
          dateRangeEnd,
          url: `/categorize/business/${businessId}/brain/vendors`,
          error: e?.message ?? e,
        });
        setVendorErr(e?.message ?? "Failed to load vendor mappings");
        setBrainVendors([]);
      }

      const urlTxn = urlSourceEventId
        ? t.find((txn) => txn.source_event_id === urlSourceEventId) ?? null
        : null;
      const existingTxn = selectedTxnRef.current
        ? t.find((txn) => txn.source_event_id === selectedTxnRef.current?.source_event_id) ?? null
        : null;
      const nextTxn = urlTxn ?? existingTxn ?? t[0] ?? null;
      setSelectedTxn(nextTxn);
      setSelectedCategoryId(pickBestCategoryId(nextTxn, c));
      if (urlTxn) {
        setDetailSourceEventId(urlTxn.source_event_id);
      } else if (urlSourceEventId) {
        setDetailSourceEventId(null);
        updateDetailParam(null);
      }
    } catch (e: any) {
      if (seq !== loadSeq.current) return;
      console.error("[categorize] load failed", {
        businessId,
        dateRangeStart,
        dateRangeEnd,
        url: `/categorize/business/${businessId}/txns?limit=50&only_uncategorized=true&start_date=${dateRangeStart}&end_date=${dateRangeEnd}`,
        error: e?.message ?? e,
      });
      setLoadErr(e?.message ?? "Failed to load categorization");
    } finally {
      if (seq === loadSeq.current) setLoading(false);
    }
  }, [
    businessId,
    dateRangeEnd,
    dateRangeStart,
    invalidBusinessId,
    invalidDateRange,
    pickBestCategoryId,
    urlSourceEventId,
  ]);

  const loadRules = useCallback(async () => {
    if (!businessId || invalidBusinessId) return;
    setRulesLoading(true);
    setRulesErr(null);
    try {
      const data = await listCategoryRules(businessId);
      setRules(data);
    } catch (e: any) {
      console.error("[categorize] rules fetch failed", {
        businessId,
        dateRangeStart,
        dateRangeEnd,
        url: `/categorize/${businessId}/rules`,
        error: e?.message ?? e,
      });
      setRulesErr(e?.message ?? "Failed to load rules");
    } finally {
      setRulesLoading(false);
    }
  }, [businessId, dateRangeEnd, dateRangeStart, invalidBusinessId]);

  const pickTxn = useCallback(
    (t: NormalizedTxn) => {
      setSelectedTxn(t);
      setSelectedCategoryId(pickBestCategoryId(t, cats));
      setDetailSourceEventId(t.source_event_id);
      updateDetailParam(t.source_event_id);
      setMsg(null);
      setActionErr(null);
    },
    [cats, pickBestCategoryId, updateDetailParam]
  );

  const handleDrawerClose = useCallback(() => {
    setDetailSourceEventId(null);
    updateDetailParam(null);
  }, [updateDetailParam]);

  const handleAutoCategorize = useCallback(async () => {
    if (!businessId || invalidBusinessId) return;
    setActionErr(null);
    setMsg(null);
    setAutoCategorizeRunning(true);
    try {
      const res = await autoCategorize(businessId);
      setMsg(`Auto-categorized ${res.applied} transactions.`);
      bumpDataVersion();
      await load();
    } catch (e: any) {
      setActionErr(e?.message ?? "Auto-categorize failed.");
    } finally {
      setAutoCategorizeRunning(false);
    }
  }, [businessId, bumpDataVersion, invalidBusinessId, load]);

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
    const start = Date.parse(dateRangeStart);
    const endDay = Date.parse(dateRangeEnd);
    const end = Number.isFinite(endDay) ? endDay + 24 * 60 * 60 * 1000 - 1 : Number.NaN;
    let filtered = txns.filter((t) => {
      if (!Number.isFinite(start) || !Number.isFinite(end)) return true;
      const occurredAt = t.occurred_at ? Date.parse(t.occurred_at) : Number.NaN;
      if (!Number.isFinite(occurredAt)) return false;
      return occurredAt >= start && occurredAt <= end;
    });

    if (!activeDrilldown) return filtered;

    const search = activeDrilldown.search.trim().toLowerCase();
    const merchantKey = activeDrilldown.merchantKey.trim().toLowerCase();
    const now = Date.now();
    const days = activeDrilldown.datePreset
      ? DATE_PRESET_DAYS[activeDrilldown.datePreset as DatePreset]
      : null;
    const cutoff = days ? now - days * 24 * 60 * 60 * 1000 : null;

    return filtered.filter((t) => {
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
  }, [activeDrilldown, dateRangeEnd, dateRangeStart, txns]);

  const sortedRules = useMemo(() => {
    return [...rules].sort((a, b) => {
      const priorityDiff = a.priority - b.priority;
      if (priorityDiff !== 0) return priorityDiff;
      const createdDiff =
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      if (createdDiff !== 0) return createdDiff;
      return a.id.localeCompare(b.id);
    });
  }, [rules]);

  const previewRule = useMemo(() => {
    if (!previewRuleId) return null;
    return rules.find((rule) => rule.id === previewRuleId) ?? null;
  }, [previewRuleId, rules]);

  const ruleCategoryOptions = useMemo(
    () => cats.filter((c) => hasValidCategoryMapping(c)),
    [cats]
  );

  const showToast = useCallback((message: string) => {
    setToastMsg(message);
    if (toastTimeoutRef.current) {
      window.clearTimeout(toastTimeoutRef.current);
    }
    toastTimeoutRef.current = window.setTimeout(() => {
      setToastMsg(null);
      setToastAuditId(null);
      toastTimeoutRef.current = null;
    }, 4000);
  }, []);

  const doSave = useCallback(
    async (categoryId: string, source: "manual" | "rule" | "ml") => {
      const txn = selectedTxnRef.current;
      if (!txn) return;
      const category = catsById.get(categoryId);
      if (!hasValidCategoryMapping(category)) {
        setActionErr("Selected category is missing a valid COA mapping.");
        return;
      }

      setActionErr(null);
      setMsg(null);
      setReconciliationHint(null);

      try {
        const res: any = await saveCategorization(businessId, {
          source_event_id: txn.source_event_id,
          category_id: categoryId,
          source,
          confidence: source === "manual" ? 1.0 : Number(txn.confidence ?? 0.75),
        });

        setMsg(
          res?.learned
            ? `Saved. Learned vendor → ${res.learned_system_key ?? ""}. Reloading…`
            : "Saved. Reloading…"
        );
        setToastAuditId(res?.audit_id ?? null);
        showToast("Categorization saved.");
        if (res?.updated === false) {
          setReconciliationHint("Reconciliation hint: New posted transactions may affect signals.");
        }

        await load(); // ✅ ensures next txn shows updated suggestions
        onCategorizationChange?.();
        bumpDataVersion();
      } catch (e: any) {
        setActionErr(e?.message ?? "Save failed");
      }
    },
    [bumpDataVersion, businessId, catsById, load, onCategorizationChange, showToast]
  );

  const doBulkApply = useCallback(
    async (categoryId: string) => {
      const txn = selectedTxnRef.current;
      if (!txn) return;

      const category = catsById.get(categoryId);
      if (!hasValidCategoryMapping(category)) {
        setActionErr("Selected category is missing a valid COA mapping.");
        return;
      }

      if (!txn.merchant_key) {
        setActionErr("No merchant key available for this vendor.");
        return;
      }

      setActionErr(null);
      setMsg(null);
      setReconciliationHint(null);

      try {
        const res = await bulkApplyByMerchantKey(businessId, {
          merchant_key: txn.merchant_key,
          category_id: categoryId,
          source: "bulk",
          confidence: Number(txn.confidence ?? 1.0),
        });

        setMsg(
          `Applied to ${res.matched_events} events (${res.created} new, ${res.updated} updated). Reloading…`
        );
        showToast("Vendor categorization applied.");
        if (res.created > 0) {
          setReconciliationHint("Reconciliation hint: New posted transactions may affect signals.");
        }
        await load();
        onCategorizationChange?.();
        bumpDataVersion();
      } catch (e: any) {
        setActionErr(e?.message ?? "Failed to apply vendor categorization");
      }
    },
    [bumpDataVersion, businessId, catsById, load, onCategorizationChange, showToast]
  );

  const updateRuleEdit = useCallback(
    (rule: CategoryRuleOut, patch: { priority?: string; category_id?: string }) => {
      setRuleEdits((prev) => {
        const existing = prev[rule.id] ?? {
          priority: String(rule.priority),
          category_id: rule.category_id,
        };
        return {
          ...prev,
          [rule.id]: {
            ...existing,
            ...patch,
          },
        };
      });
    },
    []
  );

  const clearRuleEdit = useCallback((ruleId: string) => {
    setRuleEdits((prev) => {
      if (!prev[ruleId]) return prev;
      const next = { ...prev };
      delete next[ruleId];
      return next;
    });
  }, []);

  const saveRuleEdit = useCallback(
    async (rule: CategoryRuleOut) => {
      const edit = ruleEdits[rule.id];
      if (!edit) return;

      const priorityValue = edit.priority.trim();
      const parsedPriority = Number(priorityValue);
      if (!Number.isFinite(parsedPriority)) {
        setRulesErr("Priority must be a number.");
        return;
      }

      const patch: Record<string, any> = {};
      if (parsedPriority !== rule.priority) patch.priority = parsedPriority;
      if (edit.category_id !== rule.category_id) {
        const category = catsById.get(edit.category_id);
        if (!hasValidCategoryMapping(category)) {
          setRulesErr("Rule category is missing a valid COA mapping.");
          return;
        }
        patch.category_id = edit.category_id;
      }

      if (Object.keys(patch).length === 0) {
        clearRuleEdit(rule.id);
        return;
      }

      setRulesErr(null);
      setRulesMsg(null);
      try {
        await updateCategoryRule(businessId, rule.id, patch);
        setRulesMsg("Rule updated.");
        showToast("Rule updated.");
        clearRuleEdit(rule.id);
        await loadRules();
        onCategorizationChange?.();
        bumpDataVersion();
      } catch (e: any) {
        setRulesErr(e?.message ?? "Failed to update rule");
      }
    },
    [
      bumpDataVersion,
      businessId,
      catsById,
      clearRuleEdit,
      loadRules,
      onCategorizationChange,
      ruleEdits,
      showToast,
    ]
  );

  const toggleRuleActive = useCallback(
    async (rule: CategoryRuleOut) => {
      setRulesErr(null);
      setRulesMsg(null);
      try {
        await updateCategoryRule(businessId, rule.id, { active: !rule.active });
        setRulesMsg(rule.active ? "Rule deactivated." : "Rule activated.");
        showToast(rule.active ? "Rule deactivated." : "Rule activated.");
        await loadRules();
        onCategorizationChange?.();
        bumpDataVersion();
      } catch (e: any) {
        setRulesErr(e?.message ?? "Failed to update rule");
      }
    },
    [bumpDataVersion, businessId, loadRules, onCategorizationChange, showToast]
  );

  const deleteRule = useCallback(
    async (rule: CategoryRuleOut) => {
      const ok = window.confirm(`Delete rule "${rule.contains_text}"?`);
      if (!ok) return;
      setRulesErr(null);
      setRulesMsg(null);
      try {
        await deleteCategoryRule(businessId, rule.id);
        setRulesMsg("Rule deleted.");
        showToast("Rule deleted.");
        await loadRules();
        onCategorizationChange?.();
        bumpDataVersion();
      } catch (e: any) {
        setRulesErr(e?.message ?? "Failed to delete rule");
      }
    },
    [bumpDataVersion, businessId, loadRules, onCategorizationChange, showToast]
  );

  const clearPreview = useCallback(() => {
    setPreviewRuleId(null);
    setPreviewData(null);
    setPreviewErr(null);
    setPreviewLoading(false);
  }, []);

  const runRulePreview = useCallback(
    async (rule: CategoryRuleOut) => {
      setPreviewRuleId(rule.id);
      setPreviewLoading(true);
      setPreviewErr(null);
      setPreviewData(null);
      try {
        const res = await previewCategoryRule(businessId, rule.id);
        setPreviewData(res);
      } catch (e: any) {
        setPreviewErr(e?.message ?? "Failed to preview rule");
      } finally {
        setPreviewLoading(false);
      }
    },
    [businessId]
  );

  const applyRuleNow = useCallback(
    async (rule: CategoryRuleOut) => {
      const category = catsById.get(rule.category_id);
      if (!hasValidCategoryMapping(category)) {
        setRulesErr("Rule category is missing a valid COA mapping.");
        return;
      }
      setApplyLoadingRuleId(rule.id);
      setRulesErr(null);
      setRulesMsg(null);
      try {
        const res = await applyCategoryRule(businessId, rule.id);
        setRulesMsg(`Applied rule to ${res.updated} transactions (matched ${res.matched}).`);
        setRules((prev) =>
          prev.map((item) =>
            item.id === rule.id
              ? {
                  ...item,
                  last_run_at: new Date().toISOString(),
                  last_run_updated_count: res.updated,
                }
              : item
          )
        );
        await load();
        await loadRules();
        if (previewRuleId === rule.id) {
          await runRulePreview(rule);
        }
        onCategorizationChange?.();
        bumpDataVersion();
      } catch (e: any) {
        setRulesErr(e?.message ?? "Failed to apply rule");
      } finally {
        setApplyLoadingRuleId(null);
      }
    },
    [
      bumpDataVersion,
      businessId,
      catsById,
      load,
      loadRules,
      onCategorizationChange,
      previewRuleId,
      runRulePreview,
    ]
  );

  const createRuleFromTxn = useCallback(async () => {
    if (!selectedTxn) return;
    const category = catsById.get(selectedCategoryId);
    if (!hasValidCategoryMapping(category)) {
      setCreateRuleErr("Select a category with a valid COA mapping first.");
      return;
    }
    const contains = (selectedTxn.description || "").trim();
    if (!contains) {
      setCreateRuleErr("No description available to build a rule.");
      return;
    }
    setCreateRuleLoading(true);
    setCreateRuleErr(null);
    setRulesMsg(null);
    try {
      const direction =
        selectedTxn.direction === "inflow" || selectedTxn.direction === "outflow"
          ? selectedTxn.direction
          : null;
      await createCategoryRule(businessId, {
        contains_text: contains,
        category_id: selectedCategoryId,
        priority: 100,
        direction,
        account: selectedTxn.account || null,
        active: true,
      });
      setRulesMsg("Rule created from this transaction.");
      showToast("Rule created.");
      await loadRules();
      bumpDataVersion();
    } catch (e: any) {
      setCreateRuleErr(e?.message ?? "Failed to create rule");
    } finally {
      setCreateRuleLoading(false);
    }
  }, [
    bumpDataVersion,
    businessId,
    catsById,
    loadRules,
    selectedCategoryId,
    selectedTxn,
    showToast,
  ]);


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

  useEffect(() => {
    return () => {
      if (toastTimeoutRef.current) {
        window.clearTimeout(toastTimeoutRef.current);
      }
    };
  }, []);

  // On business change, reload
  useEffect(() => {
    load();
  }, [dataVersion, load]);

  useEffect(() => {
    loadRules();
  }, [dataVersion, loadRules]);

  useEffect(() => {
    if (!selectedTxn) return;
    const stillVisible = filteredTxns.some(
      (txn) => txn.source_event_id === selectedTxn.source_event_id
    );
    if (!stillVisible) {
      const nextTxn = filteredTxns[0] ?? null;
      setSelectedTxn(nextTxn);
      setSelectedCategoryId(pickBestCategoryId(nextTxn, cats));
    }
  }, [cats, filteredTxns, pickBestCategoryId, selectedTxn]);

  useEffect(() => {
    if (!urlSourceEventId) return;
    const match = txns.find((txn) => txn.source_event_id === urlSourceEventId) ?? null;
    if (!match) return;
    setSelectedTxn(match);
    setSelectedCategoryId(pickBestCategoryId(match, cats));
    setDetailSourceEventId(match.source_event_id);
  }, [cats, pickBestCategoryId, txns, urlSourceEventId]);

  const reloadAll = useCallback(() => {
    load();
    loadRules();
  }, [load, loadRules]);

  if (invalidBusinessId) {
    return <div className={styles.error}>Invalid business id.</div>;
  }

  if (invalidDateRange) {
    return (
      <div className={styles.error}>
        Invalid date range: {dateRange.start} → {dateRange.end}
      </div>
    );
  }

  if (loading) return <div className={styles.loading}>Loading…</div>;

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        {/* LEFT: txns */}
        <div className={styles.panel}>
          <div className={styles.headerRow}>
            <h3 className={styles.title}>To categorize</h3>
            <div className={styles.headerActions}>
              <button
                className={styles.buttonSecondary}
                onClick={handleAutoCategorize}
                disabled={autoCategorizeRunning}
              >
                Auto-categorize
              </button>
              <button className={styles.buttonSecondary} onClick={reloadAll}>
                Reload
              </button>
            </div>
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
        {vendorErr && (
          <div className={styles.error}>
            Vendor mappings unavailable: {vendorErr}. Categorization still works.
          </div>
        )}
        {missingCoaMappings.length > 0 && (
          <div className={styles.error}>
            Missing COA mapping for {missingCoaMappings.length} categories. Fix Chart of
            Accounts before categorizing.
          </div>
        )}

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

        {cats.length === 0 ? (
          <div className={styles.emptyState}>No categories found. Fix your COA mapping first.</div>
        ) : filteredTxns.length === 0 ? (
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
                <div className={styles.txnTitle}>
                  {normalizeVendorDisplay(
                    t.description,
                    vendorNameByKey.get(t.merchant_key ?? "")?.canonical_name
                  )}
                </div>
                <div className={styles.txnMeta}>
                  {formatTxnDateTime(t.occurred_at)} • {t.account} • {t.direction} •{" "}
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
        {reconciliationHint && (
          <div className={styles.hint}>
            {reconciliationHint}{" "}
            <Link to={`/app/${businessId}/signals`}>Re-run monitoring</Link>.
          </div>
        )}
        {toastMsg && (
          <div className={styles.toast}>
            <span>{toastMsg}</span>
            <Link
              className={styles.toastLink}
              to={`${location.pathname}${toastAuditId ? `?auditId=${encodeURIComponent(toastAuditId)}` : ""}#recent-changes`}
            >
              View in Recent Changes
            </Link>
          </div>
        )}
        {actionErr && <div className={styles.error}>Error: {actionErr}</div>}

        {!selectedTxn ? (
          <div className={styles.noSelection}>Select a transaction.</div>
        ) : (
          <>
            <div className={styles.txnTitle}>
              {normalizeVendorDisplay(
                selectedTxn.description,
                vendorNameByKey.get(selectedTxn.merchant_key ?? "")?.canonical_name
              )}
            </div>
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
                  disabled={!selectedCategoryValid}
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

                <button
                  className={styles.buttonSecondary}
                  disabled={createRuleLoading || !selectedCategoryValid}
                  onClick={createRuleFromTxn}
                >
                  {createRuleLoading ? "Creating rule…" : "Create rule from this"}
                </button>
              </div>
            </div>
          </>
        )}
        </div>
      </div>
      <div className={`${styles.panel} ${styles.rulesPanel}`}>
        <div className={styles.headerRow}>
          <div>
            <h3 className={styles.title}>Rule management</h3>
            <div className={styles.rulesSubtitle}>Manage saved categorization rules.</div>
          </div>
          <button className={styles.buttonSecondary} onClick={loadRules}>
            Refresh rules
          </button>
        </div>

        {rulesMsg && <div className={styles.message}>{rulesMsg}</div>}
        {rulesErr && <div className={styles.error}>Error: {rulesErr}</div>}
        {createRuleErr && <div className={styles.error}>Error: {createRuleErr}</div>}
        {previewRuleId && (
          <div className={styles.previewPanel}>
            <div className={styles.previewHeader}>
              <div>
                <div className={styles.previewTitle}>Rule preview</div>
                <div className={styles.previewMeta}>
                  {previewRule
                    ? `Contains "${previewRule.contains_text}" · Priority ${previewRule.priority}`
                    : "Loading rule details…"}
                </div>
              </div>
              <button className={styles.buttonSecondary} onClick={clearPreview}>
                Close
              </button>
            </div>
            {previewLoading ? (
              <div className={styles.loading}>Loading preview…</div>
            ) : previewErr ? (
              <div className={styles.error}>Error: {previewErr}</div>
            ) : previewData ? (
              <>
                <div className={styles.previewSummary}>
                  <strong>{previewData.matched}</strong> uncategorized transactions match
                  this rule.
                  <div className={styles.previewNote}>
                    Conflicts resolve by priority, then created date, then rule id.
                  </div>
                </div>
                {previewData.samples.length === 0 ? (
                  <div className={styles.emptyState}>No sample matches.</div>
                ) : (
                  <div className={styles.previewTableWrap}>
                    <table className={styles.previewTable}>
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Description</th>
                          <th>Amount</th>
                          <th>Direction</th>
                          <th>Account</th>
                        </tr>
                      </thead>
                      <tbody>
                        {previewData.samples.map((sample) => (
                          <tr key={sample.source_event_id}>
                            <td>{formatTxnDate(sample.occurred_at)}</td>
                            <td>{sample.description}</td>
                            <td>{formatSignedAmount(sample.amount, sample.direction)}</td>
                            <td>{sample.direction}</td>
                            <td>{sample.account || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            ) : null}
          </div>
        )}

        {rulesLoading ? (
          <div className={styles.loading}>Loading rules…</div>
        ) : sortedRules.length === 0 ? (
          <div className={styles.emptyState}>No rules yet.</div>
        ) : (
          <div className={styles.rulesTableWrap}>
            <table className={styles.rulesTable}>
              <thead>
                <tr>
                  <th>Active</th>
                  <th>Priority</th>
                  <th>Contains Text</th>
                  <th>Direction</th>
                  <th>Account</th>
                  <th>Category</th>
                  <th>Last run</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {sortedRules.map((rule) => {
                  const edit = ruleEdits[rule.id];
                  const priorityValue = edit?.priority ?? String(rule.priority);
                  const categoryValue = edit?.category_id ?? rule.category_id;
                  const hasChanges =
                    Number(priorityValue) !== rule.priority || categoryValue !== rule.category_id;
                  const category = catsById.get(rule.category_id);
                  return (
                    <tr key={rule.id}>
                      <td>
                        <label className={styles.toggle}>
                          <input
                            type="checkbox"
                            checked={rule.active}
                            onChange={() => toggleRuleActive(rule)}
                          />
                          <span>{rule.active ? "On" : "Off"}</span>
                        </label>
                      </td>
                      <td>
                        <input
                          type="number"
                          className={styles.ruleInput}
                          value={priorityValue}
                          onChange={(e) => updateRuleEdit(rule, { priority: e.target.value })}
                        />
                      </td>
                      <td className={styles.containsText}>{rule.contains_text}</td>
                      <td>{rule.direction ?? "—"}</td>
                      <td>{rule.account ?? "—"}</td>
                      <td>
                        <select
                          className={styles.ruleSelect}
                          value={categoryValue}
                          onChange={(e) => updateRuleEdit(rule, { category_id: e.target.value })}
                        >
                          {ruleCategoryOptions.map((cat) => (
                            <option key={cat.id} value={cat.id}>
                              {cat.name} — {cat.account_code ? `${cat.account_code} ` : ""}
                              {cat.account_name}
                            </option>
                          ))}
                          {!ruleCategoryOptions.find((cat) => cat.id === rule.category_id) && (
                            <option value={rule.category_id}>
                              {category?.name ?? "Unknown category"}
                            </option>
                          )}
                        </select>
                      </td>
                      <td>{formatLastRun(rule)}</td>
                      <td>{formatTxnDate(rule.created_at)}</td>
                      <td>
                        <div className={styles.buttonRow}>
                          <button
                            className={styles.buttonSecondary}
                            disabled={!hasChanges}
                            onClick={() => saveRuleEdit(rule)}
                          >
                            Save
                          </button>
                          <button
                            className={styles.buttonSecondary}
                            onClick={() => deleteRule(rule)}
                          >
                            Delete
                          </button>
                          <button
                            className={styles.buttonSecondary}
                            onClick={() => runRulePreview(rule)}
                          >
                            {previewRuleId === rule.id && previewLoading ? "Previewing…" : "Preview"}
                          </button>
                          <button
                            className={styles.buttonPrimary}
                            disabled={applyLoadingRuleId === rule.id}
                            onClick={() => applyRuleNow(rule)}
                          >
                            {applyLoadingRuleId === rule.id ? "Applying…" : "Apply now"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div id="recent-changes">
        <RecentChangesPanel businessId={businessId} dataVersion={dataVersion} />
      </div>

      <TransactionDetailDrawer
        open={Boolean(detailSourceEventId)}
        businessId={businessId}
        sourceEventId={detailSourceEventId}
        onClose={handleDrawerClose}
      />
    </div>
  );
}
