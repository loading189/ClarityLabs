import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import Drawer from "../../components/common/Drawer";
import { ErrorState, LoadingState } from "../../components/common/DataState";
import { getAuditLog, type AuditLogOut } from "../../api/audit";
import { fetchHealthScore, type HealthScoreOut } from "../../api/healthScore";
import {
  fetchSignals,
  getSignalDetail,
  getSignalExplain,
  listSignalStates,
  updateSignalStatus,
  type Signal,
  type SignalSeverity,
  type SignalState,
  type SignalStateDetail,
  type SignalStatus,
} from "../../api/signals";
import styles from "./SignalsCenter.module.css";
import HealthScoreBreakdownDrawer from "../../components/health-score/HealthScoreBreakdownDrawer";
import { Button, Chip, Panel } from "../../components/ui";

const STATUS_LABELS: Record<string, string> = {
  open: "Open",
  in_progress: "In progress",
  resolved: "Resolved",
  ignored: "Ignored",
};

const SIGNAL_AUDIT_TYPES = new Set([
  "signal_detected",
  "signal_updated",
  "signal_resolved",
  "signal_status_changed",
]);

function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString();
}

function severityClass(severity: string | null) {
  if (severity === "red") return styles.severityRed;
  if (severity === "yellow") return styles.severityYellow;
  if (severity === "green") return styles.severityGreen;
  return styles.severityNeutral;
}

function formatDomainLabel(domain?: string | null) {
  if (!domain) return "—";
  return domain.charAt(0).toUpperCase() + domain.slice(1);
}

function toIsoDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

function buildLegacyDateRange() {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - 30);
  return { start: toIsoDate(start), end: toIsoDate(end) };
}

function mapLegacySignal(signal: Signal): SignalState {
  const title = signal.type.replace(/_/g, " ");
  return {
    id: signal.id,
    type: signal.type,
    severity: signal.severity,
    status: "open",
    title,
    summary: signal.window ? `Window ${signal.window}` : "—",
    updated_at: null,
  };
}

type StatusModalState = {
  open: boolean;
  nextStatus: SignalStatus | null;
};

function RelatedChanges({
  businessId,
  onSelect,
}: {
  businessId: string;
  onSelect: (auditId: string) => void;
}) {
  const [items, setItems] = useState<AuditLogOut[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const DISPLAY_LIMIT = 10;
  const FETCH_LIMIT = 20;

  async function fetchFilteredAuditPage(
    businessId: string,
    cursor?: string | null
  ) {
    const data = await getAuditLog(businessId, {
      limit: FETCH_LIMIT,
      cursor: cursor ?? undefined,
    });
    const filtered = data.items.filter((item) => SIGNAL_AUDIT_TYPES.has(item.event_type));
    return { filtered, nextCursor: data.next_cursor ?? null };
  }


  const load = useCallback(async () => {
  if (!businessId) return;
  setLoading(true);
  setErr(null);

  try {
    let collected: AuditLogOut[] = [];
    let cursor: string | null = null;
    let next: string | null = null;

    // Keep fetching until we have enough filtered items or no more pages
    do {
      const res = await fetchFilteredAuditPage(businessId, cursor);
      collected = collected.concat(res.filtered);
      next = res.nextCursor;
      cursor = next;
    } while (collected.length < DISPLAY_LIMIT && next);

    setItems(collected.slice(0, DISPLAY_LIMIT));
    setNextCursor(next);
  } catch (e: any) {
    setErr(e?.message ?? "Failed to load audit history");
  } finally {
    setLoading(false);
  }
  }, [businessId]);


 const loadMore = useCallback(async () => {
  if (!businessId || !nextCursor || loadingMore) return;
  setLoadingMore(true);
  setErr(null);

  try {
    let collected: AuditLogOut[] = [];
    let cursor: string | null = nextCursor;
    let next: string | null = nextCursor;

    do {
      const res = await fetchFilteredAuditPage(businessId, cursor);
      collected = collected.concat(res.filtered);
      next = res.nextCursor;
      cursor = next;
    } while (collected.length < DISPLAY_LIMIT && next);

    setItems((prev) => prev.concat(collected.slice(0, DISPLAY_LIMIT)));
    setNextCursor(next);
  } catch (e: any) {
    setErr(e?.message ?? "Failed to load more audit history");
  } finally {
    setLoadingMore(false);
  }
}, [businessId, loadingMore, nextCursor]);


  return (
    <div className={styles.auditSection}>
      <div className={styles.auditHeader}>
        <div>
          <div className={styles.auditTitle}>Related changes</div>
          <div className={styles.auditSubtitle}>Latest signal detections and updates.</div>
        </div>
        <Button variant="secondary" className={styles.secondaryButton} type="button" onClick={load}>
          Refresh
        </Button>
      </div>

      {loading && <LoadingState label="Loading related changes…" />}
      {err && <ErrorState label={err} />}

      {!loading && !err && (
        <div className={styles.auditList}>
          {items.length === 0 && <div className={styles.empty}>No related changes yet.</div>}
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              className={styles.auditRow}
              onClick={() => onSelect(item.id)}
            >
              <div>
                <div className={styles.auditEvent}>{item.event_type.replace(/_/g, " ")}</div>
                <div className={styles.auditMeta}>
                  {item.actor} · {formatDate(item.created_at)}
                </div>
              </div>
              <span className={styles.auditLink}>View</span>
            </button>
          ))}
        </div>
      )}

      {nextCursor && (
        <Button
          className={styles.loadMore}
          type="button"
          onClick={loadMore}
          disabled={loadingMore}
        >
          {loadingMore ? "Loading…" : "Load more"}
        </Button>
      )}
    </div>
  );
}

