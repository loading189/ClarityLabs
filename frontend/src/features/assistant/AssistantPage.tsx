import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  getSignalExplain,
  listSignalStates,
  updateSignalStatus,
  type SignalExplainOut,
  type SignalState,
  type SignalStatus,
} from "../../api/signals";
import { fetchHealthScore, type HealthScoreOut } from "../../api/healthScore";
import { useAppState } from "../../app/state/appState";
import { ledgerPath } from "../../app/routes/routeUtils";
import type { FilterState } from "../../app/filters/filters";
import HealthScoreBreakdownDrawer from "../../components/health-score/HealthScoreBreakdownDrawer";
import LedgerTraceDrawer from "../../components/ledger/LedgerTraceDrawer";
import styles from "./AssistantPage.module.css";

type ActionOption = {
  label: string;
  status: SignalStatus;
};

const ACTIONS: ActionOption[] = [
  { label: "Acknowledge", status: "in_progress" },
  { label: "Snooze", status: "ignored" },
  { label: "Resolve", status: "resolved" },
];

function formatDate(value?: string | null) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString();
}

function sortSignals(a: SignalState, b: SignalState) {
  const aTime = a.updated_at ? new Date(a.updated_at).getTime() : 0;
  const bTime = b.updated_at ? new Date(b.updated_at).getTime() : 0;
  if (aTime !== bTime) {
    return bTime - aTime;
  }
  return (a.id ?? "").localeCompare(b.id ?? "");
}

function formatDomainLabel(domain?: string | null) {
  if (!domain) return "—";
  return domain.charAt(0).toUpperCase() + domain.slice(1);
}

function buildLedgerFilters(
  anchors: SignalExplainOut["evidence"][number]["anchors"]
): FilterState | null {
  if (!anchors) return null;
  const filters: FilterState = {};
  if (anchors.date_start) filters.start = anchors.date_start;
  if (anchors.date_end) filters.end = anchors.date_end;
  if (anchors.category) filters.category = anchors.category;
  if (anchors.vendor) filters.q = anchors.vendor;
  if (anchors.txn_ids && anchors.txn_ids.length > 0) {
    filters.q = anchors.txn_ids.join(" ");
  }
  return Object.keys(filters).length > 0 ? filters : null;
}

