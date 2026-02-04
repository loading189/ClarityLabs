// src/components/detail/SignalDetail.tsx
import { useEffect, useState } from "react";
import type { HealthSignal, HealthSignalStatus } from "../../types";
import {
  bulkApplyByMerchantKey,
  createCategoryRule,
  getCategorizeMetrics,
  setBrainVendor,
} from "../../api/categorize";
import { updateSignalStatus } from "../../api/signals";
import styles from "../../features/signals/HealthTab.module.css";

type Props = {
  businessId: string;
  signal: HealthSignal;
  onNavigate?: (
    target: "transactions" | "trends" | "categorize" | "ledger",
    drilldown?: Record<string, any> | null
  ) => void;
  onAfterAction?: () => void;
};

function toPercent(part?: number | null, total?: number | null) {
  const safePart = Number(part ?? 0);
  const safeTotal = Number(total ?? 0);
  if (!Number.isFinite(safePart) || !Number.isFinite(safeTotal) || safeTotal <= 0) {
    return null;
  }
  return Math.round((safePart / safeTotal) * 100);
}

export default function SignalDetail({ businessId, signal, onNavigate, onAfterAction }: Props) {
  const [status, setStatus] = useState<HealthSignalStatus>(signal.status ?? "open");
  const [note, setNote] = useState(signal.resolution_note ?? "");
  const [statusSaving, setStatusSaving] = useState(false);
  const [statusErr, setStatusErr] = useState<string | null>(null);
  const [impactLine, setImpactLine] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    setStatus(signal.status ?? "open");
    setNote(signal.resolution_note ?? "");
    setImpactLine(null);
    setActionErr(null);
  }, [signal.id, signal.status, signal.resolution_note]);

  const fixSuggestions = signal.fix_suggestions ?? [];
  const statusLabel = String(signal.status ?? "open").replace(/_/g, " ");

  const drilldownButtons = (signal.drilldowns ?? []).map((d, idx) => {
    const label = d.label ?? "Open drilldown";
    const payload = d.payload ?? null;
    return (
      <button
        key={`${d.target}-${idx}`}
        className={styles.actionButton}
        onClick={() => onNavigate?.(d.target, payload as Record<string, any> | null)}
        type="button"
      >
        {label}
      </button>
    );
  });

  async function handleStatusSave() {
    if (!businessId) return;
    setStatusSaving(true);
    setStatusErr(null);
    try {
      await updateSignalStatus(
        businessId,
        signal.id,
        {
          status,
          reason: note?.trim() || null,
        },
        { mode: "demo" }
      );
      onAfterAction?.();
    } catch (e: any) {
      setStatusErr(e?.message ?? "Failed to update signal status");
    } finally {
      setStatusSaving(false);
    }
  }

  function buildImpactLine(before: any, after: any) {
    if (!before || !after) return null;
    if (signal.id === "rule_coverage_low") {
      const beforePct = toPercent(before.suggestion_coverage, before.total_events);
      const afterPct = toPercent(after.suggestion_coverage, after.total_events);
      if (beforePct != null && afterPct != null) {
        return `Suggestion coverage: ${beforePct}% → ${afterPct}%`;
      }
      return `Suggestion coverage: ${before.suggestion_coverage} → ${after.suggestion_coverage}`;
    }
    if (signal.id === "new_unknown_vendors") {
      const beforePct = toPercent(before.brain_coverage, before.total_events);
      const afterPct = toPercent(after.brain_coverage, after.total_events);
      if (beforePct != null && afterPct != null) {
        return `Brain coverage: ${beforePct}% → ${afterPct}%`;
      }
      return `Brain coverage: ${before.brain_coverage} → ${after.brain_coverage}`;
    }
    return `Uncategorized: ${before.uncategorized} → ${after.uncategorized}`;
  }

  async function handleFixAction(
    kind: "rule" | "vendor" | "bulk",
    suggestion: (typeof fixSuggestions)[number]
  ) {
    if (!businessId || !suggestion?.suggested_category_id || !suggestion.merchant_key) return;
    setActionLoading(true);
    setActionErr(null);
    try {
      const before = await getCategorizeMetrics(businessId);
      if (kind === "rule") {
        await createCategoryRule(businessId, {
          contains_text:
            suggestion.contains_text ||
            suggestion.sample_description ||
            suggestion.merchant_key,
          category_id: suggestion.suggested_category_id,
          direction: suggestion.direction as "inflow" | "outflow" | null,
          account: suggestion.account,
          priority: 90,
        });
      } else if (kind === "vendor") {
        await setBrainVendor(businessId, {
          merchant_key: suggestion.merchant_key,
          category_id: suggestion.suggested_category_id,
          canonical_name: suggestion.sample_description || undefined,
        });
      } else {
        await bulkApplyByMerchantKey(businessId, {
          merchant_key: suggestion.merchant_key,
          category_id: suggestion.suggested_category_id,
        });
      }
      onAfterAction?.();
      const after = await getCategorizeMetrics(businessId);
      setImpactLine(buildImpactLine(before, after));
    } catch (e: any) {
      setActionErr(e?.message ?? "Fix action failed");
    } finally {
      setActionLoading(false);
    }
  }

  return (
    <div className={styles.signalDetail}>
      <div className={styles.signalDetailHeader}>
        <div>
          <div className={styles.signalDetailTitle}>{signal.title}</div>
          <div className={styles.signalDetailMeta}>
            <span
              className={`${styles.pill} ${
                signal.severity === "red"
                  ? styles.pillRed
                  : signal.severity === "yellow"
                  ? styles.pillYellow
                  : styles.pillGreen
              }`}
            >
              {String(signal.severity ?? "green").toUpperCase()}
            </span>
            <span className={`${styles.pill} ${styles.pillSoft}`}>{statusLabel}</span>
            {signal.updated_at && <span className={styles.pill}>Updated {signal.updated_at}</span>}
            {signal.resolved_at && <span className={styles.pill}>Resolved {signal.resolved_at}</span>}
          </div>
        </div>
      </div>

      <div className={styles.signalDetailMessage}>{signal.short_summary}</div>

      <div className={styles.signalDetailBlock}>
        <div className={styles.signalDetailLabel}>Resolution status</div>
        <div className={styles.signalStatusRow}>
          <select
            className={styles.selectInput}
            value={status}
            onChange={(event) => setStatus(event.target.value as HealthSignalStatus)}
          >
            <option value="open">Open</option>
            <option value="in_progress">In progress</option>
            <option value="resolved">Resolved</option>
            <option value="ignored">Ignored</option>
          </select>
          <button
            className={styles.actionButton}
            onClick={handleStatusSave}
            disabled={statusSaving}
            type="button"
          >
            {statusSaving ? "Saving…" : "Save status"}
          </button>
        </div>
        <textarea
          className={styles.textArea}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Add a resolution note (optional)"
          rows={3}
        />
        {statusErr && <div className={styles.inlineError}>{statusErr}</div>}
      </div>

      <div className={styles.signalDetailBlock}>
        <div className={styles.signalDetailLabel}>Why it matters</div>
        <div className={styles.signalDetailBody}>{signal.why_it_matters}</div>
      </div>

      <div className={styles.signalDetailBlock}>
        <div className={styles.signalDetailLabel}>Evidence</div>
        <div className={styles.signalEvidenceStack}>
          {(signal.evidence ?? []).map((ev, idx) => (
            <div key={idx} className={styles.signalEvidenceCard}>
              <div className={styles.signalEvidenceHeader}>
                <div className={styles.signalEvidenceTitle}>
                  {ev.date_range?.label || "Period"}
                </div>
                <div className={styles.signalEvidenceRange}>
                  {ev.date_range?.start} → {ev.date_range?.end}
                </div>
              </div>
              <div className={styles.signalEvidenceMetrics}>
                {Object.entries(ev.metrics ?? {}).map(([key, value]) => (
                  <div key={key} className={styles.signalEvidenceMetric}>
                    <div className={styles.signalEvidenceKey}>{key}</div>
                    <div className={styles.signalEvidenceValue}>{String(value)}</div>
                  </div>
                ))}
              </div>
              {ev.examples && ev.examples.length > 0 && (
                <div className={styles.signalEvidenceExamples}>
                  <div className={styles.signalEvidenceLabel}>Example transactions</div>
                  <div className={styles.signalEvidenceTable}>
                    {ev.examples.map((ex: any, i: number) => (
                      <div key={`${ex.source_event_id}-${i}`} className={styles.signalEvidenceRow}>
                        <div className={styles.noWrap}>{ex.date ?? ex.occurred_at ?? "—"}</div>
                        <div className={styles.signalEvidenceDesc}>
                          {ex.description ?? "—"}
                          <div className={styles.signalEvidenceSub}>
                            event {String(ex.source_event_id ?? "").slice(-6)}
                          </div>
                        </div>
                        <div className={styles.alignRight}>
                          {ex.amount != null
                            ? `${ex.direction === "outflow" ? "-" : ""}$${Number(
                                Math.abs(ex.amount)
                              ).toFixed(2)}`
                            : "—"}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {fixSuggestions.length > 0 && (
        <div className={styles.signalDetailBlock}>
          <div className={styles.signalDetailLabel}>Fix it</div>
          <div className={styles.signalFixList}>
            {fixSuggestions.map((suggestion) => (
              <div key={`${suggestion.merchant_key}-${suggestion.suggested_category_id}`} className={styles.signalFixCard}>
                <div className={styles.signalFixHeader}>
                  <div className={styles.signalFixTitle}>{suggestion.merchant_key}</div>
                  <div className={styles.signalFixSub}>
                    {suggestion.suggested_category_name}
                    {suggestion.count ? ` • ${suggestion.count} txns` : ""}
                  </div>
                </div>
                {suggestion.sample_description && (
                  <div className={styles.signalFixMeta}>{suggestion.sample_description}</div>
                )}
                <div className={styles.signalFixActions}>
                  <button
                    className={styles.actionButton}
                    onClick={() => handleFixAction("rule", suggestion)}
                    disabled={actionLoading || !suggestion.suggested_category_id}
                    type="button"
                  >
                    Create rule
                  </button>
                  <button
                    className={styles.actionButton}
                    onClick={() => handleFixAction("vendor", suggestion)}
                    disabled={actionLoading || !suggestion.suggested_category_id}
                    type="button"
                  >
                    Set vendor memory
                  </button>
                  <button
                    className={styles.actionButton}
                    onClick={() => handleFixAction("bulk", suggestion)}
                    disabled={actionLoading || !suggestion.suggested_category_id}
                    type="button"
                  >
                    Bulk apply
                  </button>
                </div>
              </div>
            ))}
          </div>
          {actionErr && <div className={styles.inlineError}>{actionErr}</div>}
          {impactLine && <div className={styles.signalImpactLine}>{impactLine}</div>}
        </div>
      )}

      {drilldownButtons.length > 0 && (
        <div className={styles.signalActions}>{drilldownButtons}</div>
      )}
    </div>
  );
}