export default function SignalsCenter({ businessId }: { businessId: string }) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [signals, setSignals] = useState<SignalState[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [useLegacyV1, setUseLegacyV1] = useState(false);
  const [selected, setSelected] = useState<SignalState | null>(null);
  const [detail, setDetail] = useState<SignalStateDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailErr, setDetailErr] = useState<string | null>(null);
  const [detailExplain, setDetailExplain] = useState<any | null>(null);
  const [statusModal, setStatusModal] = useState<StatusModalState>({
    open: false,
    nextStatus: null,
  });
  const [healthScore, setHealthScore] = useState<HealthScoreOut | null>(null);
  const [healthScoreLoading, setHealthScoreLoading] = useState(false);
  const [healthScoreErr, setHealthScoreErr] = useState<string | null>(null);
  const [breakdownOpen, setBreakdownOpen] = useState(false);
  const [actor, setActor] = useState("");
  const [reason, setReason] = useState("");
  const [savingStatus, setSavingStatus] = useState(false);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [toastAuditId, setToastAuditId] = useState<string | null>(null);
  const legacyDateRange = useMemo(() => buildLegacyDateRange(), []);

  const loadSignals = useCallback(async () => {
    if (!businessId) return;
    setLoading(true);
    setErr(null);
    try {
      if (useLegacyV1) {
        const data = await fetchSignals(businessId, {
          start_date: legacyDateRange.start,
          end_date: legacyDateRange.end,
        });
        setSignals((data.signals ?? []).map(mapLegacySignal));
      } else {
        const data = await listSignalStates(businessId);
        setSignals(data.signals ?? []);
      }
    } catch (e: any) {
      setErr(e?.message ?? "Failed to load signals");
    } finally {
      setLoading(false);
    }
  }, [businessId, legacyDateRange.end, legacyDateRange.start, useLegacyV1]);

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

  useEffect(() => {
    loadSignals();
    loadHealthScore();
  }, [loadHealthScore, loadSignals]);

  useEffect(() => {
    if (useLegacyV1) {
      setSelected(null);
      setDetail(null);
      setStatusModal({ open: false, nextStatus: null });
      setActor("");
      setReason("");
      setStatusFilter("");
      return;
    }
    const selectedId = selected?.id;
    if (!selectedId) {
      setDetail(null);
      setDetailExplain(null);
      return;
    }
    const resolvedId = selectedId;
    let active = true;
    async function loadDetail() {
      setDetailLoading(true);
      setDetailErr(null);
      try {
        const [data, explainData] = await Promise.all([
          getSignalDetail(businessId, resolvedId),
          getSignalExplain(businessId, resolvedId),
        ]);
        if (!active) return;
        setDetail(data);
        setDetailExplain(explainData);
      } catch (e: any) {
        if (!active) return;
        setDetailErr(e?.message ?? "Failed to load signal details");
      } finally {
        if (active) setDetailLoading(false);
      }
    }
    loadDetail();
    return () => {
      active = false;
    };
  }, [businessId, selected, useLegacyV1]);

  const [statusFilter, setStatusFilter] = useState(searchParams.get("status") ?? "");
  const [severityFilter, setSeverityFilter] = useState(searchParams.get("severity") ?? "");
  const [domainFilter, setDomainFilter] = useState(searchParams.get("domain") ?? "");
  const [textFilter, setTextFilter] = useState(searchParams.get("search") ?? "");
  const [hasLedgerAnchors, setHasLedgerAnchors] = useState(searchParams.get("has_ledger_anchors") === "true");

  const filterOptions = useMemo(() => {
    const domains = Array.from(
      new Set(
        signals
          .map((signal) => signal.domain)
          .filter((domain): domain is string => Boolean(domain))
      )
    );
    const severities = Array.from(
      new Set(
        signals
          .map((signal) => signal.severity)
          .filter((severity): severity is SignalSeverity => Boolean(severity))
      )
    );
    return { domains, severities };
  }, [signals]);

  useEffect(() => {
    const next = new URLSearchParams();
    if (statusFilter) next.set("status", statusFilter);
    if (severityFilter) next.set("severity", severityFilter);
    if (domainFilter) next.set("domain", domainFilter);
    if (textFilter) next.set("search", textFilter);
    if (hasLedgerAnchors) next.set("has_ledger_anchors", "true");
    setSearchParams(next, { replace: true });
  }, [domainFilter, hasLedgerAnchors, setSearchParams, severityFilter, statusFilter, textFilter]);

  const signalTitleById = useMemo(() => {
    return new Map(signals.map((signal) => [signal.id, signal.title ?? signal.id]));
  }, [signals]);

  const filteredSignals = useMemo(() => {
    return signals.filter((signal) => {
      if (statusFilter && signal.status !== statusFilter) return false;
      if (severityFilter && signal.severity !== severityFilter) return false;
      if (domainFilter && signal.domain !== domainFilter) return false;
      if (textFilter) {
        const q = textFilter.toLowerCase();
        const haystack = `${signal.title ?? ""} ${signal.summary ?? ""} ${signal.type ?? ""}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      if (hasLedgerAnchors) {
        const payload = (detail?.payload_json as Record<string, unknown> | null) ?? null;
        const hasAnchor = Boolean(payload && (payload["txn_ids"] || payload["ledger_anchor"]));
        if (!hasAnchor && selected?.id === signal.id) return false;
      }
      return true;
    });
  }, [detail?.payload_json, domainFilter, hasLedgerAnchors, selected?.id, signals, severityFilter, statusFilter, textFilter]);

  const openStatusModal = (nextStatus: SignalStatus) => {
    setStatusModal({ open: true, nextStatus });
  };

  const closeStatusModal = () => {
    setStatusModal({ open: false, nextStatus: null });
    setActor("");
    setReason("");
  };

  const handleStatusSubmit = async () => {
    if (useLegacyV1) return;
    if (!selected || !statusModal.nextStatus) return;
    if (!actor.trim() || !reason.trim()) return;
    setSavingStatus(true);
    setToastMsg(null);
    setToastAuditId(null);
    try {
      const result = await updateSignalStatus(businessId, selected.id, {
        status: statusModal.nextStatus,
        actor: actor.trim(),
        reason: reason.trim(),
      });
      setToastAuditId(result.audit_id ?? null);
      setToastMsg(`Status updated to ${STATUS_LABELS[result.status] ?? result.status}.`);
      closeStatusModal();
      await loadSignals();
      await loadHealthScore();
      const detailData = await getSignalDetail(businessId, selected.id);
      setDetail(detailData);
      setSelected((prev) => (prev ? { ...prev, status: result.status } : prev));
    } catch (e: any) {
      setDetailErr(e?.message ?? "Failed to update status");
    } finally {
      setSavingStatus(false);
    }
  };

  const handleAuditSelect = (auditId: string) => {
    navigate(`/app/${businessId}/categorize?auditId=${auditId}#recent-changes`);
  };

  const statusButtons = useMemo<Array<{ label: string; status: SignalStatus }>>(() => {
    if (!detail) return [] as Array<{ label: string; status: SignalStatus }>;
    if (detail.status === "resolved" || detail.status === "ignored") {
      return [{ label: "Reopen", status: "open" }];
    }
    return [
      { label: "Resolve", status: "resolved" },
      { label: "Ignore", status: "ignored" },
    ];
  }, [detail]);

  return (
    <div className={styles.container}>
      <Panel className={styles.scoreHeader}>
        <div>
          <div className={styles.scoreTitle}>Health score</div>
          {healthScoreLoading && <div className={styles.scoreMuted}>Loading…</div>}
          {healthScoreErr && <div className={styles.scoreError}>{healthScoreErr}</div>}
          {!healthScoreLoading && !healthScoreErr && healthScore && (
            <div className={styles.scoreValue}>{Math.round(healthScore.score)}</div>
          )}
        </div>
        {healthScore && (
          <div className={styles.scoreDomains}>
            {healthScore.domains.map((domain) => (
              <Chip key={domain.domain} className={styles.scorePill}>
                {domain.domain}: {Math.round(domain.score)}
              </Chip>
            ))}
          </div>
        )}
        <Button
          type="button"
          variant="primary"
          className={styles.primaryButton}
          onClick={() => setBreakdownOpen(true)}
          disabled={!healthScore}
        >
          View breakdown
        </Button>
      </Panel>
      <div className={styles.filters}>
        <label className={styles.filterField}>
          Status
          <select
            className={styles.select}
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            disabled={useLegacyV1}
          >
            <option value="">All</option>
            <option value="open">Open</option>
            <option value="in_progress">In progress</option>
            <option value="resolved">Resolved</option>
            <option value="ignored">Ignored</option>
          </select>
        </label>
        <label className={styles.filterField}>
          Severity
          <select
            className={styles.select}
            value={severityFilter}
            onChange={(event) => setSeverityFilter(event.target.value)}
          >
            <option value="">All</option>
            {filterOptions.severities.map((severity) => (
              <option key={severity} value={severity}>
                {severity}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.filterField}>
          Domain
          <select
            className={styles.select}
            value={domainFilter}
            onChange={(event) => setDomainFilter(event.target.value)}
          >
            <option value="">All</option>
            {filterOptions.domains.map((domain) => (
              <option key={domain} value={domain}>
                {domain}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.filterField}>
          Search
          <input className={styles.input} value={textFilter} onChange={(e) => setTextFilter(e.target.value)} />
        </label>
        <label className={styles.legacyToggle}>
          <span>Has ledger anchors</span>
          <input type="checkbox" checked={hasLedgerAnchors} onChange={(e) => setHasLedgerAnchors(e.target.checked)} />
        </label>
        <label className={styles.legacyToggle}>
          <span>V1 (legacy)</span>
          <input
            type="checkbox"
            checked={useLegacyV1}
            onChange={(event) => setUseLegacyV1(event.target.checked)}
          />
        </label>
      </div>
      {useLegacyV1 && (
        <div className={styles.legacyNote}>
          Legacy signals are read-only. Switch off to manage statuses and view details.
        </div>
      )}

      {loading && <LoadingState label="Loading signals…" />}
      {err && <ErrorState label={err} />}

      {!loading && !err && (
        <div className={styles.list}>
          {filteredSignals.length === 0 && (
            <div className={styles.empty}>No signals match the selected filters.</div>
          )}
          {filteredSignals.map((signal) => (
            <button
              key={signal.id}
              type="button"
              className={`${styles.row} ${selected?.id === signal.id ? styles.rowActive : ""} ${
                useLegacyV1 ? styles.rowDisabled : ""
              }`}
              onClick={() => {
                if (useLegacyV1) return;
                setSelected(signal);
              }}
              disabled={useLegacyV1}
            >
              <span className={`${styles.severityBadge} ${severityClass(signal.severity)}`}>
                {signal.severity ?? "—"}
              </span>
              <div className={styles.rowMain}>
                <div className={styles.rowTitle}>{signal.title ?? signal.type ?? "Signal"}</div>
                <div className={styles.rowDomain}>{formatDomainLabel(signal.domain)}</div>
                <div className={styles.rowSummary}>{signal.summary ?? "—"}</div>
              </div>
              <div className={styles.rowMeta}>
                <div>{formatDate(signal.updated_at)}</div>
                <div className={styles.statusPill}>{STATUS_LABELS[signal.status] ?? signal.status}</div>
              </div>
            </button>
          ))}
        </div>
      )}

      {toastMsg && (
        <div className={styles.toast}>
          <span>{toastMsg}</span>
          {toastAuditId && (
            <button
              type="button"
              className={styles.toastLink}
              onClick={() => handleAuditSelect(toastAuditId)}
            >
              View in Recent Changes
            </button>
          )}
        </div>
      )}

      <Drawer
        open={Boolean(selected)}
        title="Signal details"
        onClose={() => setSelected(null)}
      >
        {detailLoading && <LoadingState label="Loading signal details…" />}
        {detailErr && <ErrorState label={detailErr} />}

        {!detailLoading && !detailErr && detail && (
          <div className={styles.detailContent}>
            <div>
              <div className={styles.detailTitle}>{detail.title ?? detail.type ?? "Signal"}</div>
              <div className={styles.detailSummary}>{detail.summary ?? "—"}</div>
              <div className={styles.detailMeta}>
                <span>Status: {STATUS_LABELS[detail.status] ?? detail.status}</span>
                <span>Domain: {formatDomainLabel(detail.domain)}</span>
                <span>Last updated: {formatDate(detail.updated_at)}</span>
              </div>
            </div>

            <div className={styles.statusActions}>
              {statusButtons.map((btn) => (
                <button
                  key={btn.status}
                  className={styles.primaryButton}
                  type="button"
                  onClick={() => openStatusModal(btn.status)}
                >
                  {btn.label}
                </button>
              ))}
              {detail && (
                <Link
                  className={styles.secondaryButton}
                  to={`/app/${businessId}/assistant?signalId=${detail.id}`}
                >
                  Open in Assistant
                </Link>
              )}
              {detail && (
                <Link
                  className={styles.secondaryButton}
                  to={`/app/${businessId}/assistant?signalId=${detail.id}&createPlanSignalId=${detail.id}`}
                >
                  Create plan
                </Link>
              )}
            </div>

            <div>
              <div className={styles.sectionTitle}>What resolves this</div>
              <div className={styles.detailSummary}>{detailExplain?.clear_condition?.summary ?? "Resolution criteria not defined."}</div>
            </div>

            <div>
              <div className={styles.sectionTitle}>Payload</div>
              <pre className={styles.payload}>
                {JSON.stringify(detail.payload_json ?? {}, null, 2)}
              </pre>
            </div>

            <RelatedChanges businessId={businessId} onSelect={handleAuditSelect} />
          </div>
        )}
      </Drawer>

      {statusModal.open && (
        <div className={styles.modalOverlay} role="dialog" aria-modal="true">
          <div className={styles.modal}>
            <div className={styles.modalHeader}>
              <div>
                <div className={styles.modalTitle}>Update status</div>
                <div className={styles.modalSubtitle}>
                  Provide who is making this change and why.
                </div>
              </div>
              <button type="button" className={styles.modalClose} onClick={closeStatusModal}>
                Close
              </button>
            </div>
            <div className={styles.modalBody}>
              <label className={styles.modalField}>
                Actor
                <input
                  className={styles.input}
                  type="text"
                  value={actor}
                  onChange={(event) => setActor(event.target.value)}
                  placeholder="Name"
                />
              </label>
              <label className={styles.modalField}>
                Reason
                <textarea
                  className={styles.textarea}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder="Why are you updating this signal?"
                />
              </label>
              <div className={styles.modalActions}>
                <button
                  className={styles.secondaryButton}
                  type="button"
                  onClick={closeStatusModal}
                  disabled={savingStatus}
                >
                  Cancel
                </button>
                <button
                  className={styles.primaryButton}
                  type="button"
                  onClick={handleStatusSubmit}
                  disabled={savingStatus || !actor.trim() || !reason.trim()}
                >
                  {savingStatus ? "Saving…" : "Confirm update"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <HealthScoreBreakdownDrawer
        open={breakdownOpen}
        onClose={() => setBreakdownOpen(false)}
        score={healthScore}
        getSignalLabel={(signalId) => signalTitleById.get(signalId) ?? null}
        onSelectSignal={(signalId) => {
          const match = signals.find((signal) => signal.id === signalId);
          if (match && !useLegacyV1) {
            setSelected(match);
          }
          setBreakdownOpen(false);
        }}
      />
    </div>
  );
}