export default function AssistantPage() {
  const { businessId: businessIdParam } = useParams();
  const [searchParams] = useSearchParams();
  const businessId =
    businessIdParam?.trim() || searchParams.get("businessId")?.trim() || "";
  const initialSignalId = searchParams.get("signalId")?.trim() || null;
  const { setActiveBusinessId } = useAppState();

  const [signals, setSignals] = useState<SignalState[]>([]);
  const [signalsLoading, setSignalsLoading] = useState(false);
  const [signalsErr, setSignalsErr] = useState<string | null>(null);
  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(initialSignalId);
  const [explain, setExplain] = useState<SignalExplainOut | null>(null);
  const [explainLoading, setExplainLoading] = useState(false);
  const [explainErr, setExplainErr] = useState<string | null>(null);
  const [healthScore, setHealthScore] = useState<HealthScoreOut | null>(null);
  const [healthScoreLoading, setHealthScoreLoading] = useState(false);
  const [healthScoreErr, setHealthScoreErr] = useState<string | null>(null);
  const [breakdownOpen, setBreakdownOpen] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  const [traceAnchors, setTraceAnchors] = useState<
    SignalExplainOut["evidence"][number]["anchors"] | null
  >(null);
  const [activeAction, setActiveAction] = useState<ActionOption | null>(null);
  const [actor, setActor] = useState("");
  const [reason, setReason] = useState("");
  const [actionSaving, setActionSaving] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);

  useEffect(() => {
    setActiveBusinessId(businessId || null);
  }, [businessId, setActiveBusinessId]);

  useEffect(() => {
    if (initialSignalId) {
      setSelectedSignalId(initialSignalId);
    }
  }, [initialSignalId]);

  const loadSignals = useCallback(async () => {
    if (!businessId) return;
    setSignalsLoading(true);
    setSignalsErr(null);
    try {
      const data = await listSignalStates(businessId);
      setSignals(data.signals ?? []);
    } catch (e: any) {
      setSignalsErr(e?.message ?? "Failed to load signals");
    } finally {
      setSignalsLoading(false);
    }
  }, [businessId]);

  const loadHealthScore = useCallback(async () => {
    if (!businessId) return;
    setHealthScoreLoading(true);
    setHealthScoreErr(null);
    try {
      const data = await fetchHealthScore(businessId);
      setHealthScore(data);
    } catch (e: any) {
      setHealthScoreErr(e?.message ?? "Failed to load health score");
    } finally {
      setHealthScoreLoading(false);
    }
  }, [businessId]);

  const loadExplain = useCallback(
    async (signalId: string) => {
      if (!businessId || !signalId) return;
      setExplainLoading(true);
      setExplainErr(null);
      try {
        const data = await getSignalExplain(businessId, signalId);
        setExplain(data);
      } catch (e: any) {
        setExplainErr(e?.message ?? "Failed to load explain data");
      } finally {
        setExplainLoading(false);
      }
    },
    [businessId]
  );

  useEffect(() => {
    loadSignals();
    loadHealthScore();
  }, [loadHealthScore, loadSignals]);

  useEffect(() => {
    if (!selectedSignalId) {
      setExplain(null);
      return;
    }
    loadExplain(selectedSignalId);
  }, [loadExplain, selectedSignalId]);

  const activeAlerts = useMemo(() => {
    return signals.filter(
      (signal) => signal.status !== "resolved" && signal.status !== "ignored"
    );
  }, [signals]);

  const alertCount = activeAlerts.length;
  const alertCountsBySeverity = useMemo(() => {
    return activeAlerts.reduce<Record<string, number>>((acc, signal) => {
      const key = signal.severity ?? "unknown";
      acc[key] = (acc[key] ?? 0) + 1;
      return acc;
    }, {});
  }, [activeAlerts]);

  const signalTitleById = useMemo(() => {
    return new Map(signals.map((signal) => [signal.id, signal.title ?? signal.id]));
  }, [signals]);

  const topAlerts = useMemo(() => {
    return [...activeAlerts].sort(sortSignals).slice(0, 10);
  }, [activeAlerts]);

  const handleSelectSignal = (signalId: string) => {
    setSelectedSignalId(signalId);
    setActiveAction(null);
    setActionMsg(null);
    setActionErr(null);
  };

  const handleOpenTrace = (
    anchors: SignalExplainOut["evidence"][number]["anchors"] | null
  ) => {
    setTraceAnchors(anchors);
    setTraceOpen(true);
  };

  const handleActionSubmit = async () => {
    if (!businessId || !selectedSignalId || !activeAction) return;
    if (!actor.trim() || !reason.trim()) return;
    setActionSaving(true);
    setActionErr(null);
    setActionMsg(null);
    try {
      const result = await updateSignalStatus(businessId, selectedSignalId, {
        status: activeAction.status,
        actor: actor.trim(),
        reason: reason.trim(),
      });
      setActionMsg(
        `Status updated to ${result.status.replace(/_/g, " ")} (audit ${result.audit_id}).`
      );
      setActiveAction(null);
      setActor("");
      setReason("");
      await loadSignals();
      await loadHealthScore();
      await loadExplain(selectedSignalId);
    } catch (e: any) {
      setActionErr(e?.message ?? "Failed to update status");
    } finally {
      setActionSaving(false);
    }
  };

  if (!businessId) {
    return (
      <div className={styles.emptyState}>
        <h2>Assistant</h2>
        <p>Select a business to start the assistant experience.</p>
        <Link to="/app/select">Go to business picker</Link>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.contextPanel}>
        <div className={styles.sectionHeader}>
          <div>
            <div className={styles.sectionTitle}>Context</div>
            <div className={styles.sectionSubtitle}>Current alert landscape.</div>
          </div>
          <Link className={styles.linkButton} to={`/app/${businessId}/signals`}>
            Signals Center
          </Link>
        </div>

        <div className={styles.card}>
          <div className={styles.cardTitle}>Active alerts</div>
          {signalsLoading && <div className={styles.muted}>Loading alerts…</div>}
          {signalsErr && <div className={styles.error}>{signalsErr}</div>}
          {!signalsLoading && !signalsErr && (
            <>
              <div className={styles.alertCount}>{alertCount}</div>
              <div className={styles.alertMeta}>
                {Object.keys(alertCountsBySeverity).length === 0 && (
                  <span>All clear.</span>
                )}
                {Object.entries(alertCountsBySeverity).map(([severity, count]) => (
                  <span key={severity}>
                    {severity}: {count}
                  </span>
                ))}
              </div>
            </>
          )}
        </div>

        <div className={styles.card}>
          <div className={styles.cardTitle}>Health score</div>
          {healthScoreLoading && <div className={styles.muted}>Loading health score…</div>}
          {healthScoreErr && <div className={styles.error}>{healthScoreErr}</div>}
          {!healthScoreLoading && !healthScoreErr && healthScore && (
            <div className={styles.scoreCard}>
              <div className={styles.scoreValue}>{Math.round(healthScore.score)}</div>
              <div className={styles.scoreMeta}>
                {healthScore.domains.map((domain) => (
                  <span key={domain.domain}>
                    {domain.domain}: {Math.round(domain.score)}
                  </span>
                ))}
              </div>
              <div className={styles.scoreContributors}>
                {healthScore.contributors.slice(0, 3).map((item) => (
                  <div key={item.signal_id} className={styles.scoreContributor}>
                    <span>{signalTitleById.get(item.signal_id) ?? item.signal_id}</span>
                    <span>-{item.penalty.toFixed(1)}</span>
                  </div>
                ))}
              </div>
              <button
                type="button"
                className={styles.linkButton}
                onClick={() => setBreakdownOpen(true)}
              >
                View breakdown
              </button>
            </div>
          )}
        </div>

        <div className={styles.card}>
          <div className={styles.cardTitle}>Active alerts list</div>
          {!signalsLoading && topAlerts.length === 0 && (
            <div className={styles.muted}>No active alerts.</div>
          )}
          <div className={styles.alertList}>
            {topAlerts.map((signal) => (
              <button
                key={signal.id}
                type="button"
                className={`${styles.alertRow} ${
                  selectedSignalId === signal.id ? styles.alertRowActive : ""
                }`}
                onClick={() => handleSelectSignal(signal.id)}
              >
                <div>
                  <div className={styles.alertTitle}>{signal.title ?? signal.id}</div>
                  <div className={styles.alertSubtitle}>
                    {signal.status.replace(/_/g, " ")} · {signal.severity ?? "—"}
                  </div>
                </div>
                <span className={styles.alertChevron}>›</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className={styles.mainPanel}>
        <div className={styles.card}>
          <div className={styles.cardTitle}>Current alerts summary</div>
          <p className={styles.cardBody}>
            Tracking {alertCount} active alerts for business {businessId}. Select an alert to
            view deterministic evidence and recent audit context.
          </p>
        </div>

        {selectedSignalId && (
          <div className={styles.card}>
            <div className={styles.cardTitle}>Explain signal</div>
            {explainLoading && <div className={styles.muted}>Loading explain data…</div>}
            {explainErr && <div className={styles.error}>{explainErr}</div>}
            {!explainLoading && explain && (
              <>
                <div className={styles.explainHeader}>
                  <div>
                    <div className={styles.explainTitle}>{explain.detector.title}</div>
                    <div className={styles.explainMeta}>
                      <span>Status: {explain.state.status.replace(/_/g, " ")}</span>
                      <span>Severity: {explain.state.severity ?? "—"}</span>
                      <span>Domain: {formatDomainLabel(explain.detector.domain)}</span>
                      <span>Updated: {formatDate(explain.state.updated_at)}</span>
                    </div>
                  </div>
                </div>

                <div className={styles.explainSection}>
                  <div className={styles.sectionLabel}>Evidence</div>
                  {explain.evidence.length === 0 && (
                    <div className={styles.muted}>No evidence available.</div>
                  )}
                  <ul className={styles.evidenceList}>
                    {explain.evidence.map((item) => {
                      const filters = buildLedgerFilters(item.anchors ?? null);
                      const ledgerLink =
                        filters && businessId ? ledgerPath(businessId, filters) : null;
                      return (
                        <li key={item.key} className={styles.evidenceItem}>
                          <div>
                            <div className={styles.evidenceLabel}>{item.label}</div>
                            <div className={styles.evidenceValue}>{String(item.value)}</div>
                            {item.anchors && (
                              <div className={styles.evidenceAnchor}>
                                {item.anchors.date_start && item.anchors.date_end && (
                                  <span>
                                    Ledger window: {item.anchors.date_start} →{" "}
                                    {item.anchors.date_end}
                                  </span>
                                )}
                                {item.anchors.vendor && (
                                  <span>Vendor: {item.anchors.vendor}</span>
                                )}
                                {item.anchors.category && (
                                  <span>Category: {item.anchors.category}</span>
                                )}
                                {ledgerLink && (
                                  <Link className={styles.anchorLink} to={ledgerLink}>
                                    View in ledger
                                  </Link>
                                )}
                                {(item.anchors.txn_ids?.length ||
                                  (item.anchors.date_start && item.anchors.date_end)) && (
                                  <button
                                    type="button"
                                    className={styles.anchorButton}
                                    onClick={() => handleOpenTrace(item.anchors ?? null)}
                                  >
                                    View transactions
                                  </button>
                                )}
                              </div>
                            )}
                          </div>
                          <span className={styles.evidenceSource}>{item.source}</span>
                        </li>
                      );
                    })}
                  </ul>
                </div>

                <div className={styles.explainSection}>
                  <div className={styles.sectionLabel}>Related audits</div>
                  {explain.related_audits.length === 0 && (
                    <div className={styles.muted}>No recent audit activity.</div>
                  )}
                  <ul className={styles.auditList}>
                    {explain.related_audits.map((audit) => (
                      <li key={audit.id} className={styles.auditItem}>
                        <Link
                          to={`/app/${businessId}/categorize?auditId=${audit.id}#recent-changes`}
                          className={styles.auditLink}
                        >
                          {audit.event_type.replace(/_/g, " ")}
                        </Link>
                        <span className={styles.auditMeta}>
                          {audit.actor ?? "system"} · {formatDate(audit.created_at)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className={styles.explainSection}>
                  <div className={styles.sectionLabel}>Actions</div>
                  <div className={styles.actionChips}>
                    {ACTIONS.map((action) => (
                      <button
                        key={action.status}
                        type="button"
                        className={styles.actionChip}
                        onClick={() => setActiveAction(action)}
                      >
                        {action.label}
                      </button>
                    ))}
                  </div>

                  {activeAction && (
                    <div className={styles.actionForm}>
                      <div className={styles.actionFormTitle}>
                        {activeAction.label} requires actor and reason.
                      </div>
                      <label className={styles.field}>
                        Actor
                        <input
                          className={styles.input}
                          type="text"
                          value={actor}
                          onChange={(event) => setActor(event.target.value)}
                          placeholder="Name"
                        />
                      </label>
                      <label className={styles.field}>
                        Reason
                        <textarea
                          className={styles.textarea}
                          value={reason}
                          onChange={(event) => setReason(event.target.value)}
                          placeholder="Why are you updating this signal?"
                          rows={3}
                        />
                      </label>
                      <div className={styles.actionButtons}>
                        <button
                          type="button"
                          className={styles.secondaryButton}
                          onClick={() => setActiveAction(null)}
                          disabled={actionSaving}
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          className={styles.primaryButton}
                          onClick={handleActionSubmit}
                          disabled={actionSaving || !actor.trim() || !reason.trim()}
                        >
                          {actionSaving ? "Saving…" : "Confirm update"}
                        </button>
                      </div>
                    </div>
                  )}

                  {actionMsg && <div className={styles.success}>{actionMsg}</div>}
                  {actionErr && <div className={styles.error}>{actionErr}</div>}
                </div>
              </>
            )}
          </div>
        )}
      </div>

      <HealthScoreBreakdownDrawer
        open={breakdownOpen}
        onClose={() => setBreakdownOpen(false)}
        score={healthScore}
        getSignalLabel={(signalId) => signalTitleById.get(signalId) ?? null}
        onSelectSignal={(signalId) => {
          handleSelectSignal(signalId);
          setBreakdownOpen(false);
        }}
      />

      <LedgerTraceDrawer
        open={traceOpen}
        onClose={() => setTraceOpen(false)}
        businessId={businessId}
        anchors={traceAnchors}
      />
    </div>
  );
}
