import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import Drawer from "../../components/common/Drawer";
import { getAuditLog, type AuditLogOut } from "../../api/audit";
import { fetchHealthScore, type HealthScoreOut } from "../../api/healthScore";
import {
  fetchSignals,
  getSignalDetail,
  getSignalExplain,
  listSignalStates,
  type Signal,
  type SignalSeverity,
  type SignalState,
  type SignalStateDetail,
  type SignalExplainLedgerAnchor,
} from "../../api/signals";
import { getMonitorStatus, type MonitorStatus } from "../../api/monitor";
import styles from "./SignalsCenter.module.css";
import HealthScoreBreakdownDrawer from "../../components/health-score/HealthScoreBreakdownDrawer";
import { Button, Chip, EmptyState, InlineAlert, LoadingState, Panel } from "../../components/ui";
import TransactionDetailDrawer from "../../components/transactions/TransactionDetailDrawer";
import FilterBar from "../../components/common/FilterBar";
import { useFilters } from "../../app/filters/useFilters";
import { resolveDateRange, type FilterState } from "../../app/filters/filters";
import { useAppState } from "../../app/state/appState";
import { ledgerPath } from "../../app/routes/routeUtils";
import LedgerTraceDrawer from "../../components/ledger/LedgerTraceDrawer";
import { ApiError } from "../../api/client";
import { useAuth } from "../../app/auth/AuthContext";
import { createActionFromSignal } from "../../api/actions";
import DataStatusStrip from "../../components/status/DataStatusStrip";

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

type LoadError = { message: string; status?: number };

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

function joinListParam(values?: string[] | null) {
  if (!values || values.length === 0) return undefined;
  return values.slice().sort((a, b) => a.localeCompare(b)).join(",");
}

