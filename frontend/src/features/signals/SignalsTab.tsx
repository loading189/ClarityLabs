import { useEffect, useMemo, useState } from "react";
import { getCategorizeMetrics, type CategorizeMetricsOut } from "../../api/categorize";
import type { BusinessDetail, HealthSignal } from "../../types";
import SignalGrid from "../../components/DetailPanel/SignalGrid";
import SignalDetail from "../../components/DetailPanel/SignalDetail";
import styles from "./HealthTab.module.css";
import { logRefresh } from "../../utils/refreshLog";

function sevRank(sev?: string) {
  if (sev === "red") return 3;
  if (sev === "yellow") return 2;
  return 1;
}

function toPercent(part?: number | null, total?: number | null) {
  const safePart = Number(part ?? 0);
  const safeTotal = Number(total ?? 0);
  if (!Number.isFinite(safePart) || !Number.isFinite(safeTotal) || safeTotal <= 0) {
    return null;
  }
  return Math.round((safePart / safeTotal) * 100);
}

type HealthNavigateTarget = "transactions" | "trends" | "categorize" | "ledger";

export default function SignalsTab({
  detail,
  refreshToken,
  onNavigate,
  onAfterAction,
}: {
  detail: BusinessDetail;
  refreshToken?: number;
  onNavigate?: (target: HealthNavigateTarget, drilldown?: Record<string, any> | null) => void;
  onAfterAction?: () => void;
}) {
  const signals = (detail.health_signals ?? []) as HealthSignal[];

  // Sort once for stable UI behavior
  const sorted = useMemo(() => {
    return [...signals].sort((a, b) => {
      const r = sevRank(b.severity) - sevRank(a.severity);
      if (r !== 0) return r;
      const aUpdated = a.updated_at ?? "";
      const bUpdated = b.updated_at ?? "";
      if (aUpdated !== bUpdated) {
        return bUpdated.localeCompare(aUpdated);
      }
      return String(a.id).localeCompare(String(b.id));
    });
  }, [signals]);

  // Keep selection stable across renders AND reset when business changes
  const [selectedKey, setSelectedKey] = useState<string | null>(sorted[0]?.id ?? null);

  // When switching businesses, default to the top signal for that business
  useEffect(() => {
    setSelectedKey(sorted[0]?.id ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail.business_id]); // only when business changes

  // If keys change (signals recomputed), keep selection valid
  const selected = useMemo(() => {
    if (!sorted.length) return null;
    return sorted.find((s) => s.id === selectedKey) ?? sorted[0] ?? null;
  }, [sorted, selectedKey]);

  const [metrics, setMetrics] = useState<CategorizeMetricsOut | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [metricsErr, setMetricsErr] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function loadMetrics() {
      setMetricsLoading(true);
      setMetricsErr(null);
      try {
        logRefresh("health", "categorize-metrics");
        const data = await getCategorizeMetrics(detail.business_id);
        if (!active) return;
        setMetrics(data);
      } catch (e: any) {
        if (!active) return;
        setMetricsErr(e?.message ?? "Failed to load categorization metrics");
      } finally {
        if (active) setMetricsLoading(false);
      }
    }

    if (detail.business_id) {
      loadMetrics();
    }

    return () => {
      active = false;
    };
  }, [detail.business_id, refreshToken]);

  const redSignals = useMemo(
    () => sorted.filter((s) => s.severity === "red").length,
    [sorted]
  );
  const yellowSignals = useMemo(
    () => sorted.filter((s) => s.severity === "yellow").length,
    [sorted]
  );

  const categorizedPercent = useMemo(() => {
    if (!metrics) return null;
    return toPercent(metrics.posted, metrics.total_events);
  }, [metrics]);

  const remainingPercent = useMemo(() => {
    if (!metrics) return null;
    return toPercent(metrics.uncategorized, metrics.total_events);
  }, [metrics]);

  const suggestionPercent = useMemo(() => {
    if (!metrics) return null;
    const denom = Math.max(metrics.uncategorized, metrics.total_events);
    return toPercent(metrics.suggestion_coverage, denom);
  }, [metrics]);

  const brainPercent = useMemo(() => {
    if (!metrics) return null;
    return toPercent(metrics.brain_coverage, metrics.total_events);
  }, [metrics]);

  const lastLedgerBalance = useMemo(() => {
    const rows = detail.ledger_preview ?? [];
    if (!rows.length) return null;
    const last = rows[rows.length - 1];
    const balance = Number(last?.balance);
    if (!Number.isFinite(balance)) return null;
    return balance;
  }, [detail.ledger_preview]);

  const summaryTiles = [
    {
      label: "Health score",
      value: detail.health_score ?? null,
      hint: detail.risk ? `Risk: ${detail.risk}` : null,
    },
    {
      label: "Signals (red / yellow)",
      value: `${redSignals} / ${yellowSignals}`,
      hint: `${sorted.length} total`,
    },
    {
      label: "Uncategorized remaining",
      value: metrics?.uncategorized ?? null,
      hint: metrics ? `${metrics.posted} posted` : null,
      action: {
        label: "Review",
        onClick: () => onNavigate?.("categorize"),
      },
    },
    {
      label: "Suggestion coverage",
      value: suggestionPercent != null ? `${suggestionPercent}%` : null,
      hint: metrics ? `${metrics.suggestion_coverage} suggested` : null,
    },
    {
      label: "Brain coverage",
      value: brainPercent != null ? `${brainPercent}%` : null,
      hint: metrics ? `${metrics.brain_coverage} learned` : null,
    },
    {
      label: "Latest balance",
      value: lastLedgerBalance != null ? `$${lastLedgerBalance.toFixed(2)}` : null,
      hint: detail.ledger_preview?.length ? "Ledger preview" : null,
    },
  ];

  return (
    <div className={styles.healthTab}>
      <div className={styles.healthHeader}>
        <div>
          <h3 className={styles.healthTitle}>Health</h3>
          <div className={styles.healthSubtitle}>
            Signals and categorization health for {detail.name ?? "this business"}.
          </div>
        </div>
        <div className={styles.healthActions}>
          <button
            className={styles.actionButton}
            onClick={() => onNavigate?.("transactions", { date_preset: "30d" })}
          >
            View transactions
          </button>
          <button className={styles.actionButton} onClick={() => onNavigate?.("trends")}>
            View trends
          </button>
        </div>
      </div>

      <div className={styles.summaryPanel}>
        <div className={styles.summaryHeader}>
          <div>
            <div className={styles.summaryTitle}>Summary</div>
            <div className={styles.summarySub}>Snapshot across key health indicators.</div>
          </div>
          <div className={styles.summaryStatus}>
            {metricsLoading && "Loading categorization metrics…"}
          </div>
        </div>
        <div className={styles.summaryGrid}>
          {summaryTiles.map((tile) => (
            <div key={tile.label} className={styles.summaryTile}>
              <div className={styles.tileLabel}>{tile.label}</div>
              <div className={styles.tileValue}>{tile.value ?? "—"}</div>
              {tile.hint && <div className={styles.tileHint}>{tile.hint}</div>}
              {tile.action && (
                <button className={styles.tileAction} onClick={tile.action.onClick}>
                  {tile.action.label}
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className={styles.dataQualityCard}>
        <div className={styles.dataQualityHeader}>
          <div>
            <div className={styles.dataQualityTitle}>Data quality</div>
            <div className={styles.dataQualitySub}>
              Keep transactions categorized so health and trends stay reliable.
            </div>
          </div>
          <div className={styles.dataQualityActions}>
            <button className={styles.actionButton} onClick={() => onNavigate?.("categorize")}>
              Categorize now
            </button>
            <button
              className={styles.actionButton}
              onClick={() => onNavigate?.("transactions", { category_id: "uncategorized" })}
            >
              View uncategorized
            </button>
          </div>
        </div>
        {metricsErr && <div className={styles.inlineError}>Metrics unavailable: {metricsErr}</div>}
        {!metricsErr && metricsLoading && (
          <div className={styles.inlineMuted}>Loading categorization metrics…</div>
        )}
        <div className={styles.dataQualityGrid}>
          <div className={styles.dataQualityMetric}>
            <div className={styles.dataQualityLabel}>Categorized</div>
            <div className={styles.dataQualityValue}>
              {categorizedPercent != null ? `${categorizedPercent}%` : "—"}
            </div>
            <div className={styles.dataQualityHint}>
              {metrics ? `${metrics.posted} of ${metrics.total_events} events` : "—"}
            </div>
            {categorizedPercent != null && (
              <div className={styles.progressTrack}>
                <div className={styles.progressFill} style={{ width: `${categorizedPercent}%` }} />
              </div>
            )}
          </div>
          <div className={styles.dataQualityMetric}>
            <div className={styles.dataQualityLabel}>Remaining</div>
            <div className={styles.dataQualityValue}>{metrics ? metrics.uncategorized : "—"}</div>
            <div className={styles.dataQualityHint}>Uncategorized transactions</div>
            {remainingPercent != null && (
              <div className={styles.progressTrack}>
                <div className={styles.progressFill} style={{ width: `${remainingPercent}%` }} />
              </div>
            )}
          </div>
          <div className={styles.dataQualityMetric}>
            <div className={styles.dataQualityLabel}>Suggestion coverage</div>
            <div className={styles.dataQualityValue}>
              {suggestionPercent != null ? `${suggestionPercent}%` : "—"}
            </div>
            <div className={styles.dataQualityHint}>
              {metrics ? `${metrics.suggestion_coverage} suggestions` : "—"}
            </div>
            {suggestionPercent != null && (
              <div className={styles.progressTrack}>
                <div className={styles.progressFill} style={{ width: `${suggestionPercent}%` }} />
              </div>
            )}
          </div>
          <div className={styles.dataQualityMetric}>
            <div className={styles.dataQualityLabel}>Brain coverage</div>
            <div className={styles.dataQualityValue}>
              {metrics ? metrics.brain_coverage : "—"}
            </div>
            <div className={styles.dataQualityHint}>Vendors with memory</div>
          </div>
        </div>
      </div>

      {sorted.length === 0 ? (
        <div className={styles.emptyState}>
          No signals yet — <a href={`/app/${detail.business_id}/admin/simulator`}>Seed demo data</a>.
        </div>
      ) : (
        <div className={styles.signalDashboardLayout}>
          <SignalGrid
            signals={sorted}
            selectedKey={selectedKey}
            onSelect={(s) => setSelectedKey(s.id)}
          />

          {/* Pass businessId so SignalDetail can fetch related transactions via evidence_refs */}
          {selected && (
            <SignalDetail
              businessId={detail.business_id}
              signal={selected}
              onNavigate={(target, drilldown) => onNavigate?.(target, drilldown)}
              onAfterAction={onAfterAction}
            />
          )}
        </div>
      )}

      {detail.ledger_preview && detail.ledger_preview.length > 0 && (
        <div className={styles.ledgerPreview}>
          <div className={styles.ledgerTitle}>Ledger preview</div>
          <div className={styles.ledgerTable}>
            {detail.ledger_preview.slice(0, 8).map((row: any, i: number) => (
              <div key={i} className={styles.ledgerRow}>
                <div>{String(row.date ?? "")}</div>
                <div className={styles.ledgerDesc}>{String(row.description ?? "")}</div>
                <div className={styles.alignRight}>
                  {row.balance != null ? `$${Number(row.balance).toFixed(2)}` : ""}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
