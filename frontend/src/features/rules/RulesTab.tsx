import { useCallback, useEffect, useMemo, useState } from "react";
import {
  applyCategoryRule,
  getCategories,
  listCategoryRules,
  previewCategoryRule,
  type CategoryOut,
  type CategoryRuleOut,
  type CategoryRulePreviewOut,
} from "../../api/categorize";
import { useAppState } from "../../app/state/appState";
import { isBusinessIdValid } from "../../utils/businessId";
import { hasValidCategoryMapping } from "../../utils/categories";
import styles from "./RulesTab.module.css";

export default function RulesTab({ businessId }: { businessId: string }) {
  const { dateRange, dataVersion, bumpDataVersion } = useAppState();
  const [rules, setRules] = useState<CategoryRuleOut[]>([]);
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [preview, setPreview] = useState<CategoryRulePreviewOut | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const [applyRuleId, setApplyRuleId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const catsById = useMemo(() => {
    const map = new Map<string, CategoryOut>();
    categories.forEach((cat) => map.set(cat.id, cat));
    return map;
  }, [categories]);

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

  const load = useCallback(async () => {
    if (!businessId || !isBusinessIdValid(businessId)) {
      setErr("Invalid business id.");
      return;
    }
    setLoading(true);
    setErr(null);
    setMessage(null);
    try {
      const [rulesData, categoriesData] = await Promise.all([
        listCategoryRules(businessId),
        getCategories(businessId),
      ]);
      setRules(rulesData);
      setCategories(categoriesData);
    } catch (e: any) {
      console.error("[rules] fetch failed", {
        businessId,
        dateRange,
        url: `/categorize/${businessId}/rules`,
        error: e?.message ?? e,
      });
      setErr(e?.message ?? "Failed to load rules");
    } finally {
      setLoading(false);
    }
  }, [businessId, dateRange]);

  useEffect(() => {
    load();
  }, [dataVersion, load]);

  const runPreview = useCallback(
    async (rule: CategoryRuleOut) => {
      setPreviewLoading(true);
      setPreviewErr(null);
      setPreview(null);
      try {
        const data = await previewCategoryRule(businessId, rule.id);
        setPreview(data);
      } catch (e: any) {
        console.error("[rules] preview failed", {
          businessId,
          dateRange,
          url: `/categorize/${businessId}/rules/${rule.id}/preview`,
          error: e?.message ?? e,
        });
        setPreviewErr(e?.message ?? "Failed to preview rule");
      } finally {
        setPreviewLoading(false);
      }
    },
    [businessId, dateRange]
  );

  const applyRule = useCallback(
    async (rule: CategoryRuleOut) => {
      const category = catsById.get(rule.category_id);
      if (!hasValidCategoryMapping(category)) {
        setErr("Rule category is missing a valid COA mapping.");
        return;
      }
      setApplyRuleId(rule.id);
      setErr(null);
      setMessage(null);
      try {
        const res = await applyCategoryRule(businessId, rule.id);
        setMessage(`Applied rule to ${res.updated} transactions (matched ${res.matched}).`);
        bumpDataVersion();
        await load();
        if (preview?.rule_id === rule.id) {
          await runPreview(rule);
        }
      } catch (e: any) {
        console.error("[rules] apply failed", {
          businessId,
          dateRange,
          url: `/categorize/${businessId}/rules/${rule.id}/apply`,
          error: e?.message ?? e,
        });
        setErr(e?.message ?? "Failed to apply rule");
      } finally {
        setApplyRuleId(null);
      }
    },
    [bumpDataVersion, businessId, catsById, dateRange, load, preview?.rule_id, runPreview]
  );

  if (loading) {
    return <div className={styles.loading}>Loading rules…</div>;
  }

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div>
          <h3 className={styles.title}>Rules</h3>
          <div className={styles.subtitle}>Preview and apply automation rules.</div>
        </div>
        <button className={styles.buttonSecondary} onClick={load} type="button">
          Refresh
        </button>
      </div>

      {message && <div className={styles.message}>{message}</div>}
      {err && <div className={styles.error}>Error: {err}</div>}

      {sortedRules.length === 0 ? (
        <div className={styles.empty}>No rules yet.</div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Priority</th>
                <th>Contains</th>
                <th>Direction</th>
                <th>Account</th>
                <th>Category</th>
                <th>Last run</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sortedRules.map((rule) => {
                const category = catsById.get(rule.category_id);
                return (
                  <tr key={rule.id}>
                    <td>{rule.priority}</td>
                    <td>{rule.contains_text}</td>
                    <td>{rule.direction ?? "—"}</td>
                    <td>{rule.account ?? "—"}</td>
                    <td>
                      {category?.name ?? "Unknown"}{" "}
                      {!hasValidCategoryMapping(category) && (
                        <span className={styles.badge}>Missing mapping</span>
                      )}
                    </td>
                    <td>
                      {rule.last_run_at
                        ? new Date(rule.last_run_at).toLocaleString()
                        : "Never"}
                    </td>
                    <td>
                      <div className={styles.buttonRow}>
                        <button
                          className={styles.buttonSecondary}
                          onClick={() => runPreview(rule)}
                          type="button"
                        >
                          Preview
                        </button>
                        <button
                          className={styles.buttonPrimary}
                          onClick={() => applyRule(rule)}
                          disabled={applyRuleId === rule.id}
                          type="button"
                        >
                          {applyRuleId === rule.id ? "Applying…" : "Apply"}
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

      {preview && (
        <div className={styles.previewPanel}>
          <div className={styles.previewHeader}>
            <div>
              <div className={styles.previewTitle}>Rule preview</div>
              <div className={styles.previewMeta}>
                Matched {preview.matched} uncategorized transactions.
              </div>
            </div>
            <button
              className={styles.buttonSecondary}
              onClick={() => setPreview(null)}
              type="button"
            >
              Close
            </button>
          </div>
          {previewLoading && <div className={styles.loading}>Loading preview…</div>}
          {previewErr && <div className={styles.error}>Error: {previewErr}</div>}
          {!previewLoading && preview.samples.length === 0 && (
            <div className={styles.empty}>No sample matches.</div>
          )}
          {!previewLoading && preview.samples.length > 0 && (
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
                  {preview.samples.map((sample) => (
                    <tr key={sample.source_event_id}>
                      <td>{new Date(sample.occurred_at).toLocaleDateString()}</td>
                      <td>{sample.description}</td>
                      <td>{sample.amount}</td>
                      <td>{sample.direction}</td>
                      <td>{sample.account || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