function anchorToLedgerFilters(anchor: SignalExplainLedgerAnchor | null): FilterState | null {
  if (!anchor || !anchor.query) return null;
  const query = anchor.query;
  const filters: FilterState = {};
  if (query.start_date && query.end_date) {
    filters.start = query.start_date;
    filters.end = query.end_date;
    filters.window = undefined;
  }
  const accountParam = joinListParam(query.accounts ?? undefined);
  if (accountParam) filters.account = accountParam;
  const vendorParam = joinListParam(query.vendors ?? undefined);
  if (vendorParam) filters.vendor = vendorParam;
  const categoryParam = joinListParam(query.categories ?? undefined);
  if (categoryParam) filters.category = categoryParam;
  if (query.search) filters.q = query.search;
  if (query.direction) filters.direction = query.direction;
  const highlightParam = joinListParam(query.source_event_ids ?? undefined);
  if (highlightParam) {
    filters.highlight_source_event_ids = highlightParam;
    if (query.source_event_ids && query.source_event_ids.length === 1) {
      filters.anchor_source_event_id = query.source_event_ids[0] ?? undefined;
    }
  }
  return filters;
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

function RelatedChanges({
  businessId,
  onSelect,
}: {
  businessId: string;
  onSelect: (auditId: string) => void;
}) {
  const { logout } = useAuth();
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
    if (e instanceof ApiError && e.status === 401) {
      logout();
      return;
    }
    setErr(e?.message ?? "Failed to load audit history");
  } finally {
    setLoading(false);
  }
  }, [businessId, logout]);


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
    if (e instanceof ApiError && e.status === 401) {
      logout();
      return;
    }
    setErr(e?.message ?? "Failed to load more audit history");
  } finally {
    setLoadingMore(false);
  }
}, [businessId, loadingMore, logout, nextCursor]);


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
      {err && (
        <InlineAlert tone="error" title="Unable to load related changes" description={err} />
      )}

      {!loading && !err && (
        <div className={styles.auditList}>
          {items.length === 0 && (
            <EmptyState title="No related changes yet" description="Signal activity will appear here." />
          )}
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

const STALE_THRESHOLD_HOURS = 6;

export default function SignalsCenter({ businessId }: { businessId: string }) {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useFilters();
  const { setDateRange, dataVersion } = useAppState();
  const [signals, setSignals] = useState<SignalState[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<LoadError | null>(null);
  const [useLegacyV1, setUseLegacyV1] = useState(false);
  const [selected, setSelected] = useState<SignalState | null>(null);
  const [detail, setDetail] = useState<SignalStateDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailErr, setDetailErr] = useState<LoadError | null>(null);
  const [detailExplain, setDetailExplain] = useState<any | null>(null);
  const [rowActionError, setRowActionError] = useState<string | null>(null);
  const [creatingActionSignalId, setCreatingActionSignalId] = useState<string | null>(null);
  const [detailSourceEventId, setDetailSourceEventId] = useState<string | null>(null);
  const [ledgerTraceOpen, setLedgerTraceOpen] = useState(false);
  const [selectedLedgerAnchor, setSelectedLedgerAnchor] = useState<SignalExplainLedgerAnchor | null>(null);
  const [healthScore, setHealthScore] = useState<HealthScoreOut | null>(null);
  const [healthScoreLoading, setHealthScoreLoading] = useState(false);
  const [healthScoreErr, setHealthScoreErr] = useState<LoadError | null>(null);
  const [breakdownOpen, setBreakdownOpen] = useState(false);
  const [toastMsg] = useState<string | null>(null);
  const [toastAuditId] = useState<string | null>(null);
  const [monitorStatus, setMonitorStatus] = useState<MonitorStatus | null>(null);
  const [monitorLoading, setMonitorLoading] = useState(false);
  const [monitorErr, setMonitorErr] = useState<LoadError | null>(null);
  const resolvedRange = useMemo(() => resolveDateRange(filters), [filters]);
  const selectedSignalIdParam = searchParams.get("signal_id") ?? "";
  const updateSignalParam = useCallback(
    (signalId: string | null) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (signalId) {
          next.set("signal_id", signalId);
        } else {
          next.delete("signal_id");
        }
        return next;
      }, { replace: true });
    },
    [setSearchParams]
  );

  useEffect(() => {
    setDateRange({ start: resolvedRange.start, end: resolvedRange.end });
  }, [resolvedRange.end, resolvedRange.start, setDateRange]);

  const loadSignals = useCallback(async () => {
    if (!businessId) return;
    setLoading(true);
    setErr(null);
    try {
      if (useLegacyV1) {
        const data = await fetchSignals(businessId, {
          start_date: resolvedRange.start,
          end_date: resolvedRange.end,
        });
        setSignals((data.signals ?? []).map(mapLegacySignal));
      } else {
        const data = await listSignalStates(businessId);
        setSignals(data.signals ?? []);
      }
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 401) {
        logout();
        return;
      }
      setErr({ message: e?.message ?? "Failed to load signals", status: e?.status });
    } finally {
      setLoading(false);
    }
  }, [businessId, logout, resolvedRange.end, resolvedRange.start, useLegacyV1]);

  const loadHealthScore = useCallback(async () => {
    if (!businessId) return;
    setHealthScoreLoading(true);
    setHealthScoreErr(null);
    try {
      const data = await fetchHealthScore(businessId);
      setHealthScore(data);
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 401) {
        logout();
        return;
      }
      setHealthScoreErr({ message: e?.message ?? "Failed to load health score", status: e?.status });
    } finally {
      setHealthScoreLoading(false);
    }
  }, [businessId, logout]);

  const loadMonitorStatus = useCallback(async () => {
    if (!businessId) return;
    setMonitorLoading(true);
    setMonitorErr(null);
    try {
      const data = await getMonitorStatus(businessId);
      setMonitorStatus(data);
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 401) {
        logout();
        return;
      }
      setMonitorErr({ message: e?.message ?? "Failed to load monitoring status", status: e?.status });
    } finally {
      setMonitorLoading(false);
    }
  }, [businessId, logout]);

  useEffect(() => {
    loadSignals();
    loadHealthScore();
    loadMonitorStatus();
  }, [loadHealthScore, loadMonitorStatus, loadSignals]);

  useEffect(() => {
    if (useLegacyV1) {
      setSelected(null);
      setDetail(null);
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
        if (e instanceof ApiError && e.status === 401) {
          logout();
          return;
        }
        setDetailErr({ message: e?.message ?? "Failed to load signal details", status: e?.status });
      } finally {
        if (active) setDetailLoading(false);
      }
    }
    loadDetail();
    return () => {
      active = false;
    };
  }, [businessId, logout, selected, useLegacyV1]);

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
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (statusFilter) next.set("status", statusFilter);
      else next.delete("status");
      if (severityFilter) next.set("severity", severityFilter);
      else next.delete("severity");
      if (domainFilter) next.set("domain", domainFilter);
      else next.delete("domain");
      if (textFilter) next.set("search", textFilter);
      else next.delete("search");
      if (hasLedgerAnchors) next.set("has_ledger_anchors", "true");
      else next.delete("has_ledger_anchors");
      return next;
    }, { replace: true });
  }, [domainFilter, hasLedgerAnchors, setSearchParams, severityFilter, statusFilter, textFilter]);

  useEffect(() => {
    if (!selectedSignalIdParam) {
      setSelected(null);
      return;
    }
    const match = signals.find((signal) => signal.id === selectedSignalIdParam) ?? null;
    if (!match) return;
    setSelected(match);
  }, [selectedSignalIdParam, signals]);

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
        if (!signal.has_ledger_anchors) return false;
      }
      return true;
    });
  }, [domainFilter, hasLedgerAnchors, signals, severityFilter, statusFilter, textFilter]);

  const handlePrimaryAction = useCallback(
    async (signalId: string, linkedActionId?: string | null) => {
      if (!businessId || !signalId) return;
      setRowActionError(null);
      if (linkedActionId) {
        navigate(`/app/${businessId}/advisor?action_id=${encodeURIComponent(linkedActionId)}`);
        return;
      }
      setCreatingActionSignalId(signalId);
      try {
        const response = await createActionFromSignal(businessId, signalId);
        await loadSignals();
        navigate(`/app/${businessId}/advisor?action_id=${encodeURIComponent(response.action_id)}`);
      } catch (e: any) {
        setRowActionError(e?.message ?? "Unable to create action from signal.");
      } finally {
        setCreatingActionSignalId(null);
      }
    },
    [businessId, loadSignals, navigate]
  );

  const handleAuditSelect = (auditId: string) => {
    navigate(`/app/${businessId}/categorize?auditId=${auditId}#recent-changes`);
  };

  const evidenceTxns = useMemo(() => {
    const entries = new Map<string, { id: string; label?: string; source?: string }>();
    const add = (value: unknown, label?: string, source?: string) => {
      if (typeof value !== "string") return;
      const trimmed = value.trim();
      if (!trimmed) return;
      const existing = entries.get(trimmed);
      if (existing) {
        entries.set(trimmed, { ...existing, label: existing.label ?? label, source: existing.source ?? source });
        return;
      }
      entries.set(trimmed, { id: trimmed, label, source });
    };
    const payload = detail?.payload_json ?? null;
    if (payload && typeof payload === "object") {
      const txnIds = (payload as any).txn_ids;
      const evidenceIds = (payload as any).evidence_source_event_ids;
      const evidenceTxnIds = (payload as any).evidence_txn_ids;
      if (Array.isArray(txnIds)) {
        txnIds.forEach((id) => add(id, "Detector evidence", "payload"));
      }
      if (Array.isArray(evidenceIds)) {
        evidenceIds.forEach((id: unknown) => add(id, "Detector evidence", "payload"));
      }
      if (Array.isArray(evidenceTxnIds)) {
        evidenceTxnIds.forEach((id: unknown) => add(id, "Detector evidence", "payload"));
      }
      add((payload as any).ledger_anchor, "Ledger anchor", "payload");
      add((payload as any).txn_id, "Detector evidence", "payload");
      add((payload as any).source_event_id, "Detector evidence", "payload");
    }
    const evidence = detailExplain?.evidence ?? [];
    if (Array.isArray(evidence)) {
      evidence.forEach((item: any) => {
        const anchors = item?.anchors ?? null;
        const sourceEventIds = anchors?.source_event_ids;
        if (Array.isArray(sourceEventIds)) {
          sourceEventIds.forEach((id: unknown) => add(id, item?.label ?? "Evidence", item?.source));
        }
      });
    }
    return Array.from(entries.values());
  }, [detail?.payload_json, detailExplain?.evidence]);

  const anchorFromEvidence = useMemo(() => evidenceTxns[0]?.id ?? null, [evidenceTxns]);
  const ledgerAnchors = useMemo(
    () => (Array.isArray(detailExplain?.ledger_anchors) ? detailExplain?.ledger_anchors : []) as SignalExplainLedgerAnchor[],
    [detailExplain?.ledger_anchors]
  );
  const primaryLedgerAnchor = ledgerAnchors[0] ?? null;
  const ledgerFilters = useMemo(
    () => anchorToLedgerFilters(primaryLedgerAnchor),
    [primaryLedgerAnchor]
  );
  const isStale =
    monitorStatus?.stale ??
    (monitorStatus?.last_pulse_at
      ? (Date.now() - Date.parse(monitorStatus.last_pulse_at)) / (1000 * 60 * 60) > STALE_THRESHOLD_HOURS
      : false);

  return (
    <div className={styles.container}>
      <DataStatusStrip businessId={businessId} refreshKey={dataVersion} />
      <Panel className={styles.scoreHeader}>
        <div>
          <div className={styles.scoreTitle}>Health score</div>
          {healthScoreLoading && <div className={styles.scoreMuted}>Loading…</div>}
          {healthScoreErr && (
            <InlineAlert tone="error" title="Unable to load health score" description={healthScoreErr.message} />
          )}
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
        <div className={styles.monitoringPanel}>
          <div className={styles.monitoringTitle}>Monitoring</div>
          {monitorLoading && <div className={styles.scoreMuted}>Loading status…</div>}
          {monitorErr && (
            <InlineAlert tone="error" title="Unable to load monitoring" description={monitorErr.message} />
          )}
          {!monitorLoading && !monitorErr && monitorStatus && (
            <div className={styles.monitoringBody}>
              <div className={styles.monitoringRow}>
                <span>Last pulse</span>
                <span className={styles.monitoringValue}>
                  {formatDate(monitorStatus.last_pulse_at)}
                  {isStale && <span className={styles.staleBadge}>Stale</span>}
                </span>
              </div>
              <div className={styles.monitoringRow}>
                <span>Newest cursor</span>
                <span>
                  {formatDate(monitorStatus.newest_event_at)} ·{" "}
                  {(monitorStatus.newest_event_source_event_id ?? "—").slice(-6)}
                </span>
              </div>
              <div className={styles.monitoringRow}>
                <span>Open signals</span>
                <span>{monitorStatus.open_count}</span>
              </div>
              <div className={styles.monitoringRow}>
                <span>Status counts</span>
                <span>
                  {Object.entries(monitorStatus.counts.by_status)
                    .map(([key, value]) => `${key}: ${value}`)
                    .join(" · ") || "—"}
                </span>
              </div>
              <div className={styles.monitoringRow}>
                <span>Severity counts</span>
                <span>
                  {Object.entries(monitorStatus.counts.by_severity)
                    .map(([key, value]) => `${key}: ${value}`)
                    .join(" · ") || "—"}
                </span>
              </div>
              {monitorStatus.gated && (
                <div className={styles.monitoringGate}>
                  {monitorStatus.gating_reason}
                  {monitorStatus.gating_reason_code ? ` (${monitorStatus.gating_reason_code})` : ""}
                </div>
              )}
              {isStale && monitorStatus.stale_reason && (
                <div className={styles.monitoringGate}>{monitorStatus.stale_reason}</div>
              )}
            </div>
          )}
        </div>
      </Panel>
      <FilterBar
        filters={filters}
        onChange={setFilters}
        showAccountFilter={false}
        showCategoryFilter={false}
        showSearch={false}
      />
      <div className={styles.microcopy}>
        Signals show what the system detects. They don’t require action until you create an action.
      </div>
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
          Legacy signals are read-only. Switch off to view details.
        </div>
      )}
      {rowActionError && <InlineAlert tone="error" title="Signal action unavailable" description={rowActionError} />}

      {loading && <LoadingState label="Loading signals…" />}
      {err?.status === 403 && (
        <EmptyState
          title="You don’t have access"
          description="Ask an admin to grant access to this business."
        />
      )}
      {err && err.status !== 403 && (
        <InlineAlert tone="error" title="Unable to load signals" description={err.message} />
      )}

      {!loading && !err && (
        <div className={styles.list}>
          {filteredSignals.length === 0 && (
            <EmptyState
              title="No signals match filters"
              description="Adjust filters or check back after the next monitoring run."
            />
          )}
          {filteredSignals.map((signal) => (
            <div
              key={signal.id}
              role="button"
              tabIndex={useLegacyV1 ? -1 : 0}
              className={`${styles.row} ${selected?.id === signal.id ? styles.rowActive : ""} ${
                useLegacyV1 ? styles.rowDisabled : ""
              }`}
              onClick={() => {
                if (useLegacyV1) return;
                setSelected(signal);
                updateSignalParam(signal.id);
              }}
              onKeyDown={(event) => {
                if (useLegacyV1) return;
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setSelected(signal);
                  updateSignalParam(signal.id);
                }
              }}
              aria-disabled={useLegacyV1}
            >
              <span className={`${styles.severityBadge} ${severityClass(signal.severity)}`}>
                {signal.severity ?? "—"}
              </span>
              <div className={styles.rowMain}>
                <div className={styles.rowTitle}>{signal.title ?? signal.type ?? "Signal"}</div>
                <div className={styles.rowDomain}>{formatDomainLabel(signal.domain)}</div>
                <div className={styles.rowSummary}>{signal.summary ?? "—"}</div>
                {!useLegacyV1 && (
                  <div className={styles.rowActions} onClick={(event) => event.stopPropagation()}>
                    <button
                      className={styles.secondaryButton}
                      type="button"
                      onClick={() => {
                        setSelected(signal);
                        updateSignalParam(signal.id);
                      }}
                    >
                      Explain
                    </button>
                    <button
                      className={styles.primaryButton}
                      type="button"
                      onClick={() => void handlePrimaryAction(signal.id, signal.linked_action_id)}
                      disabled={creatingActionSignalId === signal.id}
                    >
                      {creatingActionSignalId === signal.id
                        ? "Opening…"
                        : signal.linked_action_id
                          ? "Open in Inbox"
                          : "Create Action"}
                    </button>
                  </div>
                )}
              </div>
              <div className={styles.rowMeta}>
                <div className={styles.metaLabel}>Last evaluated</div>
                <div>{formatDate(signal.updated_at)}</div>
                <div className={styles.statusPill}>{STATUS_LABELS[signal.status] ?? signal.status}</div>
              </div>
            </div>
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
        onClose={() => {
          setSelected(null);
          updateSignalParam(null);
        }}
      >
        {detailLoading && <LoadingState label="Loading signal details…" />}
        {detailErr?.status === 403 && (
          <EmptyState title="Access restricted" description="You don’t have permission to view this signal." />
        )}
        {detailErr && detailErr.status !== 403 && (
          <InlineAlert tone="error" title="Unable to load signal detail" description={detailErr.message} />
        )}

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
              <Chip tone="neutral">{STATUS_LABELS[detail.status] ?? detail.status}</Chip>
              {ledgerFilters && (
                <Link className={styles.secondaryButton} to={ledgerPath(businessId, ledgerFilters)}>
                  View in Ledger
                </Link>
              )}
              {primaryLedgerAnchor && (
                <button
                  type="button"
                  className={styles.secondaryButton}
                  onClick={() => {
                    setSelectedLedgerAnchor(primaryLedgerAnchor);
                    setLedgerTraceOpen(true);
                  }}
                >
                  View ledger trace
                </button>
              )}
              {anchorFromEvidence && (
                <Link
                  className={styles.secondaryButton}
                  to={`/app/${businessId}/ledger?anchor_source_event_id=${encodeURIComponent(anchorFromEvidence)}`}
                >
                  Highlight evidence
                </Link>
              )}
            </div>

            {detailExplain?.explanation && (
              <div>
                <div className={styles.sectionTitle}>Explanation</div>
                <div className={styles.detailSummary}>{detailExplain.explanation.observation}</div>
                <div className={styles.explanationGrid}>
                  <div>
                    <div className={styles.explanationLabel}>Evidence counts</div>
                    <ul className={styles.explanationList}>
                      {Object.entries(detailExplain.explanation.evidence?.counts ?? {}).map(([key, value]) => (
                        <li key={key}>
                          <strong>{key}:</strong> {String(value)}
                        </li>
                      ))}
                      {Object.keys(detailExplain.explanation.evidence?.counts ?? {}).length === 0 && (
                        <li>—</li>
                      )}
                    </ul>
                  </div>
                  <div>
                    <div className={styles.explanationLabel}>Evidence deltas</div>
                    <ul className={styles.explanationList}>
                      {Object.entries(detailExplain.explanation.evidence?.deltas ?? {}).map(([key, value]) => (
                        <li key={key}>
                          <strong>{key}:</strong> {String(value)}
                        </li>
                      ))}
                      {Object.keys(detailExplain.explanation.evidence?.deltas ?? {}).length === 0 && (
                        <li>—</li>
                      )}
                    </ul>
                  </div>
                  <div>
                    <div className={styles.explanationLabel}>Evidence rows</div>
                    <div className={styles.detailSummary}>
                      {(detailExplain.explanation.evidence?.rows ?? []).length} linked rows
                    </div>
                  </div>
                </div>
                <div className={styles.detailSummary}>{detailExplain.explanation.implication}</div>
              </div>
            )}

            {ledgerAnchors.length > 0 && (
              <div>
                <div className={styles.sectionTitle}>Ledger anchors</div>
                <div className={styles.detailSummary}>Click an anchor to inspect the ledger window.</div>
                <div className={styles.auditList}>
                  {ledgerAnchors.map((anchor) => (
                    <div key={anchor.label} className={styles.auditRow}>
                      <div>
                        <div className={styles.auditEvent}>{anchor.label}</div>
                        <div className={styles.auditMeta}>
                          {anchor.query?.start_date && anchor.query?.end_date
                            ? `${anchor.query.start_date} → ${anchor.query.end_date}`
                            : "Transaction set"}
                        </div>
                      </div>
                      <div className={styles.statusActions}>
                        <button
                          type="button"
                          className={styles.secondaryButton}
                          onClick={() => {
                            setSelectedLedgerAnchor(anchor);
                            setLedgerTraceOpen(true);
                          }}
                        >
                          Open trace
                        </button>
                        {anchorToLedgerFilters(anchor) && (
                          <Link
                            className={styles.secondaryButton}
                            to={ledgerPath(businessId, anchorToLedgerFilters(anchor) as FilterState)}
                          >
                            Open ledger
                          </Link>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {evidenceTxns.length > 0 && (
              <div>
                <div className={styles.sectionTitle}>Evidence</div>
                <div className={styles.detailSummary}>Linked transactions from detector output.</div>
                <div className={styles.auditList}>
                  {evidenceTxns.map((item) => (
                    <div key={item.id} className={styles.auditRow}>
                      <div>
                        <div className={styles.auditEvent}>
                          {item.label ?? "Evidence transaction"} · {item.id.slice(-6)}
                        </div>
                        <div className={styles.auditMeta}>{item.source ?? "detector"}</div>
                      </div>
                      <div className={styles.statusActions}>
                        <button
                          type="button"
                          className={styles.secondaryButton}
                          onClick={() => setDetailSourceEventId(item.id)}
                        >
                          View details
                        </button>
                        <Link
                          className={styles.secondaryButton}
                          to={`/app/${businessId}/ledger?anchor_source_event_id=${encodeURIComponent(item.id)}`}
                        >
                          View in Ledger
                        </Link>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

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

      <TransactionDetailDrawer
        open={Boolean(detailSourceEventId)}
        businessId={businessId}
        sourceEventId={detailSourceEventId}
        onClose={() => setDetailSourceEventId(null)}
      />

      <LedgerTraceDrawer
        open={ledgerTraceOpen}
        onClose={() => {
          setLedgerTraceOpen(false);
          setSelectedLedgerAnchor(null);
        }}
        businessId={businessId}
        anchors={selectedLedgerAnchor?.query ?? null}
      />

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
